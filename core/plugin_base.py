class ClientPlugin:
    """Classe base per tutti i plugin clienti."""

    id = None
    nome = None
    pattern_riconoscimento = None

    def riconosci(self, testo_pdf):
        """Ritorna True se il PDF appartiene a questo cliente."""
        if self.pattern_riconoscimento:
            return bool(self.pattern_riconoscimento.search(testo_pdf))
        return False

    def parse_ddt(self, testo_pdf):
        """Estrae i dati dal DDT PDF.
        Deve ritornare un dict con almeno:
        {
            'ddt': str,
            'data': str (dd/mm/yyyy),
            'cliente': str,
            'articoli': [{'codice': str, 'descrizione': str, 'qta': int/float, 'unita': str}],
            'totale_colli': int,
            'totale_peso': float,
            'causale': 'ingresso'|'uscita'|'',
            'extra': {} (dati specifici del cliente),
        }
        """
        raise NotImplementedError

    def genera_excel(self, ddt_data_list, excel_path):
        """Genera/aggiorna l'Excel mensile per questo cliente.
        ddt_data_list: lista di risultati da parse_ddt.
        excel_path: percorso del file Excel.
        """
        raise NotImplementedError

    def get_config(self):
        """Ritorna configurazione specifica del cliente."""
        return {}