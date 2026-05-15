import os
import uuid
import json
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

CST = timezone(timedelta(hours=8))

def now_cst():
    return datetime.now(CST).replace(tzinfo=None)

from flask import (
    Flask, render_template, request, redirect, url_for,
    abort, flash, jsonify, send_file, session
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload
import pandas as pd
from io import BytesIO

app = Flask(__name__)
ADMIN_PASSWORD = "1234567890"
PRIZE_CATEGORIES = ["实物奖品", "e卡", "优惠券", "虚拟权益", "其他"]
PHYSICAL_CATEGORY_ALIASES = {
    "挂件", "卡套", "毛绒挂件", "盲盒", "帆布袋", "笔记本",
    "实物", "周边", "实物奖品",
}


@app.template_filter("from_json")
def from_json_filter(s):
    try:
        return json.loads(s) if s else []
    except (json.JSONDecodeError, TypeError):
        return []


@app.template_filter("photo_src")
def photo_src_filter(photo):
    if not photo:
        return ""
    if isinstance(photo, str) and photo.startswith("data:image/"):
        return photo
    return url_for("serve_upload", filename=photo.replace("uploads/", ""))


def save_photo_data(photo):
    if not photo or not photo.filename:
        return None
    ext = os.path.splitext(photo.filename)[1].lower()
    mime_by_ext = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_by_ext.get(ext)
    if not mime:
        return None
    data = photo.read()
    if not data:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def remember_application(application):
    session["applicant"] = application.applicant
    tokens = session_tokens()
    if application.token not in tokens:
        tokens.insert(0, application.token)
    session["application_tokens"] = tokens[:50]


def session_tokens():
    tokens = session.get("application_tokens", [])
    if isinstance(tokens, str):
        tokens = [tokens]
    if not isinstance(tokens, list):
        tokens = []
    return [str(token) for token in tokens if token]


def can_manage_application(application):
    if session.get("role") == "admin":
        return True
    tokens = session_tokens()
    applicant = session.get("applicant", "")
    return application.token in tokens or (
        applicant and applicant == application.applicant
    )


def normalize_prize_category(category):
    category = (category or "").strip()
    if not category:
        return "其他"
    if category in PHYSICAL_CATEGORY_ALIASES:
        return "实物奖品"
    if category.lower() in {"e卡", "e-card", "ecard", "京东e卡", "京东卡"}:
        return "e卡"
    if category in PRIZE_CATEGORIES:
        return category
    return "其他"
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "prize-manager-session-key"
)

_is_vercel = os.environ.get("VERCEL", False)
_base_dir = "/tmp" if _is_vercel else os.path.dirname(__file__)

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(_base_dir, 'prize_manager.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(_base_dir, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

db = SQLAlchemy(app)
_tables_ready = False


@app.before_request
def ensure_tables():
    global _tables_ready
    if app.config.get("TESTING"):
        db.create_all()
        return
    if not _tables_ready:
        db.create_all()
        normalize_existing_prize_categories()
        _tables_ready = True


def normalize_existing_prize_categories():
    changed = False
    for prize in Prize.query.all():
        normalized = normalize_prize_category(prize.category)
        if prize.category != normalized:
            prize.category = normalized
            changed = True
    if changed:
        db.session.commit()


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def safe_back_url(default_endpoint="index"):
    referrer = request.referrer or ""
    if referrer:
        parsed = urlsplit(referrer)
        same_host = not parsed.netloc or parsed.netloc == request.host
        if same_host and parsed.path not in ("/admin/login", "/admin/logout"):
            return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return url_for(default_endpoint)


@app.context_processor
def inject_role():
    return {
        "is_admin": session.get("role") == "admin",
        "prize_categories": PRIZE_CATEGORIES,
    }


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password", "")
    if password == ADMIN_PASSWORD:
        session["role"] = "admin"
        flash("已切换为管理员", "success")
        return redirect(safe_back_url())
    else:
        flash("密码错误", "danger")
    return redirect(safe_back_url())


@app.route("/admin/logout")
def admin_logout():
    session.pop("role", None)
    flash("已切换为普通用户", "success")
    return redirect(safe_back_url())

# --- Models ---


class Prize(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="未分类")
    unit_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, default=5)
    image_path = db.Column(db.String(200), default=None)
    created_at = db.Column(db.DateTime, default=now_cst)

    @property
    def is_low_stock(self):
        return self.stock <= self.low_stock_threshold


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(36), unique=True, nullable=False,
                      default=lambda: str(uuid.uuid4()))
    purpose = db.Column(db.Text, nullable=False)
    applicant = db.Column(db.String(100), default="匿名用户")
    status = db.Column(db.String(20), default="已通过")
    photos = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=now_cst)
    updated_at = db.Column(db.DateTime, default=now_cst,
                           onupdate=now_cst)

    items = db.relationship("ApplicationItem", backref="application",
                            lazy=True, cascade="all, delete-orphan")

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items)


class ApplicationItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer,
                               db.ForeignKey("application.id"),
                               nullable=False)
    prize_id = db.Column(db.Integer, db.ForeignKey("prize.id"),
                         nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    prize = db.relationship("Prize", backref="application_items")

    @property
    def total_price(self):
        return self.prize.unit_price * self.quantity


# --- Routes ---


def admin_required():
    if session.get("role") != "admin":
        flash("请先切换为管理员", "danger")
        return True
    return False


@app.route("/")
def index():
    prizes = Prize.query.order_by(Prize.category, Prize.name).all()
    low_stock_prizes = [p for p in prizes if p.is_low_stock]
    return render_template("index.html", prizes=prizes,
                           low_stock_prizes=low_stock_prizes)


# Prize management (admin)
@app.route("/prizes")
def prize_list():
    if admin_required():
        return redirect(url_for("index"))
    prizes = Prize.query.order_by(Prize.category, Prize.name).all()
    return render_template("prizes.html", prizes=prizes)


@app.route("/prizes/add", methods=["GET", "POST"])
def prize_add():
    if admin_required():
        return redirect(url_for("index"))
    if request.method == "POST":
        prize = Prize(
            name=request.form["name"],
            category=normalize_prize_category(request.form.get("category")),
            unit_price=float(request.form["unit_price"]),
            stock=int(request.form["stock"]),
            low_stock_threshold=int(request.form.get("low_stock_threshold",
                                                     5)),
        )
        db.session.add(prize)
        db.session.commit()
        flash("奖品添加成功", "success")
        return redirect(url_for("prize_list"))
    return render_template("prize_form.html", prize=None, title="添加奖品")


@app.route("/prizes/<int:id>/edit", methods=["GET", "POST"])
def prize_edit(id):
    if admin_required():
        return redirect(url_for("index"))
    prize = Prize.query.get_or_404(id)
    if request.method == "POST":
        prize.name = request.form["name"]
        prize.category = normalize_prize_category(request.form.get("category"))
        prize.unit_price = float(request.form["unit_price"])
        prize.stock = int(request.form["stock"])
        prize.low_stock_threshold = int(request.form.get(
            "low_stock_threshold", 5))
        db.session.commit()
        flash("奖品更新成功", "success")
        return redirect(url_for("prize_list"))
    return render_template("prize_form.html", prize=prize, title="编辑奖品")


@app.route("/prizes/<int:id>/delete", methods=["POST"])
def prize_delete(id):
    if admin_required():
        return redirect(url_for("index"))
    prize = Prize.query.get_or_404(id)
    db.session.delete(prize)
    db.session.commit()
    flash("奖品已删除", "success")
    return redirect(url_for("prize_list"))


# Application
@app.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        purpose = request.form["purpose"]
        applicant = request.form.get("applicant", "").strip()
        prize_ids = request.form.getlist("prize_id[]")
        quantities = request.form.getlist("quantity[]")

        if not applicant:
            prizes = Prize.query.filter(Prize.stock > 0).order_by(
                Prize.category, Prize.name).all()
            flash("请填写申请人", "danger")
            return render_template("apply.html", prizes=prizes,
                                   form_data=request.form)

        if not prize_ids or not any(pid for pid in prize_ids):
            prizes = Prize.query.filter(Prize.stock > 0).order_by(
                Prize.category, Prize.name).all()
            flash("请至少选择一个奖品", "danger")
            return render_template("apply.html", prizes=prizes,
                                   form_data=request.form)

        # Validate all items first
        items_data = []
        requested = {}
        for pid, qty in zip(prize_ids, quantities):
            if not pid:
                continue
            try:
                prize_id = int(pid)
                quantity = int(qty)
            except (TypeError, ValueError):
                continue
            if quantity < 1:
                continue
            requested[prize_id] = requested.get(prize_id, 0) + quantity

        prizes_by_id = {
            p.id: p for p in Prize.query.filter(
                Prize.id.in_(requested.keys())).all()
        }
        for prize_id, quantity in requested.items():
            prize = prizes_by_id.get(prize_id)
            if not prize:
                continue
            if quantity > prize.stock:
                prizes = Prize.query.filter(Prize.stock > 0).order_by(
                    Prize.category, Prize.name).all()
                flash(f"「{prize.name}」库存不足（剩余 {prize.stock}）",
                      "danger")
                return render_template("apply.html", prizes=prizes,
                                       form_data=request.form)
            items_data.append((prize, quantity))

        if not items_data:
            prizes = Prize.query.filter(Prize.stock > 0).order_by(
                Prize.category, Prize.name).all()
            flash("请至少选择一个奖品", "danger")
            return render_template("apply.html", prizes=prizes,
                                   form_data=request.form)

        # Handle photo uploads
        photos = request.files.getlist("photos[]")
        photo_paths = []
        for photo in photos:
            saved = save_photo_data(photo)
            if saved:
                photo_paths.append(saved)

        # All valid — create one Application with items
        application = Application(
            purpose=purpose, applicant=applicant,
            photos=json.dumps(photo_paths))
        db.session.add(application)
        db.session.flush()  # get application.id

        for prize, quantity in items_data:
            prize.stock -= quantity
            item = ApplicationItem(
                application_id=application.id,
                prize_id=prize.id,
                quantity=quantity,
            )
            db.session.add(item)

        db.session.commit()
        remember_application(application)
        flash("申请已通过！", "success")
        detail_url = url_for("apply_history")
        if wants_json():
            return jsonify({"ok": True, "redirect": detail_url})
        return redirect(detail_url)

    prizes = Prize.query.filter(Prize.stock > 0).order_by(
        Prize.category, Prize.name).all()
    return render_template("apply.html", prizes=prizes, form_data={})


@app.route("/application/<token>")
def apply_detail(token):
    application = Application.query.filter_by(token=token).first_or_404()
    prizes = Prize.query.order_by(Prize.category, Prize.name).all()
    is_edit_mode = (
        request.args.get("mode") == "edit" and application.status == "已通过"
    )
    return render_template("apply_detail.html", application=application,
                           prizes=prizes,
                           edit_mode=is_edit_mode)


@app.route("/application/<token>/edit", methods=["POST"])
def apply_edit(token):
    application = Application.query.filter_by(token=token).first_or_404()
    if not can_manage_application(application):
        flash("只能维护自己的申请记录", "danger")
        return redirect(url_for("apply_history"))
    if application.status == "已取消":
        flash("已取消的申请不可编辑", "danger")
        return redirect(url_for("apply_detail", token=token))
    if application.status == "已关单" and session.get("role") != "admin":
        flash("已关单，不可编辑", "danger")
        return redirect(url_for("apply_detail", token=token))

    new_purpose = request.form.get("purpose", application.purpose)
    new_applicant = request.form.get("applicant", application.applicant)

    # Handle photo edits
    old_photos = json.loads(application.photos) if application.photos else []
    deleted = request.form.get("deleted_photos", "")
    try:
        deleted_set = set(json.loads(deleted)) if deleted else set()
    except (json.JSONDecodeError, TypeError):
        deleted_set = set(deleted.split(",")) if deleted else set()
    remaining = [p for p in old_photos if p not in deleted_set]

    new_photo_files = request.files.getlist("new_photos[]")
    for photo in new_photo_files:
        saved = save_photo_data(photo)
        if saved:
            remaining.append(saved)

    application.photos = json.dumps(remaining)

    # Parse updated items
    item_ids = request.form.getlist("item_id[]")
    new_prize_ids = request.form.getlist("item_prize_id[]")
    new_quantities = request.form.getlist("item_quantity[]")

    if not new_prize_ids or not any(new_prize_ids):
        flash("请至少保留一个奖品", "danger")
        return redirect(url_for("apply_detail", token=token))

    requested = {}
    for pid, qty in zip(new_prize_ids, new_quantities):
        if not pid:
            continue
        try:
            prize_id = int(pid)
            quantity = int(qty)
        except (TypeError, ValueError):
            continue
        if quantity < 1:
            continue
        requested[prize_id] = requested.get(prize_id, 0) + quantity

    if not requested:
        flash("请至少保留一个奖品", "danger")
        return redirect(url_for("apply_detail", token=token))

    # Restore all old stock first
    for item in application.items:
        item.prize.stock += item.quantity

    # Validate new quantities
    prizes_by_id = {
        p.id: p for p in Prize.query.filter(Prize.id.in_(requested.keys())).all()
    }
    for prize_id, quantity in requested.items():
        prize = prizes_by_id.get(prize_id)
        if not prize:
            flash("选择的奖品不存在", "danger")
            return redirect(url_for("apply_detail", token=token))
        if quantity > prize.stock:
            # Rollback: re-deduct old stock
            for item in application.items:
                item.prize.stock -= item.quantity
            db.session.commit()
            flash(f"「{prize.name}」库存不足（剩余 {prize.stock}）",
                  "danger")
            return redirect(url_for("apply_detail", token=token))

    # Remove old items
    for item in list(application.items):
        db.session.delete(item)
    db.session.flush()

    # Create new items
    for prize_id, quantity in requested.items():
        prize = prizes_by_id[prize_id]
        prize.stock -= quantity
        item = ApplicationItem(
            application_id=application.id,
            prize_id=prize_id,
            quantity=quantity,
        )
        db.session.add(item)

    application.purpose = new_purpose
    application.applicant = new_applicant
    application.updated_at = now_cst()
    db.session.commit()
    remember_application(application)

    flash("申请已更新", "success")
    return redirect(url_for("apply_detail", token=token))


@app.route("/application/<token>/cancel", methods=["POST"])
def apply_cancel(token):
    application = Application.query.filter_by(token=token).first_or_404()
    if not can_manage_application(application):
        flash("只能维护自己的申请记录", "danger")
        return redirect(url_for("apply_history"))
    if application.status != "已通过":
        flash("当前状态不可取消", "danger")
        return redirect(url_for("apply_detail", token=token))

    # Restore stock for all items
    for item in application.items:
        item.prize.stock += item.quantity

    application.status = "已取消"
    db.session.commit()
    flash("申请已取消，库存已恢复", "success")
    return redirect(url_for("apply_detail", token=token))


@app.route("/application/<token>/close", methods=["POST"])
def apply_close(token):
    if session.get("role") != "admin":
        flash("仅管理员可操作", "danger")
        return redirect(url_for("index"))
    application = Application.query.filter_by(token=token).first_or_404()
    if application.status != "已通过":
        flash("当前状态不可关单", "danger")
        return redirect(url_for("apply_detail", token=token))
    application.status = "已关单"
    application.updated_at = now_cst()
    db.session.commit()
    flash("已关单", "success")
    return redirect(url_for("apply_detail", token=token))


# Application history
@app.route("/history")
def apply_history():
    query = Application.query.options(
        selectinload(Application.items).joinedload(ApplicationItem.prize)
    )
    try:
        if session.get("role") == "admin":
            applications = query.order_by(Application.created_at.desc()).all()
        else:
            applicant = session.get("applicant", "")
            tokens = session_tokens()
            if applicant or tokens:
                conditions = []
                if applicant:
                    conditions.append(Application.applicant == applicant)
                if tokens:
                    conditions.append(Application.token.in_(tokens))
                applications = query.filter(or_(*conditions)).order_by(
                    Application.created_at.desc()).all()
            else:
                applications = []
    except SQLAlchemyError:
        db.session.rollback()
        db.create_all()
        applications = []
        flash("申请记录初始化完成，请重新提交或刷新查看", "success")
    for application in applications:
        prize_names = " ".join(
            item.prize.name for item in application.items if item.prize
        )
        application.search_text = (
            f"{application.applicant} {application.purpose} {prize_names}"
        )
    return render_template("history.html", applications=applications)


# Export
@app.route("/export")
def export():
    if admin_required():
        return redirect(url_for("index"))
    applications = Application.query.order_by(
        Application.created_at.desc()).all()
    data = []
    for app in applications:
        photos = json.loads(app.photos) if app.photos else []
        photo_urls = "\n".join([
            p if str(p).startswith("data:image/")
            else url_for("serve_upload", filename=str(p).lstrip("uploads/"),
                         _external=True)
            for p in photos
        ]) if photos else ""
        for item in app.items:
            data.append({
                "申请编号": app.token[:8],
                "申请人": app.applicant,
                "用途": app.purpose,
                "类别": item.prize.category,
                "奖品名称": item.prize.name,
                "数量": item.quantity,
                "状态": app.status,
                "活动现场照片": photo_urls,
                "申请时间": app.created_at.strftime("%Y-%m-%d %H:%M"),
                "更新时间": app.updated_at.strftime("%Y-%m-%d %H:%M"),
            })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="申请记录")
    output.seek(0)

    filename = f"奖品申请记录_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/prizes")
def api_prizes():
    prizes = Prize.query.order_by(Prize.name).all()
    return jsonify([{
        "id": p.id, "name": p.name, "category": p.category,
        "unit_price": p.unit_price, "stock": p.stock
    } for p in prizes])


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    safe_name = filename.replace("uploads/", "").lstrip("/")
    folders = [
        app.config["UPLOAD_FOLDER"],
        os.path.join(os.path.dirname(__file__), "static", "uploads"),
    ]
    for folder in folders:
        path = os.path.join(folder, safe_name)
        if os.path.exists(path):
            return send_file(path)
    abort(404)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
