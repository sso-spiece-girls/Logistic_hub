import os
import threading
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from flask_wtf.csrf import validate_csrf, CSRFError
from extensions import db, limiter
from models import Bolla, DettaglioBolla, Giacenza, Movimento
from forms import BollaForm
from routes.auth import log_activity, create_notification, notifica_operatori
from core.auth_decorators import staff_required
from services.bolla_service import (
    calcola_hash_pdf, bolla_esistente_per_hash, crea_bolla, modifica_bolla,
    parse_righe_json, importa_bolla_da_pdf
)

entrate = Blueprint("entrate", __name__, url_prefix="/entrate")


@entrate.route("/")
@login_required
def lista():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    stato = request.args.get("stato", "")
    query = Bolla.query.options(db.joinedload(Bolla.operatore)).order_by(Bolla.created_at.desc())
    if stato:
        query = query.filter_by(stato=stato)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    bolle = pagination.items
    visti = set()
    ids_duplicati = set()
    for b in bolle:
        key = (b.numero_bolla, b.fornitore)
        if key in visti:
            ids_duplicati.add(b.id)
        else:
            visti.add(key)
    return render_template("entrate.html", bolle=bolle, pagination=pagination, filtro_stato=stato, ids_duplicati=ids_duplicati)


@entrate.route("/nuova", methods=["GET", "POST"])
@login_required
def nuova():
    form = BollaForm()
    if form.validate_on_submit():
        try:
            bolla, esistente = crea_bolla(form, request.files, request.form, current_user.id)
        except IntegrityError:
            flash("Errore: questo PDF è già stato caricato (duplicato rilevato dal sistema).", "warning")
            return redirect(url_for("entrate.lista"))

        if esistente:
            flash(f"Attenzione: questo PDF è già stato caricato (Bolla #{esistente.numero_bolla} del {esistente.data_arrivo}). "
                  f'<a href="{url_for("entrate.dettaglio", id=esistente.id)}">Visualizza</a>', "warning")
            return render_template("entrate_form.html", form=form, titolo="Nuova Bolla")

        righe_data = parse_righe_json(request.form)
        log_activity(current_user.id, "carica_bolla",
            f"{current_user.username} ha caricato la bolla {bolla.numero_bolla} con {len(righe_data)} articoli",
            "bolla", bolla.id)
        notifica_operatori("Bolla caricata",
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
        modifica_bolla(bolla, form, request.form, current_user.id)
        log_activity(current_user.id, "modifica_bolla",
            f"{current_user.username} ha modificato la bolla {bolla.numero_bolla}", "bolla", bolla.id)
        flash("Bolla aggiornata con successo.", "success")
        return redirect(url_for("entrate.dettaglio", id=bolla.id))

    import json
    righe_json = json.dumps([{
        "descrizione": r.descrizione or r.articolo_codice or "",
        "pallet": r.quantita_pallet or 0,
        "quantita": r.quantita_colli or 1,
        "unita_misura": "colli",
        "peso_kg": r.peso_kg or 0,
    } for r in bolla.righe])
    return render_template("entrate_form.html", form=form, titolo="Modifica Bolla",
                           bolla=bolla, righe_json=righe_json)


@entrate.route("/bolla/<int:id>/elimina", methods=["POST"])
@login_required
@staff_required
def elimina(id):
    from services.bolla_service import annulla_giacenza_movimento
    bolla = Bolla.query.get_or_404(id)
    try:
        # Ripristina inventario per ogni riga, poi elimina righe e movimenti
        for riga in list(bolla.righe):
            annulla_giacenza_movimento(riga, bolla.id)
            db.session.delete(riga)
        db.session.delete(bolla)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Errore durante l'eliminazione della bolla.", "error")
        return redirect(url_for("entrate.lista"))
    log_activity(current_user.id, "elimina_bolla",
        f"{current_user.username} ha eliminato la bolla {bolla.numero_bolla}", "bolla", id)
    flash("Bolla eliminata.", "success")
    return redirect(url_for("entrate.lista"))


def _converti_data(val):
    if not val:
        return ""
    if "/" in val:
        parti = val.split("/")
        if len(parti) == 3:
            return f"{parti[2]}-{parti[1]}-{parti[0]}"
    return val


def _processa_un_pdf(percorso):
    from core.pdf_extractor import leggi_pdf as pdf_leggi_pdf
    testo = pdf_leggi_pdf(percorso)

    # 1) Plugin cliente (La Leccia, Enegan, Elle Group, Soffas, Magis, DAS)
    #    Deve andare PRIMA dei fornitori perché alcuni PDF cliente (es. La Leccia)
    #    contengono testo che potrebbe matchare pattern generici fornitore.
    from clients import riconosci_cliente
    plugin_cliente = riconosci_cliente(testo)
    if plugin_cliente:
        dati = plugin_cliente.parse_ddt(testo)
        righe = [{"descrizione": a.get("codice", "") + " " + a.get("descrizione", ""), "quantita": a.get("qta", 0), "pallet": 0, "unita_misura": a.get("unita", "PZ"), "peso_kg": 0} for a in dati.get("articoli", [])]
        data_ddt = dati.get("data", "")
        # Aggiorna automaticamente il file Excel mensile del cliente (fatturazione)
        _aggiorna_excel_cliente(plugin_cliente, dati)
        return {
            "testo": testo[:2000],
            "dati": [],
            "fornitore": plugin_cliente.nome,
            "numero_bolla": dati.get("ddt", ""),
            "data_arrivo": _converti_data(data_ddt),
            "righe": righe,
        }

    # 2) Fornitore specifico (Base SPA, Saleri, Carrara)
    from fornitori import riconosci_fornitore as riconosci_fornitore_plugin
    p = riconosci_fornitore_plugin(testo)
    if p and p.id != "gen":
        dati = p.parse_bolla(testo)
        fornitore = p.estrai_fornitore(testo)
        return {
            "testo": testo[:2000],
            "dati": [{"picking": r.get("descrizione", ""), "pallet": r.get("pallet", 0), "colli": r.get("quantita", 0), "peso_kg": r.get("peso_kg", 0)} for r in dati.get("righe", [])],
            "fornitore": fornitore,
            "numero_bolla": dati.get("numero_bolla", ""),
            "data_arrivo": _converti_data(dati.get("data_arrivo", "")),
            "righe": dati.get("righe", []),
        }

    # 3) Fallback generico
    from fornitori.generico import GenericoParser
    gen = GenericoParser({"id": "gen", "nome": "Generico", "pattern_riconoscimento": None})
    dati = gen.parse_bolla(testo)
    fornitore = gen.estrai_fornitore(testo)
    return {
        "testo": testo[:2000],
        "dati": [{"picking": r.get("descrizione", ""), "pallet": r.get("pallet", 0), "colli": r.get("quantita", 0), "peso_kg": r.get("peso_kg", 0)} for r in dati.get("righe", [])],
        "fornitore": fornitore,
        "numero_bolla": dati.get("numero_bolla", ""),
        "data_arrivo": _converti_data(dati.get("data_arrivo", "")),
        "righe": dati.get("righe", []),
    }


_TEMP_PDF_DIR = None
_ocr_tasks = {}
_ocr_tasks_lock = threading.Lock()
_excel_locks = {}
_excel_locks_lock = threading.Lock()


def _aggiorna_excel_cliente(plugin, dati):
    """Aggiorna il file Excel mensile del cliente con i dati del DDT appena parsato.
    Thread-safe: usa un lock per file Excel per evitare race condition."""
    try:
        excel_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs", "excel_clienti")
        os.makedirs(excel_dir, exist_ok=True)
        excel_path = os.path.join(excel_dir, f"{plugin.id}.xlsx")
        with _excel_locks_lock:
            if plugin.id not in _excel_locks:
                _excel_locks[plugin.id] = threading.Lock()
            lock = _excel_locks[plugin.id]
        with lock:
            plugin.genera_excel([dati], excel_path)
    except Exception:
        pass  # Non bloccare l'OCR se la generazione Excel fallisce


def _pulisci_ocr_task(task_id):
    with _ocr_tasks_lock:
        _ocr_tasks.pop(task_id, None)


def _pulisci_vecchie_task():
    import os as _os
    ora = datetime.now(timezone.utc).timestamp()
    with _ocr_tasks_lock:
        da_rimuovere = [tid for tid, t in _ocr_tasks.items() if t.get("status") in ("completed", "error") and ora - t.get("ts", 0) > 3600]
        for tid in da_rimuovere:
            # Delete associated temp PDF
            temp_id = _ocr_tasks[tid].get("result", {}).get("_temp_id", "")
            if temp_id and _TEMP_PDF_DIR:
                p = _os.path.join(_TEMP_PDF_DIR, temp_id + ".pdf")
                try:
                    if _os.path.exists(p):
                        _os.unlink(p)
                except OSError:
                    pass
            del _ocr_tasks[tid]


def _pulisci_temp_pdf_abbandonati():
    """Pulisce file PDF temporanei orfani (più di 2 ore) che non hanno più una task associata."""
    import os as _os
    if not _TEMP_PDF_DIR or not _os.path.exists(_TEMP_PDF_DIR):
        return
    with _ocr_tasks_lock:
        temp_ids_in_uso = set()
        for t in _ocr_tasks.values():
            tid = t.get("result", {}).get("_temp_id", "")
            if tid:
                temp_ids_in_uso.add(tid)
    ora = datetime.now(timezone.utc).timestamp()
    for fname in _os.listdir(_TEMP_PDF_DIR):
        if not fname.endswith(".pdf"):
            continue
        saved_id = fname[:-4]
        if saved_id in temp_ids_in_uso:
            continue
        fpath = _os.path.join(_TEMP_PDF_DIR, fname)
        try:
            if ora - _os.path.getmtime(fpath) > 7200:  # older than 2 hours
                _os.unlink(fpath)
        except OSError:
            pass


def _get_temp_pdf_dir():
    global _TEMP_PDF_DIR
    if _TEMP_PDF_DIR is None:
        import tempfile as _tf
        _TEMP_PDF_DIR = _tf.mkdtemp(prefix="ocr_pdf_")
    return _TEMP_PDF_DIR


def _processa_pdf_in_background(task_id, saved_id, filename, flask_app):
    import os as _os
    from models import Bolla
    dest = _os.path.join(_get_temp_pdf_dir(), saved_id + ".pdf")
    try:
        res = _processa_un_pdf(dest)
        res["filename"] = filename
        res["_temp_id"] = saved_id
        n_bolla = (res.get("numero_bolla") or "").strip()
        fornitore = (res.get("fornitore") or "").strip()
        if n_bolla and fornitore:
            with flask_app.app_context():
                esistente = Bolla.query.filter_by(numero_bolla=n_bolla, fornitore=fornitore).first()
                if esistente:
                    res["duplicato"] = True
                    res["bolla_esistente"] = {
                        "id": esistente.id,
                        "numero_bolla": esistente.numero_bolla,
                        "data_arrivo": str(esistente.data_arrivo or ""),
                        "fornitore": esistente.fornitore
                    }
        with _ocr_tasks_lock:
            _ocr_tasks[task_id] = {"status": "completed", "result": res, "ts": datetime.now(timezone.utc).timestamp()}
    except Exception as e:
        with _ocr_tasks_lock:
            _ocr_tasks[task_id] = {"status": "error", "error": str(e), "filename": filename, "ts": datetime.now(timezone.utc).timestamp()}


@entrate.route("/upload-ocr", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def upload_ocr():
    import uuid
    import os as _os
    from flask import current_app

    # Cleanup temp PDFs abbandonati prima di caricare nuovi file
    _pulisci_temp_pdf_abbandonati()

    _app = current_app._get_current_object()
    files = request.files.getlist("file_pdf") or [request.files.get("file_pdf")]
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "Nessun file"}), 400

    risultati = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            risultati.append({"filename": file.filename, "error": "Solo PDF"})
            continue
        # MIME type validation: check magic bytes %PDF
        file.stream.seek(0)
        header = file.read(5)
        file.stream.seek(0)
        if header != b"%PDF-":
            risultati.append({"filename": file.filename, "error": "Il file non è un PDF valido"})
            continue
        saved_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        dest = _os.path.join(_get_temp_pdf_dir(), saved_id + ".pdf")
        file.save(dest)
        with _ocr_tasks_lock:
            _ocr_tasks[task_id] = {"status": "processing", "filename": file.filename}
        thread = threading.Thread(target=_processa_pdf_in_background, args=(task_id, saved_id, file.filename, _app), daemon=True)
        thread.start()
        risultati.append({"task_id": task_id, "_temp_id": saved_id, "filename": file.filename})

    resp = {"risultati": risultati, "async": True}
    return jsonify(resp)


@entrate.route("/ocr-status/<task_id>")
@login_required
def ocr_status(task_id):
    _pulisci_vecchie_task()
    with _ocr_tasks_lock:
        task = _ocr_tasks.get(task_id)
    if task is None:
        return jsonify({"status": "not_found"}), 404
    if task["status"] == "processing":
        return jsonify({"status": "processing"})
    if task["status"] == "completed":
        res = task["result"]
        resp = {
            "status": "completed",
            "filename": res.get("filename", ""),
            "fornitore": res.get("fornitore", ""),
            "numero_bolla": res.get("numero_bolla", ""),
            "data_arrivo": res.get("data_arrivo", ""),
            "righe": res.get("righe", []),
            "dati": res.get("dati", []),
            "testo": res.get("testo", ""),
            "duplicato": res.get("duplicato", False),
            "bolla_esistente": res.get("bolla_esistente"),
            "_temp_id": res.get("_temp_id", ""),
        }
        return jsonify(resp)
    return jsonify({"status": "error", "error": task.get("error", "Errore sconosciuto"), "filename": task.get("filename", "")})


@entrate.route("/importa")
@login_required
def importa():
    from flask_wtf.csrf import generate_csrf
    return render_template("entrate_importa.html", csrf_token=generate_csrf())


@entrate.route("/conferma-importa", methods=["POST"])
@login_required
def conferma_importa():
    # CSRF validation
    try:
        validate_csrf(request.form.get("csrf_token"))
    except CSRFError:
        abort(403)

    numero_bolla = request.form.get("numero_bolla", "").strip()
    fornitore = request.form.get("fornitore", "").strip()
    if not numero_bolla or not fornitore:
        flash("Numero bolla e fornitore sono obbligatori.", "error")
        return redirect(url_for("entrate.importa"))

    try:
        bolla, esistente = importa_bolla_da_pdf(request.form, current_user.id)
    except IntegrityError:
        flash("Errore: questo PDF è già stato caricato (duplicato rilevato dal sistema).", "warning")
        return redirect(url_for("entrate.lista"))

    if esistente:
        flash(f"PDF già caricato (Bolla #{esistente.numero_bolla} del {esistente.data_arrivo}).", "warning")
        return redirect(url_for("entrate.dettaglio", id=esistente.id))

    log_activity(current_user.id, "importa_bolla",
        f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF", "bolla", bolla.id)
    notifica_operatori("Bolla importata",
        f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF", "success")
    flash(f"Bolla {bolla.numero_bolla} importata con successo.", "success")
    return redirect(url_for("entrate.dettaglio", id=bolla.id))


@entrate.route("/conferma-importa-multi", methods=["POST"])
@login_required
def conferma_importa_multi():
    # CSRF validation
    try:
        validate_csrf(request.form.get("csrf_token"))
    except CSRFError:
        abort(403)

    import json, os as _os, hashlib, base64
    raw = request.form.get("bolle_json", "")
    if not raw:
        flash("Errore: dati bolle non validi (JSON vuoto).", "error")
        return redirect(url_for("entrate.importa"))
    try:
        bolle_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        flash("Errore: dati bolle non validi.", "error")
        return redirect(url_for("entrate.importa"))

    if not bolle_data:
        flash("Nessuna bolla da importare.", "warning")
        return redirect(url_for("entrate.importa"))

    from services.bolla_service import bolla_esistente_per_hash, importa_bolla_da_pdf
    from werkzeug.datastructures import ImmutableMultiDict as _IMD

    processed_ids = set()
    importate = 0
    errori = 0
    for bd in bolle_data:
        numero_bolla = (bd.get("numero_bolla") or "").strip()
        fornitore = (bd.get("fornitore") or "").strip()
        if not numero_bolla or not fornitore:
            errori += 1
            continue

        # Legge il PDF dal file temporaneo salvato da upload-ocr
        temp_id = bd.get("_temp_id", "")
        if temp_id:
            processed_ids.add(temp_id)
        pdf_bytes = None
        if temp_id:
            pdf_path = _os.path.join(_get_temp_pdf_dir(), temp_id + ".pdf")
            if _os.path.exists(pdf_path):
                with open(pdf_path, "rb") as fh:
                    pdf_bytes = fh.read()

        hash_val = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else None
        if hash_val and bolla_esistente_per_hash(hash_val):
            errori += 1
            continue

        righe = bd.get("righe", [])
        form_data_list = [
            ("numero_bolla", numero_bolla),
            ("fornitore", fornitore),
            ("data_arrivo", (bd.get("data_arrivo") or "").strip()),
            ("stato", bd.get("stato", "completata")),
            ("note", (bd.get("note") or "").strip()),
        ]

        # Ricostruisce file_pdf_base64 dal PDF letto da disco (solo per importa_bolla_da_pdf)
        if pdf_bytes:
            f_b64 = base64.b64encode(pdf_bytes).decode("ascii")
            form_data_list.append(("file_pdf_base64", "data:application/pdf;base64," + f_b64))

        for r in righe:
            form_data_list.append(("righe_desc[]", r.get("descrizione", "")))
            form_data_list.append(("righe_qta[]", str(r.get("quantita", 1))))
            form_data_list.append(("righe_pallet[]", str(r.get("pallet", 0))))
            form_data_list.append(("righe_peso[]", str(r.get("peso_kg", 0))))

        dummy_form = _IMD(form_data_list)

        try:
            bolla, _ = importa_bolla_da_pdf(dummy_form, current_user.id)
            if bolla:
                importate += 1
                log_activity(current_user.id, "importa_bolla",
                    f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF multiplo", "bolla", bolla.id)
        except Exception:
            errori += 1

    # Cleanup temp PDFs
    for tid in processed_ids:
        p = _os.path.join(_get_temp_pdf_dir(), tid + ".pdf")
        try:
            _os.unlink(p)
        except OSError:
            pass

    if importate:
        notifica_operatori("Bolle importate",
            f"{current_user.username} ha importato {importate} bolle da PDF", "success")
        flash(f"{importate} bolle importate con successo.", "success")
    if errori:
        flash(f"{errori} bolle non importate (dati mancanti o duplicati).", "warning")
    return redirect(url_for("entrate.lista"))
