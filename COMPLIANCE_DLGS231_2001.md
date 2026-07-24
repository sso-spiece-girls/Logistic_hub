# Logistic Hub — Conformità al D.Lgs. 231/2001

## Documento Tecnico di Presidio del Sistema Informativo

---

## 1. Premessa

Il presente documento descrive le funzionalità tecniche di **Logistic Hub** che
supportano i presidi organizzativi e di controllo richiesti dal
**Decreto Legislativo 8 Giugno 2001, n. 231** in materia di responsabilità
amministrativa degli enti.

Il documento è a corredo del Modello di Organizzazione, Gestione e Controllo
(MOG) adottato dall'ente e costituisce la descrizione tecnica degli strumenti
informatici a presidio dei processi sensibili.

> **Nota:** Il presente documento descrive le capacità tecniche del sistema.
> L'adozione e l'efficacia del Modello 231 rimangono di esclusiva competenza
> dell'organo dirigente dell'ente, che valuta l'adeguatezza degli strumenti
> rispetto al contesto operativo specifico e ai rischi individuati.

---

## 2. Ambito di Applicazione

### 2.1 Processi Coperti dal Sistema

| # | Processo | Descrizione |
|---|----------|-------------|
| 1 | **Gestione entrate merci** | Carico bolle, OCR documenti fornitori, aggiornamento giacenze |
| 2 | **Gestione uscite merci** | Creazione DDT, spedizione, scarico giacenze |
| 3 | **Gestione giacenze** | Tracciamento quantità, colli, ubicazioni, movimentazioni |
| 4 | **Pianificazione picking** | Assegnazione operazioni a operatori, completamento task |
| 5 | **Prenotazioni appuntamenti** | Calendario clienti, approvazione/rifiuto, verifica QR |
| 6 | **Gestione documentale** | Archiviazione e condivisione documenti |
| 7 | **Backup e ripristino** | Salvaguardia e recovery dei dati |

### 2.2 Ruoli e Profili Abilitativi

| Ruolo | Descrizione | Privilegi |
|-------|-------------|-----------|
| **Admin** | Amministratore di sistema | Accesso completo a tutte le funzionalità, gestione utenti, backup |
| **Operatore** | Operatore di magazzino | Operatività su entrate/uscite/giacenze/prenotazioni |
| **Cliente** | Utente esterno | Solo prenotazione appuntamenti e consultazione |

La separazione dei ruoli garantisce il principio di **segregazione delle
funzioni** (Segregation of Duties), presidio fondamentale richiesto dal
Modello 231.

---

## 3. Tracciabilità delle Operazioni (Art. 6, Comma 2, Lett. a)

### 3.1 Registro Attività

Ogni operazione significativa sul sistema viene registrata automaticamente
nel **Registro Attività** (`/attivita`).

**Esempi di eventi tracciati:**

| Evento | Dati registrati |
|--------|-----------------|
| Login utente | username, data/ora, IP |
| Carico bolla | operatore, fornitore, n. bolla, timestamp |
| Creazione DDT | operatore, cliente, n. DDT, timestamp |
| Modifica stato | entità, stato precedente → nuovo stato, operatore |
| Approvazione prenotazione | admin, cliente, data/ora slot |
| Backup database | operatore, dimensione, esito |

**Caratteristiche del registro:**
- **Ordine cronologico** decrescente (il più recente in alto)
- **Immodificabilità** di fatto: le attività sono registrate in scrittura
  append-only (nessuna interfaccia consente la modifica o cancellazione
  delle voci del registro)
- **Persistenza**: i dati risiedono nel database transazionale e sono
  inclusi nei backup periodici
- **Consultabilità**: interfaccia dedicata con paginazione e filtro

### 3.2 Notifiche e Alert

Il sistema genera notifiche per eventi critici quali:
- Richieste di prenotazione in attesa di approvazione
- Completamento operazioni OCR
- Operazioni su documenti sensibili

Le notifiche sono tracciate con data, tipo, destinatario e messaggio.

---

## 4. Controllo degli Accessi (Art. 6, Comma 2, Lett. b)

### 4.1 Autenticazione

- **Password hashing** con algoritmo sicuro (Werkzeug `generate_password_hash`)
- **Sessioni persistenti** con durata configurabile (`PERMANENT_SESSION_LIFETIME`)
- **Rate limiting** su endpoint critici (max 20 richieste/minuto su upload OCR,
  5 tentativi/minuto su login)
- **Cookie di sessione** configurati con `HttpOnly`, `SameSite=Lax`
- **Logout** con invalidazione della sessione lato server

### 4.2 Autorizzazione

L'accesso alle funzionalità è regolato da tre livelli di decoratori:

```python
@login_required          # Qualsiasi utente autenticato
@staff_required          # Admin o Operatore
@admin_required          # Solo Admin
```

Esempi di protezione per endpoint:

| Endpoint | Ruolo minimo |
|----------|-------------|
| `/entrate/`, `/uscite/` | Staff (admin/operatore) |
| `/users/` | Admin |
| `/backup/` | Admin |
| `/prenotazioni/calendario` | Cliente o staff |
| `/prenotazioni/admin/` | Staff |

### 4.3 Matrice dei Poteri

| Funzione | Admin | Operatore | Cliente |
|----------|:-----:|:---------:|:-------:|
| Dashboard | ✅ | ✅ | — |
| Entrate / Bolle | ✅ | ✅ | — |
| Uscite / DDT | ✅ | ✅ | — |
| Giacenze | ✅ | ✅ | — |
| Pianificazione | ✅ | ✅ | — |
| Movimenti | ✅ | ✅ | — |
| Clienti / OCR | ✅ | ✅ | — |
| Documenti | ✅ | ✅ | — |
| Prenotazioni (admin) | ✅ | ✅ | — |
| Prenotazioni (cliente) | — | — | ✅ |
| Gestione Utenti | ✅ | — | — |
| Capienza Magazzini | ✅ | — | — |
| Backup | ✅ | — | — |
| Registro Attività | ✅ | ✅ | ✅ |

---

## 5. Gestione Documentale e Conservazione (Art. 6, Comma 2, Lett. d)

### 5.1 Archivio Documenti

- Ogni documento caricato è registrato con:
  - **nome originale** del file
  - **tipo** (PDF, XLSX, ecc.)
  - **data e ora** di caricamento (UTC, convertita in fuso Italia)
  - **utente** che ha effettuato il caricamento
  - **riferimento** all'entità associata (bolla, DDT, ecc.)
- Download tracciato implicitamente dal Registro Attività tramite
  accesso al documento

### 5.2 Elaborazione OCR

Il pipeline di OCR documentale segue questi step, ciascuno tracciato:
1. Upload PDF → salvataggio file con hash univoco
2. Riconoscimento fornitore (pattern matching su prima pagina)
3. Estrazione dati con parser specifico per fornitore
4. Validazione e controllo duplicati
5. Proposta dati all'operatore per conferma
6. Conferma e aggiornamento giacenza

Il sistema **non distrugge mai il PDF originale** dopo l'elaborazione,
garantendo la conservazione del documento fonte.

---

## 6. Integrità dei Dati e Backup

### 6.1 Backup Programmato

- Backup manuale tramite interfaccia web (`/backup/crea`)
- Backup automatico configurabile tramite cron job (°)
- Ogni backup registra:
  - **timestamp** di creazione
  - **dimensione** del file
  - **tipo** (manuale/automatico)
  - **utente** esecutore
- I file di backup sono scaricabili dall'interfaccia admin

### 6.2 Transazionalità dei Dati

- Tutte le operazioni di scrittura sono eseguite all'interno di
  transazioni SQLAlchemy con `commit` esplicito
- In caso di errore, viene eseguito `rollback` per garantire
  l'integrità referenziale
- Le operazioni di aggiornamento giacenza sono atomiche
  (aggiornamento quantità contestuale alla conferma bolla)

---

## 7. Anticorruzione e Trasparenza (Art. 25)

### 7.1 Verifica degli Accessi

Il sistema mantiene traccia di:
- **Tentativi di accesso** (login riusciti e falliti)
- **Accesso a dati sensibili** (documenti finanziari, DDT, bolle)
- **Operazioni fuori orario** (attività al di fuori della fascia
  lavorativa standard)

### 7.2 Conflitto di Interessi

- La separazione dei ruoli (admin / operatore / cliente) impedisce
  che lo stesso utente possa creare e autorizzare la stessa operazione
- Le prenotazioni dei clienti sono soggette ad **approvazione esplicita**
  da parte di un admin o operatore
- Un operatore non può modificare i propri dati utente né elevare
  i propri privilegi

---

## 8. Presidi per la Privacy e GDPR

### 8.1 Dati Personali Trattati

| Tipologia | Finalità | Conservazione |
|-----------|----------|---------------|
| Nome utente, email | Identificazione, comunicazioni | Illimitata (fino a cancellazione account) |
| Log attività | Tracciabilità operazioni | Illimitata |
| Documenti fornitori | Elaborazione ordini | Illimitata |
| Backup | Recovery dati | Fino a sostituzione con backup successivo |

### 8.2 Misure di Sicurezza

- **HTTPS** obbligatorio in produzione (terminazione TLS)
- **Hash password** con algoritmo sicuro (Werkzeug, iterazioni
  configurabili)
- **Protezione CSRF** su tutti i form (`Flask-WTF`)
- **Rate limiting** su endpoint sensibili
- **Content Security Policy** applicata tramite header HTTP
- **Cache immutabile** per asset statici (protezione da attacchi
  di cache poisoning)

### 8.3 Data Breach Response

In caso di violazione dei dati:
1. Il Registro Attività fornisce la **traccia forense**
   immediatamente consultabile
2. I backup consentono il **ripristino** dello stato precedente
   all'incidente
3. La gestione utenti permette la **disabilitazione immediata**
   di account compromessi

---

## 9. Flussi Informativi e Reportistica

| Report | Frequenza | Destinatari |
|--------|-----------|-------------|
| Attività recenti | Real-time / Dashboard | Tutti gli utenti |
| Registro completo attività | On-demand | Admin |
| Backup log | On-demand | Admin |
| Stato giacenze | Real-time | Staff |

Tutti i report sono **esportabili** e **consultabili** tramite
interfaccia web.

---

## 10. Limitazioni del Sistema

Il sistema informatico **non presidia** automaticamente:

- La **politica di conservazione dei dati** (l'eliminazione fisica
  dei dati obsoleti è manuale)
- La **firma digitale** dei documenti
- La **conservazione sostitutiva** a norma di legge
- La **certificazione** dei log (non è utilizzato un sistema di
  logging immutabile come blockchain o write-once storage)
- L'**identificazione biometrica** degli operatori

Per questi aspetti si rimanda alle procedure organizzative del
Modello 231 adottato dall'ente.

---

## 11. Glossario dei Termini Tecnici

| Termine | Descrizione |
|---------|-------------|
| **Bolla** | Documento di trasporto in entrata (documento del fornitore) |
| **DDT** | Documento di Trasporto in uscita |
| **Giacenza** | Registrazione contabile della quantità di un articolo a magazzino |
| **Picking** | Attività di prelievo merce per preparazione spedizione |
| **OCR** | Optical Character Recognition — riconoscimento automatico del testo |
| **QR Code** | Quick Response Code — codice a barre bidimensionale |
| **Rate limiting** | Limitazione del numero di richieste in un intervallo di tempo |
| **CSRF** | Cross-Site Request Forgery — protezione da attacchi di falsificazione |
| **TLS** | Transport Layer Security — protocollo di crittografia delle comunicazioni |
| **UTC** | Tempo universale coordinato |

---

## 12. Riferimenti

- **Decreto Legislativo 8 giugno 2001, n. 231**
  "Disciplina della responsabilità amministrativa delle persone giuridiche,
  delle società e delle associazioni anche prive di personalità giuridica"
  (G.U. 19 giugno 2001, n. 140)

- **Regolamento UE 2016/679 (GDPR)**
  Regolamento Generale sulla Protezione dei Dati

- **D.Lgs. 196/2003 (Codice Privacy)** e successive modifiche

---

## 13. Cronologia delle Revisioni

| Versione | Data | Autore | Modifica |
|----------|------|--------|----------|
| 1.0 | 24/07/2026 | Logistic Hub | Prima stesura |
| | | | |

---

*Il presente documento è aggiornato alla release corrente del sistema
Logistic Hub. Le funzionalità descritte possono variare in seguito a
successivi aggiornamenti del software.*
