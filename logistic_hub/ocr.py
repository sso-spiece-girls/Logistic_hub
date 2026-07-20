import os
import re
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageFilter, ImageOps

# Path configurabile via env; imposta solo se richiesto (non su server senza Tesseract)
_tess_path = os.environ.get("TESSERACT_PATH")
if _tess_path:
    pytesseract.pytesseract.tesseract_cmd = _tess_path
    os.environ["TESSDATA_PREFIX"] = os.environ.get("TESSDATA_PREFIX", os.path.join(os.path.dirname(_tess_path), "tessdata"))
elif os.name == "nt" and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"


PATTERN_FORNITORI = {
    "BASE_SPA": re.compile(
        r'PICKING\s+(\d{4,})\s+(\d{1,3})\s*pallet\s*\((\d{1,5})\s*colli\)\s*([\d.,]+)\s*kg',
        re.IGNORECASE
    ),
    "GENERICO_COLLI": re.compile(
        r'(\d{1,5})\s*colli.*?([\d.,]+)\s*kg',
        re.IGNORECASE
    ),
}

# Pattern per estrarre fornitore dal testo OCR
PATTERN_FORNITORE = [
    (re.compile(r'(?i)BASE\s*SPA'), "BASE SPA"),
    (re.compile(r'(?i)CARTIERE?\s*CARRARA'), "Cartiere Carrara"),
    (re.compile(r'(?i)PRATOLUNGO'), "Pratolungo"),
    (re.compile(r'(?i)ESSITY'), "Essity"),
    (re.compile(r'(?i)PECTEN'), "Pecten"),
    (re.compile(r'(?i)ZIGNAGO'), "Zignago"),
    (re.compile(r'(?i)SALERI'), "Saleri"),
    (re.compile(r'(?i)NSW'), "NSW"),
    (re.compile(r'(?i)CELTEX'), "Celtex"),
]

# Pattern per estrarre numero bolla/DDT
PATTERN_NUMERO_BOLLA = [
    re.compile(r'(?i)(?:DDT|D\.D\.T\.|BOLLA|DOCUMENTO\s+DI\s+TRASPORTO)\s*[Nn°.]*\s*(\d{4,10})'),
    re.compile(r'(?i)(?:N[ro°.]*|NUMERO)\s*[.:]*\s*(\d{4,10})'),
    re.compile(r'(?i)(?:DDT|BOLLA)\s*[Nn°.]*\s*(\d{4,10})'),
]

# Pattern per estrarre data
PATTERN_DATA = [
    re.compile(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})'),
    re.compile(r'(\d{1,2})\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{2,4})', re.IGNORECASE),
]


def estrai_fornitore(testo):
    """Estrae il nome del fornitore dal testo OCR."""
    for pattern, nome in PATTERN_FORNITORE:
        if pattern.search(testo):
            return nome
    return ""


def estrai_numero_bolla(testo):
    """Estrae il numero bolla/DDT dal testo OCR."""
    for pattern in PATTERN_NUMERO_BOLLA:
        match = pattern.search(testo)
        if match:
            return match.group(1)
    return ""


def estrai_data(testo):
    """Estrae la data dal testo OCR e la ritorna in formato YYYY-MM-DD."""
    from datetime import datetime
    mesi = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    # Pattern numerico: DD/MM/YYYY
    match = PATTERN_DATA[0].search(testo)
    if match:
        g, m, a = match.groups()
        if len(a) == 2:
            a = "20" + a
        try:
            return f"{int(a):04d}-{int(m):02d}-{int(g):02d}"
        except ValueError:
            pass
    # Pattern testuale: DD mese YYYY
    match = PATTERN_DATA[1].search(testo)
    if match:
        g, a = match.groups()
        mese_testo = match.group(0).lower()
        for mese_nome, mese_num in mesi.items():
            if mese_nome in mese_testo:
                if len(a) == 2:
                    a = "20" + a
                try:
                    return f"{int(a):04d}-{mese_num:02d}-{int(g):02d}"
                except ValueError:
                    pass
    return ""


def estrai_righe(testo):
    """
    Estrae le righe (articoli) dal testo OCR.
    Gestisce tutti i formati OCR reali da CamScanner + Tesseract:
      - PICKING31129 | 15 pallet (646 colli) 6835 kg
      - PiCKING31132 | 3 pallet(111 colli) 1185 kg
      - PICKING 31136 14 pallet (740 cartoni tot) 7942 kg
      - picuns 31122 | 2 pallet (100 colli
      - 31111/31124 — 1 collo
      - SPLO1240239 16 pallet 4803,11 kg
      - 1303200488 | 3pallet | 3508
    """
    righe = []
    visti = set()
    # Normalizza: lowercase, rimuovi pipe/underscore extra
    testo_norm = testo.lower().replace('_', ' ').replace('|', ' ')

    # === Pattern PICKING: copre tutti i formati OCR ===
    # 1) PICKING<code> <N> pallet (<N> colli|cartoni...) <kg>
    # 2) PICKING <code> <N> pallet (<N> colli|cartoni...) <kg>
    # 3) picuns <code> <N> pallet (<N> colli...) (OCR sbagliato)
    # Gestisce: no space, mixed case, paren aperta/chiusa mancante, "coll" abbreviato
    pattern_picking = re.compile(
        r'(?:picking|picuns|pickins|piceing|piking)'
        r'\s*'
        r'(\d{4,})'
        r'\s+'
        r'(\d{1,3})'
        r'\s*'
        r'pallet'
        r'\s*'
        r'[\(\[]?\s*'
        r'(\d{1,6})'
        r'\s*'
        r'(?:coll[iì]?|cartoni(?:\s+tot)?|colli)'
        r'[^)\]\n]{0,10}'
        r'[\)\]]?'
        r'(?:\s+([\d.,]+)\s*kg)?',
        re.IGNORECASE
    )

    for m in pattern_picking.finditer(testo_norm):
        key = m.group(1)
        if key not in visti:
            visti.add(key)
            peso = float(m.group(4).replace(",", ".")) if m.group(4) else 0
            righe.append({
                "descrizione": f"PICKING {m.group(1)}",
                "quantita": int(m.group(3)),
                "pallet": int(m.group(2)),
                "unita_misura": "colli",
                "peso_kg": peso,
            })

    # === Fallback: PICKING con OCR rotto (es: "740 P 7942kg" senza "colli") ===
    for m in re.finditer(
        r'(?:picking|picuns|pickins|piceing|piking)'
        r'\s*'
        r'(\d{4,})'
        r'\s+'
        r'(\d{1,3})'
        r'\s*'
        r'pallet'
        r'\s+'
        r'[\(\[]?'
        r'(\d{1,6})'
        r'\s+\S*\s*'
        r'([\d.,]+)\s*kg',
        testo_norm
    ):
        key = m.group(1)
        if key not in visti:
            visti.add(key)
            righe.append({
                "descrizione": f"PICKING {m.group(1)}",
                "quantita": int(m.group(3)),
                "pallet": int(m.group(2)),
                "unita_misura": "colli",
                "peso_kg": float(m.group(4).replace(",", ".")),
            })

    # === Pattern 2: <codice alfnumerico> <N> pallet <kg> kg ===
    # es: SPLO1240239 16 pallet 4803,11 kg
    for m in re.finditer(
        r'([a-z]{2,}\d{4,})\s+(\d{1,3})\s*pallet\s+([\d.,]+)\s*kg',
        testo_norm
    ):
        key = m.group(1)
        if key not in visti:
            visti.add(key)
            righe.append({
                "descrizione": m.group(1).upper(),
                "quantita": 0,
                "pallet": int(m.group(2)),
                "unita_misura": "pallet",
                "peso_kg": float(m.group(3).replace(",", ".")),
            })

    # === Pattern 3: <6+ digit code> | <N>pallet | <kg> ===
    for m in re.finditer(
        r'(\d{6,})\s+\d+\s*pallet\s+([\d.,]+)\s*kg',
        testo_norm
    ):
        key = m.group(1)
        if key not in visti:
            visti.add(key)
            righe.append({
                "descrizione": m.group(1),
                "quantita": 0,
                "pallet": 0,
                "unita_misura": "pallet",
                "peso_kg": float(m.group(2).replace(",", ".")),
            })

    # === Pattern 4: <code> — <N> collo/colli ===
    for m in re.finditer(
        r'(\d{3,}[-/\d]*)\s*[—–-]+\s*(\d+)\s*colli?',
        testo_norm
    ):
        key = m.group(1)
        if key not in visti:
            visti.add(key)
            righe.append({
                "descrizione": m.group(1),
                "quantita": int(m.group(2)),
                "pallet": 0,
                "unita_misura": "colli",
                "peso_kg": 0,
            })

    return righe


def _preprocess_adaptive(img):
    img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=5)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    return img


def _preprocess_binary(img):
    img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=10)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SMOOTH)
    img = img.point(lambda p: 255 if p > 128 else 0)
    return img


def _ocr(img, psm=6):
    return pytesseract.image_to_string(img, lang="ita", config=f"--psm {psm} --oem 3")


def _estrai_dati_da_blocco(blocco):
    picking_match = re.search(r'(\d{4,})', blocco)
    if not picking_match:
        return None
    picking = picking_match.group(1)

    pallet_match = re.search(r'(\d{1,3})\s*[pP][aA][lL][lL][eE][tT]', blocco)
    pallet = pallet_match.group(1) if pallet_match else "0"

    colli_match = re.search(r'(\d{1,5})\s*([cC][oO][lL][lL][iI]|[cC][aA][rR][tT][oO][nN][iI])', blocco)
    colli = colli_match.group(1) if colli_match else "0"

    peso_match = re.search(r'(\d+[\.,]?\d*)\s*[kK][gG]', blocco)
    peso = peso_match.group(1).replace(",", ".") if peso_match else "0"

    return (picking, pallet, colli, peso)


def estrai_dati(testo_ocr, fornitore="BASE_SPA"):
    """
    Ritorna lista di dict: {picking, pallet, colli, peso_kg}
    fornitore può essere: BASE_SPA, GENERICO_COLLI
    """
    pattern = PATTERN_FORNITORI.get(fornitore, PATTERN_FORNITORI["GENERICO_COLLI"])
    risultati = []
    for m in pattern.finditer(testo_ocr):
        if fornitore == "BASE_SPA":
            risultati.append({
                "picking": m.group(1),
                "pallet": int(m.group(2)),
                "colli": int(m.group(3)),
                "peso_kg": float(m.group(4).replace(",", ".")),
            })
        else:
            risultati.append({
                "picking": "",
                "pallet": 0,
                "colli": int(m.group(1)),
                "peso_kg": float(m.group(2).replace(",", ".")),
            })
    return risultati


def leggi_pdf(percorso):
    """
    Ritorna (testo_grezzo, lista_dati_estratti, dict_metadata).
    dict_metadata contiene: fornitore, numero_bolla, data_arrivo
    """
    immagini = convert_from_path(percorso, dpi=300)

    t_adaptive = ""
    t_binary = ""
    t_raw = ""

    for img in immagini:
        t_adaptive += _ocr(_preprocess_adaptive(img)) + "\n"
        t_binary += _ocr(_preprocess_binary(img)) + "\n"
        t_raw += _ocr(img) + "\n"

    ancora_picking = r'(?i)(?:PICKING|P[|1lI][CK][K1][I1l][Nn][Gg]|P[Cc][Kk])'

    def processa_testo(testo):
        risultati = []
        blocchi = re.split(ancora_picking, testo)
        for b in blocchi[1:]:
            dato = _estrai_dati_da_blocco(b)
            if dato:
                risultati.append(dato)
        return risultati

    risultati = processa_testo(t_adaptive)
    if not risultati:
        risultati = processa_testo(t_binary)
    if not risultati:
        risultati = processa_testo(t_raw)

    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_ocr")
    os.makedirs(debug_dir, exist_ok=True)
    for name, txt in [("adaptive", t_adaptive), ("binary", t_binary), ("raw", t_raw)]:
        path = os.path.join(debug_dir, f"{name}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)

    testo_completo = t_adaptive or t_binary or t_raw

    # Estrai metadati bolla - prova con tutti i testi OCR, usa quello con piu righe
    righe = estrai_righe(testo_completo)
    for alt_testo in [t_binary, t_raw]:
        alt_righe = estrai_righe(alt_testo)
        if len(alt_righe) > len(righe):
            righe = alt_righe

    metadata = {
        "fornitore": estrai_fornitore(testo_completo),
        "numero_bolla": estrai_numero_bolla(testo_completo),
        "data_arrivo": estrai_data(testo_completo),
        "righe": righe,
    }

    return testo_completo, risultati, metadata
