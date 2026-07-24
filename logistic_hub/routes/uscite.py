import os
import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import DDT, RigheDDT, Giacenza, User, db
from forms import DDTForm
from routes.auth import log_activity, create_notification, notifica_operatori
from core.auth_decorators import staff_required
from services.ddt_service import (
    crea_ddt, modifica_ddt, parse_righe_json
)
from pdf_generator import genera_ddt_pdf
from io import BytesIO

uscite = Blueprint("uscite", __name__, url_prefix="/uscite")


@uscite.route("/")
@login_required
def lista():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    stato = request.args.get("stato", "")
    query = DDT.query.options(
        db.joinedload(DDT.operatore).load_only(User.username),
    ).order_by(DDT.created_at.desc())
    if stato:
        query = query.filter_by(stato=stato)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    ddt = pagination.items
    return render_template("uscite.html", ddt_list=ddt, pagination=pagination, filtro_stato=stato)


@uscite.route("/api/articoli")
@login_required
def api_articoli():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])
    query = Giacenza.query.filter(
        db.or_(
            Giacenza.codice_articolo.ilike(f"%{q}%"),
            Giacenza.descrizione.ilike(f"%{q}%"),
        )
    ).order_by(Giacenza.codice_articolo).limit(20).all()
    return jsonify([{
        "codice_articolo": g.codice_articolo,
        "descrizione": g.descrizione,
        "colli": g.colli,
        "pallet": g.pallet or 0,
        "peso_kg": g.peso_kg or 0,
        "ubicazione": g.ubicazione,
        "magazzino": g.magazzino,
    } for g in query])


@uscite.route("/api/duplicato")
@login_required
def api_duplicato():
    from services.ddt_service import controlla_duplicato_giornaliero
    codice = request.args.get("codice", "").strip()
    risultato = controlla_duplicato_giornaliero(codice)
    if risultato:
        return jsonify({"duplicato": True, **risultato})
    return jsonify({"duplicato": False})


@uscite.route("/nuovo", methods=["GET", "POST"])
@login_required
def nuovo():
    form = DDTForm()
    if form.validate_on_submit():
        ddt, errori = crea_ddt(form, request.form, current_user.id)
        if errori:
            flash(f"Stock insufficiente per: {'; '.join(errori)}. DDT non creato.", "error")
            return redirect(url_for("uscite.nuovo"))

        righe_data = parse_righe_json(request.form)
        log_activity(current_user.id, "crea_ddt",
            f"{current_user.username} ha generato il DDT {ddt.numero_ddt} con {len(righe_data)} righe",
            "ddt", ddt.id)
        notifica_operatori("DDT generato",
            f"{current_user.username} ha generato il DDT {ddt.numero_ddt}", "success")
        flash(f"DDT {ddt.numero_ddt} generato con successo.", "success")
        return redirect(url_for("uscite.lista"))

    return render_template("uscite_form.html", form=form, titolo="Nuovo DDT")


@uscite.route("/ddt/<int:id>")
@login_required
def dettaglio(id):
    ddt = DDT.query.get_or_404(id)
    righe = RigheDDT.query.filter_by(ddt_id=ddt.id).all()
    return render_template("uscite_dettaglio.html", ddt=ddt, righe=righe)


@uscite.route("/ddt/<int:id>/modifica", methods=["GET", "POST"])
@login_required
def modifica(id):
    ddt = DDT.query.get_or_404(id)
    form = DDTForm(obj=ddt)
    if form.validate_on_submit():
        risultato, errori = modifica_ddt(ddt, form, request.form, current_user.id)
        if errori:
            flash(f"Stock insufficiente per: {'; '.join(errori)}. Modifica annullata.", "error")
            return redirect(url_for("uscite.lista"))

        log_activity(current_user.id, "modifica_ddt",
            f"{current_user.username} ha modificato il DDT {ddt.numero_ddt}",
            "ddt", ddt.id)
        flash("DDT aggiornato con successo.", "success")
        return redirect(url_for("uscite.dettaglio", id=ddt.id))

    righe_json = json.dumps([{
        "articolo_codice": r.articolo_codice or "",
        "descrizione": r.descrizione or "",
        "quantita_colli": r.quantita_colli or 1,
        "quantita_pallet": r.quantita_pallet or 0,
        "peso_kg": r.peso_kg or 0,
        "ubicazione": r.ubicazione or "",
    } for r in ddt.righe])

    return render_template("uscite_form.html", form=form, titolo="Modifica DDT", ddt=ddt,
        righe_json=righe_json)


@uscite.route("/ddt/<int:id>/elimina", methods=["POST"])
@login_required
@staff_required
def elimina(id):
    ddt = DDT.query.get_or_404(id)
    RigheDDT.query.filter_by(ddt_id=ddt.id).delete()
    db.session.delete(ddt)
    db.session.commit()
    log_activity(current_user.id, "elimina_ddt",
        f"{current_user.username} ha eliminato il DDT {ddt.numero_ddt}",
        "ddt", id)
    flash("DDT eliminato.", "success")
    return redirect(url_for("uscite.lista"))


@uscite.route("/ddt/<int:id>/pdf")
@login_required
def scarica_pdf(id):
    ddt = DDT.query.get_or_404(id)
    righe = RigheDDT.query.filter_by(ddt_id=ddt.id).all()
    righe_data = [{
        "articolo_codice": r.articolo_codice,
        "descrizione": r.descrizione or "",
        "quantita_colli": r.quantita_colli,
        "quantita_pallet": r.quantita_pallet,
        "peso_kg": r.peso_kg,
        "ubicazione": r.ubicazione or "",
        "magazzino": "",
    } for r in righe]
    ddt_data = {
        "numero_ddt": ddt.numero_ddt,
        "data": ddt.data_creazione.strftime("%d/%m/%Y"),
        "cliente": ddt.cliente,
        "destinatario": ddt.destinatario or ddt.cliente,
        "vettore": ddt.note if "Vettore:" in (ddt.note or "") else "",
        "causale_trasporto": "Vendita",
        "provenienza": "",
    }
    pdf_bytes = genera_ddt_pdf(ddt_data, righe_data)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"DDT_{ddt.numero_ddt.replace('/', '_')}.pdf",
    )
