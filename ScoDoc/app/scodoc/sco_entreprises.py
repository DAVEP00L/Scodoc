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

"""Fonctions sur les entreprises
"""
# codes anciens déplacés de ZEntreprise
import datetime
from operator import itemgetter

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.notesdb import ScoDocCursor, EditableTable, DateISOtoDMY, DateDMYtoISO


def _format_nom(nom):
    "formatte nom (filtre en entree db) d'une entreprise"
    if not nom:
        return nom
    return nom[0].upper() + nom[1:]


class EntreprisesEditor(EditableTable):
    def delete(self, cnx, oid):
        "delete correspondants and contacts, then self"
        # first, delete all correspondants and contacts
        cursor = cnx.cursor(cursor_factory=ScoDocCursor)
        cursor.execute(
            "delete from entreprise_contact where entreprise_id=%(entreprise_id)s",
            {"entreprise_id": oid},
        )
        cursor.execute(
            "delete from entreprise_correspondant where entreprise_id=%(entreprise_id)s",
            {"entreprise_id": oid},
        )
        cnx.commit()
        EditableTable.delete(self, cnx, oid)

    def list(
        self,
        cnx,
        args={},
        operator="and",
        test="=",
        sortkey=None,
        sort_on_contact=False,
        limit="",
        offset="",
    ):
        # list, then sort on date of last contact
        R = EditableTable.list(
            self,
            cnx,
            args=args,
            operator=operator,
            test=test,
            sortkey=sortkey,
            limit=limit,
            offset=offset,
        )
        if sort_on_contact:
            for r in R:
                c = do_entreprise_contact_list(
                    args={"entreprise_id": r["entreprise_id"]},
                    disable_formatting=True,
                )
                if c:
                    r["date"] = max([x["date"] or datetime.date.min for x in c])
                else:
                    r["date"] = datetime.date.min
            # sort
            R.sort(key=itemgetter("date"))
            for r in R:
                r["date"] = DateISOtoDMY(r["date"])
        return R

    def list_by_etud(
        self, cnx, args={}, sort_on_contact=False, disable_formatting=False
    ):
        "cherche rentreprise ayant eu contact avec etudiant"
        cursor = cnx.cursor(cursor_factory=ScoDocCursor)
        cursor.execute(
            "select E.*, I.nom as etud_nom, I.prenom as etud_prenom, C.date from entreprises E, entreprise_contact C, identite I where C.entreprise_id = E.entreprise_id and C.etudid = I.etudid and I.nom ~* %(etud_nom)s ORDER BY E.nom",
            args,
        )
        _, res = [x[0] for x in cursor.description], cursor.dictfetchall()
        R = []
        for r in res:
            r["etud_prenom"] = r["etud_prenom"] or ""
            d = {}
            for key in r:
                v = r[key]
                # format value
                if not disable_formatting and key in self.output_formators:
                    v = self.output_formators[key](v)
                d[key] = v
            R.append(d)
        # sort
        if sort_on_contact:
            R.sort(key=lambda x: (x["date"] or datetime.date.min))

        for r in R:
            r["date"] = DateISOtoDMY(r["date"] or datetime.date.min)
        return R


_entreprisesEditor = EntreprisesEditor(
    "entreprises",
    "entreprise_id",
    (
        "entreprise_id",
        "nom",
        "adresse",
        "ville",
        "codepostal",
        "pays",
        "contact_origine",
        "secteur",
        "privee",
        "localisation",
        "qualite_relation",
        "plus10salaries",
        "note",
        "date_creation",
    ),
    filter_dept=True,
    sortkey="nom",
    input_formators={
        "nom": _format_nom,
        "plus10salaries": bool,
    },
)

# -----------  Correspondants
_entreprise_correspEditor = EditableTable(
    "entreprise_correspondant",
    "entreprise_corresp_id",
    (
        "entreprise_corresp_id",
        "entreprise_id",
        "civilite",
        "nom",
        "prenom",
        "fonction",
        "phone1",
        "phone2",
        "mobile",
        "fax",
        "mail1",
        "mail2",
        "note",
    ),
    sortkey="nom",
)


# -----------  Contacts
_entreprise_contactEditor = EditableTable(
    "entreprise_contact",
    "entreprise_contact_id",
    (
        "entreprise_contact_id",
        "date",
        "type_contact",
        "entreprise_id",
        "entreprise_corresp_id",
        "etudid",
        "description",
        "enseignant",
    ),
    sortkey="date",
    output_formators={"date": DateISOtoDMY},
    input_formators={"date": DateDMYtoISO},
)


def do_entreprise_create(args):
    "entreprise_create"
    cnx = ndb.GetDBConnexion()
    r = _entreprisesEditor.create(cnx, args)
    return r


def do_entreprise_delete(oid):
    "entreprise_delete"
    cnx = ndb.GetDBConnexion()
    _entreprisesEditor.delete(cnx, oid)


def do_entreprise_list(**kw):
    "entreprise_list"
    cnx = ndb.GetDBConnexion()
    return _entreprisesEditor.list(cnx, **kw)


def do_entreprise_list_by_etud(**kw):
    "entreprise_list_by_etud"
    cnx = ndb.GetDBConnexion()
    return _entreprisesEditor.list_by_etud(cnx, **kw)


def do_entreprise_edit(*args, **kw):
    "entreprise_edit"
    cnx = ndb.GetDBConnexion()
    _entreprisesEditor.edit(cnx, *args, **kw)


def do_entreprise_correspondant_create(args):
    "entreprise_correspondant_create"
    cnx = ndb.GetDBConnexion()
    r = _entreprise_correspEditor.create(cnx, args)
    return r


def do_entreprise_correspondant_delete(oid):
    "entreprise_correspondant_delete"
    cnx = ndb.GetDBConnexion()
    _entreprise_correspEditor.delete(cnx, oid)


def do_entreprise_correspondant_list(**kw):
    "entreprise_correspondant_list"
    cnx = ndb.GetDBConnexion()
    return _entreprise_correspEditor.list(cnx, **kw)


def do_entreprise_correspondant_edit(*args, **kw):
    "entreprise_correspondant_edit"
    cnx = ndb.GetDBConnexion()
    _entreprise_correspEditor.edit(cnx, *args, **kw)


def do_entreprise_correspondant_listnames(args={}):
    "-> liste des noms des correspondants (pour affichage menu)"
    C = do_entreprise_correspondant_list(args=args)
    return [(x["prenom"] + " " + x["nom"], str(x["entreprise_corresp_id"])) for x in C]


def do_entreprise_contact_delete(oid):
    "entreprise_contact_delete"
    cnx = ndb.GetDBConnexion()
    _entreprise_contactEditor.delete(cnx, oid)


def do_entreprise_contact_list(**kw):
    "entreprise_contact_list"
    cnx = ndb.GetDBConnexion()
    return _entreprise_contactEditor.list(cnx, **kw)


def do_entreprise_contact_edit(*args, **kw):
    "entreprise_contact_edit"
    cnx = ndb.GetDBConnexion()
    _entreprise_contactEditor.edit(cnx, *args, **kw)


def do_entreprise_contact_create(args):
    "entreprise_contact_create"
    cnx = ndb.GetDBConnexion()
    r = _entreprise_contactEditor.create(cnx, args)
    return r


def do_entreprise_check_etudiant(etudiant):
    """Si etudiant est vide, ou un ETUDID valide, ou un nom unique,
    retourne (1, ETUDID).
    Sinon, retourne (0, 'message explicatif')
    """
    etudiant = etudiant.strip().translate(
        str.maketrans("", "", "'()")
    )  # suppress parens and quote from name
    if not etudiant:
        return 1, None
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ScoDocCursor)
    cursor.execute(
        "select etudid, nom, prenom from identite where upper(nom) ~ upper(%(etudiant)s) or etudid=%(etudiant)s",
        {"etudiant": etudiant},
    )
    r = cursor.fetchall()
    if len(r) < 1:
        return 0, 'Aucun etudiant ne correspond à "%s"' % etudiant
    elif len(r) > 10:
        return (
            0,
            "<b>%d etudiants</b> correspondent à ce nom (utilisez le code)" % len(r),
        )
    elif len(r) > 1:
        e = ['<ul class="entreprise_etud_list">']
        for x in r:
            e.append(
                "<li>%s %s (code %s)</li>" % ((x[1]).upper(), x[2] or "", x[0].strip())
            )
        e.append("</ul>")
        return (
            0,
            "Les étudiants suivants correspondent: préciser le nom complet ou le code\n"
            + "\n".join(e),
        )
    else:  # une seule reponse !
        return 1, r[0][0].strip()