from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Bolla, DDT, Giacenza, Picking, db

api = Blueprint("api", __name__, url_prefix="/api/v1")

BOLLA_STATI = ["da_elaborare", "in_lavorazione", "completata"]
DDT_STATI = ["bozza", "pronto", "spedito", "annullato"]
PICKING_STATI = ["aperto", "in_corso", "completato"]


@api.route("/<entity>/<int:entity_id>/stato", methods=["POST"])
@login_required
def cambia_stato(entity, entity_id):
    data = request.get_json(silent=True) or {}
    nuovo_stato = data.get("stato", "").strip()

    model_map = {
        "bolle": (Bolla, BOLLA_STATI),
        "ddt": (DDT, DDT_STATI),
        "picking": (Picking, PICKING_STATI),
    }

    if entity not in model_map:
        return jsonify({"error": "Entità non valida"}), 400

    Model, stati_validi = model_map[entity]
    if nuovo_stato not in stati_validi:
        return jsonify({"error": f"Stato non valido. Valori: {', '.join(stati_validi)}"}), 400

    obj = db.session.get(Model, entity_id)
    if not obj:
        return jsonify({"error": "Oggetto non trovato"}), 404

    obj.stato = nuovo_stato
    obj.updated_at = db.func.now()
    db.session.commit()

    return jsonify({
        "ok": True,
        "stato": nuovo_stato,
        "stato_label": obj.stato_label,
    })


@api.route("/stats")
@login_required
def stats():
    bolle_da_elaborare = Bolla.query.filter_by(stato="da_elaborare").count()
    ddt_oggi = DDT.query.filter(
        db.func.date(DDT.data_creazione) == db.func.date("now")
    ).count()
    giacenze_totali = db.session.query(db.func.sum(Giacenza.quantita)).scalar() or 0
    colli_totali = db.session.query(db.func.sum(Giacenza.colli)).scalar() or 0
    pallet_totali = db.session.query(db.func.sum(Giacenza.pallet)).scalar() or 0
    picking_attivi = Picking.query.filter(Picking.stato.in_(["aperto", "in_corso"])).count()

    return jsonify({
        "bolle_da_elaborare": bolle_da_elaborare,
        "ddt_oggi": ddt_oggi,
        "giacenze_totali": int(giacenze_totali),
        "colli_totali": int(colli_totali),
        "pallet_totali": int(pallet_totali),
        "picking_attivi": picking_attivi,
    })


@api.route("/giacenze")
@login_required
def giacenze_list():
    """Lista giacenze con filtro opzionale, paginata."""
    q = request.args.get("q", "").strip()
    magazzino = request.args.get("magazzino", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 100, type=int)
    per_page = min(per_page, 500)
    query = Giacenza.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(
            Giacenza.codice_articolo.ilike(like),
            Giacenza.descrizione.ilike(like),
            Giacenza.ubicazione.ilike(like),
        ))
    if magazzino:
        query = query.filter(Giacenza.magazzino == magazzino)
    pag = query.order_by(Giacenza.codice_articolo).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [{
            "id": g.id,
            "codice_articolo": g.codice_articolo,
            "descrizione": g.descrizione,
            "quantita": g.quantita,
            "colli": g.colli,
            "pallet": getattr(g, "pallet", 0),
            "ubicazione": g.ubicazione,
            "id_bobina": getattr(g, "id_bobina", None),
            "peso_kg": getattr(g, "peso_kg", 0),
            "magazzino": getattr(g, "magazzino", None),
        } for g in pag.items],
        "page": pag.page,
        "per_page": pag.per_page,
        "total": pag.total,
        "pages": pag.pages,
    })


@api.route("/bolle/recenti")
@login_required
def bolle_recenti():
    """Ultime 20 bolle caricate."""
    bolle = Bolla.query.order_by(Bolla.created_at.desc()).limit(20).all()
    return jsonify([{
        "id": b.id,
        "numero_bolla": b.numero_bolla,
        "fornitore": b.fornitore,
        "data_arrivo": b.data_arrivo.isoformat() if b.data_arrivo else None,
        "stato": b.stato,
    } for b in bolle])


@api.route("/ddt/recenti")
@login_required
def ddt_recenti():
    """Ultimi 20 DDT generati."""
    ddt = DDT.query.order_by(DDT.created_at.desc()).limit(20).all()
    return jsonify([{
        "id": d.id,
        "numero_ddt": d.numero_ddt,
        "cliente": d.cliente,
        "data_spedizione": d.data_spedizione.isoformat() if d.data_spedizione else None,
        "stato": d.stato,
    } for d in ddt])


@api.route("/autocomplete")
@login_required
def autocomplete():
    q = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "")
    if not q or len(q) < 2:
        return jsonify([])

    results = []

    if not tipo or tipo == "articolo":
        art = Giacenza.query.filter(
            db.or_(
                Giacenza.codice_articolo.ilike(f"%{q}%"),
                Giacenza.descrizione.ilike(f"%{q}%"),
            )
        ).order_by(Giacenza.codice_articolo).limit(100).all()
        seen = set()
        for a in art:
            if a.codice_articolo not in seen:
                seen.add(a.codice_articolo)
                results.append({
                    "value": a.codice_articolo,
                    "label": f"{a.codice_articolo} - {a.descrizione}",
                    "tipo": "articolo",
                })
                if len(results) >= 10:
                    break

    if not tipo or tipo == "cliente":
        clienti = db.session.query(DDT.cliente).filter(
            DDT.cliente.ilike(f"%{q}%")
        ).distinct().limit(5).all()
        for c in clienti:
            results.append({
                "value": c[0],
                "label": c[0],
                "tipo": "cliente",
            })

        fornitori = db.session.query(Bolla.fornitore).filter(
            Bolla.fornitore.ilike(f"%{q}%")
        ).distinct().limit(5).all()
        for f in fornitori:
            results.append({
                "value": f[0],
                "label": f"Fornitore: {f[0]}",
                "tipo": "fornitore",
            })

    return jsonify(results[:15])
