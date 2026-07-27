# FASE 1 — Piano di estensione modello dati

## Logistic Hub — 8 nuove feature

**Stato:** Bozza per conferma  
**Data:** 2026-07-24  
**Nota:** Non modificare codice. Attendere conferma del documento prima di passare alla Fase 2 (implementazione).

---

## Stato attuale (rilevato dal codice)

- **Database:** SQLAlchemy ORM, `db.create_all()` all'avvio. **Nessun Alembic/Flask-Migrate.** Le migration sono manuali via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `main.py:_migrate_prenotazioni()`.
- **Modelli esistenti coinvolti:**
  - `Prenotazione` — la tabella centrale
  - `SlotOrario` — regole fascia oraria (giorno, inizio, fine, durata, capienza)
  - `MagazzinoCapienza` — magazzino con capienza contemporanea
  - `TipologiaMateriale` — tipologia per cliente (nome, durata)
  - `User` — utenti (admin, operatore, cliente)
- **Cliente**: modellato come `User(role="cliente")`; i dati anagrafici sono gestiti tramite plugin esterni in `clients/`, non nel DB.
- **Prenotazione.stato**: `in_attesa`, `confermata`, `rifiutata`, `ingresso_registrato`, `ingresso_rifiutato`, `annullata`, `scaduta`
- **Capienza**: controllo per magazzino specifico (già presente in `approva()`)
- **TipologiaMateriale** esiste già ed è per-cliente, con durata variabile

---

## Riepilogo modifiche modello dati

| Feature | Nuova tabella | Nuovi campi su tabella esistente | Nuove relazioni |
|---------|:---:|:---:|:---:|
| 1) Inserimento manuale staff | — | `Prenotazione.inserita_da_staff`, `Prenotazione.staff_user_id` | FK → User |
| 2) Magazzini associati al cliente | `cliente_magazzini` | — | M2M Cliente ↔ MagazzinoCapienza |
| 3) Tipologia prodotto generica | — | Già esistente (`TipologiaMateriale`, `Prenotazione.tipologia_materiale_id`) | Nessuna |
| 4) Vettore/trasportatore | `vettori`, `cliente_vettori` | `Prenotazione.vettore_id` | FK → Vettore |
| 5) Vincolo targa | — | — | Vincolo applicativo |
| 6) Durata slot per magazzino | — | `MagazzinoCapienza.durata_slot_minuti` | — |
| 7) Motivo rifiuto visibile | — | Già esistente (`Prenotazione.note_operatore` usato per il motivo) | — |
| 8) Doppia prenotazione | — | — | Vincolo applicativo |

---

## Feature 1 — Inserimento manuale ingressi da admin/operatore

### Modifiche al modello

**Tabella `prenotazioni`** — 2 nuovi campi:

```python
# Nuovo campo: flag che indica prenotazione creata da staff, non dal cliente
inserita_da_staff = db.Column(db.Boolean, default=False, nullable=False)

# Nuovo campo: chi l'ha creata (staff user)
staff_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

# Relazione
staff_user = db.relationship("User", foreign_keys=[staff_user_id])
```

### SQL migration

```sql
ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS inserita_da_staff BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS staff_user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS ix_prenotazioni_staff_user ON prenotazioni (staff_user_id);
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 1.1 | Staff crea prenotazione su slot già occupato | Il controllo capienza/race condition esistenti (`with_for_update`) devono rimanere attivi. Lo staff NON bypassa i controlli di capienza e occupazione slot. |
| 1.2 | Staff crea su data passata (es. "recupero" ingresso avvenuto ieri) | Deve essere permesso? Proposta: **sì**, data >= oggi per default ma admin può inserire date passate (serve un parametro esplicito per casi di backfill). |
| 1.3 | Staff crea senza tipologia materiale | La tipologia è obbligatoria via FK attuale. Proposta: si lascia obbligatoria, lo staff seleziona una tipologia valida per quel cliente. |
| 1.4 | Staff crea per cliente che non ha tipologie attive | Bloccare: servono tipologie configurate. |
| 1.5 | Notifica al cliente | Proposta: sì, stessa notifica di una prenotazione normale ("è stata creata una prenotazione per tuo conto"). |
| 1.6 | QR code generato? | Proposta: **sì**, la prenotazione staff genera QR come una normale, e passa per lo stesso flusso di verifica. Il QR è necessario per tracciare l'effettivo ingresso. |

---

## Feature 2 — Magazzini associati al cliente (vincolo di scelta)

### Modifiche al modello

**Nuova tabella `cliente_magazzini`** (tabella di associazione M2M):

```python
class ClienteMagazzino(db.Model):
    __tablename__ = "cliente_magazzini"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    magazzino_id = db.Column(db.Integer, db.ForeignKey("magazzini_capienza.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cliente = db.relationship("User", foreign_keys=[cliente_id])
    magazzino = db.relationship("MagazzinoCapienza", foreign_keys=[magazzino_id])

    __table_args__ = (
        db.UniqueConstraint("cliente_id", "magazzino_id", name="uq_cliente_magazzino"),
    )
```

**Nessuna modifica a `Prenotazione`** (il campo `magazzino` esiste già, è una stringa).

**Modifica al modello `User`** (o via query dedicata): relazione per accedere ai magazzini associati.

```python
# Su User (opzionale, meglio query diretta):
# magazzini_associati = db.relationship("ClienteMagazzino", backref="cliente", lazy="dynamic",
#                                        foreign_keys="ClienteMagazzino.cliente_id")
```

### SQL migration

```sql
CREATE TABLE IF NOT EXISTS cliente_magazzini (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES users(id),
    magazzino_id INTEGER NOT NULL REFERENCES magazzini_capienza(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (cliente_id, magazzino_id)
);
CREATE INDEX IF NOT EXISTS ix_cliente_magazzini_cliente ON cliente_magazzini (cliente_id);
CREATE INDEX IF NOT EXISTS ix_cliente_magazzini_magazzino ON cliente_magazzini (magazzino_id);
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 2.1 | Cliente storico senza magazzini associati | **Fallback**: mostrare TUTTI i magazzini (comportamento attuale), con un messaggio "Nessuna limitazione configurata" — per non bloccare i clienti esistenti. In futuro si potrà rendere obbligatoria l'associazione. |
| 2.2 | Admin elimina associazione magazzino-cliente mentre ci sono prenotazioni future | Bloccare l'eliminazione se esistono prenotazioni attive (in_attesa, confermata) su quel magazzino per quel cliente. |
| 2.3 | Admin associa magazzino che non esiste più in MagazzinoCapienza | Usare FK → `magazzini_capienza.id` impedisce orfani. |
| 2.4 | Cliente con associazioni: il selettore mostra solo quelli associati | Modificare il filtro: `MagazzinoCapienza.query.join(ClienteMagazzino).filter(ClienteMagazzino.cliente_id == current_user.id)`. |
| 2.5 | Selettore per admin/operatore nelle viste staff | L'admin/operatore deve comunque vedere tutti i magazzini per assegnazione manuale. |

---

## Feature 3 — Tipologia prodotto (campo generico riusabile)

### Stato attuale

Il modello `TipologiaMateriale` ESISTE già ed è esattamente quello che serve:

```python
class TipologiaMateriale(db.Model):
    __tablename__ = "tipologie_materiale"
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    nome = db.Column(db.String(100), nullable=False)
    durata_minuti = db.Column(db.Integer, nullable=False, default=60)
    attivo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

`Prenotazione` ha già `tipologia_materiale_id` FK.

**Non servono modifiche al modello.** Servono solo:
- Seed dati per Celtex con: Bobine, Prodotto Finito (Celtex), Prodotto Finito (ZVG), Rientri
- Lato UI: nel forms di creazione/modifica cliente, aggiungere una sezione visibile per configurare le tipologie (è già presente in `users_form.html` per i clienti)

### Modifiche proposte

- Rinominare il campo `durata_minuti` → è già generico, nessun rename necessario
- Aggiungere un campo `ordinamento` (opzionale) per ordinare le tipologie nel selettore:

```python
ordinamento = db.Column(db.Integer, default=0)
```

### SQL migration

```sql
ALTER TABLE tipologie_materiale ADD COLUMN IF NOT EXISTS ordinamento INTEGER DEFAULT 0;
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 3.1 | Cliente non Celtex vuole configurare tipologie diverse | Già supportato: TipologiaMateriale è per-cliente. |
| 3.2 | "Rientri" ha durata fissa 45 min | La durata è già un attributo della tipologia. Si setta a 45 min per "Rientri" al seed. |
| 3.3 | Admin modifica durata tipologia dopo che sono state fatte prenotazioni | La durata è letta al momento della creazione (già copiata in `Prenotazione.ora_inizio/ora_fine`). Modificare la durata della tipologia NON impatta le prenotazioni esistenti. |
| 3.4 | Stessa tipologia su più clienti | Ogni tipologia è per-cliente. Se servono tipologie condivise, si crea una istanza per ogni cliente. OK. |

---

## Feature 4 — Vettore/trasportatore collegato al cliente

### Modifiche al modello

**Nuova tabella `vettori`:**

```python
class Vettore(db.Model):
    __tablename__ = "vettori"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    partita_iva = db.Column(db.String(20), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Vettore {self.nome}>"
```

**Nuova tabella `cliente_vettori`** (M2M tra Vettore e User cliente):

```python
class ClienteVettore(db.Model):
    __tablename__ = "cliente_vettori"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    vettore_id = db.Column(db.Integer, db.ForeignKey("vettori.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cliente = db.relationship("User", foreign_keys=[cliente_id])
    vettore = db.relationship("Vettore", foreign_keys=[vettore_id])

    __table_args__ = (
        db.UniqueConstraint("cliente_id", "vettore_id", name="uq_cliente_vettore"),
    )
```

**Tabella `prenotazioni`** — 1 nuovo campo:

```python
vettore_id = db.Column(db.Integer, db.ForeignKey("vettori.id"), nullable=True, index=True)

# Relazione
vettore = db.relationship("Vettore", foreign_keys=[vettore_id])
```

### SQL migration

```sql
CREATE TABLE IF NOT EXISTS vettori (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    partita_iva VARCHAR(20),
    telefono VARCHAR(30),
    email VARCHAR(120),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cliente_vettori (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES users(id),
    vettore_id INTEGER NOT NULL REFERENCES vettori(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (cliente_id, vettore_id)
);

CREATE INDEX IF NOT EXISTS ix_cliente_vettori_cliente ON cliente_vettori (cliente_id);
CREATE INDEX IF NOT EXISTS ix_cliente_vettori_vettore ON cliente_vettori (vettore_id);

ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS vettore_id INTEGER REFERENCES vettori(id);
CREATE INDEX IF NOT EXISTS ix_prenotazioni_vettore ON prenotazioni (vettore_id);
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 4.1 | Stesso vettore lavora per più clienti | M2M lo permette: un Vettore può essere associato a più Clienti. |
| 4.2 | Cliente prenota e vuole selezionare un vettore | Il selettore mostra solo i vettori associati al cliente loggato. |
| 4.3 | Vettore senza account (terzo) | Il vettore non ha login. La prenotazione è fatta dal cliente o dallo staff, indicando quale vettore si presenterà. |
| 4.4 | Admin cancella vettore con prenotazioni attive | Bloccare se ci sono prenotazioni in stato attivo collegate. |
| 4.5 | Vettore non specificato (cliente si presenta da solo) | `vettore_id` nullable. Compatibile con prenotazioni esistenti. |
| 4.6 | Cliente storico: prenotazioni vecchie senza vettore | OK, `vettore_id` è nullable. |

---

## Feature 5 — Vincolo targa: una prenotazione per targa al giorno

### Modifiche al modello

**Nessuna.** È un vincolo applicativo lato validazione, non un vincolo di database (perché l'eccezione "trasferimento" è condizionale).

### Logica di validazione (da implementare in Fase 2)

```
Se tipo != "trasferimento":
    esistenti = Prenotazione.query.filter(
        Prenotazione.targa == targa_inserita,
        Prenotazione.data == data_prenotazione,
        Prenotazione.stato.in_(STATI_ATTIVI),
        Prenotazione.id != id_corrente (se modifica),
    ).count()
    if esistenti > 0:
        flash: "La targa X ha già una prenotazione per questa data."
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 5.1 | Stessa targa, stesso giorno, magazzino diverso | Bloccare comunque (il vincolo è su tutta l'azienda, non per magazzino). |
| 5.2 | Trasferimento: stessa targa due slot stesso giorno | Permesso (es. Colle 1 → Colle 3). |
| 5.3 | Targa vuota/null | `targa` è già obbligatoria (`DataRequired`). |
| 5.4 | Controllo in fase di approvazione admin | Va rifatto in `approva()`: tra approvazione e creazione potrebbe essere stata creata un'altra prenotazione con la stessa targa. |

---

## Feature 6 — Durata slot variabile per magazzino

### Modifiche al modello

**Tabella `magazzini_capienza`** — 1 nuovo campo:

```python
# Nuovo campo: durata default per questo magazzino (minuti)
durata_slot_minuti = db.Column(db.Integer, nullable=False, default=30)
```

### SQL migration

```sql
ALTER TABLE magazzini_capienza ADD COLUMN IF NOT EXISTS durata_slot_minuti INTEGER NOT NULL DEFAULT 30;
```

### Aggiornamento dati esistenti

```sql
UPDATE magazzini_capienza SET durata_slot_minuti = 30 WHERE magazzino = 'Colle 1';
UPDATE magazzini_capienza SET durata_slot_minuti = 45 WHERE magazzino IN ('Colle 3', 'Colle 4');
```

### Logica di determinazione durata slot

```
def durata_effettiva(prenotazione):
    """Restituisce la durata in minuti per una prenotazione."""
    durata_tipologia = prenotazione.tipologia_materiale.durata_minuti if prenotazione.tipologia_materiale else None
    durata_magazzino = prenotazione.magazzino.durata_slot_minuti if prenotazione.magazzino else None  # Dal MagazzinoCapienza

    if durata_tipologia and durata_tipologia == 45 and prenotazione.tipologia_materiale.nome == "Rientri":
        # "Rientri" ha durata fissa 45 min → sovrascrive
        return 45

    if durata_magazzino:
        return durata_magazzino

    return durata_tipologia or 60  # fallback
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 6.1 | "Rientri" (45 min) su Colle 1 (30 min) | **Vince la tipologia** — "Rientri" è un'eccezione esplicita con durata fissa 45 min. La durata del magazzino è la durata *base*; la tipologia *sovrascrive* quando è un caso speciale come Rientri. |
| 6.2 | Altre tipologie su Colle 1 | Usare `durata_slot_minuti` del magazzino come riferimento, ma la durata effettiva viene dalla tipologia. Servono regole chiare. |
| 6.3 | Magazzino senza durata configurata | Fallback a `durata_minuti` dello SlotOrario (es. 60 min). |
| 6.4 | Cliente prenota senza magazzino (raro) | Usare durata tipologia. |

**Nota:** La griglia slot in `_slot_disponibili()` usa `regola.durata_minuti` (dello SlotOrario). Con durate variabili per magazzino/tipologia, la griglia dovrà usare un passo fisso minimo (es. 15 min) e la durata effettiva sarà data dalla combinazione magazzino+tipologia al momento della prenotazione. Questo è un impatto architetturale non banale da discutere.

---

## Feature 7 — Motivo del rifiuto visibile al cliente

### Stato attuale

`Prenotazione.note_operatore` è già popolata in `rifiuta()` con il motivo del rifiuto.  
`Prenotazione.stato = "rifiutata"` esiste già.

### Modifiche al modello

**Nessuna.** Il dato è già presente nel DB.

**Modifica necessaria:** lato template `mie_prenotazioni.html`, quando `p.stato == "rifiutata"`, mostrare una riga aggiuntiva con `p.note_operatore` se presente.

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 7.1 | Rifiuto senza motivo (note_operatore vuoto) | Mostrare "Nessun motivo specificato" o la label "Rifiutata" senza dettagli. |
| 7.2 | note_operatore già usato per altri scopi (es. approvazione con modifica) | Allo stato attuale `note_operatore` viene scritto solo in `rifiuta()` e `rifiuta_ingresso()`. Non c'è conflitto. In ogni caso, meglio separare: creare `motivo_rifiuto` separato da `note_operatore`. |

### Modifica modello (raccomandata per chiarezza)

```python
# Nuovo campo separato da note_operatore
motivo_rifiuto = db.Column(db.Text, nullable=True)
```

Questo evita confusione futura tra "note interne dell'operatore" e "motivo di rifiuto visibile al cliente".

### SQL migration

```sql
ALTER TABLE prenotazioni ADD COLUMN IF NOT EXISTS motivo_rifiuto TEXT;
```

### Logica

```
# In rifiuta():
p.stato = "rifiutata"
p.motivo_rifiuto = form.motivo.data or None
# note_operatore rimane per note interne (opzionale)

# In template:
{% if p.stato == "rifiutata" and p.motivo_rifiuto %}
    Motivo: {{ p.motivo_rifiuto }}
{% endif %}
```

---

## Feature 8 — Vincolo doppia prenotazione stesso cliente/magazzino/tipologia

### Modifiche al modello

**Nessuna.** È un vincolo applicativo.

### Logica di validazione

```
esistenti = Prenotazione.query.filter(
    Prenotazione.cliente_id == current_user.id,
    Prenotazione.magazzino == magazzino_scelto,
    Prenotazione.tipologia_materiale_id == tipologia_id,
    Prenotazione.data == data_prenot,
    Prenotazione.stato.in_(STATI_ATTIVI),
    Prenotazione.id != id_corrente (se modifica),
).count()
if esistenti > 0:
    flash: "Hai già una prenotazione attiva per questa tipologia in questo magazzino."
```

### Casi limite

| # | Caso | Gestione proposta |
|---|------|-------------------|
| 8.1 | Stessa tipologia, stesso magazzino, giorni diversi | Permesso (il vincolo è per-data: finché la prima non è completata/scaduta). |
| 8.2 | Stessa tipologia, magazzino diverso, stesso giorno | Permesso (es. Colle 1 + Colle 3 anche stessa tipologia). |
| 8.3 | Stesso cliente, stessa tipologia, stesso magazzino, stesso giorno, ma una è "carico" e l'altra "scarico" | **Bloccare comunque**: il vincolo è su cliente+magazzino+tipologia, indipendentemente dal tipo operazione. Se servono entrambi, serve distinguere con tipologie diverse. |
| 8.4 | Il vincolo vale per l'intera durata della prima prenotazione? | **Sì**: finché la prenotazione attiva esiste (stato in_attesa, confermata, ingresso_registrato). Una volta che la prenotazione è completata/scaduta/annullata, si può crearne un'altra. |
| 8.5 | Controllo va fatto anche in fase di approvazione admin? | **Sì**, per race condition. |

---

## Risposte alle domande aperte

### D1 — Punto 6 + 3: durata "Rientri" (45 min) vs durata magazzino (30 min)

**Proposta: La tipologia "Rientri" SOVRASCRIVE la durata del magazzino.**

- La durata del magazzino è la durata *base* per gli slot normali.
- "Rientri" è una tipologia speciale con durata fissa 45 min dichiarata esplicitamente.
- La regola: se la tipologia ha `durata_minuti` impostata, quella è la durata effettiva. Il `durata_slot_minuti` del magazzino viene usato solo come fallback per prenotazioni senza tipologia (caso non applicabile perché la tipologia è obbligatoria).
- Impatto sulla griglia: serve un passo slot minimo (es. 15 min) per accomodare durate variabili, oppure mostrare slot della durata del magazzino ma calcolare la sovrapposizione in base alla durata della tipologia scelta.

### D2 — Punto 5: vincolo "una targa al giorno" per singolo magazzino o su tutta l'azienda?

**Proposta: Su tutta l'azienda (tutti i magazzini insieme).**

- Una targa (camion) non può fisicamente essere in due posti contemporaneamente.
- L'unica eccezione è "trasferimento" (perché è la stessa merce che si sposta da un magazzino all'altro).
- Nessun'altra eccezione, a meno di casi specifici da discutere (es. ritorno con merce diversa).

### D3 — Punto 8: vincolo doppia prenotazione: temporaneo o permanente?

**Proposta: Permanente finché la prenotazione attiva non termina il suo ciclo.**

- Stati che bloccano: `in_attesa`, `confermata`, `ingresso_registrato`.
- Stati che sbloccano: `rifiutata`, `annullata`, `scaduta`.
- NON è limitato allo stesso giorno. Se un cliente ha una prenotazione attiva per "Bobine" a Colle 1 per il 30 luglio, non può prenotare un'altra "Bobine" a Colle 1 per il 5 agosto finché la prima non è completata/scaduta.
- **Vale per OGNI magazzino**, non solo Colle 1. La richiesta originale menziona Colle 1 ma la logica è generalizzabile: cliente + magazzino + tipologia.

### D4 — Punto 2: cliente senza magazzini associati (fallback)

**Proposta: Fallback — mostrare TUTTI i magazzini (comportamento attuale) con messaggio informativo.**

- "Nessuna limitazione configurata. Contatta l'amministratore per associare i magazzini alla tua utenza."
- Questo evita di bloccare clienti storici esistenti.
- In futuro si potrà rendere obbligatoria l'associazione con un flag `magazzini_obbligatori` a livello di configurazione.

### D5 — Punto 1: QR code per inserimento manuale staff

**Proposta: Sì, generare QR code normalmente.**

- La prenotazione staff passa per lo stesso flusso di verifica (stato → confermata → QR → verifica ingresso).
- L'unica differenza è il flag `inserita_da_staff=True` e `staff_user_id` popolato.
- Lo staff può anche opzionalmente saltare la verifica e impostare direttamente `stato = "ingresso_registrato"` con un flag esplicito "ingresso già avvenuto" nella UI.

---

## Impatto sulle slot grid (questioni architetturali)

La funzione `_slot_disponibili()` attualmente usa `regola.durata_minuti` come passo della griglia. Con l'introduzione di durate variabili per magazzino e tipologia:

**Problema:** La griglia slot deve essere indipendente dalla durata specifica, perché la durata dipende dalla combinazione magazzino+tipologia che il cliente sceglie *dopo* aver visto la griglia.

**Soluzione proposta:** Passare la griglia a uno step fisso minimo (es. 15 o 30 minuti). La durata effettiva dello slot viene calcolata al momento della prenotazione in base a magazzino + tipologia selezionati. La verifica di sovrapposizione (occupato/libero) rimane basata su `ora_inizio` < `ora_fine` e `ora_fine` > `ora_inizio`, già implementata.

Questo è un impatto trasversale che tocca: `_slot_disponibili()`, `_allinea_orario()`, `prenota()`, `approva()`.

---

## Riepilogo delle nuove tabelle

| Tabella | Scopo |
|---------|-------|
| `cliente_magazzini` | Associazione M2M Cliente → MagazzinoCapienza (Feature 2) |
| `vettori` | Anagrafica vettori/trasportatori (Feature 4) |
| `cliente_vettori` | Associazione M2M Cliente → Vettore (Feature 4) |

## Riepilogo dei nuovi campi

| Tabella | Campo | Tipo | Default | Feature |
|---------|-------|------|---------|:-------:|
| `prenotazioni` | `inserita_da_staff` | Boolean | false | 1 |
| `prenotazioni` | `staff_user_id` | FK → users.id | null | 1 |
| `prenotazioni` | `vettore_id` | FK → vettori.id | null | 4 |
| `prenotazioni` | `motivo_rifiuto` | Text | null | 7 |
| `magazzini_capienza` | `durata_slot_minuti` | Integer | 30 | 6 |
| `tipologie_materiale` | `ordinamento` | Integer | 0 | 3 |

## Riepilogo dei vincoli applicativi (non DB)

| Vincolo | Feature | Dove implementare |
|---------|:-------:|-------------------|
| Una targa/giorno (salvo trasferimenti) | 5 | `prenota()`, `approva()` |
| Doppia prenotazione stesso cliente+magazzino+tipologia | 8 | `prenota()`, `approva()` |
| Selettore magazzino filtrato per cliente associato | 2 | `calendario()`, template |
| Durata slot: tipologia sovrascrive magazzino | 6 | `_allinea_orario()`, `prenota()` |

---

**Fase 1 completa. Attendere conferma prima di procedere con la Fase 2 (implementazione).**