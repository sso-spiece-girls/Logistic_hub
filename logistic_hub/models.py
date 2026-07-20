from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="operatore")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    activities = db.relationship("Activity", backref="user", lazy="dynamic", foreign_keys="Activity.user_id")
    notifications = db.relationship("Notification", backref="user", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role in roles

    @property
    def role_label(self):
        labels = {"operatore": "Operatore", "ufficio": "Ufficio", "admin": "Admin", "cliente": "Cliente"}
        return labels.get(self.role, self.role)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Activity(db.Model):
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<Activity {self.action} by {self.user_id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(20), default="info")
    read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<Notification {self.title}>"


class Bolla(db.Model):
    __tablename__ = "bolle"

    id = db.Column(db.Integer, primary_key=True)
    numero_bolla = db.Column(db.Text, nullable=False, index=True)
    fornitore = db.Column(db.String(200), nullable=False, index=True)
    data_arrivo = db.Column(db.Date, nullable=True, index=True)
    data_caricamento = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    stato = db.Column(db.String(30), default="da_elaborare", index=True)
    operatore_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    file_path = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)
    hash_pdf = db.Column(db.String(64), nullable=True, unique=True)
    fornitore_nome = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    operatore = db.relationship("User", foreign_keys=[operatore_id])

    @property
    def stato_label(self):
        labels = {"da_elaborare": "Da elaborare", "in_lavorazione": "In lavorazione", "completata": "Completata"}
        return labels.get(self.stato, self.stato)

    def __repr__(self):
        return f"<Bolla {self.numero_bolla}>"


class DDT(db.Model):
    __tablename__ = "ddt"

    id = db.Column(db.Integer, primary_key=True)
    numero_ddt = db.Column(db.Text, nullable=False, index=True)
    cliente = db.Column(db.String(200), nullable=False, index=True)
    destinatario = db.Column(db.String(200), nullable=True)
    provenienza = db.Column(db.String(300), nullable=True)
    vettore = db.Column(db.String(200), nullable=True)
    causale_trasporto = db.Column(db.String(200), nullable=True)
    data_creazione = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    data_spedizione = db.Column(db.Date, nullable=True)
    stato = db.Column(db.String(30), default="bozza", index=True)
    operatore_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    note = db.Column(db.Text, nullable=True)
    filename_pdf = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    operatore = db.relationship("User", foreign_keys=[operatore_id])

    @property
    def stato_label(self):
        labels = {"bozza": "Bozza", "pronto": "Pronto", "spedito": "Spedito", "annullato": "Annullato"}
        return labels.get(self.stato, self.stato)

    def __repr__(self):
        return f"<DDT {self.numero_ddt}>"


class Giacenza(db.Model):
    __tablename__ = "giacenze"

    id = db.Column(db.Integer, primary_key=True)
    codice_articolo = db.Column(db.String(500), nullable=False, index=True)
    descrizione = db.Column(db.String(300), nullable=False)
    quantita = db.Column(db.Float, default=0)
    ubicazione = db.Column(db.String(100), nullable=True)
    colli = db.Column(db.Integer, default=0)
    pallet = db.Column(db.Integer, default=0)
    id_bobina = db.Column(db.String(100), nullable=True, index=True)
    qualita = db.Column(db.String(50), nullable=True)
    provenienza = db.Column(db.String(100), nullable=True)
    peso_kg = db.Column(db.Float, default=0.0)
    magazzino = db.Column(db.String(50), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    aggiornato_da = db.relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<Giacenza {self.codice_articolo}>"


class Picking(db.Model):
    __tablename__ = "picking"

    id = db.Column(db.Integer, primary_key=True)
    numero_picking = db.Column(db.String(100), nullable=False, index=True)
    cliente = db.Column(db.String(200), nullable=True)
    stato = db.Column(db.String(30), default="aperto")
    operatore_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    operatore = db.relationship("User", foreign_keys=[operatore_id])

    @property
    def stato_label(self):
        labels = {"aperto": "Aperto", "in_corso": "In corso", "completato": "Completato"}
        return labels.get(self.stato, self.stato)

    def __repr__(self):
        return f"<Picking {self.numero_picking}>"


class Documento(db.Model):
    __tablename__ = "documenti"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(300), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    caricato_da = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    caricato = db.relationship("User", foreign_keys=[caricato_da])

    def __repr__(self):
        return f"<Documento {self.nome}>"


class BackupLog(db.Model):
    __tablename__ = "backup_log"

    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(500), nullable=False)
    size = db.Column(db.Integer, default=0)
    tipo = db.Column(db.String(20), default="manuale")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    eseguito_da = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<Backup {self.created_at}>"


class Fornitore(db.Model):
    __tablename__ = "fornitori"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)
    partita_iva = db.Column(db.String(20), nullable=True)
    indirizzo = db.Column(db.String(300), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    articoli = db.relationship("Articolo", backref="fornitore", lazy="dynamic")

    def __repr__(self):
        return f"<Fornitore {self.nome}>"


class Articolo(db.Model):
    __tablename__ = "articoli"

    id = db.Column(db.Integer, primary_key=True)
    codice = db.Column(db.String(500), nullable=False, unique=True, index=True)
    descrizione = db.Column(db.String(300), nullable=False)
    unita_misura = db.Column(db.String(20), default="colli")
    categoria = db.Column(db.String(100), nullable=True)
    fornitore_id = db.Column(db.Integer, db.ForeignKey("fornitori.id"), nullable=True)

    def __repr__(self):
        return f"<Articolo {self.codice}>"


class DettaglioBolla(db.Model):
    __tablename__ = "dettaglio_bolla"

    id = db.Column(db.Integer, primary_key=True)
    bolla_id = db.Column(db.Integer, db.ForeignKey("bolle.id"), nullable=False, index=True)
    articolo_codice = db.Column(db.String(500), nullable=False, index=True)
    descrizione = db.Column(db.String(300), nullable=True)
    quantita_colli = db.Column(db.Integer, default=0)
    quantita_pallet = db.Column(db.Integer, default=0)
    peso_kg = db.Column(db.Float, default=0.0)
    sscc_lotto = db.Column(db.String(200), nullable=True)

    bolla = db.relationship("Bolla", backref=db.backref("righe", lazy="dynamic"))

    def __repr__(self):
        return f"<DettaglioBolla {self.articolo_codice}>"


class RigheDDT(db.Model):
    __tablename__ = "righe_ddt"

    id = db.Column(db.Integer, primary_key=True)
    ddt_id = db.Column(db.Integer, db.ForeignKey("ddt.id"), nullable=False, index=True)
    articolo_codice = db.Column(db.String(500), nullable=False, index=True)
    descrizione = db.Column(db.String(300), nullable=True)
    quantita_colli = db.Column(db.Integer, default=0)
    quantita_pallet = db.Column(db.Integer, default=0)
    peso_kg = db.Column(db.Float, default=0.0)
    ubicazione = db.Column(db.String(100), nullable=True)

    ddt = db.relationship("DDT", backref=db.backref("righe", lazy="dynamic"))

    def __repr__(self):
        return f"<RigheDDT {self.articolo_codice}>"


class Movimento(db.Model):
    __tablename__ = "movimenti"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)
    articolo_codice = db.Column(db.String(500), nullable=False, index=True)
    descrizione = db.Column(db.String(300), nullable=True)
    id_bobina = db.Column(db.String(100), nullable=True)
    quantita = db.Column(db.Float, default=0)
    colli = db.Column(db.Integer, default=0)
    pallet = db.Column(db.Integer, default=0)
    peso_kg = db.Column(db.Float, default=0.0)
    magazzino = db.Column(db.String(50), nullable=True)
    ubicazione = db.Column(db.String(100), nullable=True)
    riferimento_id = db.Column(db.Integer, nullable=True, index=True)
    riferimento_tipo = db.Column(db.String(50), nullable=True, index=True)
    note = db.Column(db.String(500), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<Movimento {self.tipo} {self.articolo_codice}>"


class PickingRiga(db.Model):
    __tablename__ = "picking_righe"

    id = db.Column(db.Integer, primary_key=True)
    picking_id = db.Column(db.Integer, db.ForeignKey("picking.id"), nullable=False)
    articolo_codice = db.Column(db.String(500), nullable=False)
    descrizione = db.Column(db.String(300), nullable=True)
    quantita_colli = db.Column(db.Integer, default=0)
    peso_kg = db.Column(db.Float, default=0.0)
    residuo = db.Column(db.Boolean, default=False)

    picking = db.relationship("Picking", backref=db.backref("righe", lazy="dynamic"))

    def __repr__(self):
        return f"<PickingRiga {self.articolo_codice}>"


class SlotOrario(db.Model):
    __tablename__ = "slot_orari"

    id = db.Column(db.Integer, primary_key=True)
    giorno_settimana = db.Column(db.Integer, nullable=False)  # 0=lunedì … 6=domenica
    ora_inizio = db.Column(db.Time, nullable=False)
    ora_fine = db.Column(db.Time, nullable=False)
    durata_minuti = db.Column(db.Integer, nullable=False, default=60)
    capienza = db.Column(db.Integer, nullable=False, default=1)
    attivo = db.Column(db.Boolean, default=True)
    creato_da_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creato_da = db.relationship("User", foreign_keys=[creato_da_id])

    def __repr__(self):
        return f"<SlotOrario giorno={self.giorno_settimana} {self.ora_inizio}-{self.ora_fine}>"


class MagazzinoCapienza(db.Model):
    __tablename__ = "magazzini_capienza"

    id = db.Column(db.Integer, primary_key=True)
    magazzino = db.Column(db.String(50), nullable=False, unique=True)
    capienza_contemporanea = db.Column(db.Integer, nullable=False, default=1)
    creato_da_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creato_da = db.relationship("User", foreign_keys=[creato_da_id])

    def __repr__(self):
        return f"<MagazzinoCapienza {self.magazzino} capienza={self.capienza_contemporanea}>"


class TipologiaMateriale(db.Model):
    __tablename__ = "tipologie_materiale"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    nome = db.Column(db.String(100), nullable=False)
    durata_minuti = db.Column(db.Integer, nullable=False, default=60)
    attivo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cliente = db.relationship("User", foreign_keys=[cliente_id])

    def __repr__(self):
        return f"<TipologiaMateriale {self.nome} cliente={self.cliente_id}>"


class Prenotazione(db.Model):
    __tablename__ = "prenotazioni"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    slot_orario_id = db.Column(db.Integer, db.ForeignKey("slot_orari.id"), nullable=False, index=True)
    data = db.Column(db.Date, nullable=False, index=True)
    ora_inizio = db.Column(db.Time, nullable=False)
    ora_fine = db.Column(db.Time, nullable=False)
    tipo = db.Column(db.String(10), nullable=False, default="scarico")  # carico / scarico
    magazzino = db.Column(db.String(50), nullable=True)
    tipologia_materiale_id = db.Column(db.Integer, db.ForeignKey("tipologie_materiale.id"), nullable=True)
    stato = db.Column(db.String(20), nullable=False, default="in_attesa", index=True)
    token_qr = db.Column(db.String(64), unique=True, nullable=True, index=True)
    note_operatore = db.Column(db.Text, nullable=True)
    approvato_da_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approvato_at = db.Column(db.DateTime, nullable=True)
    ingresso_verificato_da_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    ingresso_verificato_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cliente = db.relationship("User", foreign_keys=[cliente_id], backref="prenotazioni")
    slot_orario = db.relationship("SlotOrario", foreign_keys=[slot_orario_id])
    tipologia_materiale = db.relationship("TipologiaMateriale", foreign_keys=[tipologia_materiale_id])
    approvato_da = db.relationship("User", foreign_keys=[approvato_da_id])
    ingresso_verificato_da = db.relationship("User", foreign_keys=[ingresso_verificato_da_id])

    STATI_ATTIVI = ("in_attesa", "confermata")

    @property
    def stato_label(self):
        labels = {
            "in_attesa": "In attesa",
            "confermata": "Confermata",
            "rifiutata": "Rifiutata",
            "ingresso_registrato": "Ingresso registrato",
            "ingresso_rifiutato": "Ingresso rifiutato",
            "annullata": "Annullata",
            "scaduta": "Scaduta",
        }
        return labels.get(self.stato, self.stato)

    __table_args__ = (
        db.Index(
            "uq_slot_booking_attivo",
            "slot_orario_id", "data", "ora_inizio",
            unique=True,
            postgresql_where=db.text("stato IN ('in_attesa', 'confermata')"),
        ),
        db.Index("ix_prenotazioni_data_ora", "data", "ora_inizio"),
        db.Index("ix_prenotazioni_data_stato", "data", "stato"),
        db.Index("ix_prenotazioni_cliente_data", "cliente_id", "data"),
    )

    def __repr__(self):
        return f"<Prenotazione {self.id} cliente={self.cliente_id} {self.data} {self.ora_inizio}>"
