from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SelectField, TextAreaField, DateField, FloatField, IntegerField, FieldList, FormField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Length, Email, Optional, NumberRange

MAGAZZINI = [
    ("", "--- Seleziona ---"),
    ("Colle 1", "Colle 1"),
    ("Colle 2", "Colle 2"),
    ("Colle 3", "Colle 3"),
    ("Colle 4", "Colle 4"),
    ("Colle 5", "Colle 5"),
]

PROVENIENZE = [
    ("", "--- Seleziona ---"),
    ("Via Napoli 22, Collesalvetti", "Via Napoli 22, Collesalvetti"),
    ("Via Francia 70, Collesalvetti", "Via Francia 70, Collesalvetti"),
]


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField("Email", validators=[Optional(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=4)])
    role = SelectField("Ruolo", choices=[
        ("operatore", "Operatore"),
        ("ufficio", "Ufficio"),
        ("admin", "Admin"),
        ("cliente", "Cliente"),
    ], validators=[DataRequired()])


class BollaForm(FlaskForm):
    numero_bolla = StringField("Numero Bolla", validators=[DataRequired()])
    fornitore = StringField("Fornitore", validators=[DataRequired()])
    data_arrivo = DateField("Data Arrivo", validators=[Optional()])
    stato = SelectField("Stato", choices=[
        ("da_elaborare", "Da elaborare"),
        ("in_lavorazione", "In lavorazione"),
        ("completata", "Completata"),
    ])
    note = TextAreaField("Note", validators=[Optional()])
    file_pdf = FileField("File PDF", validators=[Optional(), FileAllowed(["pdf"], "Solo file PDF")])


class RigaDDTForm(FlaskForm):
    articolo_codice = StringField("Codice Articolo", validators=[DataRequired()])
    descrizione = StringField("Descrizione", validators=[Optional()])
    quantita_colli = IntegerField("Colli", validators=[Optional()], default=1)
    quantita_pallet = IntegerField("Pallet", validators=[Optional()], default=0)
    peso_kg = FloatField("Peso (kg)", validators=[Optional()], default=0.0)
    ubicazione = StringField("Ubicazione", validators=[Optional()])


class DDTForm(FlaskForm):
    numero_ddt = StringField("Numero DDT", validators=[DataRequired()])
    cliente = StringField("Cliente", validators=[DataRequired()])
    destinatario = StringField("Destinatario", validators=[Optional()])
    provenienza = SelectField("Provenienza", choices=PROVENIENZE, validators=[Optional()])
    vettore = StringField("Vettore", validators=[Optional()])
    causale_trasporto = StringField("Causale Trasporto", validators=[Optional()], default="Vendita")
    data_spedizione = DateField("Data Spedizione", validators=[Optional()])
    magazzino = SelectField("Magazzino", choices=MAGAZZINI, validators=[Optional()])
    stato = SelectField("Stato", choices=[
        ("bozza", "Bozza"),
        ("pronto", "Pronto"),
        ("spedito", "Spedito"),
        ("annullato", "Annullato"),
    ])
    note = TextAreaField("Note", validators=[Optional()])


class GiacenzaForm(FlaskForm):
    codice_articolo = StringField("Codice Articolo", validators=[DataRequired()])
    descrizione = StringField("Descrizione", validators=[DataRequired()])
    quantita = FloatField("Quantità", validators=[Optional()], default=0)
    colli = IntegerField("Colli", validators=[Optional()], default=0)
    pallet = IntegerField("Pallet", validators=[Optional()], default=0)
    peso_kg = FloatField("Peso (kg)", validators=[Optional()], default=0.0)
    id_bobina = StringField("ID Bobina", validators=[Optional()])
    qualita = StringField("Qualità", validators=[Optional()])
    provenienza = StringField("Provenienza", validators=[Optional()])
    ubicazione = StringField("Ubicazione", validators=[Optional()])
    magazzino = SelectField("Magazzino", choices=MAGAZZINI, validators=[Optional()])


class PickingForm(FlaskForm):
    numero_picking = StringField("Numero Picking", validators=[DataRequired()])
    cliente = StringField("Cliente", validators=[Optional()])
    stato = SelectField("Stato", choices=[
        ("aperto", "Aperto"),
        ("in_corso", "In corso"),
        ("completato", "Completato"),
    ])


class MovimentoFiltroForm(FlaskForm):
    tipo = SelectField("Tipo", choices=[
        ("", "Tutti"),
        ("ingresso", "Ingresso"),
        ("uscita", "Uscita"),
    ], validators=[Optional()])
    articolo_codice = StringField("Codice Articolo", validators=[Optional()])
    magazzino = SelectField("Magazzino", choices=[("", "Tutti")] + MAGAZZINI[1:], validators=[Optional()])
    data_da = DateField("Da", validators=[Optional()])
    data_a = DateField("A", validators=[Optional()])


class PrenotazioneForm(FlaskForm):
    slot_orario_id = HiddenField(validators=[DataRequired()])
    data_prenotazione = DateField("Data", validators=[DataRequired()])
    ora_inizio = StringField("Ora inizio", validators=[DataRequired()])
    ora_fine = StringField("Ora fine", validators=[DataRequired()])
    tipo = SelectField("Tipo operazione", choices=[
        ("scarico", "Scarico"),
        ("carico", "Carico"),
    ], validators=[DataRequired()])
    tipologia_materiale_id = SelectField("Tipologia materiale", coerce=int, validators=[DataRequired()])
    magazzino = SelectField("Magazzino", validators=[DataRequired()])
    targa = StringField("Targa", validators=[DataRequired()])
    ddt_cmr = StringField("DDT / CMR", validators=[DataRequired()])
    vettore_id = SelectField("Vettore (opzionale)", coerce=int, validators=[Optional()])


class SlotOrarioForm(FlaskForm):
    giorno_settimana = SelectField("Giorno della settimana", choices=[
        ("0", "Lunedì"),
        ("1", "Martedì"),
        ("2", "Mercoledì"),
        ("3", "Giovedì"),
        ("4", "Venerdì"),
        ("5", "Sabato"),
        ("6", "Domenica"),
    ], validators=[DataRequired()])
    ora_inizio = StringField("Ora inizio (HH:MM)", validators=[DataRequired()])
    ora_fine = StringField("Ora fine (HH:MM)", validators=[DataRequired()])
    durata_minuti = IntegerField("Durata slot (minuti)", validators=[DataRequired()], default=60)
    capienza = IntegerField("Capienza massima", validators=[DataRequired()], default=1)
    attivo = BooleanField("Attivo", default=True)


class PrenotazioneAdminForm(FlaskForm):
    motivo = StringField("Motivo (opzionale per rifiuto)", validators=[Optional()])
    magazzino = SelectField("Assegna magazzino", choices=MAGAZZINI, validators=[Optional()])


class MagazzinoCapienzaForm(FlaskForm):
    magazzino = SelectField("Magazzino", choices=MAGAZZINI, validators=[DataRequired()])
    capienza_contemporanea = IntegerField("Capienza contemporanea", validators=[DataRequired()], default=1)
    durata_slot_minuti = IntegerField("Durata slot fallback (minuti, opzionale)", validators=[Optional()])


class TipologiaMaterialeForm(FlaskForm):
    nome = StringField("Nome tipologia", validators=[DataRequired(), Length(max=100)])
    durata_minuti = IntegerField("Durata (minuti)", validators=[DataRequired()], default=60)


class PrenotazioneStaffForm(FlaskForm):
    cliente_id = SelectField("Cliente", coerce=int, validators=[DataRequired()])
    data_prenotazione = DateField("Data", validators=[DataRequired()])
    slot_orario_id = SelectField("Fascia oraria", coerce=int, validators=[DataRequired()])
    ora_inizio = StringField("Ora inizio", validators=[DataRequired()])
    tipo = SelectField("Tipo operazione", choices=[
        ("scarico", "Scarico"),
        ("carico", "Carico"),
    ], validators=[DataRequired()])
    tipologia_materiale_id = SelectField("Tipologia materiale", coerce=int, validators=[DataRequired()])
    magazzino = SelectField("Magazzino", validators=[DataRequired()])
    targa = StringField("Targa", validators=[DataRequired()])
    ddt_cmr = StringField("DDT / CMR", validators=[DataRequired()])
    vettore_id = SelectField("Vettore (opzionale)", coerce=int, validators=[Optional()])
    ingresso_diretto = BooleanField("Ingresso già avvenuto, registra direttamente", default=False)
    inserimento_retroattivo = BooleanField("Inserimento retroattivo (consenti date passate)", default=False)


class VettoreForm(FlaskForm):
    nome = StringField("Nome vettore", validators=[DataRequired(), Length(max=200)])
    partita_iva = StringField("Partita IVA", validators=[Optional(), Length(max=20)])
    telefono = StringField("Telefono", validators=[Optional(), Length(max=30)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=120)])
    attivo = BooleanField("Attivo", default=True)
