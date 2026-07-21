import re


def normalizza_codice_articolo(codice):
    if not codice:
        return ""
    codice = codice.strip().upper()
    codice = re.sub(r'[_\s]+', '-', codice)
    codice = re.sub(r'[^A-Z0-9.\-/]', '', codice)
    return codice


def parse_italian_number(value):
    """Convert an Italian-formatted number string to float.

    Handles Italian format (period = thousands separator, comma = decimal):
        "1.234,56"  -> 1234.56
        "1234,56"   -> 1234.56
        "1.234"     -> 1234.0
        "0,50"      -> 0.5

    Also handles standard dot-notation and US-style (comma = thousands):
        "1234.56"   -> 1234.56
        "1,234.56"  -> 1234.56
        "1234"      -> 1234.0

    When both separators are present, the LAST separator is treated as
    the decimal separator. This is deterministic and handles both
    Italian (1.234,56) and US (1,234.56) conventions.

    Empty/None values return 0.0. Malformed non-empty strings raise ValueError.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0

    # If both comma and period are present, the LAST separator is decimal
    if ',' in s and '.' in s:
        last_comma = s.rfind(',')
        last_dot = s.rfind('.')
        if last_comma > last_dot:
            # Italian: last separator is comma (decimal), periods are thousands
            s = s.replace('.', '').replace(',', '.')
        else:
            # US: last separator is period (decimal), commas are thousands
            s = s.replace(',', '')
        return float(s)

    # Only comma present -> Italian decimal comma
    if ',' in s:
        return float(s.replace(',', '.'))

    # Only period present -> could be decimal or thousands separator.
    # If a period is followed by exactly 3 digits at end of string,
    # it's a thousands separator (e.g. "1.234" -> 1234)
    if '.' in s:
        s = re.sub(r'\.(?=\d{3}$)', '', s)

    return float(s)
