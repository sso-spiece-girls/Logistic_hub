import re


def normalizza_codice_articolo(codice):
    if not codice:
        return ""
    codice = codice.strip().upper()
    codice = re.sub(r'[_\s]+', '-', codice)
    codice = re.sub(r'[^A-Z0-9.\-/]', '', codice)
    return codice
