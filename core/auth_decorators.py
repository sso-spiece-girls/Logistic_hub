from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Accesso negato. Solo gli admin possono accedere a questa sezione.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "ufficio"):
            flash("Accesso negato. Solo admin e ufficio possono eseguire questa operazione.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def operatore_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "operatore"):
            flash("Accesso negato. Solo admin e operatori possono eseguire questa operazione.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated
