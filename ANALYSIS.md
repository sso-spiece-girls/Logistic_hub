# Logistic Solution — Analisi Completa

## 0. File Ricevuti e Analizzati

### PDF Bolle di Trasporto (CamScanner — immagini, nessun testo estraibile)

| File | Fornitore | Pagine | Contenuto |
|------|-----------|--------|-----------|
| `CamScanner 08-06-2026 15.41 (1).pdf` | Cartiere Carrara + Cartiera Pratolungo | 5 | DDT carta, 8 colli, IG BIANCO PEFC, IG PEFC GR.15, B30017 BLU CEL WS. Dettagliata packing list con SSCC/lotto |
| `CamScanner 11-06-2026 16.27.pdf` | **BASE SPA** | 4 | Lista PICKING: 20+ righe con formato "PICKING 31124 3 pallet (141 colli) 1485 kg" |
| `CamScanner 12-06-2026 10.01.pdf` | PECTEN GROUP | 2 | Documento farmaceutico — non pertinente al magazzino |

### Modello DDT (testo estraibile)

| File | Creato da | Info |
|------|-----------|------|
| `DDT_1.012-0_2026-06-08.pdf` | **jsPDF 4.2.1** (JS) | Mittente: Logistic Solution S.r.l., Via Napoli 22, Collesalvetti. Cliente: INDUSTRIE CELTEX SPA. Dest.: CARTIERA DI PRATOLUNGO. DDT N. 1.012/0. 8 Colli. Vettore CTV. Articoli: 20180-SE - 280226500002442... |

### Excel (dati reali di magazzino)

| File | Sheets | Contenuto |
|------|--------|-----------|
| `GIACENZABOBINECELTEXCOLLE.xlsx` | GIACENZA (662 righe), USCITE, RIEPILOGO | **657 bobine in giacenza**, 1.369.238 kg totali, 25 articoli distinti. Colonne: COD. ARTICOLO, ID BOBINA, PESO, DESCRIZIONE, QUALITÀ, STATO, DATA REG., N. BOLLA, PROVENIENZA (ESSITY), UBICAZIONE |
| `CELTEX - 2026.xlsx` | - | Dati Celtex (fornitore) |
| `Programma giornaliero.xlsx` | 20+ fogli giornalieri (Set-Oct 2025) | **Planning giornaliero**: Entrate/Uscite per giorno. Clienti: CELTEX, ZIGNAGO, SALERI, NSW, PGM, EP, CORA. Magazzini: Colle 1-5. Unità: colonne (bobine) o pallet |

### App Esistente

| Percorso | Tecnologia | Stato |
|----------|-----------|-------|
| `C:\Users\marzu\OneDrive\Desktop\Magazzino\` | Flask + SQLite + Tesseract OCR + FPDF | **Funzionante** ma da migliorare |

---

## 1. Stato Attuale del Codice Esistente

### Magazzino App (Desktop\Magazzino\)

- **Flask** con templates HTML/CSS/JS puri (nessun framework JS)
- **SQLite** con WAL mode
- **OCR**: Tesseract con 3 strategie (adaptive, binary, raw) → estrae PICKING, pallet, colli/cartoni, peso via regex
- **DDT PDF**: generato con FPDF (layout base: intestazione, indirizzi, tabella merci, firme)
- **Login**: admin/admin, ufficio/ufficio, op/op
- **UI**: navbar, KPI dashboard, search globale, notifiche, PWA manifest + service worker
- **Backup**: automatico giornaliero, restore manuale

### Cosa Funziona Già
- Upload PDF → OCR → estrazione dati → salvataggio in giacenze
- Ricerca globale per picking/cliente/DDT
- Uscita merce con form destinazione e indirizzi salvati
- Generazione DDT PDF
- Gestione utenti (admin/ufficio/operatore)
- Documenti (PDF caricati e DDT generati)
- PWA installabile

### Cosa Non Va / Da Migliorare
1. Usa "cartoni" invece di "colli" (richiesto: **sempre colli**)
2. DDT PDF generato con FPDF — layout semplice, non replica il modello reale (jsPDF)
3. OCR solo per formato "PICKING" — non gestisce Cartiere Carrara, Pratolungo, Essity
4. Nessun **duplicato detection**: all'upload NON controlla se DDT esiste già
5. Nessuna tabella `fornitori` o `articoli` — articoli sono solo stringhe
6. La logica "magazzino" è solo Colle 1 / Colle 3 - Doganale, mancano Colle 2, 4, 5
7. Mancano: SSCC/lotto tracking, resi, ubicazioni multiple
8. Nessun'automazione per bobine (peso, ID bobina, provenienza)

---

## 2. Analisi Web App di Riferimento

### Bobine WMS — bobinwms-au45xvkz.manus.space
- React SPA con Vite, tema #3b5998 blue, Inter font
- PWA standalone portrait
- Flusso: scansione barcode → OCR PDF trasporto → giacenze bobine → DDT uscita
- Pagine: dashboard, bolle-entrata, giacenze, ddt

### MagazzinoPro — magazzino-aacqfazc.manus.space
- React SPA con Vite (CSS bundle diverso)
- OCR per lettura DDT tramite scan, gestione colli/pallet, movimenti, reportistica
- Navbar con logo aziendale, sezione DDT colorata

---

## 3. Architettura Proposta

```
┌──────────────────────────────────────────────────────┐
│                   PWA (HTML/CSS/JS)                   │
│  ┌──────┐ ┌───────────┐ ┌────────┐ ┌─────────────┐ │
│  │Dashb.│ │Ingresso   │ │Giacenze│ │Uscita + DDT │ │
│  │      │ │Merce + OCR│ │        │ │             │ │
│  └──────┘ └───────────┘ └────────┘ └─────────────┘ │
└────────────────────┬─────────────────────────────────┘
                     │ REST API (JSON)
┌────────────────────▼─────────────────────────────────┐
│                Flask Backend (esistente da migliorare)│
│  OCR: Tesseract + regex per ogni fornitore           │
│  DB: SQLite con schema esteso                        │
│  PDF: ReportLab (layout pixel-perfect)               │
│  Auth: session-based con ruoli                       │
└──────────────────────────────────────────────────────┘
```

---

## 4. Flusso Dettagliato

### 4.1 Ingresso Merce
1. Operatore apre `/entrate`
2. Seleziona **fornitore** (Essity, Cartiere Carrara, Cartiera Pratolungo, BASE SPA, Altro)
3. Seleziona magazzino e locazione
4. Carica/scansiona PDF
5. **OCR Engine**:
   - Per BASE SPA: regex `PICKING (\d+)\s+(\d+) pallet \((\d+) colli\) (\d+[.,]?\d*) kg`
   - Per Cartiere Carrara: estrai COD.ART, colli, peso
   - Per Pratolungo: estrai articolo, colli, SSCC
   - Fallback: mostra testo OCR grezzo per estrazione manuale
6. **Duplicato Detection**: calcola hash del PDF → cerca per (fornitore, num_ddt, data) → mostra "Nuovo" / "Aggiorna"
7. Conferma → movimenti + giacenze aggiornate

### 4.2 Giacenze
- Vista tabellare: Codice | Descrizione | Quantità | Ubicazione | Ultimo movimento
- **Due modalità**: Bobine (con ID bollino, peso) e Colli/Pallet (per merce generica)
- Ricerca con autocompletamento su codice parziale
- Storico movimenti con filtro

### 4.3 Uscita Merce
1. Operatore cerca articolo (autocomplete su codice parziale)
2. Seleziona quantità
3. **Duplicato Detection**: stesso articolo stesso giorno → mostra "Carica Residuo"
4. Inserisci destinazione (o seleziona da indirizzi salvati)
5. Seleziona **Provenienza**: "Via Napoli 22" o "Via Francia 70"
6. Inserisci vettore, causale trasporto
7. Conferma → giacenze aggiornate → DDT PDF generato

### 4.4 Generazione DDT PDF (pixel-perfect)
- **Header**: Logo aziendale (sinistra), "Logistic Solution S.r.l." + indirizzo, tel, P.IVA
- **Linea divisoria**
- **Titolo**: "DOCUMENTO DI TRASPORTO (DDT)" su sfondo blu #2563eb
- **Riga DDT**: N. progressivo | Data | Pagina
- **Mittente/Destinatario**: due colonne affiancate con sfondo grigio chiaro
- **Tabella Merci**: Articolo | Magazzino | Locazione | Pallet | **Colli** | Peso kg
- **Totali**: somma pallet, colli, peso
- **Firme**: conducente + destinatario (linee di firma)
- **Footer**: "Documento generato automaticamente da Logistic Solution" + data stampa

---

## 5. Schema Database Esteso

```sql
-- Anagrafiche
fornitori (id, nome, partita_iva, indirizzo, città, telefono, email)
articoli (id, codice, descrizione, unita_misura, categoria, fornitore_id)
utenti (già esistente: users)

-- Ingresso
bolle_ingresso (id, fornitore_id, num_ddt, data_ddt, filename_pdf, hash_pdf,
                totale_colli, totale_peso, stato, created_at, user_id)
dettaglio_bolla (id, bolla_id, articolo_id, quantita, peso, sscc_lotto)

-- Giacenze (unificata per bobine e colli/pallet)
giacenze (id, articolo_id, id_bobina, quantita, peso, magazzino, locazione,
          qualita, stato, data_reg, created_at, updated_at)
-- NOTA: per bobine: id_bobina univoco, quantita=1, peso=peso_bobina
-- per colli/pallet: id_bobina=NULL, quantita=colli, peso=peso_totale

-- Movimenti
movimenti (id, tipo, articolo_id, id_bobina, quantita, peso, magazzino,
           locazione, riferimento_id, riferimento_tipo, data, user_id)

-- Uscita
picking_testata (id, cliente, destinazione, provenienza, vettore, causale,
                 num_ddt, filename_pdf, data_generazione, user_id)
picking_righe (id, picking_id, articolo_id, quantita_colli, peso, residuo)

-- Logistic
indirizzi_spedizione (già esistente)
activity_log (già esistente)
contatori (già esistente — per progressivo DDT)
```

---

## 6. Problematiche e Soluzioni

| # | Problema | Soluzione |
|---|----------|-----------|
| 1 | OCR non riconosce formato Cartiere Carrara / Pratolungo | Aggiungere regex per ogni fornitore + fallback manuale |
| 2 | Duplicati all'upload | Hash SHA256 del PDF + lookup per (fornitore, num_ddt, data) |
| 3 | DDT PDF non fedele al modello | ReportLab con coordinate precise, embed logo, stesso font |
| 4 | "cartoni" invece di "colli" | Sostituire in tutta l'app (template + DB + PDF) |
| 5 | Magazzini limitati (solo Colle 1 e 3) | Aggiungere Colle 2, 4, 5 da Excel planning |
| 6 | Nessuna gestione bobine (ID, peso, provenienza) | Nuova tabella giacenze con id_bobina, qualita, stato |
| 7 | Nessun autocomplete su codice parziale | Indice FTS5 per articoli e id bobina |
| 8 | PWA non ottimizzata per Zebra | Viewport dedicata, input fisico, bottoni grandi |
| 9 | Login in chiaro | Hash password con bcrypt (o almeno SHA256) |
| 10 | Backup solo manuale + 1h scheduler | Backup automatico a ogni operazione critica |

---

## 7. Dati Reali dal Sistema

### Giacenza Bobine Celtex (dal file Excel)
- **657 bobine** in giacenza
- **1.369.238 kg** peso totale
- **25 codici articolo** distinti
- Provenienze: ESSITY (dominante)
- Ubicazione: Colle 4 (principalmente)
- Formato dati: COD.ARTICOLO | ID BOBINA | PESO | DESCRIZIONE | QUALITÀ | STATO

### Planning Giornaliero (dal file Excel)
- Clienti attivi: CELTEX, ZIGNAGO, SALERI, NSW, PGM, EP, CORA, PRYSMIAN, LAPI GELATINE, BAULI, SHADO, INTRAMARK, TK
- Magazzini: Colle 1 (Celtex paper), Colle 2 (groupage/TK), Colle 3 (Celtex/misto), Colle 4 (Celtex/misto), Colle 5 (Zignago/bauli)
- Volume: 3-8 ingressi e 4-8 uscite al giorno per Celtex

### Documenti Fornitori (OCR analysis)
- **BASE SPA**: formato "PICKING XXXX X pallet (X colli) X kg" — pulito, ~100% accuratezza OCR
- **Cartiere Carrara**: testo denso, tabellare — ~80% accuratezza, serve preprocessing migliore
- **Cartiera Pratolungo**: simile a Carrara con SSCC — ~75% accuratezza
- **Essity**: non presente nei PDF forniti (solo nel DB Excel)

---

## 8. Logo e Brand

- **Logo**: presente in `Magazzino\static\logo.png` (12953 bytes) e `WhatsApp Documents\Logistic_Solution_logo.pdf` (corrotto/non PDF valido)
- **Nome App**: "Logistic Solution" (dal DDT modello)
- **Colori suggeriti**: #2563eb (blu primary — già usato nell'app esistente), #0f172a (text dark)

---

## 9. Prossimi Passi (dopo approvazione)

1. **Backup del DB esistente** `database.db` → copia di sicurezza
2. **Estensione schema DB** — aggiungere fornitori, articoli, bolle_ingresso, picking
3. **OCR multifornitore** — regex per BASE SPA, Cartiere Carrara, Pratolungo, Essity
4. **Duplicato detection** — hash SHA256 + lookup
5. **DDT PDF pixel-perfect** — ReportLab con layout identico al modello jsPDF
6. **Sostituzione "cartoni" → "colli"** in tutti i file
7. **Aggiunta magazzini** Colle 2, 4, 5
8. **Autocomplete su ricerca** con FTS5
9. **Migrazione dati** dal file Excel GIACENZABOBINE → nuovo DB
10. **Zebra/PDA optimization**

---

*Analisi generata il 12/06/2026 basata su: 4 PDF bolle, 1 PDF DDT modello, 3 Excel, app Magazzino esistente, 2 web app Manus.space*
