import io
import secrets
from datetime import datetime, timezone, date, timedelta, time
import zoneinfo
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_file, jsonify
from flask_login import login_required, current_user
from models import db, Prenotazione, SlotOrario, User, MagazzinoCapienza, TipologiaMateriale, ClienteMagazzino
from forms import PrenotazioneForm, SlotOrarioForm, PrenotazioneAdminForm, MagazzinoCapienzaForm, TipologiaMaterialeForm, PrenotazioneStaffForm
from routes.auth import log_activity, create_notification
from core.auth_decorators import operatore_required, admin_required
import qrcode

bp = Blueprint("prenotazioni", __name__, url_prefix="/prenotazioni")

GIORNI_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]


def _giorno_bloccato_dopo_14():
    """Restituisce la data del giorno che viene bloccato dopo le 14:00,
    oppure None se siamo prima delle 14:00.

    Dopo le 14:00 non si può prenotare per il giorno successivo.
    Se oggi è venerdì, il giorno successivo è lunedì (salta weekend).
    """
    ora_corrente = datetime.now(zoneinfo.ZoneInfo("Europe/Rome")).time()
    if ora_corrente < time(14, 0):
        return None
    oggi = date.today()
    if oggi.weekday() == 4:  # Venerdì → salta a lunedì
        return oggi + timedelta(days=3)
    return oggi + timedelta(days=1)


def _capienza_magazzini():
    """Restituisce capienza totale sommando tutti i magazzini configurati, o 999 se nessuno."""
    righe = MagazzinoCapienza.query.all()
    if not righe:
        return 999
    return sum(r.capienza_contemporanea for r in righe)


def _slot_disponibili(regola, giorno, capienza=None):
    """Restituisce lista di dict {ora_inizio, ora_fine, disponibile} per una regola in un dato giorno.

    Usa un passo minimo di 30 minuti per evitare micro-slot: se la regola ha
    durata_minuti < 30, si usa comunque 30 come granularità dei tick.
    NON consolida i tick — ogni slot rimane individuale così il cliente può
    selezionare un orario di inizio preciso.
    """
    if capienza is None:
        capienza = _capienza_magazzini()
    slots = []
    cur = datetime.combine(giorno, regola.ora_inizio)
    fine = datetime.combine(giorno, regola.ora_fine)
    # Minimo 60 minuti tra un tick e l'altro — evita griglia troppo fitta
    step = timedelta(minutes=max(regola.durata_minuti, 60))
    prenotazioni_giorno = Prenotazione.query.filter(
        Prenotazione.slot_orario_id == regola.id,
        Prenotazione.data == giorno,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
    ).all()
    while cur + step <= fine:
        oi = cur.time()
        of = (cur + step).time()
        # Conta quante prenotazioni si sovrappongono a questo tick.
        # Con durate variabili (tipologia), una prenotazione può occupare più tick.
        occupate = sum(1 for p in prenotazioni_giorno if p.ora_inizio < of and p.ora_fine > oi)
        slots.append({
            "slot_orario_id": regola.id,
            "ora_inizio": oi.strftime("%H:%M"),
            "ora_fine": of.strftime("%H:%M"),
            "disponibile": occupate < capienza,
        })
        cur += step
    return slots


def _consolida_slots(slots):
    """Unisce tick adiacenti con lo stesso stato disponibile/occupato in blocchi più grandi."""
    if not slots:
        return []
    result = []
    current = dict(slots[0])
    for s in slots[1:]:
        if s["disponibile"] == current["disponibile"]:
            current["ora_fine"] = s["ora_fine"]
        else:
            result.append(current)
            current = dict(s)
    result.append(current)
    return result


def _consolida_admin(slots):
    """Unisce tick adiacenti per la vista admin: stesso stato E (se occupato) stessa prenotazione.
    Due prenotazioni diverse non vengono mai unite insieme."""
    if not slots:
        return []
    result = []
    current = dict(slots[0])
    for s in slots[1:]:
        same_available = s["disponibile"] and current["disponibile"]
        same_booking = (not s["disponibile"] and not current["disponibile"]
                        and s.get("prenotazione") is current.get("prenotazione"))
        if same_available or same_booking:
            current["ora_fine"] = s["ora_fine"]
        else:
            result.append(current)
            current = dict(s)
    result.append(current)
    return result


def _notifica_operatori(titolo, messaggio):
    operatori = User.query.filter(User.role.in_(["admin", "operatore"])).all()
    for op in operatori:
        create_notification(op.id, titolo, messaggio)


def _genera_token():
    return secrets.token_urlsafe(32)


def _allinea_orario(regola, ora_inizio_str, durata_minuti=None):
    """Verifica che ora_inizio sia valida per la regola e restituisce (ora_inizio, ora_fine) o None.

    L'allineamento usa max(regola.durata_minuti, 60) come passo effettivo,
    coerente con _slot_disponibili()."""
    if durata_minuti is None:
        durata_minuti = regola.durata_minuti
    try:
        oi = datetime.strptime(ora_inizio_str, "%H:%M").time()
    except (ValueError, TypeError):
        return None
    inizio_regola = datetime.combine(date.min, regola.ora_inizio)
    fine_regola = datetime.combine(date.min, regola.ora_fine)
    slot_start = datetime.combine(date.min, oi)
    if slot_start < inizio_regola or slot_start >= fine_regola:
        return None
    delta = int((slot_start - inizio_regola).total_seconds() // 60)
    # Allinea al passo effettivo (minimo 60 min, coerente con _slot_disponibili)
    effective_step = max(regola.durata_minuti, 60)
    if delta % effective_step != 0:
        return None
    slot_end = slot_start + timedelta(minutes=durata_minuti)
    if slot_end > fine_regola:
        return None
    return oi, slot_end.time()


def _magazzini_per_cliente(cliente_id):
    """Restituisce la lista di magazzini visibili a un cliente.

    Se il cliente ha associazioni configurate, mostra solo quelle.
    Altrimenti mostra tutti i magazzini (fallback)."""
    associazioni = ClienteMagazzino.query.filter_by(cliente_id=cliente_id).all()
    if associazioni:
        return [cm.magazzino for cm in associazioni]
    # Fallback: tutti i magazzini configurati
    return [m.magazzino for m in MagazzinoCapienza.query.order_by(MagazzinoCapienza.magazzino).all()]


# ─── API ─────────────────────────────────────────────────────────────

@bp.route("/api/tipologie-per-cliente/<int:cliente_id>")
@login_required
@operatore_required
def api_tipologie_per_cliente(cliente_id):
    """Restituisce JSON con le tipologie attive per un cliente."""
    tipologie = TipologiaMateriale.query.filter_by(cliente_id=cliente_id, attivo=True).all()
    return jsonify([{"id": t.id, "nome": t.nome, "durata_minuti": t.durata_minuti} for t in tipologie])


# ─── CLIENTE ────────────────────────────────────────────────────────

@bp.route("/calendario")
@login_required
def calendario():
    if current_user.role != "cliente":
        flash("Accesso riservato ai clienti.", "error")
        return redirect(url_for("dashboard.index"))
    regole = SlotOrario.query.filter_by(attivo=True).all()
    oggi = date.today()
    giorno_bloccato = _giorno_bloccato_dopo_14()
    slots_per_giorno = {}
    for i in range(14):
        g = oggi + timedelta(days=i)
        chiavi = []
        for r in regole:
            if g.weekday() != r.giorno_settimana:
                continue
            for s in _slot_disponibili(r, g):
                # Determina se lo slot è effettivamente prenotabile:
                # - deve essere disponibile (capienza)
                # - non deve essere oggi o nel passato
                # - non deve essere il giorno bloccato (dopo le 14:00)
                prenotabile = s["disponibile"] and g > oggi
                if giorno_bloccato and g == giorno_bloccato:
                    prenotabile = False
                s["prenotabile"] = prenotabile
                chiavi.append(s)
        if chiavi:
            slots_per_giorno[g.isoformat()] = {
                "giorno": g,
                "giorno_nome": GIORNI_IT[g.weekday()],
                "slots": chiavi,
            }
    tipologie_attive = TipologiaMateriale.query.filter_by(cliente_id=current_user.id, attivo=True).all()
    form = PrenotazioneForm()
    form.tipologia_materiale_id.choices = [(t.id, f"{t.nome} ({t.durata_minuti} min)") for t in tipologie_attive]
    # Popola il dropdown magazzino — filtra per associazioni se presenti
    magazzini_cliente = _magazzini_per_cliente(current_user.id)
    if magazzini_cliente:
        form.magazzino.choices = [(m, m) for m in magazzini_cliente]
    else:
        form.magazzino.choices = [("", "Nessun magazzino configurato")]
    return render_template(
        "prenotazioni/calendario.html",
        slots_per_giorno=slots_per_giorno,
        form=form,
        tipologie_attive=tipologie_attive,
        oggi=oggi,
        giorno_bloccato=giorno_bloccato,
    )


@bp.route("/prenota", methods=["POST"])
@login_required
def prenota():
    if current_user.role != "cliente":
        flash("Accesso riservato ai clienti.", "error")
        return redirect(url_for("dashboard.index"))
    form = PrenotazioneForm()
    form.tipologia_materiale_id.choices = [(t.id, f"{t.nome} ({t.durata_minuti} min)") for t in TipologiaMateriale.query.filter_by(cliente_id=current_user.id, attivo=True).all()]
    magazzini_cliente = _magazzini_per_cliente(current_user.id)
    form.magazzino.choices = [(m, m) for m in magazzini_cliente] if magazzini_cliente else [("", "Nessun magazzino configurato")]
    if not form.validate_on_submit():
        flash("Errore nei dati inviati. Riprova.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    # Blocco prenotazioni: dopo le 14:00 ora di Roma non si può prenotare per il giorno successivo
    # (e se venerdì, il giorno successivo è lunedì)
    ora_corrente = datetime.now(zoneinfo.ZoneInfo("Europe/Rome"))
    oggi = date.today()
    data_prenot = form.data_prenotazione.data
    if not data_prenot:
        flash("Data non valida.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    if data_prenot <= oggi:
        flash("Puoi prenotare solo a partire da domani.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    giorno_bloccato = _giorno_bloccato_dopo_14()
    if giorno_bloccato and data_prenot == giorno_bloccato:
        flash("Sono passate le 14:00, non puoi più prenotare per questo giorno. Scegli un giorno successivo.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    regola = db.session.query(SlotOrario).filter(
        SlotOrario.id == form.slot_orario_id.data
    ).with_for_update().first()
    if not regola or not regola.attivo:
        flash("Regola non trovata o non attiva.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    if data_prenot.weekday() != regola.giorno_settimana:
        flash("Giorno non valido per questa regola.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    tipologia = db.session.get(TipologiaMateriale, form.tipologia_materiale_id.data) if form.tipologia_materiale_id.data else None
    if not tipologia or tipologia.cliente_id != current_user.id or not tipologia.attivo:
        flash("Tipologia materiale non valida.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    orari = _allinea_orario(regola, form.ora_inizio.data, tipologia.durata_minuti)
    if orari is None:
        flash("Orario non valido o non allineato agli slot disponibili.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    ora_inizio, ora_fine = orari
    stesso_orario = Prenotazione.query.filter(
        Prenotazione.slot_orario_id == regola.id,
        Prenotazione.data == data_prenot,
        Prenotazione.ora_inizio == ora_inizio,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
    ).count() > 0
    if stesso_orario:
        flash("Orario non disponibile: slot già occupato.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    occupate = Prenotazione.query.filter(
        Prenotazione.slot_orario_id == regola.id,
        Prenotazione.data == data_prenot,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
        Prenotazione.ora_inizio < ora_fine,
        Prenotazione.ora_fine > ora_inizio,
    ).count()
    # Controllo capienza per il magazzino scelto dal cliente
    magazzino_scelto = form.magazzino.data
    capienza_mag = 999
    if magazzino_scelto:
        mag = MagazzinoCapienza.query.filter_by(magazzino=magazzino_scelto).first()
        capienza_mag = mag.capienza_contemporanea if mag else 999
    if occupate >= capienza_mag:
        flash("Slot non più disponibile.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    tipo = form.tipo.data
    if tipo not in ("carico", "scarico"):
        flash("Tipo operazione non valido.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    p = Prenotazione(
        cliente_id=current_user.id,
        slot_orario_id=regola.id,
        data=data_prenot,
        ora_inizio=ora_inizio,
        ora_fine=ora_fine,
        tipo=tipo,
        tipologia_materiale_id=tipologia.id,
        magazzino=form.magazzino.data,
        targa=form.targa.data,
        ddt_cmr=form.ddt_cmr.data,
        stato="in_attesa",
    )
    db.session.add(p)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Errore durante la prenotazione. Riprova.", "error")
        return redirect(url_for("prenotazioni.calendario"))
    log_activity(
        current_user.id, "prenota_slot",
        f"{current_user.username} ha prenotato {tipo} per {data_prenot} {ora_inizio}-{ora_fine}",
        "prenotazione", p.id,
    )
    _notifica_operatori(
        "Nuova prenotazione",
        f"{current_user.username} ha richiesto un {tipo} per {data_prenot} {ora_inizio.strftime('%H:%M')}-{ora_fine.strftime('%H:%M')}",
    )
    flash("Richiesta di prenotazione inviata. In attesa di approvazione.", "success")
    return redirect(url_for("prenotazioni.mie"))


@bp.route("/mie")
@login_required
def mie():
    if current_user.role != "cliente":
        flash("Accesso riservato ai clienti.", "error")
        return redirect(url_for("dashboard.index"))
    prenotazioni = Prenotazione.query.options(
        db.joinedload(Prenotazione.tipologia_materiale),
    ).filter_by(cliente_id=current_user.id).order_by(
        Prenotazione.data.desc(), Prenotazione.ora_inizio.desc()
    ).all()
    return render_template("prenotazioni/mie_prenotazioni.html", prenotazioni=prenotazioni)


@bp.route("/qr/<token>")
@login_required
def qr_code(token):
    p = Prenotazione.query.filter_by(token_qr=token).first()
    if not p:
        abort(404)
    if current_user.role not in ("admin", "operatore") and p.cliente_id != current_user.id:
        flash("Accesso negato.", "error")
        return redirect(url_for("dashboard.index"))
    if p.stato not in ("confermata", "ingresso_registrato"):
        flash("QR code non disponibile per questa prenotazione.", "warning")
        return redirect(url_for("prenotazioni.mie"))
    img = qrcode.make(request.host_url.rstrip("/") + url_for("prenotazioni.verifica", token=token))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ─── ADMIN / OPERATORE ──────────────────────────────────────────────

@bp.route("/admin/calendario")
@login_required
@operatore_required
def admin_calendario():
    oggi = date.today()
    regole = SlotOrario.query.filter_by(attivo=True).all()
    prenotazioni = Prenotazione.query.options(
        db.joinedload(Prenotazione.cliente),
        db.joinedload(Prenotazione.tipologia_materiale),
    ).filter(
        Prenotazione.data >= oggi,
    ).order_by(Prenotazione.data, Prenotazione.ora_inizio).all()
    p_map = {}
    for p in prenotazioni:
        key = (p.slot_orario_id, p.data.isoformat())
        if key not in p_map:
            p_map[key] = []
        p_map[key].append(p)
    slots_per_giorno = {}
    for i in range(14):
        g = oggi + timedelta(days=i)
        chiavi = []
        for r in regole:
            if g.weekday() != r.giorno_settimana:
                continue
            for s in _slot_disponibili(r, g):
                oi = datetime.strptime(s["ora_inizio"], "%H:%M").time()
                of = datetime.strptime(s["ora_fine"], "%H:%M").time()
                key = (r.id, g.isoformat())
                prenotazione = None
                for bp in p_map.get(key, []):
                    if bp.ora_inizio < of and bp.ora_fine > oi:
                        prenotazione = bp
                        break
                chiavi.append({
                    **s,
                    "slot_orario_id": r.id,
                    "prenotazione": prenotazione,
                })
            # Consolidamento solo per vista admin: unisce tick adiacenti
            # con lo stesso stato e la stessa prenotazione
            chiavi = _consolida_admin(chiavi)
        if chiavi:
            slots_per_giorno[g.isoformat()] = {
                "giorno": g,
                "giorno_nome": GIORNI_IT[g.weekday()],
                "slots": chiavi,
            }
    return render_template("prenotazioni/admin_calendario.html", slots_per_giorno=slots_per_giorno)


@bp.route("/admin/nuova", methods=["GET", "POST"])
@login_required
@operatore_required
def admin_nuova_prenotazione():
    """Inserimento manuale di una prenotazione da parte di admin/operatore.
    Bypassa le regole di fascia oraria cliente ma NON i controlli di capienza/race condition."""
    form = PrenotazioneStaffForm()

    # Popola scelte dinamiche
    clienti = User.query.filter_by(role="cliente", is_active=True).order_by(User.username).all()
    form.cliente_id.choices = [(c.id, c.username) for c in clienti]

    regole_attive = SlotOrario.query.filter_by(attivo=True).order_by(SlotOrario.giorno_settimana, SlotOrario.ora_inizio).all()
    form.slot_orario_id.choices = [(r.id, f"{GIORNI_IT[r.giorno_settimana]} {r.ora_inizio.strftime('%H:%M')}-{r.ora_fine.strftime('%H:%M')}") for r in regole_attive]

    # Popola magazzini (TUTTI, nessun filtro cliente)
    magazzini = MagazzinoCapienza.query.order_by(MagazzinoCapienza.magazzino).all()
    form.magazzino.choices = [(m.magazzino, m.magazzino) for m in magazzini]
    if not magazzini:
        form.magazzino.choices = [("", "Nessun magazzino configurato")]

    # Popola tipologia choices PRIMA di validate_on_submit (su POST il cliente_id è già bindato)
    if form.cliente_id.data:
        tipologie_cliente = TipologiaMateriale.query.filter_by(
            cliente_id=form.cliente_id.data, attivo=True
        ).all()
        form.tipologia_materiale_id.choices = [
            (t.id, f"{t.nome} ({t.durata_minuti} min)") for t in tipologie_cliente
        ]
    else:
        form.tipologia_materiale_id.choices = []

    if form.validate_on_submit():
        cliente = db.session.get(User, form.cliente_id.data)
        if not cliente or cliente.role != "cliente":
            flash("Cliente non valido.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        data_prenot = form.data_prenotazione.data
        if not data_prenot:
            flash("Data non valida.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        # Controllo date passate: permesse solo con flag retroattivo
        oggi = date.today()
        if data_prenot < oggi and not form.inserimento_retroattivo.data:
            flash("Non puoi inserire prenotazioni nel passato senza spuntare 'Inserimento retroattivo'.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        # Lock della regola per race condition
        regola = db.session.query(SlotOrario).filter(
            SlotOrario.id == form.slot_orario_id.data
        ).with_for_update().first()
        if not regola or not regola.attivo:
            flash("Regola non trovata o non attiva.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        if data_prenot.weekday() != regola.giorno_settimana:
            flash("Giorno non valido per questa regola.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        # Calcola durata effettiva
        tipologia = db.session.get(TipologiaMateriale, form.tipologia_materiale_id.data) if form.tipologia_materiale_id.data else None
        if not tipologia or not tipologia.attivo:
            flash("Tipologia materiale non valida.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)
        if tipologia.cliente_id != cliente.id:
            flash("Tipologia non appartenente al cliente selezionato.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        durata = tipologia.durata_minuti

        # Allinea orario
        orari = _allinea_orario(regola, form.ora_inizio.data, durata)
        if orari is None:
            flash("Orario non valido o non allineato agli slot disponibili.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)
        ora_inizio, ora_fine = orari

        # Controllo capienza per il magazzino scelto
        magazzino_scelto = form.magazzino.data
        capienza_mag = 999
        if magazzino_scelto:
            mag = db.session.query(MagazzinoCapienza).filter(
                MagazzinoCapienza.magazzino == magazzino_scelto
            ).with_for_update().first()
            capienza_mag = mag.capienza_contemporanea if mag else 999

        # Controllo sovrapposizione oraria (stessa logica usata in approva)
        occupate = Prenotazione.query.filter(
            Prenotazione.slot_orario_id == regola.id,
            Prenotazione.data == data_prenot,
            Prenotazione.stato.in_(["in_attesa", "confermata", "ingresso_registrato"]),
            Prenotazione.ora_inizio < ora_fine,
            Prenotazione.ora_fine > ora_inizio,
        ).count()

        if occupate >= capienza_mag:
            flash("Slot non disponibile: capienza esaurita.", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        # Crea la prenotazione
        stato_finale = "ingresso_registrato" if form.ingresso_diretto.data else "in_attesa"

        p = Prenotazione(
            cliente_id=cliente.id,
            slot_orario_id=regola.id,
            data=data_prenot,
            ora_inizio=ora_inizio,
            ora_fine=ora_fine,
            tipo=form.tipo.data,
            tipologia_materiale_id=tipologia.id,
            magazzino=magazzino_scelto,
            targa=form.targa.data,
            ddt_cmr=form.ddt_cmr.data,
            stato=stato_finale,
            inserita_da_staff=True,
            staff_user_id=current_user.id,
        )

        if stato_finale == "ingresso_registrato":
            p.token_qr = _genera_token()
            p.ingresso_verificato_da_id = current_user.id
            p.ingresso_verificato_at = datetime.now(timezone.utc)

        db.session.add(p)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la creazione della prenotazione: {str(e)}", "error")
            return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)

        log_activity(
            current_user.id, "prenota_staff",
            f"{current_user.username} ha creato una prenotazione staff per {cliente.username} {form.tipo.data} {data_prenot} {ora_inizio}-{ora_fine}",
            "prenotazione", p.id,
        )

        # Notifica al cliente
        create_notification(
            cliente.id,
            "Prenotazione creata dallo staff",
            f"{'Ingresso registrato' if stato_finale == 'ingresso_registrato' else 'Richiesta di prenotazione'} per {form.tipo.data} del {data_prenot} alle {ora_inizio.strftime('%H:%M')}. Magazzino: {magazzino_scelto}.",
        )

        _notifica_operatori(
            "Nuova prenotazione staff",
            f"{current_user.username} ha creato una prenotazione per {cliente.username} ({form.tipo.data} {data_prenot} {ora_inizio.strftime('%H:%M')})",
        )

        flash(f"Prenotazione creata con successo per {cliente.username}.", "success")
        return redirect(url_for("prenotazioni.admin_calendario"))

    return render_template("prenotazioni/admin_nuova_prenotazione.html", form=form)


@bp.route("/admin/in-attesa")
@login_required
@operatore_required
def in_attesa():
    richieste = Prenotazione.query.options(
        db.joinedload(Prenotazione.cliente),
        db.joinedload(Prenotazione.tipologia_materiale),
    ).filter_by(stato="in_attesa").order_by(
        Prenotazione.data, Prenotazione.ora_inizio
    ).all()
    return render_template("prenotazioni/admin_in_attesa.html", richieste=richieste, form=PrenotazioneAdminForm())


@bp.route("/admin/<int:id>/approva", methods=["POST"])
@login_required
@operatore_required
def approva(id):
    p = Prenotazione.query.get_or_404(id)
    if p.stato != "in_attesa":
        flash("Questa prenotazione non è in attesa di approvazione.", "warning")
        return redirect(url_for("prenotazioni.in_attesa"))
    form = PrenotazioneAdminForm()
    if not form.validate_on_submit():
        flash("Errore nei dati inviati.", "error")
        return redirect(url_for("prenotazioni.in_attesa"))
    # Lock della regola per race condition
    regola = db.session.query(SlotOrario).filter(SlotOrario.id == p.slot_orario_id).with_for_update().first()
    if not regola:
        flash("Regola non trovata.", "error")
        return redirect(url_for("prenotazioni.in_attesa"))
    # Controllo capienza usando il magazzino già scelto dal cliente
    capienza_mag = 999
    if p.magazzino:
        mag = db.session.query(MagazzinoCapienza).filter(
            MagazzinoCapienza.magazzino == p.magazzino
        ).with_for_update().first()
        if mag:
            capienza_mag = mag.capienza_contemporanea
            occupati = Prenotazione.query.filter(
                Prenotazione.magazzino == p.magazzino,
                Prenotazione.data == p.data,
                Prenotazione.ora_inizio < p.ora_fine,
                Prenotazione.ora_fine > p.ora_inizio,
                Prenotazione.stato.in_(["confermata", "ingresso_registrato"]),
            ).count()
            if occupati >= mag.capienza_contemporanea:
                flash(f"Magazzino {p.magazzino} già pieno in questa fascia oraria.", "error")
                return redirect(url_for("prenotazioni.in_attesa"))
    occupate = Prenotazione.query.filter(
        Prenotazione.slot_orario_id == regola.id,
        Prenotazione.data == p.data,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
        Prenotazione.ora_inizio < p.ora_fine,
        Prenotazione.ora_fine > p.ora_inizio,
    ).count()
    if occupate > capienza_mag:
        p.stato = "rifiutata"
        p.note_operatore = "Slot non più disponibile al momento dell'approvazione."
        p.approvato_da_id = current_user.id
        p.approvato_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Prenotazione rifiutata: capienza esaurita nel frattempo.", "warning")
        return redirect(url_for("prenotazioni.in_attesa"))
    if form.magazzino.data:
        mag = db.session.query(MagazzinoCapienza).filter(
            MagazzinoCapienza.magazzino == form.magazzino.data
        ).with_for_update().first()
        if mag:
            occupati = Prenotazione.query.filter(
                Prenotazione.magazzino == form.magazzino.data,
                Prenotazione.data == p.data,
                Prenotazione.ora_inizio < p.ora_fine,
                Prenotazione.ora_fine > p.ora_inizio,
                Prenotazione.stato.in_(["confermata", "ingresso_registrato"]),
            ).count()
            if occupati >= mag.capienza_contemporanea:
                flash(f"Magazzino {form.magazzino.data} già pieno in questa fascia oraria.", "error")
                return redirect(url_for("prenotazioni.in_attesa"))
    p.stato = "confermata"
    if form.magazzino.data:
        p.magazzino = form.magazzino.data
    p.token_qr = _genera_token()
    p.approvato_da_id = current_user.id
    p.approvato_at = datetime.now(timezone.utc)
    db.session.commit()
    create_notification(
        p.cliente_id,
        "Prenotazione confermata",
        f"{p.tipo.capitalize()} del {p.data} alle {p.ora_inizio.strftime('%H:%M')} confermato. Magazzino: {p.magazzino}. QR code disponibile.",
    )
    log_activity(
        current_user.id, "approva_prenotazione",
        f"{current_user.username} ha approvato {p.tipo} prenotazione {p.id} su {p.magazzino}",
        "prenotazione", p.id,
    )
    flash("Prenotazione approvata con successo.", "success")
    return redirect(url_for("prenotazioni.in_attesa"))


@bp.route("/admin/<int:id>/rifiuta", methods=["POST"])
@login_required
@operatore_required
def rifiuta(id):
    p = Prenotazione.query.get_or_404(id)
    if p.stato != "in_attesa":
        flash("Questa prenotazione non è in attesa.", "warning")
        return redirect(url_for("prenotazioni.in_attesa"))
    form = PrenotazioneAdminForm()
    if form.validate_on_submit():
        p.stato = "rifiutata"
        p.note_operatore = form.motivo.data or None
        p.approvato_da_id = current_user.id
        p.approvato_at = datetime.now(timezone.utc)
        db.session.commit()
        motivo = f" Motivo: {form.motivo.data}" if form.motivo.data else ""
        create_notification(
            p.cliente_id,
            "Prenotazione rifiutata",
            f"La tua prenotazione del {p.data} alle {p.ora_inizio.strftime('%H:%M')} è stata rifiutata.{motivo}",
        )
        log_activity(
            current_user.id, "rifiuta_prenotazione",
            f"{current_user.username} ha rifiutato la prenotazione {p.id}",
            "prenotazione", p.id,
        )
        flash("Prenotazione rifiutata.", "success")
    return redirect(url_for("prenotazioni.in_attesa"))


# ─── ADMIN SOLO GESTIONE SLOT ──────────────────────────────────────

@bp.route("/admin/slot")
@login_required
@admin_required
def admin_slot():
    regole = SlotOrario.query.order_by(SlotOrario.giorno_settimana, SlotOrario.ora_inizio).all()
    return render_template("prenotazioni/admin_slot.html", regole=regole, giorni=GIORNI_IT)


@bp.route("/admin/slot/nuovo", methods=["GET", "POST"])
@login_required
@admin_required
def admin_slot_nuovo():
    form = SlotOrarioForm()
    if form.validate_on_submit():
        try:
            oi = datetime.strptime(form.ora_inizio.data or "", "%H:%M").time()
            of = datetime.strptime(form.ora_fine.data or "", "%H:%M").time()
        except (ValueError, TypeError):
            flash("Formato ora non valido (usa HH:MM).", "error")
            return render_template("prenotazioni/admin_slot_form.html", form=form, titolo="Nuova regola")
        if of <= oi:
            flash("L'ora di fine deve essere successiva all'ora di inizio.", "error")
            return render_template("prenotazioni/admin_slot_form.html", form=form, titolo="Nuova regola")
        regola = SlotOrario(
            giorno_settimana=int(form.giorno_settimana.data),
            ora_inizio=oi,
            ora_fine=of,
            durata_minuti=form.durata_minuti.data,
            capienza=form.capienza.data,
            attivo=form.attivo.data,
            creato_da_id=current_user.id,
        )
        db.session.add(regola)
        db.session.commit()
        log_activity(
            current_user.id, "crea_slot_orario",
            f"{current_user.username} ha creato una regola slot per {GIORNI_IT[regola.giorno_settimana]} {oi.strftime('%H:%M')}-{of.strftime('%H:%M')}",
            "slot_orario", regola.id,
        )
        flash("Regola slot creata con successo.", "success")
        return redirect(url_for("prenotazioni.admin_slot"))
    return render_template("prenotazioni/admin_slot_form.html", form=form, titolo="Nuova regola")


@bp.route("/admin/slot/<int:id>/modifica", methods=["GET", "POST"])
@login_required
@admin_required
def admin_slot_modifica(id):
    regola = SlotOrario.query.get_or_404(id)
    form = SlotOrarioForm(obj=regola)
    form.giorno_settimana.data = str(regola.giorno_settimana)
    form.ora_inizio.data = regola.ora_inizio.strftime("%H:%M")
    form.ora_fine.data = regola.ora_fine.strftime("%H:%M")
    if form.validate_on_submit():
        try:
            oi = datetime.strptime(form.ora_inizio.data or "", "%H:%M").time()
            of = datetime.strptime(form.ora_fine.data or "", "%H:%M").time()
        except (ValueError, TypeError):
            flash("Formato ora non valido (usa HH:MM).", "error")
            return render_template("prenotazioni/admin_slot_form.html", form=form, titolo="Modifica regola")
        if of <= oi:
            flash("L'ora di fine deve essere successiva all'ora di inizio.", "error")
            return render_template("prenotazioni/admin_slot_form.html", form=form, titolo="Modifica regola")
        regola.giorno_settimana = int(form.giorno_settimana.data)
        regola.ora_inizio = oi
        regola.ora_fine = of
        regola.durata_minuti = form.durata_minuti.data
        regola.capienza = form.capienza.data
        regola.attivo = form.attivo.data
        db.session.commit()
        log_activity(
            current_user.id, "modifica_slot_orario",
            f"{current_user.username} ha modificato la regola slot {regola.id}",
            "slot_orario", regola.id,
        )
        flash("Regola slot aggiornata.", "success")
        return redirect(url_for("prenotazioni.admin_slot"))
    return render_template("prenotazioni/admin_slot_form.html", form=form, titolo="Modifica regola")


@bp.route("/admin/slot/<int:id>/elimina", methods=["POST"])
@login_required
@admin_required
def admin_slot_elimina(id):
    regola = SlotOrario.query.get_or_404(id)
    attive = Prenotazione.query.filter(
        Prenotazione.slot_orario_id == regola.id,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
    ).count()
    if attive > 0:
        flash(f"Impossibile eliminare: ci sono {attive} prenotazioni attive su questa regola. Disattivala invece.", "error")
        return redirect(url_for("prenotazioni.admin_slot"))
    db.session.delete(regola)
    db.session.commit()
    log_activity(
        current_user.id, "elimina_slot_orario",
        f"{current_user.username} ha eliminato la regola slot {regola.id}",
        "slot_orario", regola.id,
    )
    flash("Regola slot eliminata.", "success")
    return redirect(url_for("prenotazioni.admin_slot"))


# ─── ADMIN MAGAZZINI ────────────────────────────────────────────────

@bp.route("/admin/magazzini")
@login_required
@admin_required
def admin_magazzini():
    magazzini = MagazzinoCapienza.query.order_by(MagazzinoCapienza.magazzino).all()
    return render_template("prenotazioni/admin_magazzini.html", magazzini=magazzini)


@bp.route("/admin/magazzini/nuovo", methods=["GET", "POST"])
@login_required
@admin_required
def admin_magazzini_nuovo():
    form = MagazzinoCapienzaForm()
    if form.validate_on_submit():
        esistente = MagazzinoCapienza.query.filter_by(magazzino=form.magazzino.data).first()
        if esistente:
            flash("Magazzino già configurato.", "error")
            return render_template("prenotazioni/admin_magazzini_form.html", form=form, titolo="Nuova capienza magazzino")
        mag = MagazzinoCapienza(
            magazzino=form.magazzino.data,
            capienza_contemporanea=form.capienza_contemporanea.data,
            creato_da_id=current_user.id,
        )
        db.session.add(mag)
        db.session.commit()
        log_activity(
            current_user.id, "crea_capienza_magazzino",
            f"{current_user.username} ha configurato capienza per {mag.magazzino} ({mag.capienza_contemporanea})",
            "magazzino_capienza", mag.id,
        )
        flash("Capienza magazzino configurata.", "success")
        return redirect(url_for("prenotazioni.admin_magazzini"))
    return render_template("prenotazioni/admin_magazzini_form.html", form=form, titolo="Nuova capienza magazzino")


@bp.route("/admin/magazzini/<int:id>/modifica", methods=["GET", "POST"])
@login_required
@admin_required
def admin_magazzini_modifica(id):
    mag = MagazzinoCapienza.query.get_or_404(id)
    form = MagazzinoCapienzaForm(obj=mag)
    if form.validate_on_submit():
        conflitto = MagazzinoCapienza.query.filter(
            MagazzinoCapienza.magazzino == form.magazzino.data,
            MagazzinoCapienza.id != id,
        ).first()
        if conflitto:
            flash("Un altro magazzino ha già questo nome.", "error")
            return render_template("prenotazioni/admin_magazzini_form.html", form=form, titolo="Modifica capienza magazzino")
        mag.magazzino = form.magazzino.data
        mag.capienza_contemporanea = form.capienza_contemporanea.data
        db.session.commit()
        log_activity(
            current_user.id, "modifica_capienza_magazzino",
            f"{current_user.username} ha modificato capienza per {mag.magazzino}",
            "magazzino_capienza", mag.id,
        )
        flash("Capienza magazzino aggiornata.", "success")
        return redirect(url_for("prenotazioni.admin_magazzini"))
    return render_template("prenotazioni/admin_magazzini_form.html", form=form, titolo="Modifica capienza magazzino")


@bp.route("/admin/magazzini/<int:id>/elimina", methods=["POST"])
@login_required
@admin_required
def admin_magazzini_elimina(id):
    mag = MagazzinoCapienza.query.get_or_404(id)
    attive = Prenotazione.query.filter(
        Prenotazione.magazzino == mag.magazzino,
        Prenotazione.stato.in_(["in_attesa", "confermata"]),
    ).count()
    if attive > 0:
        flash(f"Impossibile eliminare: ci sono {attive} prenotazioni attive su {mag.magazzino}.", "error")
        return redirect(url_for("prenotazioni.admin_magazzini"))
    db.session.delete(mag)
    db.session.commit()
    log_activity(
        current_user.id, "elimina_capienza_magazzino",
        f"{current_user.username} ha eliminato capienza per {mag.magazzino}",
        "magazzino_capienza", mag.id,
    )
    flash("Configurazione capienza eliminata.", "success")
    return redirect(url_for("prenotazioni.admin_magazzini"))


# ─── VERIFICA QR ────────────────────────────────────────────────────

@bp.route("/verifica/<token>")
@login_required
@operatore_required
def verifica(token):
    p = Prenotazione.query.options(
        db.joinedload(Prenotazione.cliente),
        db.joinedload(Prenotazione.tipologia_materiale),
        db.joinedload(Prenotazione.ingresso_verificato_da),
    ).filter_by(token_qr=token).first()
    if not p:
        flash("QR code non valido.", "error")
        return render_template("prenotazioni/verifica.html", prenotazione=None)
    return render_template("prenotazioni/verifica.html", prenotazione=p, form=PrenotazioneAdminForm())


@bp.route("/verifica/<token>/conferma-ingresso", methods=["POST"])
@login_required
@operatore_required
def conferma_ingresso(token):
    p = Prenotazione.query.filter_by(token_qr=token).first()
    if not p:
        flash("QR code non valido.", "error")
        return redirect(url_for("prenotazioni.verifica", token=token))
    if p.stato not in ("confermata",):
        flash("La prenotazione non è in stato confermata.", "warning")
        return redirect(url_for("prenotazioni.verifica", token=token))
    p.stato = "ingresso_registrato"
    p.ingresso_verificato_da_id = current_user.id
    p.ingresso_verificato_at = datetime.now(timezone.utc)
    db.session.commit()
    create_notification(
        p.cliente_id,
        f"{p.tipo.capitalize()} accettato",
        f"Il {p.tipo} del {p.data} alle {p.ora_inizio.strftime('%H:%M')} è stato accettato.",
    )
    log_activity(
        current_user.id, "conferma_ingresso",
        f"{current_user.username} ha confermato l'ingresso per la prenotazione {p.id}",
        "prenotazione", p.id,
    )
    flash("Ingresso registrato con successo.", "success")
    return redirect(url_for("prenotazioni.verifica", token=token))


@bp.route("/verifica/<token>/rifiuta-ingresso", methods=["POST"])
@login_required
@operatore_required
def rifiuta_ingresso(token):
    p = Prenotazione.query.filter_by(token_qr=token).first()
    if not p:
        flash("QR code non valido.", "error")
        return redirect(url_for("prenotazioni.verifica", token=token))
    if p.stato not in ("confermata",):
        flash("La prenotazione non è in stato confermata.", "warning")
        return redirect(url_for("prenotazioni.verifica", token=token))
    form = PrenotazioneAdminForm()
    if form.validate_on_submit():
        p.stato = "ingresso_rifiutato"
        p.note_operatore = form.motivo.data or "Nessun motivo specificato"
        p.ingresso_verificato_da_id = current_user.id
        p.ingresso_verificato_at = datetime.now(timezone.utc)
        db.session.commit()
        log_activity(
            current_user.id, "rifiuta_ingresso",
            f"{current_user.username} ha rifiutato l'ingresso per la prenotazione {p.id}: {p.note_operatore}",
            "prenotazione", p.id,
        )
        flash("Ingresso rifiutato.", "success")
    return redirect(url_for("prenotazioni.verifica", token=token))
