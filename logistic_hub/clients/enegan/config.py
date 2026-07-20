import re

PLUGIN_CONFIG = {
    "id": "enegan",
    "nome": "ENEGAN SPA",
    "pattern_riconoscimento": re.compile(r'ENEGAN\s*SPA', re.IGNORECASE),
}