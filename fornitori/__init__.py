import re
from .base import FornitorePlugin
from .base_spa import BaseSpaParser
from .saleri import SaleriParser
from .carrara import CarraraParser
from .generico import GenericoParser

_specifici = []
_generico = None


def carica_tutti():
    global _specifici, _generico
    _specifici = []

    _specifici.append(SaleriParser({
        "id": "saleri",
        "nome": "Saleri",
        "pattern_riconoscimento": re.compile(r'SALERI', re.IGNORECASE),
    }))
    _specifici.append(CarraraParser({
        "id": "carrara",
        "nome": "Cartiere Carrara",
        "pattern_riconoscimento": re.compile(r'CARTIERE?\s*CARRARA', re.IGNORECASE),
    }))
    _specifici.append(BaseSpaParser({
        "id": "base_spa",
        "nome": "BASE SPA",
        "pattern_riconoscimento": re.compile(r'BASE\s*SPA', re.IGNORECASE),
    }))

    _generico = GenericoParser({
        "id": "generico",
        "nome": "Generico",
        "pattern_riconoscimento": None,
    })

    return _specifici + [_generico]


def get_plugin(nome=None, id=None):
    for p in _specifici + [_generico]:
        if nome and p.nome == nome:
            return p
        if id and p.id == id:
            return p
    return None


def get_all_plugins():
    return list(_specifici) + ([_generico] if _generico else [])


def riconosci_fornitore(testo_pdf):
    for p in _specifici:
        if p.riconosci(testo_pdf):
            return p
    return _generico


carica_tutti()
