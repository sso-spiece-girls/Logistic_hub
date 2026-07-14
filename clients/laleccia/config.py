import re

PLUGIN_CONFIG = {
    "id": "laleccia",
    "nome": "LA LECCIA",
    "pattern_riconoscimento": re.compile(r'(?:LA\s*LECCIA|FATTORIA\s*LA\s*LECCIA)', re.IGNORECASE),
    "causale_default": "uscita",
}