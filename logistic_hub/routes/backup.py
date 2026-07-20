import os
import shutil
import subprocess
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, send_file, request
from flask_login import login_required, current_user
from models import BackupLog, db
from routes.auth import log_activity, create_notification, notifica_operatori
from core.auth_decorators import admin_required

backup = Blueprint("backup", __name__, url_prefix="/backup")

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "backup")


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
    drivername = db.engine.url.drivername

    if drivername.startswith("sqlite"):
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
            notifica_operatori("Backup completato",
                f"Backup creato con successo ({size // 1024} KB)", "success")
            flash(f"Backup creato con successo ({size // 1024} KB).", "success")
        else:
            flash("Database non trovato.", "error")
    elif drivername.startswith("postgresql"):
        backup_filename = f"logistic_hub_backup_{timestamp}.dump"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        url = db.engine.url
        pg_dump_path = shutil.which("pg_dump")
        if not pg_dump_path:
            flash("pg_dump non trovato sul server. Impossibile creare backup del database PostgreSQL.", "error")
            return redirect(url_for("backup.lista"))

        env = os.environ.copy()
        env["PGPASSWORD"] = url.password or ""

        cmd = [
            pg_dump_path,
            "-h", url.host or "localhost",
            "-p", str(url.port or 5432),
            "-U", url.username or "postgres",
            "-F", "c",
            "-f", backup_path,
            url.database or "logistic_hub",
        ]

        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
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
                f"{current_user.username} ha creato un backup PostgreSQL ({timestamp})",
                "backup", log.id)
            notifica_operatori("Backup completato",
                f"Backup PostgreSQL creato con successo ({size // 1024} KB)", "success")
            flash(f"Backup PostgreSQL creato con successo ({size // 1024} KB).", "success")
        except subprocess.CalledProcessError as e:
            flash(f"Errore pg_dump: {e.stderr or e.stdout}", "error")
        except FileNotFoundError:
            flash("pg_dump non trovato sul server.", "error")

    return redirect(url_for("backup.lista"))


@backup.route("/ripristina/<int:id>", methods=["POST"])
@login_required
@admin_required
def ripristina(id):
    backup_log = BackupLog.query.get_or_404(id)
    if not os.path.exists(backup_log.file_path):
        flash("File di backup non trovato.", "error")
        return redirect(url_for("backup.lista"))

    drivername = db.engine.url.drivername

    if drivername.startswith("sqlite"):
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "logistic_hub.db")
        try:
            shutil.copy2(backup_log.file_path, db_path)
            log_activity(current_user.id, "ripristino_backup",
                f"{current_user.username} ha ripristinato il backup {backup_log.created_at}",
                "backup", backup_log.id)
            flash("Database ripristinato con successo. Riavvia l'applicazione.", "success")
        except Exception as e:
            flash(f"Errore durante il ripristino: {str(e)}", "error")
    elif drivername.startswith("postgresql"):
        url = db.engine.url
        pg_restore_path = shutil.which("pg_restore")
        if not pg_restore_path:
            flash("pg_restore non trovato sul server. Impossibile ripristinare.", "error")
            return redirect(url_for("backup.lista"))

        env = os.environ.copy()
        env["PGPASSWORD"] = url.password or ""

        cmd = [
            pg_restore_path,
            "-h", url.host or "localhost",
            "-p", str(url.port or 5432),
            "-U", url.username or "postgres",
            "-d", url.database or "logistic_hub",
            "--clean",
            "--if-exists",
            backup_log.file_path,
        ]

        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
            log_activity(current_user.id, "ripristino_backup",
                f"{current_user.username} ha ripristinato il backup PostgreSQL {backup_log.created_at}",
                "backup", backup_log.id)
            flash("Database PostgreSQL ripristinato con successo.", "success")
        except subprocess.CalledProcessError as e:
            flash(f"Errore pg_restore: {e.stderr or e.stdout}", "error")
        except FileNotFoundError:
            flash("pg_restore non trovato sul server.", "error")

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
