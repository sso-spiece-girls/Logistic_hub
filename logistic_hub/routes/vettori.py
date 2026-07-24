from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Vettore, ClienteVettore, User, Prenotazione
from forms import VettoreForm
from routes.auth import log_activity
from core.auth_decorators import admin_required

vettori = Blueprint("vettori", __name__, url_prefix="/vettori")


@vettori.route("/")
@login_required
@admin_required
def lista():
    tutti = Vettore.query.order_by(Vettore.nome).all()
    return render_template("vettori/lista.html", vettori=tutti)


@vettori.route("/nuovo", methods=["GET", "POST"])
@login_required
@admin_required
def nuovo():
    form = VettoreForm()
    if form.validate_on_submit():
        v = Vettore(
            nome=form.nome.data,
            partita_iva=form.partita_iva.data,
            telefono=form.telefono.data,
            email=form.email.data,
            attivo=form.attivo.data,
        )
        db.session.add(v)
        db.session.commit()
        log_activity(current_user.id, "crea_vettore",
                     f"{current_user.username} ha creato il vettore {v.nome}",
                     "vettore", v.id)
        flash(f"Vettore '{v.nome}' creato.", "success")
        return redirect(url_for("vettori.lista"))
    return render_template("vettori/form.html", form=form, titolo="Nuovo vettore")


@vettori.route("/<int:id>/modifica", methods=["GET", "POST"])
@login_required
@admin_required
def modifica(id):
    v = Vettore.query.get_or_404(id)
    form = VettoreForm(obj=v)
    if form.validate_on_submit():
        v.nome = form.nome.data
        v.partita_iva = form.partita_iva.data
        v.telefono = form.telefono.data
        v.email = form.email.data
        v.attivo = form.attivo.data
        db.session.commit()
        log_activity(current_user.id, "modifica_vettore",
                     f"{current_user.username} ha modificato il vettore {v.nome}",
                     "vettore", v.id)
        flash(f"Vettore '{v.nome}' aggiornato.", "success")
        return redirect(url_for("vettori.lista"))
    return render_template("vettori/form.html", form=form, titolo="Modifica vettore")


@vettori.route("/<int:id>/elimina", methods=["POST"])
@login_required
@admin_required
def elimina(id):
    v = Vettore.query.get_or_404(id)
    attive = Prenotazione.query.filter(
        Prenotazione.vettore_id == v.id,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
    ).count()
    if attive > 0:
        flash(f"Impossibile eliminare: {attive} prenotazioni attive usano questo vettore.", "error")
        return redirect(url_for("vettori.lista"))
    # Rimuovi associazioni
    ClienteVettore.query.filter_by(vettore_id=v.id).delete()
    db.session.delete(v)
    db.session.commit()
    log_activity(current_user.id, "elimina_vettore",
                 f"{current_user.username} ha eliminato il vettore {v.nome}",
                 "vettore", v.id)
    flash(f"Vettore '{v.nome}' eliminato.", "success")
    return redirect(url_for("vettori.lista"))


@vettori.route("/associazioni")
@login_required
@admin_required
def associazioni():
    clienti = User.query.filter_by(role="cliente", is_active=True).order_by(User.username).all()
    vettori_lista = Vettore.query.filter_by(attivo=True).order_by(Vettore.nome).all()
    associazioni_map = {}
    for cv in ClienteVettore.query.all():
        associazioni_map.setdefault(cv.cliente_id, set()).add(cv.vettore_id)
    return render_template("vettori/associazioni.html", clienti=clienti,
                           vettori=vettori_lista, associazioni_map=associazioni_map)


@vettori.route("/salva-associazioni", methods=["POST"])
@login_required
@admin_required
def salva_associazioni():
    cliente_id = request.form.get("cliente_id", type=int)
    if not cliente_id:
        flash("Cliente non valido.", "error")
        return redirect(url_for("vettori.associazioni"))
    selezionati = set(int(x) for x in request.form.getlist("vettori_ids"))
    # Rimuovi deselezionati
    for cv in ClienteVettore.query.filter_by(cliente_id=cliente_id).all():
        if cv.vettore_id not in selezionati:
            db.session.delete(cv)
    # Aggiungi nuovi
    esistenti = {cv.vettore_id for cv in ClienteVettore.query.filter_by(cliente_id=cliente_id).all()}
    for vid in selezionati:
        if vid not in esistenti:
            db.session.add(ClienteVettore(cliente_id=cliente_id, vettore_id=vid))
    db.session.commit()
    flash("Associazioni vettori aggiornate.", "success")
    return redirect(url_for("vettori.associazioni"))