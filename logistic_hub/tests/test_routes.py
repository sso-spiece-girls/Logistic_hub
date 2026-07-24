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


def test_admin_nuova_prenotazione_post_ok(auth_client, db):
    """Verifica che il POST a /prenotazioni/admin/nuova non vada in 500
    per mancanza di choices su tipologia_materiale_id prima della validazione."""
    from datetime import date, time, timedelta
    from models import User, SlotOrario, MagazzinoCapienza, TipologiaMateriale, Prenotazione

    with auth_client.application.app_context():
        # Cliente di test
        cliente = User(username="testcliente", email="c@c.local", role="cliente")
        cliente.set_password("pass")
        db.session.add(cliente)
        db.session.flush()  # necessario per avere cliente.id

        # Slot orario: giorno futuro che matchi il giorno_settimana
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
            capienza=2,
            attivo=True,
            creato_da_id=1,
        )
        db.session.add(slot)

        # Magazzino
        mag = MagazzinoCapienza(magazzino="TestMag", capienza_contemporanea=2, creato_da_id=1)
        db.session.add(mag)

        # Tipologia per il cliente (cliente.id ora disponibile grazie a flush)
        tip = TipologiaMateriale(cliente_id=cliente.id, nome="TestTipo", durata_minuti=60, attivo=True)
        db.session.add(tip)
        db.session.commit()

        cliente_id = cliente.id
        slot_id = slot.id
        tip_id = tip.id

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
    # Deve essere 302 (redirect dopo successo), NON 500
    assert resp.status_code == 302, (
        f"Expected 302, got {resp.status_code}. "
        f"Redirect location: {getattr(resp, 'location', 'N/A')}"
    )

    # Verifica che la prenotazione sia stata creata
    with auth_client.application.app_context():
        p = Prenotazione.query.filter_by(targa="AB123CD").first()
        assert p is not None, "Prenotazione non creata"
        assert p.cliente_id == cliente_id
        assert p.inserita_da_staff is True
        assert p.stato == "ingresso_registrato"
