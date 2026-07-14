import re
from .base import FornitorePlugin


class CarraraParser(FornitorePlugin):
    def parse_bolla(self, testo_pdf):
        righe = self._estrai_righe(testo_pdf)
        return {
            "fornitore": self.nome,
            "numero_bolla": self.estrai_numero_bolla(testo_pdf),
            "data_arrivo": self.estrai_data(testo_pdf),
            "righe": righe,
        }

    def _estrai_righe(self, testo):
        righe = []
        visti = set()
        testo_norm = testo.lower().replace("_", " ").replace("|", " ")

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

        for m in re.finditer(
            r'(\d{1,5})\s*colli.*?([\d.,]+)\s*kg',
            testo_norm
        ):
            key = m.group(1)
            if key not in visti:
                visti.add(key)
                righe.append({
                    "descrizione": "",
                    "quantita": int(m.group(1)),
                    "pallet": 0,
                    "unita_misura": "colli",
                    "peso_kg": float(m.group(2).replace(",", ".")),
                })

        return righe
