import os
import uuid
import json
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, session
)
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from io import BytesIO

app = Flask(__name__)
ADMIN_PASSWORD = "1234567890"


@app.template_filter("from_json")
def from_json_filter(s):
    try:
        return json.loads(s) if s else []
    except (json.JSONDecodeError, TypeError):
        return []
app.config["SECRET_KEY"] = os.urandom(24)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///prize_manager.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__),
                                           "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

db = SQLAlchemy(app)


@app.context_processor
def inject_role():
    return {"is_admin": session.get("role") == "admin"}


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password", "")
    if password == ADMIN_PASSWORD:
        session["role"] = "admin"
        return redirect(request.referrer or url_for("index") + "?toast=已切换为管理员")
    else:
        flash("密码错误", "danger")
    return redirect(request.referrer or url_for("index"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("role", None)
    return redirect(url_for("index") + "?toast=已切换为普通用户")

# --- Models ---


class Prize(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="未分类")
    unit_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, default=5)
    image_path = db.Column(db.String(200), default=None)
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now,
                           onupdate=datetime.now)

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
            category=request.form.get("category", "未分类"),
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
        prize.category = request.form.get("category", "未分类")
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
    prizes = Prize.query.filter(Prize.stock > 0).order_by(
        Prize.category, Prize.name).all()
    if request.method == "POST":
        purpose = request.form["purpose"]
        applicant = request.form.get("applicant", "").strip()
        prize_ids = request.form.getlist("prize_id[]")
        quantities = request.form.getlist("quantity[]")

        if not applicant:
            flash("请填写申请人", "danger")
            return render_template("apply.html", prizes=prizes,
                                   form_data=request.form)

        if not prize_ids or not any(pid for pid in prize_ids):
            flash("请至少选择一个奖品", "danger")
            return render_template("apply.html", prizes=prizes,
                                   form_data=request.form)

        # Validate all items first
        items_data = []
        for pid, qty in zip(prize_ids, quantities):
            if not pid:
                continue
            prize_id = int(pid)
            quantity = int(qty)
            prize = Prize.query.get_or_404(prize_id)

            if quantity > prize.stock:
                flash(f"「{prize.name}」库存不足（剩余 {prize.stock}）",
                      "danger")
                return render_template("apply.html", prizes=prizes,
                                       form_data=request.form)
            items_data.append((prize, quantity))

        # Handle photo uploads
        photos = request.files.getlist("photos[]")
        photo_paths = []
        upload_dir = app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)
        for photo in photos:
            if photo and photo.filename:
                ext = os.path.splitext(photo.filename)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                    filename = f"{uuid.uuid4().hex}{ext}"
                    photo.save(os.path.join(upload_dir, filename))
                    photo_paths.append(f"uploads/{filename}")

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
        flash("申请已通过！", "success")
        return redirect(url_for("apply_detail", token=application.token))

    return render_template("apply.html", prizes=prizes, form_data={})


@app.route("/application/<token>")
def apply_detail(token):
    application = Application.query.filter_by(token=token).first_or_404()
    prizes = Prize.query.order_by(Prize.category, Prize.name).all()
    return render_template("apply_detail.html", application=application,
                           prizes=prizes)


@app.route("/application/<token>/edit", methods=["POST"])
def apply_edit(token):
    application = Application.query.filter_by(token=token).first_or_404()

    new_purpose = request.form.get("purpose", application.purpose)
    new_applicant = request.form.get("applicant", application.applicant)

    # Handle photo edits
    old_photos = json.loads(application.photos) if application.photos else []
    deleted = request.form.get("deleted_photos", "")
    deleted_set = set(deleted.split(",")) if deleted else set()
    remaining = [p for p in old_photos if p not in deleted_set]

    new_photo_files = request.files.getlist("new_photos[]")
    upload_dir = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    for photo in new_photo_files:
        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                filename = f"{uuid.uuid4().hex}{ext}"
                photo.save(os.path.join(upload_dir, filename))
                remaining.append(f"uploads/{filename}")

    application.photos = json.dumps(remaining)

    # Parse updated items
    item_ids = request.form.getlist("item_id[]")
    new_prize_ids = request.form.getlist("item_prize_id[]")
    new_quantities = request.form.getlist("item_quantity[]")

    # Restore all old stock first
    for item in application.items:
        item.prize.stock += item.quantity

    # Validate new quantities
    for item_id, pid, qty in zip(item_ids, new_prize_ids, new_quantities):
        prize = Prize.query.get_or_404(int(pid))
        quantity = int(qty)
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
    for pid, qty in zip(new_prize_ids, new_quantities):
        prize = Prize.query.get_or_404(int(pid))
        quantity = int(qty)
        prize.stock -= quantity
        item = ApplicationItem(
            application_id=application.id,
            prize_id=int(pid),
            quantity=quantity,
        )
        db.session.add(item)

    application.purpose = new_purpose
    application.applicant = new_applicant
    application.updated_at = datetime.now()
    db.session.commit()

    flash("申请已更新", "success")
    return redirect(url_for("apply_detail", token=token))


@app.route("/application/<token>/cancel", methods=["POST"])
def apply_cancel(token):
    application = Application.query.filter_by(token=token).first_or_404()

    # Restore stock for all items
    for item in application.items:
        item.prize.stock += item.quantity

    application.status = "已取消"
    db.session.commit()
    flash("申请已取消，库存已恢复", "success")
    return redirect(url_for("apply_detail", token=token))


# Application history
@app.route("/history")
def apply_history():
    if admin_required():
        return redirect(url_for("index"))
    applications = Application.query.order_by(
        Application.created_at.desc()).all()
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
        photo_urls = "\n".join([f"http://localhost:5000/static/{p}" for p in photos]) if photos else ""
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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
