"""
WSGI entry point per Railway / Gunicorn.
Inizializza l'app, il database e l'utente admin.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import create_app, seed_admin
from models import db
from sqlalchemy import text


def run_migrations(app):
    """Applica migrazioni colonne mancanti (safe: ignora se colonna esiste gia)."""
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
        "ALTER TABLE prenotazioni ADD COLUMN tipo VARCHAR(10) DEFAULT 'scarico'",
        "ALTER TABLE prenotazioni ADD COLUMN magazzino VARCHAR(50)",
        "ALTER TABLE prenotazioni ADD COLUMN tipologia_materiale_id INTEGER REFERENCES tipologie_materiale(id)",
    ]
    with app.app_context():
        for sql in migrazioni:
            try:
                db.session.execute(text(sql))
                db.session.commit()
            except Exception:
                pass


app = create_app()

with app.app_context():
    db.create_all()
    run_migrations(app)
    seed_admin(app)
    print("[WSGI] Database initialized, admin user ready.")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=(os.environ.get("FLASK_DEBUG", "0") == "1"),
    )
