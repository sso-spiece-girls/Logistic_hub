from core.excel_writer import apri_o_crea_excel, stile_intestazione, stile_cella, CENTER_ALIGN


CLIENT_EXCEL_CONFIGS = {}

_CONFIGS = [
    {
        "id": "das",
        "sheet_name": "DDT DAS",
        "headers": ["Data", "DDT", "Pallet ID", "Cliente", "Indirizzo", "Peso (Kg)", "Note"],
        "col_widths": [14, 22, 20, 25, 30, 12, 30],
        "row_builder": lambda ddt: [
            ddt.get("data", ""),
            ddt.get("ddt", ""),
            ", ".join(ddt.get("extra", {}).get("pallet_ids", [])),
            ddt.get("cliente", ""),
            ddt.get("extra", {}).get("localita", ""),
            ddt.get("totale_peso", 0),
            ", ".join(a.get("codice", "") for a in ddt.get("articoli", [])),
        ],
    },
]

_SPECIAL_WRITERS = {}


def register_excel_config(config):
    CLIENT_EXCEL_CONFIGS[config["id"]] = config


def register_special_writer(client_id, writer_class):
    _SPECIAL_WRITERS[client_id] = writer_class


def genera_excel_per_cliente(client_id, ddt_data_list, excel_path):
    if client_id in _SPECIAL_WRITERS:
        return _SPECIAL_WRITERS[client_id].genera_excel(ddt_data_list, excel_path)

    config = CLIENT_EXCEL_CONFIGS.get(client_id)
    if not config:
        raise ValueError(f"Nessuna configurazione Excel per cliente: {client_id}")

    wb, esistente = apri_o_crea_excel(excel_path)
    if not esistente:
        ws = wb.active
        ws.title = config["sheet_name"]
        for i, h in enumerate(config["headers"], 1):
            ws.cell(row=1, column=i, value=h)
        stile_intestazione(ws, 1, len(config["headers"]))
        for col, w in zip("ABCDEFGHIJ", config["col_widths"]):
            ws.column_dimensions[col].width = w

    ws = wb[config["sheet_name"]] if config["sheet_name"] in wb.sheetnames else wb.active
    for ddt in ddt_data_list:
        prox_riga = ws.max_row + 1
        valori = config["row_builder"](ddt)
        for i, v in enumerate(valori, 1):
            align = CENTER_ALIGN if i in config.get("center_cols", [1, 2, 6]) else None
            stile_cella(ws, prox_riga, i, v, align=align)

    wb.save(excel_path)
    return excel_path
