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

"""Rapports sur lycées d'origine des étudiants d'un  semestre.
  - statistiques decisions
  - suivi cohortes
"""
from operator import itemgetter

from flask import url_for, g, request

import app
import app.scodoc.sco_utils as scu
from app.scodoc import html_sco_header
from app.scodoc import sco_formsemestre
from app.scodoc import sco_preferences
from app.scodoc import sco_report
from app.scodoc import sco_etud
import sco_version
from app.scodoc.gen_tables import GenTable


def formsemestre_table_etuds_lycees(
    formsemestre_id, group_lycees=True, only_primo=False
):
    """Récupère liste d'etudiants avec etat et decision."""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etuds = sco_report.tsp_etud_list(formsemestre_id, only_primo=only_primo)[0]
    if only_primo:
        primostr = "primo-entrants du "
    else:
        primostr = "du "
    title = "Lycées des étudiants %ssemestre " % primostr + sem["titreannee"]
    return _table_etuds_lycees(
        etuds,
        group_lycees,
        title,
        sco_preferences.SemPreferences(formsemestre_id),
    )


def scodoc_table_etuds_lycees(format="html"):
    """Table avec _tous_ les étudiants des semestres non verrouillés
    de _tous_ les départements.
    """
    cur_dept = g.scodoc_dept
    semdepts = sco_formsemestre.scodoc_get_all_unlocked_sems()
    etuds = []
    try:
        for (sem, dept) in semdepts:
            app.set_sco_dept(dept.acronym)
            etuds += sco_report.tsp_etud_list(sem["formsemestre_id"])[0]
    finally:
        app.set_sco_dept(cur_dept)

    tab, etuds_by_lycee = _table_etuds_lycees(
        etuds,
        False,
        "Lycées de TOUS les étudiants",
        sco_preferences.SemPreferences(),
        no_links=True,
    )
    tab.base_url = request.base_url
    t = tab.make_page(format=format, with_html_headers=False)
    if format != "html":
        return t
    H = [
        html_sco_header.sco_header(
            page_title=tab.page_title,
            init_google_maps=True,
            init_qtip=True,
            javascripts=["js/etud_info.js", "js/map_lycees.js"],
        ),
        """<h2 class="formsemestre">Lycées d'origine des %d étudiants (%d semestres)</h2>"""
        % (len(etuds), len(semdepts)),
        t,
        """<div id="lyc_map_canvas"></div>          
          """,
        js_coords_lycees(etuds_by_lycee),
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def _table_etuds_lycees(etuds, group_lycees, title, preferences, no_links=False):
    etuds = [sco_etud.etud_add_lycee_infos(e) for e in etuds]
    etuds_by_lycee = scu.group_by_key(etuds, "codelycee")
    #
    if group_lycees:
        L = [etuds_by_lycee[codelycee][0] for codelycee in etuds_by_lycee]
        for l in L:
            l["nbetuds"] = len(etuds_by_lycee[l["codelycee"]])
        # L.sort( key=operator.itemgetter('codepostallycee', 'nomlycee') ) argh, only python 2.5+ !!!
        L.sort(key=itemgetter("codepostallycee", "nomlycee"))
        columns_ids = (
            "nbetuds",
            "codelycee",
            "codepostallycee",
            "villelycee",
            "nomlycee",
        )
        bottom_titles = {
            "nbetuds": len(etuds),
            "nomlycee": "%d lycées"
            % len([x for x in etuds_by_lycee if etuds_by_lycee[x][0]["codelycee"]]),
        }
    else:
        L = etuds
        columns_ids = (
            "civilite_str",
            "nom",
            "prenom",
            "codelycee",
            "codepostallycee",
            "villelycee",
            "nomlycee",
        )
        bottom_titles = None
        if not no_links:
            for etud in etuds:
                fiche_url = url_for(
                    "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
                )
                etud["_nom_target"] = fiche_url
                etud["_prenom_target"] = fiche_url
                etud["_nom_td_attrs"] = 'id="%s" class="etudinfo"' % (etud["etudid"])

    tab = GenTable(
        columns_ids=columns_ids,
        rows=L,
        titles={
            "nbetuds": "Nb d'étudiants",
            "civilite_str": "",
            "nom": "Nom",
            "prenom": "Prénom",
            "etudid": "etudid",
            "codelycee": "Code Lycée",
            "codepostallycee": "Code postal",
            "nomlycee": "Lycée",
            "villelycee": "Commune",
        },
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption=title,
        page_title="Carte lycées d'origine",
        html_sortable=True,
        html_class="table_leftalign table_listegroupe",
        bottom_titles=bottom_titles,
        preferences=preferences,
    )
    return tab, etuds_by_lycee


def formsemestre_etuds_lycees(
    formsemestre_id,
    format="html",
    only_primo=False,
    no_grouping=False,
):
    """Table des lycées d'origine"""
    tab, etuds_by_lycee = formsemestre_table_etuds_lycees(
        formsemestre_id, only_primo=only_primo, group_lycees=not no_grouping
    )
    tab.base_url = "%s?formsemestre_id=%s" % (request.base_url, formsemestre_id)
    if only_primo:
        tab.base_url += "&only_primo=1"
    if no_grouping:
        tab.base_url += "&no_grouping=1"
    t = tab.make_page(format=format, with_html_headers=False)
    if format != "html":
        return t
    F = [
        sco_report.tsp_form_primo_group(
            only_primo, no_grouping, formsemestre_id, format
        )
    ]
    H = [
        html_sco_header.sco_header(
            page_title=tab.page_title,
            init_google_maps=True,
            init_qtip=True,
            javascripts=["js/etud_info.js", "js/map_lycees.js"],
        ),
        """<h2 class="formsemestre">Lycées d'origine des étudiants</h2>""",
        "\n".join(F),
        t,
        """<div id="lyc_map_canvas"></div>          
          """,
        js_coords_lycees(etuds_by_lycee),
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def qjs(txt):  # quote for JS
    return txt.replace("'", r"\'").replace('"', r"\"")


def js_coords_lycees(etuds_by_lycee):
    """Formatte liste des lycees en JSON pour Google Map"""
    L = []
    for codelycee in etuds_by_lycee:
        if codelycee:
            lyc = etuds_by_lycee[codelycee][0]
            if not lyc.get("positionlycee", False):
                continue
            listeetuds = "<br/>%d étudiants: " % len(
                etuds_by_lycee[codelycee]
            ) + ", ".join(
                [
                    '<a class="discretelink" href="%s" title="">%s</a>'
                    % (
                        url_for(
                            "scolar.ficheEtud",
                            scodoc_dept=g.scodoc_dept,
                            etudid=e["etudid"],
                        ),
                        qjs(e["nomprenom"]),
                    )
                    for e in etuds_by_lycee[codelycee]
                ]
            )
            pos = qjs(lyc["positionlycee"])
            legend = "%s %s" % (qjs("%(nomlycee)s (%(villelycee)s)" % lyc), listeetuds)
            L.append(
                "{'position' : '%s', 'name' : '%s', 'number' : %d }"
                % (pos, legend, len(etuds_by_lycee[codelycee]))
            )

    return """<script type="text/javascript">
          var lycees_coords = [%s];
          </script>""" % ",".join(
        L
    )
