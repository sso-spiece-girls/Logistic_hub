import importlib
import os
import pkgutil
from core.plugin_base import ClientPlugin

_plugins = {}
_plugins_by_id = {}


def carica_tutti():
    """Carica automaticamente tutti i plugin clienti dalla directory clients/."""
    global _plugins, _plugins_by_id
    _plugins = {}
    _plugins_by_id = {}

    package_dir = os.path.dirname(__file__)
    for entry in os.listdir(package_dir):
        entry_path = os.path.join(package_dir, entry)
        if entry.startswith("_") or entry.startswith("."):
            continue
        if os.path.isdir(entry_path) and os.path.exists(os.path.join(entry_path, "__init__.py")):
            try:
                module = importlib.import_module(f"clients.{entry}")
                if hasattr(module, "plugin") and isinstance(module.plugin, ClientPlugin):
                    p = module.plugin
                    _plugins[p.nome] = p
                    _plugins_by_id[p.id] = p
            except Exception as e:
                print(f"[WARN] Plugin {entry}: {e}")

    return _plugins


def get_plugin(nome=None, id=None):
    if not _plugins:
        carica_tutti()
    if nome and nome in _plugins:
        return _plugins[nome]
    if id and id in _plugins_by_id:
        return _plugins_by_id[id]
    return None


def get_all_plugins():
    if not _plugins:
        carica_tutti()
    return list(_plugins.values())


def riconosci_cliente(testo_pdf):
    """Auto-riconosce il cliente dal testo del PDF."""
    if not _plugins:
        carica_tutti()
    for nome, plugin in _plugins.items():
        if plugin.riconosci(testo_pdf):
            return plugin
    return None


def lista_clienti():
    if not _plugins:
        carica_tutti()
    return {p.id: p.nome for p in _plugins.values()}