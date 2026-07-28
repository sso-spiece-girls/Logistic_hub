from sqlalchemy.exc import IntegrityError
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import User, db, TipologiaMateriale, ClienteMagazzino, MagazzinoCapienza, Prenotazione, Vettore, ClienteVettore
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
    # Clienti disponibili (per associazione vettore)
    clienti_disponibili = User.query.filter_by(role="cliente", is_active=True).order_by(User.username).all()
    clienti_associati_ids = []  # nuovo utente → nessun cliente associato
    tutti_magazzini = MagazzinoCapienza.query.order_by(MagazzinoCapienza.magazzino).all()

    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Username già esistente.", "error")
            return render_template("users_form.html", form=form, titolo="Nuovo Utente",
                                   clienti_disponibili=clienti_disponibili,
                                   clienti_associati_ids=clienti_associati_ids,
                                   tutti_magazzini=tutti_magazzini,
                                   magazzini_associati=[])

        try:
            email_val = form.email.data or None  # stringa vuota → None per evitare conflitto unique
            user = User(
                username=form.username.data,
                email=email_val,
                role=form.role.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()

            # Per vettore: auto-crea Vettore + associa clienti selezionati
            if form.role.data == "vettore":
                vettore = Vettore(
                    nome=user.username,
                    email=user.email,
                    attivo=True,
                    user_id=user.id,
                )
                db.session.add(vettore)
                db.session.flush()

                clienti_ids = set(int(x) for x in request.form.getlist("clienti_associati") if x)
                for cid in clienti_ids:
                    if any(c.id == cid for c in clienti_disponibili):
                        db.session.add(ClienteVettore(cliente_id=cid, vettore_id=vettore.id))

            db.session.commit()

            # Salva associazioni magazzini per nuovi clienti
            if form.role.data == "cliente":
                _salva_magazzini_associati(user.id)

        except IntegrityError:
            db.session.rollback()
            flash("Errore: username o email già in uso.", "error")
            return render_template("users_form.html", form=form, titolo="Nuovo Utente",
                                   clienti_disponibili=clienti_disponibili,
                                   clienti_associati_ids=clienti_associati_ids,
                                   tutti_magazzini=tutti_magazzini,
                                   magazzini_associati=[])
        log_activity(current_user.id, "crea_utente",
            f"{current_user.username} ha creato l'utente {user.username}",
            "user", user.id)
        notifica_operatori("Utente creato",
            f"{current_user.username} ha creato l'utente {user.username} ({user.role_label})", "info")
        flash("Utente creato con successo.", "success")
        return redirect(url_for("users.lista"))
    return render_template("users_form.html", form=form, titolo="Nuovo Utente",
                           clienti_disponibili=clienti_disponibili,
                           clienti_associati_ids=clienti_associati_ids,
                           tutti_magazzini=tutti_magazzini,
                           magazzini_associati=[])


@users.route("/<int:id>/modifica", methods=["GET", "POST"])
@login_required
@admin_required
def modifica(id):
    user = User.query.get_or_404(id)
    form = UserForm(obj=user)
    form.password.validators = []
    form.password.render_kw = {"placeholder": "Lascia vuoto per non cambiare"}

    # Clienti disponibili per associazione vettore
    clienti_disponibili = User.query.filter_by(role="cliente", is_active=True).order_by(User.username).all()
    # Clienti già associati (tramite Vettore)
    clienti_associati_ids = []
    if user.vettore:
        clienti_associati_ids = [
            cv.cliente_id for cv in ClienteVettore.query.filter_by(vettore_id=user.vettore.id).all()
        ]

    # Template vars condivise (sia GET che POST error)
    tipologie = TipologiaMateriale.query.filter_by(cliente_id=user.id).order_by(TipologiaMateriale.nome).all() if user.role == "cliente" else []
    magazzini_associati = [cm.magazzino for cm in ClienteMagazzino.query.filter_by(cliente_id=user.id).all()] if user.role == "cliente" else []
    tutti_magazzini = MagazzinoCapienza.query.order_by(MagazzinoCapienza.magazzino).all()
    template_ctx = dict(form=form, titolo="Modifica Utente", user=user,
                        tipologie=tipologie, tipologia_form=TipologiaMaterialeForm(),
                        magazzini_associati=magazzini_associati, tutti_magazzini=tutti_magazzini,
                        clienti_disponibili=clienti_disponibili,
                        clienti_associati_ids=clienti_associati_ids)

    if form.validate_on_submit():
        if form.password.data:
            user.set_password(form.password.data)
        user.username = form.username.data
        user.email = form.email.data or None  # stringa vuota → None
        user.role = form.role.data

        # Gestione associazioni vettore-clienti
        if form.role.data == "vettore":
            # Auto-crea Vettore se non esiste (backward compat)
            vettore = user.vettore
            if not vettore:
                vettore = Vettore(
                    nome=user.username,
                    email=user.email,
                    attivo=True,
                    user_id=user.id,
                )
                db.session.add(vettore)
                db.session.flush()

            # Sincronizza ClienteVettore coi clienti selezionati
            selezionati = set(int(x) for x in request.form.getlist("clienti_associati") if x)
            # Rimuovi deselezionati
            for cv in ClienteVettore.query.filter_by(vettore_id=vettore.id).all():
                if cv.cliente_id not in selezionati:
                    db.session.delete(cv)
            # Aggiungi nuovi
            esistenti = {cv.cliente_id for cv in ClienteVettore.query.filter_by(vettore_id=vettore.id).all()}
            for cid in selezionati:
                if cid not in esistenti and any(c.id == cid for c in clienti_disponibili):
                    db.session.add(ClienteVettore(cliente_id=cid, vettore_id=vettore.id))
        else:
            # Se non è più vettore, scollega eventuale Vettore e rimuovi associazioni
            vettore = user.vettore
            if vettore:
                ClienteVettore.query.filter_by(vettore_id=vettore.id).delete()
                vettore.user_id = None

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Errore: username o email già in uso.", "error")
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
