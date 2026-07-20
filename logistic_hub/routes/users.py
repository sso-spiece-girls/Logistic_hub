from sqlalchemy.exc import IntegrityError
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import User, db, TipologiaMateriale
from forms import UserForm, TipologiaMaterialeForm
from routes.auth import log_activity, create_notification, notifica_operatori
from core.auth_decorators import admin_required

users = Blueprint("users", __name__, url_prefix="/users")


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
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Username già esistente.", "error")
            return render_template("users_form.html", form=form, titolo="Nuovo Utente")

        try:
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Errore: username o email già in uso.", "error")
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

    if form.validate_on_submit():
        if form.password.data:
            user.set_password(form.password.data)
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        db.session.commit()
        log_activity(current_user.id, "modifica_utente",
            f"{current_user.username} ha modificato l'utente {user.username}",
            "user", user.id)
        flash("Utente aggiornato con successo.", "success")
        return redirect(url_for("users.lista"))
    tipologie = TipologiaMateriale.query.filter_by(cliente_id=user.id).order_by(TipologiaMateriale.nome).all() if user.role == "cliente" else []
    return render_template("users_form.html", form=form, titolo="Modifica Utente", user=user, tipologie=tipologie, tipologia_form=TipologiaMaterialeForm())


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
