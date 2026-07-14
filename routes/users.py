from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import User, db
from forms import UserForm
from routes.auth import log_activity, create_notification

users = Blueprint("users", __name__, url_prefix="/users")


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Accesso negato. Solo gli admin possono accedere a questa sezione.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


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

        user = User(
            username=form.username.data,
            email=form.email.data,
            role=form.role.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        log_activity(current_user.id, "crea_utente",
            f"{current_user.username} ha creato l'utente {user.username}",
            "user", user.id)
        create_notification(None, "Utente creato",
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
    return render_template("users_form.html", form=form, titolo="Modifica Utente", user=user)


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
