import re


class FornitorePlugin:
    def __init__(self, config):
        self.id = config["id"]
        self.nome = config["nome"]
        self.pattern_riconoscimento = config.get("pattern_riconoscimento")

    def riconosci(self, testo_pdf):
        if self.pattern_riconoscimento:
            return bool(self.pattern_riconoscimento.search(testo_pdf))
        return False

    def parse_bolla(self, testo_pdf):
        raise NotImplementedError

    def estrai_fornitore(self, testo_pdf):
        return self.nome if self.nome != "Generico" else ""

    def estrai_numero_bolla(self, testo_pdf):
        for pattern in [
            re.compile(r'(?i)(?:DDT|D\.D\.T\.|BOLLA|DOCUMENTO\s+DI\s+TRASPORTO)\s*[Nn°.]*\s*(\d{4,10})'),
            re.compile(r'(?i)(?:N[ro°.]*|NUMERO)\s*[.:]*\s*(\d{4,10})'),
            re.compile(r'(?i)(?:DDT|BOLLA)\s*[Nn°.]*\s*(\d{4,10})'),
        ]:
            m = pattern.search(testo_pdf)
            if m:
                return m.group(1)
        return ""

    def estrai_data(self, testo_pdf):
        from datetime import datetime
        mesi = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
                "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
                "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
        for day, month, year in re.findall(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', testo_pdf):
            if len(year) == 2:
                year = "20" + year
            try:
                y = int(year)
                if 2020 <= y <= 2030:
                    return f"{y:04d}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                pass
        m = re.search(r'(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{2,4})', testo_pdf, re.IGNORECASE)
        if m:
            g, mese_testo, a = m.groups()
            if len(a) == 2:
                a = "20" + a
            mese_num = mesi.get(mese_testo.lower(), 1)
            try:
                y = int(a)
                if 2020 <= y <= 2030:
                    return f"{y:04d}-{mese_num:02d}-{int(g):02d}"
            except ValueError:
                pass
        return ""
