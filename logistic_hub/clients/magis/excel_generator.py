from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN, LEFT_ALIGN, crea_backup


class MagisExcelWriter:
    """Scrive DDT nel file Excel Magis — semplice append."""

    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        crea_backup(excel_path)
        wb, esistente = apri_o_crea_excel(excel_path)

        if not esistente:
            # BIG BAG
            ws1 = wb.active
            ws1.title = "BIG BAG"
            headers1 = ["Data", "DDT", "Cliente", "PLT OUT", "Note"]
            self._scrivi_headers(ws1, headers1, [14, 20, 28, 14, 30])

            # SMALL BAG
            ws2 = wb.create_sheet("SMALL BAG")
            self._scrivi_headers(ws2, headers1, [14, 20, 28, 14, 30])

            # GIACENZE
            ws3 = wb.create_sheet("GIACENZE")
            headers3 = ["Deposito", "Articolo", "Qta Iniziale", "Uscite", "Qta Finale"]
            self._scrivi_headers(ws3, headers3, [18, 28, 14, 14, 14])

        for ddt in ddt_data_list:
            for art in ddt.get("articoli", []):
                sheet_name = "BIG BAG"  # default
                desc = f"{art.get('codice', '')} {art.get('descrizione', '')}"
                # Determina il foglio in base alla descrizione
                if "small" in desc.lower() or "sm" in art.get("codice", "").lower():
                    sheet_name = "SMALL BAG"

                ws = wb[sheet_name]
                prox_riga = ws.max_row + 1
                stile_cella(ws, prox_riga, 1, ddt.get("data", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 2, ddt.get("ddt", ""), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 3, ddt.get("cliente", ""), align=LEFT_ALIGN)
                stile_cella(ws, prox_riga, 4, art.get("qta", 0), align=CENTER_ALIGN)
                stile_cella(ws, prox_riga, 5, "")

        wb.save(excel_path)
        return excel_path

    def _scrivi_headers(self, ws, headers, widths):
        for i, h in enumerate(headers, 1):
            ws.cell(row=1, column=i, value=h)
        stile_intestazione(ws, 1, len(headers))
        for col_letter, w in zip("ABCDEFGHIJ"[:len(widths)], widths):
            ws.column_dimensions[col_letter].width = w