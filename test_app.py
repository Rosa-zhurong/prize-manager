import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from app import app, db, Prize, Application, ApplicationItem


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


def _add_prize(name="键盘", category="电子产品", price=299.0, stock=10):
    prize = Prize(name=name, category=category, unit_price=price, stock=stock)
    db.session.add(prize)
    db.session.commit()
    return prize


# --- Model tests ---


class TestModels:
    def test_application_has_items(self, client):
        with app.app_context():
            p = _add_prize()
            app1 = Application(purpose="测试", applicant="张三")
            db.session.add(app1)
            db.session.flush()
            db.session.add(ApplicationItem(
                application_id=app1.id, prize_id=p.id, quantity=2))
            db.session.commit()

            assert len(app1.items) == 1
            assert app1.items[0].quantity == 2
            assert app1.total_quantity == 2

    def test_application_total_quantity(self, client):
        with app.app_context():
            p1 = _add_prize("键盘", price=100, stock=20)
            p2 = _add_prize("鼠标", price=50, stock=30)
            app1 = Application(purpose="测试", applicant="张三")
            db.session.add(app1)
            db.session.flush()
            db.session.add(ApplicationItem(
                application_id=app1.id, prize_id=p1.id, quantity=3))
            db.session.add(ApplicationItem(
                application_id=app1.id, prize_id=p2.id, quantity=5))
            db.session.commit()

            assert app1.total_quantity == 8

    def test_application_item_total_price(self, client):
        with app.app_context():
            p = _add_prize(price=99.9)
            app1 = Application(purpose="测试", applicant="张三")
            db.session.add(app1)
            db.session.flush()
            item = ApplicationItem(
                application_id=app1.id, prize_id=p.id, quantity=3)
            db.session.add(item)
            db.session.commit()

            assert item.total_price == pytest.approx(299.7)

    def test_cascade_delete(self, client):
        with app.app_context():
            p = _add_prize()
            app1 = Application(purpose="测试", applicant="张三")
            db.session.add(app1)
            db.session.flush()
            db.session.add(ApplicationItem(
                application_id=app1.id, prize_id=p.id, quantity=2))
            db.session.commit()

            app_id = app1.id
            db.session.delete(app1)
            db.session.commit()

            assert Application.query.get(app_id) is None
            assert ApplicationItem.query.filter_by(
                application_id=app_id).count() == 0

    def test_application_default_status(self, client):
        with app.app_context():
            app1 = Application(purpose="测试", applicant="张三")
            db.session.add(app1)
            db.session.commit()
            assert app1.status == "已通过"


# --- Route tests ---


class TestApplyRoute:
    def test_get_apply_page(self, client):
        _add_prize()
        resp = client.get("/apply")
        assert resp.status_code == 200
        assert "选择奖品" in resp.data.decode()

    def test_single_prize_creates_one_application(self, client):
        p = _add_prize()
        resp = client.post("/apply", data={
            "purpose": "活动奖品",
            "applicant": "张三",
            "prize_id[]": [str(p.id)],
            "quantity[]": ["2"],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            apps = Application.query.all()
            assert len(apps) == 1
            assert apps[0].items[0].prize_id == p.id
            assert apps[0].items[0].quantity == 2
            assert apps[0].total_quantity == 2
            assert p.stock == 8

    def test_multiple_prizes_creates_one_application(self, client):
        p1 = _add_prize("键盘", stock=10)
        p2 = _add_prize("鼠标", stock=20)
        resp = client.post("/apply", data={
            "purpose": "团建奖品",
            "applicant": "李四",
            "prize_id[]": [str(p1.id), str(p2.id)],
            "quantity[]": ["3", "5"],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            apps = Application.query.all()
            assert len(apps) == 1
            assert len(apps[0].items) == 2
            assert apps[0].total_quantity == 8

            stock1 = Prize.query.get(p1.id).stock
            stock2 = Prize.query.get(p2.id).stock
            assert stock1 == 7
            assert stock2 == 15

    def test_no_prize_selected_shows_error(self, client):
        resp = client.post("/apply", data={
            "purpose": "测试",
            "applicant": "张三",
            "prize_id[]": [""],
            "quantity[]": ["1"],
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert Application.query.count() == 0

    def test_stock_insufficient_rejects(self, client):
        p = _add_prize(stock=3)
        resp = client.post("/apply", data={
            "purpose": "测试",
            "applicant": "张三",
            "prize_id[]": [str(p.id)],
            "quantity[]": ["5"],
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            assert Application.query.count() == 0
            assert Prize.query.get(p.id).stock == 3


class TestApplyDetail:
    def test_detail_page(self, client):
        p = _add_prize()
        resp = client.post("/apply", data={
            "purpose": "测试", "applicant": "张三",
            "prize_id[]": [str(p.id)], "quantity[]": ["1"],
        }, follow_redirects=False)
        token = resp.location.split("/")[-1]

        resp = client.get(f"/application/{token}")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "键盘" in html
        assert "电子产品" in html
        assert "张三" in html

    def test_detail_shows_multiple_items(self, client):
        p1 = _add_prize("键盘", category="电子产品")
        p2 = _add_prize("鼠标", category="电子产品")
        resp = client.post("/apply", data={
            "purpose": "团建", "applicant": "李四",
            "prize_id[]": [str(p1.id), str(p2.id)],
            "quantity[]": ["2", "3"],
        }, follow_redirects=False)
        token = resp.location.split("/")[-1]

        resp = client.get(f"/application/{token}")
        html = resp.data.decode()
        assert "共 2 项" in html
        assert "键盘" in html
        assert "鼠标" in html


class TestCancelApplication:
    def test_cancel_restores_all_stock(self, client):
        p1 = _add_prize("键盘", stock=10)
        p2 = _add_prize("鼠标", stock=20)
        resp = client.post("/apply", data={
            "purpose": "测试", "applicant": "张三",
            "prize_id[]": [str(p1.id), str(p2.id)],
            "quantity[]": ["3", "5"],
        }, follow_redirects=False)
        token = resp.location.split("/")[-1]

        resp = client.post(
            f"/application/{token}/cancel", follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            app1 = Application.query.filter_by(token=token).first()
            assert app1.status == "已取消"
            assert Prize.query.get(p1.id).stock == 10
            assert Prize.query.get(p2.id).stock == 20


class TestEditApplication:
    def test_edit_changes_items(self, client):
        p1 = _add_prize("键盘", stock=10)
        p2 = _add_prize("鼠标", stock=20)
        resp = client.post("/apply", data={
            "purpose": "测试", "applicant": "张三",
            "prize_id[]": [str(p1.id), str(p2.id)],
            "quantity[]": ["2", "3"],
        }, follow_redirects=False)
        token = resp.location.split("/")[-1]

        with app.app_context():
            app1 = Application.query.filter_by(token=token).first()
            item_ids = [str(i.id) for i in app1.items]

        resp = client.post(f"/application/{token}/edit", data={
            "purpose": "修改后用途",
            "applicant": "王五",
            "item_id[]": item_ids,
            "item_prize_id[]": [str(p2.id), str(p1.id)],
            "item_quantity[]": ["4", "1"],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            app1 = Application.query.filter_by(token=token).first()
            assert app1.purpose == "修改后用途"
            assert app1.applicant == "王五"
            assert len(app1.items) == 2
            assert Prize.query.get(p1.id).stock == 9
            assert Prize.query.get(p2.id).stock == 16

    def test_edit_stock_insufficient_rolls_back(self, client):
        p = _add_prize("键盘", stock=5)
        resp = client.post("/apply", data={
            "purpose": "测试", "applicant": "张三",
            "prize_id[]": [str(p.id)], "quantity[]": ["2"],
        }, follow_redirects=False)
        token = resp.location.split("/")[-1]

        with app.app_context():
            app1 = Application.query.filter_by(token=token).first()
            item_id = str(app1.items[0].id)

        resp = client.post(f"/application/{token}/edit", data={
            "purpose": "测试", "applicant": "张三",
            "item_id[]": [item_id],
            "item_prize_id[]": [str(p.id)],
            "item_quantity[]": ["10"],
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            assert Prize.query.get(p.id).stock == 3


class TestHistory:
    def test_history_shows_applications(self, client):
        p = _add_prize()
        client.post("/apply", data={
            "purpose": "测试", "applicant": "张三",
            "prize_id[]": [str(p.id)], "quantity[]": ["1"],
        })
        resp = client.get("/history")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "1 项" in html
        assert "张三" in html


class TestExport:
    def test_export_excel(self, client):
        p = _add_prize()
        client.post("/apply", data={
            "purpose": "测试", "applicant": "张三",
            "prize_id[]": [str(p.id)], "quantity[]": ["2"],
        })
        resp = client.get("/export")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/vnd.openxmlformats")


class TestApiPrizes:
    def test_api_prizes(self, client):
        _add_prize("键盘")
        _add_prize("鼠标")
        resp = client.get("/api/prizes")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
