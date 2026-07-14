import os
import shutil
from datetime import datetime
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from core.excel_writer import stile_intestazione, stile_cella, CENTER_ALIGN

# Template: use the real Excel file as basis for structure
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.xlsx")


class EllegroupExcelWriter:
    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        base = os.path.dirname(excel_path)
        if os.path.exists(TEMPLATE_PATH):
            wb = load_workbook(TEMPLATE_PATH)
            esistente = True
        else:
            wb = self._creda_struttura_base()
            esistente = False

        ws_usciti = wb["PROSPETTO USCITE"] if "PROSPETTO USCITE" in wb.sheetnames else wb.active
        ws_ingressi = wb["PROSPETTO INGRESSI"] if "PROSPETTO INGRESSI" in wb.sheetnames else None

        # Clear old data (rows 15+)
        for ws in [ws_usciti]:
            if ws.max_row >= 15:
                ws.delete_rows(15, ws.max_row - 14)

        data_row = 15
        for ddt in ddt_data_list:
            extra = ddt.get("extra", {})
            agenti = extra.get("agenti", {})
            ws_usciti.cell(row=data_row, column=1, value=ddt.get("data", ""))
            ws_usciti.cell(row=data_row, column=2, value=ddt.get("cliente", ""))
            ws_usciti.cell(row=data_row, column=4, value=ddt.get("ddt", ""))
            ws_usciti.cell(row=data_row, column=6, value=extra.get("pallet", ""))

            for col in (1, 2, 4, 6):
                ws_usciti.cell(row=data_row, column=col).alignment = CENTER_ALIGN

            # Marina Galanti: H(8)=colli, J(10)=pezzi, K(11)=picking
            if "marina" in agenti:
                a = agenti["marina"]
                ws_usciti.cell(row=data_row, column=8, value=a.get("colli", ""))
                ws_usciti.cell(row=data_row, column=10, value=a.get("pezzi", ""))
                ws_usciti.cell(row=data_row, column=11, value=a.get("picking", ""))

            # Gianmarco Venturi: P(16)=colli, R(18)=pezzi, S(19)=picking
            if "gmv" in agenti:
                a = agenti["gmv"]
                ws_usciti.cell(row=data_row, column=16, value=a.get("colli", ""))
                ws_usciti.cell(row=data_row, column=18, value=a.get("pezzi", ""))
                ws_usciti.cell(row=data_row, column=19, value=a.get("picking", ""))

            # Marta Marzotto: X(24)=colli, Z(26)=pezzi, AA(27)=picking
            if "marta" in agenti:
                a = agenti["marta"]
                ws_usciti.cell(row=data_row, column=24, value=a.get("colli", ""))
                ws_usciti.cell(row=data_row, column=26, value=a.get("pezzi", ""))
                ws_usciti.cell(row=data_row, column=27, value=a.get("picking", ""))

            data_row += 1

        wb.save(excel_path)
        wb.close()
        return excel_path

    def _creda_struttura_base(self):
        wb = Workbook()
        # Create PROSPETTO USCITE
        ws = wb.active
        ws.title = "PROSPETTO USCITE"
        headers_usciti = [
            "DATA", "CLIENTE", "APERTURA COLLI", "DDT",
            "LAVORAZIONE 1-2-3-4-5", "PALLET", "FASCIATURA PALLET",
            "COLLI SPEDIZIONE", "ATTIVITA' PICK",
            "PEZZI", "SI (1 PZ) NO (1 PZ)",
            "PICKING (DA 1 PZ)", "PICKING (DA 2 PZ)", "LAVORAZIONE",
            "", "", "", "", "", "",
            "", "", "", "", "", "", "", "",
            "COSTI SQ (MAR.GAL.)", "COSTI SQ (GMV)", "COSTI SQ (MARZOTTO)", "FASCIATURA PALLET",
        ]
        for i, h in enumerate(headers_usciti, 1):
            ws.cell(row=14, column=i, value=h)
        stile_intestazione(ws, 14, len(headers_usciti))

        ws = wb.create_sheet("PROSPETTO INGRESSI")
        headers_ingressi = [
            "CNTR / DDT", "DATA", "N. COLLI", "SVUOTAMENTO",
            "", "N. COLLI", "SVUOTAMENTO",
            "", "N. COLLI", "SVUOTAMENTO",
            "COSTI SQ (MAR.GAL.)", "COSTI SQ (GMV)", "COSTI SQ (MARZOTTO)",
        ]
        for i, h in enumerate(headers_ingressi, 1):
            ws.cell(row=14, column=i, value=h)
        stile_intestazione(ws, 14, len(headers_ingressi))

        return wb
