from core.normalize import normalizza_codice_articolo


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
