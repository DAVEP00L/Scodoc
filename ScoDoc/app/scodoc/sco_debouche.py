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
#   Emmanuel Viennet      emmanuel.viennet@gmail.com
#
##############################################################################

"""
Rapport (table) avec dernier semestre fréquenté et débouché de chaque étudiant
"""
import http
from flask import url_for, g, request

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.sco_exceptions import AccessDenied
from app.scodoc.scolog import logdb
from app.scodoc.gen_tables import GenTable
from app.scodoc import safehtml
from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_permissions_check
from app.scodoc import sco_preferences
from app.scodoc import sco_tag_module
from app.scodoc import sco_etud
import sco_version


def report_debouche_date(start_year=None, format="html"):
    """Rapport (table) pour les débouchés des étudiants sortis
    à partir de l'année indiquée.
    """
    if not start_year:
        return report_debouche_ask_date("Année de début de la recherche")
    else:
        try:
            start_year = int(start_year)
        except ValueError:
            return report_debouche_ask_date(
                "Année invalide. Année de début de la recherche"
            )

    if format == "xls":
        keep_numeric = True  # pas de conversion des notes en strings
    else:
        keep_numeric = False

    etudids = get_etudids_with_debouche(start_year)
    tab = table_debouche_etudids(etudids, keep_numeric=keep_numeric)

    tab.filename = scu.make_filename("debouche_scodoc_%s" % start_year)
    tab.origin = (
        "Généré par %s le " % sco_version.SCONAME + scu.timedate_human_repr() + ""
    )
    tab.caption = "Récapitulatif débouchés à partir du 1/1/%s." % start_year
    tab.base_url = "%s?start_year=%s" % (request.base_url, start_year)
    return tab.make_page(
        title="""<h2 class="formsemestre">Débouchés étudiants </h2>""",
        init_qtip=True,
        javascripts=["js/etud_info.js"],
        format=format,
        with_html_headers=True,
    )


def get_etudids_with_debouche(start_year):
    """Liste des etudids de tous les semestres terminant
    à partir du 1er janvier de start_year
    et ayant un 'debouche' renseigné.
    """
    start_date = str(start_year) + "-01-01"
    # Recupere tous les etudid avec un debouché renseigné et une inscription dans un semestre
    # posterieur à la date de depart:
    # r = ndb.SimpleDictFetch(
    #                    """SELECT DISTINCT i.etudid
    #                    FROM notes_formsemestre_inscription i, admissions adm, notes_formsemestre s
    #                    WHERE adm.debouche is not NULL
    #                    AND i.etudid = adm.etudid AND i.formsemestre_id = s.formsemestre_id
    #                    AND s.date_fin >= %(start_date)s
    #                    """,
    #                    {'start_date' : start_date })

    r = ndb.SimpleDictFetch(
        """SELECT DISTINCT i.etudid
        FROM notes_formsemestre_inscription i, notes_formsemestre s, itemsuivi it
        WHERE i.etudid = it.etudid
        AND i.formsemestre_id = s.id AND s.date_fin >= %(start_date)s
        AND s.dept_id = %(dept_id)s
        """,
        {"start_date": start_date, "dept_id": g.scodoc_dept_id},
    )

    return [x["etudid"] for x in r]


def table_debouche_etudids(etudids, keep_numeric=True):
    """Rapport pour ces etudiants"""
    L = []
    for etudid in etudids:
        etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
        # retrouve le "dernier" semestre (au sens de la date de fin)
        sems = etud["sems"]
        es = [(s["date_fin_iso"], i) for i, s in enumerate(sems)]
        imax = max(es)[1]
        last_sem = sems[imax]
        nt = sco_cache.NotesTableCache.get(last_sem["formsemestre_id"])
        row = {
            "etudid": etudid,
            "civilite": etud["civilite"],
            "nom": etud["nom"],
            "prenom": etud["prenom"],
            "_nom_target": url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
            ),
            "_prenom_target": url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
            ),
            "_nom_td_attrs": 'id="%s" class="etudinfo"' % (etud["etudid"]),
            # 'debouche' : etud['debouche'],
            "moy": scu.fmt_note(nt.get_etud_moy_gen(etudid), keep_numeric=keep_numeric),
            "rang": nt.get_etud_rang(etudid),
            "effectif": len(nt.T),
            "semestre_id": last_sem["semestre_id"],
            "semestre": last_sem["titre"],
            "date_debut": last_sem["date_debut"],
            "date_fin": last_sem["date_fin"],
            "periode": "%s - %s" % (last_sem["mois_debut"], last_sem["mois_fin"]),
            "sem_ident": "%s %s"
            % (last_sem["date_debut_iso"], last_sem["titre"]),  # utile pour tris
        }

        # recherche des débouchés
        debouche = itemsuivi_list_etud(etudid)  # liste de plusieurs items
        if debouche:
            row["debouche"] = "<br>".join(
                [
                    str(it["item_date"])
                    + " : "
                    + it["situation"]
                    + " <i>"
                    + it["tags"]
                    + "</i>"
                    for it in debouche
                ]
            )  #
        else:
            row["debouche"] = "non renseigné"
        L.append(row)
    L.sort(key=lambda x: x["sem_ident"])

    titles = {
        "civilite": "",
        "nom": "Nom",
        "prenom": "Prénom",
        "semestre": "Dernier semestre",
        "semestre_id": "S",
        "periode": "Dates",
        "moy": "Moyenne",
        "rang": "Rang",
        "effectif": "Eff.",
        "debouche": "Débouché",
    }
    tab = GenTable(
        columns_ids=(
            "semestre",
            "semestre_id",
            "periode",
            "civilite",
            "nom",
            "prenom",
            "moy",
            "rang",
            "effectif",
            "debouche",
        ),
        titles=titles,
        rows=L,
        # html_col_width='4em',
        html_sortable=True,
        html_class="table_leftalign table_listegroupe",
        preferences=sco_preferences.SemPreferences(),
    )
    return tab


def report_debouche_ask_date(msg: str) -> str:
    """Formulaire demande date départ"""
    return f"""{html_sco_header.sco_header()}
    <h2>Table des débouchés des étudiants</h2>
    <form method="GET">
    {msg} 
    <input type="text" name="start_year" value="" size=10/>
    </form>
    {html_sco_header.sco_footer()}
    """


# ----------------------------------------------------------------------------
#
# Nouveau suivi des etudiants (nov 2017)
#
# ----------------------------------------------------------------------------


_itemsuiviEditor = ndb.EditableTable(
    "itemsuivi",
    "itemsuivi_id",
    ("itemsuivi_id", "etudid", "item_date", "situation"),
    sortkey="item_date desc",
    convert_null_outputs_to_empty=True,
    output_formators={
        "situation": safehtml.html_to_safe_html,
        "item_date": ndb.DateISOtoDMY,
    },
    input_formators={"item_date": ndb.DateDMYtoISO},
)

_itemsuivi_create = _itemsuiviEditor.create
_itemsuivi_delete = _itemsuiviEditor.delete
_itemsuivi_list = _itemsuiviEditor.list
_itemsuivi_edit = _itemsuiviEditor.edit


class ItemSuiviTag(sco_tag_module.ScoTag):
    """Les tags sur les items"""

    tag_table = "itemsuivi_tags"  # table (tag_id, title)
    assoc_table = "itemsuivi_tags_assoc"  # table (tag_id, object_id)
    obj_colname = "itemsuivi_id"  # column name for object_id in assoc_table


def itemsuivi_get(cnx, itemsuivi_id, ignore_errors=False):
    """get an item"""
    items = _itemsuivi_list(cnx, {"itemsuivi_id": itemsuivi_id})
    if items:
        return items[0]
    elif not ignore_errors:
        raise ValueError("invalid itemsuivi_id")
    return None


def itemsuivi_suppress(itemsuivi_id):
    """Suppression d'un item"""
    if not sco_permissions_check.can_edit_suivi():
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    cnx = ndb.GetDBConnexion()
    item = itemsuivi_get(cnx, itemsuivi_id, ignore_errors=True)
    if item:
        _itemsuivi_delete(cnx, itemsuivi_id)
        logdb(cnx, method="itemsuivi_suppress", etudid=item["etudid"])
        log("suppressed itemsuivi %s" % (itemsuivi_id,))
    return ("", 204)


def itemsuivi_create(etudid, item_date=None, situation="", format=None):
    """Creation d'un item"""
    if not sco_permissions_check.can_edit_suivi():
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    cnx = ndb.GetDBConnexion()
    itemsuivi_id = _itemsuivi_create(
        cnx, args={"etudid": etudid, "item_date": item_date, "situation": situation}
    )
    logdb(cnx, method="itemsuivi_create", etudid=etudid)
    log("created itemsuivi %s for %s" % (itemsuivi_id, etudid))
    item = itemsuivi_get(cnx, itemsuivi_id)
    if format == "json":
        return scu.sendJSON(item)
    return item


def itemsuivi_set_date(itemsuivi_id, item_date):
    """set item date
    item_date is a string dd/mm/yyyy
    """
    if not sco_permissions_check.can_edit_suivi():
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    # log('itemsuivi_set_date %s : %s' % (itemsuivi_id, item_date))
    cnx = ndb.GetDBConnexion()
    item = itemsuivi_get(cnx, itemsuivi_id)
    item["item_date"] = item_date
    _itemsuivi_edit(cnx, item)
    return ("", 204)


def itemsuivi_set_situation(object, value):
    """set situation"""
    if not sco_permissions_check.can_edit_suivi():
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    itemsuivi_id = object
    situation = value.strip("-_ \t")
    # log('itemsuivi_set_situation %s : %s' % (itemsuivi_id, situation))
    cnx = ndb.GetDBConnexion()
    item = itemsuivi_get(cnx, itemsuivi_id)
    item["situation"] = situation
    _itemsuivi_edit(cnx, item)
    return situation or scu.IT_SITUATION_MISSING_STR


def itemsuivi_list_etud(etudid, format=None):
    """Liste des items pour cet étudiant, avec tags"""
    cnx = ndb.GetDBConnexion()
    items = _itemsuivi_list(cnx, {"etudid": etudid})
    for it in items:
        it["tags"] = ", ".join(itemsuivi_tag_list(it["itemsuivi_id"]))
    if format == "json":
        return scu.sendJSON(items)
    return items


def itemsuivi_tag_list(itemsuivi_id):
    """les noms de tags associés à cet item"""
    r = ndb.SimpleDictFetch(
        """SELECT t.title
          FROM itemsuivi_tags_assoc a, itemsuivi_tags t
          WHERE a.tag_id = t.id
          AND a.itemsuivi_id = %(itemsuivi_id)s
          """,
        {"itemsuivi_id": itemsuivi_id},
    )
    return [x["title"] for x in r]


def itemsuivi_tag_search(term):
    """List all used tag names (for auto-completion)"""
    # restrict charset to avoid injections
    if not scu.ALPHANUM_EXP.match(term):
        data = []
    else:
        r = ndb.SimpleDictFetch(
            "SELECT title FROM itemsuivi_tags WHERE title LIKE %(term)s AND dept_id=%(dept_id)s",
            {
                "term": term + "%",
                "dept_id": g.scodoc_dept_id,
            },
        )
        data = [x["title"] for x in r]

    return scu.sendJSON(data)


def itemsuivi_tag_set(itemsuivi_id="", taglist=None):
    """taglist may either be:
    a string with tag names separated by commas ("un;deux")
    or a list of strings (["un", "deux"])
    """
    if not sco_permissions_check.can_edit_suivi():
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    if not taglist:
        taglist = []
    elif isinstance(taglist, str):
        taglist = taglist.split(",")
    taglist = [t.strip() for t in taglist]
    # log('itemsuivi_tag_set: itemsuivi_id=%s taglist=%s' % (itemsuivi_id, taglist))
    # Sanity check:
    cnx = ndb.GetDBConnexion()
    _ = itemsuivi_get(cnx, itemsuivi_id)

    newtags = set(taglist)
    oldtags = set(itemsuivi_tag_list(itemsuivi_id))
    to_del = oldtags - newtags
    to_add = newtags - oldtags

    # should be atomic, but it's not.
    for tagname in to_add:
        t = ItemSuiviTag(tagname, object_id=itemsuivi_id)
    for tagname in to_del:
        t = ItemSuiviTag(tagname)
        t.remove_tag_from_object(itemsuivi_id)
    return "", http.HTTPStatus.NO_CONTENT
