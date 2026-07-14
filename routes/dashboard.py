from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Bolla, DDT, Giacenza, Picking, Activity, Documento, Notification, db

dashboard = Blueprint("dashboard", __name__)


@dashboard.route("/")
@dashboard.route("/dashboard")
@login_required
def index():
    bolle_da_elaborare = Bolla.query.filter_by(stato="da_elaborare").count()
    ddt_oggi = DDT.query.filter(
        db.func.date(DDT.data_creazione) == datetime.now(timezone.utc).date()
    ).count()
    giacenze_totali = db.session.query(db.func.sum(Giacenza.quantita)).scalar() or 0
    colli_totali = db.session.query(db.func.sum(Giacenza.colli)).scalar() or 0

    ultime_attivita = Activity.query.order_by(Activity.created_at.desc()).limit(10).all()
    ultimi_documenti = Documento.query.order_by(Documento.created_at.desc()).limit(5).all()

    picking_attivi = Picking.query.filter(Picking.stato.in_(["aperto", "in_corso"])).count()

    notifiche_non_lette = Notification.query.filter(
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None)),
        Notification.read == False
    ).order_by(Notification.created_at.desc()).all()

    return render_template("dashboard.html",
        bolle_da_elaborare=bolle_da_elaborare,
        ddt_oggi=ddt_oggi,
        giacenze_totali=int(giacenze_totali),
        colli_totali=int(colli_totali),
        picking_attivi=picking_attivi,
        ultime_attivita=ultime_attivita,
        ultimi_documenti=ultimi_documenti,
        notifiche_non_lette=notifiche_non_lette,
    )
