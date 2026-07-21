import hashlib
import json
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from flask import current_app
from sqlalchemy.exc import IntegrityError
from extensions import db
from models import Bolla, DettaglioBolla, Giacenza, Movimento
from core.normalize import normalizza_codice_articolo, parse_italian_number


def calcola_hash_pdf(file_storage):
    sha256 = hashlib.sha256()
    file_storage.stream.seek(0)
    while chunk := file_storage.stream.read(8192):
        sha256.update(chunk)
    file_storage.stream.seek(0)
    return sha256.hexdigest()


def bolla_esistente_per_hash(hash_val):
    if not hash_val:
        return None
    return Bolla.query.filter_by(hash_pdf=hash_val).first()


def salva_pdf_su_disco(file, numero_bolla):
    filename = secure_filename(file.filename)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
    filename = f"{timestamp}{numero_bolla}_{filename}"
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)
    return file_path, upload_dir


def parse_righe_json(form_data):
    righe_json = form_data.get("righe_json", "[]")
    try:
        return json.loads(righe_json)
    except (json.JSONDecodeError, TypeError):
        return []


def crea_righe_bolla(bolla_id, righe_data, operatore_id):
    codici = {normalizza_codice_articolo(r.get("descrizione", "")) for r in righe_data if r.get("descrizione", "").strip()}
    giacenze_esistenti = {g.codice_articolo: g for g in Giacenza.query.filter(Giacenza.codice_articolo.in_(codici)).all()}

    for r in righe_data:
        art_codice = normalizza_codice_articolo(r.get("descrizione", ""))
        if not art_codice:
            continue
        riga = DettaglioBolla(
            bolla_id=bolla_id,
            articolo_codice=art_codice,
            descrizione=r.get("descrizione", ""),
            quantita_colli=int(r.get("quantita", 1)),
            quantita_pallet=int(r.get("pallet", 0)),
            peso_kg=float(r.get("peso_kg", 0)),
        )
        db.session.add(riga)
        _aggiorna_giacenza_ingresso(art_codice, r, operatore_id, bolla_id, None, giacenze_esistenti)


def _aggiorna_giacenza_ingresso(art_codice, r, operatore_id, riferimento_id, riferimento_tipo, giacenze_cache=None):
    colli = int(r.get("quantita", 1))
    pallet = int(r.get("pallet", 0))
    peso = float(r.get("peso_kg", 0))

    giac = giacenze_cache.get(art_codice) if giacenze_cache is not None else Giacenza.query.filter_by(codice_articolo=art_codice).first()
    if giac:
        giac.colli = (giac.colli or 0) + colli
        giac.peso_kg = (giac.peso_kg or 0) + peso
        giac.updated_by = operatore_id
    else:
        giac = Giacenza(
            codice_articolo=art_codice,
            descrizione=art_codice,
            colli=colli,
            pallet=pallet,
            peso_kg=peso,
            updated_by=operatore_id,
        )
        db.session.add(giac)
        if giacenze_cache is not None:
            giacenze_cache[art_codice] = giac

    mov = Movimento(
        tipo="ingresso",
        articolo_codice=art_codice,
        descrizione=art_codice,
        colli=colli,
        pallet=pallet,
        peso_kg=peso,
        riferimento_id=riferimento_id,
        riferimento_tipo=riferimento_tipo,
        user_id=operatore_id,
    )
    db.session.add(mov)


def crea_bolla(form, request_files, request_form, operatore_id):
    hash_val = None
    file_path = None

    if request_files.get("file_pdf"):
        file = request_files["file_pdf"]
        hash_val = calcola_hash_pdf(file)
        esistente = bolla_esistente_per_hash(hash_val)
        if esistente:
            return None, esistente

    bolla = Bolla(
        numero_bolla=form.numero_bolla.data,
        fornitore=form.fornitore.data,
        fornitore_nome=form.fornitore.data,
        data_arrivo=form.data_arrivo.data,
        stato=form.stato.data,
        note=form.note.data,
        hash_pdf=hash_val,
        operatore_id=operatore_id,
    )

    if request_files.get("file_pdf"):
        file = request_files["file_pdf"]
        if file.filename:
            file_path, _ = salva_pdf_su_disco(file, form.numero_bolla.data)
            bolla.file_path = file_path

    db.session.add(bolla)
    db.session.flush()

    righe_data = parse_righe_json(request_form)
    crea_righe_bolla(bolla.id, righe_data, operatore_id)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise

    return bolla, None


def modifica_bolla(bolla, form, request_form, operatore_id):
    bolla.numero_bolla = form.numero_bolla.data
    bolla.fornitore = form.fornitore.data
    bolla.data_arrivo = form.data_arrivo.data
    bolla.stato = form.stato.data
    bolla.note = form.note.data

    righe_data = parse_righe_json(request_form)
    _sostituisci_righe_bolla(bolla, righe_data, operatore_id)

    db.session.commit()
    return bolla


def _sostituisci_righe_bolla(bolla, righe_data, operatore_id):
    nuovi_codici = {
        normalizza_codice_articolo(r.get("descrizione", ""))
        for r in righe_data if r.get("descrizione", "").strip()
    }

    for vecchia in list(bolla.righe):
        if vecchia.articolo_codice not in nuovi_codici:
            _annulla_giacenza_movimento(vecchia, bolla.id)
            db.session.delete(vecchia)

    for r in righe_data:
        art_codice = normalizza_codice_articolo(r.get("descrizione", ""))
        if not art_codice:
            continue
        riga = DettaglioBolla(
            bolla_id=bolla.id,
            articolo_codice=art_codice,
            descrizione=r.get("descrizione", ""),
            quantita_colli=int(r.get("quantita", 1)),
            quantita_pallet=int(r.get("pallet", 0)),
            peso_kg=float(r.get("peso_kg", 0)),
        )
        db.session.add(riga)
        _aggiorna_giacenza_ingresso(art_codice, r, operatore_id, bolla.id, "bolla")


def _annulla_giacenza_movimento(riga, riferimento_id):
    giac = Giacenza.query.filter_by(codice_articolo=riga.articolo_codice).first()
    if giac:
        giac.colli = max(0, (giac.colli or 0) - (riga.quantita_colli or 0))
        giac.peso_kg = max(0, (giac.peso_kg or 0) - (riga.peso_kg or 0))
    Movimento.query.filter_by(
        riferimento_id=riferimento_id,
        riferimento_tipo="bolla",
        articolo_codice=riga.articolo_codice,
    ).delete()


def importa_bolla_da_pdf(form_data, operatore_id):
    import base64

    numero_bolla = form_data.get("numero_bolla", "").strip()
    fornitore = form_data.get("fornitore", "").strip()
    data_arrivo_str = form_data.get("data_arrivo", "").strip()
    stato = form_data.get("stato", "da_elaborare")
    note = form_data.get("note", "").strip()
    file_data = form_data.get("file_pdf_base64", "")

    data_arrivo_date = None
    if data_arrivo_str:
        try:
            data_arrivo_date = datetime.strptime(data_arrivo_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    file_path = None
    hash_val = None
    if file_data and ";base64," in file_data:
        try:
            header, b64data = file_data.split(";base64,", 1)
            pdf_bytes = base64.b64decode(b64data)
            upload_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "docs"
            )
            os.makedirs(upload_dir, exist_ok=True)
            filename = secure_filename(f"bolla_{numero_bolla}.pdf")
            file_path = os.path.join(upload_dir, filename)
            with open(file_path, "wb") as f:
                f.write(pdf_bytes)
            hash_val = hashlib.sha256(pdf_bytes).hexdigest()
        except Exception:
            file_path = None

    if hash_val:
        esistente = bolla_esistente_per_hash(hash_val)
        if esistente:
            return None, esistente

    bolla = Bolla(
        numero_bolla=numero_bolla,
        fornitore=fornitore,
        fornitore_nome=fornitore,
        data_arrivo=data_arrivo_date,
        stato=stato,
        note=note,
        hash_pdf=hash_val,
        file_path=file_path,
        operatore_id=operatore_id,
    )
    db.session.add(bolla)
    db.session.flush()

    righe_desc = form_data.getlist("righe_desc[]")
    righe_qta = form_data.getlist("righe_qta[]")
    righe_peso = form_data.getlist("righe_peso[]")
    righe_pallet = form_data.getlist("righe_pallet[]")

    for i in range(len(righe_desc)):
        art_codice = normalizza_codice_articolo(righe_desc[i])
        if art_codice:
            colli = int(righe_qta[i]) if i < len(righe_qta) else 0
            pallet = int(righe_pallet[i]) if i < len(righe_pallet) else 0
            peso = parse_italian_number(righe_peso[i]) if i < len(righe_peso) else 0

            riga = DettaglioBolla(
                bolla_id=bolla.id,
                articolo_codice=art_codice,
                descrizione=righe_desc[i].strip(),
                quantita_colli=colli,
                quantita_pallet=pallet,
                peso_kg=peso,
            )
            db.session.add(riga)

            _aggiorna_giacenza_ingresso(art_codice, {
                "quantita": colli, "pallet": pallet, "peso_kg": peso
            }, operatore_id, bolla.id, "bolla")

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise

    return bolla, None
