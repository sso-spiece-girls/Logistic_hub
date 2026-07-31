import re
from .base import FornitorePlugin
from core.normalize import parse_italian_number


class SaleriParser(FornitorePlugin):
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

        # SPLO<codice> <N> pallet <kg> kg
        for m in re.finditer(
            r'([a-z]{2,}\d{4,})\s+(\d{1,3})\s*pallet\s+([\d.,]+)\s*kg',
            testo_norm
        ):
            key = m.group(1)
            if key not in visti:
                visti.add(key)
                righe.append({
                    "descrizione": m.group(1).upper(),
                    "quantita": int(m.group(2)),
                    "pallet": int(m.group(2)),
                    "unita_misura": "pallet",
                    "peso_kg": parse_italian_number(m.group(3)),
                })

        # Only use numeric code pattern if no SPLO pattern matched
        if not righe:
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
                        "peso_kg": parse_italian_number(m.group(2)),
                    })

        return righe
