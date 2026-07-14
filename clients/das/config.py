import re

PLUGIN_CONFIG = {
    "id": "das",
    "nome": "DAS EUROPE",
    "pattern_riconoscimento": re.compile(r'DAS\s*(?:EUROPE|S\.R\.L\.?)', re.IGNORECASE),
    "causale_default": "uscita",
}