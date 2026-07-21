import json
import os
from datetime import date
from flask import current_app
from sqlalchemy import update as sa_update
from extensions import db
from models import DDT, RigheDDT, Giacenza, Movimento
from core.normalize import normalizza_codice_articolo
from pdf_generator import genera_ddt_pdf


def parse_righe_json(form_data):
    righe_json = form_data.get("righe_json", "[]")
    try:
        return json.loads(righe_json)
    except (json.JSONDecodeError, TypeError):
        return []


def verifica_stock(righe_data):
    insufficienti = []
    for r in righe_data:
        art_codice = normalizza_codice_articolo(r.get("articolo_codice", ""))
        colli_richiesti = int(r.get("quantita_colli", 0))
        peso_richiesto = float(r.get("peso_kg", 0))
        if colli_richiesti > 0 or peso_richiesto > 0:
            giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
            if not giac:
                insufficienti.append(f"{art_codice} (nessuna giacenza)")
            else:
                if colli_richiesti > 0 and (giac.colli or 0) < colli_richiesti:
                    insufficienti.append(
                        f"{art_codice} ({colli_richiesti} colli richiesti, {giac.colli or 0} disponibili)"
                    )
                if peso_richiesto > 0 and (giac.peso_kg or 0) < peso_richiesto:
                    insufficienti.append(
                        f"{art_codice} ({peso_richiesto} kg richiesti, {giac.peso_kg or 0} disponibili)"
                    )
    return insufficienti


def controlla_duplicato_giornaliero(codice):
    if not codice:
        return None
    oggi = date.today()
    esistente = RigheDDT.query.join(DDT).filter(
        RigheDDT.articolo_codice == codice,
        db.func.date(DDT.data_creazione) == oggi,
        DDT.stato != "annullato",
    ).first()
    if esistente:
        return {"ddt_id": esistente.ddt_id, "numero_ddt": esistente.ddt.numero_ddt}
    return None


def scarica_giacenza_atomico(art_codice, colli_da_scaricare, peso_da_scaricare, operatore_id, pallet_da_scaricare=0):
    if colli_da_scaricare == 0 and peso_da_scaricare == 0 and pallet_da_scaricare == 0:
        return True
    stmt = sa_update(Giacenza)
    conditions = [Giacenza.codice_articolo == art_codice]
    values = {"updated_by": operatore_id}
    if colli_da_scaricare > 0:
        conditions.append(Giacenza.colli >= colli_da_scaricare)
        values["colli"] = Giacenza.colli - colli_da_scaricare
        values["quantita"] = Giacenza.quantita - colli_da_scaricare
    if peso_da_scaricare > 0:
        conditions.append(Giacenza.peso_kg >= peso_da_scaricare)
        values["peso_kg"] = Giacenza.peso_kg - peso_da_scaricare
    if pallet_da_scaricare > 0:
        conditions.append(Giacenza.pallet >= pallet_da_scaricare)
        values["pallet"] = Giacenza.pallet - pallet_da_scaricare
    risultato = db.session.execute(stmt.where(*conditions).values(**values))
    return risultato.rowcount > 0


def ripristina_giacenza(art_codice, colli, peso, pallet=0):
    giac = Giacenza.query.filter_by(codice_articolo=art_codice).first()
    if giac:
        giac.colli = (giac.colli or 0) + colli
        giac.pallet = (giac.pallet or 0) + pallet
        giac.peso_kg = (giac.peso_kg or 0) + peso
        giac.quantita = (giac.quantita or 0) + colli


def crea_ddt(form, request_form, operatore_id):
    righe_data = parse_righe_json(request_form)

    insufficienti = verifica_stock(righe_data)
    if insufficienti:
        return None, insufficienti

    ddt = DDT(
        numero_ddt=form.numero_ddt.data,
        cliente=form.cliente.data,
        destinatario=form.destinatario.data or form.cliente.data,
        provenienza=request_form.get("provenienza", ""),
        vettore=request_form.get("vettore", ""),
        causale_trasporto=request_form.get("causale_trasporto", "Vendita"),
        data_spedizione=form.data_spedizione.data,
        stato=form.stato.data,
        note=form.note.data,
        operatore_id=operatore_id,
    )
    db.session.add(ddt)
    db.session.flush()

    for r in righe_data:
        art_codice = normalizza_codice_articolo(r.get("articolo_codice", ""))
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

        colli = int(r.get("quantita_colli", 0))
        peso = float(r.get("peso_kg", 0))
        pallet = int(r.get("quantita_pallet", 0))
        ok = scarica_giacenza_atomico(art_codice, colli, peso, operatore_id, pallet)
        if not ok:
            db.session.rollback()
            return None, [f"Stock insufficiente per {art_codice} durante la creazione"]

        mov = Movimento(
            tipo="uscita",
            articolo_codice=art_codice,
            descrizione=r.get("descrizione", ""),
            colli=colli,
            pallet=int(r.get("quantita_pallet", 0)),
            peso_kg=peso,
            ubicazione=r.get("ubicazione", ""),
            riferimento_id=ddt.id,
            riferimento_tipo="ddt",
            user_id=operatore_id,
            note=f"DDT {form.numero_ddt.data} - {form.cliente.data}",
        )
        db.session.add(mov)

    ddt_data = {
        "numero_ddt": ddt.numero_ddt,
        "data": ddt.data_creazione.strftime("%d/%m/%Y"),
        "cliente": ddt.cliente,
        "destinatario": ddt.destinatario or ddt.cliente,
        "vettore": request_form.get("vettore", ""),
        "causale_trasporto": request_form.get("causale_trasporto", "Vendita"),
        "provenienza": request_form.get("provenienza", ""),
    }
    pdf_bytes = genera_ddt_pdf(ddt_data, righe_data)

    pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_filename = f"DDT_{ddt.numero_ddt.replace('/', '_')}.pdf"
    pdf_path = os.path.join(pdf_dir, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    ddt.filename_pdf = pdf_path

    db.session.commit()
    return ddt, None


def modifica_ddt(ddt, form, request_form, operatore_id):
    form.populate_obj(ddt)
    ddt.provenienza = request_form.get("provenienza", "")
    ddt.vettore = request_form.get("vettore", "")
    ddt.causale_trasporto = request_form.get("causale_trasporto", "Vendita")

    righe_data = parse_righe_json(request_form)

    for vecchia in list(ddt.righe):
        ripristina_giacenza(
            vecchia.articolo_codice,
            vecchia.quantita_colli or 0,
            vecchia.peso_kg or 0,
            vecchia.quantita_pallet or 0,
        )
        Movimento.query.filter_by(
            riferimento_id=ddt.id,
            riferimento_tipo="ddt",
            articolo_codice=vecchia.articolo_codice,
        ).delete()
        db.session.delete(vecchia)

    for r in righe_data:
        art_codice = normalizza_codice_articolo(r.get("articolo_codice", ""))
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

        colli = int(r.get("quantita_colli", 0))
        peso = float(r.get("peso_kg", 0))
        pallet = int(r.get("quantita_pallet", 0))
        ok = scarica_giacenza_atomico(art_codice, colli, peso, operatore_id, pallet)
        if not ok:
            db.session.rollback()
            return None, [f"Stock insufficiente per {art_codice} durante la modifica"]

    try:
        pdf_bytes = genera_ddt_pdf(
            {
                "numero_ddt": ddt.numero_ddt,
                "data": ddt.data_creazione.strftime("%d/%m/%Y"),
                "cliente": ddt.cliente,
                "destinatario": ddt.destinatario or ddt.cliente,
                "vettore": request_form.get("vettore", ""),
                "causale_trasporto": request_form.get("causale_trasporto", "Vendita"),
                "provenienza": request_form.get("provenienza", ""),
            },
            righe_data,
        )
        pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_filename = f"DDT_{ddt.numero_ddt.replace('/', '_')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        ddt.filename_pdf = pdf_path
    except Exception:
        pass

    db.session.commit()
    return ddt, None
