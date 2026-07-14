import os
import json
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import DDT, RigheDDT, Giacenza, Movimento, db
from forms import DDTForm
from routes.auth import log_activity, create_notification
from pdf_generator import genera_ddt_pdf
from io import BytesIO

uscite = Blueprint("uscite", __name__, url_prefix="/uscite")


@uscite.route("/")
@login_required
def lista():
    stato = request.args.get("stato", "")
    query = DDT.query.order_by(DDT.created_at.desc())
    if stato:
        query = query.filter_by(stato=stato)
    ddt = query.all()
    return render_template("uscite.html", ddt_list=ddt, filtro_stato=stato)


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
    """Controlla se esiste già un DDT per lo stesso articolo e stesso giorno."""
    codice = request.args.get("codice", "").strip()
    oggi = date.today()
    if not codice:
        return jsonify({"duplicato": False})
    esistente = RigheDDT.query.join(DDT).filter(
        RigheDDT.articolo_codice == codice,
        db.func.date(DDT.data_creazione) == oggi,
        DDT.stato != "annullato",
    ).first()
    if esistente:
        return jsonify({
            "duplicato": True,
            "ddt_id": esistente.ddt_id,
            "numero_ddt": esistente.ddt.numero_ddt,
        })
    return jsonify({"duplicato": False})


@uscite.route("/nuovo", methods=["GET", "POST"])
@login_required
def nuovo():
    form = DDTForm()
    if form.validate_on_submit():
        # Legge e valida le righe PRIMA di creare il DDT
        righe_json = request.form.get("righe_json", "[]")
        try:
            righe_data = json.loads(righe_json)
        except (json.JSONDecodeError, TypeError):
            righe_data = []

        insufficienti = []
        for r in righe_data:
            art_codice = r.get("articolo_codice", "")
            colli_richiesti = int(r.get("quantita_colli", 0))
            peso_richiesto = float(r.get("peso_kg", 0))
            if colli_richiesti > 0 or peso_richiesto > 0:
                giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
                if not giac:
                    insufficienti.append(f"{art_codice} (nessuna giacenza)")
                else:
                    if colli_richiesti > 0 and (giac.colli or 0) < colli_richiesti:
                        disp = giac.colli or 0
                        insufficienti.append(f"{art_codice} ({colli_richiesti} colli richiesti, {disp} disponibili)")
                    if peso_richiesto > 0 and (giac.peso_kg or 0) < peso_richiesto:
                        disp = giac.peso_kg or 0
                        insufficienti.append(f"{art_codice} ({peso_richiesto} kg richiesti, {disp} disponibili)")

        if insufficienti:
            flash(f"Stock insufficiente per: {'; '.join(insufficienti)}. DDT non creato.", "error")
            return redirect(url_for("uscite.nuovo"))

        ddt = DDT(
            numero_ddt=form.numero_ddt.data,
            cliente=form.cliente.data,
            destinatario=form.destinatario.data or form.cliente.data,
            provenienza=request.form.get("provenienza", ""),
            vettore=request.form.get("vettore", ""),
            causale_trasporto=request.form.get("causale_trasporto", "Vendita"),
            data_spedizione=form.data_spedizione.data,
            stato=form.stato.data,
            note=form.note.data,
            operatore_id=current_user.id,
        )
        db.session.add(ddt)
        db.session.flush()

        for r in righe_data:
            riga = RigheDDT(
                ddt_id=ddt.id,
                articolo_codice=r.get("articolo_codice", ""),
                descrizione=r.get("descrizione", ""),
                quantita_colli=int(r.get("quantita_colli", 0)),
                quantita_pallet=int(r.get("quantita_pallet", 0)),
                peso_kg=float(r.get("peso_kg", 0)),
                ubicazione=r.get("ubicazione", ""),
            )
            db.session.add(riga)

            # Aggiorna giacenza (stock già verificato sopra)
            giac = Giacenza.query.filter_by(codice_articolo=r.get("articolo_codice", "")).first()
            if giac:
                colli_da_scaricare = int(r.get("quantita_colli", 0))
                if colli_da_scaricare > 0 and giac.colli >= colli_da_scaricare:
                    giac.colli -= colli_da_scaricare
                peso_da_scaricare = float(r.get("peso_kg", 0))
                if peso_da_scaricare > 0 and (giac.peso_kg or 0) >= peso_da_scaricare:
                    giac.peso_kg = (giac.peso_kg or 0) - peso_da_scaricare
                giac.updated_by = current_user.id

            # Registra movimento
            mov = Movimento(
                tipo="uscita",
                articolo_codice=r.get("articolo_codice", ""),
                descrizione=r.get("descrizione", ""),
                colli=int(r.get("quantita_colli", 0)),
                pallet=int(r.get("quantita_pallet", 0)),
                peso_kg=float(r.get("peso_kg", 0)),
                ubicazione=r.get("ubicazione", ""),
                riferimento_id=ddt.id,
                riferimento_tipo="ddt",
                user_id=current_user.id,
                note=f"DDT {form.numero_ddt.data} - {form.cliente.data}",
            )
            db.session.add(mov)

        db.session.commit()

        # Genera PDF
        ddt_data = {
            "numero_ddt": ddt.numero_ddt,
            "data": ddt.data_creazione.strftime("%d/%m/%Y"),
            "cliente": ddt.cliente,
            "destinatario": ddt.destinatario or ddt.cliente,
            "vettore": request.form.get("vettore", ""),
            "causale_trasporto": request.form.get("causale_trasporto", "Vendita"),
            "provenienza": request.form.get("provenienza", ""),
        }
        pdf_bytes = genera_ddt_pdf(ddt_data, righe_data)

        # Salva PDF su disco
        pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_filename = f"DDT_{ddt.numero_ddt.replace('/', '_')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        ddt.filename_pdf = pdf_path
        db.session.commit()

        log_activity(current_user.id, "crea_ddt",
            f"{current_user.username} ha generato il DDT {ddt.numero_ddt} con {len(righe_data)} righe",
            "ddt", ddt.id)
        create_notification(None, "DDT generato",
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
        form.populate_obj(ddt)
        ddt.provenienza = request.form.get("provenienza", "")
        ddt.vettore = request.form.get("vettore", "")
        ddt.causale_trasporto = request.form.get("causale_trasporto", "Vendita")

        # Carica righe dal form
        try:
            righe_json = request.form.get("righe_json", "[]")
            righe_data = json.loads(righe_json)
        except (json.JSONDecodeError, TypeError):
            righe_data = []

        # Annulla giacenze e movimenti delle vecchie righe
        for vecchia in list(ddt.righe):
            giac = Giacenza.query.filter_by(codice_articolo=vecchia.articolo_codice).first()
            if giac:
                giac.colli = (giac.colli or 0) + (vecchia.quantita_colli or 0)
                giac.peso_kg = (giac.peso_kg or 0) + (vecchia.peso_kg or 0)
                giac.updated_by = current_user.id
            Movimento.query.filter_by(riferimento_id=ddt.id, riferimento_tipo="ddt",
                articolo_codice=vecchia.articolo_codice).delete()
            db.session.delete(vecchia)

        # Salva nuove righe
        for r in righe_data:
            art_codice = r.get("articolo_codice", "").strip()
            if not art_codice:
                continue
            riga = RigheDDT(
                ddt_id=ddt.id,
                articolo_codice=art_codice,
                descrizione=r.get("descrizione", ""),
                quantita_colli=int(r.get("quantita_colli", 0)),
                quantita_pallet=int(r.get("quantita_pallet", 0)),
                peso_kg=float(r.get("peso_kg", 0)),
                ubicazione=r.get("ubicazione", ""),
            )
            db.session.add(riga)

            giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
            if giac:
                colli = int(r.get("quantita_colli", 0))
                if colli > 0 and giac.colli >= colli:
                    giac.colli -= colli
                peso = float(r.get("peso_kg", 0))
                if peso > 0 and (giac.peso_kg or 0) >= peso:
                    giac.peso_kg = (giac.peso_kg or 0) - peso
                giac.updated_by = current_user.id

        db.session.commit()

        # Rigenera PDF
        try:
            pdf_bytes = genera_ddt_pdf({
                "numero_ddt": ddt.numero_ddt,
                "data": ddt.data_creazione.strftime("%d/%m/%Y"),
                "cliente": ddt.cliente,
                "destinatario": ddt.destinatario or ddt.cliente,
                "vettore": request.form.get("vettore", ""),
                "causale_trasporto": request.form.get("causale_trasporto", "Vendita"),
                "provenienza": request.form.get("provenienza", ""),
            }, righe_data)
            pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
            os.makedirs(pdf_dir, exist_ok=True)
            pdf_filename = f"DDT_{ddt.numero_ddt.replace('/', '_')}.pdf"
            pdf_path = os.path.join(pdf_dir, pdf_filename)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            ddt.filename_pdf = pdf_path
            db.session.commit()
        except Exception:
            pass

        log_activity(current_user.id, "modifica_ddt",
            f"{current_user.username} ha modificato il DDT {ddt.numero_ddt}",
            "ddt", ddt.id)
        flash("DDT aggiornato con successo.", "success")
        return redirect(url_for("uscite.dettaglio", id=ddt.id))

    # Passa righe esistenti come JSON al template
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
def elimina(id):
    if current_user.role not in ("admin", "ufficio"):
        flash("Solo admin e ufficio possono eliminare DDT.", "error")
        return redirect(url_for("uscite.lista"))
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