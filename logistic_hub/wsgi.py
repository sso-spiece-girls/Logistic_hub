"""
WSGI entry point per Railway / Gunicorn.
Inizializza l'app, il database e l'utente admin.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import create_app, seed_admin, seed_slot_orari
from models import db
from sqlalchemy import text


app = create_app()

with app.app_context():
    db.create_all()
    # Crea indici composti che db.create_all() non aggiunge su tabelle esistenti
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
    print("[WSGI] Database initialized, admin user ready.")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=(os.environ.get("FLASK_DEBUG", "0") == "1"),
    )
