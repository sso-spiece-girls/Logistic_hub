def test_login_page(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_success(client, db):
    from models import User
    with client.application.app_context():
        u = User(username="test", email="t@t.local", role="operatore")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
    resp = client.post("/login", data={"username": "test", "password": "pass"})
    assert resp.status_code == 302


def test_login_fail(client, db):
    from models import User
    with client.application.app_context():
        u = User(username="test", email="t@t.local", role="operatore")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
    resp = client.post("/login", data={"username": "test", "password": "wrong"})
    assert resp.status_code == 200


def test_dashboard_redirects_when_not_logged_in(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 302


def test_dashboard_ok_when_logged_in(auth_client):
    resp = auth_client.get("/dashboard")
    assert resp.status_code == 200


def test_entrate_list(auth_client):
    resp = auth_client.get("/entrate/")
    assert resp.status_code == 200


def test_uscite_list(auth_client):
    resp = auth_client.get("/uscite/")
    assert resp.status_code == 200


def test_giacenze_list(auth_client):
    resp = auth_client.get("/giacenze/")
    assert resp.status_code == 200


def test_clienti_list(auth_client):
    resp = auth_client.get("/clienti/")
    assert resp.status_code == 200


# ─── Helper base ───────────────────────────────────────────────────────────
# _setup_prenotazione_base restituisce SOLO ID (int) + data_futura (date)
# così nessun oggetto detached viene passato fuori dal context.

def _setup_prenotazione_base(auth_client, db):
    """Crea i dati minimi: cliente, slot, magazzino, 2 tipologie.
    Restituisce (cliente_id, slot_id, tip_id, tip2_id, data_futura)."""
    from datetime import date, time, timedelta
    from models import User, SlotOrario, MagazzinoCapienza, TipologiaMateriale

    with auth_client.application.app_context():
        cliente = User(username="testcliente", email="c@c.local", role="cliente")
        cliente.set_password("pass")
        db.session.add(cliente)
        db.session.flush()

        oggi = date.today()
        giorno_slot = (oggi.weekday() + 3) % 7
        data_futura = oggi + timedelta(days=3)
        while data_futura.weekday() != giorno_slot or data_futura <= oggi:
            data_futura += timedelta(days=1)

        slot = SlotOrario(
            giorno_settimana=giorno_slot,
            ora_inizio=time(8, 0),
            ora_fine=time(13, 0),
            durata_minuti=60,
            capienza=10,
            attivo=True,
            creato_da_id=1,
        )
        db.session.add(slot)

        mag = MagazzinoCapienza(magazzino="TestMag", capienza_contemporanea=10, creato_da_id=1)
        db.session.add(mag)

        tip = TipologiaMateriale(cliente_id=cliente.id, nome="TestTipo", durata_minuti=60, attivo=True)
        db.session.add(tip)

        tip2 = TipologiaMateriale(cliente_id=cliente.id, nome="AltroTipo", durata_minuti=60, attivo=True)
        db.session.add(tip2)

        db.session.commit()
        # Ritorna SOLO valori scalar — nessun oggetto detached
        return cliente.id, slot.id, tip.id, tip2.id, data_futura


def _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                              targa="AB123CD", tipo="scarico", ora="08:00",
                              ingresso_diretto="n"):
    """Esegue POST a /prenotazioni/admin/nuova e restituisce la risposta."""
    resp = auth_client.post("/prenotazioni/admin/nuova", data={
        "cliente_id": cliente_id,
        "data_prenotazione": data_futura.isoformat(),
        "slot_orario_id": slot_id,
        "ora_inizio": ora,
        "tipo": tipo,
        "tipologia_materiale_id": tip_id,
        "magazzino": "TestMag",
        "targa": targa,
        "ddt_cmr": "DDT999",
        "vettore_id": "0",
        "ingresso_diretto": "y" if ingresso_diretto == "y" else "",
        "inserimento_retroattivo": "",
    })
    return resp


# ─── Feature 1 — Staff nuova prenotazione (bug choices) ────────────────────

def test_admin_nuova_prenotazione_post_ok(auth_client, db):
    """Verifica che il POST a /prenotazioni/admin/nuova non vada in 500
    per mancanza di choices su tipologia_materiale_id prima della validazione."""
    from models import Prenotazione

    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp = auth_client.post("/prenotazioni/admin/nuova", data={
        "cliente_id": cliente_id,
        "data_prenotazione": data_futura.isoformat(),
        "slot_orario_id": slot_id,
        "ora_inizio": "08:00",
        "tipo": "scarico",
        "tipologia_materiale_id": tip_id,
        "magazzino": "TestMag",
        "targa": "AB123CD",
        "ddt_cmr": "DDT123",
        "vettore_id": "0",
        "ingresso_diretto": "y",
        "inserimento_retroattivo": "",
    })
    assert resp.status_code == 302, (
        f"Expected 302, got {resp.status_code}. "
        f"Redirect location: {getattr(resp, 'location', 'N/A')}"
    )

    with auth_client.application.app_context():
        p = Prenotazione.query.filter_by(targa="AB123CD").first()
        assert p is not None, "Prenotazione non creata"
        assert p.cliente_id == cliente_id
        assert p.inserita_da_staff is True
        assert p.stato == "ingresso_registrato"


# ─── Feature 5 — Vincolo targa ─────────────────────────────────────────────

def test_targa_bloccata_stesso_giorno(auth_client, db):
    """Due prenotazioni 'scarico' stessa targa stesso giorno → la seconda fallisce."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="XX111YY", tipo="scarico")
    assert resp1.status_code == 302, f"Prima prenotazione fallita: {resp1.status_code}"

    resp2 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="XX111YY", tipo="scarico", ora="09:00")
    assert resp2.status_code == 200, "Targa duplicata avrebbe dovuto essere rifiutata"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter_by(targa="XX111YY").count()
        assert count == 1, f"Dev'esserci solo 1 prenotazione con targa XX111YY, trovata {count}"


def test_targa_trasferimento_esente(auth_client, db):
    """Due prenotazioni stessa targa stesso giorno,
    la seconda con tipo=trasferimento → deve passare."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="XX222ZZ", tipo="scarico")
    assert resp1.status_code == 302, f"Prima prenotazione fallita: {resp1.status_code}"

    resp2 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="XX222ZZ", tipo="trasferimento", ora="09:00")
    assert resp2.status_code == 302, f"Trasferimento con stessa targa fallito: {resp2.status_code}"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter_by(targa="XX222ZZ").count()
        assert count == 2, f"Devono esserci 2 prenotazioni con targa XX222ZZ, trovata {count}"


# ─── Feature 8 — Vincolo sovrapposizione ───────────────────────────────────

def test_overlap_stessa_tipologia_bloccato(auth_client, db):
    """Stesso cliente, magazzino, tipologia, giorno, orari sovrapposti → seconda fallisce."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="AA111BB", ora="08:00")
    assert resp1.status_code == 302

    resp2 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="CC222DD", ora="08:00")
    assert resp2.status_code == 200, "Overlap stessa tipologia avrebbe dovuto essere bloccato"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter(
            Prenotazione.tipologia_materiale_id == tip_id,
            Prenotazione.data == data_futura,
        ).count()
        assert count == 1, f"Dev'esserci solo 1 prenotazione per questa tipologia/giorno, trovata {count}"


def test_overlap_stessa_tipologia_orari_diversi_ok(auth_client, db):
    """Stessa tipologia ma orari NON sovrapposti → entrambe passano."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="AA111BB", ora="08:00")
    assert resp1.status_code == 302

    resp2 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="CC222DD", ora="09:00")
    assert resp2.status_code == 302, f"Orari non sovrapposti avrebbero dovuto passare: {resp2.status_code}"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter(
            Prenotazione.tipologia_materiale_id == tip_id,
            Prenotazione.data == data_futura,
        ).count()
        assert count == 2, f"Devono esserci 2 prenotazioni, trovata {count}"


# ── TEST RIPRISTINATO (punto 3): stesso orario, tipologia diversa ──────────
def test_overlap_tipologie_diverse_stesso_orario_ok(auth_client, db):
    """Stesso orario inizio, tipologia diversa → entrambe passano (il vecchio
    vincolo UNIQUE uq_slot_booking_attivo è stato rimosso)."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, tip2_id, data_futura = _setup_prenotazione_base(auth_client, db)

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="AA111BB", ora="08:00")
    assert resp1.status_code == 302

    resp2 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip2_id, data_futura,
                                      targa="CC222DD", ora="08:00")
    assert resp2.status_code == 302, f"Stesso orario, tipologia diversa dovrebbe passare: {resp2.status_code}"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter(
            Prenotazione.data == data_futura,
            Prenotazione.magazzino == "TestMag",
        ).count()
        assert count == 2, f"Devono esserci 2 prenotazioni (tipologie diverse), trovata {count}"


# ── TEST NUOVO (punto 4): due clienti diversi, stesso orario ──────────────
def test_overlap_clienti_diversi_stesso_orario_ok(auth_client, db):
    """Due clienti diversi, stesso magazzino, stesso orario → entrambe passano
    (limitate solo da capienza_contemporanea, qui 10)."""
    from models import User, TipologiaMateriale, Prenotazione
    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    # Crea un secondo cliente con una propria tipologia
    with auth_client.application.app_context():
        cliente2 = User(username="cliente2", email="c2@c2.local", role="cliente")
        cliente2.set_password("pass")
        db.session.add(cliente2)
        db.session.flush()
        tip_cliente2 = TipologiaMateriale(
            cliente_id=cliente2.id, nome="TipoCliente2", durata_minuti=60, attivo=True,
        )
        db.session.add(tip_cliente2)
        db.session.commit()
        cliente2_id = cliente2.id
        tip2_id = tip_cliente2.id

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="AA111BB", ora="08:00")
    assert resp1.status_code == 302

    resp2 = _crea_prenotazione_admin(auth_client, cliente2_id, slot_id, tip2_id, data_futura,
                                      targa="CC222DD", ora="08:00")
    assert resp2.status_code == 302, f"Secondo cliente stesso orario dovrebbe passare: {resp2.status_code}"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter(
            Prenotazione.data == data_futura,
            Prenotazione.magazzino == "TestMag",
        ).count()
        assert count == 2, f"Devono esserci 2 prenotazioni (clienti diversi), trovata {count}"


# ─── Feature 7 — Motivo rifiuto ────────────────────────────────────────────

def test_motivo_rifiuto_visibile_rifiuta(auth_client, db):
    """Crea prenotazione, rifiuta con motivo → p.motivo_rifiuto popolato."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                     targa="XX999XX", ora="08:00", ingresso_diretto="n")
    assert resp.status_code == 302

    with auth_client.application.app_context():
        p = Prenotazione.query.filter_by(targa="XX999XX").first()
        assert p is not None
        assert p.stato == "in_attesa"
        pren_id = p.id

    resp_rifiuta = auth_client.post(f"/prenotazioni/admin/{pren_id}/rifiuta", data={
        "motivo": "Giorno non disponibile",
    })
    assert resp_rifiuta.status_code == 302

    with auth_client.application.app_context():
        p = Prenotazione.query.get(pren_id)
        assert p.stato == "rifiutata"
        assert p.motivo_rifiuto == "Giorno non disponibile", (
            f"motivo_rifiuto atteso 'Giorno non disponibile', ottenuto '{p.motivo_rifiuto}'"
        )


def test_motivo_rifiuto_visibile_rifiuta_ingresso(auth_client, db):
    """Crea prenotazione approvata, rifiuta ingresso → p.motivo_rifiuto popolato."""
    from models import Prenotazione
    import secrets

    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    resp = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                     targa="YY888YY", ora="08:00", ingresso_diretto="n")
    assert resp.status_code == 302

    with auth_client.application.app_context():
        p = Prenotazione.query.filter_by(targa="YY888YY").first()
        assert p is not None
        assert p.stato == "in_attesa"
        p.stato = "confermata"
        p.token_qr = secrets.token_urlsafe(32)
        db.session.commit()
        token = p.token_qr
        pren_id = p.id

    resp_rifiuta = auth_client.post(f"/prenotazioni/verifica/{token}/rifiuta-ingresso", data={
        "motivo": "Documenti non conformi",
    })
    assert resp_rifiuta.status_code == 302

    with auth_client.application.app_context():
        p = Prenotazione.query.get(pren_id)
        assert p.stato == "ingresso_rifiutato"
        assert p.motivo_rifiuto == "Documenti non conformi", (
            f"motivo_rifiuto atteso 'Documenti non conformi', ottenuto '{p.motivo_rifiuto}'"
        )


# ─── Regressione: calendario admin mostra tutte le prenotazioni per tick ──
def test_admin_calendario_mostra_tutte_prenotazioni(auth_client, db):
    """Due prenotazioni (clienti diversi) stesso slot/giorno/orario → il calendario
    admin deve mostrarle ENTRAMBE, non solo la prima, e i tick non devono essere
    fusi in un blocco unico."""
    from models import User, TipologiaMateriale, Prenotazione

    cliente_id, slot_id, tip_id, _, data_futura = _setup_prenotazione_base(auth_client, db)

    # Secondo cliente con propria tipologia
    with auth_client.application.app_context():
        cliente2 = User(username="cal-cliente2", email="cal-c2@local", role="cliente")
        cliente2.set_password("pass")
        db.session.add(cliente2)
        db.session.flush()
        tip2 = TipologiaMateriale(cliente_id=cliente2.id, nome="TipoCal2", durata_minuti=60, attivo=True)
        db.session.add(tip2)
        db.session.commit()
        c2_id = cliente2.id
        t2_id = tip2.id

    # Due prenotazioni stesso slot/giorno/orario
    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="CAL111", ora="08:00")
    assert resp1.status_code == 302

    resp2 = _crea_prenotazione_admin(auth_client, c2_id, slot_id, t2_id, data_futura,
                                      targa="CAL222", ora="08:00")
    assert resp2.status_code == 302

    # Chiama il calendario admin
    resp_cal = auth_client.get("/prenotazioni/admin/calendario")
    assert resp_cal.status_code == 200

    # Verifica che entrambe le targhe compaiano nell'HTML
    # (se una delle due fosse nascosta, la sua targa o username non apparirebbe)
    assert "CAL111" in resp_cal.text, "Targa CAL111 non trovata nel calendario"
    assert "CAL222" in resp_cal.text, "Targa CAL222 non trovata nel calendario"
    assert "cal-cliente2" in resp_cal.text, "cliente2 non trovato nel calendario"

    # Verifica che NON ci sia un singolo blocco fuso che nasconde le prenotazioni:
    # ogni booking-item è un <div class="calendario-booking-item"> separato
    import re
    items = re.findall(r'<div class="calendario-booking-item">', resp_cal.text)
    assert len(items) >= 2, (
        f"Dovrebbero esserci almeno 2 booking-item distinti, trovati {len(items)}"
    )


# ─── VETTORE ────────────────────────────────────────────────────────────────

def test_vettore_on_delete_set_null(app, db):
    """ON DELETE SET NULL: eliminato l'User, il Vettore sopravvive con user_id=NULL."""
    from models import User, Vettore

    with app.app_context():
        u = User(username="vettore-del-test", email="v@del.local", role="vettore")
        u.set_password("pass")
        db.session.add(u)
        db.session.flush()
        uid = u.id

        v = Vettore(nome="Vettore Da Eliminare", user_id=uid)
        db.session.add(v)
        db.session.commit()
        vid = v.id

        # Elimina l'User — ON DELETE SET NULL deve scattare
        db.session.delete(u)
        db.session.commit()

        # Verifica: Vettore esiste ancora, user_id è NULL
        v_dopo = db.session.get(Vettore, vid)
        assert v_dopo is not None, "Il Vettore NON dovrebbe essere stato eliminato a cascata"
        assert v_dopo.nome == "Vettore Da Eliminare"
        assert v_dopo.user_id is None, "user_id dovrebbe essere NULL (SET NULL)"


def _crea_setup_vettore(db, clienti_count=1, con_vettore=True, vettore_attivo=True):
    """Helper: crea User(vettore), Vettore e N clienti associati.
    Restituisce (username_vettore, password, lista_id_clienti)."""
    from models import User, Vettore, ClienteVettore

    vu = User(username="vettore-test", role="vettore")
    vu.set_password("pass")
    db.session.add(vu)
    db.session.flush()
    vu_id = vu.id

    if con_vettore:
        v = Vettore(nome="Vettore Test SRL", user_id=vu_id, attivo=vettore_attivo)
        db.session.add(v)
        db.session.flush()
        v_id = v.id
    else:
        v_id = None

    clienti_ids = []
    for i in range(clienti_count):
        c = User(username=f"cliente-vettore-{i}", role="cliente")
        c.set_password("pass")
        db.session.add(c)
        db.session.flush()
        clienti_ids.append(c.id)
        if v_id is not None:
            db.session.add(ClienteVettore(cliente_id=c.id, vettore_id=v_id))

    db.session.commit()
    return ("vettore-test", "pass", clienti_ids)


def test_vettore_login_redirect(app, db):
    """Vettore loggato → redirect a /vettore/seleziona-cliente."""
    from models import User, Vettore
    client = app.test_client()

    with app.app_context():
        _crea_setup_vettore(db, clienti_count=1)

    resp = client.post(
        "/login",
        data={"username": "vettore-test", "password": "pass"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/vettore/seleziona-cliente" in resp.headers.get("Location", "")


def test_vettore_no_vettore_record(app, db):
    """User vettore senza Vettore collegato → 'Account non configurato'."""
    from models import User
    client = app.test_client()

    with app.app_context():
        # Crea solo User(vettore), nessun Vettore con user_id
        _crea_setup_vettore(db, con_vettore=False, clienti_count=0)

    resp = client.post(
        "/login",
        data={"username": "vettore-test", "password": "pass"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Account non configurato" in resp.text
    assert "contatta" in resp.text.lower()


def test_vettore_no_clienti(app, db):
    """Vettore con account ma nessun ClienteVettore → 'Account non configurato'."""
    client = app.test_client()

    with app.app_context():
        _crea_setup_vettore(db, clienti_count=0)

    resp = client.post(
        "/login",
        data={"username": "vettore-test", "password": "pass"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Account non configurato" in resp.text


def test_vettore_single_cliente_auto_select(app, db):
    """Un solo cliente associato → auto-selezione, redirect a calendario."""
    client = app.test_client()

    with app.app_context():
        _crea_setup_vettore(db, clienti_count=1)

    resp = client.post(
        "/login",
        data={"username": "vettore-test", "password": "pass"},
        follow_redirects=False,
    )

    # Prima redirect a seleziona-cliente (dopo login)
    assert resp.status_code == 302
    # Il seleziona-cliente dovrebbe auto-selezionare e redirect a calendario
    resp2 = client.get("/vettore/seleziona-cliente", follow_redirects=False)
    # Dopo l'auto-selezione, dovrebbe essere redirect a /prenotazioni/calendario
    if resp2.status_code == 302:
        assert "/prenotazioni/calendario" in resp2.headers.get("Location", "")

    # Verifica anche la sessione
    with client.session_transaction() as sess:
        assert sess.get("vettore_cliente_id") is not None
        assert sess.get("vettore_cliente_nome") is not None


def test_vettore_multi_cliente_shows_selection(app, db):
    """Più clienti → mostra schermata di selezione."""
    client = app.test_client()

    with app.app_context():
        _crea_setup_vettore(db, clienti_count=2)

    # Login
    client.post("/login", data={"username": "vettore-test", "password": "pass"})

    # GET seleziona-cliente → deve mostrare la pagina di selezione
    resp = client.get("/vettore/seleziona-cliente")
    assert resp.status_code == 200
    assert "cliente-vettore-0" in resp.text
    assert "cliente-vettore-1" in resp.text
    # Nessun messaggio di errore
    assert "Account non configurato" not in resp.text


def test_vettore_seleziona_cliente_post(app, db):
    """POST selezione cliente → sessione aggiornata."""
    client = app.test_client()

    with app.app_context():
        _crea_setup_vettore(db, clienti_count=2)

    # Login
    client.post("/login", data={"username": "vettore-test", "password": "pass"})

    # Recupera gli ID dei clienti dalla pagina di selezione
    resp = client.get("/vettore/seleziona-cliente")
    assert resp.status_code == 200

    # Trova il primo cliente_id nel form action
    import re
    match = re.search(r'name="cliente_id"\s+value="(\d+)"', resp.text)
    assert match, "Campo cliente_id hidden non trovato"
    primo_cliente_id = int(match.group(1))

    # POST selezione
    resp = client.post(
        "/vettore/seleziona-cliente",
        data={"cliente_id": primo_cliente_id},
        follow_redirects=False,
    )
    # Dopo selezione, redirect a calendario
    assert resp.status_code == 302
    assert "/prenotazioni/calendario" in resp.headers.get("Location", "")

    # Verifica sessione
    with client.session_transaction() as sess:
        assert sess.get("vettore_cliente_id") == primo_cliente_id
        assert sess.get("vettore_cliente_nome") is not None


def test_vettore_cambia_cliente_resets_session(app, db):
    """GET cambia-cliente → sessione resettata."""
    import re
    client = app.test_client()

    with app.app_context():
        _crea_setup_vettore(db, clienti_count=2)

    # Login e seleziona cliente
    client.post("/login", data={"username": "vettore-test", "password": "pass"})
    resp = client.get("/vettore/seleziona-cliente")
    match = re.search(r'name="cliente_id"\s+value="(\d+)"', resp.text)
    client.post(
        "/vettore/seleziona-cliente",
        data={"cliente_id": int(match.group(1))},
    )

    # Verifica sessione prima del reset
    with client.session_transaction() as sess:
        assert "vettore_cliente_id" in sess

    # Cambia cliente
    resp = client.get("/vettore/cambia-cliente", follow_redirects=False)
    assert resp.status_code == 302
    assert "/vettore/seleziona-cliente" in resp.headers.get("Location", "")

    # Verifica sessione dopo reset
    with client.session_transaction() as sess:
        assert "vettore_cliente_id" not in sess
        assert "vettore_cliente_nome" not in sess
