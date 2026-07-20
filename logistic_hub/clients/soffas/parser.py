import re
from core.plugin_base import ClientPlugin


class SoffasParser(ClientPlugin):
    def __init__(self, config):
        self.id = config["id"]
        self.nome = config["nome"]
        self.pattern_riconoscimento = config["pattern_riconoscimento"]
        self.cfg = config

    def parse_ddt(self, testo_pdf):
        ddt_num = self._estrai_ddt(testo_pdf)
        data = self._estrai_data(testo_pdf)
        bobine = self._estrai_bobine(testo_pdf)
        qualita = self._estrai_qualita(testo_pdf)
        pallet = self._estrai_pallet(testo_pdf)

        return {
            "ddt": ddt_num,
            "data": data,
            "cliente": self.nome,
            "causale": "ingresso",
            "articoli": bobine,
            "totale_colli": pallet or len(bobine),
            "totale_peso": sum(b.get("qta", 0) for b in bobine),
            "extra": {"qualita": qualita, "pallet": pallet},
        }

    def _estrai_ddt(self, testo):
        for label in ["DDT", "Bolla", "PROGRESSIVO", "NUMERO"]:
            m = re.search(rf'{re.escape(label)}\s*(?:BOLLA|BOLLA|BOLL)\s*:?\s*([\d]{{5,}})', testo, re.IGNORECASE)
            if m:
                return m.group(1).strip()
            m = re.search(rf'{re.escape(label)}\s*:?\s*([\d]{{5,}})', testo, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        m = re.search(r'(?:N\.|N°)\s*(\d{3,})', testo)
        if m:
            return m.group(1)
        m = re.search(r'(?:B|G)OLL[A-Z]\s+(\d{5,})', testo, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return ""

    def _estrai_data(self, testo):
        for m in re.finditer(r'(\d{2})[./](\d{2})[./](\d{4})', testo):
            g, mese, a = m.groups()
            if 2020 <= int(a) <= 2030:
                return f"{g:0>2}/{mese:0>2}/{a}"
        return ""

    def _estrai_bobine(self, testo):
        bobine = []
        righe = testo.split("\n")
        for riga in righe:
            # Material code line: 300652N280A 1257007 ... KG 14.900 0
            m = re.search(
                r'^([A-Z0-9]+)\s+(\d+)\s+(.+?)\s+KG\s+([\d.,]+)\s+\d',
                riga, re.IGNORECASE
            )
            if m:
                codice = m.group(1).strip() + m.group(2).strip()
                desc = re.sub(r'\s+', ' ', m.group(3)).strip()
                try:
                    qta = float(m.group(4).replace(",", "."))
                except ValueError:
                    qta = 0
                bobine.append({
                    "codice": codice,
                    "descrizione": desc,
                    "qta": qta,
                    "unita": "KG",
                })
                continue
            # BOBINA prefix pattern
            m = re.search(
                r'(?:BOBINA|BOBB|BOB|B\.)\s*[:#]?\s*([\d\.\-]+)\s+(.+?)\s+([\d.,]+)\s*(KG|MT|PZ|RULLO)?',
                riga, re.IGNORECASE
            )
            if m:
                try:
                    qta = float(m.group(3).replace(",", "."))
                except ValueError:
                    qta = 0
                bobine.append({
                    "codice": m.group(1).strip(),
                    "descrizione": m.group(2).strip(),
                    "qta": qta,
                    "unita": m.group(4) or "KG",
                })
                continue
            # Generic fallback: code + description + qty
            m = re.match(r'\s*([\d\.\-]{3,})\s+(.+?)\s+([\d.,]+)\s*$', riga)
            if m:
                try:
                    qta = float(m.group(3).replace(",", "."))
                except ValueError:
                    qta = 0
                bobine.append({
                    "codice": m.group(1).strip(),
                    "descrizione": m.group(2).strip(),
                    "qta": qta,
                    "unita": "KG",
                })
        return bobine

    def _estrai_qualita(self, testo):
        m = re.search(r'(?:QUALITA|QUALITÀ|TIPO|ARTICOLO)\s*:?\s*(.+?)(?:\n|$)', testo, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return ""

    def _estrai_pallet(self, testo):
        m = re.search(r'(\d+)\s*(?:PLT|PALLET|BANCALE)', testo, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return 0

    def genera_excel(self, ddt_data_list, excel_path):
        from .excel_generator import SoffasExcelWriter
        return SoffasExcelWriter(self.cfg).genera_excel(ddt_data_list, excel_path)