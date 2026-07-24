import os
import sys
import time
from datetime import date, datetime, time as dt_time
import zoneinfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix
from extensions import db, login_manager, limiter, csrf
from models import (
    User, Bolla, DDT, Giacenza, Picking, Documento, Activity, Notification, BackupLog,
    Fornitore, Articolo, DettaglioBolla, RigheDDT, Movimento, PickingRiga,
    SlotOrario, Prenotazione, MagazzinoCapienza, TipologiaMateriale,
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
from routes.prenotazioni import bp as prenotazioni
from routes.tipologie_materiale import tipologie
from config import Config


_NOTIF_CACHE = {}
_NOTIF_TTL = 120


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


def _migrate_prenotazioni():
    """Aggiunge colonne mancanti alla tabella prenotazioni (migrazione senza Alembic)."""
    from sqlalchemy import text
    for col, coltype in [("targa", "VARCHAR(20)"), ("ddt_cmr", "VARCHAR(200)"),
                         ("inserita_da_staff", "BOOLEAN DEFAULT FALSE"),
                         ("staff_user_id", "INTEGER REFERENCES users(id)"),
                         ("motivo_rifiuto", "TEXT")]:
        try:
            db.session.execute(text(f"ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS {col} {coltype}"))
            db.session.commit()
        except Exception:
            db.session.rollback()


def _seed_slot_orari():
    """Crea gli slot orari default (8-13 e 14-17, Lun-Ven) se non ne esiste nessuno."""
    from models import SlotOrario
    from datetime import time as dt_time
    if SlotOrario.query.first() is not None:
        return
    giorni = [0, 1, 2, 3, 4]  # Lun-Ven
    fasce = [
        (dt_time(8, 0), dt_time(13, 0)),   # 8:00-13:00
        (dt_time(14, 0), dt_time(17, 0)),  # 14:00-17:00
    ]
    admin = User.query.filter_by(role="admin").first()
    admin_id = admin.id if admin else 1
    for g in giorni:
        for oi, of in fasce:
            db.session.add(SlotOrario(
                giorno_settimana=g, ora_inizio=oi, ora_fine=of,
                durata_minuti=60, capienza=1, attivo=True, creato_da_id=admin_id,
            ))
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Compress(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["BACKUP_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)

    # Seed: crea tabelle e SlotOrario default (8-13 e 14-17, Lun-Ven)
    with app.app_context():
        db.create_all()
        _migrate_prenotazioni()
        try:
            _seed_slot_orari()
        except Exception:
            pass  # Non bloccare l'avvio se il seed fallisce

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

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
    app.register_blueprint(prenotazioni)
    app.register_blueprint(tipologie)

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

    @app.template_filter("roma_time")
    def roma_time_filter(dt, fmt="%d/%m/%Y %H:%M"):
        """Converte UTC → Europe/Rome e formatta. Gestisce date, time, None e datetime."""
        if dt is None:
            return "-"
        if isinstance(dt, datetime):
            if dt.tzinfo is not None:
                dt = dt.astimezone(zoneinfo.ZoneInfo("Europe/Rome"))
            return dt.strftime(fmt)
        if isinstance(dt, date):
            return dt.strftime(fmt)
        if isinstance(dt, dt_time):
            return dt.strftime(fmt)
        return str(dt)

    @app.route("/ping")
    def ping():
        return "pong", 200, {"Content-Type": "text/plain"}

    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    @app.after_request
    def add_cache_headers(response):
        if response.content_type and "text/" in response.content_type:
            response.headers["X-Content-Type-Options"] = "nosniff"
        if response.content_type and ("text/css" in response.content_type or "application/javascript" in response.content_type or "image/" in response.content_type):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["Expires"] = "Thu, 31 Dec 2037 23:55:55 GMT"

        # Security headers (su tutte le risposte)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'self'",
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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


def seed_slot_orari(app):
    """Crea slot orari default Lun-Ven 09:00-18:00 se non esiste già nessuna regola."""
    with app.app_context():
        if SlotOrario.query.count() > 0:
            return
        admin = User.query.filter_by(role="admin").first()
        if not admin:
            return
        from datetime import time
        for giorno in range(5):  # 0=lunedì … 4=venerdì
            regola = SlotOrario(
                giorno_settimana=giorno,
                ora_inizio=time(9, 0),
                ora_fine=time(18, 0),
                durata_minuti=60,
                capienza=1,
                attivo=True,
                creato_da_id=admin.id,
            )
            db.session.add(regola)
        db.session.commit()
        print(f"Slot orari Lun-Ven creati (admin: {admin.username}).")


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        from sqlalchemy import text
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_prenotazioni_data_stato ON prenotazioni (data, stato)",
            "CREATE INDEX IF NOT EXISTS ix_prenotazioni_cliente_data ON prenotazioni (cliente_id, data)",
        ]:
            try:
                db.session.execute(text(idx_sql))
                db.session.commit()
            except Exception:
                db.session.rollback()
        seed_admin(app)
        seed_slot_orari(app)

    port = int(os.environ.get("PORT", 5000))
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        use_reloader=False,
    )
