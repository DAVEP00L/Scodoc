# -*- mode: python -*-
# -*- coding: utf-8 -*-

##############################################################################
#
# Gestion scolarite IUT
#
# Copyright (c) 1999 - 2021 Emmanuel Viennet.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#   Emmanuel Viennet      emmanuel.viennet@viennet.net
#
##############################################################################

"""Fonctions sur les absences
"""

import calendar
import datetime
import html
import string
import time
import types

from app.scodoc import notesdb as ndb
from app import log
from app.scodoc.scolog import logdb
from app.scodoc.sco_exceptions import ScoValueError, ScoInvalidDateError
from app.scodoc import sco_abs_notification
from app.scodoc import sco_cache
from app.scodoc import sco_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_preferences

# --- Misc tools.... ------------------


def _isFarFutur(jour):
    # check si jour est dans le futur "lointain"
    # pour autoriser les saisies dans le futur mais pas a plus de 6 mois
    y, m, d = [int(x) for x in jour.split("-")]
    j = datetime.date(y, m, d)
    # 6 mois ~ 182 jours:
    return j - datetime.date.today() > datetime.timedelta(182)


def _toboolean(x):
    "convert a value to boolean"
    return bool(x)


def is_work_saturday():
    "Vrai si le samedi est travaillé"
    return int(sco_preferences.get_preference("work_saturday"))


def MonthNbDays(month, year):
    "returns nb of days in month"
    if month > 7:
        month = month + 1
    if month % 2:
        return 31
    elif month == 2:
        if calendar.isleap(year):
            return 29
        else:
            return 28
    else:
        return 30


class ddmmyyyy(object):
    """immutable dates"""

    def __init__(self, date=None, fmt="ddmmyyyy", work_saturday=False):
        self.work_saturday = work_saturday
        if date is None:
            return
        try:
            if fmt == "ddmmyyyy":
                self.day, self.month, self.year = date.split("/")
            elif fmt == "iso":
                self.year, self.month, self.day = date.split("-")
            else:
                raise ValueError("invalid format spec. (%s)" % fmt)
            self.year = int(self.year)
            self.month = int(self.month)
            self.day = int(self.day)
        except ValueError:
            raise ScoValueError("date invalide: %s" % date)
        # accept years YYYY or YY, uses 1970 as pivot
        if self.year < 1970:
            if self.year > 100:
                raise ScoInvalidDateError("Année invalide: %s" % self.year)
            if self.year < 70:
                self.year = self.year + 2000
            else:
                self.year = self.year + 1900
        if self.month < 1 or self.month > 12:
            raise ScoInvalidDateError("Mois invalide: %s" % self.month)

        if self.day < 1 or self.day > MonthNbDays(self.month, self.year):
            raise ScoInvalidDateError("Jour invalide: %s" % self.day)

        # weekday in 0-6, where 0 is monday
        self.weekday = calendar.weekday(self.year, self.month, self.day)

        self.time = time.mktime((self.year, self.month, self.day, 0, 0, 0, 0, 0, 0))

    def iswork(self):
        "returns true if workable day"
        if self.work_saturday:
            nbdays = 6
        else:
            nbdays = 5
        if (
            self.weekday >= 0 and self.weekday < nbdays
        ):  # monday-friday or monday-saturday
            return 1
        else:
            return 0

    def __repr__(self):
        return "'%02d/%02d/%04d'" % (self.day, self.month, self.year)

    def __str__(self):
        return "%02d/%02d/%04d" % (self.day, self.month, self.year)

    def ISO(self):
        "iso8601 representation of the date"
        return "%04d-%02d-%02d" % (self.year, self.month, self.day)

    def next_day(self, days=1):
        "date for the next day (nota: may be a non workable day)"
        day = self.day + days
        month = self.month
        year = self.year

        while day > MonthNbDays(month, year):
            day = day - MonthNbDays(month, year)
            month = month + 1
            if month > 12:
                month = 1
                year = year + 1
        return self.__class__(
            "%02d/%02d/%04d" % (day, month, year), work_saturday=self.work_saturday
        )

    def prev(self, days=1):
        "date for previous day"
        day = self.day - days
        month = self.month
        year = self.year
        while day <= 0:
            month = month - 1
            if month == 0:
                month = 12
                year = year - 1
            day = day + MonthNbDays(month, year)

        return self.__class__(
            "%02d/%02d/%04d" % (day, month, year), work_saturday=self.work_saturday
        )

    def next_monday(self):
        "date of next monday"
        return self.next_day((7 - self.weekday) % 7)

    def prev_monday(self):
        "date of last monday, but on sunday, pick next monday"
        if self.weekday == 6:
            return self.next_monday()
        else:
            return self.prev(self.weekday)

    def __cmp__(self, other):  # #py3 TODO à supprimer
        """return a negative integer if self < other,
        zero if self == other, a positive integer if self > other"""
        return int(self.time - other.time)

    def __eq__(self, other):
        return self.time == other.time

    def __ne__(self, other):
        return self.time != other.time

    def __lt__(self, other):
        return self.time < other.time

    def __le__(self, other):
        return self.time <= other.time

    def __gt__(self, other):
        return self.time > other.time

    def __ge__(self, other):
        return self.time >= other.time

    def __hash__(self):
        "we are immutable !"
        return hash(self.time) ^ hash(str(self))


# d = ddmmyyyy( '21/12/99' )
def DateRangeISO(date_beg, date_end, workable=1):
    """returns list of dates in [date_beg,date_end]
    workable = 1 => keeps only workable days"""
    if not date_beg:
        raise ScoValueError("pas de date spécifiée !")
    if not date_end:
        date_end = date_beg
    r = []
    work_saturday = is_work_saturday()
    cur = ddmmyyyy(date_beg, work_saturday=work_saturday)
    end = ddmmyyyy(date_end, work_saturday=work_saturday)
    while cur <= end:
        if (not workable) or cur.iswork():
            r.append(cur)
        cur = cur.next_day()

    return [x.ISO() for x in r]


def day_names():
    """Returns week day names.
    If work_saturday property is set, include saturday
    """
    if is_work_saturday():
        return ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
    else:
        return ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]


def next_iso_day(date):
    "return date after date"
    d = ddmmyyyy(date, fmt="iso", work_saturday=is_work_saturday())
    return d.next_day().ISO()


def YearTable(
    year,
    events=[],
    firstmonth=9,
    lastmonth=7,
    halfday=0,
    dayattributes="",
    pad_width=8,
):
    """Generate a calendar table
    events = list of tuples (date, text, color, href [,halfday])
             where date is a string in ISO format (yyyy-mm-dd)
             halfday is boolean (true: morning, false: afternoon)
    text  = text to put in calendar (must be short, 1-5 cars) (optional)
    if halfday, generate 2 cells per day (morning, afternoon)
    """
    T = [
        '<table id="maincalendar" class="maincalendar" border="3" cellpadding="1" cellspacing="1" frame="box">'
    ]
    T.append("<tr>")
    month = firstmonth
    while 1:
        T.append('<td valign="top">')
        T.append(MonthTableHead(month))
        T.append(
            MonthTableBody(
                month,
                year,
                events,
                halfday,
                dayattributes,
                is_work_saturday(),
                pad_width=pad_width,
            )
        )
        T.append(MonthTableTail())
        T.append("</td>")
        if month == lastmonth:
            break
        month = month + 1
        if month > 12:
            month = 1
            year = year + 1
    T.append("</table>")
    return "\n".join(T)


def list_abs_in_range(etudid, debut, fin, matin=None, moduleimpl_id=None, cursor=None):
    """Liste des absences entre deux dates.

    Args:
        etudid:
        debut:   string iso date ("2020-03-12")
        end:     string iso date ("2020-03-12")
        matin:   None, True, False
        moduleimpl_id: restreint le comptage aux absences dans ce module

    Returns:
        List of absences
    """
    if matin != None:
        matin = _toboolean(matin)
        ismatin = " AND A.MATIN = %(matin)s "
    else:
        ismatin = ""
    if moduleimpl_id:
        modul = " AND A.MODULEIMPL_ID = %(moduleimpl_id)s "
    else:
        modul = ""
    if not cursor:
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT DISTINCT A.JOUR, A.MATIN
        FROM ABSENCES A
        WHERE A.ETUDID = %(etudid)s
        AND A.ESTABS"""
        + ismatin
        + modul
        + """
        AND A.JOUR BETWEEN %(debut)s AND %(fin)s
        """,
        {
            "etudid": etudid,
            "debut": debut,
            "fin": fin,
            "matin": matin,
            "moduleimpl_id": moduleimpl_id,
        },
    )
    res = cursor.dictfetchall()
    return res


def count_abs(etudid, debut, fin, matin=None, moduleimpl_id=None) -> int:
    """compte le nombre d'absences

    Args:
        etudid: l'étudiant considéré
        debut: date, chaîne iso, eg "2021-06-15"
        fin: date de fin, incluse
        matin: True (compte les matinées), False (les après-midi), None (les deux)
        moduleimpl_id: restreint le comptage aux absences dans ce module.

    Returns:
        An integer.
    """
    return len(
        list_abs_in_range(etudid, debut, fin, matin=matin, moduleimpl_id=moduleimpl_id)
    )


def count_abs_just(etudid, debut, fin, matin=None, moduleimpl_id=None) -> int:
    """compte le nombre d'absences justifiées

    Args:
        etudid: l'étudiant considéré
        debut: date, chaîne iso, eg "2021-06-15"
        fin: date de fin, incluse
        matin: True (compte les matinées), False (les après-midi), None (les deux)
        moduleimpl_id: restreint le comptage aux absences dans ce module.

    Returns:
        An integer.
    """
    if matin != None:
        matin = _toboolean(matin)
        ismatin = " AND A.MATIN = %(matin)s "
    else:
        ismatin = ""
    if moduleimpl_id:
        modul = " AND A.MODULEIMPL_ID = %(moduleimpl_id)s "
    else:
        modul = ""
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT COUNT(*) AS NbAbsJust FROM (
SELECT DISTINCT A.JOUR, A.MATIN
FROM ABSENCES A, ABSENCES B
WHERE A.ETUDID = %(etudid)s
    AND A.ETUDID = B.ETUDID
    AND A.JOUR = B.JOUR AND A.MATIN = B.MATIN
    AND A.JOUR BETWEEN %(debut)s AND %(fin)s
    AND A.ESTABS AND (A.ESTJUST OR B.ESTJUST)"""
        + ismatin
        + modul
        + """
) AS tmp
    """,
        vars(),
    )
    res = cursor.fetchone()[0]
    return res


def list_abs_date(etudid, beg_date, end_date):
    """Liste des absences et justifs entre deux dates (inclues)."""
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT jour, matin, estabs, estjust, description FROM ABSENCES A 
    WHERE A.ETUDID = %(etudid)s
    AND A.jour >= %(beg_date)s 
    AND A.jour <= %(end_date)s 
        """,
        vars(),
    )
    Abs = cursor.dictfetchall()
    # remove duplicates
    A = {}  # { (jour, matin) : abs }
    for a in Abs:
        jour, matin = a["jour"], a["matin"]
        if (jour, matin) in A:
            # garde toujours la description
            a["description"] = a["description"] or A[(jour, matin)]["description"]
            # et la justif:
            a["estjust"] = a["estjust"] or A[(jour, matin)]["estjust"]
            a["estabs"] = a["estabs"] or A[(jour, matin)]["estabs"]
            A[(jour, matin)] = a
        else:
            A[(jour, matin)] = a
        if A[(jour, matin)]["description"] is None:
            A[(jour, matin)]["description"] = ""
        # add hours: matin = 8:00 - 12:00, apresmidi = 12:00 - 18:00
        dat = "%04d-%02d-%02d" % (a["jour"].year, a["jour"].month, a["jour"].day)
        if a["matin"]:
            A[(jour, matin)]["begin"] = dat + " 08:00:00"
            A[(jour, matin)]["end"] = dat + " 11:59:59"
        else:
            A[(jour, matin)]["begin"] = dat + " 12:00:00"
            A[(jour, matin)]["end"] = dat + " 17:59:59"
    # sort
    R = list(A.values())
    R.sort(key=lambda x: (x["begin"]))
    return R


def _get_abs_description(a, cursor=None):
    "Description associee a l'absence"
    from app.scodoc import sco_moduleimpl

    if not cursor:
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    a = a.copy()
    # a['jour'] = a['jour'].date()
    if a["matin"]:  # devrait etre booleen... :-(
        a["matin"] = True
    else:
        a["matin"] = False
    cursor.execute(
        """select * from absences where etudid=%(etudid)s and jour=%(jour)s and matin=%(matin)s order by entry_date desc""",
        a,
    )
    A = cursor.dictfetchall()
    desc = None
    module = ""
    for a in A:
        if a["description"]:
            desc = a["description"]
        if a["moduleimpl_id"] and a["moduleimpl_id"] != "NULL":
            # Trouver le nom du module
            Mlist = sco_moduleimpl.moduleimpl_withmodule_list(
                moduleimpl_id=a["moduleimpl_id"]
            )
            if Mlist:
                M = Mlist[0]
                module += "%s " % M["module"]["code"]

    if desc:
        return "(%s) %s" % (desc, module)
    if module:
        return module
    return ""


def list_abs_jour(date, am=True, pm=True, is_abs=True, is_just=None):
    """Liste des absences et/ou justificatifs ce jour.
    is_abs: None (peu importe), True, False
    is_just: idem
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = """SELECT DISTINCT etudid, jour, matin FROM ABSENCES A 
WHERE A.jour = %(date)s
"""
    if is_abs != None:
        req += " AND A.estabs = %(is_abs)s"
    if is_just != None:
        req += " AND A.estjust = %(is_just)s"
    if not am:
        req += " AND NOT matin "
    if not pm:
        req += " AND matin"

    cursor.execute(req, {"date": date, "is_just": is_just, "is_abs": is_abs})
    A = cursor.dictfetchall()
    for a in A:
        a["description"] = _get_abs_description(a, cursor=cursor)
    return A


def list_abs_non_just_jour(date, am=True, pm=True):
    "Liste des absences non justifiees ce jour"
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    reqa = ""
    if not am:
        reqa += " AND NOT matin "
    if not pm:
        reqa += " AND matin "
    req = (
        """SELECT  etudid, jour, matin FROM ABSENCES A 
WHERE A.estabs 
AND A.jour = %(date)s
"""
        + reqa
        + """EXCEPT SELECT etudid, jour, matin FROM ABSENCES B 
WHERE B.estjust AND B.jour = %(date)s"""
        + reqa
    )

    cursor.execute(req, {"date": date})
    A = cursor.dictfetchall()
    for a in A:
        a["description"] = _get_abs_description(a, cursor=cursor)
    return A


def list_abs_non_just(etudid, datedebut):
    "Liste des absences NON justifiees (par ordre chronologique)"
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT ETUDID, JOUR, MATIN FROM ABSENCES A 
WHERE A.ETUDID = %(etudid)s
AND A.estabs 
AND A.jour >= %(datedebut)s
EXCEPT SELECT ETUDID, JOUR, MATIN FROM ABSENCES B 
WHERE B.estjust 
AND B.ETUDID = %(etudid)s
ORDER BY JOUR
    """,
        vars(),
    )
    A = cursor.dictfetchall()
    for a in A:
        a["description"] = _get_abs_description(a, cursor=cursor)
    return A


def list_abs_just(etudid, datedebut):
    "Liste des absences justifiees (par ordre chronologique)"
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT DISTINCT A.ETUDID, A.JOUR, A.MATIN FROM ABSENCES A, ABSENCES B
WHERE A.ETUDID = %(etudid)s
AND A.ETUDID = B.ETUDID 
AND A.JOUR = B.JOUR AND A.MATIN = B.MATIN AND A.JOUR >= %(datedebut)s
AND A.ESTABS AND (A.ESTJUST OR B.ESTJUST)
ORDER BY A.JOUR
    """,
        vars(),
    )
    A = cursor.dictfetchall()
    for a in A:
        a["description"] = _get_abs_description(a, cursor=cursor)
    return A


def list_abs_justifs(etudid, datedebut, datefin=None, only_no_abs=False):
    """Liste des justificatifs (avec ou sans absence relevée) à partir d'une date,
    ou, si datefin spécifié, entre deux dates.

    Args:
        etudid:
        datedebut: date de début, iso, eg "2002-03-15"
        datefin: date de fin, incluse, eg "2002-03-15"
        only_no_abs: si vrai, seulement les justificatifs correspondant
        aux jours sans absences relevées.
    Returns:
        Liste de dict absences
        {'etudid': 'EID214', 'jour': datetime.date(2021, 1, 15),
         'matin': True, 'description': ''
        }
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = """SELECT DISTINCT ETUDID, JOUR, MATIN FROM ABSENCES A
WHERE A.ETUDID = %(etudid)s
AND A.ESTJUST
AND A.JOUR >= %(datedebut)s"""
    if datefin:
        req += """AND A.JOUR <= %(datefin)s"""
    if only_no_abs:
        req += """
EXCEPT SELECT ETUDID, JOUR, MATIN FROM ABSENCES B 
WHERE B.estabs
AND B.ETUDID = %(etudid)s
    """
    cursor.execute(req, vars())
    A = cursor.dictfetchall()
    for a in A:
        a["description"] = _get_abs_description(a, cursor=cursor)

    return A


def add_absence(
    etudid,
    jour,
    matin,
    estjust,
    description=None,
    moduleimpl_id=None,
):
    "Ajoute une absence dans la bd"
    if _isFarFutur(jour):
        raise ScoValueError("date absence trop loin dans le futur !")
    estjust = _toboolean(estjust)
    matin = _toboolean(matin)
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """
        INSERT into absences (etudid,jour,estabs,estjust,matin,description, moduleimpl_id) 
        VALUES (%(etudid)s, %(jour)s, true, %(estjust)s, %(matin)s, %(description)s, %(moduleimpl_id)s )
        """,
        vars(),
    )
    logdb(
        cnx,
        "AddAbsence",
        etudid=etudid,
        msg="JOUR=%(jour)s,MATIN=%(matin)s,ESTJUST=%(estjust)s,description=%(description)s,moduleimpl_id=%(moduleimpl_id)s"
        % vars(),
    )
    cnx.commit()
    invalidate_abs_etud_date(etudid, jour)
    sco_abs_notification.abs_notify(etudid, jour)


def add_justif(etudid, jour, matin, description=None):
    "Ajoute un justificatif dans la base"
    # unpublished
    if _isFarFutur(jour):
        raise ScoValueError("date justificatif trop loin dans le futur !")
    matin = _toboolean(matin)
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """INSERT INTO absences (etudid, jour, estabs, estjust, matin, description)
        VALUES (%(etudid)s, %(jour)s, FALSE, TRUE, %(matin)s, %(description)s)
        """,
        vars(),
    )
    logdb(
        cnx,
        "AddJustif",
        etudid=etudid,
        msg="JOUR=%(jour)s,MATIN=%(matin)s" % vars(),
    )
    cnx.commit()
    invalidate_abs_etud_date(etudid, jour)


def add_abslist(abslist, moduleimpl_id=None):
    for a in abslist:
        etudid, jour, ampm = a.split(":")
        if ampm == "am":
            matin = 1
        elif ampm == "pm":
            matin = 0
        else:
            raise ValueError("invalid ampm !")
        # ajoute abs si pas deja absent
        if count_abs(etudid, jour, jour, matin, moduleimpl_id) == 0:
            add_absence(etudid, jour, matin, 0, "", moduleimpl_id)


def annule_absence(etudid, jour, matin, moduleimpl_id=None):
    """Annule une absence dans la base. N'efface pas l'éventuel justificatif.
    Args:
        etudid:
        jour: date, chaîne iso, eg "1999-12-31"
        matin:
        moduleimpl_id: si spécifié, n'annule que pour ce module.

    Returns:
        None
    """
    # unpublished
    matin = _toboolean(matin)
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = "delete from absences where jour=%(jour)s and matin=%(matin)s and etudid=%(etudid)s and estabs"
    if moduleimpl_id:
        req += " and moduleimpl_id=%(moduleimpl_id)s"
    cursor.execute(req, vars())
    logdb(
        cnx,
        "AnnuleAbsence",
        etudid=etudid,
        msg="JOUR=%(jour)s,MATIN=%(matin)s,moduleimpl_id=%(moduleimpl_id)s" % vars(),
    )
    cnx.commit()
    invalidate_abs_etud_date(etudid, jour)


def annule_justif(etudid, jour, matin):
    "Annule un justificatif"
    # unpublished
    matin = _toboolean(matin)
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        "delete from absences where jour=%(jour)s and matin=%(matin)s and etudid=%(etudid)s and ESTJUST AND NOT ESTABS",
        vars(),
    )
    cursor.execute(
        "update absences set estjust=false where jour=%(jour)s and matin=%(matin)s and etudid=%(etudid)s",
        vars(),
    )
    logdb(
        cnx,
        "AnnuleJustif",
        etudid=etudid,
        msg="JOUR=%(jour)s,MATIN=%(matin)s" % vars(),
    )
    cnx.commit()
    invalidate_abs_etud_date(etudid, jour)


# ---- BILLETS

_billet_absenceEditor = ndb.EditableTable(
    "billet_absence",
    "billet_id",
    (
        "billet_id",
        "etudid",
        "abs_begin",
        "abs_end",
        "description",
        "etat",
        "entry_date",
        "justified",
    ),
    sortkey="entry_date desc",
    input_formators={
        "etat": bool,
        "justified": bool,
    },
)

billet_absence_create = _billet_absenceEditor.create
billet_absence_delete = _billet_absenceEditor.delete
billet_absence_list = _billet_absenceEditor.list
billet_absence_edit = _billet_absenceEditor.edit

# ------ HTML Calendar functions (see YearTable function)

# MONTH/DAY NAMES:

MONTHNAMES = (
    "Janvier",
    "F&eacute;vrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "D&eacute;cembre",
)

MONTHNAMES_ABREV = (
    "Jan.",
    "F&eacute;v.",
    "Mars",
    "Avr.",
    "Mai&nbsp;",
    "Juin",
    "Juil",
    "Aout",
    "Sept",
    "Oct.",
    "Nov.",
    "D&eacute;c.",
)

DAYNAMES = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")

DAYNAMES_ABREV = ("L", "M", "M", "J", "V", "S", "D")

# COLORS:

WHITE = "#FFFFFF"
GRAY1 = "#EEEEEE"
GREEN3 = "#99CC99"
WEEKDAYCOLOR = GRAY1
WEEKENDCOLOR = GREEN3


def MonthTableHead(month):
    color = WHITE
    return """<table class="monthcalendar" border="0" cellpadding="0" cellspacing="0" frame="box">
     <tr bgcolor="%s"><td class="calcol" colspan="2" align="center">%s</td></tr>\n""" % (
        color,
        MONTHNAMES_ABREV[month - 1],
    )


def MonthTableTail():
    return "</table>\n"


def MonthTableBody(
    month, year, events=[], halfday=0, trattributes="", work_saturday=False, pad_width=8
):
    firstday, nbdays = calendar.monthrange(year, month)
    localtime = time.localtime()
    current_weeknum = time.strftime("%U", localtime)
    current_year = localtime[0]
    T = []
    # cherche date du lundi de la 1ere semaine de ce mois
    monday = ddmmyyyy("1/%d/%d" % (month, year))
    while monday.weekday != 0:
        monday = monday.prev()

    if work_saturday:
        weekend = ("D",)
    else:
        weekend = ("S", "D")

    if not halfday:
        for d in range(1, nbdays + 1):
            weeknum = time.strftime(
                "%U", time.strptime("%d/%d/%d" % (d, month, year), "%d/%m/%Y")
            )
            day = DAYNAMES_ABREV[(firstday + d - 1) % 7]
            if day in weekend:
                bgcolor = WEEKENDCOLOR
                weekclass = "wkend"
                attrs = ""
            else:
                bgcolor = WEEKDAYCOLOR
                weekclass = "wk" + str(monday).replace("/", "_")
                attrs = trattributes
            color = None
            legend = ""
            href = ""
            descr = ""
            # event this day ?
            # each event is a tuple (date, text, color, href)
            #  where date is a string in ISO format (yyyy-mm-dd)
            for ev in events:
                ev_year = int(ev[0][:4])
                ev_month = int(ev[0][5:7])
                ev_day = int(ev[0][8:10])
                if year == ev_year and month == ev_month and ev_day == d:
                    if ev[1]:
                        legend = ev[1]
                    if ev[2]:
                        color = ev[2]
                    if ev[3]:
                        href = ev[3]
                    if len(ev) > 4 and ev[4]:
                        descr = ev[4]
            #
            cc = []
            if color != None:
                cc.append('<td bgcolor="%s" class="calcell">' % color)
            else:
                cc.append('<td class="calcell">')

            if href:
                href = 'href="%s"' % href
            if descr:
                descr = 'title="%s"' % html.escape(descr, quote=True)
            if href or descr:
                cc.append("<a %s %s>" % (href, descr))

            if legend or d == 1:
                if pad_width != None:
                    n = pad_width - len(legend)  # pad to 8 cars
                    if n > 0:
                        legend = (
                            "&nbsp;" * (n // 2) + legend + "&nbsp;" * ((n + 1) // 2)
                        )
            else:
                legend = "&nbsp;"  # empty cell
            cc.append(legend)
            if href or descr:
                cc.append("</a>")
            cc.append("</td>")
            cell = "".join(cc)
            if day == "D":
                monday = monday.next_day(7)
            if (
                weeknum == current_weeknum
                and current_year == year
                and weekclass != "wkend"
            ):
                weekclass += " currentweek"
            T.append(
                '<tr bgcolor="%s" class="%s" %s><td class="calday">%d%s</td>%s</tr>'
                % (bgcolor, weekclass, attrs, d, day, cell)
            )
    else:
        # Calendar with 2 cells / day
        for d in range(1, nbdays + 1):
            weeknum = time.strftime(
                "%U", time.strptime("%d/%d/%d" % (d, month, year), "%d/%m/%Y")
            )
            day = DAYNAMES_ABREV[(firstday + d - 1) % 7]
            if day in weekend:
                bgcolor = WEEKENDCOLOR
                weekclass = "wkend"
                attrs = ""
            else:
                bgcolor = WEEKDAYCOLOR
                weekclass = "wk" + str(monday).replace("/", "_")
                attrs = trattributes
            if (
                weeknum == current_weeknum
                and current_year == year
                and weekclass != "wkend"
            ):
                weeknum += " currentweek"

            if day == "D":
                monday = monday.next_day(7)
            T.append(
                '<tr bgcolor="%s" class="wk%s" %s><td class="calday">%d%s</td>'
                % (bgcolor, weekclass, attrs, d, day)
            )
            cc = []
            for morning in (True, False):
                color = None
                legend = ""
                href = ""
                descr = ""
                for ev in events:
                    ev_year = int(ev[0][:4])
                    ev_month = int(ev[0][5:7])
                    ev_day = int(ev[0][8:10])
                    if ev[4] != None:
                        ev_half = int(ev[4])
                    else:
                        ev_half = 0
                    if (
                        year == ev_year
                        and month == ev_month
                        and ev_day == d
                        and morning == ev_half
                    ):
                        if ev[1]:
                            legend = ev[1]
                        if ev[2]:
                            color = ev[2]
                        if ev[3]:
                            href = ev[3]
                        if len(ev) > 5 and ev[5]:
                            descr = ev[5]
                #
                if color != None:
                    cc.append('<td bgcolor="%s" class="calcell">' % (color))
                else:
                    cc.append('<td class="calcell">')
                if href:
                    href = 'href="%s"' % href
                if descr:
                    descr = 'title="%s"' % html.escape(descr, quote=True)
                if href or descr:
                    cc.append("<a %s %s>" % (href, descr))
                if legend or d == 1:
                    n = 3 - len(legend)  # pad to 3 cars
                    if n > 0:
                        legend = (
                            "&nbsp;" * (n // 2) + legend + "&nbsp;" * ((n + 1) // 2)
                        )
                else:
                    legend = "&nbsp;&nbsp;&nbsp;"  # empty cell
                cc.append(legend)
                if href or descr:
                    cc.append("</a>")
                cc.append("</td>\n")
            T.append("".join(cc) + "</tr>")
    return "\n".join(T)


# --------------------------------------------------------------------
#
# Cache absences
#
# On cache (via REDIS ou autre, voir sco_cache.py) les _nombres_ d'absences
# (justifiées et non justifiées) de chaque etudiant dans un semestre donné.
# Le cache peut être invalidé soit par étudiant/semestre, soit pour tous
# les étudiant d'un semestre.
#
# On ne cache pas la liste des absences car elle est rarement utilisée (calendrier,
#  absences à une date donnée).
#
# --------------------------------------------------------------------


def get_abs_count(etudid, sem):
    """Les comptes d'absences de cet étudiant dans ce semestre:
    tuple (nb abs non justifiées, nb abs justifiées)
    Utilise un cache.
    """
    date_debut = sem["date_debut_iso"]
    date_fin = sem["date_fin_iso"]
    key = str(etudid) + "_" + date_debut + "_" + date_fin
    r = sco_cache.AbsSemEtudCache.get(key)
    if not r:
        nb_abs = count_abs(  # was CountAbs XXX
            etudid=etudid,
            debut=date_debut,
            fin=date_fin,
        )
        nb_abs_just = count_abs_just(  # XXX was CountAbsJust
            etudid=etudid,
            debut=date_debut,
            fin=date_fin,
        )
        r = (nb_abs, nb_abs_just)
        ans = sco_cache.AbsSemEtudCache.set(key, r)
        if not ans:
            log("warning: get_abs_count failed to cache")
    return r


def invalidate_abs_count(etudid, sem):
    """Invalidate (clear) cached counts"""
    date_debut = sem["date_debut_iso"]
    date_fin = sem["date_fin_iso"]
    key = str(etudid) + "_" + date_debut + "_" + date_fin
    sco_cache.AbsSemEtudCache.delete(key)


def invalidate_abs_count_sem(sem):
    """Invalidate (clear) cached abs counts for all the students of this semestre"""
    inscriptions = (
        sco_formsemestre_inscriptions.do_formsemestre_inscription_listinscrits(
            sem["formsemestre_id"]
        )
    )
    for ins in inscriptions:
        invalidate_abs_count(ins["etudid"], sem)


def invalidate_abs_etud_date(etudid, date):  # was invalidateAbsEtudDate
    """Doit etre appelé à chaque modification des absences pour cet étudiant et cette date.
    Invalide cache absence et caches semestre
    date: date au format ISO
    """
    from app.scodoc import sco_compute_moy

    # Semestres a cette date:
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    sems = [
        sem
        for sem in etud["sems"]
        if sem["date_debut_iso"] <= date and sem["date_fin_iso"] >= date
    ]

    # Invalide les PDF et les absences:
    for sem in sems:
        # Inval cache bulletin et/ou note_table
        if sco_compute_moy.formsemestre_expressions_use_abscounts(
            sem["formsemestre_id"]
        ):
            # certaines formules utilisent les absences
            pdfonly = False
        else:
            # efface toujours le PDF car il affiche en général les absences
            pdfonly = True

        sco_cache.invalidate_formsemestre(
            formsemestre_id=sem["formsemestre_id"], pdfonly=pdfonly
        )

        # Inval cache compteurs absences:
        invalidate_abs_count_sem(sem)
