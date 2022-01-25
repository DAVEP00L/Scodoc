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

"""Export d'une table avec les résultats de tous les étudiants
"""
from flask import url_for, g, request

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_bac
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_formations
from app.scodoc import sco_preferences
from app.scodoc import sco_pvjury
from app.scodoc import sco_etud
import sco_version
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_codes_parcours import NO_SEMESTRE_ID


def _build_results_table(start_date=None, end_date=None, types_parcours=[]):
    """Construit une table avec les résultats de jury de TOUS les étudiants
    de TOUS les semestres ScoDoc de ce département entre les dates indiquées
    (c'est à dire commençant APRES ou à start_date et terminant avant ou à end_date)
    Les dates sont des chaines iso.
    """
    formsemestre_ids = get_set_formsemestre_id_dates(start_date, end_date)
    # Décisions de jury de tous les semestres:
    dpv_by_sem = {}
    for formsemestre_id in formsemestre_ids:
        dpv_by_sem[formsemestre_id] = sco_pvjury.dict_pvjury(
            formsemestre_id, with_parcours_decisions=True
        )

    semlist = [dpv["formsemestre"] for dpv in dpv_by_sem.values() if dpv]
    semlist_parcours = []
    for sem in semlist:
        sem["formation"] = sco_formations.formation_list(
            args={"formation_id": sem["formation_id"]}
        )[0]
        sem["parcours"] = sco_codes_parcours.get_parcours_from_code(
            sem["formation"]["type_parcours"]
        )
        if sem["parcours"].TYPE_PARCOURS in types_parcours:
            semlist_parcours.append(sem)
    formsemestre_ids_parcours = [sem["formsemestre_id"] for sem in semlist_parcours]

    # Ensemble des étudiants
    etuds_infos = (
        {}
    )  # etudid : { formsemestre_id d'inscription le plus recent dans les dates considérées, etud }
    for formsemestre_id in formsemestre_ids_parcours:
        nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etudids
        etudids = nt.get_etudids()
        for etudid in etudids:
            if etudid not in etuds_infos:  # pas encore traité ?
                etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
                for sem in etud["sems"]:  # le plus récent d'abord
                    if sem["formsemestre_id"] in formsemestre_ids_parcours:
                        etuds_infos[etudid] = {
                            "recent_formsemestre_id": sem["formsemestre_id"],
                            "etud": etud,
                        }
                        break
                # sanity check
                assert etudid in etuds_infos
    # Construit la table (semblable à pvjury_table)
    rows, titles, columns_ids = _build_results_list(dpv_by_sem, etuds_infos)
    tab = GenTable(
        rows=rows,
        titles=titles,
        columns_ids=columns_ids,
        filename=scu.make_filename("scodoc-results-%s-%s" % (start_date, end_date)),
        caption="Résultats ScoDoc de %s à %s" % (start_date, end_date),
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        html_class="table_leftalign",
        html_sortable=True,
        preferences=sco_preferences.SemPreferences(),
    )
    return tab, semlist


def _build_results_list(dpv_by_sem, etuds_infos):
    """Construit la table (semblable à pvjury_table)
    Returns:
        rows, titles, columns_ids
    """
    titles = {
        "anneescolaire": "Année",
        "periode": "Période",
        "sid": "Semestre",
        "etudid": "etudid",
        "code_nip": "NIP",
        "nom": "Nom",
        "prenom": "Prénom",
        "civilite_str": "Civ.",
        "nom_usuel": "Nom usuel",
        "bac": "Bac",
        "parcours": "Parcours",
        "devenir": "Devenir",
    }
    columns_ids = [
        "anneescolaire",
        "periode",
        "sid",
        "code_nip",
        "civilite_str",
        "nom",
        # 'nom_usuel', # inutile ?
        "prenom",
        "bac",
        "parcours",
    ]

    # Recherche la liste des indices de semestres à considérer
    all_idx = set()
    for etudid in etuds_infos:
        # la décision de jury à considérer pour cet étudiant:
        e = dpv_by_sem[etuds_infos[etudid]["recent_formsemestre_id"]]["decisions_dict"][
            etudid
        ]
        all_idx |= set(e["parcours_decisions"].keys())
    sem_ids = sorted(all_idx)
    # ajoute les titres des colonnes résultats de semestres
    for i in sem_ids:
        if i != NO_SEMESTRE_ID:
            titles[i] = "S%d" % i
        else:
            titles[i] = "S"  # pas très parlant ?
        columns_ids += [i]
    columns_ids += ["devenir"]
    # Construit la liste:
    rows = []
    for etudid in etuds_infos:
        etud = etuds_infos[etudid]["etud"]
        bac = sco_bac.Baccalaureat(etud["bac"], etud["specialite"])
        dpv = dpv_by_sem[etuds_infos[etudid]["recent_formsemestre_id"]]
        dec = dpv["decisions_dict"][etudid]
        l = {
            "etudid": etudid,
            "code_nip": etud["code_nip"],
            "nom": etud["nom"],
            "nom_usuel": etud["nom_usuel"],
            "prenom": etud["prenom"],
            "civilite_str": etud["civilite_str"],
            "_nom_target": "%s"
            % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            "_nom_td_attrs": 'id="%s" class="etudinfo"' % etudid,
            "bac": bac.abbrev(),
            "parcours": dec["parcours"],
        }
        for sem in reversed(etud["sems"]):
            r = l.copy()
            dpv = dpv_by_sem.get(sem["formsemestre_id"], None)
            if dpv:  # semestre à inclure dans ce rapport
                dec = dpv["decisions_dict"].get(etudid, None)
                if dec and dec["decision_sem"]:
                    code = dec["decision_sem"]["code"]
                    if dec["validation_parcours"]:
                        r["devenir"] = "Diplôme obtenu"
                    else:
                        r["devenir"] = dec["autorisations_descr"]
                else:
                    code = "-"
                r[sem["semestre_id"]] = code
                r["periode"] = sem["periode"]
                r["anneescolaire"] = scu.annee_scolaire_debut(
                    int(sem["annee_debut"]), sem["mois_debut_ord"]
                )
                r["sid"] = "{} {} {}".format(
                    sem["sem_id_txt"], g.scodoc_dept, sem["modalite"]
                )
                rows.append(r)

    return rows, titles, columns_ids


def get_set_formsemestre_id_dates(start_date, end_date):
    """Ensemble des formsemestre_id entre ces dates"""
    s = ndb.SimpleDictFetch(
        """SELECT id
        FROM notes_formsemestre
        WHERE date_debut >= %(start_date)s AND date_fin <= %(end_date)s
        """,
        {"start_date": start_date, "end_date": end_date},
    )
    return {x["id"] for x in s}


def scodoc_table_results(start_date="", end_date="", types_parcours=[], format="html"):
    """Page affichant la table des résultats
    Les dates sont en dd/mm/yyyy (datepicker javascript)
    types_parcours est la liste des types de parcours à afficher
    (liste de chaines, eg ['100', '210'] )
    """
    log("scodoc_table_results: start_date=%s" % (start_date,))  # XXX
    if not types_parcours:
        types_parcours = []
    if not isinstance(types_parcours, list):
        types_parcours = [types_parcours]
    if start_date:
        start_date_iso = ndb.DateDMYtoISO(start_date)
    if end_date:
        end_date_iso = ndb.DateDMYtoISO(end_date)
    types_parcours = [int(x) for x in types_parcours if x]

    if start_date and end_date:
        tab, semlist = _build_results_table(
            start_date_iso, end_date_iso, types_parcours
        )
        tab.base_url = "%s?start_date=%s&end_date=%s&types_parcours=%s" % (
            request.base_url,
            start_date,
            end_date,
            "&types_parcours=".join([str(x) for x in types_parcours]),
        )
        if format != "html":
            return tab.make_page(format=format, with_html_headers=False)
        tab_html = tab.html()
        nb_rows = tab.get_nb_rows()
    else:
        tab = None
        nb_rows = 0
        tab_html = ""
        semlist = []

    # affiche la liste des semestres utilisés:
    info_sems = ["<ul>"]
    menu_options = []
    type_parcours_set = set()
    for sem in sorted(semlist, key=lambda x: x["dateord"]):
        if sem["parcours"].TYPE_PARCOURS in types_parcours:
            selected = "selected"
        else:
            selected = ""
        if sem["parcours"].TYPE_PARCOURS not in type_parcours_set:
            type_parcours_set.add(sem["parcours"].TYPE_PARCOURS)
            menu_options.append(
                '<option value="%s" %s>%s</option>'
                % (sem["parcours"].TYPE_PARCOURS, selected, sem["parcours"].__doc__)
            )

        if sem["parcours"].TYPE_PARCOURS in types_parcours:
            info_sems.append(
                '<li><a class="stdlink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titremois)s</a></li>'
                % sem
            )

    info_sems.append("</ul>")

    H = [
        html_sco_header.sco_header(
            page_title="Export résultats",
            init_qtip=True,
            javascripts=html_sco_header.BOOTSTRAP_MULTISELECT_JS
            + ["js/etud_info.js", "js/export_results.js"],
            cssstyles=html_sco_header.BOOTSTRAP_MULTISELECT_CSS,
        ),
        # XXX
        """
        <h2>Table des résultats de tous les semestres</h2>
        <p class="warning">Développement en cours / attention !</p>
        """,
        _DATE_FORM.format(
            start_date=start_date,
            end_date=end_date,
            menu_options="\n".join(menu_options),
        ),
        """<div>
        <h4>%d étudiants dans les %d semestres de cette période</h4>
        </div>
        """
        % (nb_rows, len(semlist)),
        tab_html,
        """<div><h4>Semestres pris en compte:</h4>
        """,
        "\n".join(info_sems),
        """</div>""",
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


# Formulaire pour saisie dates et sélection parcours
_DATE_FORM = """
<form method="get">
<div><b>Choisir les dates :</b>
<div>Début: <input type="text" name="start_date" size="10" value="{start_date}" class="datepicker"/> </div>
<div>Fin: <input type="text" name="end_date" size="10" value="{end_date}" class="datepicker"/></div>
<input type="submit" name="" value=" OK " width=100/>
</div>
<div>
<b>Types de parcours :</b>
<select name="types_parcours" id="parcours_sel" class="multiselect" multiple="multiple">
{menu_options}
</select>

<input type="submit" name="" value=" charger " width=100/>
</form>
"""

# ------- debug
"""
# /opt/scodoc/bin/zopectl debug 
from debug import *
from app.scodoc.sco_export_results import *
_ = go_dept(app, 'RT').Notes
etudid = 'EID27764'
etud = sco_etud.get_etud_info( etudid=etudid, filled=True)[0]

start_date='2015-08-15'
end_date='2017-08-31'

formsemestre_ids = get_set_formsemestre_id_dates( start_date, end_date)
dpv_by_sem = {}
for formsemestre_id in formsemestre_ids:
    dpv_by_sem[formsemestre_id] = sco_pvjury.dict_pvjury( formsemestre_id, with_parcours_decisions=True)

semlist = [ dpv['formsemestre'] for dpv in dpv_by_sem.values() ]

"""
