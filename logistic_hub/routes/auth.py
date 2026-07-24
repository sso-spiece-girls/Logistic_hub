from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import User, Activity, Notification, db
from forms import LoginForm
from extensions import limiter

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == "cliente":
            return redirect(url_for("prenotazioni.calendario"))
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("Utente disabilitato. Contattare l'amministratore.", "error")
                return render_template("login.html", form=form)

            login_user(user)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()

            log_activity(user.id, "login", f"{user.username} ha effettuato l'accesso")
            notifica_operatori("Accesso effettuato", f"{user.username} ha effettuato l'accesso", "info")

            next_page = request.args.get("next")
            if user.role == "cliente":
                return redirect(next_page or url_for("prenotazioni.calendario"))
            return redirect(next_page or url_for("dashboard.index"))
        else:
            flash("Credenziali non valide.", "error")

    return render_template("login.html", form=form)


@auth.route("/logout")
@login_required
def logout():
    log_activity(current_user.id, "logout", f"{current_user.username} ha effettuato il logout")
    logout_user()
    return redirect(url_for("auth.login"))


@auth.route("/notifiche/marca/<int:notifica_id>")
@login_required
def mark_notification(notifica_id):
    notifica = Notification.query.get_or_404(notifica_id)
    if notifica.user_id and notifica.user_id != current_user.id:
        if current_user.role != "admin":
            return redirect(url_for("dashboard.index"))
    notifica.read = True
    db.session.commit()
    from main import _NOTIF_CACHE
    _NOTIF_CACHE.pop(current_user.id, None)
    if notifica.user_id and notifica.user_id != current_user.id:
        _NOTIF_CACHE.pop(notifica.user_id, None)
    return redirect(request.referrer or url_for("dashboard.index"))


@auth.route("/notifiche/marca-tutte")
@login_required
def mark_all_notifications():
    notifications = Notification.query.filter(
        (Notification.user_id == current_user.id) | (Notification.user_id.is_(None)),
        Notification.read == False
    ).all()
    for n in notifications:
        n.read = True
    db.session.commit()
    from main import _NOTIF_CACHE
    _NOTIF_CACHE.pop(current_user.id, None)
    flash("Tutte le notifiche sono state segnate come lette.", "success")
    return redirect(request.referrer or url_for("dashboard.index"))


def log_activity(user_id, action, description, entity_type=None, entity_id=None):
    activity = Activity(
        user_id=user_id,
        action=action,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.session.add(activity)
    db.session.commit()


def create_notification(user_id, title, message, type="info"):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
    )
    db.session.add(notification)
    db.session.commit()


def notifica_operatori(title, message, type="info"):
    from models import User
    operatori = User.query.filter(User.role.in_(["admin", "operatore"])).all()
    for op in operatori:
        create_notification(op.id, title, message, type)
