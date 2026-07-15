import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_compress import Compress
from extensions import db, login_manager
from models import (
    User, Bolla, DDT, Giacenza, Picking, Documento, Activity, Notification, BackupLog,
    Fornitore, Articolo, DettaglioBolla, RigheDDT, Movimento, PickingRiga,
)
from routes.auth import auth
from routes.dashboard import dashboard
from routes.search import search
from routes.entrate import entrate
from routes.uscite import uscite
from routes.giacenze import giacenze
from routes.pianificazione import pianificazione
from routes.activities import activities
from routes.users import users
from routes.backup import backup
from routes.documenti import documenti
from routes.movimenti import movimenti
from routes.api import api
from routes.clienti import clienti
from config import Config


_NOTIF_CACHE = {}
_NOTIF_TTL = 20


def _get_cached_notifiche(user_id):
    now = time.monotonic()
    cached = _NOTIF_CACHE.get(user_id)
    if cached and now - cached[0] < _NOTIF_TTL:
        return cached[1], cached[2]

    base_q = Notification.query.filter(
        (Notification.user_id == user_id) | (Notification.user_id.is_(None)),
        Notification.read == False
    )
    unread_count = base_q.count()
    notifications = base_q.order_by(Notification.created_at.desc()).limit(10).all()
    _NOTIF_CACHE[user_id] = (now, unread_count, notifications)
    return unread_count, notifications


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Compress(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["BACKUP_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    css_path = os.path.join(os.path.dirname(__file__), "static", "css", "app.css")
    css_mtime = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 1

    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(search)
    app.register_blueprint(entrate)
    app.register_blueprint(uscite)
    app.register_blueprint(giacenze)
    app.register_blueprint(pianificazione)
    app.register_blueprint(activities)
    app.register_blueprint(users)
    app.register_blueprint(backup)
    app.register_blueprint(documenti)
    app.register_blueprint(movimenti)
    app.register_blueprint(api)
    app.register_blueprint(clienti)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        unread_count = 0
        notifications = []
        if current_user.is_authenticated:
            unread_count, notifications = _get_cached_notifiche(current_user.id)
        return {
            "unread_notifications": notifications,
            "unread_count": unread_count,
            "css_mtime": css_mtime,
        }

    @app.route("/ping")
    def ping():
        return "pong", 200, {"Content-Type": "text/plain"}

    @app.after_request
    def add_cache_headers(response):
        if response.content_type and "text/" in response.content_type:
            response.headers["X-Content-Type-Options"] = "nosniff"
        if response.content_type and ("text/css" in response.content_type or "application/javascript" in response.content_type or "image/" in response.content_type):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["Expires"] = "Thu, 31 Dec 2037 23:55:55 GMT"
        return response

    return app


def seed_admin(app):
    with app.app_context():
        # Rinomina vecchio utente "admin" in "Francesco" se esiste ancora
        vecchio = User.query.filter_by(username="admin").first()
        if vecchio:
            vecchio.username = "Francesco"
            vecchio.email = os.environ.get("ADMIN_EMAIL", "francesco@logistichub.local")
            db.session.commit()
            print("Utente admin rinominato in Francesco.")

        if not User.query.filter_by(username="Francesco").first():
            pwd = os.environ.get("ADMIN_PASSWORD", "")
            if not pwd:
                import secrets
                pwd = secrets.token_urlsafe(16)
                import logging
                logging.getLogger(__name__).warning(
                    "ADMIN_PASSWORD non impostata. Password generata: %s. "
                    "Imposta ADMIN_PASSWORD per fissarla.", pwd
                )
            admin = User(
                username="Francesco",
                email=os.environ.get("ADMIN_EMAIL", "francesco@logistichub.local"),
                role="admin",
            )
            admin.set_password(pwd)
            db.session.add(admin)
            db.session.commit()
            import logging
            logging.getLogger(__name__).info("Utente Francesco creato con ruolo admin.")


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_admin(app)
        # Aggiungi colonne mancanti se necessario
        from sqlalchemy import text
        migrazioni = [
            "ALTER TABLE giacenze ADD COLUMN pallet INTEGER DEFAULT 0",
            "ALTER TABLE giacenze ADD COLUMN peso_kg FLOAT DEFAULT 0.0",
            "ALTER TABLE giacenze ADD COLUMN id_bobina VARCHAR(100)",
            "ALTER TABLE giacenze ADD COLUMN qualita VARCHAR(50)",
            "ALTER TABLE giacenze ADD COLUMN provenienza VARCHAR(100)",
            "ALTER TABLE giacenze ADD COLUMN magazzino VARCHAR(50)",
            "ALTER TABLE ddt ADD COLUMN filename_pdf VARCHAR(500)",
            "ALTER TABLE ddt ADD COLUMN provenienza VARCHAR(300)",
            "ALTER TABLE ddt ADD COLUMN vettore VARCHAR(200)",
            "ALTER TABLE ddt ADD COLUMN causale_trasporto VARCHAR(200)",
        ]
        for sql in migrazioni:
            try:
                db.session.execute(text(sql))
                db.session.commit()
            except Exception:
                pass

    port = int(os.environ.get("PORT", 5000))
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        use_reloader=False,
    )
