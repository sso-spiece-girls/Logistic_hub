import re
from core.plugin_base import ClientPlugin


class EllegroupParser(ClientPlugin):
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

        # Header detection
        for i, linea in enumerate(linee):
            m = re.search(r"D\.D\.T\.\s*n[°0]\s*([\d]+/[\d]+)\s+del\s+(\d{2}/\d{2}/\d{4})", linea, re.IGNORECASE)
            if m:
                ddt_num = m.group(1)
                data = m.group(2)
                break

        if not ddt_num:
            for linea in linee:
                m = re.search(r"D\.D\.T\.\s*n[°0]\s*([\d]+/[\d]+)", linea, re.IGNORECASE)
                if m:
                    ddt_num = m.group(1)
                m = re.search(r"del\s+(\d{2}/\d{2}/\d{4})", linea, re.IGNORECASE)
                if m:
                    data = m.group(1)

        if not data:
            for linea in linee:
                m = re.search(r'(\d{2}/\d{2}/\d{4})', linea)
                if m:
                    data = m.group(1)
                    break

        # Client name: first uppercase line after "Cliente" header, excluding header labels
        capture_cliente = False
        for i, linea in enumerate(linee):
            if linea.strip() == "Cliente":
                capture_cliente = True
                continue
            if capture_cliente and linea.strip() and linea.strip() not in (
                "Destinazione Merce", "Pagina:", "Partita Iva", "Codice Fiscale", "Porto:",
                "Descrizione", "Qt.", "UMP", "Idem"
            ):
                # Skip the page number line
                if re.match(r'^\d+$', linea.strip()):
                    continue
                # Skip if it's the address continuation
                if re.match(r'^Via\s|^Viale\s|^C\.so\s|^Piazza\s|^Localit', linea, re.IGNORECASE):
                    continue
                if not re.match(r'^[0-9%]', linea.strip()) and len(linea.strip()) > 3:
                    cliente = linea.strip()
                    break

        if not cliente:
            for linea in linee:
                ll = linea.strip()
                if ll in ("ELLEGROUP", "ELLE GROUP"):
                    cliente = ll
                    break

        # Fixed pattern for MAGRO sub-client
        if not cliente:
            for linea in linee:
                if "MAGRO" in linea.upper():
                    cliente = linea.strip()
                    break

        # Extract articles: read multi-line blocks
        # Pattern: code on its own line, then 1-2 description lines, then "NR", then 3 numbers
        idx = 0
        while idx < len(linee):
            linea = linee[idx]
            ls = linea.strip()

            # Check if this line is an article code (like MB0634HG3.001.TU or MH0024BH3)
            is_article = (
                re.match(r'^[A-Z]{2}\d{4}[A-Z]{1,2}\d{1,2}\.\d{3}\.[A-Z]{2}$', ls, re.IGNORECASE) or
                re.match(r'^[A-Z]{2}\d{4}[A-Z]{1,2}\d{1,2}$', ls, re.IGNORECASE)
            )
            if is_article:
                codice = ls
                # Read description lines until we hit "NR"
                desc_lines = []
                idx += 1
                while idx < len(linee) and linee[idx].strip() != "NR":
                    if not re.match(r'^[A-Z]{2}\d{4}', linee[idx].strip()):
                        d = linee[idx].strip()
                        if d and not re.match(r'^(SEGUE|Colli|Pz x|Tot\.|D\.D\.T|Cliente|Destinazione|Pagina|Partita|Codice|Porto|Descrizione|Qt\.|UMP|Mittente|Trasporto|Aspetto|Totale|Data|Firma|Vettore|Peso|Note|Informazioni|Volume)', d):
                            desc_lines.append(d)
                    idx += 1

                descrizione = " ".join(desc_lines).strip()
                if not descrizione:
                    descrizione = codice

                # Now reading numbers after NR
                numeri = []
                idx += 1
                while idx < len(linee) and len(numeri) < 3:
                    n_line = linee[idx].strip()
                    if re.match(r'^\d+$', n_line):
                        numeri.append(int(n_line))
                    idx += 1
                # Skip past "SEGUE >>>" and other non-article lines
                while idx < len(linee) and not re.match(r'^[A-Z]{2}\d{4}', linee[idx].strip()) and linee[idx].strip() not in ("NR",):
                    if re.match(r'^\d+$', linee[idx].strip()):
                        break
                    idx += 1

                qta = max(numeri) if numeri else 0
                articoli.append({
                    "codice": codice,
                    "descrizione": descrizione,
                    "qta": qta,
                    "unita": "PZ",
                })
            else:
                idx += 1

        # Totale colli
        totale_colli = 0
        totale_pezzi = 0
        for i, linea in enumerate(linee):
            m = re.search(r'Totale\s+colli\s*:?\s*(\d+)', linea, re.IGNORECASE)
            if m:
                totale_colli = int(m.group(1))
                break
        for i, linea in enumerate(linee):
            m = re.search(r'Totale\s+Pezzi\s*:?\s*([\d.]+)', linea, re.IGNORECASE)
            if m:
                totale_pezzi = int(m.group(1).replace(".", ""))
                break

        if not totale_colli:
            # Look for the total line near "Mittente"
            for i, linea in enumerate(linee):
                if linea.strip() == "Mittente" and i + 1 < len(linee):
                    try:
                        totale_colli = int(linee[i + 1].strip())
                    except ValueError:
                        pass
                    break

        return {
            "ddt": ddt_num,
            "data": data,
            "cliente": cliente,
            "causale": "uscita",
            "articoli": articoli,
            "totale_colli": totale_colli,
            "totale_peso": 0.0,
            "extra": {
                "provincia": self._estrai_provincia(testo_pdf),
                "totale_pezzi": totale_pezzi,
            },
        }

    def _estrai_provincia(self, testo):
        m = re.search(r'\(([A-Z]{2})\)', testo)
        if m:
            return m.group(1)
        return ""

    def genera_excel(self, ddt_data_list, excel_path):
        from .excel_generator import EllegroupExcelWriter
        return EllegroupExcelWriter(self.cfg).genera_excel(ddt_data_list, excel_path)