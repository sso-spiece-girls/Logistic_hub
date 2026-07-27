"""Test per Blocco 4 — Collegamento Vettore ↔ User dal form admin."""


def test_creazione_vettore_con_link(auth_client, db):
    """Crea utente vettore con vettore_id valido → Vettore.user_id impostato."""
    from models import Vettore, User

    with auth_client.application.app_context():
        v = Vettore(nome="Trasporti Rossi", partita_iva="12345678901", attivo=True)
        db.session.add(v)
        db.session.commit()
        vettore_id = v.id

    resp = auth_client.post("/users/nuovo", data={
        "username": "nuovovettore",
        "email": "vettore@example.com",
        "password": "pass1234",
        "role": "vettore",
        "vettore_id": str(vettore_id),
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Creazione dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        user = User.query.filter_by(username="nuovovettore").first()
        assert user is not None
        assert user.role == "vettore"
        vettore = Vettore.query.get(vettore_id)
        assert vettore.user_id == user.id, "Vettore deve essere collegato al nuovo utente"


def test_creazione_vettore_senza_vettore_id(auth_client, db):
    """POST con role=vettore + vettore_id=0 → errore, User NON creato."""
    from models import User

    resp = auth_client.post("/users/nuovo", data={
        "username": "vettorenolink",
        "email": "nolink@example.com",
        "password": "pass1234",
        "role": "vettore",
        "vettore_id": "0",
    }, follow_redirects=False)

    assert resp.status_code == 200, "Errore di validazione: deve restare sul form"

    with auth_client.application.app_context():
        user = User.query.filter_by(username="vettorenolink").first()
        assert user is None, "L'utente non deve essere creato"


def test_modifica_vettore_cambio_vettore(auth_client, db):
    """Modifica utente vettore → scollega vecchio Vettore, collega nuovo."""
    from models import User, Vettore

    with auth_client.application.app_context():
        v1 = Vettore(nome="V1", partita_iva="11111111111", attivo=True)
        v2 = Vettore(nome="V2", partita_iva="22222222222", attivo=True)
        db.session.add_all([v1, v2])
        db.session.flush()
        user = User(username="vettoremodexisting", email="mod@example.com", role="vettore")
        user.set_password("pass")
        db.session.add(user)
        db.session.flush()
        v1.user_id = user.id
        db.session.commit()
        uid, v1id, v2id = user.id, v1.id, v2.id

    resp = auth_client.post(f"/users/{uid}/modifica", data={
        "username": "vettoremodexisting",
        "email": "mod@example.com",
        "password": "",
        "role": "vettore",
        "vettore_id": str(v2id),
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Modifica dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        v1a = Vettore.query.get(v1id)
        v2a = Vettore.query.get(v2id)
        assert v1a.user_id is None, "Il vecchio Vettore deve essere scollegato"
        assert v2a.user_id == uid, "Il nuovo Vettore deve essere collegato"


def test_creazione_vettore_conflitto_unique(auth_client, db):
    """Vettore già collegato ad altro utente → form validation rifiuta, User non creato."""
    from models import User, Vettore

    with auth_client.application.app_context():
        v = Vettore(nome="V3", partita_iva="33333333333", attivo=True)
        db.session.add(v)
        db.session.flush()
        u1 = User(username="primovettore", email="p1@example.com", role="vettore")
        u1.set_password("pass")
        db.session.add(u1)
        db.session.flush()
        v.user_id = u1.id
        db.session.commit()
        vettore_id = v.id

    resp = auth_client.post("/users/nuovo", data={
        "username": "secondovettore",
        "email": "p2@example.com",
        "password": "pass1234",
        "role": "vettore",
        "vettore_id": str(vettore_id),
    }, follow_redirects=False)

    assert resp.status_code == 200, "Vettore già collegato deve restare sul form"

    with auth_client.application.app_context():
        assert User.query.filter_by(username="secondovettore").first() is None


def test_modifica_vettore_conflitto_unique(auth_client, db):
    """Modifica: POST con vettore già collegato a un altro utente → bloccato, nessun cambiamento."""
    from models import User, Vettore

    with auth_client.application.app_context():
        v1 = Vettore(nome="VettoreUno", partita_iva="11111111111", attivo=True)
        v2 = Vettore(nome="VettoreDue", partita_iva="22222222222", attivo=True)
        db.session.add_all([v1, v2])
        db.session.flush()
        u1 = User(username="user_a_vettore", email="ua@example.com", role="vettore")
        u1.set_password("pass")
        u2 = User(username="user_b_vettore", email="ub@example.com", role="vettore")
        u2.set_password("pass")
        db.session.add_all([u1, u2])
        db.session.flush()
        v1.user_id = u1.id
        v2.user_id = u2.id
        db.session.commit()
        uid_a, uid_b, v1id, v2id = u1.id, u2.id, v1.id, v2.id

    # POST diretto: prova a collegare UserA a V2 (già collegato a UserB)
    resp = auth_client.post(f"/users/{uid_a}/modifica", data={
        "username": "user_a_vettore",
        "email": "ua@example.com",
        "password": "",
        "role": "vettore",
        "vettore_id": str(v2id),
    }, follow_redirects=False)

    assert resp.status_code == 200, "Deve restare sul form (errore validazione)"

    with auth_client.application.app_context():
        v1_now = Vettore.query.get(v1id)
        v2_now = Vettore.query.get(v2id)
        u1_now = User.query.get(uid_a)
        u2_now = User.query.get(uid_b)
        # Nessun collegamento deve cambiare
        assert v1_now.user_id == uid_a, "V1 deve restare collegato a UserA"
        assert v2_now.user_id == uid_b, "V2 deve restare collegato a UserB"
        # Nessun utente deve cambiare ruolo
        assert u1_now.role == "vettore"
        assert u2_now.role == "vettore"
