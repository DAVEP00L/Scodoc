# -*- coding: UTF-8 -*

"""
Create some Postgresql sequences and functions used by ScoDoc
using raw SQL
"""

from app import db


def create_database_functions():  # XXX obsolete
    """Create specific SQL functions and sequences

    XXX Obsolete: cette fonction est dans la première migration 9.0.3
    Flask-Migrate fait maintenant (dans les versions >= 9.0.4) ce travail.
    """
    # Important: toujours utiliser IF NOT EXISTS
    # car cette fonction peut être appelée plusieurs fois sur la même db
    db.session.execute(
        """
CREATE SEQUENCE IF NOT EXISTS notes_idgen_fcod;
CREATE OR REPLACE FUNCTION notes_newid_fcod() RETURNS TEXT
    AS $$ SELECT 'FCOD' || to_char(nextval('notes_idgen_fcod'), 'FM999999999');  $$
    LANGUAGE SQL;
CREATE OR REPLACE FUNCTION notes_newid_ucod() RETURNS TEXT
    AS $$ SELECT 'UCOD' || to_char(nextval('notes_idgen_fcod'), 'FM999999999');  $$
    LANGUAGE SQL;

CREATE OR REPLACE FUNCTION truncate_tables(username IN VARCHAR) RETURNS void AS $$
DECLARE
    statements CURSOR FOR
        SELECT tablename FROM pg_tables
        WHERE tableowner = username AND schemaname = 'public'
        AND tablename <> 'notes_semestres'
        AND tablename <> 'notes_form_modalites';
BEGIN
    FOR stmt IN statements LOOP
        EXECUTE 'TRUNCATE TABLE ' || quote_ident(stmt.tablename) || ' CASCADE;';
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Fonction pour anonymisation:
-- inspirée par https://www.simononsoftware.com/random-string-in-postgresql/
CREATE OR REPLACE FUNCTION random_text_md5( integer ) returns text
    LANGUAGE SQL
    AS $$
    select upper( substring( (SELECT string_agg(md5(random()::TEXT), '')
    FROM generate_series(
        1,
        CEIL($1 / 32.)::integer)
    ), 1, $1) );
    $$;
    """
    )
    db.session.commit()
