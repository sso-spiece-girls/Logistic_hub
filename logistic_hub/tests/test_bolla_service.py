import hashlib
from services.bolla_service import calcola_hash_pdf, parse_righe_json


class FakeStream:
    def __init__(self, data):
        self.stream = data
        self.pos = 0
    def seek(self, pos):
        self.pos = pos
    def read(self, size):
        if self.pos >= len(self.stream):
            return b""
        chunk = self.stream[self.pos:self.pos + size]
        self.pos += size
        return chunk


from io import BytesIO


class FakeFile:
    def __init__(self, data, filename="test.pdf"):
        self.stream = BytesIO(data if isinstance(data, bytes) else data.encode())
        self.filename = filename


def test_calcola_hash_pdf():
    f = FakeFile(b"contenuto pdf finto")
    h = calcola_hash_pdf(f)
    expected = hashlib.sha256(b"contenuto pdf finto").hexdigest()
    assert h == expected


def test_parse_righe_json_valido():
    class FakeForm:
        def get(self, key, default="[]"):
            return '[{"descrizione": "ART001", "quantita": 5}]'
    righe = parse_righe_json(FakeForm())
    assert len(righe) == 1
    assert righe[0]["descrizione"] == "ART001"


def test_parse_righe_json_invalido():
    class FakeForm:
        def get(self, key, default="[]"):
            return "not json"
    righe = parse_righe_json(FakeForm())
    assert righe == []
