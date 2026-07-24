import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, abort
from flask_login import login_required, current_user
from flask_wtf.csrf import validate_csrf, CSRFError
from werkzeug.utils import secure_filename
from models import Documento, db
from routes.auth import log_activity

documenti = Blueprint("documenti", __name__, url_prefix="/documenti")

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "docs")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "tif", "xlsx", "xls", "doc", "docx"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@documenti.route("/")
@login_required
def lista():
    from flask_wtf.csrf import generate_csrf
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    pagination = Documento.query.order_by(Documento.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    doc_list = pagination.items
    return render_template("documenti.html", documenti=doc_list, pagination=pagination, csrf_token=generate_csrf())


@documenti.route("/carica", methods=["POST"])
@login_required
def carica():
    # CSRF validation
    try:
        validate_csrf(request.form.get("csrf_token"))
    except CSRFError:
        abort(403)

    if "file" not in request.files:
        flash("Nessun file selezionato.", "error")
        return redirect(url_for("documenti.lista"))

    file = request.files["file"]
    if file.filename == "":
        flash("Nessun file selezionato.", "error")
        return redirect(url_for("documenti.lista"))

    tipo = request.form.get("tipo", "altro")
    entity_type = request.form.get("entity_type", "")
    entity_id = request.form.get("entity_id", type=int)

    if file and allowed_file(file.filename):
        # MIME type validation for PDF
        if file.filename.lower().endswith(".pdf"):
            file.stream.seek(0)
            header = file.read(5)
            file.stream.seek(0)
            if header != b"%PDF-":
                flash("Il file non è un PDF valido.", "error")
                return redirect(url_for("documenti.lista"))
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(file.filename)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
        filename = timestamp + filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        doc = Documento(
            nome=file.filename,
            tipo=tipo,
            file_path=filepath,
            entity_type=entity_type or None,
            entity_id=entity_id or None,
            caricato_da=current_user.id,
        )
        db.session.add(doc)
        db.session.commit()

        log_activity(current_user.id, "carica_documento",
            f"{current_user.username} ha caricato il documento {doc.nome}",
            "documento", doc.id)
        flash("Documento caricato con successo.", "success")
    else:
        flash("Tipo file non supportato.", "error")

    return redirect(url_for("documenti.lista"))


@documenti.route("/download/<int:id>")
@login_required
def download(id):
    doc = Documento.query.get_or_404(id)
    if os.path.exists(doc.file_path):
        return send_file(doc.file_path, as_attachment=True, download_name=doc.nome)
    flash("File non trovato.", "error")
    return redirect(url_for("documenti.lista"))
