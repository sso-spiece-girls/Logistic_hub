import re
from core.plugin_base import ClientPlugin


class EneganParser(ClientPlugin):
    def __init__(self, config):
        self.id = config["id"]
        self.nome = config["nome"]
        self.pattern_riconoscimento = config["pattern_riconoscimento"]
        self.cfg = config

    def parse_ddt(self, testo_pdf):
        linee = [r for r in testo_pdf.split("\n") if r.strip()]

        ddt_num = ""
        data = ""
        cliente = ""
        articoli = []
        riferimento = ""

        # Find client - it's in the "DESTINAZIONE/Delivery address" section
        # Usually 3 lines after "CLIENTE/Addressee" or after "BUSINESS PARTNER"
        in_dest = False
        for i, linea in enumerate(linee):
            ls = linea.strip()
            if "CLIENTE/Addressee" in ls or "BUSINESS PARTNER" in ls:
                in_dest = True
                continue
            if in_dest and ls and not re.match(r'^(P\.IVA|NS\.|eDOC|RIF)', ls, re.IGNORECASE):
                # This should be the client name
                if ls not in ("DESTINAZIONE/Delivery address", "P. IVA/Vat number"):
                    if not re.match(r'^\d', ls) and len(ls) > 3:
                        cliente = ls
                    break

        if not cliente:
            # Second attempt: look for ANNA CINQUE or similar names after addresses
            for i, linea in enumerate(linee):
                ls = linea.strip()
                if re.match(r'^[A-Z][A-Z\s]+$', ls) and len(ls) > 5 and ls.find(" ") >= 0:
                    # Check if it's in the right section (after ENEGAN SPA)
                    cliente = ls
                    break

        # DDT number - look for document/order references (numeric values only)
        for i, linea in enumerate(linee):
            ls = linea.strip()
            if "RIF./Internal ref" in ls or "Internal ref" in ls:
                for j in range(i + 1, min(i + 4, len(linee))):
                    rif = linee[j].strip()
                    if re.match(r'^\d+$', rif):
                        ddt_num = rif
                        break
                if ddt_num:
                    break

        if not ddt_num:
            for i, linea in enumerate(linee):
                if re.search(r'NS\.\s*COD|Supplier\s*code', linea, re.IGNORECASE) and i + 1 < len(linee):
                    cod = linee[i + 1].strip()
                    if re.match(r'^\d+$', cod):
                        ddt_num = cod
                        break

        if not ddt_num:
            found_doc_section = False
            for i, linea in enumerate(linee):
                if "DOCUMENTO DI TRASPORTO" in linea:
                    found_doc_section = True
                    continue
                if found_doc_section:
                    m = re.search(r'\b(\d{7,10})\b', linea)
                    if m:
                        ddt_num = m.group(1)
                        break

        # Date in format "23/giu/26"
        for linea in linee:
            ls = linea.strip()
            m = re.search(r'(\d{2})/([a-z]+)/(\d{2})', ls, re.IGNORECASE)
            if m:
                month_map = {
                    "gen": "01", "feb": "02", "mar": "03", "apr": "04",
                    "mag": "05", "giu": "06", "lug": "07", "ago": "08",
                    "set": "09", "ott": "10", "nov": "11", "dic": "12",
                }
                giorno = m.group(1)
                mese_testo = m.group(2).lower()[:3]
                anno = "20" + m.group(3)
                if mese_testo in month_map:
                    data = f"{giorno}/{month_map[mese_testo]}/{anno}"
                    break

        if not data:
            for linea in linee:
                m = re.search(r'(\d{2})/(\d{2})/(\d{4})', linea)
                if m:
                    data = m.group(0)
                    break

        # Products: scan for T4T items with quantity/unit before them
        # ENEGAN format: <qta>\n<PZ|KG>\n<T4T-CODICE>\n<descrizione>
        for i, linea in enumerate(linee):
            # Find quantity line (just a number)
            m_qta = re.match(r'^(\d+)$', linea.strip())
            if not m_qta:
                continue
            qta_val = int(m_qta.group(1))

            # Next line should be unit (PZ/KG/etc)
            if i + 1 >= len(linee):
                continue
            unita = linee[i + 1].strip()
            if unita not in ("PZ", "KG", "MT", "LT", "NR"):
                continue

            # The line after unit should be product code (T4T-xxx or similar)
            if i + 2 >= len(linee):
                continue
            codice = linee[i + 2].strip()
            if len(codice) < 2:
                continue

            descrizione = ""
            if i + 3 < len(linee):
                desc_line = linee[i + 3].strip()
                # Description should not be a number or unit
                if not re.match(r'^\d+$', desc_line) and desc_line not in ("PZ", "KG", "MT", "LT", "NR"):
                    descrizione = desc_line

            articoli.append({
                "codice": codice,
                "descrizione": descrizione,
                "qta": qta_val,
                "unita": unita,
            })

        if not articoli:
            # Fallback: search whole text for T4T/any product code
            for i, linea in enumerate(linee):
                m = re.search(r'(T4T-[\w\s\-]+)', linea, re.IGNORECASE)
                if m:
                    codice = m.group(1).strip()
                    qta = 0
                    for j in range(i - 1, max(i - 4, -1), -1):
                        if re.match(r'^\d+$', linee[j].strip()):
                            qta = int(linee[j].strip())
                            break
                    descrizione = ""
                    if i + 1 < len(linee):
                        descrizione = linee[i + 1].strip()
                    articoli.append({
                        "codice": codice,
                        "descrizione": descrizione,
                        "qta": qta,
                        "unita": "PZ",
                    })

        return {
            "ddt": ddt_num,
            "data": data,
            "cliente": cliente,
            "causale": "uscita",
            "articoli": articoli,
            "totale_colli": 0,
            "totale_peso": 0.0,
            "extra": {"riferimento": riferimento, "vettore": "SDA EXPRESS COURIER SPA"},
        }

    def genera_excel(self, ddt_data_list, excel_path):
        from .excel_generator import EneganExcelWriter
        return EneganExcelWriter(self.cfg).genera_excel(ddt_data_list, excel_path)