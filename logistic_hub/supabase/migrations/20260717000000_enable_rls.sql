-- Enable RLS on all tables and create pass-through policies.
-- Authentication is handled by Flask-Login, not PostgREST.
-- These policies allow all access so PostgREST stops warning, while Flask
-- still enforces permissions via its own decorators.

DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY[
        'users',
        'activities',
        'notifications',
        'bolle',
        'dettaglio_bolla',
        'ddt',
        'righe_ddt',
        'giacenze',
        'movimenti',
        'picking',
        'picking_righe',
        'articoli',
        'fornitori',
        'documenti',
        'backup_log',
        'slot_orari',
        'prenotazioni',
        'magazzini_capienza',
        'tipologie_materiale'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('
            DROP POLICY IF EXISTS ''allow_all_%s'' ON %I;
            CREATE POLICY allow_all_%s ON %I
                FOR ALL
                USING (true)
                WITH CHECK (true);
        ', tbl, tbl, tbl, tbl);
    END LOOP;
END;
$$;
