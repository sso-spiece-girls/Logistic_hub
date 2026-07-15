from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import Giacenza, Movimento, db
from forms import GiacenzaForm
from routes.auth import log_activity, create_notification
from core.auth_decorators import staff_required
from core.normalize import normalizza_codice_articolo

giacenze = Blueprint("giacenze", __name__, url_prefix="/giacenze")


@giacenze.route("/")
@login_required
def lista():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    search = request.args.get("q", "").strip()
    filtro_magazzino = request.args.get("magazzino", "").strip()
    gruppi = request.args.get("gruppi") == "1"
    query = Giacenza.query.order_by(Giacenza.codice_articolo)

    if search:
        query = query.filter(
            db.or_(
                Giacenza.codice_articolo.ilike(f"%{search}%"),
                Giacenza.descrizione.ilike(f"%{search}%"),
                Giacenza.ubicazione.ilike(f"%{search}%"),
                Giacenza.id_bobina.ilike(f"%{search}%"),
                Giacenza.provenienza.ilike(f"%{search}%"),
            )
        )
    if filtro_magazzino:
        query = query.filter(Giacenza.magazzino == filtro_magazzino)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    giacenze = pagination.items
    return render_template("giacenze.html", giacenze=giacenze, pagination=pagination, search=search, filtro_magazzino=filtro_magazzino, gruppi=gruppi)


@giacenze.route("/nuovo", methods=["GET", "POST"])
@login_required
def nuovo():
    form = GiacenzaForm()
    if form.validate_on_submit():
        codice = normalizza_codice_articolo(form.codice_articolo.data)
        esistente = Giacenza.query.filter_by(codice_articolo=codice).first()
        if esistente:
            flash(f"Codice articolo '{codice}' già esistente (ID {esistente.id}).", "warning")
            return redirect(url_for("giacenze.dettaglio", id=esistente.id))
        giacenza = Giacenza(
            codice_articolo=codice,
            descrizione=form.descrizione.data,
            quantita=form.quantita.data or 0,
            colli=form.colli.data or 0,
            pallet=form.pallet.data or 0,
            peso_kg=form.peso_kg.data or 0.0,
            id_bobina=form.id_bobina.data or None,
            qualita=form.qualita.data or None,
            provenienza=form.provenienza.data or None,
            ubicazione=form.ubicazione.data or None,
            magazzino=form.magazzino.data or None,
            updated_by=current_user.id,
        )
        db.session.add(giacenza)
        db.session.commit()
        log_activity(current_user.id, "crea_giacenza",
            f"{current_user.username} ha creato la giacenza {giacenza.codice_articolo}",
            "giacenza", giacenza.id)
        flash("Giacenza creata con successo.", "success")
        return redirect(url_for("giacenze.lista"))
    return render_template("giacenze_form.html", form=form, titolo="Nuova Giacenza", giacenza=None)


@giacenze.route("/<int:id>")
@login_required
def dettaglio(id):
    giacenza = Giacenza.query.get_or_404(id)
    return render_template("giacenze_dettaglio.html", giacenza=giacenza)


@giacenze.route("/<int:id>/modifica", methods=["GET", "POST"])
@login_required
def modifica(id):
    giacenza = Giacenza.query.get_or_404(id)
    form = GiacenzaForm(obj=giacenza)
    if form.validate_on_submit():
        vecchi_colli = giacenza.colli or 0
        vecchio_peso = giacenza.peso_kg or 0.0
        vecchio_codice = giacenza.codice_articolo

        form.populate_obj(giacenza)
        giacenza.codice_articolo = normalizza_codice_articolo(form.codice_articolo.data)
        giacenza.updated_by = current_user.id
        db.session.commit()

        # Registra movimento per la rettifica
        nuovi_colli = giacenza.colli or 0
        nuovo_peso = giacenza.peso_kg or 0.0
        if vecchi_colli != nuovi_colli or vecchio_peso != nuovo_peso:
            mov = Movimento(
                tipo="rettifica",
                articolo_codice=giacenza.codice_articolo,
                descrizione=giacenza.descrizione,
                colli=nuovi_colli - vecchi_colli,
                peso_kg=nuovo_peso - vecchio_peso,
                ubicazione=giacenza.ubicazione,
                magazzino=giacenza.magazzino,
                riferimento_tipo="giacenza",
                riferimento_id=giacenza.id,
                user_id=current_user.id,
                note=f"Rettifica manuale giacenza {giacenza.codice_articolo}",
            )
            db.session.add(mov)
            db.session.commit()

        log_activity(current_user.id, "modifica_giacenza",
            f"{current_user.username} ha modificato la giacenza {giacenza.codice_articolo}",
            "giacenza", giacenza.id)
        flash("Giacenza aggiornata con successo.", "success")
        return redirect(url_for("giacenze.lista"))
    return render_template("giacenze_form.html", form=form, titolo="Modifica Giacenza", giacenza=giacenza)


@giacenze.route("/<int:id>/elimina", methods=["POST"])
@login_required
@staff_required
def elimina(id):
    giacenza = Giacenza.query.get_or_404(id)
    db.session.delete(giacenza)
    db.session.commit()
    log_activity(current_user.id, "elimina_giacenza",
        f"{current_user.username} ha eliminato la giacenza {giacenza.codice_articolo}",
        "giacenza", id)
    flash("Giacenza eliminata.", "success")
    return redirect(url_for("giacenze.lista"))


@giacenze.route("/api/check-duplicato")
@login_required
def check_duplicato():
    """API AJAX: verifica se un codice articolo esiste gia'."""
    codice = request.args.get("codice", "").strip()
    if not codice:
        return jsonify({"esiste": False})
    esistente = Giacenza.query.filter_by(codice_articolo=codice).first()
    if esistente:
        return jsonify({
            "esiste": True,
            "id": esistente.id,
            "codice_articolo": esistente.codice_articolo,
            "descrizione": esistente.descrizione,
            "quantita": esistente.quantita,
            "colli": esistente.colli,
            "pallet": esistente.pallet,
        })
    return jsonify({"esiste": False})