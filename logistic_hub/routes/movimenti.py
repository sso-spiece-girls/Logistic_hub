from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from sqlalchemy.orm import load_only, joinedload
from models import Movimento, User, db

movimenti = Blueprint("movimenti", __name__, url_prefix="/movimenti")


@movimenti.route("/")
@login_required
def lista():
    tipo = request.args.get("tipo", "")
    articolo = request.args.get("articolo", "").strip()
    magazzino = request.args.get("magazzino", "").strip()
    data_da = request.args.get("data_da", "").strip()
    data_a = request.args.get("data_a", "").strip()

    page = request.args.get("page", 1, type=int)
    query = Movimento.query.options(
        joinedload(Movimento.user).load_only(User.username),
        load_only(
            Movimento.tipo, Movimento.articolo_codice, Movimento.descrizione,
            Movimento.colli, Movimento.pallet, Movimento.peso_kg,
            Movimento.riferimento_tipo, Movimento.riferimento_id,
            Movimento.created_at, Movimento.magazzino,
        ),
    ).order_by(Movimento.created_at.desc())

    if tipo:
        query = query.filter(Movimento.tipo == tipo)
    if articolo:
        query = query.filter(Movimento.articolo_codice.ilike(f"%{articolo}%"))
    if magazzino:
        query = query.filter(Movimento.magazzino == magazzino)

    pagination = query.paginate(page=page, per_page=100, error_out=False)
    return render_template("movimenti.html", pagination=pagination,
                           filtro_tipo=tipo, filtro_articolo=articolo,
                           filtro_magazzino=magazzino)


@movimenti.route("/api/ultimi")
@login_required
def ultimi():
    mov = Movimento.query.order_by(Movimento.created_at.desc()).limit(20).all()
    return jsonify([{
        "id": m.id,
        "tipo": m.tipo,
        "articolo_codice": m.articolo_codice,
        "descrizione": m.descrizione,
        "colli": m.colli,
        "pallet": m.pallet,
        "peso_kg": m.peso_kg,
        "riferimento_tipo": m.riferimento_tipo,
        "riferimento_id": m.riferimento_id,
        "data": m.created_at.isoformat(),
    } for m in mov])