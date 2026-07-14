from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN


class EneganExcelWriter:
    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        wb, esistente = apri_o_crea_excel(excel_path)
        if not esistente:
            ws = wb.active
            ws.title = "DDT ENEGAN"
            headers = ["Data", "DDT", "Cliente DDT", "Cliente Finale", "Articolo", "Qta", "Unità", "Note"]
            for i, h in enumerate(headers, 1):
                ws.cell(row=1, column=i, value=h)
            stile_intestazione(ws, 1, len(headers))
            for col, w in zip("ABCDEFGH", [14, 22, 25, 28, 16, 10, 8, 30]):
                ws.column_dimensions[col].width = w

        ws = wb["DDT ENEGAN"] if "DDT ENEGAN" in wb.sheetnames else wb.active
        for ddt in ddt_data_list:
            prox_riga = ws.max_row + 1
            stile_cella(ws, prox_riga, 1, ddt.get("data", ""), align=CENTER_ALIGN)
            stile_cella(ws, prox_riga, 2, ddt.get("ddt", ""), align=CENTER_ALIGN)
            stile_cella(ws, prox_riga, 3, ddt.get("extra", {}).get("cliente_ddt", ""))
            stile_cella(ws, prox_riga, 4, ddt.get("cliente", ""))
            art = "; ".join([f"{a.get('codice', '')} {a.get('descrizione', '')}" for a in ddt.get("articoli", [])])
            stile_cella(ws, prox_riga, 5, art)
            stile_cella(ws, prox_riga, 6, sum(a.get("qta", 0) for a in ddt.get("articoli", [])), align=CENTER_ALIGN)
            stile_cella(ws, prox_riga, 7, ddt.get("articoli", [{}])[0].get("unita", "") if ddt.get("articoli") else "", align=CENTER_ALIGN)
            stile_cella(ws, prox_riga, 8, "")

        wb.save(excel_path)
        return excel_path