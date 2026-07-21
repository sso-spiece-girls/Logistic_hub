from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN, crea_backup, LEFT_ALIGN


class DasExcelWriter:
    """Scrive DDT nel file Excel DAS — semplice append dopo l'ultima riga."""

    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        crea_backup(excel_path)
        wb, esistente = apri_o_crea_excel(excel_path)
        if not esistente:
            ws = wb.active
            ws.title = "DDT DAS"
            headers = ["Data", "DDT", "Pallet ID", "Cliente", "Indirizzo", "Peso (Kg)", "Note"]
            for i, h in enumerate(headers, 1):
                stile_intestazione(ws, 1, len(headers))
                ws.cell(row=1, column=i, value=h)
            stile_intestazione(ws, 1, len(headers))
            for col, w in zip("ABCDEFG", [14, 20, 14, 28, 28, 14, 30]):
                ws.column_dimensions[col].width = w

        ws = wb["DDT DAS"] if "DDT DAS" in wb.sheetnames else wb.active
        for ddt in ddt_data_list:
            extra = ddt.get("extra", {})
            for art in ddt.get("articoli", []):
                prox_riga = ws.max_row + 1
                stile_cella(ws, prox_riga, 1, ddt.get("data", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 2, ddt.get("ddt", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 3, extra.get("pallet_id", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 4, ddt.get("cliente", ""), align=LEFT_ALIGN)
                stile_cella(ws, prox_riga, 5, extra.get("indirizzo", ""), align=LEFT_ALIGN)
                stile_cella(ws, prox_riga, 6, art.get("qta", 0), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 7, "")

        wb.save(excel_path)
        return excel_path