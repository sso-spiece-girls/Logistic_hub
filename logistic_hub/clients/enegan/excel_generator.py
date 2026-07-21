from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN, LEFT_ALIGN, crea_backup


class EneganExcelWriter:
    """Scrive DDT nel file Enegan — trova la prima riga vuota e scrive i dati.
    Il file ha righe 12-699 pre-formattate con formule di calcolo costi.
    """

    DATA_START_ROW = 12
    DATA_END_ROW = 699

    def __init__(self, config):
        self.cfg = config

    def genera_excel(self, ddt_data_list, excel_path):
        crea_backup(excel_path)
        wb, esistente = apri_o_crea_excel(excel_path)

        if not esistente:
            self._crea_struttura_base(wb)

        ws = wb["DDT ENEGAN"] if "DDT ENEGAN" in wb.sheetnames else wb.active

        for ddt in ddt_data_list:
            for art in ddt.get("articoli", []):
                target_row = self._trova_riga_vuota(ws)
                if target_row is None:
                    continue

                # Col A: Data
                stile_cella(ws, target_row, 1, ddt.get("data", ""), align=CENTER_ALIGN)
                # Col B: DDT
                stile_cella(ws, target_row, 2, ddt.get("ddt", ""), align=CENTER_ALIGN)
                # Col C: Cliente
                stile_cella(ws, target_row, 3, ddt.get("cliente", ""), align=LEFT_ALIGN)
                # Col E: Pz sfusi (quantità)
                qta = art.get("qta", 0)
                stile_cella(ws, target_row, 5, qta, align=CENTER_ALIGN)
                # Le colonne G, K, M, N hanno già le formule di calcolo costo

        wb.save(excel_path)
        return excel_path

    def _trova_riga_vuota(self, ws):
        """Trova la prima riga dati con colonna A vuota."""
        for row in range(self.DATA_START_ROW, self.DATA_END_ROW + 1):
            a_val = ws.cell(row=row, column=1).value
            if a_val is None or str(a_val).strip() == "":
                return row
        return None

    def _crea_struttura_base(self, wb):
        """Crea struttura base se il file non esiste."""
        ws = wb.active
        ws.title = "DDT ENEGAN"
        headers = ["Data", "DDT", "Cliente DDT", "Cliente Finale", "Articolo", "Qta", "Unita", "Note"]
        for i, h in enumerate(headers, 1):
            ws.cell(row=1, column=i, value=h)
        stile_intestazione(ws, 1, len(headers))
        for col, w in zip("ABCDEFGH", [14, 16, 20, 20, 28, 10, 10, 30]):
            ws.column_dimensions[col].width = w