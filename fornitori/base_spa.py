import re
from .base import FornitorePlugin
from core.normalize import parse_italian_number


class BaseSpaParser(FornitorePlugin):
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

        # PICKING<code> <N> pallet (<N> colli) <kg>
        for m in re.finditer(
            r'(?:picking|picuns|pickins|piceing|piking)'
            r'\s*(\d{4,})\s+(\d{1,3})\s*pallet\s*[\(\[]?\s*(\d{1,6})\s*'
            r'(?:coll[iì]?|cartoni(?:\s+tot)?|colli)[^)\]\n]{0,10}[\)\]]?'
            r'(?:\s+([\d.,]+)\s*kg)?',
            testo_norm, re.IGNORECASE
        ):
            key = m.group(1)
            if key not in visti:
                visti.add(key)
                peso = parse_italian_number(m.group(4)) if m.group(4) else 0
                righe.append({
                    "descrizione": f"PICKING {m.group(1)}",
                    "quantita": int(m.group(3)),
                    "pallet": int(m.group(2)),
                    "unita_misura": "colli",
                    "peso_kg": peso,
                })

        # PICKING senza parentesi (OCR rotto)
        for m in re.finditer(
            r'(?:picking|picuns|pickins|piceing|piking)'
            r'\s*(\d{4,})\s+(\d{1,3})\s*pallet\s+[\(\[]?(\d{1,6})\s+\S*\s*([\d.,]+)\s*kg',
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
                    "peso_kg": parse_italian_number(m.group(4)),
                })

        return righe
