def test_login_page(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_success(client, db):
    from models import User
    with client.application.app_context():
        u = User(username="test", email="t@t.local", role="operatore")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
    resp = client.post("/login", data={"username": "test", "password": "pass"})
    assert resp.status_code == 302


def test_login_fail(client, db):
    from models import User
    with client.application.app_context():
        u = User(username="test", email="t@t.local", role="operatore")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
    resp = client.post("/login", data={"username": "test", "password": "wrong"})
    assert resp.status_code == 200


def test_dashboard_redirects_when_not_logged_in(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 302


def test_dashboard_ok_when_logged_in(auth_client):
    resp = auth_client.get("/dashboard")
    assert resp.status_code == 200


def test_entrate_list(auth_client):
    resp = auth_client.get("/entrate/")
    assert resp.status_code == 200


def test_uscite_list(auth_client):
    resp = auth_client.get("/uscite/")
    assert resp.status_code == 200


def test_giacenze_list(auth_client):
    resp = auth_client.get("/giacenze/")
    assert resp.status_code == 200


def test_clienti_list(auth_client):
    resp = auth_client.get("/clienti/")
    assert resp.status_code == 200
