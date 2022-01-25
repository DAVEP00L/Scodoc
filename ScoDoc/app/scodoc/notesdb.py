# -*- mode: python -*-
# -*- coding: utf-8 -*-

import html
import traceback
import psycopg2
import psycopg2.pool
import psycopg2.extras

from flask import g, current_app, abort

import app
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.sco_exceptions import ScoException, ScoValueError, NoteProcessError
import datetime

quote_html = html.escape


def quote_dict(d):
    "html quote all values in dict"
    for k in d.keys():
        v = d[k]
        if isinstance(v, str):
            d[k] = quote_html(v, quote=True)


def unquote(s):
    "inverse of quote"
    # pas d'inverse de cgi.escape
    # ne traite que &
    # XX voir aussi sco_utils.unescape_html
    return s.replace("&amp;", "&")


def open_db_connection():
    """Open a connection to the database"""
    try:
        g.db_conn = psycopg2.connect(current_app.config["SQLALCHEMY_DATABASE_URI"])
    except psycopg2.OperationalError:
        # Dans la majorité des cas, cela signifie que le serveur postgres
        # n'est pas lancé.
        log("open_db_connection: psycopg2.OperationalError")
        abort(503)  # HTTP 503 Service Unavailable


def close_db_connection():
    """Commit and close database."""
    if hasattr(g, "db_conn"):
        g.db_conn.commit()
        g.db_conn.close()
        del g.db_conn


def GetDBConnexion(autocommit=True):  # on n'utilise plus autocommit
    return g.db_conn


# Nota:  on pourrait maintenant utiliser psycopg2.extras.DictCursor
class ScoDocCursor(psycopg2.extensions.cursor):
    """A database cursor emulating some methods of psycopg v1 cursors"""

    def dictfetchall(self):
        col_names = [d[0] for d in self.description]
        return [dict(zip(col_names, row)) for row in self.fetchall()]

    def dictfetchone(self):
        col_names = [d[0] for d in self.description]
        row = self.fetchone()
        if row:
            return dict(zip(col_names, row))
        else:
            return {}


def SimpleQuery(query, args, cursor=None):
    if not cursor:
        cnx = GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    # log( 'SimpleQuery(%s)' % (query % args) )
    cursor.execute(query, args)
    return cursor


def SimpleDictFetch(query, args, cursor=None):
    cursor = SimpleQuery(query, args, cursor=cursor)
    return cursor.dictfetchall()


def DBInsertDict(
    cnx,
    table,
    vals,
    commit=0,
    convert_empty_to_nulls=1,
    return_id=True,
    ignore_conflicts=False,
) -> int:
    """insert into table values in dict 'vals'
    Return: id de l'object créé
    """
    cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    if convert_empty_to_nulls:
        for col in vals.keys():
            if vals[col] == "":
                vals[col] = None
    # open('/tmp/vals','a').write( str(vals) + '\n' )
    cols = list(vals.keys())
    colnames = ",".join(cols)
    fmt = ",".join(["%%(%s)s" % col for col in cols])
    # print 'insert into %s (%s) values (%s)' % (table,colnames,fmt)
    oid = None
    if ignore_conflicts:
        ignore = " ON CONFLICT DO NOTHING"
    else:
        ignore = ""
    try:
        if vals:
            cursor.execute(
                "insert into %s (%s) values (%s)%s" % (table, colnames, fmt, ignore),
                vals,
            )
        else:
            cursor.execute("insert into %s default values%s" % (table, ignore))
        if return_id:
            cursor.execute(f"SELECT CURRVAL('{table}_id_seq')")  # id créé
            oid = cursor.fetchone()[0]
        else:
            oid = None
    except:
        log("DBInsertDict: EXCEPTION !")
        log("DBInsertDict: table=%s, vals=%s" % (str(table), str(vals)))
        log("DBInsertDict: commit (exception)")
        cnx.commit()  # get rid of this transaction
        raise  # and re-raise exception
    if commit:
        # log("DBInsertDict: commit (requested)")
        cnx.commit()
    return oid


_SQL_REMOVE_BAD_CHARS = str.maketrans("", "", '%*()+=&|[]"`')


def DBSelectArgs(
    cnx,
    table,
    vals,
    what=["*"],
    sortkey=None,
    test="=",
    operator="and",
    distinct=True,
    aux_tables=[],
    id_name=None,
    limit="",
    offset="",
):
    """Select * from table where values match dict vals.
    Returns cnx, columns_names, list of tuples
    aux_tables = ( tablename, id_name )
    """
    cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    if sortkey:
        orderby = " order by " + sortkey
    else:
        orderby = ""
    if distinct:
        distinct = " distinct "
    else:
        distinct = ""
    if limit != "":
        limit = " LIMIT %d" % limit
    if not offset:
        offset = ""
    if offset != "":
        offset = " OFFSET %d" % offset
    operator = " " + operator + " "
    # liste des tables (apres "from")
    tables = [table] + [x[0] for x in aux_tables]
    for i in range(len(tables)):
        tables[i] = "%s T%d" % (tables[i], i)
    tables = ", ".join(tables)
    # condition (apres "where")
    cond = ""
    i = 1
    cl = []
    for (_, aux_id) in aux_tables:
        cl.append("T0.%s = T%d.%s" % (id_name, i, aux_id))
        i = i + 1
    cond += " and ".join(cl)

    if vals:
        if aux_tables:  # paren
            cond += " AND ( "

        if test == "~":
            # Traitement des expressions régulières:
            #  n'autorise pas d'expressions
            explist = []
            for k in vals.keys():
                # n'applique ~ qu'aux strings
                if isinstance(vals[k], str):
                    vals[k] = vals[k].translate(_SQL_REMOVE_BAD_CHARS)
                    explist.append("T0.%s~%%(%s)s" % (k, k))
                elif vals[k] is not None:
                    explist.append("T0.%s=%%(%s)s" % (k, k))
            cond += operator.join(explist)
        else:
            cond += operator.join(
                [
                    "T0.%s%s%%(%s)s" % (x, test, x)
                    for x in vals.keys()
                    if vals[x] != None
                ]
            )
        # conditions sur NULLs:
        cnuls = " and ".join(
            ["T0.%s is NULL" % x for x in vals.keys() if vals[x] is None]
        )
        if cnuls:
            if cond:
                cond = cond + " and " + cnuls
            else:
                cond = cnuls
        # close paren
        if aux_tables:
            cond += ") "
    if cond:
        cond = " where " + cond
    #
    req = (
        "select "
        + distinct
        + ", ".join(what)
        + " from "
        + tables
        + cond
        + orderby
        + limit
        + offset
    )
    try:
        cursor.execute(req, vals)
    except:
        log('Exception in DBSelectArgs:\n\treq="%s"\n\tvals="%s"\n' % (req, vals))
        log(traceback.format_exc())
        cnx.rollback()
        raise ScoException()
    return cursor.dictfetchall()


def DBUpdateArgs(cnx, table, vals, where=None, commit=False, convert_empty_to_nulls=1):
    if not vals or where is None:
        return
    cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    if convert_empty_to_nulls:
        for col in vals.keys():
            if vals[col] == "":
                vals[col] = None
    s = ", ".join(["%s=%%(%s)s" % (x, x) for x in vals.keys()])
    try:
        req = "update " + table + " set " + s + " where " + where
        cursor.execute(req, vals)
        # log('req=%s\n'%req)
        # log('vals=%s\n'%vals)
    except:
        cnx.commit()  # get rid of this transaction
        log('Exception in DBUpdateArgs:\n\treq="%s"\n\tvals="%s"\n' % (req, vals))
        raise  # and re-raise exception
    if commit:
        cnx.commit()


def DBDelete(cnx, table, oid, commit=False):
    cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    try:
        cursor.execute("delete from " + table + " where id=%(oid)s", {"oid": oid})
    except:
        cnx.commit()  # get rid of this transaction
        raise  # and re-raise exception
    if commit:
        cnx.commit()


# --------------------------------------------------------------------


class EditableTable(object):
    """--- generic class: SQL table with create/edit/list/delete"""

    def __init__(
        self,
        table_name,
        id_name,
        dbfields,
        sortkey=None,
        output_formators={},
        input_formators={},
        aux_tables=[],
        convert_null_outputs_to_empty=True,
        html_quote=False,  # changed in 9.0.10
        fields_creators={},  # { field : [ sql_command_to_create_it ] }
        filter_nulls=True,  # dont allow to set fields to null
        filter_dept=False,  # ajoute selection sur g.scodoc_dept_id
        insert_ignore_conflicts=False,
    ):
        self.table_name = table_name
        self.id_name = id_name
        self.aux_tables = aux_tables
        self.dbfields = dbfields
        # DB remove object_id and replace by "id":
        try:
            i = self.dbfields.index(id_name)
            self.dbfields = ("id",) + self.dbfields[:i] + self.dbfields[i + 1 :]
        except ValueError:
            pass
        self.sortkey = sortkey
        self.output_formators = output_formators
        self.input_formators = input_formators
        self.convert_null_outputs_to_empty = convert_null_outputs_to_empty
        self.html_quote = html_quote
        self.fields_creators = fields_creators
        self.filter_nulls = filter_nulls
        self.filter_dept = filter_dept
        self.sql_default_values = None
        self.insert_ignore_conflicts = insert_ignore_conflicts

    def create(self, cnx, args) -> int:
        "create object in table"
        vals = dictfilter(args, self.dbfields, self.filter_nulls)
        if self.id_name in vals:
            del vals[self.id_name]
        if "id" in vals:
            del vals["id"]
        if self.filter_dept:
            vals["dept_id"] = g.scodoc_dept_id
        if (
            self.html_quote
        ):  # quote all HTML markup (une bien mauvaise idée venue des ages obscurs)
            quote_dict(vals)
        # format value
        for title in vals:
            if title in self.input_formators:
                vals[title] = self.input_formators[title](vals[title])
        # insert
        new_id = DBInsertDict(
            cnx,
            self.table_name,
            vals,
            commit=True,
            return_id=(self.id_name is not None),
            ignore_conflicts=self.insert_ignore_conflicts,
        )
        return new_id

    def delete(self, cnx, oid, commit=True):
        "delete tuple"
        DBDelete(cnx, self.table_name, oid, commit=commit)

    def list(
        self,
        cnx,
        args={},
        operator="and",
        test="=",
        sortkey=None,
        disable_formatting=False,
        limit="",
        offset="",
    ):
        "returns list of dicts"
        id_value = args.get(self.id_name)
        vals = dictfilter(args, self.dbfields, self.filter_nulls)
        if (id_value is not None) and (not "id" in vals):
            vals["id"] = id_value
        if self.filter_dept:
            vals["dept_id"] = g.scodoc_dept_id
        if not sortkey:
            sortkey = self.sortkey
        res = DBSelectArgs(
            cnx,
            self.table_name,
            vals,
            sortkey=sortkey,
            test=test,
            operator=operator,
            aux_tables=self.aux_tables,
            id_name=self.id_name,
            limit=limit,
            offset=offset,
        )
        for r in res:
            self.format_output(r, disable_formatting=disable_formatting)
            # Add ScoDoc7 id:
            if "id" in r:
                r[self.id_name] = r["id"]
        return res

    def format_output(self, r, disable_formatting=False):
        "Format dict using provided output_formators"
        for (k, v) in r.items():
            if v is None and self.convert_null_outputs_to_empty:
                v = ""
            # format value
            if not disable_formatting and k in self.output_formators:
                try:  # XXX debug "isodate"
                    v = self.output_formators[k](v)
                except:
                    log("*** list: vars=%s" % str(vars()))
                    log("*** list: r=%s" % str(r))
                    raise
            r[k] = v

    def edit(self, cnx, args, html_quote=None):
        """Change fields"""
        # assert self.id_name in args
        oid = args[self.id_name]
        vals = dictfilter(args, self.dbfields, self.filter_nulls)
        vals["id"] = oid
        html_quote = html_quote or self.html_quote
        if html_quote:
            quote_dict(vals)  # quote HTML
        # format value
        for title in vals.keys():
            if title in self.input_formators:
                try:
                    vals[title] = self.input_formators[title](vals[title])
                except:
                    log("exception while converting %s=%s" % (title, vals[title]))
                    raise
        DBUpdateArgs(
            cnx,
            self.table_name,
            vals,
            where="id=%(id)s",
            commit=True,
        )


def dictfilter(d, fields, filter_nulls=True):
    """returns a copy of d with only keys listed in "fields" and non null values"""
    r = {}
    for f in fields:
        if f in d and (d[f] != None or not filter_nulls):
            try:
                val = d[f].strip()
            except:
                val = d[f]
            r[f] = val
    return r


# --------------------------------------------------------------------
# --- Misc Tools


def DateDMYtoISO(dmy, null_is_empty=False):
    "convert date string from french format to ISO"
    if not dmy:
        if null_is_empty:
            return ""
        else:
            return None
    if not isinstance(dmy, str):
        return dmy.strftime("%Y-%m-%d")

    t = dmy.split("/")

    if len(t) != 3:
        raise ScoValueError('Format de date (j/m/a) invalide: "%s"' % str(dmy))
    day, month, year = t
    year = int(year)
    month = int(month)
    day = int(day)
    # accept years YYYY or YY, uses 1970 as pivot
    if year < 100:
        if year > 70:
            year += 1900
        else:
            year += 2000

    if month < 1 or month > 12:
        raise ScoValueError("mois de la date invalide ! (%s)" % month)
    # compute nb of day in month:
    mo = month
    if mo > 7:
        mo = mo + 1
    if mo % 2:
        MonthNbDays = 31
    elif mo == 2:
        if year % 4 == 0 and ((year % 100 != 0) or (year % 400 == 0)):
            MonthNbDays = 29  # leap
        else:
            MonthNbDays = 28
    else:
        MonthNbDays = 30
    if day < 1 or day > MonthNbDays:
        raise ScoValueError("jour de la date invalide ! (%s)" % day)
    return "%04d-%02d-%02d" % (year, month, day)


def DateISOtoDMY(isodate):
    if not isodate:
        return ""
    arg = isodate  # debug
    # si isodate est une instance de DateTime !
    try:
        isodate = "%s-%s-%s" % (isodate.year(), isodate.month(), isodate.day())
        # log('DateISOtoDMY: converted isodate to iso !')
    except:
        pass
    # drop time from isodate and split
    t = str(isodate).split()[0].split("-")
    if len(t) != 3:
        # XXX recherche bug intermittent assez etrange
        log('*** DateISOtoDMY: invalid isodate "%s" (arg="%s")' % (str(isodate), arg))
        raise NoteProcessError(
            'invalid isodate: "%s" (arg="%s" type=%s)' % (str(isodate), arg, type(arg))
        )
    year, month, day = t
    year = int(year)
    month = int(month)
    day = int(day)
    if month < 1 or month > 12:
        raise ValueError("invalid month")
    if day < 1 or day > 31:
        raise ValueError("invalid day")
    return "%02d/%02d/%04d" % (day, month, year)


def TimetoISO8601(t, null_is_empty=False):
    "convert time string to ISO 8601 (allow 16:03, 16h03, 16)"
    if isinstance(t, datetime.time):
        return t.isoformat()
    if not t and null_is_empty:
        return ""
    t = t.strip().upper().replace("H", ":")
    if t and t.count(":") == 0 and len(t) < 3:
        t = t + ":00"
    return t


def TimefromISO8601(t):
    "convert time string from ISO 8601 to our display format"
    if not t:
        return t
    # XXX strange bug turnaround...
    try:
        t = "%s:%s" % (t.hour(), t.minute())
        # log('TimefromISO8601: converted isotime to iso !')
    except:
        pass
    fs = str(t).split(":")
    return fs[0] + "h" + fs[1]  # discard seconds


def TimeDuration(heure_debut, heure_fin):
    """duree (nb entier de minutes) entre deux heures a notre format
    ie 12h23
    """
    if heure_debut and heure_fin:
        h0, m0 = [int(x) for x in heure_debut.split("h")]
        h1, m1 = [int(x) for x in heure_fin.split("h")]
        d = (h1 - h0) * 60 + (m1 - m0)
        return d
    else:
        return None


def float_null_is_zero(x):
    if x is None or x == "":
        return 0.0
    else:
        return float(x)


def int_null_is_zero(x):
    if x is None or x == "":
        return 0
    else:
        return int(x)


def int_null_is_null(x):
    if x is None or x == "":
        return None
    else:
        return int(x)


def float_null_is_null(x):
    if x is None or x == "":
        return None
    else:
        return float(x)


BOOL_STR = {
    "": False,
    "false": False,
    "0": False,
    "1": True,
    "true": True,
}


def bool_or_str(x) -> bool:
    """a boolean, may also be encoded as a string "0", "False",  "1", "True" """
    if isinstance(x, str):
        return BOOL_STR[x.lower()]
    return bool(x)


# post filtering
#
def UniqListofDicts(L, key):
    """L is a list of dicts.
    Remove from L all items which share the same key/value
    """
    # well, code is simpler than documentation:
    d = {}
    for item in L:
        d[item[key]] = item
    return list(d.values())


#
def copy_tuples_changing_attribute(
    cnx, table, column, old_value, new_value, to_exclude=[]
):
    """Duplicate tuples in DB table, replacing column old_value by new_value

    Will raise exception if violation of integerity constraint !
    """
    cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    cursor.execute(
        "select * from %s where %s=%%(old_value)s" % (table, column),
        {"old_value": old_value},
    )
    res = cursor.dictfetchall()
    for t in res:
        t[column] = new_value
        for c in to_exclude:
            del t[c]
        _ = DBInsertDict(cnx, table, t, convert_empty_to_nulls=False)
