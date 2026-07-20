import os
import sys
import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))


@pytest.fixture
def app():
    from main import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from extensions import db as _db
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture
def auth_client(app, db):
    from models import User
    with app.app_context():
        admin = User(
            username="testadmin",
            email="test@test.local",
            role="admin",
        )
        admin.set_password("testpass")
        db.session.add(admin)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "testadmin", "password": "testpass"})
    return client
