from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def _redirect_for_role():
    """Reindirizza l'utente alla pagina appropriata in base al ruolo.
    I ruoli cliente/vettore non devono mai vedere la dashboard interna."""
    if not current_user.is_authenticated:
        return url_for("auth.login")
    if current_user.role == "cliente":
        return url_for("prenotazioni.calendario")
    if current_user.role == "vettore":
        return url_for("vettore_portale.seleziona_cliente")
    return url_for("dashboard.index")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Accesso negato. Solo gli admin possono accedere a questa sezione.", "error")
            return redirect(_redirect_for_role())
        return f(*args, **kwargs)
    return decorated


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "ufficio"):
            flash("Accesso negato. Solo admin e ufficio possono eseguire questa operazione.", "error")
            return redirect(_redirect_for_role())
        return f(*args, **kwargs)
    return decorated


def operativo_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "ufficio", "operatore"):
            flash("Accesso negato. Solo il personale interno può accedere a questa sezione.", "error")
            return redirect(_redirect_for_role())
        return f(*args, **kwargs)
    return decorated


def operatore_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "operatore"):
            flash("Accesso negato. Solo admin e operatori possono eseguire questa operazione.", "error")
            return redirect(_redirect_for_role())
        return f(*args, **kwargs)
    return decorated


def vettore_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "vettore":
            flash("Accesso riservato ai vettori.", "error")
            return redirect(_redirect_for_role())
        return f(*args, **kwargs)
    return decorated
