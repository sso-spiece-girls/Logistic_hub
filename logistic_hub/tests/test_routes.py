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


def test_overlap_tipologie_diverse_stesso_orario_ok(auth_client, db):
    """Stessa data, tipologia diversa, orari NON sovrapposti → entrambe passano.
    Nota: il DB ha UNIQUE(slot_orario_id, data, ora_inizio), quindi stesso orario
    è vietato anche con tipologie diverse. Usiamo orari diversi."""
    from models import Prenotazione
    cliente_id, slot_id, tip_id, tip2_id, data_futura = _setup_prenotazione_base(auth_client, db)

    resp1 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip_id, data_futura,
                                      targa="AA111BB", ora="08:00")
    assert resp1.status_code == 302

    resp2 = _crea_prenotazione_admin(auth_client, cliente_id, slot_id, tip2_id, data_futura,
                                      targa="CC222DD", ora="09:00")
    assert resp2.status_code == 302, f"Tipologia diversa orario diverso dovrebbe passare: {resp2.status_code}"

    with auth_client.application.app_context():
        count = Prenotazione.query.filter(
            Prenotazione.data == data_futura,
            Prenotazione.magazzino == "TestMag",
        ).count()
        assert count == 2, f"Devono esserci 2 prenotazioni (tipologie diverse), trovata {count}"


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
