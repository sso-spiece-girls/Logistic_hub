from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from models import Picking, db
from forms import PickingForm
from routes.auth import log_activity

pianificazione = Blueprint("pianificazione", __name__, url_prefix="/pianificazione")


@pianificazione.route("/")
@login_required
def lista():
    picking = Picking.query.order_by(Picking.created_at.desc()).all()
    return render_template("pianificazione.html", picking=picking)


@pianificazione.route("/nuovo", methods=["GET", "POST"])
@login_required
def nuovo():
    form = PickingForm()
    if form.validate_on_submit():
        p = Picking(
            numero_picking=form.numero_picking.data,
            cliente=form.cliente.data,
            stato=form.stato.data,
            operatore_id=current_user.id,
        )
        db.session.add(p)
        db.session.commit()
        log_activity(current_user.id, "crea_picking",
            f"{current_user.username} ha creato il picking {p.numero_picking}",
            "picking", p.id)
        flash("Picking creato con successo.", "success")
        return redirect(url_for("pianificazione.lista"))
    return render_template("pianificazione_form.html", form=form, titolo="Nuovo Picking")


@pianificazione.route("/<int:id>/completa", methods=["POST"])
@login_required
def completa(id):
    p = Picking.query.get_or_404(id)
    p.stato = "completato"
    p.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    log_activity(current_user.id, "completa_picking",
        f"{current_user.username} ha completato il picking {p.numero_picking}",
        "picking", p.id)
    flash("Picking completato.", "success")
    return redirect(url_for("pianificazione.lista"))
