import re

PLUGIN_CONFIG = {
    "id": "soffas",
    "nome": "SOFFAS",
    "pattern_riconoscimento": re.compile(r'(?:SOFFAS|SOFFA\'?S|Soffas)', re.IGNORECASE),
    "pattern_ddt": re.compile(r'(?:DDT|BOLLA|PROGRESSIVO)\s*:?\s*([\d\.\-/A-Z]{2,})', re.IGNORECASE),
    "pattern_bobina": re.compile(
        r'(BOBINA|BOBB|BOB|B\.)?\s*[:#]?\s*(\d[\d\.\-]*)\s+(.+?)\s+(\d+\.?\d*)\s*(KG|MT|PZ|RULLO)?',
        re.IGNORECASE
    ),
    "pattern_pallet": re.compile(r'(\d+)\s*(?:PLT|PALLET|BANCALE)', re.IGNORECASE),
    "pattern_qualita": re.compile(r'(QUALITA|QUALITÀ|TIPO)\s*:?\s*(.+?)(?:\n|$)', re.IGNORECASE),
    "pattern_data": re.compile(r'(\d{2}/\d{2}/\d{4})'),
    "colonne_excel": {
        "data": "A", "ddt": "B", "qualita": "C", "bobina": "D",
        "peso": "E", "pallet": "F", "note": "G",
    },
}