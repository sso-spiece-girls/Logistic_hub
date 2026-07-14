import re
from core.plugin_base import ClientPlugin
from core.erp_parser import ERPGenericParser


class _LaLecciaERP(ERPGenericParser):
    def _estrai_prodotti(self, linee):
        prodotti = []
        for linea in linee:
            rs = linea.strip()
            if not rs or rs.startswith("."):
                continue
            m = re.search(
                r'([A-Z0-9][-A-Z0-9.]{3,20})\s{2,}(.+?)\s{2,}(\d+)\s+(BT\.?|NR\.?)\s+(\d+)',
                rs, re.IGNORECASE
            )
            if m:
                desc = re.sub(r'\s+', ' ', m.group(2)).strip()
                prodotti.append({
                    "codice": m.group(1).strip(),
                    "descrizione": desc,
                    "qta": int(m.group(3)),
                    "unita": m.group(4).rstrip("."),
                })
        totale_pallet = 0
        for linea in linee:
            m = re.search(r'(\d+)\s+PALLET', linea, re.IGNORECASE)
            if m:
                totale_pallet = int(m.group(1))
                break
        return prodotti, totale_pallet


class LaLecciaParser(ClientPlugin):
    def __init__(self, config):
        self.id = config["id"]
        self.nome = config["nome"]
        self.pattern_riconoscimento = config["pattern_riconoscimento"]
        self.cfg = config
        self._erp = _LaLecciaERP(self)

    def parse_ddt(self, testo_pdf):
        return self._erp.parse_ddt(testo_pdf)

    def genera_excel(self, ddt_data_list, excel_path):
        from .excel_generator import LaLecciaExcelWriter
        return LaLecciaExcelWriter(self.cfg).genera_excel(ddt_data_list, excel_path)