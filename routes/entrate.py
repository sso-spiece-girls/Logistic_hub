import hashlib
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Bolla, DettaglioBolla, Giacenza, Movimento
from forms import BollaForm
from routes.auth import log_activity, create_notification

entrate = Blueprint("entrate", __name__, url_prefix="/entrate")


def calcola_hash_pdf(file_storage):
    """Calcola SHA256 del file PDF senza salvarlo su disco."""
    sha256 = hashlib.sha256()
    file_storage.stream.seek(0)
    while chunk := file_storage.stream.read(8192):
        sha256.update(chunk)
    file_storage.stream.seek(0)
    return sha256.hexdigest()


@entrate.route("/")
@login_required
def lista():
    stato = request.args.get("stato", "")
    query = Bolla.query.order_by(Bolla.created_at.desc())
    if stato:
        query = query.filter_by(stato=stato)
    bolle = query.all()
    return render_template("entrate.html", bolle=bolle, filtro_stato=stato)


@entrate.route("/nuova", methods=["GET", "POST"])
@login_required
def nuova():
    form = BollaForm()
    if form.validate_on_submit():
        # Controlla duplicato se è stato caricato un file PDF
        hash_val = None
        if request.files.get("file_pdf"):
            file = request.files["file_pdf"]
            hash_val = calcola_hash_pdf(file)
            esistente = Bolla.query.filter_by(hash_pdf=hash_val).first()
            if esistente:
                flash(
                    f"Attenzione: questo PDF è già stato caricato "
                    f"(Bolla #{esistente.numero_bolla} del {esistente.data_arrivo}). "
                    f'<a href="{url_for("entrate.dettaglio", id=esistente.id)}">Visualizza</a>',
                    "warning"
                )
                return render_template("entrate_form.html", form=form, titolo="Nuova Bolla")

        bolla = Bolla(
            numero_bolla=form.numero_bolla.data,
            fornitore=form.fornitore.data,
            fornitore_nome=form.fornitore.data,
            data_arrivo=form.data_arrivo.data,
            stato=form.stato.data,
            note=form.note.data,
            hash_pdf=hash_val,
            operatore_id=current_user.id,
        )

        # Salva il file PDF se presente
        if request.files.get("file_pdf"):
            file = request.files["file_pdf"]
            if file.filename:
                from werkzeug.utils import secure_filename
                import os
                filename = secure_filename(file.filename)
                upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                bolla.file_path = file_path

        db.session.add(bolla)
        db.session.flush()

        # Salva righe dal form (OCR o manuali)
        import json
        try:
            righe_json = request.form.get("righe_json", "[]")
            righe_data = json.loads(righe_json)
        except (json.JSONDecodeError, TypeError):
            righe_data = []

        for r in righe_data:
            riga = DettaglioBolla(
                bolla_id=bolla.id,
                articolo_codice=r.get("descrizione", ""),
                descrizione=r.get("descrizione", ""),
                quantita_colli=int(r.get("quantita", 1)),
                quantita_pallet=int(r.get("pallet", 0)),
                peso_kg=float(r.get("peso_kg", 0)),
            )
            db.session.add(riga)

            # Aggiorna giacenza
            art_codice = r.get("descrizione", "")
            if art_codice:
                giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
                if giac:
                    giac.colli = (giac.colli or 0) + int(r.get("quantita", 1))
                    giac.peso_kg = (giac.peso_kg or 0) + float(r.get("peso_kg", 0))
                    giac.updated_by = current_user.id
                else:
                    giac = Giacenza(
                        codice_articolo=art_codice,
                        descrizione=art_codice,
                        colli=int(r.get("quantita", 1)),
                        pallet=int(r.get("pallet", 0)),
                        peso_kg=float(r.get("peso_kg", 0)),
                        updated_by=current_user.id,
                    )
                    db.session.add(giac)

                # Registra movimento
                mov = Movimento(
                    tipo="ingresso",
                    articolo_codice=art_codice,
                    descrizione=art_codice,
                    colli=int(r.get("quantita", 1)),
                    pallet=int(r.get("pallet", 0)),
                    peso_kg=float(r.get("peso_kg", 0)),
                    riferimento_id=bolla.id,
                    riferimento_tipo="bolla",
                    user_id=current_user.id,
                    note=f"Bolla {form.numero_bolla.data} - {form.fornitore.data}",
                )
                db.session.add(mov)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Errore: questo PDF è già stato caricato (duplicato rilevato dal sistema).", "warning")
            return redirect(url_for("entrate.lista"))

        log_activity(current_user.id, "carica_bolla",
            f"{current_user.username} ha caricato la bolla {bolla.numero_bolla} con {len(righe_data)} articoli",
            "bolla", bolla.id)
        create_notification(None, "Bolla caricata",
            f"{current_user.username} ha caricato la bolla {bolla.numero_bolla}", "success")
        flash("Bolla caricata con successo.", "success")
        return redirect(url_for("entrate.lista"))
    return render_template("entrate_form.html", form=form, titolo="Nuova Bolla")


@entrate.route("/bolla/<int:id>")
@login_required
def dettaglio(id):
    bolla = Bolla.query.get_or_404(id)
    return render_template("entrate_dettaglio.html", bolla=bolla)


@entrate.route("/bolla/<int:id>/modifica", methods=["GET", "POST"])
@login_required
def modifica(id):
    bolla = Bolla.query.get_or_404(id)
    form = BollaForm(obj=bolla)
    if form.validate_on_submit():
        bolla.numero_bolla = form.numero_bolla.data
        bolla.fornitore = form.fornitore.data
        bolla.data_arrivo = form.data_arrivo.data
        bolla.stato = form.stato.data
        bolla.note = form.note.data

        import json
        from datetime import datetime, timezone

        # Carica righe dal form
        try:
            righe_json = request.form.get("righe_json", "[]")
            righe_data = json.loads(righe_json)
        except (json.JSONDecodeError, TypeError):
            righe_data = []

        # Rileva righe rimosse: annulla le relative giacenze e movimenti
        vecchie_righe = {r.id for r in bolla.righe}
        nuovi_codici = {r.get("descrizione", "").strip() for r in righe_data if r.get("descrizione", "").strip()}

        for vecchia in list(bolla.righe):
            if vecchia.articolo_codice not in nuovi_codici:
                giac = Giacenza.query.filter_by(codice_articolo=vecchia.articolo_codice).first()
                if giac:
                    giac.colli = max(0, (giac.colli or 0) - (vecchia.quantita_colli or 0))
                    giac.peso_kg = max(0, (giac.peso_kg or 0) - (vecchia.peso_kg or 0))
                    giac.updated_by = current_user.id
                Movimento.query.filter_by(riferimento_id=bolla.id, riferimento_tipo="bolla",
                    articolo_codice=vecchia.articolo_codice).delete()
                db.session.delete(vecchia)

        # Salva nuove righe
        for r in righe_data:
            art_codice = r.get("descrizione", "").strip()
            if not art_codice:
                continue
            riga = DettaglioBolla(
                bolla_id=bolla.id,
                articolo_codice=art_codice,
                descrizione=art_codice,
                quantita_colli=int(r.get("quantita", 1)),
                quantita_pallet=int(r.get("pallet", 0)),
                peso_kg=float(r.get("peso_kg", 0)),
            )
            db.session.add(riga)

            giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
            if giac:
                giac.colli = (giac.colli or 0) + int(r.get("quantita", 1))
                giac.peso_kg = (giac.peso_kg or 0) + float(r.get("peso_kg", 0))
                giac.updated_by = current_user.id
            else:
                giac = Giacenza(
                    codice_articolo=art_codice,
                    descrizione=art_codice,
                    colli=int(r.get("quantita", 1)),
                    pallet=int(r.get("pallet", 0)),
                    peso_kg=float(r.get("peso_kg", 0)),
                    updated_by=current_user.id,
                )
                db.session.add(giac)

            mov = Movimento(
                tipo="ingresso",
                articolo_codice=art_codice,
                descrizione=art_codice,
                colli=int(r.get("quantita", 1)),
                pallet=int(r.get("pallet", 0)),
                peso_kg=float(r.get("peso_kg", 0)),
                riferimento_id=bolla.id,
                riferimento_tipo="bolla",
                user_id=current_user.id,
                note=f"Bolla {form.numero_bolla.data} - {form.fornitore.data}",
            )
            db.session.add(mov)

        db.session.commit()
        log_activity(current_user.id, "modifica_bolla",
            f"{current_user.username} ha modificato la bolla {bolla.numero_bolla}",
            "bolla", bolla.id)
        flash("Bolla aggiornata con successo.", "success")
        return redirect(url_for("entrate.dettaglio", id=bolla.id))

    # Passa righe esistenti come JSON al template
    righe_json = json.dumps([{
        "descrizione": r.articolo_codice or r.descrizione or "",
        "pallet": r.quantita_pallet or 0,
        "quantita": r.quantita_colli or 1,
        "unita_misura": "colli",
        "peso_kg": r.peso_kg or 0,
    } for r in bolla.righe])

    return render_template("entrate_form.html", form=form, titolo="Modifica Bolla", bolla=bolla,
        righe_json=righe_json)


@entrate.route("/bolla/<int:id>/elimina", methods=["POST"])
@login_required
def elimina(id):
    if current_user.role not in ("admin", "ufficio"):
        flash("Solo admin e ufficio possono eliminare bolle.", "error")
        return redirect(url_for("entrate.lista"))
    bolla = Bolla.query.get_or_404(id)
    db.session.delete(bolla)
    db.session.commit()
    log_activity(current_user.id, "elimina_bolla",
        f"{current_user.username} ha eliminato la bolla {bolla.numero_bolla}",
        "bolla", id)
    flash("Bolla eliminata.", "success")
    return redirect(url_for("entrate.lista"))


@entrate.route("/upload-ocr", methods=["POST"])
@login_required
def upload_ocr():
    """Upload PDF e restituisce JSON con dati estratti (testo o OCR via PyMuPDF)."""
    import tempfile, time
    from flask import jsonify

    file = request.files.get("file_pdf")
    if not file:
        return jsonify({"error": "Nessun file"}), 400

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    file.save(tmp.name)
    tmp.close()

    try:
        from core.pdf_extractor import leggi_pdf as pdf_leggi_pdf
        from ocr import estrai_fornitore, estrai_numero_bolla, estrai_data, estrai_righe, estrai_dati

        testo = pdf_leggi_pdf(tmp.name)
        fornitore = estrai_fornitore(testo)
        return jsonify({
            "testo": testo[:2000],
            "dati": estrai_dati(testo, fornitore or "BASE_SPA"),
            "fornitore": fornitore,
            "numero_bolla": estrai_numero_bolla(testo),
            "data_arrivo": estrai_data(testo),
            "righe": estrai_righe(testo),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        import os
        for _ in range(5):
            try:
                os.unlink(tmp.name)
                break
            except OSError:
                time.sleep(0.3)


@entrate.route("/importa")
@login_required
def importa():
    """Pagina dedicata per importazione PDF con review."""
    from flask_wtf.csrf import generate_csrf
    return render_template("entrate_importa.html", csrf_token=generate_csrf())


@entrate.route("/conferma-importa", methods=["POST"])
@login_required
def conferma_importa():
    """Salva la bolla dopo la review dei dati OCR."""
    from flask import jsonify
    import base64, os
    from werkzeug.utils import secure_filename

    numero_bolla = request.form.get("numero_bolla", "").strip()
    fornitore = request.form.get("fornitore", "").strip()
    data_arrivo = request.form.get("data_arrivo", "").strip()
    stato = request.form.get("stato", "da_elaborare")
    note = request.form.get("note", "").strip()
    file_data = request.form.get("file_pdf_base64", "")

    if not numero_bolla or not fornitore:
        flash("Numero bolla e fornitore sono obbligatori.", "error")
        return redirect(url_for("entrate.importa"))

    # Parse date
    data_arrivo_date = None
    if data_arrivo:
        try:
            from datetime import datetime
            data_arrivo_date = datetime.strptime(data_arrivo, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Salva PDF se presente
    file_path = None
    hash_val = None
    if file_data and ";base64," in file_data:
        try:
            header, b64data = file_data.split(";base64,", 1)
            pdf_bytes = base64.b64decode(b64data)
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
            os.makedirs(upload_dir, exist_ok=True)
            filename = secure_filename(f"bolla_{numero_bolla}.pdf")
            file_path = os.path.join(upload_dir, filename)
            with open(file_path, "wb") as f:
                f.write(pdf_bytes)
            # Calcola hash
            import hashlib
            hash_val = hashlib.sha256(pdf_bytes).hexdigest()
        except Exception:
            pass

    # Controlla duplicato
    if hash_val:
        esistente = Bolla.query.filter_by(hash_pdf=hash_val).first()
        if esistente:
            flash(
                f"PDF già caricato (Bolla #{esistente.numero_bolla} del {esistente.data_arrivo}).",
                "warning"
            )
            return redirect(url_for("entrate.dettaglio", id=esistente.id))

    bolla = Bolla(
        numero_bolla=numero_bolla,
        fornitore=fornitore,
        fornitore_nome=fornitore,
        data_arrivo=data_arrivo_date,
        stato=stato,
        note=note,
        hash_pdf=hash_val,
        file_path=file_path,
        operatore_id=current_user.id,
    )
    db.session.add(bolla)
    db.session.commit()

    # Salva righe se presenti
    righe_desc = request.form.getlist("righe_desc[]")
    righe_qta = request.form.getlist("righe_qta[]")
    righe_um = request.form.getlist("righe_um[]")
    righe_peso = request.form.getlist("righe_peso[]")
    righe_pallet = request.form.getlist("righe_pallet[]")
    for i in range(len(righe_desc)):
        if righe_desc[i].strip():
            riga = DettaglioBolla(
                bolla_id=bolla.id,
                articolo_codice=righe_desc[i].strip(),
                descrizione=righe_desc[i].strip(),
                quantita_colli=int(righe_qta[i]) if i < len(righe_qta) else 0,
                quantita_pallet=int(righe_pallet[i]) if i < len(righe_pallet) else 0,
                peso_kg=float(righe_peso[i]) if i < len(righe_peso) else 0,
            )
            db.session.add(riga)

            # Aggiorna giacenza
            art_codice = righe_desc[i].strip()
            giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
            if giac:
                giac.colli = (giac.colli or 0) + int(righe_qta[i]) if i < len(righe_qta) else giac.colli
                giac.peso_kg = (giac.peso_kg or 0) + float(righe_peso[i]) if i < len(righe_peso) else giac.peso_kg
                giac.updated_by = current_user.id
            else:
                giac = Giacenza(
                    codice_articolo=art_codice,
                    descrizione=art_codice,
                    colli=int(righe_qta[i]) if i < len(righe_qta) else 0,
                    pallet=int(righe_pallet[i]) if i < len(righe_pallet) else 0,
                    peso_kg=float(righe_peso[i]) if i < len(righe_peso) else 0,
                    updated_by=current_user.id,
                )
                db.session.add(giac)

            # Registra movimento
            mov = Movimento(
                tipo="ingresso",
                articolo_codice=art_codice,
                descrizione=art_codice,
                colli=int(righe_qta[i]) if i < len(righe_qta) else 0,
                pallet=int(righe_pallet[i]) if i < len(righe_pallet) else 0,
                peso_kg=float(righe_peso[i]) if i < len(righe_peso) else 0,
                riferimento_id=bolla.id,
                riferimento_tipo="bolla",
                user_id=current_user.id,
                note=f"Bolla {numero_bolla} - {fornitore}",
            )
            db.session.add(mov)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Errore: questo PDF è già stato caricato (duplicato rilevato dal sistema).", "warning")
        return redirect(url_for("entrate.lista"))

    log_activity(current_user.id, "importa_bolla",
        f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF",
        "bolla", bolla.id)
    create_notification(None, "Bolla importata",
        f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF", "success")
    flash(f"Bolla {bolla.numero_bolla} importata con successo.", "success")
    return redirect(url_for("entrate.dettaglio", id=bolla.id))
