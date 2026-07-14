from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN


class LaLecciaExcelWriter:
    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        wb, esistente = apri_o_crea_excel(excel_path)
        if not esistente:
            ws = wb.active
            ws.title = "DDT LA LECCIA"
            headers = ["Data", "DDT", "Ristorante", "Articolo", "Qta", "Importo", "Note"]
            for i, h in enumerate(headers, 1):
                ws.cell(row=1, column=i, value=h)
            stile_intestazione(ws, 1, len(headers))
            for col, w in zip("ABCDEFG", [14, 16, 28, 30, 10, 14, 30]):
                ws.column_dimensions[col].width = w

        ws = wb["DDT LA LECCIA"] if "DDT LA LECCIA" in wb.sheetnames else wb.active
        for ddt in ddt_data_list:
            extra = ddt.get("extra", {})
            for art in ddt.get("articoli", []):
                prox_riga = ws.max_row + 1
                stile_cella(ws, prox_riga, 1, ddt.get("data", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 2, ddt.get("ddt", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 3, extra.get("ristorante", ddt.get("cliente", "")))
                stile_cella(ws, prox_riga, 4, f"{art.get('codice', '')} {art.get('descrizione', '')}")
                stile_cella(ws, prox_riga, 5, art.get("qta", 0), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 6, extra.get("importo_totale", 0), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 7, "")

        wb.save(excel_path)
        return excel_path