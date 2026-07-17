from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, TipologiaMateriale, Prenotazione, User
from forms import TipologiaMaterialeForm
from routes.auth import log_activity
from core.auth_decorators import admin_required

tipologie = Blueprint("tipologie", __name__, url_prefix="/users")


@tipologie.route("/<int:cliente_id>/tipologie/nuova", methods=["POST"])
@login_required
@admin_required
def nuova(cliente_id):
    cliente = db.session.get(User, cliente_id)
    if not cliente or cliente.role != "cliente":
        flash("Utente non trovato o non è un cliente.", "error")
        return redirect(url_for("users.lista"))
    form = TipologiaMaterialeForm()
    if form.validate_on_submit():
        t = TipologiaMateriale(
            cliente_id=cliente_id,
            nome=form.nome.data,
            durata_minuti=form.durata_minuti.data,
            attivo=True,
        )
        db.session.add(t)
        db.session.commit()
        log_activity(
            current_user.id, "crea_tipologia_materiale",
            f"{current_user.username} ha creato tipologia '{t.nome}' per {cliente.username}",
            "tipologia_materiale", t.id,
        )
        flash(f"Tipologia '{t.nome}' creata per {cliente.username}.", "success")
    else:
        for field, errors in form.errors.items():
            for e in errors:
                flash(f"{getattr(form, field).label.text}: {e}", "error")
    return redirect(url_for("users.modifica", id=cliente_id))


@tipologie.route("/<int:cliente_id>/tipologie/<int:id>/elimina", methods=["POST"])
@login_required
@admin_required
def elimina(cliente_id, id):
    t = TipologiaMateriale.query.get_or_404(id)
    if t.cliente_id != cliente_id:
        flash("Tipologia non appartenente a questo cliente.", "error")
        return redirect(url_for("users.modifica", id=cliente_id))
    attive = Prenotazione.query.filter(
        Prenotazione.tipologia_materiale_id == t.id,
        Prenotazione.stato.in_(["in_attesa", "confermata", "ingresso_registrato"]),
    ).count()
    if attive > 0:
        t.attivo = False
        db.session.commit()
        log_activity(
            current_user.id, "disattiva_tipologia_materiale",
            f"{current_user.username} ha disattivato tipologia '{t.nome}' per prenotazioni attive collegate",
            "tipologia_materiale", t.id,
        )
        flash(f"Tipologia '{t.nome}' disattivata (prenotazioni attive collegate).", "warning")
    else:
        db.session.delete(t)
        db.session.commit()
        log_activity(
            current_user.id, "elimina_tipologia_materiale",
            f"{current_user.username} ha eliminato tipologia '{t.nome}'",
            "tipologia_materiale", t.id,
        )
        flash(f"Tipologia '{t.nome}' eliminata.", "success")
    return redirect(url_for("users.modifica", id=cliente_id))
