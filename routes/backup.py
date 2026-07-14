import os
import shutil
import sqlite3
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, send_file, request
from flask_login import login_required, current_user
from models import BackupLog, db
from routes.auth import log_activity, create_notification

backup = Blueprint("backup", __name__, url_prefix="/backup")

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "backup")


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Accesso negato.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


@backup.route("/")
@login_required
def lista():
    backups = BackupLog.query.order_by(BackupLog.created_at.desc()).all()
    ultimo_backup = BackupLog.query.order_by(BackupLog.created_at.desc()).first()
    return render_template("backup.html", backups=backups, ultimo_backup=ultimo_backup)


@backup.route("/crea", methods=["POST"])
@login_required
@admin_required
def crea():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"logistic_hub_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "logistic_hub.db")

    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)
        size = os.path.getsize(backup_path)

        log = BackupLog(
            file_path=backup_path,
            size=size,
            tipo="manuale",
            eseguito_da=current_user.id,
        )
        db.session.add(log)
        db.session.commit()

        log_activity(current_user.id, "backup",
            f"{current_user.username} ha creato un backup ({timestamp})",
            "backup", log.id)
        create_notification(None, "Backup completato",
            f"Backup creato con successo ({size // 1024} KB)", "success")
        flash(f"Backup creato con successo ({size // 1024} KB).", "success")
    else:
        flash("Database non trovato.", "error")

    return redirect(url_for("backup.lista"))


@backup.route("/ripristina/<int:id>", methods=["POST"])
@login_required
@admin_required
def ripristina(id):
    backup_log = BackupLog.query.get_or_404(id)
    if not os.path.exists(backup_log.file_path):
        flash("File di backup non trovato.", "error")
        return redirect(url_for("backup.lista"))

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "logistic_hub.db")

    try:
        shutil.copy2(backup_log.file_path, db_path)
        log_activity(current_user.id, "ripristino_backup",
            f"{current_user.username} ha ripristinato il backup {backup_log.created_at}",
            "backup", backup_log.id)
        flash("Database ripristinato con successo. Riavvia l'applicazione.", "success")
    except Exception as e:
        flash(f"Errore durante il ripristino: {str(e)}", "error")

    return redirect(url_for("backup.lista"))


@backup.route("/scarica/<int:id>")
@login_required
@admin_required
def scarica(id):
    backup_log = BackupLog.query.get_or_404(id)
    if os.path.exists(backup_log.file_path):
        return send_file(backup_log.file_path, as_attachment=True)
    flash("File non trovato.", "error")
    return redirect(url_for("backup.lista"))
