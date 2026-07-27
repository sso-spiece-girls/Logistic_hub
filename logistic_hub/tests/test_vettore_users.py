"""Test per associazione Vettore ↔ Clienti dal form utenti.
Quando si crea un utente ruolo "vettore", si possono selezionare
più clienti esistenti da associare. Il record Vettore viene auto-creato.
"""


def _crea_clienti(db, count=2):
    """Helper: crea N utenti cliente e restituisce lista degli ID."""
    from models import User

    ids = []
    for i in range(count):
        c = User(username=f"cliente-test-{i}", email=f"c{i}@test.local", role="cliente")
        c.set_password("pass")
        db.session.add(c)
        db.session.flush()
        ids.append(c.id)
    db.session.commit()
    return ids


def test_creazione_vettore_con_clienti(auth_client, db):
    """Crea utente vettore con 2 clienti selezionati → Vettore auto-creato + ClienteVettore."""
    from models import Vettore, User, ClienteVettore

    with auth_client.application.app_context():
        ids = _crea_clienti(db, 2)

    resp = auth_client.post("/users/nuovo", data={
        "username": "nuovovettore",
        "email": "vettore@example.com",
        "password": "pass1234",
        "role": "vettore",
        "clienti_associati": [str(ids[0]), str(ids[1])],
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Creazione dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        user = User.query.filter_by(username="nuovovettore").first()
        assert user is not None
        assert user.role == "vettore"
        # Vettore auto-creato
        vettore = user.vettore
        assert vettore is not None, "Vettore deve essere auto-creato"
        assert vettore.nome == f"Autista {user.username}"
        assert vettore.attivo is True
        # ClienteVettore creati
        associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
        assert len(associazioni) == 2
        ids_associati = {a.cliente_id for a in associazioni}
        assert ids_associati == {ids[0], ids[1]}


def test_creazione_vettore_senza_clienti(auth_client, db):
    """Crea utente vettore senza selezionare clienti → Vettore creato, nessun ClienteVettore."""
    from models import User, Vettore, ClienteVettore

    resp = auth_client.post("/users/nuovo", data={
        "username": "vettore_solo",
        "email": "solo@example.com",
        "password": "pass1234",
        "role": "vettore",
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Creazione dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        user = User.query.filter_by(username="vettore_solo").first()
        assert user is not None
        assert user.role == "vettore"
        vettore = user.vettore
        assert vettore is not None, "Vettore deve essere auto-creato anche senza clienti"
        associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
        assert len(associazioni) == 0


def test_modifica_vettore_aggiungi_clienti(auth_client, db):
    """Crea vettore senza clienti, poi modifica aggiungendone 2."""
    from models import User, ClienteVettore

    with auth_client.application.app_context():
        ids = _crea_clienti(db, 2)

    # Crea vettore senza clienti
    auth_client.post("/users/nuovo", data={
        "username": "vettore_mod",
        "email": "mod@example.com",
        "password": "pass1234",
        "role": "vettore",
    })

    with auth_client.application.app_context():
        user = User.query.filter_by(username="vettore_mod").first()
        uid = user.id

    # Modifica: aggiungi 2 clienti
    resp = auth_client.post(f"/users/{uid}/modifica", data={
        "username": "vettore_mod",
        "email": "mod@example.com",
        "password": "",
        "role": "vettore",
        "clienti_associati": [str(ids[0]), str(ids[1])],
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Modifica dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        user = User.query.get(uid)
        vettore = user.vettore
        associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
        assert len(associazioni) == 2
        ids_associati = {a.cliente_id for a in associazioni}
        assert ids_associati == {ids[0], ids[1]}


def test_modifica_vettore_rimuovi_clienti(auth_client, db):
    """Crea vettore con 2 clienti, poi modifica rimuovendone 1."""
    from models import User, ClienteVettore

    with auth_client.application.app_context():
        ids = _crea_clienti(db, 2)

    # Crea vettore con 2 clienti
    auth_client.post("/users/nuovo", data={
        "username": "vettore_rm",
        "email": "rm@example.com",
        "password": "pass1234",
        "role": "vettore",
        "clienti_associati": [str(ids[0]), str(ids[1])],
    })

    with auth_client.application.app_context():
        user = User.query.filter_by(username="vettore_rm").first()
        uid = user.id

    # Modifica: rimuovi ids[1], tieni solo ids[0]
    resp = auth_client.post(f"/users/{uid}/modifica", data={
        "username": "vettore_rm",
        "email": "rm@example.com",
        "password": "",
        "role": "vettore",
        "clienti_associati": [str(ids[0])],
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Modifica dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        user = User.query.get(uid)
        vettore = user.vettore
        associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
        assert len(associazioni) == 1
        assert associazioni[0].cliente_id == ids[0]


def test_modifica_vettore_diventa_admin(auth_client, db):
    """Vettore cambiato in admin → Vettore scollegato, ClienteVettore rimossi."""
    from models import User, Vettore, ClienteVettore

    with auth_client.application.app_context():
        ids = _crea_clienti(db, 1)

    # Crea vettore con 1 cliente
    auth_client.post("/users/nuovo", data={
        "username": "vettore2admin",
        "email": "v2a@example.com",
        "password": "pass1234",
        "role": "vettore",
        "clienti_associati": [str(ids[0])],
    })

    with auth_client.application.app_context():
        user = User.query.filter_by(username="vettore2admin").first()
        uid = user.id
        vettore_id = user.vettore.id

    # Cambia ruolo da vettore ad admin
    resp = auth_client.post(f"/users/{uid}/modifica", data={
        "username": "vettore2admin",
        "email": "v2a@example.com",
        "password": "",
        "role": "admin",
    }, follow_redirects=False)

    assert resp.status_code == 302, f"Modifica dovrebbe redirect, status={resp.status_code}"

    with auth_client.application.app_context():
        user = User.query.get(uid)
        assert user.role == "admin"
        # Vettore scollegato (user_id = None)
        vettore = Vettore.query.get(vettore_id)
        assert vettore.user_id is None, "Il Vettore deve essere scollegato"
        # ClienteVettore rimossi
        associazioni = ClienteVettore.query.filter_by(vettore_id=vettore_id).all()
        assert len(associazioni) == 0
