import hashlib
import pytest
from services.bolla_service import (
    calcola_hash_pdf, parse_righe_json, _aggiorna_giacenza_ingresso,
    annulla_giacenza_movimento, crea_righe_bolla, _sostituisci_righe_bolla
)
from models import Giacenza, Movimento, DettaglioBolla, Bolla


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


# ─── Inventory Accounting Tests ───────────────────────────────────────────

def test_aggiorna_giacenza_ingresso_creates_new(app, db):
    """Verify _aggiorna_giacenza_ingresso creates a new Giacenza record with all fields, including description."""
    with app.app_context():
        _aggiorna_giacenza_ingresso(
            "ART001", {"quantita": 10, "pallet": 2, "peso_kg": 50.5, "descrizione": "Product Alpha"},
            1, 100, "bolla"
        )
        giac = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert giac is not None
        assert giac.colli == 10
        assert giac.pallet == 2
        assert giac.peso_kg == 50.5
        assert giac.quantita == 10  # quantita follows colli
        assert giac.descrizione == "Product Alpha"  # original description preserved


def test_aggiorna_giacenza_ingresso_creates_new_fallback_to_code(app, db):
    """Verify _aggiorna_giacenza_ingresso falls back to normalized code when no description provided."""
    with app.app_context():
        _aggiorna_giacenza_ingresso(
            "ART001", {"quantita": 10, "pallet": 2, "peso_kg": 50.5},
            1, 100, "bolla"
        )
        giac = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert giac is not None
        # When no 'descrizione' key exists in r, fall back to art_codice
        assert giac.descrizione == "ART001"


def test_aggiorna_giacenza_ingresso_updates_existing(app, db):
    """Verify _aggiorna_giacenza_ingresso updates all fields on existing Giacenza."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=5, pallet=1, peso_kg=25.0, quantita=5)
        db.session.add(g)
        db.session.commit()

        _aggiorna_giacenza_ingresso(
            "ART001", {"quantita": 10, "pallet": 2, "peso_kg": 50.5},
            1, 100, "bolla"
        )
        db.session.commit()
        db.session.refresh(g)
        assert g.colli == 15    # 5 + 10
        assert g.pallet == 3    # 1 + 2
        assert g.peso_kg == 75.5  # 25.0 + 50.5
        assert g.quantita == 15   # 5 + 10


def test_annulla_giacenza_movimento_reverts_all_fields(app, db):
    """Verify annulla_giacenza_movimento reverts colli, pallet, peso_kg, quantita."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=20, pallet=4, peso_kg=100.0, quantita=20)
        db.session.add(g)
        db.session.commit()

        # Create a DettaglioBolla-like object
        class FakeRiga:
            articolo_codice = "ART001"
            quantita_colli = 8
            quantita_pallet = 2
            peso_kg = 40.0

        annulla_giacenza_movimento(FakeRiga(), 999)
        db.session.refresh(g)
        assert g.colli == 12     # 20 - 8
        assert g.pallet == 2     # 4 - 2
        assert g.peso_kg == 60.0  # 100 - 40
        assert g.quantita == 12   # 20 - 8


def test_annulla_giacenza_movimento_prevents_negative(app, db):
    """Verify annulla_giacenza_movimento does not produce negative values."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=3, pallet=1, peso_kg=10.0, quantita=3)
        db.session.add(g)
        db.session.commit()

        class FakeRiga:
            articolo_codice = "ART001"
            quantita_colli = 10
            quantita_pallet = 5
            peso_kg = 100.0

        annulla_giacenza_movimento(FakeRiga(), 999)
        db.session.refresh(g)
        assert g.colli == 0
        assert g.pallet == 0
        assert g.peso_kg == 0.0
        assert g.quantita == 0


def test_annulla_giacenza_movimento_deletes_movimenti(app, db):
    """Verify annulla_giacenza_movimento deletes related Movimento records."""
    with app.app_context():
        mov = Movimento(tipo="ingresso", articolo_codice="ART001",
                        colli=5, riferimento_id=999, riferimento_tipo="bolla",
                        user_id=1)
        db.session.add(mov)
        db.session.commit()

        class FakeRiga:
            articolo_codice = "ART001"
            quantita_colli = 5
            quantita_pallet = 0
            peso_kg = 0

        annulla_giacenza_movimento(FakeRiga(), 999)
        remaining = Movimento.query.filter_by(riferimento_id=999, riferimento_tipo="bolla").count()
        assert remaining == 0


def test_crea_righe_bolla_updates_giacenza_and_creates_movimenti(app, db):
    """Verify crea_righe_bolla creates Giacenza records and Movimento records."""
    with app.app_context():
        b = Bolla(numero_bolla="B123", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()

        righe = [
            {"descrizione": "Product Alpha - 001", "quantita": 5, "pallet": 1, "peso_kg": 25.0},
            {"descrizione": "Product Beta - 002", "quantita": 3, "pallet": 0, "peso_kg": 15.0},
        ]
        crea_righe_bolla(b.id, righe, 1)
        db.session.commit()

        # Verify Giacenza records — articolo_codice is normalized, descrizione is original
        g1 = Giacenza.query.filter_by(codice_articolo="PRODUCT-ALPHA---001").first()
        assert g1 is not None
        assert g1.colli == 5
        assert g1.pallet == 1
        assert g1.quantita == 5
        assert g1.descrizione == "Product Alpha - 001"  # original human-readable description

        g2 = Giacenza.query.filter_by(codice_articolo="PRODUCT-BETA---002").first()
        assert g2 is not None
        assert g2.colli == 3
        assert g2.pallet == 0
        assert g2.quantita == 3
        assert g2.descrizione == "Product Beta - 002"  # original human-readable description

        # Verify Movimento records (crea_righe_bolla passa riferimento_tipo="bolla")
        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 2
        codici = {m.articolo_codice for m in movs}
        assert codici == {"PRODUCT-ALPHA---001", "PRODUCT-BETA---002"}


def test_bolla_create_delete_removes_movimenti(app, db):
    """Verify that creating a bolla creates Movimento with riferimento_tipo='bolla',
    and deleting the bolla removes the associated Movimento records."""
    with app.app_context():
        # Create bolla with one riga
        b = Bolla(numero_bolla="B456", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()

        righe = [
            {"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0},
        ]
        crea_righe_bolla(b.id, righe, 1)
        db.session.commit()

        # Verify Movimento was created with riferimento_tipo="bolla"
        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 1
        assert movs[0].riferimento_tipo == "bolla"
        assert movs[0].articolo_codice == "ART001"
        assert movs[0].colli == 5

        # Verify Giacenza was updated
        g = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g is not None
        assert g.colli == 5

        # Now simulate deletion: revert inventory and delete Movimento
        riga = b.righe.first()
        annulla_giacenza_movimento(riga, b.id)
        db.session.delete(riga)
        db.session.delete(b)
        db.session.commit()

        # Verify Movimento was deleted
        remaining = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").count()
        assert remaining == 0

        # Verify Giacenza was reverted to 0
        db.session.refresh(g)
        assert g.colli == 0
        assert g.pallet == 0
        assert g.peso_kg == 0.0
        assert g.quantita == 0


def test_crea_righe_bolla_preserves_description(app, db):
    """Verify crea_righe_bolla stores original description in Giacenza, not normalized code."""
    with app.app_context():
        b = Bolla(numero_bolla="B789", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()

        # Input with human-readable description different from the normalized code
        righe = [
            {"descrizione": "IG BIANCO PEFC GR.15", "quantita": 10, "pallet": 2, "peso_kg": 100.0},
        ]
        crea_righe_bolla(b.id, righe, 1)
        db.session.commit()

        # articular_code should be the normalized version
        g = Giacenza.query.filter_by(codice_articolo="IG-BIANCO-PEFC-GR.15").first()
        assert g is not None
        # descrizione should be the original human-readable text
        assert g.descrizione == "IG BIANCO PEFC GR.15"


def test_dettaglio_bolla_description_preferred_over_code(app, db):
    """Verify DettaglioBolla.descrizione is preferred over articolo_codice for form prefill (F6)."""
    with app.app_context():
        # Simulate a DettaglioBolla as it would be stored after creation
        riga = DettaglioBolla(
            bolla_id=1,
            articolo_codice="IG-BIANCO-PEFC-GR.15",
            descrizione="IG BIANCO PEFC GR.15",
            quantita_colli=10,
        )
        db.session.add(riga)
        db.session.commit()

        # This is the exact logic used in the edit form prefill (entrate.py line 90)
        prefill_descrizione = riga.descrizione or riga.articolo_codice or ""
        assert prefill_descrizione == "IG BIANCO PEFC GR.15"
        # Ensure the normalized code is NOT used when descrizione is available
        assert prefill_descrizione != "IG-BIANCO-PEFC-GR.15"

        # When descrizione is None, fall back to articolo_codice
        riga2 = DettaglioBolla(
            bolla_id=2,
            articolo_codice="ART001",
            descrizione=None,
            quantita_colli=5,
        )
        db.session.add(riga2)
        db.session.commit()
        prefill2 = riga2.descrizione or riga2.articolo_codice or ""
        assert prefill2 == "ART001"


# ─── Bolla Edit Regression Tests ────────────────────────────────────────
# These tests verify that _sostituisci_righe_bolla() uses a full revert+reapply
# strategy, avoiding the double-counting bug where old rows sharing an article
# code with new rows were not reverted.

def test_bolla_edit_same_article_changed_quantity(app, db):
    """Edit: ART001 5 colli -> 10 colli. Net inventory = 10, not 15."""
    with app.app_context():
        b = Bolla(numero_bolla="B001", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()
        crea_righe_bolla(b.id, [{"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        g = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g.colli == 5
        assert g.pallet == 1
        assert g.peso_kg == 25.0
        assert g.quantita == 5

        _sostituisci_righe_bolla(b, [{"descrizione": "ART001", "quantita": 10, "pallet": 2, "peso_kg": 50.0}], 1)
        db.session.commit()

        db.session.refresh(g)
        assert g.colli == 10, f"Expected 10, got {g.colli}"
        assert g.pallet == 2, f"Expected 2, got {g.pallet}"
        assert g.peso_kg == 50.0, f"Expected 50.0, got {g.peso_kg}"
        assert g.quantita == 10, f"Expected 10, got {g.quantita}"

        righe = b.righe.all()
        assert len(righe) == 1, f"Expected 1 DettaglioBolla, got {len(righe)}"
        assert righe[0].articolo_codice == "ART001"
        assert righe[0].quantita_colli == 10

        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 1, f"Expected 1 Movimento, got {len(movs)}"
        assert movs[0].articolo_codice == "ART001"
        assert movs[0].colli == 10


def test_bolla_edit_same_article_unchanged_quantity(app, db):
    """Edit: ART001 5 colli -> 5 colli. Net inventory unchanged."""
    with app.app_context():
        b = Bolla(numero_bolla="B002", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()
        crea_righe_bolla(b.id, [{"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        g = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g.colli == 5

        _sostituisci_righe_bolla(b, [{"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        db.session.refresh(g)
        assert g.colli == 5, f"Expected 5, got {g.colli}"
        assert g.pallet == 1
        assert g.peso_kg == 25.0
        assert g.quantita == 5

        righe = b.righe.all()
        assert len(righe) == 1, f"Expected 1 DettaglioBolla, got {len(righe)}"

        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 1, f"Expected 1 Movimento, got {len(movs)}"
        assert movs[0].colli == 5


def test_bolla_edit_removes_article(app, db):
    """Edit: remove ART001. Inventory reverts to 0. Rows and Movimenti cleaned."""
    with app.app_context():
        b = Bolla(numero_bolla="B003", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()
        crea_righe_bolla(b.id, [{"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        g = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g.colli == 5

        _sostituisci_righe_bolla(b, [], 1)
        db.session.commit()

        db.session.refresh(g)
        assert g.colli == 0
        assert g.pallet == 0
        assert g.peso_kg == 0.0
        assert g.quantita == 0

        righe = b.righe.all()
        assert len(righe) == 0, f"Expected 0 DettaglioBolla, got {len(righe)}"

        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 0, f"Expected 0 Movimento, got {len(movs)}"


def test_bolla_edit_adds_article(app, db):
    """Edit: add ART002=7. Only new contribution applied."""
    with app.app_context():
        b = Bolla(numero_bolla="B004", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()
        crea_righe_bolla(b.id, [{"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        _sostituisci_righe_bolla(
            b,
            [
                {"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0},
                {"descrizione": "ART002", "quantita": 7, "pallet": 2, "peso_kg": 35.0},
            ],
            1,
        )
        db.session.commit()

        g1 = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g1.colli == 5, f"ART001 expected 5, got {g1.colli}"

        g2 = Giacenza.query.filter_by(codice_articolo="ART002").first()
        assert g2 is not None
        assert g2.colli == 7, f"ART002 expected 7, got {g2.colli}"
        assert g2.pallet == 2
        assert g2.peso_kg == 35.0
        assert g2.quantita == 7

        righe = b.righe.all()
        assert len(righe) == 2, f"Expected 2 DettaglioBolla, got {len(righe)}"

        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 2, f"Expected 2 Movimento, got {len(movs)}"


def test_bolla_edit_changes_article_code(app, db):
    """Edit: ART001=5 -> ART002=5. Old code reverted, new code applied."""
    with app.app_context():
        b = Bolla(numero_bolla="B005", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()
        crea_righe_bolla(b.id, [{"descrizione": "ART001", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        g1 = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g1.colli == 5

        _sostituisci_righe_bolla(b, [{"descrizione": "ART002", "quantita": 5, "pallet": 1, "peso_kg": 25.0}], 1)
        db.session.commit()

        # Old code reverted
        db.session.refresh(g1)
        assert g1.colli == 0
        assert g1.pallet == 0
        assert g1.peso_kg == 0.0
        assert g1.quantita == 0

        # New code applied
        g2 = Giacenza.query.filter_by(codice_articolo="ART002").first()
        assert g2 is not None
        assert g2.colli == 5
        assert g2.pallet == 1
        assert g2.peso_kg == 25.0
        assert g2.quantita == 5

        righe = b.righe.all()
        assert len(righe) == 1, f"Expected 1 DettaglioBolla, got {len(righe)}"
        assert righe[0].articolo_codice == "ART002"

        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 1, f"Expected 1 Movimento, got {len(movs)}"
        assert movs[0].articolo_codice == "ART002"


def test_bolla_edit_updates_pallet_and_weight_without_double_counting(app, db):
    """Edit: ART001 same colli, changed pallet and weight. Only new values count."""
    with app.app_context():
        b = Bolla(numero_bolla="B006", fornitore="Test", operatore_id=1)
        db.session.add(b)
        db.session.flush()
        crea_righe_bolla(b.id, [{"descrizione": "ART001", "quantita": 5, "pallet": 2, "peso_kg": 100.0}], 1)
        db.session.commit()

        g = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g.colli == 5
        assert g.pallet == 2
        assert g.peso_kg == 100.0

        # Edit: same colli, different pallet and weight
        _sostituisci_righe_bolla(b, [{"descrizione": "ART001", "quantita": 5, "pallet": 3, "peso_kg": 150.0}], 1)
        db.session.commit()

        db.session.refresh(g)
        assert g.colli == 5, f"Expected 5, got {g.colli}"
        assert g.pallet == 3, f"Expected 3, got {g.pallet}"
        assert g.peso_kg == 150.0, f"Expected 150.0, got {g.peso_kg}"
        assert g.quantita == 5, f"Expected 5, got {g.quantita}"

        righe = b.righe.all()
        assert len(righe) == 1, f"Expected 1 DettaglioBolla, got {len(righe)}"

        movs = Movimento.query.filter_by(riferimento_id=b.id, riferimento_tipo="bolla").all()
        assert len(movs) == 1, f"Expected 1 Movimento, got {len(movs)}"
        assert movs[0].pallet == 3
        assert movs[0].peso_kg == 150.0


# ─── F8: Italian Number Parsing Tests ───────────────────────────────────

def test_f8_parse_italian_number_with_thousands_and_decimal():
    """F8: 1.234,56 -> 1234.56 (Italian format with thousands separator)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("1.234,56") == 1234.56


def test_f8_parse_italian_number_decimal_comma_only():
    """F8: 1234,56 -> 1234.56 (decimal comma, no thousands separator)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("1234,56") == 1234.56


def test_f8_parse_italian_number_decimal_dot():
    """F8: 1234.56 -> 1234.56 (already in dot notation)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("1234.56") == 1234.56


def test_f8_parse_italian_number_thousands_only():
    """F8: 1.234 -> 1234.0 (Italian thousands separator, no decimal)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("1.234") == 1234.0


def test_f8_parse_italian_number_plain_integer():
    """F8: 1234 -> 1234.0 (plain integer)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("1234") == 1234.0


def test_f8_parse_italian_number_small_decimal():
    """F8: 0,50 -> 0.5 (small decimal value)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("0,50") == 0.5


def test_f8_parse_italian_number_large_integer():
    """F8: 6835 -> 6835.0 (large integer without separators)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("6835") == 6835.0


def test_f8_parse_italian_number_ocr_decimal():
    """F8: 4803,11 -> 4803.11 (typical OCR output with decimal comma)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("4803,11") == 4803.11


def test_f8_parse_italian_number_empty_string():
    """F8: '' -> 0.0 (empty string returns 0.0)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("") == 0.0


def test_f8_parse_italian_number_none():
    """F8: None -> 0.0 (None returns 0.0)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number(None) == 0.0


def test_f8_parse_italian_number_with_whitespace():
    """F8: '  1.234,56  ' -> 1234.56 (whitespace stripped)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("  1.234,56  ") == 1234.56


def test_f8_parse_italian_number_us_format():
    """F8: 1,234.56 -> 1234.56 (US format with comma thousands, dot decimal)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number("1,234.56") == 1234.56


def test_f8_parse_italian_number_int_input():
    """F8: int 1234 -> 1234.0 (int input returns float)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number(1234) == 1234.0


def test_f8_parse_italian_number_float_input():
    """F8: float 1234.56 -> 1234.56 (float input returns as-is)."""
    from core.normalize import parse_italian_number
    assert parse_italian_number(1234.56) == 1234.56


def test_f8_parse_italian_number_malformed_raises():
    """F8: 'abc' -> ValueError (malformed input raises)."""
    from core.normalize import parse_italian_number
    with pytest.raises(ValueError):
        parse_italian_number("abc")


def test_f8_base_spa_parser_handles_italian_weight():
    """F8 regression: BaseSpaParser must parse '1.234,56 kg' as 1234.56, not crash."""
    from fornitori.base_spa import BaseSpaParser
    parser = BaseSpaParser({"id": "base_spa", "nome": "BASE SPA", "pattern_riconoscimento": None})
    testo = "PICKING 31122 2 pallet (100 colli) 1.234,56 kg"
    result = parser.parse_bolla(testo)
    assert len(result["righe"]) == 1
    assert result["righe"][0]["peso_kg"] == 1234.56


def test_f8_generico_parser_handles_italian_weight():
    """F8 regression: GenericoParser must parse '1.234,56 kg' as 1234.56, not crash."""
    from fornitori.generico import GenericoParser
    parser = GenericoParser({"id": "gen", "nome": "Generico", "pattern_riconoscimento": None})
    testo = "picking 31122 2 pallet (100 colli) 1.234,56 kg"
    result = parser.parse_bolla(testo)
    # The generic parser may match multiple patterns; verify at least one row
    # has the correct Italian-format weight.
    assert len(result["righe"]) >= 1
    picking_righe = [r for r in result["righe"] if r.get("descrizione") == "PICKING 31122"]
    assert len(picking_righe) == 1
    assert picking_righe[0]["peso_kg"] == 1234.56


def test_f8_saleri_parser_handles_italian_weight():
    """F8 regression: SaleriParser must parse '1.234,56 kg' as 1234.56, not crash."""
    from fornitori.saleri import SaleriParser
    parser = SaleriParser({"id": "saleri", "nome": "Saleri", "pattern_riconoscimento": None})
    testo = "SPLO1240239 16 pallet 1.234,56 kg"
    result = parser.parse_bolla(testo)
    assert len(result["righe"]) == 1
    assert result["righe"][0]["peso_kg"] == 1234.56


def test_f8_carrara_parser_handles_italian_weight():
    """F8 regression: CarraraParser must parse '1.234,56 kg' as 1234.56, not crash."""
    from fornitori.carrara import CarraraParser
    parser = CarraraParser({"id": "carrara", "nome": "Cartiere Carrara", "pattern_riconoscimento": None})
    testo = "100 colli 1.234,56 kg"
    result = parser.parse_bolla(testo)
    assert len(result["righe"]) == 1
    assert result["righe"][0]["peso_kg"] == 1234.56


def test_f8_importa_bolla_da_pdf_handles_italian_weight(app, db):
    """F8 regression: importa_bolla_da_pdf must convert Italian-formatted weight correctly."""
    from services.bolla_service import importa_bolla_da_pdf
    from werkzeug.datastructures import ImmutableMultiDict

    with app.app_context():
        form_data = ImmutableMultiDict([
            ("numero_bolla", "B-F8-1"),
            ("fornitore", "Test F8"),
            ("data_arrivo", ""),
            ("stato", "da_elaborare"),
            ("note", ""),
            ("righe_desc[]", "ART001"),
            ("righe_qta[]", "5"),
            ("righe_pallet[]", "1"),
            ("righe_peso[]", "1.234,56"),  # Italian format
        ])
        bolla, esistente = importa_bolla_da_pdf(form_data, 1)
        assert esistente is None
        assert bolla is not None

        # Verify the weight was parsed correctly
        riga = bolla.righe.first()
        assert riga.peso_kg == 1234.56, f"Expected 1234.56, got {riga.peso_kg}"

        # Verify Giacenza was updated with the correct weight
        g = Giacenza.query.filter_by(codice_articolo="ART001").first()
        assert g is not None
        assert g.peso_kg == 1234.56, f"Expected 1234.56, got {g.peso_kg}"

        # Verify Movimento was created with the correct weight
        mov = Movimento.query.filter_by(
            riferimento_id=bolla.id, riferimento_tipo="bolla", articolo_codice="ART001"
        ).first()
        assert mov is not None
        assert mov.peso_kg == 1234.56, f"Expected 1234.56, got {mov.peso_kg}"
