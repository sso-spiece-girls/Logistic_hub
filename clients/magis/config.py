import re

PLUGIN_CONFIG = {
    "id": "magis",
    "nome": "MAGIS SPA",
    "pattern_riconoscimento": re.compile(r'MAGIS\s*SPA', re.IGNORECASE),
    "causale_default": "uscita",
}