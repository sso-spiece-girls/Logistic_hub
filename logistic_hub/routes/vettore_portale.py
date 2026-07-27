from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from models import db, Vettore, ClienteVettore, User
from core.auth_decorators import vettore_required

vettore_portale = Blueprint("vettore_portale", __name__, url_prefix="/vettore")


@vettore_portale.route("/seleziona-cliente", methods=["GET", "POST"])
@login_required
@vettore_required
def seleziona_cliente():
    """Menù di selezione cliente attivo per vettori multi-cliente.

    Se il vettore ha un solo cliente, lo seleziona automaticamente.
    Se non ha Vettore collegato o clienti associati, mostra pagina statica
    'Account non configurato' — nessun logout forzato, solo messaggio.
    """
    vettore = Vettore.query.filter_by(user_id=current_user.id, attivo=True).first()
    if not vettore:
        return render_template(
            "vettore/account_non_configurato.html",
            messaggio="Il tuo account non è collegato a nessun vettore attivo. Contatta l'amministratore.",
        )

    associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
    if not associazioni:
        return render_template(
            "vettore/account_non_configurato.html",
            messaggio="Il tuo account vettore non ha ancora clienti associati. Contatta l'amministratore.",
        )

    clienti_ids = [cv.cliente_id for cv in associazioni]
    clienti = (
        User.query.filter(User.id.in_(clienti_ids), User.is_active == True)
        .order_by(User.username)
        .all()
    )
    if not clienti:
        return render_template(
            "vettore/account_non_configurato.html",
            messaggio="Nessun cliente attivo associato al tuo account. Contatta l'amministratore.",
        )

    # Auto-selezione: un solo cliente → salta la schermata
    if len(clienti) == 1:
        session["vettore_cliente_id"] = clienti[0].id
        session["vettore_cliente_nome"] = clienti[0].username
        flash(f"Stai prenotando per conto di: {clienti[0].username}", "info")
        return redirect(url_for("prenotazioni.calendario"))

    # Multi-cliente: mostra la schermata di selezione
    if request.method == "POST":
        cliente_id = request.form.get("cliente_id", type=int)
        if cliente_id and cliente_id in [c.id for c in clienti]:
            session["vettore_cliente_id"] = cliente_id
            session["vettore_cliente_nome"] = next(
                c.username for c in clienti if c.id == cliente_id
            )
            flash(
                f"Stai prenotando per conto di: {session['vettore_cliente_nome']}",
                "info",
            )
            return redirect(url_for("prenotazioni.calendario"))
        flash("Selezione non valida.", "error")

    return render_template("vettore/seleziona_cliente.html", clienti=clienti)


@vettore_portale.route("/cambia-cliente")
@login_required
@vettore_required
def cambia_cliente():
    """Resetta la selezione cliente attivo e riporta alla schermata di scelta."""
    session.pop("vettore_cliente_id", None)
    session.pop("vettore_cliente_nome", None)
    flash("Selezione cliente resettata.", "info")
    return redirect(url_for("vettore_portale.seleziona_cliente"))
