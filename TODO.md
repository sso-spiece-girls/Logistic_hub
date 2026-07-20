# Feature: capienza magazzini, tipologie materiale per cliente, tile dashboard + fix sicurezza

Questo documento ha **due parti indipendenti**. Puoi farle eseguire separatamente a DeepSeek se preferisci, ma segui lo stesso schema per entrambe: **piano scritto prima, diff dopo, un file alla volta**, coerente con come è stata costruita tutta la feature prenotazioni finora.

---

# PARTE 1 — Capienza magazzini, tipologie materiale, tile dashboard

## Contesto (leggere prima di scrivere codice)

Il blueprint `prenotazioni` esiste già e funziona: modelli `SlotOrario`/`Prenotazione` in `models.py`, route in `routes/prenotazioni.py`, form in `forms.py`, decorator `operatore_required`/`admin_required` in `core/auth_decorators.py`. Il pattern di lock per evitare race condition (`with_for_update()` sulla riga bloccante, dentro la stessa transazione, count+insert prima del commit) è già validato e testato con concorrenza reale — **riusa lo stesso pattern**, non inventarne uno diverso.

`MAGAZZINI` è una lista di tuple già definita in cima a `forms.py`:
```python
MAGAZZINI = [
    ("", "--- Seleziona ---"),
    ("Colle 1", "Colle 1"),
    ("Colle 2", "Colle 2"),
    ("Colle 3", "Colle 3"),
    ("Colle 4", "Colle 4"),
    # ... altri valori esistenti, non modificarli
]
```
Riusala per il nuovo modello, non duplicarla.

**Importante — cosa NON cambia rispetto a prima:** il cliente prenota solo una fascia oraria, punto. Non sceglie un magazzino. È l'operatore che assegna il magazzino in fase di approvazione (route `approva()` già esistente, campo `PrenotazioneAdminForm.magazzino`). Il problema da risolvere è solo: **impedire che l'operatore assegni un magazzino già pieno in quella fascia oraria**, senza dover contare a mano.

## 1. Capienza magazzini

### Modello

```python
class MagazzinoCapienza(db.Model):
    __tablename__ = "magazzino_capienza"
    id = db.Column(db.Integer, primary_key=True)
    magazzino = db.Column(db.String(50), unique=True, nullable=False)
    capienza_contemporanea = db.Column(db.Integer, nullable=False, default=1)
    creato_da_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

Un magazzino senza riga in questa tabella si considera **senza limite** (capienza illimitata) — così non è obbligatorio configurarli tutti subito, solo quelli che davvero hanno un vincolo fisico. Nella route di approvazione, se non esiste una riga per quel magazzino, salta il controllo di capienza.

### CRUD (solo admin)

Nuove route in `routes/prenotazioni.py`, stesso schema di `admin_slot()`/`admin_slot_nuovo()`/`admin_slot_modifica()`:
- `GET /prenotazioni/admin/magazzini` — lista
- `GET/POST /prenotazioni/admin/magazzini/nuovo`
- `GET/POST /prenotazioni/admin/magazzini/<id>/modifica`

Form in `forms.py`:
```python
class MagazzinoCapienzaForm(FlaskForm):
    magazzino = SelectField("Magazzino", choices=MAGAZZINI, validators=[DataRequired()])
    capienza_contemporanea = IntegerField("Capienza contemporanea", validators=[DataRequired()], default=1)
```

Template: `templates/prenotazioni/admin_magazzini.html` + `admin_magazzini_form.html`, ricalcando esattamente `admin_slot.html`/`admin_slot_form.html` (stessa struttura tabella, stessi bottoni modifica/elimina).

### Controllo in fase di approvazione

Modifica alla route `approva()` esistente in `routes/prenotazioni.py`. **Dopo** il controllo di capienza dello slot già presente (quello sul lock di `SlotOrario`), aggiungere il controllo sul magazzino, **stesso identico pattern di lock**:

```python
if form.magazzino.data:
    mag = db.session.query(MagazzinoCapienza).filter(
        MagazzinoCapienza.magazzino == form.magazzino.data
    ).with_for_update().first()
    if mag:
        occupati = Prenotazione.query.filter(
            Prenotazione.magazzino == form.magazzino.data,
            Prenotazione.data == p.data,
            Prenotazione.ora_inizio == p.ora_inizio,
            Prenotazione.stato.in_(["confermata", "ingresso_registrato"]),
        ).count()
        if occupati >= mag.capienza_contemporanea:
            flash(f"Magazzino {form.magazzino.data} già pieno in questa fascia oraria.", "error")
            return redirect(url_for("prenotazioni.in_attesa"))
```

Nota: il lock qui è su `MagazzinoCapienza`, non su `SlotOrario` — sono due risorse diverse che possono essere contese in momenti diversi (due operatori che approvano verso lo stesso magazzino nello stesso slot). Non serve lockarle entrambe nella stessa transazione in un ordine particolare qui, perché il lock su `SlotOrario` è già stato acquisito e rilasciato (commit) nel momento della *creazione* della prenotazione, non nell'approvazione — sono transazioni separate nel tempo, non c'è rischio di deadlock tra le due.

## 2. Tipologie materiale per cliente

### Modello

```python
class TipologiaMateriale(db.Model):
    __tablename__ = "tipologie_materiale"
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    durata_minuti = db.Column(db.Integer, nullable=False, default=60)
    attivo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cliente = db.relationship("User", backref="tipologie_materiale", foreign_keys=[cliente_id])
```

`Prenotazione` guadagna un campo:
```python
tipologia_materiale_id = db.Column(db.Integer, db.ForeignKey("tipologie_materiale.id"), nullable=True)
```
`nullable=True` per non rompere le prenotazioni già esistenti in produzione create prima di questa modifica.

### Gestione tipologie (admin, dentro la scheda cliente)


Non serve una pagina separata: aggiungere la sezione tipologie **dentro `templates/users_form.html`**, visibile solo quando `form.role.data == "cliente"` (mostra/nascondi via JS semplice, coerente con come il form utenti già gestisce campi condizionali se ce ne sono — controllare `users_form.html` per pattern esistenti prima di aggiungerne uno nuovo). Sotto il form principale utente, una tabella con le tipologie esistenti del cliente + form rapido per aggiungerne una (nome + durata), + azione elimina/disattiva per riga.


Route dedicate in un nuovo file `routes/tipologie_materiale.py` (o dentro `routes/users.py` se preferisci accorpare, verifica quale sembra più naturale dato lo stato attuale del file):
- `POST /users/<cliente_id>/tipologie/nuova`
- `POST /users/<cliente_id>/tipologie/<id>/elimina` (o disattiva se ci sono prenotazioni storiche collegate — stesso pattern già usato in `admin_slot_elimina()` che blocca l'eliminazione se ci sono prenotazioni attive collegate)

### Flusso di prenotazione cliente — cambia il form e la logica


Questo è il cambio più delicato. Il form `PrenotazioneForm` guadagna:
```python
tipologia_materiale_id = SelectField("Tipologia materiale", coerce=int, validators=[DataRequired()])
```
Popolato dinamicamente nella route `calendario()`/`prenota()` con **solo le tipologie attive del cliente loggato** (`current_user.tipologie_materiale` filtrate su `attivo=True`) — se un cliente non ha nessuna tipologia configurata, mostrare un messaggio chiaro ("Contatta l'ufficio per configurare le tipologie di materiale prima di prenotare") invece di un dropdown vuoto che genera un errore di validazione poco chiaro.

**La durata della prenotazione non viene più dalla `SlotOrario.durata_minuti`, ma dalla tipologia scelta.** Questo cambia `_slot_disponibili()` e la logica di `prenota()`:

- `_slot_disponibili()` continua a generare i tick della griglia usando `regola.durata_minuti` come **passo di iterazione** (granularità minima, es. ogni 15/30 min) — serve solo per proporre orari di partenza sensati nel calendario, non è più la durata effettiva della prenotazione.
- In `prenota()`, dopo aver validato che `ora_inizio` cade su un tick valido della griglia (`_allinea_orario()` esistente, ma va adattata: non deve più calcolare `ora_fine` dalla durata della regola, deve calcolarla da `tipologia.durata_minuti`), il controllo di disponibilità **non è più un'uguaglianza su `ora_inizio`**, deve diventare un controllo di sovrapposizione reale tra intervalli:

```python
proposta_fine = (datetime.combine(date.min, ora_inizio) + timedelta(minutes=tipologia.durata_minuti)).time()
occupate = Prenotazione.query.filter(
    Prenotazione.slot_orario_id == regola.id,
    Prenotazione.data == data_prenot,
    Prenotazione.stato.in_(["in_attesa", "confermata"]),
    Prenotazione.ora_inizio < proposta_fine,
    Prenotazione.ora_fine > ora_inizio,
).count()
if occupate >= regola.capienza:
    ...
```

Il lock su `SlotOrario` resta invariato (`with_for_update()` prima di questo controllo, stessa posizione di adesso) — è quello che rende sicuro questo controllo anche con durate diverse, non il partial unique index.

**Il partial unique index `uq_slot_booking_attivo` (`slot_orario_id + data + ora_inizio`) non è più una rete di sicurezza affidabile** con durate variabili: due prenotazioni con `ora_inizio` diversi possono comunque sovrapporsi nel tempo, e l'indice non se ne accorge. Lasciarlo pure (non fa danno, blocca il caso più comune di doppia prenotazione sullo stesso identico minuto), ma DeepSeek deve sapere che **da qui in poi la vera protezione è solo il lock + il controllo applicativo**, non l'indice DB. Se preferisci, si può anche togliere l'indice per evitare confusione — a te la scelta, ma segnalalo esplicitamente nel piano prima di procedere.

Anche `admin_calendario()` (la vista completa) va aggiornata: oggi calcola `p_map` con chiave `(slot_orario_id, data, ora_inizio)` assumendo prenotazioni allineate alla griglia della regola — con durate variabili, una prenotazione può occupare più tick consecutivi. Serve segnare come "occupati" tutti i tick della griglia coperti dall'intervallo `[ora_inizio, ora_fine)` della prenotazione, non solo quello coincidente con `ora_inizio`.

## 3. Tile calendario nella dashboard

Semplice link, nessuna query nuova, nessun dato caricato. Aggiungere dentro `templates/dashboard.html`, nel blocco `action-grid` esistente (dopo la tile "Movimenti"), solo per chi ha `current_user.role in ("admin", "operatore")` — il blocco `action-grid` va quindi avvolto (o la singola tile) in un controllo di ruolo se non c'è già:

```html
<a href="{{ url_for('prenotazioni.admin_calendario') }}" class="action-card">
    <div class="action-icon" style="background:var(--info-bg);color:var(--info)">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>

    </div>

    <span>Calendario Prenotazioni</span>
</a>

```

Usare `url_for(...)` invece dell'URL scritto a mano come fanno le altre tile esistenti (`/entrate/nuova` ecc. sono hardcoded — non serve replicare quella scelta, `url_for` è più robusto e sei libero di migliorare qui senza che sia "fuori scope").


## File coinvolti — Parte 1

Crea:
- `templates/prenotazioni/admin_magazzini.html`
- `templates/prenotazioni/admin_magazzini_form.html`
- `routes/tipologie_materiale.py` (o route aggiunte a `routes/users.py`, valuta tu il posto più naturale)

Modifica:
- `models.py` — `MagazzinoCapienza`, `TipologiaMateriale`, `Prenotazione.tipologia_materiale_id`
- `forms.py` — `MagazzinoCapienzaForm`, aggiornare `PrenotazioneForm` con `tipologia_materiale_id`
- `routes/prenotazioni.py` — route CRUD magazzini, modifica `_slot_disponibili()`, `prenota()`, `approva()`, `admin_calendario()`
- `templates/users_form.html` — sezione tipologie materiale condizionale
- `templates/dashboard.html` — tile calendario
- `templates/prenotazioni/calendario.html` — dropdown tipologia materiale nel form

## Decisioni da confermare nel piano prima del codice

1. Vuoi tenere o rimuovere il partial unique index `uq_slot_booking_attivo` ora che non è più sufficiente da solo? (consigliato: tenerlo comunque come rete parziale, ma va deciso esplicitamente)
2. Se un cliente non ha tipologie configurate, blocchi la prenotazione con messaggio o fai un fallback a una durata di default? (consigliato: blocco esplicito, evita ambiguità sui tempi)
3. Le tipologie eliminabili solo se non hanno prenotazioni attive collegate, stesso pattern di `admin_slot_elimina()` — confermi o preferisci soft-delete (`attivo=False`) sempre, senza mai eliminazione fisica?

---

# PARTE 2 — Fix sicurezza (indipendente dalla Parte 1)


## Contesto


Due problemi trovati in revisione di `routes/auth.py` e `config.py`. Non toccano la feature prenotazioni, possono essere fatti prima, dopo, o in parallelo.


## 1. Nessuna protezione anti-brute-force sul login


`routes/auth.py`, route `/login`: nessun rate limiting. Aggiungere **Flask-Limiter**.


```
Flask-Limiter>=3.5.0

```

In `main.py`, dentro `create_app()`, inizializzare il limiter (stesso punto dove vengono inizializzate `db`, `login_manager`, coerente con `extensions.py` se il progetto centralizza lì le estensioni — verificare come sono dichiarate `db`/`login_manager` in `extensions.py` e seguire lo stesso schema per il limiter).

Sulla route `/login` in `routes/auth.py`:
```python
@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
    ...
```

Il limite va applicato per IP di default (comportamento standard di Flask-Limiter) — non serve altro, non implementare un sistema di lockout per-utente separato, è ridondante con questo e aggiunge complessità senza beneficio proporzionato per un'app di queste dimensioni.

## 2. `SECRET_KEY` non fissata — bug attivo con 2 worker gunicorn

`config.py`:
```python
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
```

Il fallback genera una chiave diversa per ogni worker gunicorn (`--workers 2` in `Procfile`/`render.yaml`), causando sessioni e token CSRF invalidati in modo intermittente a seconda di quale worker gestisce la richiesta.


**Questo non è un fix di codice, è configurazione**: generare una chiave fissa e impostarla come variabile d'ambiente `SECRET_KEY` su Render (Environment tab), non nel codice. Comando per generarla:

```bash
python -c "import secrets; print(secrets.token_hex(32))"

```
Il codice in `config.py` può restare com'è (il fallback va bene come rete di sicurezza per lo sviluppo locale senza `.env`), ma va segnalato chiaramente nel `.env.example` (se esiste, altrimenti nel `README`) che `SECRET_KEY` è obbligatoria in produzione. Se non esiste un `.env.example` nel progetto, valuta se crearlo — non è indispensabile per questa fix ma è buona norma.

## File coinvolti — Parte 2

Modifica:
- `requirements.txt` — `Flask-Limiter`
- `extensions.py` — inizializzazione limiter
- `main.py` — `limiter.init_app(app)`
- `routes/auth.py` — decorator su `/login`

Nessuna azione di codice per `SECRET_KEY`, solo configurazione su Render (comunicalo esplicitamente nel piano, non generare codice per questo punto).

---
Ho controllato un dettaglio prima di dare l'ok — e ne è uscito un problema serio, non nella logica della Parte 1 (quella è pulita), ma nella configurazione del Limiter in Parte 2. Due cose, entrambe da correggere prima dei diff.
🔴 default_limits si applica a TUTTE le route, non solo al login
pythonlimiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
Questo non limita solo /login — limita ogni singola richiesta di tutta l'app, a meno che una route non venga esplicitamente esentata con @limiter.exempt. Il tuo progetto è un'app server-rendered a pagina intera (non una SPA): ogni click di un operatore che naviga tra dashboard, giacenze, movimenti, entrate è una richiesta HTTP separata. 50 richieste/ora per un operatore attivo si esauriscono in pochi minuti di lavoro normale — dopo di che l'app smette letteralmente di rispondere a chiunque, con un errore 429, fino al reset dell'ora.
Il fix è togliere default_limits dall'istanza globale e mettere il limite solo sulla route di login, esattamente come già scritto nel resto del piano:
pythonlimiter = Limiter(key_func=get_remote_address)  # nessun default_limits
python@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
Così il rate limit esiste solo dove serve.
🔴 Nessun ProxyFix — il rate limit colpirebbe tutti gli utenti insieme, non il singolo attaccante
Ho controllato main.py/config.py/extensions.py: non c'è nessuna configurazione ProxyFix. Render mette l'app dietro un proxy interno — senza ProxyFix, request.remote_addr (quello che get_remote_address usa come chiave) restituisce l'IP del proxy di Render, che è lo stesso per tutte le richieste, indipendentemente da chi le fa davvero. Risultato pratico: il limite "5 tentativi ogni 15 minuti" verrebbe condiviso da tutti gli utenti del sito contemporaneamente, non per singolo IP reale. Basterebbe che una persona sbagli la password 5 volte per bloccare temporaneamente il login a tutti gli altri — un effetto collaterale peggiore del problema che si voleva risolvere.
Serve aggiungere il middleware in main.py, dentro create_app(), prima di restituire app:
pythonfrom werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
x_for=1 perché Render ha un solo hop di proxy davanti alla tua app — fidarsi di più hop di quelli reali aprirebbe la porta a spoofing dell'header X-Forwarded-For da parte di un client malintenzionato.

Verdetto: correggi questi due punti nel piano di Parte 2 (togli default_limits, aggiungi ProxyFix), il resto — Parte 1 compresa — è a posto così com'è. Per il resto via libera ai diff, procedi file per file come sempre.


