from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import Bolla, DDT, Giacenza, Picking, db

search = Blueprint("search", __name__)


@search.route("/search")
@login_required
def global_search():
    q = request.args.get("q", "").strip()
    if not q:
        return render_template("search.html", results=None, query="")

    # IDOR protection: clienti non possono cercare dati interni
    if current_user.role == "cliente":
        return render_template("search.html", results={"bolle": [], "ddt": [], "giacenze": [], "picking": []}, query=q)

    query = f"%{q}%"

    bolle = Bolla.query.filter(
        db.or_(
            Bolla.numero_bolla.ilike(query),
            Bolla.fornitore.ilike(query),
            Bolla.note.ilike(query),
        )
    ).limit(10).all()

    ddt = DDT.query.filter(
        db.or_(
            DDT.numero_ddt.ilike(query),
            DDT.cliente.ilike(query),
            DDT.destinatario.ilike(query),
        )
    ).limit(10).all()

    giacenze = Giacenza.query.filter(
        db.or_(
            Giacenza.codice_articolo.ilike(query),
            Giacenza.descrizione.ilike(query),
            Giacenza.ubicazione.ilike(query),
        )
    ).limit(10).all()

    picking = Picking.query.filter(
        db.or_(
            Picking.numero_picking.ilike(query),
            Picking.cliente.ilike(query),
        )
    ).limit(10).all()

    return render_template("search.html",
        query=q,
        bolle=bolle,
        ddt=ddt,
        giacenze=giacenze,
        picking=picking,
    )


@search.route("/api/search")
@login_required
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": []})

    # IDOR protection: clienti non possono cercare dati interni via API
    if current_user.role == "cliente":
        return jsonify({"results": []})

    query = f"%{q}%"

    bolle = Bolla.query.filter(Bolla.numero_bolla.ilike(query)).limit(5).all()
    ddt = DDT.query.filter(DDT.numero_ddt.ilike(query)).limit(5).all()
    giacenze = Giacenza.query.filter(
        db.or_(Giacenza.codice_articolo.ilike(query), Giacenza.descrizione.ilike(query))
    ).limit(5).all()

    results = []
    for b in bolle:
        results.append({"type": "Bolla", "id": b.id, "label": f"Bolla {b.numero_bolla} - {b.fornitore}", "url": f"/entrate/bolla/{b.id}"})
    for d in ddt:
        results.append({"type": "DDT", "id": d.id, "label": f"DDT {d.numero_ddt} - {d.cliente}", "url": f"/uscite/ddt/{d.id}"})
    for g in giacenze:
        results.append({"type": "Giacenza", "id": g.id, "label": f"{g.codice_articolo} - {g.descrizione}", "url": f"/giacenze/{g.id}"})

    return jsonify({"results": results})
