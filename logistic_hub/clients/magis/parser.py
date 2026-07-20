from core.plugin_base import ClientPlugin
from core.erp_parser import ERPGenericParser


class MagisParser(ClientPlugin):
    def __init__(self, config):
        self.id = config["id"]
        self.nome = config["nome"]
        self.pattern_riconoscimento = config["pattern_riconoscimento"]
        self.cfg = config
        self._erp = ERPGenericParser(self)

    def parse_ddt(self, testo_pdf):
        return self._erp.parse_ddt(testo_pdf)

    def genera_excel(self, ddt_data_list, excel_path):
        from .excel_generator import MagisExcelWriter
        return MagisExcelWriter(self.cfg).genera_excel(ddt_data_list, excel_path)