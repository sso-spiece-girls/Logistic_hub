import re


class ERPGenericParser:
    """Parser condiviso per DDT formato SAP/ERP usato da MAGIS, DAS, La Leccia.
    
    Formato DDT:
        Linea 1: <DDT numero> <data> <codici> ... <CLIENTE>
        Linea 2: <codice> <CAUSALE> ... <indirizzo>
        Linea 3: <magazzino> <timestamp>
        Linea 4+: prodotti in formato: <MATERIALE> <CODICE> ... <CONFEZIONE> <QTA> <UNITA>
    """

    def __init__(self, plugin):
        self.plugin = plugin

    def parse_ddt(self, testo_pdf):
        linee = [r for r in testo_pdf.split("\n") if r.strip()]

        ddt_num = self._estrai_ddt(linee)
        data = self._estrai_data(linee)
        cliente, causale, indirizzo = self._estrai_cliente(linee)
        prodotti, totale_pallet = self._estrai_prodotti(linee)
        colli = self._estrai_colli(linee)
        peso = self._estrai_peso(linee)

        return {
            "ddt": ddt_num,
            "data": data,
            "cliente": cliente,
            "causale": causale or "uscita",
            "articoli": prodotti,
            "totale_colli": colli or totale_pallet,
            "totale_pallet": totale_pallet,
            "totale_peso": peso,
            "extra": {"causale_originale": causale, "indirizzo": indirizzo},
        }

    def _estrai_ddt(self, linee):
        for linea in linee:
            m = re.search(r'(\d{4}-\d{8}/\d{3,})', linea)
            if m:
                return m.group(1)
            m = re.search(r'(?:DDT|BOLLA|N[°0]|NUMERO)\s*:?\s*(\d[\d\.\-/A-Z]{2,})', linea, re.IGNORECASE)
            if m:
                return m.group(1)
        for linea in linee:
            m = re.search(r'(\d{3,}/\d{3,})', linea)
            if m:
                return m.group(1)
        return ""

    def _estrai_data(self, linee):
        for linea in linee:
            m = re.search(r'(\d{4}-\d{8}/\d{3,})\s+(\d{2}/\d{2}/\d{4})', linea)
            if m:
                return m.group(2)
        for linea in linee:
            m = re.search(r'(\d{2}/\d{2}/\d{4})', linea)
            if m:
                return m.group(1)
        for linea in linee:
            m = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', linea)
            if m:
                g, mese, a = m.groups()
                if 2020 <= int(a) <= 2030:
                    return f"{g:0>2}/{mese:0>2}/{a}"
        return ""

    def _estrai_cliente(self, linee):
        cliente = ""
        causale = ""
        indirizzo = ""

        # STRATEGIA 1: cliente sulla stessa riga del DDT (formato La Leccia)
        for linea in linee:
            m = re.search(r'(\d{4}-\d{8}/\d{3,})\s+\d{2}/\d{2}/\d{4}\s+\d+\s+\d+\s+\.?\s+(.+)$', linea)
            if m:
                candidato = m.group(2).strip()
                if candidato and candidato != "." and not re.match(r'^[\d\s]+$', candidato):
                    if len(candidato) > 3:
                        cliente = candidato
                        break

        # STRATEGIA 2: cerca riga col cliente (con SRL/SPA) dopo la sezione DDT
        if not cliente:
            ddt_line_idx = -1
            for i, linea in enumerate(linee):
                if re.search(r'\d{4}-\d{8}/\d{3,}', linea):
                    ddt_line_idx = i
                    break

            if ddt_line_idx >= 0:
                for i in range(ddt_line_idx + 1, min(ddt_line_idx + 15, len(linee))):
                    linea = linee[i]
                    rs = linea.strip()
                    if not rs:
                        continue
                    # Skip transaction/warehouse lines
                    if re.search(r'^(STD|RESO|005|DEPOSITO|MAGAZZINO)', rs, re.IGNORECASE):
                        # Check for causale
                        m_causale = re.search(r'(VENDITA|RESO\s*DA\s*C/DEPOS|RESO|TRASFERIMENTO)', rs, re.IGNORECASE)
                        if m_causale and not causale:
                            causale = m_causale.group(1)
                        continue
                    # Match company name
                    if re.search(r'\b(SRL|SPA|SSV|SRV|S\.R\.L\.?|S\.P\.A\.?)\b', rs, re.IGNORECASE):
                        if not re.search(r'(MAGIS|TRASPORT|SPEDIZION|FATTORIA|CEDENTE)', rs, re.IGNORECASE):
                            cliente = rs
                            break

        # STRATEGIA 3: cerca nome cliente (parole maiuscole consecutive) dopo la sezione DDT
        if not cliente and ddt_line_idx >= 0:
            for i in range(ddt_line_idx + 1, min(ddt_line_idx + 20, len(linee))):
                rs = linee[i].strip()
                if re.match(r'^[A-Z][A-Z\s\.\'\-]+$', rs) and len(rs) > 8:
                    if not re.search(r'(STD|DEPOSITO|MAGAZZINO|CEDENTE|PALLET|SCATOLA|CARTONE|VIA\s|VIALE\s)', rs, re.IGNORECASE):
                        # Skip if first word looks like a product code
                        first_word = rs.split()[0] if rs.split() else ""
                        if not re.search(r'\d', first_word) or len(first_word) > 6:
                            cliente = rs
                            break

        # STRATEGIA 4: extract from DDT line itself (any text after codes)
        if not cliente:
            for linea in linee:
                m = re.search(r'(\d{4}-\d{8}/\d{3,})', linea)
                if m:
                    parts = linea.split()
                    if len(parts) >= 6:
                        after = " ".join(parts[5:]).strip()
                        if after and after != "." and len(after) > 5:
                            cliente = after
                            break

        # Clean up
        if cliente:
            cliente = re.sub(r'^\s*\.?\s*', '', cliente).strip()
            cliente = re.sub(r'\s+', ' ', cliente)


        return cliente, causale, indirizzo

    def _estrai_prodotti(self, linee):
        prodotti = []
        for linea in linee:
            rs = linea.strip()
            if not rs:
                continue
            # Pattern principale: MATERIALE CODICE ... CONFEZIONE QTA UNITA
            m = re.search(r'([A-Z]+)\s+([\w-]+)\s+.*?(BIG\s*BAG|SMALL\s*BAG|BAG)\s+(\d+)\s+(PLT|PZ|KG)', rs, re.IGNORECASE)
            if m:
                prodotti.append({
                    "codice": m.group(2).strip(),
                    "descrizione": f"{m.group(1)} {m.group(2)} {m.group(3)}",
                    "qta": int(m.group(4)),
                    "unita": m.group(5),
                })
                continue
            # Fallback: codice flessibile
            m = re.search(r'([A-Z]{2,10}[\s-]*\d{2,6})\s+.*?(\d+)\s+(PLT|PZ|KG|BAG|CART)', rs, re.IGNORECASE)
            if m:
                prodotti.append({
                    "codice": m.group(1).strip(),
                    "descrizione": "",
                    "qta": int(m.group(2)),
                    "unita": m.group(3),
                })
                continue
            # Generic product line
            skip_words = r'^(PESO|TOTALE|TOTAL|DATA|DDT|NOTA|COLLI|SPETT|DESTINATARIO|FIRMA|CAUSALE|VETTORE|PROVENIENZA|RIF|STD|MITTENTE|PAGINA|SEGUE|TRASPORTO)'
            if re.search(skip_words, rs, re.IGNORECASE):
                continue
            m = re.search(r'(?:ART\.?\s*|N\.\s*|CODICE\s*)?([A-Z0-9][-A-Z0-9]{2,6})\s+(.+?)\s+(\d+)\s+(PLT|PZ|KG|BAG|CART)', rs, re.IGNORECASE)
            if m:
                prodotti.append({
                    "codice": m.group(1).strip(),
                    "descrizione": m.group(2).strip(),
                    "qta": int(m.group(3)),
                    "unita": m.group(4),
                })

        # Extract total pallet count
        totale_pallet = 0
        for linea in linee:
            m = re.search(r'(\d+)\s+PALLET\s+.*?(\d+)', linea, re.IGNORECASE)
            if m:
                totale_pallet = int(m.group(2))
                break
            m = re.search(r'(\d+)\s+PALLET', linea, re.IGNORECASE)
            if m:
                totale_pallet = int(m.group(1))

        return prodotti, totale_pallet

    def _estrai_colli(self, linee):
        for linea in linee:
            m = re.search(r'(?:TOTALE\s+COLLI|N\.\s*COLLI|COLLI)\s*:?\s*(\d+)', linea, re.IGNORECASE)
            if m:
                return int(m.group(1))
            m = re.search(r'(\d+)\s+COLLI', linea, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return 0

    def _estrai_peso(self, linee):
        for linea in linee:
            m = re.search(r'(?:PESO\s*(?:LORDO|NETTO|KG|TOTALE)?)\s*:?\s*([\d.,]+)\s*(?:KG)?', linea, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1).replace(",", "."))
                except ValueError:
                    pass
        return 0.0