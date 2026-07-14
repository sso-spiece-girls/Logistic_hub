import os
import re
from datetime import datetime


def estrai_testo_da_pdf(percorso):
    """Estrae testo da PDF usando PyMuPDF (pymupdf). Fallback a pdfminer."""
    try:
        import fitz
        doc = fitz.open(percorso)
        testo = ""
        for page in doc:
            testo += page.get_text() + "\n"
        doc.close()
        return testo
    except ImportError:
        pass

    try:
        from pdfminer.high_level import extract_text
        return extract_text(percorso)
    except ImportError:
        pass

    raise ImportError("Nessuna libreria PDF disponibile. Installa pymupdf o pdfminer.six")


def estrai_testo_da_immagine(percorso):
    """OCR su PDF scansionato (immagine). Richiede pytesseract + poppler."""
    try:
        from pdf2image import convert_from_path
        import pytesseract
        immagini = convert_from_path(percorso, dpi=300)
        testo = ""
        for img in immagini:
            testo += pytesseract.image_to_string(img, lang="ita", config="--psm 6 --oem 3") + "\n"
        return testo
    except (ImportError, OSError) as e:
        raise RuntimeError(
            "OCR non disponibile su questo server (mancano tesseract/poppler). "
            "Usa PDF con testo selezionabile."
        ) from e


def leggi_pdf(percorso, forza_ocr=False):
    """Legge PDF: prima tenta testo diretto, se poco testo fa OCR."""
    testo_diretto = ""
    if not forza_ocr:
        try:
            testo_diretto = estrai_testo_da_pdf(percorso)
            if len(testo_diretto.strip()) > 50:
                return testo_diretto
        except ImportError:
            pass

    # OCR fallback con graceful degradation
    try:
        return estrai_testo_da_immagine(percorso)
    except (RuntimeError, ImportError, OSError) as e:
        if testo_diretto:
            # Se abbiamo anche poco testo, restituiamo quello anziche' fallire
            return testo_diretto
        raise RuntimeError(
            f"Impossibile leggere il PDF: {e}. "
            "Carica un PDF con testo selezionabile (non scansionato)."
        )