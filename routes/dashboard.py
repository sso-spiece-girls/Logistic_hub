from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import Bolla, DDT, Giacenza, Picking, Prenotazione, Activity, Documento, Notification, db
from sqlalchemy import select, func

dashboard = Blueprint("dashboard", __name__)


@dashboard.route("/")
@dashboard.route("/dashboard")
@login_required
def index():
    if current_user.role == "cliente":
        return redirect(url_for("prenotazioni.calendario"))
    today = datetime.now(timezone.utc).date()

    row = db.session.execute(
        select(
            select(func.count()).select_from(Bolla).where(Bolla.stato == "da_elaborare").scalar_subquery(),
            select(func.count()).select_from(DDT).where(db.func.date(DDT.data_creazione) == today).scalar_subquery(),
            select(func.coalesce(func.sum(Giacenza.quantita), 0)).select_from(Giacenza).scalar_subquery(),
            select(func.coalesce(func.sum(Giacenza.colli), 0)).select_from(Giacenza).scalar_subquery(),
            select(func.count()).select_from(Picking).where(Picking.stato.in_(["aperto", "in_corso"])).scalar_subquery(),
            select(func.count()).select_from(DDT).where(DDT.stato == "pronto").scalar_subquery(),
            select(func.count()).select_from(Prenotazione).where(Prenotazione.stato == "in_attesa").scalar_subquery(),
        )
    ).one()

    bolle_da_elaborare, ddt_oggi, giacenze_totali, colli_totali, picking_attivi, ddt_pronti, prenotazioni_in_attesa = row

    ultime_attivita = Activity.query.order_by(Activity.created_at.desc()).limit(10).all()
    ultimi_documenti = Documento.query.order_by(Documento.created_at.desc()).limit(5).all()

    notifiche_non_lette = Notification.query.filter(
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None)),
        Notification.read == False
    ).order_by(Notification.created_at.desc()).limit(10).all()

    return render_template("dashboard.html",
        bolle_da_elaborare=bolle_da_elaborare,
        ddt_oggi=ddt_oggi,
        giacenze_totali=int(giacenze_totali),
        colli_totali=int(colli_totali),
        picking_attivi=picking_attivi,
        ddt_pronti=ddt_pronti,
        prenotazioni_in_attesa=prenotazioni_in_attesa,
        ultime_attivita=ultime_attivita,
        ultimi_documenti=ultimi_documenti,
        notifiche_non_lette=notifiche_non_lette,
    )
