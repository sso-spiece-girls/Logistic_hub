from core.normalize import normalizza_codice_articolo, parse_italian_number
import pytest


def test_codice_semplice():
    assert normalizza_codice_articolo("ABC-123") == "ABC-123"


def test_codice_con_spazi():
    assert normalizza_codice_articolo(" ABC 123 ") == "ABC-123"


def test_codice_minuscolo():
    assert normalizza_codice_articolo("abc-123") == "ABC-123"


def test_codice_con_underscore():
    assert normalizza_codice_articolo("ABC_123") == "ABC-123"


def test_codice_vuoto():
    assert normalizza_codice_articolo("") == ""


def test_codice_con_punteggiatura():
    assert normalizza_codice_articolo("MB0634HG3.001.TU") == "MB0634HG3.001.TU"


def test_codice_con_slash():
    assert normalizza_codice_articolo("ABC/123/DEF") == "ABC/123/DEF"


# ─── parse_italian_number Tests (F8) ─────────────────────────────────────

def test_parse_italian_thousands_and_decimal():
    assert parse_italian_number("1.234,56") == 1234.56


def test_parse_italian_decimal_comma_only():
    assert parse_italian_number("1234,56") == 1234.56


def test_parse_italian_decimal_dot():
    assert parse_italian_number("1234.56") == 1234.56


def test_parse_italian_thousands_only():
    assert parse_italian_number("1.234") == 1234.0


def test_parse_italian_plain_integer():
    assert parse_italian_number("1234") == 1234.0


def test_parse_italian_small_decimal():
    assert parse_italian_number("0,50") == 0.5


def test_parse_italian_large_integer():
    assert parse_italian_number("6835") == 6835.0


def test_parse_italian_ocr_decimal():
    assert parse_italian_number("4803,11") == 4803.11


def test_parse_italian_empty_string():
    assert parse_italian_number("") == 0.0


def test_parse_italian_none():
    assert parse_italian_number(None) == 0.0


def test_parse_italian_with_whitespace():
    assert parse_italian_number("  1.234,56  ") == 1234.56


def test_parse_italian_us_format():
    assert parse_italian_number("1,234.56") == 1234.56


def test_parse_italian_int_input():
    assert parse_italian_number(1234) == 1234.0


def test_parse_italian_float_input():
    assert parse_italian_number(1234.56) == 1234.56


def test_parse_italian_malformed_raises():
    with pytest.raises(ValueError):
        parse_italian_number("abc")
