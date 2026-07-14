import re

PLUGIN_CONFIG = {
    "id": "ellegroup",
    "nome": "ELLE GROUP",
    "pattern_riconoscimento": re.compile(r'(?:ELLEGROUP|ELLE\s*GROUP|D\.D\.T\.\s*n[°0]\s*\d+/\d+)', re.IGNORECASE),
}