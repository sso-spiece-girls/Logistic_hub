from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN


class SoffasExcelWriter:
    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        wb, esistente = apri_o_crea_excel(excel_path)
        if not esistente:
            ws = wb.active
            ws.title = "DDT SOFFAS"
            headers = ["Data", "DDT", "Qualità", "Bobina", "Peso (Kg)", "Pallet", "Note"]
            for i, h in enumerate(headers, 1):
                ws.cell(row=1, column=i, value=h)
            stile_intestazione(ws, 1, len(headers))
            for col, w in zip("ABCDEFG", [14, 22, 20, 18, 12, 10, 30]):
                ws.column_dimensions[col].width = w

        ws = wb["DDT SOFFAS"] if "DDT SOFFAS" in wb.sheetnames else wb.active
        for ddt in ddt_data_list:
            extra = ddt.get("extra", {})
            for art in ddt.get("articoli", []):
                prox_riga = ws.max_row + 1
                stile_cella(ws, prox_riga, 1, ddt.get("data", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 2, ddt.get("ddt", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 3, extra.get("qualita", ""))
                stile_cella(ws, prox_riga, 4, art.get("codice", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 5, art.get("qta", 0), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 6, extra.get("pallet", 0), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 7, art.get("descrizione", ""))

        wb.save(excel_path)
        return excel_path