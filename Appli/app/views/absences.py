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

"""
Module absences: issu de ScoDoc7 / ZAbsences.py

Emmanuel Viennet, 2021

Gestion des absences (v4)

Code dérivé de la partie la plus ancienne de ScoDoc, et à revoir.

L'API de plus bas niveau est en gros:

 AnnuleAbsencesDatesNoJust( dates)
 count_abs(etudid, debut, fin, matin=None, moduleimpl_id=None)
 count_abs_just(etudid, debut, fin, matin=None, moduleimpl_id=None)
 list_abs_just(etudid, datedebut)  [pas de fin ?]
 list_abs_non_just(etudid, datedebut)  [pas de fin ?]
 list_abs_justifs(etudid, datedebut, datefin=None, only_no_abs=True)

 list_abs_jour(date, am=True, pm=True, is_abs=None, is_just=None)
 list_abs_non_just_jour(date, am=True, pm=True)

"""

import calendar
import datetime
import dateutil
import dateutil.parser
import re
import time
import urllib
from xml.etree import ElementTree

import flask
from flask import g, request
from flask import url_for
from flask_login import current_user

from app.decorators import (
    scodoc,
    scodoc7func,
    permission_required,
    admin_required,
    login_required,
    permission_required_compat_scodoc7,
)

from app.views import absences_bp as bp

# ---------------
from app.models.absences import BilletAbsence
from app.scodoc import sco_utils as scu
from app.scodoc import notesdb as ndb
from app import log
from app.scodoc.scolog import logdb
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import ScoValueError, APIInvalidParams
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc.gen_tables import GenTable
from app.scodoc import html_sco_header
from app.scodoc import sco_abs
from app.scodoc import sco_abs_notification
from app.scodoc import sco_abs_views
from app.scodoc import sco_cache
from app.scodoc import sco_compute_moy
from app.scodoc import sco_etud
from app.scodoc import sco_excel
from app.scodoc import sco_find_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_preferences
from app.scodoc import sco_xml


CSSSTYLES = html_sco_header.BOOTSTRAP_MULTISELECT_CSS


def sco_publish(route, function, permission, methods=["GET"]):
    """Declare a route for a python function,
    protected by permission and called following ScoDoc 7 Zope standards.
    """
    return bp.route(route, methods=methods)(
        scodoc(permission_required(permission)(scodoc7func(function)))
    )


# --------------------------------------------------------------------
#
#   ABSENCES (/ScoDoc/<dept>/Scolarite/Absences/...)
#
# --------------------------------------------------------------------


@bp.route("/")
@bp.route("/index_html")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def index_html():
    """Gestionnaire absences, page principale"""
    # crude portage from 1999 DTML
    sems = sco_formsemestre.do_formsemestre_list()
    authuser = current_user

    H = [
        html_sco_header.sco_header(
            page_title="Gestion des absences",
            cssstyles=["css/calabs.css"],
            javascripts=["js/calabs.js"],
        ),
        """<h2>Gestion des Absences</h2>""",
    ]
    if not sems:
        H.append(
            """<p class="warning">Aucun semestre défini (ou aucun groupe d'étudiant)</p>"""
        )
    else:
        H.append(
            """<ul><li><a href="EtatAbsences">Afficher l'état des absences (pour tout un groupe)</a></li>"""
        )
        if sco_preferences.get_preference("handle_billets_abs"):
            H.append(
                """<li><a href="listeBillets">Traitement des billets d'absence en attente</a></li>"""
            )
        H.append(
            """<p>Pour signaler, annuler ou justifier une absence, choisissez d'abord l'étudiant concerné:</p>"""
        )
        H.append(sco_find_etud.form_search_etud())
        if authuser.has_permission(Permission.ScoAbsChange):
            H.extend(
                (
                    """<hr/>
<form action="SignaleAbsenceGrHebdo" id="formw">
<input type="hidden" name="destination" value="%s"/>
<p>
<span  style="font-weight: bold; font-size:120%%;">
 Saisie par semaine </span> - Choix du groupe:
 <input name="datelundi" type="hidden" value="x"/>
            """
                    % request.base_url,
                    sco_abs_views.formChoixSemestreGroupe(),
                    "</p>",
                    cal_select_week(),
                    """<p class="help">Sélectionner le groupe d'étudiants, puis cliquez sur une semaine pour
saisir les absences de toute cette semaine.</p>
                      </form>""",
                )
            )
        else:
            H.append(
                """<p class="scoinfo">Vous n'avez pas l'autorisation d'ajouter, justifier ou supprimer des absences.</p>"""
            )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def cal_select_week(year=None):
    "display calendar allowing week selection"
    if not year:
        year = scu.AnneeScolaire()
    sems = sco_formsemestre.do_formsemestre_list()
    if not sems:
        js = ""
    else:
        js = 'onmouseover="highlightweek(this);" onmouseout="deselectweeks();" onclick="wclick(this);"'
    C = sco_abs.YearTable(int(year), dayattributes=js)
    return C


sco_publish("/EtatAbsences", sco_abs_views.EtatAbsences, Permission.ScoView)
sco_publish("/CalAbs", sco_abs_views.CalAbs, Permission.ScoView)
sco_publish(
    "/SignaleAbsenceEtud",
    sco_abs_views.SignaleAbsenceEtud,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/doSignaleAbsence",
    sco_abs_views.doSignaleAbsence,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/JustifAbsenceEtud",
    sco_abs_views.JustifAbsenceEtud,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/doJustifAbsence",
    sco_abs_views.doJustifAbsence,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/AnnuleAbsenceEtud",
    sco_abs_views.AnnuleAbsenceEtud,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/doAnnuleAbsence",
    sco_abs_views.doAnnuleAbsence,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/doAnnuleJustif",
    sco_abs_views.doAnnuleJustif,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)
sco_publish(
    "/AnnuleAbsencesDatesNoJust",
    sco_abs_views.AnnuleAbsencesDatesNoJust,
    Permission.ScoAbsChange,
    methods=["GET", "POST"],
)

sco_publish("/ListeAbsEtud", sco_abs_views.ListeAbsEtud, Permission.ScoView)

# --------------------------------------------------------------------
#
#   SQL METHODS (xxx #sco8 not views => à déplacer)
#
# --------------------------------------------------------------------

# API backward compatibility
sco_publish("/CountAbs", sco_abs.count_abs, Permission.ScoView)
sco_publish("/CountAbsJust", sco_abs.count_abs_just, Permission.ScoView)
# TODO nouvel appel rendnat les deux valeurs et utilisant le cache


@bp.route("/doSignaleAbsenceGrSemestre", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoAbsChange)
@scodoc7func
def doSignaleAbsenceGrSemestre(
    moduleimpl_id=None,
    abslist=[],
    dates="",
    etudids="",
    destination=None,
):
    """Enregistre absences aux dates indiquees (abslist et dates).
    dates est une liste de dates ISO (séparées par des ',').
    Efface les absences aux dates indiquées par dates,
    ou bien ajoute celles de abslist.
    """
    moduleimpl_id = moduleimpl_id or None
    if etudids:
        etudids = [int(x) for x in str(etudids).split(",")]
    else:
        etudids = []
    if dates:
        dates = dates.split(",")
    else:
        dates = []

    # 1- Efface les absences
    if dates:
        for etudid in etudids:
            sco_abs_views.AnnuleAbsencesDatesNoJust(etudid, dates, moduleimpl_id)
        return "Absences effacées"

    # 2- Ajoute les absences
    if abslist:
        sco_abs.add_abslist(abslist, moduleimpl_id)
        return "Absences ajoutées"

    return ("", 204)


# ------------ HTML Interfaces
@bp.route("/SignaleAbsenceGrHebdo", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoAbsChange)
@scodoc7func
def SignaleAbsenceGrHebdo(
    datelundi, group_ids=[], destination="", moduleimpl_id=None, formsemestre_id=None
):
    "Saisie hebdomadaire des absences"
    if not moduleimpl_id:
        moduleimpl_id = None

    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, moduleimpl_id=moduleimpl_id, formsemestre_id=formsemestre_id
    )
    if not groups_infos.members:
        return (
            html_sco_header.sco_header(page_title="Saisie des absences")
            + "<h3>Aucun étudiant !</h3>"
            + html_sco_header.sco_footer()
        )

    base_url = "SignaleAbsenceGrHebdo?datelundi=%s&%s&destination=%s" % (
        datelundi,
        groups_infos.groups_query_args,
        urllib.parse.quote(destination),
    )

    formsemestre_id = groups_infos.formsemestre_id
    require_module = sco_preferences.get_preference(
        "abs_require_module", formsemestre_id
    )
    etuds = [
        sco_etud.get_etud_info(etudid=m["etudid"], filled=True)[0]
        for m in groups_infos.members
    ]
    # Restreint aux inscrits au module sélectionné
    if moduleimpl_id:
        mod_inscrits = set(
            [
                x["etudid"]
                for x in sco_moduleimpl.do_moduleimpl_inscription_list(
                    moduleimpl_id=moduleimpl_id
                )
            ]
        )
        etuds_inscrits_module = [e for e in etuds if e["etudid"] in mod_inscrits]
        if etuds_inscrits_module:
            etuds = etuds_inscrits_module
        else:
            # Si aucun etudiant n'est inscrit au module choisi...
            moduleimpl_id = None
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    sem = sco_formsemestre.do_formsemestre_list({"formsemestre_id": formsemestre_id})[0]

    # calcule dates jours de cette semaine
    # liste de dates iso "yyyy-mm-dd"
    datessem = [ndb.DateDMYtoISO(datelundi)]
    for _ in sco_abs.day_names()[1:]:
        datessem.append(sco_abs.next_iso_day(datessem[-1]))
    #
    if groups_infos.tous_les_etuds_du_sem:
        gr_tit = "en"
    else:
        if len(groups_infos.group_ids) > 1:
            p = "des groupes"
        else:
            p = "du groupe"
        gr_tit = p + ' <span class="fontred">' + groups_infos.groups_titles + "</span>"

    H = [
        html_sco_header.sco_header(
            page_title="Saisie hebdomadaire des absences",
            init_qtip=True,
            javascripts=html_sco_header.BOOTSTRAP_MULTISELECT_JS
            + [
                "js/etud_info.js",
                "js/abs_ajax.js",
                "js/groups_view.js",
            ],
            cssstyles=CSSSTYLES,
            no_side_bar=1,
        ),
        """<table border="0" cellspacing="16"><tr><td>
        <h2>Saisie des absences %s %s, 
        <span class="fontred">semaine du lundi %s</span></h2>
        <div>
        <form id="group_selector" method="get">
        <input type="hidden" name="formsemestre_id" id="formsemestre_id" value="%s"/>
        <input type="hidden" name="datelundi" id="datelundi" value="%s"/>
        <input type="hidden" name="destination" id="destination" value="%s"/>
        <input type="hidden" name="moduleimpl_id" id="moduleimpl_id_o" value="%s"/>
        Groupes: %s
        </form>
        <form id="abs_form">
        """
        % (
            gr_tit,
            sem["titre_num"],
            datelundi,
            groups_infos.formsemestre_id,
            datelundi,
            destination,
            moduleimpl_id or "",
            sco_groups_view.menu_groups_choice(groups_infos, submit_on_change=True),
        ),
    ]
    #
    modimpls_list = []
    # Initialize with first student
    ues = nt.get_ues(etudid=etuds[0]["etudid"])
    for ue in ues:
        modimpls_list += nt.get_modimpls(ue_id=ue["ue_id"])

    # Add modules other students are subscribed to
    for etud in etuds[1:]:
        modimpls_etud = []
        ues = nt.get_ues(etudid=etud["etudid"])
        for ue in ues:
            modimpls_etud += nt.get_modimpls(ue_id=ue["ue_id"])
        modimpls_list += [m for m in modimpls_etud if m not in modimpls_list]

    menu_module = ""
    for modimpl in modimpls_list:
        if modimpl["moduleimpl_id"] == moduleimpl_id:
            sel = "selected"
        else:
            sel = ""
        menu_module += (
            """<option value="%(modimpl_id)s" %(sel)s>%(modname)s</option>\n"""
            % {
                "modimpl_id": modimpl["moduleimpl_id"],
                "modname": modimpl["module"]["code"]
                + " "
                + (modimpl["module"]["abbrev"] or modimpl["module"]["titre"]),
                "sel": sel,
            }
        )
    if moduleimpl_id:
        sel = ""
    else:
        sel = "selected"  # aucun module specifie

    H.append(
        """Module concerné: 
        <select id="moduleimpl_id" name="moduleimpl_id" onchange="change_moduleimpl('%(url)s')">
        <option value="" %(sel)s>non spécifié</option>
        %(menu_module)s
        </select>
        </div>"""
        % {"menu_module": menu_module, "url": base_url, "sel": sel}
    )

    H += _gen_form_saisie_groupe(
        etuds, datessem, destination, moduleimpl_id, require_module
    )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


@bp.route("/SignaleAbsenceGrSemestre", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoAbsChange)
@scodoc7func
def SignaleAbsenceGrSemestre(
    datedebut,
    datefin,
    destination="",
    group_ids=[],  # list of groups to display
    nbweeks=4,  # ne montre que les nbweeks dernieres semaines
    moduleimpl_id=None,
):
    """Saisie des absences sur une journée sur un semestre (ou intervalle de dates) entier"""
    groups_infos = sco_groups_view.DisplayedGroupsInfos(group_ids)
    if not groups_infos.members:
        return (
            html_sco_header.sco_header(page_title="Saisie des absences")
            + "<h3>Aucun étudiant !</h3>"
            + html_sco_header.sco_footer()
        )
    formsemestre_id = groups_infos.formsemestre_id
    require_module = sco_preferences.get_preference(
        "abs_require_module", formsemestre_id
    )
    etuds = [
        sco_etud.get_etud_info(etudid=m["etudid"], filled=True)[0]
        for m in groups_infos.members
    ]
    # Restreint aux inscrits au module sélectionné
    if moduleimpl_id:
        mod_inscrits = set(
            [
                x["etudid"]
                for x in sco_moduleimpl.do_moduleimpl_inscription_list(
                    moduleimpl_id=moduleimpl_id
                )
            ]
        )
        etuds = [e for e in etuds if e["etudid"] in mod_inscrits]
    if not moduleimpl_id:
        moduleimpl_id = None
    base_url_noweeks = (
        "SignaleAbsenceGrSemestre?datedebut=%s&datefin=%s&%s&destination=%s"
        % (
            datedebut,
            datefin,
            groups_infos.groups_query_args,
            urllib.parse.quote(destination),
        )
    )
    base_url = base_url_noweeks + "&nbweeks=%s" % nbweeks  # sans le moduleimpl_id

    if etuds:
        nt = sco_cache.NotesTableCache.get(formsemestre_id)
        sem = sco_formsemestre.do_formsemestre_list(
            {"formsemestre_id": formsemestre_id}
        )[0]
    work_saturday = sco_abs.is_work_saturday()
    jourdebut = sco_abs.ddmmyyyy(datedebut, work_saturday=work_saturday)
    jourfin = sco_abs.ddmmyyyy(datefin, work_saturday=work_saturday)
    today = sco_abs.ddmmyyyy(
        time.strftime("%d/%m/%Y", time.localtime()),
        work_saturday=work_saturday,
    )
    today.next_day()
    if jourfin > today:  # ne propose jamais les semaines dans le futur
        jourfin = today
    if jourdebut > today:
        raise ScoValueError("date de début dans le futur (%s) !" % jourdebut)
    #
    if not jourdebut.iswork() or jourdebut > jourfin:
        raise ValueError(
            "date debut invalide (%s, ouvrable=%d)"
            % (str(jourdebut), jourdebut.iswork())
        )
    # calcule dates
    dates = []  # sco_abs.ddmmyyyy instances
    d = sco_abs.ddmmyyyy(datedebut, work_saturday=work_saturday)
    while d <= jourfin:
        dates.append(d)
        d = d.next_day(7)  # avance d'une semaine
    #
    msg = "Montrer seulement les 4 dernières semaines"
    nwl = 4
    if nbweeks:
        nbweeks = int(nbweeks)
        if nbweeks > 0:
            dates = dates[-nbweeks:]
            msg = "Montrer toutes les semaines"
            nwl = 0
    url_link_semaines = base_url_noweeks + "&nbweeks=%s" % nwl
    if moduleimpl_id:
        url_link_semaines += "&moduleimpl_id=" + str(moduleimpl_id)
    #
    dates = [x.ISO() for x in dates]
    dayname = sco_abs.day_names()[jourdebut.weekday]

    if groups_infos.tous_les_etuds_du_sem:
        gr_tit = "en"
    else:
        if len(groups_infos.group_ids) > 1:
            p = "des groupes "
        else:
            p = "du groupe "
        gr_tit = p + '<span class="fontred">' + groups_infos.groups_titles + "</span>"

    H = [
        html_sco_header.sco_header(
            page_title="Saisie des absences",
            init_qtip=True,
            javascripts=["js/etud_info.js", "js/abs_ajax.js"],
            no_side_bar=1,
        ),
        """<table border="0" cellspacing="16"><tr><td>
            <h2>Saisie des absences %s %s, 
            les <span class="fontred">%s</span></h2>
            <p>
            <a href="%s">%s</a>
            <form id="abs_form" action="doSignaleAbsenceGrSemestre" method="post">
            """
        % (gr_tit, sem["titre_num"], dayname, url_link_semaines, msg),
    ]
    #
    if etuds:
        modimpls_list = []
        # Initialize with first student
        ues = nt.get_ues(etudid=etuds[0]["etudid"])
        for ue in ues:
            modimpls_list += nt.get_modimpls(ue_id=ue["ue_id"])

        # Add modules other students are subscribed to
        for etud in etuds[1:]:
            modimpls_etud = []
            ues = nt.get_ues(etudid=etud["etudid"])
            for ue in ues:
                modimpls_etud += nt.get_modimpls(ue_id=ue["ue_id"])
            modimpls_list += [m for m in modimpls_etud if m not in modimpls_list]

        menu_module = ""
        for modimpl in modimpls_list:
            if modimpl["moduleimpl_id"] == moduleimpl_id:
                sel = "selected"
            else:
                sel = ""
            menu_module += (
                """<option value="%(modimpl_id)s" %(sel)s>%(modname)s</option>\n"""
                % {
                    "modimpl_id": modimpl["moduleimpl_id"],
                    "modname": modimpl["module"]["code"]
                    + " "
                    + (modimpl["module"]["abbrev"] or modimpl["module"]["titre"]),
                    "sel": sel,
                }
            )
        if moduleimpl_id:
            sel = ""
        else:
            sel = "selected"  # aucun module specifie
        H.append(
            """<p>
Module concerné par ces absences (%(optionel_txt)s): 
<select id="moduleimpl_id" name="moduleimpl_id" 
onchange="document.location='%(url)s&moduleimpl_id='+document.getElementById('moduleimpl_id').value">
<option value="" %(sel)s>non spécifié</option>
%(menu_module)s
</select>
</p>"""
            % {
                "menu_module": menu_module,
                "url": base_url,
                "sel": sel,
                "optionel_txt": '<span class="redboldtext">requis</span>'
                if require_module
                else "optionnel",
            }
        )

    H += _gen_form_saisie_groupe(
        etuds, dates, destination, moduleimpl_id, require_module
    )
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def _gen_form_saisie_groupe(
    etuds, dates, destination="", moduleimpl_id=None, require_module=False
):
    """Formulaire saisie absences

    Args:
        etuds: liste des étudiants
        dates: liste ordonnée de dates iso, par exemple: [ '2020-12-24', ... ]
        moduleimpl_id: optionnel, module concerné.
    """
    H = [
        """
    <script type="text/javascript">
    $(function() {
        $(".abs_form_table input").prop( "disabled", %s );
    });
    function colorize(obj) {
            if (obj.checked) {
                obj.parentNode.className = 'absent';
            } else {
                obj.parentNode.className = 'present';
            }
    }
    function on_toggled(obj, etudid, dat) {
        colorize(obj);
        if (obj.checked) {
            ajaxFunction('add', etudid, dat);
        } else {
            ajaxFunction('remove', etudid, dat);
        }
    }
    </script>
    <div id="AjaxDiv"></div>
    <br/>
    <table rules="cols" frame="box" class="abs_form_table">
    <tr><th class="formabs_contetud">%d étudiants</th>
    """
        % (
            "true" if (require_module and not moduleimpl_id) else "false",
            len(etuds),
        )
    ]
    # Dates
    odates = [datetime.date(*[int(x) for x in d.split("-")]) for d in dates]
    begin = dates[0]
    end = dates[-1]
    # Titres colonnes
    noms_jours = []  # eg [ "Lundi", "mardi", "Samedi", ... ]
    jn = sco_abs.day_names()
    for d in odates:
        idx_jour = d.weekday()
        noms_jours.append(jn[idx_jour])
    for jour in noms_jours:
        H.append(
            '<th colspan="2" width="100px" style="padding-left: 5px; padding-right: 5px;">'
            + jour
            + "</th>"
        )
    H.append("</tr><tr><td>&nbsp;</td>")
    for d in odates:
        H.append(
            '<th colspan="2" width="100px" style="padding-left: 5px; padding-right: 5px;">'
            + d.strftime("%d/%m/%Y")
            + "</th>"
        )
    H.append("</tr><tr><td>&nbsp;</td>")
    H.append("<th>AM</th><th>PM</th>" * len(dates))
    H.append("</tr>")
    #
    if not etuds:
        H.append(
            '<tr><td><span class="redboldtext">Aucun étudiant inscrit !</span></td></tr>'
        )
    i = 1
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    for etud in etuds:
        i += 1
        etudid = etud["etudid"]
        etud_class = "etudinfo"  # css
        # UE capitalisee dans semestre courant ?
        cap = []
        if etud["cursem"]:
            nt = sco_cache.NotesTableCache.get(
                etud["cursem"]["formsemestre_id"]
            )  # > get_ues, get_etud_ue_status
            for ue in nt.get_ues():
                status = nt.get_etud_ue_status(etudid, ue["ue_id"])
                if status["is_capitalized"]:
                    cap.append(ue["acronyme"])
        if cap:
            capstr = ' <span class="capstr">(%s cap.)</span>' % ", ".join(cap)
        else:
            capstr = ""
        if etud["etatincursem"] == "D":
            capstr += ' <span class="capstr">(dém.)</span>'
            etud_class += " etuddem"
        tr_class = ("row_1", "row_2", "row_3")[i % 3]
        td_matin_class = ("matin_1", "matin_2", "matin_3")[i % 3]

        H.append(
            '<tr class="%s"><td><b class="%s" id="%s"><a class="discretelink" href="%s" target="new">%s</a></b>%s</td>'
            % (
                tr_class,
                etud_class,
                etudid,
                url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
                etud["nomprenom"],
                capstr,
            )
        )
        etud_abs = sco_abs.list_abs_in_range(
            etudid, begin, end, moduleimpl_id=moduleimpl_id, cursor=cursor
        )
        for d in odates:
            date = d.strftime("%Y-%m-%d")
            # matin
            is_abs = {"jour": d, "matin": True} in etud_abs
            if is_abs:
                checked = "checked"
            else:
                checked = ""
            #  bulle lors du passage souris
            coljour = sco_abs.DAYNAMES[(calendar.weekday(d.year, d.month, d.day))]
            datecol = coljour + " " + d.strftime("%d/%m/%Y")
            bulle_am = '"' + etud["nomprenom"] + " - " + datecol + ' (matin)"'
            bulle_pm = '"' + etud["nomprenom"] + " - " + datecol + ' (ap.midi)"'

            H.append(
                '<td class="%s"><a title=%s><input type="checkbox" name="abslist:list" value="%s" %s onclick="on_toggled(this, \'%s\', \'%s\')"/></a></td>'
                % (
                    td_matin_class,
                    bulle_am,
                    str(etudid) + ":" + date + ":" + "am",
                    checked,
                    etudid,
                    date + ":am",
                )
            )
            # après-midi
            is_abs = {"jour": d, "matin": False} in etud_abs
            if is_abs:
                checked = "checked"
            else:
                checked = ""
            H.append(
                '<td><a title=%s><input type="checkbox" name="abslist:list" value="%s" %s onclick="on_toggled(this, \'%s\', \'%s\')"/></a></td>'
                % (
                    bulle_pm,
                    str(etudid) + ":" + date + ":" + "pm",
                    checked,
                    etudid,
                    date + ":pm",
                )
            )
        H.append("</tr>")
    H.append("</table>")
    # place la liste des etudiants et les dates pour pouvoir effacer les absences
    H.append(
        '<input type="hidden" name="etudids" value="%s"/>'
        % ",".join([str(etud["etudid"]) for etud in etuds])
    )
    H.append('<input type="hidden" name="datedebut" value="%s"/>' % dates[0])
    H.append('<input type="hidden" name="datefin" value="%s"/>' % dates[-1])
    H.append('<input type="hidden" name="dates" value="%s"/>' % ",".join(dates))
    H.append(
        '<input type="hidden" name="destination" value="%s"/>'
        % urllib.parse.quote(destination)
    )
    #
    # version pour formulaire avec AJAX (Yann LB)
    H.append(
        """
        <p><input type="button" value="Retour" onClick="window.location='%s'"/>
        </p>
        </form>
        </p>
        </td></tr></table>
        <p class="help">Les cases cochées correspondent à des absences.
        Les absences saisies ne sont pas justifiées (sauf si un justificatif a été entré
        par ailleurs).
        </p><p class="help">Si vous "décochez" une case,  l'absence correspondante sera supprimée.
        Attention, les modifications sont automatiquement entregistrées au fur et à mesure.
        </p>
    """
        % destination
    )
    return H


@bp.route("/EtatAbsencesGr")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func  # ported from dtml
def EtatAbsencesGr(
    group_ids=[],  # list of groups to display
    debut="",
    fin="",
    with_boursier=True,  # colonne boursier
    format="html",
):
    """Liste les absences de groupes"""
    datedebut = ndb.DateDMYtoISO(debut)
    datefin = ndb.DateDMYtoISO(fin)
    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(group_ids)
    formsemestre_id = groups_infos.formsemestre_id
    sem = groups_infos.formsemestre

    # Construit tableau (etudid, statut, nomprenom, nbJust, nbNonJust, NbTotal)
    T = []
    for m in groups_infos.members:
        etud = sco_etud.get_etud_info(etudid=m["etudid"], filled=True)[0]
        nbabs = sco_abs.count_abs(etudid=etud["etudid"], debut=datedebut, fin=datefin)
        nbabsjust = sco_abs.count_abs_just(
            etudid=etud["etudid"], debut=datedebut, fin=datefin
        )
        nbjustifs_noabs = len(
            sco_abs.list_abs_justifs(
                etudid=etud["etudid"], datedebut=datedebut, only_no_abs=True
            )
        )
        # retrouve sem dans etud['sems']
        s = None
        for s in etud["sems"]:
            if s["formsemestre_id"] == formsemestre_id:
                break
        if not s or s["formsemestre_id"] != formsemestre_id:
            raise ValueError(
                "EtatAbsencesGr: can't retreive sem"
            )  # bug or malicious arg
        T.append(
            {
                "etudid": etud["etudid"],
                "etatincursem": s["ins"]["etat"],
                "nomprenom": etud["nomprenom"],
                "nbabsjust": nbabsjust,
                "nbabsnonjust": nbabs - nbabsjust,
                "nbabs": nbabs,
                "nbjustifs_noabs": nbjustifs_noabs,
                "_nomprenom_target": "CalAbs?etudid=%s" % etud["etudid"],
                "_nomprenom_td_attrs": 'id="%s" class="etudinfo"' % etud["etudid"],
                "boursier": etud["boursier"],
            }
        )
        if s["ins"]["etat"] == "D":
            T[-1]["_css_row_class"] = "etuddem"
            T[-1]["nomprenom"] += " (dem)"
    columns_ids = [
        "nomprenom",
        "nbjustifs_noabs",
        "nbabsjust",
        "nbabsnonjust",
        "nbabs",
    ]
    if with_boursier:
        columns_ids[1:1] = ["boursier"]
    if groups_infos.tous_les_etuds_du_sem:
        gr_tit = ""
    else:
        if len(groups_infos.group_ids) > 1:
            p = "des groupes"
        else:
            p = "du groupe"
        if format == "html":
            h = ' <span class="fontred">' + groups_infos.groups_titles + "</span>"
        else:
            h = groups_infos.groups_titles
        gr_tit = p + h

    title = "État des absences %s" % gr_tit
    if format == "xls" or format == "xml" or format == "json":
        columns_ids = ["etudid"] + columns_ids
    tab = GenTable(
        columns_ids=columns_ids,
        rows=T,
        preferences=sco_preferences.SemPreferences(formsemestre_id),
        titles={
            "etatincursem": "Etat",
            "nomprenom": "Nom",
            "nbabsjust": "Justifiées",
            "nbabsnonjust": "Non justifiées",
            "nbabs": "Total",
            "nbjustifs_noabs": "Justifs non utilisés",
            "boursier": "Bourse",
        },
        html_sortable=True,
        html_class="table_leftalign",
        html_header=html_sco_header.sco_header(
            page_title=title,
            init_qtip=True,
            javascripts=["js/etud_info.js"],
        ),
        html_title=html_sco_header.html_sem_header(
            "%s" % title, sem, with_page_header=False
        )
        + "<p>Période du %s au %s (nombre de <b>demi-journées</b>)<br/>" % (debut, fin),
        base_url="%s&formsemestre_id=%s&debut=%s&fin=%s"
        % (groups_infos.base_url, formsemestre_id, debut, fin),
        filename="etat_abs_"
        + scu.make_filename(
            "%s de %s" % (groups_infos.groups_filename, sem["titreannee"])
        ),
        caption=title,
        html_next_section="""</table>
<p class="help">
Justifs non utilisés: nombre de demi-journées avec justificatif mais sans absences relevées.
</p>
<p class="help">
Cliquez sur un nom pour afficher le calendrier des absences<br/>
ou entrez une date pour visualiser les absents un jour donné&nbsp;:
</p>
<div style="margin-bottom: 10px;">
<form action="EtatAbsencesDate" method="get" action="%s">
<input type="hidden" name="formsemestre_id" value="%s">
%s
<input type="text" name="date" size="10" class="datepicker"/>
<input type="submit" name="" value="visualiser les absences">
</form></div>
                    """
        % (request.base_url, formsemestre_id, groups_infos.get_form_elem()),
    )
    return tab.make_page(format=format)


@bp.route("/EtatAbsencesDate")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def EtatAbsencesDate(group_ids=[], date=None):  # list of groups to display
    # ported from dtml
    """Etat des absences pour un groupe à une date donnée"""
    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(group_ids)
    H = [html_sco_header.sco_header(page_title="Etat des absences")]
    if date:
        dateiso = ndb.DateDMYtoISO(date)
        nbetud = 0
        t_nbabsjustam = 0
        t_nbabsam = 0
        t_nbabsjustpm = 0
        t_nbabspm = 0
        H.append("<h2>État des absences le %s</h2>" % date)
        H.append(
            """<table border="0" cellspacing="4" cellpadding="0">
            <tr><th>&nbsp;</th>
        <th style="width: 10em;">Matin</th><th style="width: 10em;">Après-midi</th></tr>
        """
        )
        for etud in groups_infos.members:
            nbabsam = sco_abs.count_abs(
                etudid=etud["etudid"], debut=dateiso, fin=dateiso, matin=1
            )
            nbabspm = sco_abs.count_abs(
                etudid=etud["etudid"], debut=dateiso, fin=dateiso, matin=0
            )
            if (nbabsam != 0) or (nbabspm != 0):
                nbetud += 1
                nbabsjustam = sco_abs.count_abs_just(
                    etudid=etud["etudid"], debut=dateiso, fin=dateiso, matin=1
                )
                nbabsjustpm = sco_abs.count_abs_just(
                    etudid=etud["etudid"], debut=dateiso, fin=dateiso, matin=0
                )
                H.append(
                    """<tr bgcolor="#FFFFFF"><td>
                    <a href="CalAbs?etudid=%(etudid)s"><font color="#A00000">%(nomprenom)s</font></a></td><td align="center">"""
                    % etud
                )  # """
                if nbabsam != 0:
                    if nbabsjustam:
                        H.append("Just.")
                        t_nbabsjustam += 1
                    else:
                        H.append("Abs.")
                        t_nbabsam += 1
                else:
                    H.append("")
                H.append('</td><td align="center">')
                if nbabspm != 0:
                    if nbabsjustpm:
                        H.append("Just.")
                        t_nbabsjustam += 1
                    else:
                        H.append("Abs.")
                        t_nbabspm += 1
                else:
                    H.append("")
                H.append("</td></tr>")
        H.append(
            """<tr bgcolor="#FFFFFF"><td></td><td>%d abs, %d just.</td><td>%d abs, %d just.</td></tr>"""
            % (t_nbabsam, t_nbabsjustam, t_nbabspm, t_nbabsjustpm)
        )
        H.append("</table>")
        if nbetud == 0:
            H.append("<p>Aucune absence !</p>")
    else:
        H.append(
            """<h2>Erreur: vous n'avez pas choisi de date !</h2>
            """
        )

    return "\n".join(H) + html_sco_header.sco_footer()


# ----- Gestion des "billets d'absence": signalement par les etudiants eux mêmes (à travers le portail)
@bp.route("/AddBilletAbsence", methods=["GET", "POST"])  # API ScoDoc 7 compat
@scodoc
@permission_required_compat_scodoc7(Permission.ScoAbsAddBillet)
@scodoc7func
def AddBilletAbsence(
    begin,
    end,
    description,
    etudid=False,
    code_nip=None,
    code_ine=None,
    justified=True,
    format="json",
    xml_reply=True,  # deprecated
):
    """Mémorise un "billet"
    begin et end sont au format ISO (eg "1999-01-08 04:05:06")
    """
    t0 = time.time()
    begin = str(begin)
    end = str(end)
    code_nip = str(code_nip) if code_nip else None

    # check etudid
    etuds = sco_etud.get_etud_info(etudid=etudid, code_nip=code_nip, filled=True)
    if not etuds:
        sco_etud.log_unknown_etud()
        raise ScoValueError("étudiant inconnu")

    etud = etuds[0]
    # check dates
    begin_date = dateutil.parser.isoparse(begin)  # may raises ValueError
    end_date = dateutil.parser.isoparse(end)
    if begin_date > end_date:
        raise ValueError("invalid dates")
    #
    justified = bool(justified)
    xml_reply = bool(xml_reply)
    #
    cnx = ndb.GetDBConnexion()
    billet_id = sco_abs.billet_absence_create(
        cnx,
        {
            "etudid": etud["etudid"],
            "abs_begin": begin,
            "abs_end": end,
            "description": description,
            "etat": False,
            "justified": justified,
        },
    )
    if xml_reply:  # backward compat
        format = "xml"

    # Renvoie le nouveau billet au format demandé
    billets = sco_abs.billet_absence_list(cnx, {"billet_id": billet_id})
    tab = _tableBillets(billets, etud=etud)
    log("AddBilletAbsence: new billet_id=%s (%gs)" % (billet_id, time.time() - t0))
    return tab.make_page(format=format)


@bp.route("/AddBilletAbsenceForm", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoAbsAddBillet)
@scodoc7func
def AddBilletAbsenceForm(etudid):
    """Formulaire ajout billet (pour tests seulement, le vrai formulaire accessible aux etudiants
    étant sur le portail étudiant).
    """
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    H = [
        html_sco_header.sco_header(
            page_title="Billet d'absence de %s" % etud["nomprenom"]
        )
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("etudid", {"input_type": "hidden"}),
            ("begin", {"input_type": "date"}),
            ("end", {"input_type": "date"}),
            (
                "justified",
                {"input_type": "boolcheckbox", "default": 0, "title": "Justifiée"},
            ),
            ("description", {"input_type": "textarea"}),
        ),
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(scu.ScoURL())
    else:
        e = tf[2]["begin"].split("/")
        begin = e[2] + "-" + e[1] + "-" + e[0] + " 00:00:00"
        e = tf[2]["end"].split("/")
        end = e[2] + "-" + e[1] + "-" + e[0] + " 00:00:00"
        log(
            AddBilletAbsence(
                begin,
                end,
                tf[2]["description"],
                etudid=etudid,
                xml_reply=True,
                justified=tf[2]["justified"],
            )
        )
        return flask.redirect("listeBilletsEtud?etudid=" + str(etudid))


def _tableBillets(billets, etud=None, title=""):
    for b in billets:
        if b["abs_begin"].hour < 12:
            m = " matin"
        else:
            m = " après-midi"
        b["abs_begin_str"] = b["abs_begin"].strftime("%d/%m/%Y") + m
        if b["abs_end"].hour < 12:
            m = " matin"
        else:
            m = " après-midi"
        b["abs_end_str"] = b["abs_end"].strftime("%d/%m/%Y") + m
        if b["etat"] == 0:
            if b["justified"]:
                b["etat_str"] = "à traiter"
            else:
                b["etat_str"] = "à justifier"
            b["_etat_str_target"] = (
                "ProcessBilletAbsenceForm?billet_id=%s" % b["billet_id"]
            )
            if etud:
                b["_etat_str_target"] += "&etudid=%s" % etud["etudid"]
            b["_billet_id_target"] = b["_etat_str_target"]
        else:
            b["etat_str"] = "ok"
        if not etud:
            # ajoute info etudiant
            e = sco_etud.get_etud_info(etudid=b["etudid"], filled=1)
            if not e:
                b["nomprenom"] = "???"  # should not occur
            else:
                b["nomprenom"] = e[0]["nomprenom"]
            b["_nomprenom_target"] = url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=b["etudid"]
            )
    if etud and not title:
        title = "Billets d'absence déclarés par %(nomprenom)s" % etud
    else:
        title = title
    columns_ids = ["billet_id"]
    if not etud:
        columns_ids += ["nomprenom"]
    columns_ids += ["abs_begin_str", "abs_end_str", "description", "etat_str"]

    tab = GenTable(
        titles={
            "billet_id": "Numéro",
            "abs_begin_str": "Début",
            "abs_end_str": "Fin",
            "description": "Raison de l'absence",
            "etat_str": "Etat",
        },
        columns_ids=columns_ids,
        page_title=title,
        html_title="<h2>%s</h2>" % title,
        preferences=sco_preferences.SemPreferences(),
        rows=billets,
        html_sortable=True,
    )
    return tab


@bp.route("/listeBilletsEtud")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def listeBilletsEtud(etudid=False, format="html"):
    """Liste billets pour un etudiant"""
    etuds = sco_etud.get_etud_info(filled=True, etudid=etudid)
    if not etuds:
        sco_etud.log_unknown_etud()
        raise ScoValueError("étudiant inconnu")

    etud = etuds[0]
    cnx = ndb.GetDBConnexion()
    billets = sco_abs.billet_absence_list(cnx, {"etudid": etud["etudid"]})
    tab = _tableBillets(billets, etud=etud)
    return tab.make_page(format=format)


@bp.route(
    "/XMLgetBilletsEtud", methods=["GET", "POST"]
)  # pour compat anciens clients PHP
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def XMLgetBilletsEtud(etudid=False):
    """Liste billets pour un etudiant"""
    if not sco_preferences.get_preference("handle_billets_abs"):
        return ""
    t0 = time.time()
    r = listeBilletsEtud(etudid, format="xml")
    log("XMLgetBilletsEtud (%gs)" % (time.time() - t0))
    return r


@bp.route("/listeBillets", methods=["GET"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def listeBillets():
    """Page liste des billets non traités et formulaire recherche d'un billet"""
    # utilise Flask, jointure avec departement de l'étudiant
    billets = (
        BilletAbsence.query.filter_by(etat=False)
        .join(BilletAbsence.etudiant, aliased=True)
        .filter_by(dept_id=g.scodoc_dept_id)
    )
    # reconverti en dict pour les fonctions scodoc7
    billets = [b.to_dict() for b in billets]
    #
    tab = _tableBillets(billets)
    T = tab.html()
    H = [
        html_sco_header.sco_header(page_title="Billet d'absence non traités"),
        "<h2>Billets d'absence en attente de traitement (%d)</h2>" % len(billets),
    ]

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("billet_id", {"input_type": "text", "title": "Numéro du billet"}),),
        submitbutton=False,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + T + html_sco_header.sco_footer()
    else:
        return flask.redirect(
            "ProcessBilletAbsenceForm?billet_id=" + tf[2]["billet_id"]
        )


@bp.route("/deleteBilletAbsence", methods=["POST", "GET"])
@scodoc
@permission_required(Permission.ScoAbsChange)
@scodoc7func
def deleteBilletAbsence(billet_id, dialog_confirmed=False):
    """Supprime un billet."""
    cnx = ndb.GetDBConnexion()
    billets = sco_abs.billet_absence_list(cnx, {"billet_id": billet_id})
    if not billets:
        return flask.redirect(
            "listeBillets?head_message=Billet%%20%s%%20inexistant !" % billet_id
        )
    if not dialog_confirmed:
        tab = _tableBillets(billets)
        return scu.confirm_dialog(
            """<h2>Supprimer ce billet ?</h2>""" + tab.html(),
            dest_url="",
            cancel_url="listeBillets",
            parameters={"billet_id": billet_id},
        )

    sco_abs.billet_absence_delete(cnx, billet_id)

    return flask.redirect("listeBillets?head_message=Billet%20supprimé")


def _ProcessBilletAbsence(billet, estjust, description):
    """Traite un billet: ajoute absence(s) et éventuellement justificatifs,
    et change l'état du billet à 1.
    NB: actuellement, les heures ne sont utilisées que pour déterminer si matin et/ou après-midi.
    """
    cnx = ndb.GetDBConnexion()
    if billet["etat"] != 0:
        log("billet=%s" % billet)
        log("billet deja traité !")
        return -1
    n = 0  # nombre de demi-journées d'absence ajoutées
    # 1-- ajout des absences (et justifs)
    datedebut = billet["abs_begin"].strftime("%d/%m/%Y")
    datefin = billet["abs_end"].strftime("%d/%m/%Y")
    dates = sco_abs.DateRangeISO(datedebut, datefin)
    # commence après-midi ?
    if dates and billet["abs_begin"].hour > 11:
        sco_abs.add_absence(
            billet["etudid"],
            dates[0],
            0,
            estjust,
            description=description,
        )
        n += 1
        dates = dates[1:]
    # termine matin ?
    if dates and billet["abs_end"].hour < 12:
        sco_abs.add_absence(
            billet["etudid"],
            dates[-1],
            1,
            estjust,
            description=description,
        )
        n += 1
        dates = dates[:-1]

    for jour in dates:
        sco_abs.add_absence(
            billet["etudid"],
            jour,
            0,
            estjust,
            description=description,
        )
        sco_abs.add_absence(
            billet["etudid"],
            jour,
            1,
            estjust,
            description=description,
        )
        n += 2

    # 2- change etat du billet
    sco_abs.billet_absence_edit(cnx, {"billet_id": billet["billet_id"], "etat": 1})

    return n


@bp.route("/ProcessBilletAbsenceForm", methods=["POST", "GET"])
@scodoc
@permission_required(Permission.ScoAbsChange)
@scodoc7func
def ProcessBilletAbsenceForm(billet_id):
    """Formulaire traitement d'un billet"""
    cnx = ndb.GetDBConnexion()
    billets = sco_abs.billet_absence_list(cnx, {"billet_id": billet_id})
    if not billets:
        return flask.redirect(
            "listeBillets?head_message=Billet%%20%s%%20inexistant !" % billet_id
        )
    billet = billets[0]
    etudid = billet["etudid"]
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]

    H = [
        html_sco_header.sco_header(
            page_title="Traitement billet d'absence de %s" % etud["nomprenom"],
        ),
        '<h2>Traitement du billet %s : <a class="discretelink" href="%s">%s</a></h2>'
        % (
            billet_id,
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            etud["nomprenom"],
        ),
    ]

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("billet_id", {"input_type": "hidden"}),
            (
                "etudid",
                {"input_type": "hidden"},
            ),  # pour centrer l'UI sur l'étudiant
            (
                "estjust",
                {"input_type": "boolcheckbox", "title": "Absences justifiées"},
            ),
            ("description", {"input_type": "text", "size": 42, "title": "Raison"}),
        ),
        initvalues={
            "description": billet["description"],
            "estjust": billet["justified"],
            "etudid": etudid,
        },
        submitlabel="Enregistrer ces absences",
    )
    if tf[0] == 0:
        tab = _tableBillets([billet], etud=etud)
        H.append(tab.html())
        if billet["justified"]:
            H.append(
                """<p>L'étudiant pense pouvoir justifier cette absence.<br/><em>Vérifiez le justificatif avant d'enregistrer.</em></p>"""
            )
        F = (
            """<p><a class="stdlink" href="deleteBilletAbsence?billet_id=%s">Supprimer ce billet</a> (utiliser en cas d'erreur, par ex. billet en double)</p>"""
            % billet_id
        )
        F += '<p><a class="stdlink" href="listeBillets">Liste de tous les billets en attente</a></p>'

        return "\n".join(H) + "<br/>" + tf[1] + F + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(scu.ScoURL())
    else:
        n = _ProcessBilletAbsence(billet, tf[2]["estjust"], tf[2]["description"])
        if tf[2]["estjust"]:
            j = "justifiées"
        else:
            j = "non justifiées"
        H.append('<div class="head_message">')
        if n > 0:
            H.append("%d absences (1/2 journées) %s ajoutées" % (n, j))
        elif n == 0:
            H.append("Aucun jour d'absence dans les dates indiquées !")
        elif n < 0:
            H.append("Ce billet avait déjà été traité !")
        H.append(
            '</div><p><a class="stdlink" href="listeBillets">Autre billets en attente</a></p><h4>Billets déclarés par %s</h4>'
            % (etud["nomprenom"])
        )
        billets = sco_abs.billet_absence_list(cnx, {"etudid": etud["etudid"]})
        tab = _tableBillets(billets, etud=etud)
        H.append(tab.html())
        return "\n".join(H) + html_sco_header.sco_footer()


# @bp.route("/essai_api7")
# @scodoc
# @permission_required_compat_scodoc7(Permission.ScoView)
# @scodoc7func
# def essai_api7(x="xxx"):
#     "un essai"
#     log("arfffffffffffffffffff")
#     return "OK OK x=" + str(x)


@bp.route("/XMLgetAbsEtud", methods=["GET", "POST"])  # pour compat anciens clients PHP
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def XMLgetAbsEtud(beg_date="", end_date=""):
    """returns list of absences in date interval"""
    t0 = time.time()
    etuds = sco_etud.get_etud_info(filled=False)
    if not etuds:
        raise APIInvalidParams("étudiant inconnu")
        # raise ScoValueError("étudiant inconnu")
    etud = etuds[0]
    exp = re.compile(r"^(\d{4})\D?(0[1-9]|1[0-2])\D?([12]\d|0[1-9]|3[01])$")
    if not exp.match(beg_date):
        raise ScoValueError("invalid date: %s" % beg_date)
    if not exp.match(end_date):
        raise ScoValueError("invalid date: %s" % end_date)

    abs_list = sco_abs.list_abs_date(etud["etudid"], beg_date, end_date)

    doc = ElementTree.Element(
        "absences", etudid=str(etud["etudid"]), beg_date=beg_date, end_date=end_date
    )
    for a in abs_list:
        if a["estabs"]:  # ne donne pas les justifications si pas d'absence
            doc.append(
                ElementTree.Element(
                    "abs",
                    begin=a["begin"],
                    end=a["end"],
                    description=a["description"],
                    justified=str(int(a["estjust"])),
                )
            )
    log("XMLgetAbsEtud (%gs)" % (time.time() - t0))
    data = sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING)
    return scu.send_file(data, mime=scu.XML_MIMETYPE, attached=False)
