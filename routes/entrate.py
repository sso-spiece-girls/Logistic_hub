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


@entrate.route("/upload-ocr", methods=["POST"])
@login_required
def upload_ocr():
    import os as _os
    import tempfile
    from time import sleep
    file = request.files.get("file_pdf")
    if not file:
        return jsonify({"error": "Nessun file"}), 400
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Sono ammessi solo file PDF"}), 400
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    file.save(tmp.name)
    tmp.close()
    try:
        from core.pdf_extractor import leggi_pdf as pdf_leggi_pdf
        testo = pdf_leggi_pdf(tmp.name)

        from fornitori import riconosci_fornitore
        plugin = riconosci_fornitore(testo)
        if plugin:
            dati = plugin.parse_bolla(testo)
            fornitore = plugin.estrai_fornitore(testo)
            return jsonify({
                "testo": testo[:2000],
                "dati": [{
                    "picking": r.get("descrizione", ""),
                    "pallet": r.get("pallet", 0),
                    "colli": r.get("quantita", 0),
                    "peso_kg": r.get("peso_kg", 0),
                } for r in dati.get("righe", [])],
                "fornitore": fornitore,
                "numero_bolla": dati.get("numero_bolla", ""),
                "data_arrivo": dati.get("data_arrivo", ""),
                "righe": dati.get("righe", []),
            })

        from clients import riconosci_cliente
        plugin_cliente = riconosci_cliente(testo)
        if plugin_cliente:
            dati = plugin_cliente.parse_ddt(testo)
            righe = [{
                "descrizione": a.get("codice", "") + " " + a.get("descrizione", ""),
                "quantita": a.get("qta", 0),
                "pallet": 0,
                "unita_misura": a.get("unita", "PZ"),
                "peso_kg": 0,
            } for a in dati.get("articoli", [])]
            return jsonify({
                "testo": testo[:2000],
                "dati": [],
                "fornitore": dati.get("cliente", ""),
                "numero_bolla": dati.get("ddt", ""),
                "data_arrivo": dati.get("data", "").replace("/", "-") if "/" in dati.get("data", "") else dati.get("data", ""),
                "righe": righe,
            })

        from ocr import estrai_fornitore, estrai_numero_bolla, estrai_data, estrai_righe, estrai_dati
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
        for _ in range(5):
            try:
                _os.unlink(tmp.name)
                break
            except OSError:
                sleep(0.3)


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
