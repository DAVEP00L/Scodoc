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

"""Rapports suivi:
  - statistiques decisions
  - suivi cohortes
"""
import os
import tempfile
import re
import time
import datetime
from operator import itemgetter

from flask import url_for, g, request
import pydot

import app.scodoc.sco_utils as scu
from app.models import NotesFormModalite
from app.scodoc import notesdb as ndb
from app.scodoc import html_sco_header
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_etud
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_pdf
from app.scodoc import sco_preferences
import sco_version
from app.scodoc.gen_tables import GenTable
from app import log
from app.scodoc.sco_codes_parcours import code_semestre_validant
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_pdf import SU

MAX_ETUD_IN_DESCR = 20


def formsemestre_etuds_stats(sem, only_primo=False):
    """Récupère liste d'etudiants avec etat et decision."""
    nt = sco_cache.NotesTableCache.get(
        sem["formsemestre_id"]
    )  # > get_table_moyennes_triees, identdict, get_etud_decision_sem, get_etud_etat,
    T = nt.get_table_moyennes_triees()
    # Construit liste d'étudiants du semestre avec leur decision
    etuds = []
    for t in T:
        etudid = t[-1]
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        decision = nt.get_etud_decision_sem(etudid)
        if decision:
            etud["codedecision"] = decision["code"]
        etud["etat"] = nt.get_etud_etat(etudid)
        if etud["etat"] == "D":
            etud["codedecision"] = "DEM"
        if "codedecision" not in etud:
            etud["codedecision"] = "(nd)"  # pas de decision jury
        # Ajout devenir (autorisations inscriptions), utile pour stats passage
        aut_list = sco_parcours_dut.formsemestre_get_autorisation_inscription(
            etudid, sem["formsemestre_id"]
        )
        autorisations = ["S%s" % x["semestre_id"] for x in aut_list]
        autorisations.sort()
        autorisations_str = ", ".join(autorisations)
        etud["devenir"] = autorisations_str
        # Ajout clé 'bac-specialite'
        bs = []
        if etud["bac"]:
            bs.append(etud["bac"])
        if etud["specialite"]:
            bs.append(etud["specialite"])
        etud["bac-specialite"] = " ".join(bs)
        #
        if (not only_primo) or is_primo_etud(etud, sem):
            etuds.append(etud)
    return etuds


def is_primo_etud(etud, sem):
    """Determine si un (filled) etud a ete inscrit avant ce semestre.
    Regarde la liste des semestres dans lesquels l'étudiant est inscrit
    """
    now = sem["dateord"]
    for s in etud["sems"]:  # le + recent d'abord
        if s["dateord"] < now:
            return False
    return True


def _categories_and_results(etuds, category, result):
    categories = {}
    results = {}
    for etud in etuds:
        categories[etud[category]] = True
        results[etud[result]] = True
    categories = list(categories.keys())
    categories.sort()
    results = list(results.keys())
    results.sort()
    return categories, results


def _results_by_category(
    etuds,
    category="",
    result="",
    category_name=None,
    formsemestre_id=None,
):
    """Construit table: categories (eg types de bacs) en ligne, décisions jury en colonnes

    etuds est une liste d'etuds (dicts).
    category et result sont des clés de etud (category définie les lignes, result les colonnes).

    Retourne une table.
    """
    if category_name is None:
        category_name = category
    # types de bacs differents:
    categories, results = _categories_and_results(etuds, category, result)
    #
    Count = {}  # { bac : { decision : nb_avec_ce_bac_et_ce_code } }
    results = {}  # { result_value : True }
    for etud in etuds:
        results[etud[result]] = True
        if etud[category] in Count:
            Count[etud[category]][etud[result]] += 1
        else:
            Count[etud[category]] = scu.DictDefault(kv_dict={etud[result]: 1})
    # conversion en liste de dict
    C = [Count[cat] for cat in categories]
    # Totaux par lignes et colonnes
    tot = 0
    for l in [Count[cat] for cat in categories]:
        l["sum"] = sum(l.values())
        tot += l["sum"]
    # pourcentages sur chaque total de ligne
    for l in C:
        l["sumpercent"] = "%2.1f%%" % ((100.0 * l["sum"]) / tot)
    #
    codes = list(results.keys())
    codes.sort()

    bottom_titles = []
    if C:  # ligne du bas avec totaux:
        bottom_titles = {}
        for code in codes:
            bottom_titles[code] = sum([l[code] for l in C])
        bottom_titles["sum"] = tot
        bottom_titles["sumpercent"] = "100%"
        bottom_titles["row_title"] = "Total"

    # ajout titre ligne:
    for (cat, l) in zip(categories, C):
        l["row_title"] = cat or "?"

    #
    codes.append("sum")
    codes.append("sumpercent")

    # on veut { ADM : ADM, ... }, était peu elegant en python 2.3:
    # titles = {}
    # map( lambda x,titles=titles: titles.__setitem__(x[0],x[1]), zip(codes,codes) )
    # Version moderne:
    titles = {x: x for x in codes}
    titles["sum"] = "Total"
    titles["sumpercent"] = "%"
    titles["DEM"] = "Dém."  # démissions
    titles["row_title"] = category_name
    return GenTable(
        titles=titles,
        columns_ids=codes,
        rows=C,
        bottom_titles=bottom_titles,
        html_col_width="4em",
        html_sortable=True,
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )


# pages
def formsemestre_report(
    formsemestre_id,
    etuds,
    category="bac",
    result="codedecision",
    category_name="",
    result_name="",
    title="Statistiques",
    only_primo=None,
):
    """
    Tableau sur résultats (result) par type de category bac
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not category_name:
        category_name = category
    if not result_name:
        result_name = result
    if result_name == "codedecision":
        result_name = "résultats"
    #
    tab = _results_by_category(
        etuds,
        category=category,
        category_name=category_name,
        result=result,
        formsemestre_id=formsemestre_id,
    )
    #
    tab.filename = scu.make_filename("stats " + sem["titreannee"])

    tab.origin = (
        "Généré par %s le " % sco_version.SCONAME + scu.timedate_human_repr() + ""
    )
    tab.caption = "Répartition des résultats par %s, semestre %s" % (
        category_name,
        sem["titreannee"],
    )
    tab.html_caption = "Répartition des résultats par %s." % category_name
    tab.base_url = "%s?formsemestre_id=%s" % (request.base_url, formsemestre_id)
    if only_primo:
        tab.base_url += "&only_primo=on"
    return tab


# def formsemestre_report_bacs(formsemestre_id, format='html'):
#     """
#     Tableau sur résultats par type de bac
#     """
#     sem = sco_formsemestre.get_formsemestre( formsemestre_id)
#     title = 'Statistiques bacs ' + sem['titreannee']
#     etuds = formsemestre_etuds_stats(sem)
#     tab = formsemestre_report(formsemestre_id, etuds,
#                               category='bac', result='codedecision',
#                               category_name='Bac',
#                               title=title)
#     return tab.make_page(
#         title =  """<h2>Résultats de <a href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titreannee)s</a></h2>""" % sem,
#         format=format, page_title = title)


def formsemestre_report_counts(
    formsemestre_id,
    format="html",
    category="bac",
    result="codedecision",
    allkeys=False,
    only_primo=False,
):
    """
    Tableau comptage avec choix des categories
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    category_name = category.capitalize()
    title = "Comptages " + category_name
    etuds = formsemestre_etuds_stats(sem, only_primo=only_primo)
    tab = formsemestre_report(
        formsemestre_id,
        etuds,
        category=category,
        result=result,
        category_name=category_name,
        title=title,
        only_primo=only_primo,
    )
    if not etuds:
        F = ["""<p><em>Aucun étudiant</em></p>"""]
    else:
        if allkeys:
            keys = list(etuds[0].keys())
        else:
            # clés présentées à l'utilisateur:
            keys = [
                "annee_bac",
                "annee_naissance",
                "bac",
                "specialite",
                "bac-specialite",
                "codedecision",
                "devenir",
                "etat",
                "civilite",
                "qualite",
                "villelycee",
                "statut",
                "type_admission",
                "boursier_prec",
            ]
        keys.sort()
        F = [
            """<form name="f" method="get" action="%s"><p>
              Colonnes: <select name="result" onchange="document.f.submit()">"""
            % request.base_url
        ]
        for k in keys:
            if k == result:
                selected = "selected"
            else:
                selected = ""
            F.append('<option value="%s" %s>%s</option>' % (k, selected, k))
        F.append("</select>")
        F.append(' Lignes: <select name="category" onchange="document.f.submit()">')
        for k in keys:
            if k == category:
                selected = "selected"
            else:
                selected = ""
            F.append('<option value="%s" %s>%s</option>' % (k, selected, k))
        F.append("</select>")
        if only_primo:
            checked = 'checked="1"'
        else:
            checked = ""
        F.append(
            '<br/><input type="checkbox" name="only_primo" onchange="document.f.submit()" %s>Restreindre aux primo-entrants</input>'
            % checked
        )
        F.append(
            '<input type="hidden" name="formsemestre_id" value="%s"/>' % formsemestre_id
        )
        F.append("</p></form>")

    t = tab.make_page(
        title="""<h2 class="formsemestre">Comptes croisés</h2>""",
        format=format,
        with_html_headers=False,
    )
    if format != "html":
        return t
    H = [
        html_sco_header.sco_header(page_title=title),
        t,
        "\n".join(F),
        """<p class="help">Le tableau affiche le nombre d'étudiants de ce semestre dans chacun
          des cas choisis: à l'aide des deux menus, vous pouvez choisir les catégories utilisées
          pour les lignes et les colonnes. Le <tt>codedecision</tt> est le code de la décision 
          du jury.
          </p>""",
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


# --------------------------------------------------------------------------
def table_suivi_cohorte(
    formsemestre_id,
    percent=False,
    bac="",  # selection sur type de bac
    bacspecialite="",
    annee_bac="",
    civilite=None,
    statut="",
    only_primo=False,
):
    """
    Tableau indiquant le nombre d'etudiants de la cohorte dans chaque état:
    Etat     date_debut_Sn   date1  date2 ...
    S_n       #inscrits en Sn
    S_n+1
    ...
    S_last
    Diplome
    Sorties

    Determination des dates: on regroupe les semestres commençant à des dates proches

    """
    sem = sco_formsemestre.get_formsemestre(
        formsemestre_id
    )  # sem est le semestre origine
    t0 = time.time()

    def logt(op):
        if 0:  # debug, set to 0 in production
            log("%s: %s" % (op, time.time() - t0))

    logt("table_suivi_cohorte: start")
    # 1-- Liste des semestres posterieurs dans lesquels ont été les etudiants de sem
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etudids, get_etud_decision_sem
    etudids = nt.get_etudids()

    logt("A: orig etuds set")
    S = {formsemestre_id: sem}  # ensemble de formsemestre_id
    orig_set = set()  # ensemble d'etudid du semestre d'origine
    bacs = set()
    bacspecialites = set()
    annee_bacs = set()
    civilites = set()
    statuts = set()
    for etudid in etudids:
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        bacspe = etud["bac"] + " / " + etud["specialite"]
        # sélection sur bac:
        if (
            (not bac or (bac == etud["bac"]))
            and (not bacspecialite or (bacspecialite == bacspe))
            and (not annee_bac or (annee_bac == str(etud["annee_bac"])))
            and (not civilite or (civilite == etud["civilite"]))
            and (not statut or (statut == etud["statut"]))
            and (not only_primo or is_primo_etud(etud, sem))
        ):
            orig_set.add(etudid)
            # semestres suivants:
            for s in etud["sems"]:
                if ndb.DateDMYtoISO(s["date_debut"]) > ndb.DateDMYtoISO(
                    sem["date_debut"]
                ):
                    S[s["formsemestre_id"]] = s
        bacs.add(etud["bac"])
        bacspecialites.add(bacspe)
        annee_bacs.add(str(etud["annee_bac"]))
        civilites.add(etud["civilite"])
        if etud["statut"]:  # ne montre pas les statuts non renseignés
            statuts.add(etud["statut"])
    sems = list(S.values())
    # tri les semestres par date de debut
    for s in sems:
        d, m, y = [int(x) for x in s["date_debut"].split("/")]
        s["date_debut_dt"] = datetime.datetime(y, m, d)
    sems.sort(key=itemgetter("date_debut_dt"))

    # 2-- Pour chaque semestre, trouve l'ensemble des etudiants venant de sem
    logt("B: etuds sets")
    sem["members"] = orig_set
    for s in sems:
        ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            args={"formsemestre_id": s["formsemestre_id"]}
        )  # sans dems
        inset = set([i["etudid"] for i in ins])
        s["members"] = orig_set.intersection(inset)
        nb_dipl = 0  # combien de diplomes dans ce semestre ?
        if s["semestre_id"] == nt.parcours.NB_SEM:
            nt = sco_cache.NotesTableCache.get(
                s["formsemestre_id"]
            )  # > get_etud_decision_sem
            for etudid in s["members"]:
                dec = nt.get_etud_decision_sem(etudid)
                if dec and code_semestre_validant(dec["code"]):
                    nb_dipl += 1
        s["nb_dipl"] = nb_dipl

    # 3-- Regroupe les semestres par date de debut
    P = []  #  liste de periodsem

    class periodsem(object):
        pass

    # semestre de depart:
    porigin = periodsem()
    d, m, y = [int(x) for x in sem["date_debut"].split("/")]
    porigin.datedebut = datetime.datetime(y, m, d)
    porigin.sems = [sem]

    #
    tolerance = datetime.timedelta(days=45)
    for s in sems:
        merged = False
        for p in P:
            if abs(s["date_debut_dt"] - p.datedebut) < tolerance:
                p.sems.append(s)
                merged = True
                break
        if not merged:
            p = periodsem()
            p.datedebut = s["date_debut_dt"]
            p.sems = [s]
            P.append(p)

    # 4-- regroupe par indice de semestre S_i
    indices_sems = list(set([s["semestre_id"] for s in sems]))
    indices_sems.sort()
    for p in P:
        p.nb_etuds = 0  # nombre total d'etudiants dans la periode
        p.sems_by_id = scu.DictDefault(defaultvalue=[])
        for s in p.sems:
            p.sems_by_id[s["semestre_id"]].append(s)
            p.nb_etuds += len(s["members"])

    # 5-- Contruit table
    logt("C: build table")
    nb_initial = len(sem["members"])

    def fmtval(x):
        if not x:
            return ""  # ne montre pas les 0
        if percent:
            return "%2.1f%%" % (100.0 * x / nb_initial)
        else:
            return x

    L = [
        {
            "row_title": "Origine: S%s" % sem["semestre_id"],
            porigin.datedebut: nb_initial,
            "_css_row_class": "sorttop",
        }
    ]
    if nb_initial <= MAX_ETUD_IN_DESCR:
        etud_descr = _descr_etud_set(sem["members"])
        L[0]["_%s_help" % porigin.datedebut] = etud_descr
    for idx_sem in indices_sems:
        if idx_sem >= 0:
            d = {"row_title": "S%s" % idx_sem}
        else:
            d = {"row_title": "Autre semestre"}

        for p in P:
            etuds_period = set()
            for s in p.sems:
                if s["semestre_id"] == idx_sem:
                    etuds_period = etuds_period.union(s["members"])
            nbetuds = len(etuds_period)
            if nbetuds:
                d[p.datedebut] = fmtval(nbetuds)
                if nbetuds <= MAX_ETUD_IN_DESCR:  # si peu d'etudiants, indique la liste
                    etud_descr = _descr_etud_set(etuds_period)
                    d["_%s_help" % p.datedebut] = etud_descr
        L.append(d)
    # Compte nb de démissions et de ré-orientation par période
    logt("D: cout dems reos")
    sem["dems"], sem["reos"] = _count_dem_reo(formsemestre_id, sem["members"])
    for p in P:
        p.dems = set()
        p.reos = set()
        for s in p.sems:
            d, r = _count_dem_reo(s["formsemestre_id"], s["members"])
            p.dems.update(d)
            p.reos.update(r)
    # Nombre total d'etudiants par periode
    l = {
        "row_title": "Inscrits",
        "row_title_help": "Nombre d'étudiants inscrits",
        "_table_part": "foot",
        porigin.datedebut: fmtval(nb_initial),
    }
    for p in P:
        l[p.datedebut] = fmtval(p.nb_etuds)
    L.append(l)
    # Nombre de démissions par période
    l = {
        "row_title": "Démissions",
        "row_title_help": "Nombre de démissions pendant la période",
        "_table_part": "foot",
        porigin.datedebut: fmtval(len(sem["dems"])),
    }
    if len(sem["dems"]) <= MAX_ETUD_IN_DESCR:
        etud_descr = _descr_etud_set(sem["dems"])
        l["_%s_help" % porigin.datedebut] = etud_descr
    for p in P:
        l[p.datedebut] = fmtval(len(p.dems))
        if len(p.dems) <= MAX_ETUD_IN_DESCR:
            etud_descr = _descr_etud_set(p.dems)
            l["_%s_help" % p.datedebut] = etud_descr
    L.append(l)
    # Nombre de réorientations par période
    l = {
        "row_title": "Echecs",
        "row_title_help": "Ré-orientations (décisions NAR)",
        "_table_part": "foot",
        porigin.datedebut: fmtval(len(sem["reos"])),
    }
    if len(sem["reos"]) < 10:
        etud_descr = _descr_etud_set(sem["reos"])
        l["_%s_help" % porigin.datedebut] = etud_descr
    for p in P:
        l[p.datedebut] = fmtval(len(p.reos))
        if len(p.reos) <= MAX_ETUD_IN_DESCR:
            etud_descr = _descr_etud_set(p.reos)
            l["_%s_help" % p.datedebut] = etud_descr
    L.append(l)
    # derniere ligne: nombre et pourcentage de diplomes
    l = {
        "row_title": "Diplômes",
        "row_title_help": "Nombre de diplômés à la fin de la période",
        "_table_part": "foot",
    }
    for p in P:
        nb_dipl = 0
        for s in p.sems:
            nb_dipl += s["nb_dipl"]
        l[p.datedebut] = fmtval(nb_dipl)
    L.append(l)

    columns_ids = [p.datedebut for p in P]
    titles = dict([(p.datedebut, p.datedebut.strftime("%d/%m/%y")) for p in P])
    titles[porigin.datedebut] = porigin.datedebut.strftime("%d/%m/%y")
    if percent:
        pp = "(en % de la population initiale) "
        titles["row_title"] = "%"
    else:
        pp = ""
        titles["row_title"] = ""
    if only_primo:
        pp += "(restreint aux primo-entrants) "
    if bac:
        dbac = " (bacs %s)" % bac
    else:
        dbac = ""
    if bacspecialite:
        dbac += " (spécialité %s)" % bacspecialite
    if annee_bac:
        dbac += " (année bac %s)" % annee_bac
    if civilite:
        dbac += " civilité: %s" % civilite
    if statut:
        dbac += " statut: %s" % statut
    tab = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=L,
        html_col_width="4em",
        html_sortable=True,
        filename=scu.make_filename("cohorte " + sem["titreannee"]),
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption="Suivi cohorte " + pp + sem["titreannee"] + dbac,
        page_title="Suivi cohorte " + sem["titreannee"],
        html_class="table_cohorte",
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )
    # Explication: liste des semestres associés à chaque date
    if not P:
        expl = [
            '<p class="help">(aucun étudiant trouvé dans un semestre ultérieur)</p>'
        ]
    else:
        expl = ["<h3>Semestres associés à chaque date:</h3><ul>"]
        for p in P:
            expl.append("<li><b>%s</b>:" % p.datedebut.strftime("%d/%m/%y"))
            ls = []
            for s in p.sems:
                ls.append(
                    '<a href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titreannee)s</a>'
                    % s
                )
            expl.append(", ".join(ls) + "</li>")
        expl.append("</ul>")
    logt("Z: table_suivi_cohorte done")
    return (
        tab,
        "\n".join(expl),
        bacs,
        bacspecialites,
        annee_bacs,
        civilites,
        statuts,
    )


def formsemestre_suivi_cohorte(
    formsemestre_id,
    format="html",
    percent=1,
    bac="",
    bacspecialite="",
    annee_bac="",
    civilite=None,
    statut="",
    only_primo=False,
):
    """Affiche suivi cohortes par numero de semestre"""
    annee_bac = str(annee_bac)
    percent = int(percent)
    (
        tab,
        expl,
        bacs,
        bacspecialites,
        annee_bacs,
        civilites,
        statuts,
    ) = table_suivi_cohorte(
        formsemestre_id,
        percent=percent,
        bac=bac,
        bacspecialite=bacspecialite,
        annee_bac=annee_bac,
        civilite=civilite,
        statut=statut,
        only_primo=only_primo,
    )
    tab.base_url = (
        "%s?formsemestre_id=%s&percent=%s&bac=%s&bacspecialite=%s&civilite=%s"
        % (request.base_url, formsemestre_id, percent, bac, bacspecialite, civilite)
    )
    if only_primo:
        tab.base_url += "&only_primo=on"
    t = tab.make_page(format=format, with_html_headers=False)
    if format != "html":
        return t

    base_url = request.base_url
    burl = "%s?formsemestre_id=%s&bac=%s&bacspecialite=%s&civilite=%s&statut=%s" % (
        base_url,
        formsemestre_id,
        bac,
        bacspecialite,
        civilite,
        statut,
    )
    if percent:
        pplink = '<p><a href="%s&percent=0">Afficher les résultats bruts</a></p>' % burl
    else:
        pplink = (
            '<p><a href="%s&percent=1">Afficher les résultats en pourcentages</a></p>'
            % burl
        )
    help = (
        pplink
        + """    
    <p class="help">Nombre d'étudiants dans chaque semestre. Les dates indiquées sont les dates approximatives de <b>début</b> des semestres (les semestres commençant à des dates proches sont groupés). Le nombre de diplômés est celui à la <b>fin</b> du semestre correspondant. Lorsqu'il y a moins de %s étudiants dans une case, vous pouvez afficher leurs noms en passant le curseur sur le chiffre.</p>
<p class="help">Les menus permettent de n'étudier que certaines catégories d'étudiants (titulaires d'un type de bac, garçons ou filles). La case "restreindre aux primo-entrants" permet de ne considérer que les étudiants qui n'ont jamais été inscrits dans ScoDoc avant le semestre considéré.</p>
    """
        % (MAX_ETUD_IN_DESCR,)
    )

    H = [
        html_sco_header.sco_header(page_title=tab.page_title),
        """<h2 class="formsemestre">Suivi cohorte: devenir des étudiants de ce semestre</h2>""",
        _gen_form_selectetuds(
            formsemestre_id,
            only_primo=only_primo,
            bac=bac,
            bacspecialite=bacspecialite,
            annee_bac=annee_bac,
            civilite=civilite,
            statut=statut,
            bacs=bacs,
            bacspecialites=bacspecialites,
            annee_bacs=annee_bacs,
            civilites=civilites,
            statuts=statuts,
            percent=percent,
        ),
        t,
        help,
        expl,
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def _gen_form_selectetuds(
    formsemestre_id,
    percent=None,
    only_primo=None,
    bac=None,
    bacspecialite=None,
    annee_bac=None,
    civilite=None,
    statut=None,
    bacs=None,
    bacspecialites=None,
    annee_bacs=None,
    civilites=None,
    statuts=None,
):
    """HTML form pour choix criteres selection etudiants"""
    bacs = list(bacs)
    bacs.sort()
    bacspecialites = list(bacspecialites)
    bacspecialites.sort()
    # on peut avoir un mix de chaines vides et d'entiers:
    annee_bacs = [int(x) if x else 0 for x in annee_bacs]
    annee_bacs.sort()
    civilites = list(civilites)
    civilites.sort()
    statuts = list(statuts)
    statuts.sort()
    #
    if bac:
        selected = ""
    else:
        selected = 'selected="selected"'
    F = [
        """<form id="f" method="get" action="%s">
    <p>Bac: <select name="bac" onchange="javascript: submit(this);">
    <option value="" %s>tous</option>
    """
        % (request.base_url, selected)
    ]
    for b in bacs:
        if bac == b:
            selected = 'selected="selected"'
        else:
            selected = ""
        F.append('<option value="%s" %s>%s</option>' % (b, selected, b))
    F.append("</select>")
    if bacspecialite:
        selected = ""
    else:
        selected = 'selected="selected"'
    F.append(
        """&nbsp; Bac/Specialité: <select name="bacspecialite" onchange="javascript: submit(this);">
    <option value="" %s>tous</option>
    """
        % selected
    )
    for b in bacspecialites:
        if bacspecialite == b:
            selected = 'selected="selected"'
        else:
            selected = ""
        F.append('<option value="%s" %s>%s</option>' % (b, selected, b))
    F.append("</select>")
    #
    if annee_bac:
        selected = ""
    else:
        selected = 'selected="selected"'
    F.append(
        """&nbsp; Année bac: <select name="annee_bac" onchange="javascript: submit(this);">
    <option value="" %s>tous</option>
    """
        % selected
    )
    for b in annee_bacs:
        if str(annee_bac) == str(b):
            selected = 'selected="selected"'
        else:
            selected = ""
        F.append('<option value="%s" %s>%s</option>' % (b, selected, b))
    F.append("</select>")
    #
    F.append(
        """&nbsp; Genre: <select name="civilite" onchange="javascript: submit(this);">
    <option value="" %s>tous</option>
    """
        % selected
    )
    for b in civilites:
        if civilite == b:
            selected = 'selected="selected"'
        else:
            selected = ""
        F.append('<option value="%s" %s>%s</option>' % (b, selected, b))
    F.append("</select>")

    F.append(
        """&nbsp; Statut: <select name="statut" onchange="javascript: submit(this);">
    <option value="" %s>tous</option>
    """
        % selected
    )
    for b in statuts:
        if statut == b:
            selected = 'selected="selected"'
        else:
            selected = ""
        F.append('<option value="%s" %s>%s</option>' % (b, selected, b))
    F.append("</select>")

    if only_primo:
        checked = 'checked="1"'
    else:
        checked = ""
    F.append(
        '<br/><input type="checkbox" name="only_primo" onchange="javascript: submit(this);" %s/>Restreindre aux primo-entrants'
        % checked
    )
    F.append(
        '<input type="hidden" name="formsemestre_id" value="%s"/>' % formsemestre_id
    )
    F.append('<input type="hidden" name="percent" value="%s"/>' % percent)
    F.append("</p></form>")
    return "\n".join(F)


def _descr_etud_set(etudids):
    "textual html description of a set of etudids"
    etuds = []
    for etudid in etudids:
        etuds.append(sco_etud.get_etud_info(etudid=etudid, filled=True)[0])
    # sort by name
    etuds.sort(key=itemgetter("nom"))
    return ", ".join([e["nomprenom"] for e in etuds])


def _count_dem_reo(formsemestre_id, etudids):
    "count nb of demissions and reorientation in this etud set"
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etud_etat, get_etud_decision_sem
    dems = set()
    reos = set()
    for etudid in etudids:
        if nt.get_etud_etat(etudid) == "D":
            dems.add(etudid)
        dec = nt.get_etud_decision_sem(etudid)
        if dec and dec["code"] in sco_codes_parcours.CODES_SEM_REO:
            reos.add(etudid)
    return dems, reos


"""OLDGEA:
27s pour  S1 F.I. classique Semestre 1 2006-2007
B 2.3s
C 5.6s
D 5.9s
Z 27s  => cache des semestres pour nt

à chaud: 3s
B: etuds sets: 2.4s => lent: N x getEtudInfo (non caché)
"""

EXP_LIC = re.compile(r"licence", re.I)
EXP_LPRO = re.compile(r"professionnelle", re.I)


def _codesem(sem, short=True, prefix=""):
    "code semestre: S1 ou S1d"
    idx = sem["semestre_id"]
    # semestre décalé ?
    # les semestres pairs normaux commencent entre janvier et mars
    # les impairs normaux entre aout et decembre
    d = ""
    if idx and idx > 0 and sem["date_debut"]:
        mois_debut = int(sem["date_debut"].split("/")[1])
        if (idx % 2 and mois_debut < 3) or (idx % 2 == 0 and mois_debut >= 8):
            d = "d"
    if idx == -1:
        if short:
            idx = "Autre "
        else:
            idx = sem["titre"] + " "
            idx = EXP_LPRO.sub("pro.", idx)
            idx = EXP_LIC.sub("Lic.", idx)
            prefix = ""  # indique titre au lieu de Sn
    return "%s%s%s" % (prefix, idx, d)


def get_codeparcoursetud(etud, prefix="", separator=""):
    """calcule un code de parcours pour un etudiant
    exemples:
       1234A pour un etudiant ayant effectué S1, S2, S3, S4 puis diplome
       12D   pour un étudiant en S1, S2 puis démission en S2
       12R   pour un etudiant en S1, S2 réorienté en fin de S2
    Construit aussi un dict: { semestre_id : decision_jury | None }
    """
    p = []
    decisions_jury = {}
    # élimine les semestres spéciaux sans parcours (LP...)
    sems = [s for s in etud["sems"] if s["semestre_id"] >= 0]
    i = len(sems) - 1
    while i >= 0:
        s = sems[i]  # 'sems' est a l'envers, du plus recent au plus ancien
        nt = sco_cache.NotesTableCache.get(
            s["formsemestre_id"]
        )  # > get_etud_etat, get_etud_decision_sem
        p.append(_codesem(s, prefix=prefix))
        # code decisions jury de chaque semestre:
        if nt.get_etud_etat(etud["etudid"]) == "D":
            decisions_jury[s["semestre_id"]] = "DEM"
        else:
            dec = nt.get_etud_decision_sem(etud["etudid"])
            if not dec:
                decisions_jury[s["semestre_id"]] = ""
            else:
                decisions_jury[s["semestre_id"]] = dec["code"]
        # code etat dans le codeparcours sur dernier semestre seulement
        if i == 0:
            # Démission
            if nt.get_etud_etat(etud["etudid"]) == "D":
                p.append(":D")
            else:
                dec = nt.get_etud_decision_sem(etud["etudid"])
                if dec and dec["code"] in sco_codes_parcours.CODES_SEM_REO:
                    p.append(":R")
                if (
                    dec
                    and s["semestre_id"] == nt.parcours.NB_SEM
                    and code_semestre_validant(dec["code"])
                ):
                    p.append(":A")
        i -= 1
    return separator.join(p), decisions_jury


def tsp_etud_list(
    formsemestre_id,
    only_primo=False,
    bac="",  # selection sur type de bac
    bacspecialite="",
    annee_bac="",
    civilite="",
    statut="",
):
    """Liste des etuds a considerer dans table suivi parcours
    ramene aussi ensembles des bacs, genres, statuts de (tous) les etudiants
    """
    # log('tsp_etud_list(%s, bac="%s")' % (formsemestre_id,bac))
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etudids,
    etudids = nt.get_etudids()
    etuds = []
    bacs = set()
    bacspecialites = set()
    annee_bacs = set()
    civilites = set()
    statuts = set()
    for etudid in etudids:
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        bacspe = etud["bac"] + " / " + etud["specialite"]
        # sélection sur bac, primo, ...:
        if (
            (not bac or (bac == etud["bac"]))
            and (not bacspecialite or (bacspecialite == bacspe))
            and (not annee_bac or (annee_bac == str(etud["annee_bac"])))
            and (not civilite or (civilite == etud["civilite"]))
            and (not statut or (statut == etud["statut"]))
            and (not only_primo or is_primo_etud(etud, sem))
        ):
            etuds.append(etud)

        bacs.add(etud["bac"])
        bacspecialites.add(bacspe)
        annee_bacs.add(etud["annee_bac"])
        civilites.add(etud["civilite"])
        if etud["statut"]:  # ne montre pas les statuts non renseignés
            statuts.add(etud["statut"])
    # log('tsp_etud_list: %s etuds' % len(etuds))
    return etuds, bacs, bacspecialites, annee_bacs, civilites, statuts


def tsp_grouped_list(codes_etuds):
    """Liste pour table regroupant le nombre d'étudiants (+ bulle avec les noms) de chaque parcours"""
    L = []
    parcours = list(codes_etuds.keys())
    parcours.sort()
    for p in parcours:
        nb = len(codes_etuds[p])
        l = {"parcours": p, "nb": nb}
        if nb <= MAX_ETUD_IN_DESCR:
            l["_nb_help"] = _descr_etud_set([e["etudid"] for e in codes_etuds[p]])
        L.append(l)
    # tri par effectifs décroissants
    L.sort(key=itemgetter("nb"))
    return L


def table_suivi_parcours(formsemestre_id, only_primo=False, grouped_parcours=True):
    """Tableau recapitulant tous les parcours"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etuds, bacs, bacspecialites, annee_bacs, civilites, statuts = tsp_etud_list(
        formsemestre_id, only_primo=only_primo
    )
    codes_etuds = scu.DictDefault(defaultvalue=[])
    for etud in etuds:
        etud["codeparcours"], etud["decisions_jury"] = get_codeparcoursetud(etud)
        codes_etuds[etud["codeparcours"]].append(etud)
        fiche_url = url_for(
            "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
        )
        etud["_nom_target"] = fiche_url
        etud["_prenom_target"] = fiche_url
        etud["_nom_td_attrs"] = 'id="%s" class="etudinfo"' % (etud["etudid"])

    titles = {
        "parcours": "Code parcours",
        "nb": "Nombre d'étudiants",
        "civilite": "",
        "nom": "Nom",
        "prenom": "Prénom",
        "etudid": "etudid",
        "codeparcours": "Code parcours",
        "bac": "Bac",
        "specialite": "Spe.",
    }

    if grouped_parcours:
        L = tsp_grouped_list(codes_etuds)
        columns_ids = ("parcours", "nb")
    else:
        # Table avec le parcours de chaque étudiant:
        L = etuds
        columns_ids = (
            "etudid",
            "civilite",
            "nom",
            "prenom",
            "bac",
            "specialite",
            "codeparcours",
        )
        # Calcule intitulés de colonnes
        S = set()
        sems_ids = list(S.union(*[list(e["decisions_jury"].keys()) for e in etuds]))
        sems_ids.sort()
        sem_tits = ["S%s" % s for s in sems_ids]
        titles.update([(s, s) for s in sem_tits])
        columns_ids += tuple(sem_tits)
        for etud in etuds:
            for s in etud["decisions_jury"]:
                etud["S%s" % s] = etud["decisions_jury"][s]

    if only_primo:
        primostr = "primo-entrants du"
    else:
        primostr = "passés dans le"
    tab = GenTable(
        columns_ids=columns_ids,
        rows=L,
        titles=titles,
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption="Parcours suivis, étudiants %s semestre " % primostr
        + sem["titreannee"],
        page_title="Parcours " + sem["titreannee"],
        html_sortable=True,
        html_class="table_leftalign table_listegroupe",
        html_next_section="""<table class="help">
                    <tr><td><tt>1, 2, ...</tt></td><td> numéros de semestres</td></tr>
                    <tr><td><tt>1d, 2d, ...</tt></td><td>semestres "décalés"</td></tr>
                    <tr><td><tt>:A</tt></td><td> étudiants diplômés</td></tr>
                    <tr><td><tt>:R</tt></td><td> étudiants réorientés</td></tr>
                    <tr><td><tt>:D</tt></td><td> étudiants démissionnaires</td></tr>
                    </table>""",
        bottom_titles={
            "parcours": "Total",
            "nb": len(etuds),
            "codeparcours": len(etuds),
        },
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )
    return tab


def tsp_form_primo_group(only_primo, no_grouping, formsemestre_id, format):
    """Element de formulaire pour choisir si restriction aux primos entrants et groupement par lycees"""
    F = ["""<form name="f" method="get" action="%s">""" % request.base_url]
    if only_primo:
        checked = 'checked="1"'
    else:
        checked = ""
    F.append(
        '<input type="checkbox" name="only_primo" onchange="document.f.submit()" %s>Restreindre aux primo-entrants</input>'
        % checked
    )
    if no_grouping:
        checked = 'checked="1"'
    else:
        checked = ""
    F.append(
        '<input type="checkbox" name="no_grouping" onchange="document.f.submit()" %s>Lister chaque étudiant</input>'
        % checked
    )
    F.append(
        '<input type="hidden" name="formsemestre_id" value="%s"/>' % formsemestre_id
    )
    F.append('<input type="hidden" name="format" value="%s"/>' % format)
    F.append("""</form>""")
    return "\n".join(F)


def formsemestre_suivi_parcours(
    formsemestre_id,
    format="html",
    only_primo=False,
    no_grouping=False,
):
    """Effectifs dans les differents parcours possibles."""
    tab = table_suivi_parcours(
        formsemestre_id,
        only_primo=only_primo,
        grouped_parcours=not no_grouping,
    )
    tab.base_url = "%s?formsemestre_id=%s" % (request.base_url, formsemestre_id)
    if only_primo:
        tab.base_url += "&only_primo=1"
    if no_grouping:
        tab.base_url += "&no_grouping=1"
    t = tab.make_page(format=format, with_html_headers=False)
    if format != "html":
        return t
    F = [tsp_form_primo_group(only_primo, no_grouping, formsemestre_id, format)]

    H = [
        html_sco_header.sco_header(
            page_title=tab.page_title,
            init_qtip=True,
            javascripts=["js/etud_info.js"],
        ),
        """<h2 class="formsemestre">Parcours suivis par les étudiants de ce semestre</h2>""",
        "\n".join(F),
        t,
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


# -------------
def graph_parcours(
    formsemestre_id,
    format="svg",
    only_primo=False,
    bac="",  # selection sur type de bac
    bacspecialite="",
    annee_bac="",
    civilite="",
    statut="",
):
    """"""
    etuds, bacs, bacspecialites, annee_bacs, civilites, statuts = tsp_etud_list(
        formsemestre_id,
        only_primo=only_primo,
        bac=bac,
        bacspecialite=bacspecialite,
        annee_bac=annee_bac,
        civilite=civilite,
        statut=statut,
    )
    # log('graph_parcours: %s etuds (only_primo=%s)' % (len(etuds), only_primo))
    if not etuds:
        return "", etuds, bacs, bacspecialites, annee_bacs, civilites, statuts
    edges = scu.DictDefault(
        defaultvalue=set()
    )  # {("SEM"formsemestre_id_origin, "SEM"formsemestre_id_dest) : etud_set}

    def sem_node_name(sem, prefix="SEM"):
        "pydot node name for this integer id"
        return prefix + str(sem["formsemestre_id"])

    sems = {}
    effectifs = scu.DictDefault(defaultvalue=set())  # formsemestre_id : etud_set
    decisions = scu.DictDefault(defaultvalue={})  # formsemestre_id : { code : nb_etud }
    isolated_nodes = []  # [ node_name_de_formsemestre_id, ... ]
    connected_nodes = set()  # { node_name_de_formsemestre_id }
    diploma_nodes = []
    dem_nodes = {}  # formsemestre_id : noeud (node name) pour demissionnaires
    nar_nodes = {}  # formsemestre_id : noeud pour NAR
    for etud in etuds:
        nxt = {}
        etudid = etud["etudid"]
        for s in etud["sems"]:  # du plus recent au plus ancien
            nt = sco_cache.NotesTableCache.get(
                s["formsemestre_id"]
            )  # > get_etud_decision_sem, get_etud_etat
            dec = nt.get_etud_decision_sem(etudid)
            if nxt:
                if (
                    s["semestre_id"] == nt.parcours.NB_SEM
                    and dec
                    and code_semestre_validant(dec["code"])
                    and nt.get_etud_etat(etudid) == "I"
                ):
                    # cas particulier du diplome puis poursuite etude
                    edges[
                        (
                            sem_node_name(s, "_dipl_"),
                            sem_node_name(nxt),  # = "SEM{formsemestre_id}"
                        )
                    ].add(etudid)
                else:
                    edges[(sem_node_name(s), sem_node_name(nxt))].add(etudid)
                connected_nodes.add(sem_node_name(s))
                connected_nodes.add(sem_node_name(nxt))
            else:
                isolated_nodes.append(sem_node_name(s))
            sems[s["formsemestre_id"]] = s
            effectifs[s["formsemestre_id"]].add(etudid)
            nxt = s
            # Compte decisions jury de chaque semestres:
            dc = decisions[s["formsemestre_id"]]
            if dec:
                if dec["code"] in dc:
                    dc[dec["code"]] += 1
                else:
                    dc[dec["code"]] = 1
            # ajout noeud pour demissionnaires
            if nt.get_etud_etat(etudid) == "D":
                nid = sem_node_name(s, "_dem_")
                dem_nodes[s["formsemestre_id"]] = nid
                edges[(sem_node_name(s), nid)].add(etudid)
            # ajout noeud pour NAR (seulement pour noeud de depart)
            if (
                s["formsemestre_id"] == formsemestre_id
                and dec
                and dec["code"] == sco_codes_parcours.NAR
            ):
                nid = sem_node_name(s, "_nar_")
                nar_nodes[s["formsemestre_id"]] = nid
                edges[(sem_node_name(s), nid)].add(etudid)

            # si "terminal", ajoute noeud pour diplomes
            if s["semestre_id"] == nt.parcours.NB_SEM:
                if (
                    dec
                    and code_semestre_validant(dec["code"])
                    and nt.get_etud_etat(etudid) == "I"
                ):
                    nid = sem_node_name(s, "_dipl_")
                    edges[(sem_node_name(s), nid)].add(etudid)
                    diploma_nodes.append(nid)
    #
    g = scu.graph_from_edges(list(edges.keys()))
    for fid in isolated_nodes:
        if not fid in connected_nodes:
            n = pydot.Node(name=fid)
            g.add_node(n)
    g.set("rankdir", "LR")  # left to right
    g.set_fontname("Helvetica")
    if format == "svg":
        g.set_bgcolor("#fffff0")  # ou 'transparent'
    # titres des semestres:
    for s in sems.values():
        n = g.get_node(sem_node_name(s))[0]
        log("s['formsemestre_id'] = %s" % s["formsemestre_id"])
        log("n=%s" % n)
        log("get=%s" % g.get_node(sem_node_name(s)))
        log("nodes names = %s" % [x.get_name() for x in g.get_node_list()])
        if s["modalite"] and s["modalite"] != NotesFormModalite.DEFAULT_MODALITE:
            modalite = " " + s["modalite"]
        else:
            modalite = ""
        label = "%s%s\\n%d/%s - %d/%s\\n%d" % (
            _codesem(s, short=False, prefix="S"),
            modalite,
            s["mois_debut_ord"],
            s["annee_debut"][2:],
            s["mois_fin_ord"],
            s["annee_fin"][2:],
            len(effectifs[s["formsemestre_id"]]),
        )
        n.set("label", scu.suppress_accents(label))
        n.set_fontname("Helvetica")
        n.set_fontsize(8.0)
        n.set_width(1.2)
        n.set_shape("box")
        n.set_URL(f"formsemestre_status?formsemestre_id={s['formsemestre_id']}")
    # semestre de depart en vert
    n = g.get_node("SEM" + str(formsemestre_id))[0]
    n.set_color("green")
    # demissions en rouge, octagonal
    for nid in dem_nodes.values():
        n = g.get_node(nid)[0]
        n.set_color("red")
        n.set_shape("octagon")
        n.set("label", "Dem.")

    # NAR en rouge, Mcircle
    for nid in nar_nodes.values():
        n = g.get_node(nid)[0]
        n.set_color("red")
        n.set_shape("Mcircle")
        n.set("label", sco_codes_parcours.NAR)
    # diplomes:
    for nid in diploma_nodes:
        n = g.get_node(nid)[0]
        n.set_color("red")
        n.set_shape("ellipse")
        n.set("label", "Diplome")  # bug si accent (pas compris pourquoi)
    # Arètes:
    bubbles = {}  # substitue titres pour bulle aides: src_id:dst_id : etud_descr
    for (src_id, dst_id) in edges.keys():
        e = g.get_edge(src_id, dst_id)[0]
        e.set("arrowhead", "normal")
        e.set("arrowsize", 1)
        e.set_label(len(edges[(src_id, dst_id)]))
        e.set_fontname("Helvetica")
        e.set_fontsize(8.0)
        # bulle avec liste etudiants
        if len(edges[(src_id, dst_id)]) <= MAX_ETUD_IN_DESCR:
            etud_descr = _descr_etud_set(edges[(src_id, dst_id)])
            bubbles[src_id + ":" + dst_id] = etud_descr
            e.set_URL(f"__xxxetudlist__?{src_id}:{dst_id}")
    # Genere graphe
    _, path = tempfile.mkstemp(".gr")
    g.write(path=path, format=format)
    with open(path, "rb") as f:
        data = f.read()
    log("dot generated %d bytes in %s format" % (len(data), format))
    if not data:
        log("graph.to_string=%s" % g.to_string())
        raise ValueError(
            "Erreur lors de la génération du document au format %s" % format
        )
    os.unlink(path)
    if format == "svg":
        # dot génère un document XML complet, il faut enlever l'en-tête
        data_str = data.decode("utf-8")
        data = "<svg" + "<svg".join(data_str.split("<svg")[1:])
        # Substitution des titres des URL des aretes pour bulles aide
        def repl(m):
            return '<a title="%s"' % bubbles[m.group("sd")]

        exp = re.compile(
            r'<a.*?href="__xxxetudlist__\?(?P<sd>\w*:\w*).*?".*?xlink:title=".*?"', re.M
        )
        data = exp.sub(repl, data)
        # Substitution des titres des boites (semestres)
        exp1 = re.compile(
            r'<a xlink:href="formsemestre_status\?formsemestre_id=(?P<fid>\w*).*?".*?xlink:title="(?P<title>.*?)"',
            re.M | re.DOTALL,
        )

        def repl_title(m):
            fid = int(m.group("fid"))
            title = sems[fid]["titreannee"]
            if decisions[fid]:
                title += (
                    (" (" + str(decisions[fid]) + ")").replace("{", "").replace("'", "")
                )
            return (
                '<a xlink:href="formsemestre_status?formsemestre_id=%s" xlink:title="%s"'
                % (fid, scu.suppress_accents(title))
            )  # evite accents car svg utf-8 vs page en latin1...

        data = exp1.sub(repl_title, data)
        # Substitution de Arial par Helvetica (new prblem in Debian 5) ???
        # bug turnaround: il doit bien y avoir un endroit ou regler cela ?
        # cf http://groups.google.com/group/pydot/browse_thread/thread/b3704c53e331e2ec
        data = data.replace("font-family:Arial", "font-family:Helvetica")

    return data, etuds, bacs, bacspecialites, annee_bacs, civilites, statuts


def formsemestre_graph_parcours(
    formsemestre_id,
    format="html",
    only_primo=False,
    bac="",  # selection sur type de bac
    bacspecialite="",
    annee_bac="",
    civilite="",
    statut="",
    allkeys=False,  # unused
):
    """Graphe suivi cohortes"""
    annee_bac = str(annee_bac)
    # log("formsemestre_graph_parcours")
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if format == "pdf":
        (
            doc,
            etuds,
            bacs,
            bacspecialites,
            annee_bacs,
            civilites,
            statuts,
        ) = graph_parcours(
            formsemestre_id,
            format="pdf",
            only_primo=only_primo,
            bac=bac,
            bacspecialite=bacspecialite,
            annee_bac=annee_bac,
            civilite=civilite,
            statut=statut,
        )
        filename = scu.make_filename("flux " + sem["titreannee"])
        return scu.sendPDFFile(doc, filename + ".pdf")
    elif format == "png":
        #
        (
            doc,
            etuds,
            bacs,
            bacspecialites,
            annee_bacs,
            civilites,
            statuts,
        ) = graph_parcours(
            formsemestre_id,
            format="png",
            only_primo=only_primo,
            bac=bac,
            bacspecialite=bacspecialite,
            annee_bac=annee_bac,
            civilite=civilite,
            statut=statut,
        )
        return scu.send_file(
            doc,
            filename="flux " + sem["titreannee"],
            suffix=".png",
            attached=True,
            mime="image/png",
        )
    elif format == "html":
        url_kw = {
            "scodoc_dept": g.scodoc_dept,
            "formsemestre_id": formsemestre_id,
            "bac": bac,
            "specialite": bacspecialite,
            "civilite": civilite,
            "statut": statut,
        }
        if only_primo:
            url_kw["only_primo"] = "on"
        (
            doc,
            etuds,
            bacs,
            bacspecialites,
            annee_bacs,
            civilites,
            statuts,
        ) = graph_parcours(
            formsemestre_id,
            only_primo=only_primo,
            bac=bac,
            bacspecialite=bacspecialite,
            annee_bac=annee_bac,
            civilite=civilite,
            statut=statut,
        )

        H = [
            html_sco_header.sco_header(
                page_title="Parcours étudiants de %(titreannee)s" % sem,
                no_side_bar=True,
            ),
            """<h2 class="formsemestre">Parcours des étudiants de ce semestre</h2>""",
            doc,
            "<p>%d étudiants sélectionnés</p>" % len(etuds),
            _gen_form_selectetuds(
                formsemestre_id,
                only_primo=only_primo,
                bac=bac,
                bacspecialite=bacspecialite,
                annee_bac=annee_bac,
                civilite=civilite,
                statut=statut,
                bacs=bacs,
                bacspecialites=bacspecialites,
                annee_bacs=annee_bacs,
                civilites=civilites,
                statuts=statuts,
                percent=0,
            ),
            """<p>Origine et devenir des étudiants inscrits dans %(titreannee)s"""
            % sem,
            """(<a href="%s">version pdf</a>"""
            % url_for("notes.formsemestre_graph_parcours", format="pdf", **url_kw),
            """, <a href="%s">image PNG</a>)"""
            % url_for("notes.formsemestre_graph_parcours", format="png", **url_kw),
            """</p>""",
            """<p class="help">Le graphe permet de suivre les étudiants inscrits dans le semestre
              sélectionné (dessiné en vert). Chaque rectangle représente un semestre (cliquez dedans
              pour afficher son tableau de bord). Les flèches indiquent le nombre d'étudiants passant
              d'un semestre à l'autre (s'il y en a moins de %s, vous pouvez visualiser leurs noms en
              passant la souris sur le chiffre).
              </p>"""
            % MAX_ETUD_IN_DESCR,
            html_sco_header.sco_footer(),
        ]
        return "\n".join(H)
    else:
        raise ValueError("invalid format: %s" % format)
