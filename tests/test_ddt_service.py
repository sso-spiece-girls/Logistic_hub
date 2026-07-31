import pytest
from services.ddt_service import (
    scarica_giacenza_atomico, ripristina_giacenza, verifica_stock
)
from models import Giacenza, Movimento


# ─── Inventory Accounting Tests ───────────────────────────────────────────


def test_scarica_giacenza_atomico_decrements_all_fields(app, db):
    """Verify scarica_giacenza_atomico decrements colli, pallet, peso_kg, quantita."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=20, pallet=4, peso_kg=100.0, quantita=20)
        db.session.add(g)
        db.session.commit()

        ok = scarica_giacenza_atomico("ART001", 8, 40.0, 1, 2)
        assert ok is True
        db.session.refresh(g)
        assert g.colli == 12       # 20 - 8
        assert g.pallet == 2       # 4 - 2
        assert g.peso_kg == 60.0   # 100 - 40
        assert g.quantita == 12    # 20 - 8


def test_scarica_giacenza_atomico_prevents_negative(app, db):
    """Verify scarica_giacenza_atomico returns False when stock insufficient."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=3, pallet=1, peso_kg=10.0, quantita=3)
        db.session.add(g)
        db.session.commit()

        ok = scarica_giacenza_atomico("ART001", 10, 100.0, 1, 5)
        assert ok is False
        db.session.refresh(g)
        # Stock should be unchanged
        assert g.colli == 3
        assert g.pallet == 1
        assert g.peso_kg == 10.0
        assert g.quantita == 3


def test_scarica_giacenza_atomico_zero_colli_skips(app, db):
    """Verify scarica_giacenza_atomico with zero colli does not update quantita."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=10, pallet=2, peso_kg=50.0, quantita=10)
        db.session.add(g)
        db.session.commit()

        ok = scarica_giacenza_atomico("ART001", 0, 0, 1, 0)
        assert ok is True
        db.session.refresh(g)
        assert g.colli == 10
        assert g.pallet == 2
        assert g.quantita == 10


def test_ripristina_giacenza_restores_all_fields(app, db):
    """Verify ripristina_giacenza restores colli, pallet, peso_kg, quantita."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=10, pallet=2, peso_kg=50.0, quantita=10)
        db.session.add(g)
        db.session.commit()

        ripristina_giacenza("ART001", 5, 25.0, 1)
        db.session.commit()
        db.session.refresh(g)
        assert g.colli == 15       # 10 + 5
        assert g.pallet == 3       # 2 + 1
        assert g.peso_kg == 75.0   # 50 + 25
        assert g.quantita == 15     # 10 + 5


def test_ripristina_giacenza_no_record(app, db):
    """Verify ripristina_giacenza does nothing when no Giacenza record exists."""
    with app.app_context():
        count_before = Giacenza.query.count()
        ripristina_giacenza("NONEXISTENT", 5, 25.0, 1)
        count_after = Giacenza.query.count()
        assert count_after == count_before


def test_verifica_stock_checks_colli_and_peso(app, db):
    """Verify verifica_stock correctly identifies insufficient stock."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=10, pallet=2, peso_kg=50.0, quantita=10)
        db.session.add(g)
        db.session.commit()

        # Sufficient stock
        insufficienti = verifica_stock([
            {"articolo_codice": "ART001", "quantita_colli": 5, "peso_kg": 25.0}
        ])
        assert insufficienti == []

        # Insufficient colli
        insufficienti = verifica_stock([
            {"articolo_codice": "ART001", "quantita_colli": 15, "peso_kg": 25.0}
        ])
        assert len(insufficienti) == 1
        assert "colli" in insufficienti[0]

        # Insufficient peso
        insufficienti = verifica_stock([
            {"articolo_codice": "ART001", "quantita_colli": 5, "peso_kg": 100.0}
        ])
        assert len(insufficienti) == 1
        assert "kg" in insufficienti[0]

        # No giacenza record
        insufficienti = verifica_stock([
            {"articolo_codice": "NONEXISTENT", "quantita_colli": 5, "peso_kg": 25.0}
        ])
        assert len(insufficienti) == 1
        assert "nessuna giacenza" in insufficienti[0]


def test_scarica_giacenza_atomico_partial_colli_only(app, db):
    """Verify scarica_giacenza_atomico with only colli (no pallet/peso)."""
    with app.app_context():
        g = Giacenza(codice_articolo="ART001", descrizione="Test",
                     colli=10, pallet=2, peso_kg=50.0, quantita=10)
        db.session.add(g)
        db.session.commit()

        ok = scarica_giacenza_atomico("ART001", 3, 0, 1, 0)
        assert ok is True
        db.session.refresh(g)
        assert g.colli == 7
        assert g.pallet == 2       # unchanged
        assert g.peso_kg == 50.0   # unchanged
        assert g.quantita == 7