# -*- coding: utf-8 -*-

"""
    Some utilities used by upgrade scripts
    XXX python2 XXX
"""


import glob
import os
import psycopg2
import sys
import traceback

SCODOC_DIR = os.environ.get("SCODOC_DIR", "/opt/scodoc")
SCODOC_VAR_DIR = os.environ.get("SCODOC_VAR_DIR", "/opt/scodoc-data")


def log(msg):
    "write msg on stderr, add newline and flush"
    sys.stdout.flush()
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def get_dept_cnx_str(dept):
    "db cnx string for dept"
    f = os.path.join(SCODOC_VAR_DIR, "config", "depts", dept + ".cfg")
    try:
        return open(f).readline().strip()
    except:
        log("Error: can't read connexion string for dept %s" % dept)
        log("(tried to open %s)" % f)
        raise


def get_depts():
    "list of defined depts"
    files = glob.glob(SCODOC_VAR_DIR + "/config/depts/*.cfg")
    return [os.path.splitext(os.path.split(f)[1])[0] for f in files]


def field_exists(cnx, table, field):
    "true if field exists in sql table"
    cursor = cnx.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = '%s'"
        % table
    )
    r = cursor.fetchall()
    fields = [f[0] for f in r]
    return field in fields


def list_constraint(cnx, constraint_name=""):
    "liste la contrainte (utile surtout pour savoir si elle existe)"
    cursor = cnx.cursor()
    cursor.execute(
        "SELECT * FROM information_schema.table_constraints WHERE constraint_name = %(constraint_name)s",
        {"constraint_name": constraint_name},
    )
    return cursor.fetchall()


def list_table_index(cnx, table):
    "liste les index associés à cette table"
    cursor = cnx.cursor()
    cursor.execute(
        """SELECT t.relname as table_name, i.relname as index_name, a.attname as column_name 
    FROM 
        pg_class t, pg_class i, pg_index ix, pg_attribute a 
    WHERE 
        t.oid = ix.indrelid and i.oid = ix.indexrelid and a.attrelid = t.oid 
        and a.attnum = ANY(ix.indkey) and t.relkind = 'r' 
        and t.relname = %(table)s;
    """,
        {"table": table},
    )
    r = cursor.fetchall()
    return [x[1] for x in r]  # ne garde que le nom de l'index


def _run_sql(sql, cnx):
    cursor = cnx.cursor()
    error = False
    try:
        for cmd in sql:
            log("executing SQL: %s" % cmd)
            cursor.execute(cmd)
            cnx.commit()
    except:
        cnx.rollback()
        log("check_field: failure. Aborting transaction.")
        error = True
        traceback.print_exc()
    return error


def check_field(cnx, table, field, sql_create_commands):
    "if field does not exists in table, run sql commands"
    if not field_exists(cnx, table, field):
        log("missing field %s in table %s: trying to create it" % (field, table))
        error = _run_sql(sql_create_commands, cnx)
        if not field_exists(cnx, table, field):
            log("check_field: new field still missing !")
            raise Exception("database configuration problem")
        elif error:
            log("\n\nAN UNEXPECTED ERROR OCCURRED WHILE UPGRADING DATABASE !\n\n")
        else:
            log("field %s added successfully." % field)


def table_exists(cnx, table):
    "true if SQL table exists"
    cursor = cnx.cursor()
    cursor.execute(
        "SELECT table_name FROM information_schema.tables where table_name='%s'" % table
    )
    r = cursor.fetchall()
    return len(r) > 0


def check_table(cnx, table, sql_create_commands):
    "if table does not exists in table, run sql commands"
    if not table_exists(cnx, table):
        log("missing table %s: trying to create it" % (table))
        error = _run_sql(sql_create_commands, cnx)
        if not table_exists(cnx, table):
            log("check_table: new table still missing !")
            raise Exception("database configuration problem")
        elif error:
            log("\n\nAN UNEXPECTED ERROR OCCURRED WHILE UPGRADING DATABASE !\n\n")
        else:
            log("table %s added successfully." % table)


def sequence_exists(cnx, seq_name):
    "true if SQL sequence exists"
    cursor = cnx.cursor()
    cursor.execute(
        """SELECT relname FROM pg_class
     WHERE relkind = 'S' and relname = '%s'
     AND relnamespace IN (
        SELECT oid FROM pg_namespace WHERE nspname NOT LIKE 'pg_%%' AND nspname != 'information_schema'
     );
    """
        % seq_name
    )
    r = cursor.fetchall()
    return len(r) > 0


def function_exists(cnx, func_name):
    "true if SQL function exists"
    cursor = cnx.cursor()
    cursor.execute(
        """SELECT routine_name FROM information_schema.routines
      WHERE specific_schema NOT IN ('pg_catalog', 'information_schema')
      AND type_udt_name != 'trigger' 
      AND routine_name = '%s';"""
        % func_name
    )
    r = cursor.fetchall()
    return len(r) > 0
