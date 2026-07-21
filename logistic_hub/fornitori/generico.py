import re
from .base import FornitorePlugin
from core.normalize import parse_italian_number


class GenericoParser(FornitorePlugin):
    def __init__(self, config):
        super().__init__(config)
        self._nome_rilevato = ""

    def riconosci(self, testo_pdf):
        return False  # Only used as explicit fallback, never auto-detected

    def estrai_fornitore(self, testo_pdf):
        if self._nome_rilevato:
            return self._nome_rilevato
        for pattern, nome in [
            (re.compile(r'(?i)BASE\s*SPA'), "BASE SPA"),
            (re.compile(r'(?i)CARTIERE?\s*CARRARA'), "Cartiere Carrara"),
            (re.compile(r'(?i)PRATOLUNGO'), "Pratolungo"),
            (re.compile(r'(?i)ESSITY'), "Essity"),
            (re.compile(r'(?i)PECTEN'), "Pecten"),
            (re.compile(r'(?i)ZIGNAGO'), "Zignago"),
            (re.compile(r'(?i)SALERI'), "Saleri"),
            (re.compile(r'(?i)NSW'), "NSW"),
            (re.compile(r'(?i)CELTEX'), "Celtex"),
        ]:
            if pattern.search(testo_pdf):
                self._nome_rilevato = nome
                return nome
        return ""

    def parse_bolla(self, testo_pdf):
        fornitore = self.estrai_fornitore(testo_pdf)
        righe = self._estrai_righe(testo_pdf)
        return {
            "fornitore": fornitore or self.nome,
            "numero_bolla": self.estrai_numero_bolla(testo_pdf),
            "data_arrivo": self.estrai_data(testo_pdf),
            "righe": righe,
        }

    def _estrai_righe(self, testo):
        righe = []
        visti = set()
        testo_norm = testo.lower().replace("_", " ").replace("|", " ")

        # 1) PICKING format
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

        # 2) PICKING no parentesi
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

        # 3) SPLO/code + pallet + kg
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

        # 4) 6+ digit code + pallet + kg (only if no SPLO matched already)
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

        # 5) code — N colli
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

        # 6) N colli ... kg (generic)
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
                    "peso_kg": parse_italian_number(m.group(2)),
                })

        return righe
