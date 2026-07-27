from sqlalchemy.exc import IntegrityError
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import User, db, TipologiaMateriale, ClienteMagazzino, MagazzinoCapienza, Prenotazione, Vettore
from forms import UserForm, TipologiaMaterialeForm
from routes.auth import log_activity, create_notification, notifica_operatori
from core.auth_decorators import admin_required

users = Blueprint("users", __name__, url_prefix="/users")


def _salva_magazzini_associati(cliente_id):
    """Aggiorna le associazioni cliente-magazzino da request.form."""
    selezionati = request.form.getlist("magazzini_associati")
    # Rimuovi associazioni non più selezionate (con controllo prenotazioni attive)
    esistenti = ClienteMagazzino.query.filter_by(cliente_id=cliente_id).all()
    for cm in esistenti:
        if cm.magazzino not in selezionati:
            attive = Prenotazione.query.filter(
                Prenotazione.cliente_id == cliente_id,
                Prenotazione.magazzino == cm.magazzino,
                Prenotazione.stato.in_(["in_attesa", "confermata"]),
            ).count()
            if attive > 0:
                flash(f"Impossibile rimuovere {cm.magazzino}: ci sono {attive} prenotazioni attive.", "warning")
                continue
            db.session.delete(cm)
    # Aggiungi nuove associazioni
    esistenti_nomi = {cm.magazzino for cm in esistenti}
    for magazzino in selezionati:
        if magazzino not in esistenti_nomi:
            db.session.add(ClienteMagazzino(cliente_id=cliente_id, magazzino=magazzino))
    db.session.commit()


@users.route("/")
@login_required
@admin_required
def lista():
    utenti = User.query.all()
    return render_template("users.html", utenti=utenti)


@users.route("/nuovo", methods=["GET", "POST"])
@login_required
@admin_required
def nuovo():
    form = UserForm()
    # Popola choices vettore (filtra solo vettori attivi non ancora collegati)
    vettori_disponibili = Vettore.query.filter(
        Vettore.user_id.is_(None), Vettore.attivo.is_(True)
    ).order_by(Vettore.nome).all()
    form.vettore_id.choices = [(0, "-- Nessuno --")] + [(v.id, v.nome) for v in vettori_disponibili]

    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Username già esistente.", "error")
            return render_template("users_form.html", form=form, titolo="Nuovo Utente")

        # Validazione: per ruolo vettore, selezionare un vettore è obbligatorio
        if form.role.data == "vettore" and form.vettore_id.data in (0, None, ""):
            flash("Per il ruolo Vettore è obbligatorio selezionare un vettore da collegare.", "error")
            return render_template("users_form.html", form=form, titolo="Nuovo Utente")

        try:
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()

            # Collega vettore dopo flush per avere user.id
            if form.role.data == "vettore":
                vettore = Vettore.query.get(form.vettore_id.data)
                if vettore is None:
                    flash("Vettore selezionato non trovato. Potrebbe essere stato eliminato.", "error")
                    return render_template("users_form.html", form=form, titolo="Nuovo Utente")
                vettore.user_id = user.id

            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Errore: username, email o vettore già in uso.", "error")
            return render_template("users_form.html", form=form, titolo="Nuovo Utente")
        log_activity(current_user.id, "crea_utente",
            f"{current_user.username} ha creato l'utente {user.username}",
            "user", user.id)
        notifica_operatori("Utente creato",
            f"{current_user.username} ha creato l'utente {user.username} ({user.role_label})", "info")
        flash("Utente creato con successo.", "success")
        return redirect(url_for("users.lista"))
    return render_template("users_form.html", form=form, titolo="Nuovo Utente")


@users.route("/<int:id>/modifica", methods=["GET", "POST"])
@login_required
@admin_required
def modifica(id):
    user = User.query.get_or_404(id)
    form = UserForm(obj=user)
    form.password.validators = []
    form.password.render_kw = {"placeholder": "Lascia vuoto per non cambiare"}

    # Popola choices vettore (include quello già collegato a questo utente)
    vettori_disponibili = Vettore.query.filter(
        Vettore.attivo.is_(True)
    ).filter(
        (Vettore.user_id.is_(None)) | (Vettore.user_id == user.id)
    ).order_by(Vettore.nome).all()
    form.vettore_id.choices = [(0, "-- Nessuno --")] + [(v.id, v.nome) for v in vettori_disponibili]
    if request.method == "GET" and user.vettore:
        form.vettore_id.data = user.vettore.id

    # Template vars condivise (sia GET che POST error)
    tipologie = TipologiaMateriale.query.filter_by(cliente_id=user.id).order_by(TipologiaMateriale.nome).all() if user.role == "cliente" else []
    magazzini_associati = [cm.magazzino for cm in ClienteMagazzino.query.filter_by(cliente_id=user.id).all()] if user.role == "cliente" else []
    tutti_magazzini = MagazzinoCapienza.query.order_by(MagazzinoCapienza.magazzino).all()
    template_ctx = dict(form=form, titolo="Modifica Utente", user=user,
                        tipologie=tipologie, tipologia_form=TipologiaMaterialeForm(),
                        magazzini_associati=magazzini_associati, tutti_magazzini=tutti_magazzini)

    if form.validate_on_submit():
        if form.password.data:
            user.set_password(form.password.data)
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data

        # Validazione vettore obbligatorio per ruolo vettore
        if form.role.data == "vettore" and form.vettore_id.data in (0, None, ""):
            flash("Per il ruolo Vettore è obbligatorio selezionare un vettore da collegare.", "error")
            return render_template("users_form.html", **template_ctx)

        # Gestione collegamento vettore
        if form.role.data == "vettore":
            nuovo_vettore = Vettore.query.get(form.vettore_id.data)
            if nuovo_vettore is None:
                flash("Vettore selezionato non trovato. Potrebbe essere stato eliminato.", "error")
                return render_template("users_form.html", **template_ctx)
            if nuovo_vettore.user_id is not None and nuovo_vettore.user_id != user.id:
                flash("Vettore già collegato a un altro utente.", "error")
                return render_template("users_form.html", **template_ctx)
            # Scollega vecchio vettore se diverso da quello selezionato
            vecchio_vettore = Vettore.query.filter_by(user_id=user.id).first()
            if vecchio_vettore and vecchio_vettore.id != nuovo_vettore.id:
                vecchio_vettore.user_id = None
                db.session.flush()  # UPDATE immediato per evitare UNIQUE violation
            nuovo_vettore.user_id = user.id
        else:
            # Se non è più vettore, scollega eventuale vettore collegato
            Vettore.query.filter_by(user_id=user.id).update({"user_id": None})

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Errore: username, email o vettore già in uso.", "error")
            return render_template("users_form.html", **template_ctx)

        # Salva associazioni magazzini per clienti
        if user.role == "cliente":
            _salva_magazzini_associati(user.id)

        log_activity(current_user.id, "modifica_utente",
            f"{current_user.username} ha modificato l'utente {user.username}",
            "user", user.id)
        flash("Utente aggiornato con successo.", "success")
        return redirect(url_for("users.lista"))
    return render_template("users_form.html", **template_ctx)


@users.route("/<int:id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("Non puoi disabilitare te stesso.", "error")
        return redirect(url_for("users.lista"))
    user.is_active = not user.is_active
    db.session.commit()
    stato = "abilitato" if user.is_active else "disabilitato"
    flash(f"Utente {user.username} {stato}.", "success")
    return redirect(url_for("users.lista"))
