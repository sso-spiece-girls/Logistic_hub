from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Bolla, DettaglioBolla, Giacenza, Movimento
from forms import BollaForm
from routes.auth import log_activity, create_notification
from core.auth_decorators import staff_required
from services.bolla_service import (
    calcola_hash_pdf, bolla_esistente_per_hash, crea_bolla, modifica_bolla,
    parse_righe_json, importa_bolla_da_pdf
)

entrate = Blueprint("entrate", __name__, url_prefix="/entrate")


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
        modifica_bolla(bolla, form, request.form, current_user.id)
        log_activity(current_user.id, "modifica_bolla",
            f"{current_user.username} ha modificato la bolla {bolla.numero_bolla}", "bolla", bolla.id)
        flash("Bolla aggiornata con successo.", "success")
        return redirect(url_for("entrate.dettaglio", id=bolla.id))

    import json
    righe_json = json.dumps([{
        "descrizione": r.articolo_codice or r.descrizione or "",
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
    bolla = Bolla.query.get_or_404(id)
    db.session.delete(bolla)
    db.session.commit()
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

    from fornitori import riconosci_fornitore
    plugin = riconosci_fornitore(testo)
    if plugin:
        dati = plugin.parse_bolla(testo)
        fornitore = plugin.estrai_fornitore(testo)
        return {
            "testo": testo[:2000],
            "dati": [{"picking": r.get("descrizione", ""), "pallet": r.get("pallet", 0), "colli": r.get("quantita", 0), "peso_kg": r.get("peso_kg", 0)} for r in dati.get("righe", [])],
            "fornitore": fornitore,
            "numero_bolla": dati.get("numero_bolla", ""),
            "data_arrivo": _converti_data(dati.get("data_arrivo", "")),
            "righe": dati.get("righe", []),
        }

    from clients import riconosci_cliente
    plugin_cliente = riconosci_cliente(testo)
    if plugin_cliente:
        dati = plugin_cliente.parse_ddt(testo)
        righe = [{"descrizione": a.get("codice", "") + " " + a.get("descrizione", ""), "quantita": a.get("qta", 0), "pallet": 0, "unita_misura": a.get("unita", "PZ"), "peso_kg": 0} for a in dati.get("articoli", [])]
        data_ddt = dati.get("data", "")
        return {
            "testo": testo[:2000],
            "dati": [],
            "fornitore": plugin_cliente.nome,
            "numero_bolla": dati.get("ddt", ""),
            "data_arrivo": _converti_data(data_ddt),
            "righe": righe,
        }

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


@entrate.route("/upload-ocr", methods=["POST"])
@login_required
def upload_ocr():
    import os as _os
    import tempfile
    from time import sleep
    files = request.files.getlist("file_pdf") or [request.files.get("file_pdf")]
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "Nessun file"}), 400

    risultati = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            risultati.append({"filename": file.filename, "error": "Solo PDF"})
            continue
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        file.save(tmp.name)
        tmp.close()
        try:
            res = _processa_un_pdf(tmp.name)
            res["filename"] = file.filename
            risultati.append(res)
        except Exception as e:
            risultati.append({"filename": file.filename, "error": str(e)})
        finally:
            for _ in range(5):
                try:
                    _os.unlink(tmp.name)
                    break
                except OSError:
                    sleep(0.3)

    resp = {"risultati": risultati}
    if len(risultati) == 1 and not risultati[0].get("error"):
        r = risultati[0]
        resp["testo"] = r.get("testo", "")
        resp["dati"] = r.get("dati", [])
        resp["fornitore"] = r.get("fornitore", "")
        resp["numero_bolla"] = r.get("numero_bolla", "")
        resp["data_arrivo"] = r.get("data_arrivo", "")
        resp["righe"] = r.get("righe", [])
    return jsonify(resp)


@entrate.route("/importa")
@login_required
def importa():
    from flask_wtf.csrf import generate_csrf
    return render_template("entrate_importa.html", csrf_token=generate_csrf())


@entrate.route("/conferma-importa", methods=["POST"])
@login_required
def conferma_importa():
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
    create_notification(None, "Bolla importata",
        f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF", "success")
    flash(f"Bolla {bolla.numero_bolla} importata con successo.", "success")
    return redirect(url_for("entrate.dettaglio", id=bolla.id))


@entrate.route("/conferma-importa-multi", methods=["POST"])
@login_required
def conferma_importa_multi():
    import json
    try:
        bolle_data = json.loads(request.form.get("bolle_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        flash("Errore: dati bolle non validi.", "error")
        return redirect(url_for("entrate.importa"))

    if not bolle_data:
        flash("Nessuna bolla da importare.", "warning")
        return redirect(url_for("entrate.importa"))

    importate = 0
    errori = 0
    for idx, bd in enumerate(bolle_data):
        numero_bolla = (bd.get("numero_bolla") or "").strip()
        fornitore = (bd.get("fornitore") or "").strip()
        if not numero_bolla or not fornitore:
            errori += 1
            continue

        from werkzeug.datastructures import ImmutableMultiDict
        righe = bd.get("righe", [])
        form_data_list = [
            ("numero_bolla", numero_bolla),
            ("fornitore", fornitore),
            ("data_arrivo", (bd.get("data_arrivo") or "").strip()),
            ("stato", bd.get("stato", "da_elaborare")),
            ("note", (bd.get("note") or "").strip()),
            ("file_pdf_base64", (bd.get("file_pdf_base64") or "")),
        ]

        pdf_bytes = None
        file_data = bd.get("file_pdf_base64", "")
        if file_data and ";base64," in file_data:
            import base64
            try:
                header, b64data = file_data.split(";base64,", 1)
                pdf_bytes = base64.b64decode(b64data)
            except Exception:
                pdf_bytes = None

        if pdf_bytes:
            hash_val = hashlib.sha256(pdf_bytes).hexdigest()
            from services.bolla_service import bolla_esistente_per_hash
            if bolla_esistente_per_hash(hash_val):
                errori += 1
                continue

        for r in righe:
            form_data_list.append(("righe_desc[]", r.get("descrizione", "")))
            form_data_list.append(("righe_qta[]", str(r.get("quantita", 1))))
            form_data_list.append(("righe_pallet[]", str(r.get("pallet", 0))))
            form_data_list.append(("righe_peso[]", str(r.get("peso_kg", 0))))

        from werkzeug.datastructures import ImmutableMultiDict as _IMD
        dummy_form = _IMD(form_data_list)

        try:
            bolla, _ = importa_bolla_da_pdf(dummy_form, current_user.id)
            if bolla:
                importate += 1
                log_activity(current_user.id, "importa_bolla",
                    f"{current_user.username} ha importato la bolla {bolla.numero_bolla} da PDF multiplo", "bolla", bolla.id)
        except Exception:
            errori += 1

    if importate:
        create_notification(None, "Bolle importate",
            f"{current_user.username} ha importato {importate} bolle da PDF", "success")
        flash(f"{importate} bolle importate con successo.", "success")
    if errori:
        flash(f"{errori} bolle non importate (dati mancanti o duplicati).", "warning")
    return redirect(url_for("entrate.lista"))
