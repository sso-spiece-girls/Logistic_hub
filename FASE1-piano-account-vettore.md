# FASE 1 — Piano di estensione: Account Vettore con login e prenotazione per conto cliente

## Indice
1. [Analisi del contesto attuale](#1-analisi-del-contesto-attuale)
2. [Modello dati — modifiche proposte](#2-modello-dati--modifiche-proposte)
3. [Autenticazione e routing](#3-autenticazione-e-routing)
4. [Casi limite](#4-casi-limite)
5. [Domande aperte con proposta di risposta](#5-domande-aperte-con-proposta-di-risposta)

---

## 1. Analisi del contesto attuale

### Stato oggi (Feature 4, commit 0468ec1)

| Entità | Ruolo |
|--------|-------|
| `User` | Tabella `users`, 4 ruoli: `operatore`, `ufficio`, `admin`, `cliente`. Auth via Flask-Login. |
| `Vettore` | Tabella `vettori`, anagrafica pura (nome, partita_iva, telefono, email, attivo). **Nessun legame con User.** |
| `ClienteVettore` | Join table: `(cliente_id → users.id, vettore_id → vettori.id)`. UniqueConstraint su coppia. |
| `Prenotazione` | Ha `cliente_id` (FK → users.id), `vettore_id` (FK → vettori.id, nullable), `staff_user_id`. |

### Flussi attuali

- **Login** (`routes/auth.py`): se `role == "cliente"` → redirect a `/prenotazioni/calendario`. Altrimenti → dashboard.
- **Calendario/Prenota/Mie** (`routes/prenotazioni.py`): guard `current_user.role != "cliente"` → bloccano.
- **Cliente seleziona vettore** nel form di prenotazione: dropdown basato su `ClienteVettore`.
- **Admin crea prenotazione** (`admin_nuova_prenotazione`): può già selezionare `vettore_id` opzionalmente.
- **CRUD Vettore** (`routes/vettori.py`): solo admin.

---

## 2. Modello dati — modifiche proposte

### 2.1 Collegamento Vettore → User (opzionale, uno-a-uno)

**Scelta progettuale: `Vettore.user_id` (FK → users.id, nullable, unique)**

Due opzioni valutate:

| Opzione | Pro | Contro |
|---------|-----|--------|
| **A) `Vettore.user_id` (FK, nullable, unique)** | L'anagrafica vettore resta autonoma. Utente con ruolo "vettore" esiste separatamente. I vettori senza account restano invariati. Un account = un vettore (unique). | Richiede nuovo ruolo `"vettore"` in User (ma serve comunque). |
| **B) Solo `role="vettore"` su User, nessuna FK** | Login diretto. Semplice. | L'anagrafica Vettore (nome, p.iva, ecc.) sarebbe duplicata in User oppure servirebbe una tabella separata. Impossibile avere più utenti per lo stesso vettore in futuro. Non compatibile col modello dati attuale (`Prenotazione.vettore_id` punta a `Vettore.id`, non a `User.id`). |

**Scelta: Opzione A** — è più coerente con l'esistente perché:
- `Vettore` è già un modello separato con i propri dati anagrafici
- La `Prenotazione.vettore_id` punta già a `Vettore.id`
- Il requisito "non tutti i vettori hanno un account" si traduce naturalmente in `user_id` nullable
- `unique=True` garantisce che un account gestisca un solo Vettore

Modifica in `models.py`:

```python
class Vettore(db.Model):
    __tablename__ = "vettori"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)
    partita_iva = db.Column(db.String(20), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    attivo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # NUOVO:
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, unique=True)

    # NUOVA RELAZIONE:
    user = db.relationship("User", foreign_keys=[user_id], back_populates="vettore")
```

In `User`:

```python
class User(UserMixin, db.Model):
    # ... campi esistenti ...
    # NUOVA RELAZIONE (opzionale, uno-a-uno):
    vettore = db.relationship("Vettore", back_populates="user", uselist=False)
```

**Niente cascade delete**: se si elimina l'User, `Vettore.user_id` va impostato a `NULL` (l'anagrafica vettore sopravvive), non deve eliminare il Vettore.

### 2.2 Nuovo ruolo `"vettore"` in User.role

Anche se il collegamento è via FK, il sistema di autenticazione ha bisogno di un ruolo per:
- Decidere il redirect post-login (vettore → pagina selezione cliente, non calendario, non dashboard)
- Il template `base.html` deve sapere se mostrare la sidebar operativa o quella cliente
- I decoratori devono poter riconoscere un utente vettore

Modifiche:

**`User.role_label`**:
```python
@property
def role_label(self):
    labels = {
        "operatore": "Operatore", "ufficio": "Ufficio",
        "admin": "Admin", "cliente": "Cliente",
        "vettore": "Vettore",  # NUOVO
    }
    return labels.get(self.role, self.role)
```

**`UserForm.role.choices`** in `forms.py`:
```python
role = SelectField("Ruolo", choices=[
    ("operatore", "Operatore"),
    ("ufficio", "Ufficio"),
    ("admin", "Admin"),
    ("cliente", "Cliente"),
    ("vettore", "Vettore"),  # NUOVO
], validators=[DataRequired()])
```

**Login redirect** (`routes/auth.py`):
```python
if user.role == "cliente":
    return redirect(next_page or url_for("prenotazioni.calendario"))
if user.role == "vettore":               # NUOVO
    return redirect(next_page or url_for("vettori.seleziona_cliente"))
return redirect(next_page or url_for("dashboard.index"))
```

### 2.3 "Cliente attivo" in sessione — nessuna tabella

Il cliente per cui il vettore sta prenotando va tenuto in `session` Flask, non in DB:

```python
# Alla selezione:
session["vettore_cliente_id"] = cliente_id
session["vettore_cliente_nome"] = cliente_username  # per la UI

# Alla verifica:
cliente_id = session.get("vettore_cliente_id")
if not cliente_id:
    flash("Seleziona un cliente prima di prenotare.", "warning")
    return redirect(url_for("vettori.seleziona_cliente"))
```

Motivazione:
- Dato temporaneo legato alla sessione di navigazione
- Non serve persistenza oltre il logout o lo switch manuale
- Semplice, già usato da Flask per cose analoghe
- Se la sessione scade, il vettore deve rifare login e riscegliere — comportamento corretto

---

## 3. Autenticazione e routing

### 3.1 Nuovo decoratore `vettore_required`

In `core/auth_decorators.py`:

```python
def vettore_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "vettore":
            flash("Accesso riservato ai vettori.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated
```

Usato sulle route del blueprint vettore. Nota: il controllo sull'esistenza del Vettore collegato (`Vettore.query.filter_by(user_id=current_user.id, attivo=True).first()`) va fatto dentro ogni route che ne ha bisogno, non nel decoratore (altrimenti il decoratore farebbe query al DB a ogni chiamata).

### 3.2 Nuova route: selezione cliente attivo

Nuovo blueprint (o estensione di `routes/vettori.py`) — propongo un nuovo blueprint separato `routes/vettore_portale.py` per non confondere con le route admin di gestione vettori. Ma per minimizzare i file nuovi, si può estendere `routes/prenotazioni.py` con un nuovo gruppo di route `vettore_` oppure creare un piccolo blueprint dedicato.

**Proposta: creare `routes/vettore_portale.py`** (o potrebbe stare in un blueprint separato, es. `routes/vettore_bp.py`). Contiene:

```python
# routes/vettore_portale.py
vettore_portale = Blueprint("vettore_portale", __name__, url_prefix="/vettore")

@vettore_portale.route("/seleziona-cliente", methods=["GET", "POST"])
@login_required
@vettore_required
def seleziona_cliente():
    """Menù di selezione cliente attivo per vettori multi-cliente."""
    # Trova il record Vettore collegato all'account corrente
    vettore = Vettore.query.filter_by(user_id=current_user.id, attivo=True).first()
    if not vettore:
        flash("Il tuo account non è collegato a nessun vettore attivo. Contatta l'amministratore.", "error")
        return redirect(url_for("auth.logout"))
    
    # Trova i clienti associati a questo vettore
    associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
    if not associazioni:
        flash("Nessun cliente associato al tuo account. Contatta l'amministratore.", "error")
        return redirect(url_for("auth.logout"))
    
    clienti_ids = [cv.cliente_id for cv in associazioni]
    clienti = User.query.filter(User.id.in_(clienti_ids), User.is_active == True).order_by(User.username).all()
    
    if not clienti:
        flash("Nessun cliente attivo associato al tuo account.", "error")
        return redirect(url_for("auth.logout"))
    
    # Se un solo cliente, salta la selezione
    if len(clienti) == 1:
        session["vettore_cliente_id"] = clienti[0].id
        session["vettore_cliente_nome"] = clienti[0].username
        flash(f"Stai prenotando per conto di: {clienti[0].username}", "info")
        return redirect(url_for("prenotazioni.calendario"))
    
    if request.method == "POST":
        cliente_id = request.form.get("cliente_id", type=int)
        if cliente_id in [c.id for c in clienti]:
            session["vettore_cliente_id"] = cliente_id
            session["vettore_cliente_nome"] = next(c.username for c in clienti if c.id == cliente_id)
            flash(f"Stai prenotando per conto di: {session['vettore_cliente_nome']}", "info")
            return redirect(url_for("prenotazioni.calendario"))
        flash("Selezione non valida.", "error")
    
    return render_template("vettore/seleziona_cliente.html", clienti=clienti)
```

**Nuova route per cambiare cliente**:
```python
@vettore_portale.route("/cambia-cliente")
@login_required
@vettore_required
def cambia_cliente():
    session.pop("vettore_cliente_id", None)
    session.pop("vettore_cliente_nome", None)
    return redirect(url_for("vettore_portale.seleziona_cliente"))
```

### 3.3 Route esistenti: adattamento per vettore

#### `calendario()` — permettere anche vettore

Modificare il guard:
```python
# PRIMA:
if current_user.role != "cliente":
    flash("Accesso riservato ai clienti.", "error")
    return redirect(url_for("dashboard.index"))

# DOPO:
if current_user.role not in ("cliente", "vettore"):
    flash("Accesso riservato.", "error")
    return redirect(url_for("dashboard.index"))
```

Determinare `cliente_id` per query:
```python
if current_user.role == "vettore":
    cliente_id = session.get("vettore_cliente_id")
    if not cliente_id:
        flash("Seleziona un cliente prima di prenotare.", "warning")
        return redirect(url_for("vettore_portale.seleziona_cliente"))
else:
    cliente_id = current_user.id
```

Poi usare `cliente_id` al posto di `current_user.id` nelle query per:
- Tipologie materiale: `TipologiaMateriale.query.filter_by(cliente_id=cliente_id, attivo=True)`
- Magazzini associati: `_magazzini_per_cliente(cliente_id)`
- Vettori associati: `ClienteVettore.query.filter_by(cliente_id=cliente_id)`

#### `prenota()` — logica analoga

Stessa modifica guard. Determinare `cliente_id` come sopra. In fase di creazione della `Prenotazione`:

```python
p = Prenotazione(
    cliente_id=cliente_id,        # ← cliente per cui si prenota
    vettore_id=vettore.id,        # ← vettore loggato (SOLO se role="vettore")
    # ... altri campi invariati ...
)
```

Dove `vettore = Vettore.query.filter_by(user_id=current_user.id).first()`. Se il vettore è collegato, il suo `vettore_id` va sempre inserito.

**Log attività**: quando un vettore prenota, `log_activity` userà `current_user.id` (corretto: l'utente che ha fatto l'azione).

#### `mie()` — vista vettore separata

Per il vettore, "le mie prenotazioni" = filtrate per `vettore_id` (il suo record Vettore), non per `cliente_id`.

Nuova route (in `prenotazioni.py` o in `vettore_portale.py`):
```python
@bp.route("/vettore/mie")
@login_required
@vettore_required
def vettore_mie():
    vettore = Vettore.query.filter_by(user_id=current_user.id).first()
    if not vettore:
        flash("Account vettore non configurato correttamente.", "error")
        return redirect(url_for("dashboard.index"))
    prenotazioni = Prenotazione.query.options(
        db.joinedload(Prenotazione.tipologia_materiale),
        db.joinedload(Prenotazione.cliente),
    ).filter_by(vettore_id=vettore.id).order_by(
        Prenotazione.data.desc(), Prenotazione.ora_inizio.desc()
    ).all()
    return render_template("prenotazioni/mie_prenotazioni.html", prenotazioni=prenotazioni)
```

**Template**: si può riusare `mie_prenotazioni.html` così com'è, perché mostra solo "Le mie prenotazioni" con colonne generiche. Non fa riferimento a `current_user` nel template (solo a `p`). Per differenziare il titolo, si può passare un parametro extra alla view o al template. Proposta: modificare minimamente il template per mostrare "Le mie prenotazioni" come titolo indipendentemente dal ruolo. Per i vettori si potrebbe aggiungere una colonna "Cliente" (già presente in `p.cliente` tramite eager load), ma per ora il template base va bene.

**Alternativa**: se si vuole mostrare il cliente per cui è stata fatta la prenotazione (utile per vettori multi-cliente), aggiungere colonna "Cliente" al template. Ma va fatto senza rompere la vista cliente. Si può aggiungere condizionalmente:
```html
{% if show_cliente_column %}
<th>Cliente</th>
{% endif %}
```
Non necessario per ora.

### 3.4 Template base e navigazione

Nella sidebar di `base.html`, aggiungere sezione per vettore:

```html
{% elif current_user.role == 'vettore' %}
<div class="sidebar-section">
    <div class="sidebar-label">PRENOTAZIONI</div>
    <a href="/prenotazioni/calendario" class="sidebar-item ...">
        Calendario
    </a>
    <a href="/prenotazioni/vettore/mie" class="sidebar-item ...">
        Le mie prenotazioni
    </a>
    <a href="/vettore/cambia-cliente" class="sidebar-item ...">
        Cambia cliente
    </a>
</div>
```

### 3.5 Gestione account admin

La creazione di un account vettore va fatta dall'admin:
- **Opzione A**: Estendere `UserForm` per aggiungere un campo `vettore_id` quando `role == "vettore"` (select dei Vettore esistenti)
- **Opzione B**: Estendere `VettoreForm` per aggiungere un campo per creare/collegare un utente

**Scelta: Opzione A** — più coerente: l'admin va in "Gestione Utenti" e crea un utente con ruolo "Vettore", selezionando da un dropdown il record Vettore da collegare.

Dettaglio implementativo: quando `role == "vettore"`, il form mostra un campo select con i Vettori senza account (`Vettore.query.filter_by(user_id=None, attivo=True)`). Dopo la creazione dell'User, si imposta `Vettore.user_id = nuovo_utente.id`.

**Assunzione dichiarata**: solo l'admin può creare account vettore. Il cliente non può "invitare" un vettore — ma può già associare vettori esistenti (anagrafica) tramite la pagina di associazioni admin.

---

## 4. Casi limite

### 4.1 Vettore con account ma zero clienti associati

**Scenario**: un vettore ha un User attivo (role="vettore") collegato al suo record Vettore, ma `ClienteVettore` non ha nessuna riga per quel vettore.

**Comportamento**: dopo il login, la route `seleziona_cliente` fa la query:
```python
associazioni = ClienteVettore.query.filter_by(vettore_id=vettore.id).all()
if not associazioni:
    flash("Nessun cliente associato al tuo account. Contatta l'amministratore.", "error")
    return redirect(url_for("auth.logout"))
```
Il vettore viene reindirizzato al logout (e può fare login di nuovo, ma si ripete). Questo è intenzionale: senza clienti, non può fare nulla.

**Miglioramento possibile**: mostrare una pagina informativa invece di fare logout forzato, ma per ora il redirect al logout è accettabile (messaggio chiaro all'utente).

**Test di accettazione**:
- Creare User con role="vettore", collegato a Vettore senza ClienteVettore
- Login → redirect a selezione cliente → flash errore → redirect logout

### 4.2 Admin disabilita l'account di un vettore che ha prenotazioni attive

**Scenario**: `User.is_active = False` per un vettore con prenotazioni in stato "in_attesa" o "confermata".

**Comportamento**:
- Nuovo login bloccato: il codice `login()` già controlla `if not user.is_active: flash(...)`
- Sessione attiva: Flask-Login non invalida le sessioni attive quando is_active cambia. Il vettore potrebbe continuare a usare il sistema fino al logout o scadenza sessione.

**Soluzione**: aggiungere un controllo `current_user.is_active` nelle route critiche:
```python
if current_user.role == "vettore" and not current_user.is_active:
    flash("Account disabilitato.", "error")
    return redirect(url_for("auth.logout"))
```
Oppure in un `before_request` handler. Ma è overkill — l'admin di solito disabilita e poi comunica al vettore. Accettiamo che la sessione attiva rimanga fino al logout. Le prenotazioni esistenti restano in DB (non vengono cancellate).

**Cosa NON fare**: non eliminare le prenotazioni esistenti. Il campo `Prenotazione.vettore_id` è solo informativo.

### 4.3 Vettore prova ad accedere a `/prenotazioni/calendario` senza cliente attivo

**Scenario**: vettore loggato, multi-cliente, accede direttamente via URL a `/calendario` senza passare dalla selezione.

**Comportamento**: la route `calendario()` controlla:
```python
if current_user.role == "vettore":
    cliente_id = session.get("vettore_cliente_id")
    if not cliente_id:
        flash("Seleziona un cliente prima di prenotare.", "warning")
        return redirect(url_for("vettore_portale.seleziona_cliente"))
```
Reindirizza alla pagina di selezione. OK.

### 4.4 Stesso vettore associato allo stesso cliente due volte

**Scenario**: un errore admin o un tentativo di creare un duplicato in `ClienteVettore`.

**Comportamento**: già gestito dal `UniqueConstraint("cliente_id", "vettore_id")` su `ClienteVettore`. Nessuna modifica necessaria. La route `salva_associazioni` usa `set()` per evitare duplicati lato applicazione, ma il constraint DB è la garanzia finale.

### 4.5 Admin crea prenotazione manuale per un cliente con vettore (invariato)

**Scenario**: Feature 1, `admin_nuova_prenotazione` — admin seleziona un vettore dal dropdown.

**Comportamento**: nessuna modifica. Il campo `vettore_id` è già presente e opzionale. L'unica differenza: ora il dropdown potrebbe mostrare anche vettori con account (non cambia nulla, la selezione è la stessa).

### 4.6 Vettore senza record Vettore (user_id non collegato)

**Scenario**: utente con `role="vettore"` ma nessun Vettore ha `user_id = current_user.id`.

**Comportamento**: la route `seleziona_cliente` fa:
```python
vettore = Vettore.query.filter_by(user_id=current_user.id, attivo=True).first()
if not vettore:
    flash("Il tuo account non è collegato a nessun vettore attivo.", "error")
    return redirect(url_for("auth.logout"))
```
Blocca subito.

**Prevenzione**: l'admin in fase di creazione deve obbligatoriamente selezionare un Vettore. Il form admin dovrebbe validare che se `role == "vettore"`, il campo `vettore_id` sia presente.

### 4.7 Vettore disattivato (`Vettore.attivo = False`)

**Scenario**: l'admin disattiva il record Vettore (non l'User), ma l'User rimane attivo.

**Comportamento**: il controllo `Vettore.attivo == True` in `seleziona_cliente` blocca. Il vettore non può selezionare clienti né prenotare.

**Implicazione**: serve un controllo analogo anche in `calendario()` e `prenota()` per sicurezza, anche se il flusso normale passa sempre da `seleziona_cliente` prima.

### 4.8 Vettore con cliente selezionato, ma il cliente viene disattivato

**Scenario**: admin imposta `User.is_active = False` per un cliente che era stato selezionato dal vettore.

**Comportamento**: `session["vettore_cliente_id"]` contiene ancora l'ID. Le route che fanno query (tipologie, magazzini, vincoli) potrebbero restituire risultati vuoti. Il vettore vedrebbe "nessuna tipologia configurata" ecc.

**Soluzione**: aggiungere una validità del cliente selezionato nelle route critiche:
```python
cliente = db.session.get(User, cliente_id)
if not cliente or not cliente.is_active or cliente.role != "cliente":
    flash("Il cliente selezionato non è più disponibile.", "warning")
    session.pop("vettore_cliente_id", None)
    return redirect(url_for("vettore_portale.seleziona_cliente"))
```

---

## 5. Domande aperte con proposta di risposta

### Q1: Un vettore può anche essere lui stesso un cliente (doppio ruolo)?

**Proposta**: **No, sono sempre entità distinte.** 
Un singolo User non può avere due ruoli contemporaneamente. Se una persona giuridica è sia cliente che vettore, servono due account separati. Questo è allineato col sistema attuale dove ruolo è una stringa singola. Separare i ruoli eviterebbe:
- Confusione sulla sidebar (cliente vede booking, operativo vede dashboard)
- Problemi di autorizzazione (un vettore non dovrebbe vedere i dati di altri clienti)
- Complessità nelle route (bisognerebbe distinguere in quale "modalità" l'utente sta operando)

**Nota**: nulla vieta in futuro di permettere a un vettore di avere anche `role="cliente"` in un account separato con la stessa email — ma non è un requisito ora.

### Q2: Se un vettore ha un solo cliente associato, la UI salta la selezione o la mostra comunque?

**Proposta**: **Salta la selezione e reindirizza direttamente al calendario.**
Il requisito ("se il vettore ha un solo cliente collegato, salta la selezione") è esplicito. La logica:
1. Dopo login, redirect a `/vettore/seleziona-cliente`
2. Query: `ClienteVettore` per il vettore → 1 risultato
3. Auto-imposta `session["vettore_cliente_id"]` e redirect a `/prenotazioni/calendario`
4. Flash message: "Stai prenotando per conto di: NomeCliente"

Il vettore vedrà comunque l'opzione "Cambia cliente" nella sidebar per cambiare (utile se in futuro vengono aggiunti altri clienti).

### Q3: Chi crea l'account vettore? Solo admin? Il cliente può invitare?

**Proposta**: **Solo admin crea account vettore.**
Assunzione esplicita per questa fase. Motivi:
- La creazione di un account coinvolge dati sensibili (password, username)
- Il Vettore è un'entità anagrafica gestita dall'admin (CRUD già esiste)
- Il cliente può già associare vettori esistenti (anagrafica) al proprio profilo tramite admin
- Estendere il form di creazione utente con un campo "Vettore" select è semplice

**Futuro**: si potrebbe aggiungere un flusso di "invito" dal cliente, ma è fuori scope.

### Q4: Come gestire la navbar/sidebar per il ruolo vettore?

**Proposta**: Il vettore vede solo:
- Una sidebar simile a quella del cliente (prenotazioni, mie prenotazioni, cambia cliente)
- Niente dashboard operativa, niente sezione amministrativa
- Nel dropdown utente: mostra "Vettore: NomeAzienda" (dal record Vettore associato)
- Il breadcrumb e la navigazione restano minimali

### Q5: Un account vettore può essere usato da più persone (es. più autisti della stessa azienda)?

**Proposta**: **No, per ora un account = un utente.**
Se un'azienda vettore ha bisogno di più login, si creano più User con role="vettore", tutti collegati a Vettore diversi (uno per autista, oppure con nomi tipo "Trasporti Rossi - Mario", "Trasporti Rossi - Luigi"). Ogni autista vede solo le proprie prenotazioni perché il filtro è su `vettore_id`.

Questo vincolo deriva da `Vettore.user_id = unique`: un account può gestire un solo Vettore, e un Vettore può avere un solo account.

**In futuro**: se serve un Vettore con più account, si può togliere il unique constraint e permettere a più User di puntare allo stesso Vettore. Ma allora bisognerebbe distinguere chi ha creato quale prenotazione — forse aggiungendo un campo `inserito_da_vettore_user_id` a Prenotazione. Non è necessario ora.

---

## Riepilogo modifiche ai file

| File | Modifica |
|------|----------|
| `models.py` | `User`: aggiungere relazione `vettore` backref. `Vettore`: aggiungere `user_id` (FK, nullable, unique) e relazione `user`. |
| `core/auth_decorators.py` | Aggiungere `vettore_required` decorator. |
| `routes/auth.py` | Aggiungere redirect post-login per ruolo "vettore". |
| `routes/vettori.py` | *(nessuna modifica alle route CRUD admin)* |
| `routes/prenotazioni.py` | `calendario()`: permettere ruolo vettore, usare `cliente_id` da sessione. `prenota()`: idem, impostare `vettore_id`. `mie()`: invariata per cliente. Nuova route `vettore_mie()`. |
| `routes/vettore_portale.py` (NUOVO) | Blueprint vettore: selezione cliente, cambio cliente. |
| `forms.py` | `UserForm.role.choices`: aggiungere "vettore". Nuovo campo `vettore_id` nel form utenti. |
| `templates/base.html` | Sidebar: aggiungere sezione per ruolo vettore. |
| `templates/vettore/seleziona_cliente.html` (NUOVO) | Pagina di selezione cliente attivo. |
| `templates/prenotazioni/mie_prenotazioni.html` | Opzionale: aggiungere colonna "Cliente" condizionale per vettore. |
| `main.py` | Registrare nuovo blueprint `vettore_portale`. |

---

*Fine documento Fase 1. Attendere conferma prima di procedere con Fase 2 (implementazione).*
