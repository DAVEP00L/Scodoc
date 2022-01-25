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

"""Opérations d'inscriptions aux modules (interface pour gérer options ou parcours)
"""
from operator import itemgetter

import flask
from flask import url_for, g, request
from flask_login import current_user

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.scolog import logdb
from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_cache
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_etud
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_permissions import Permission


def moduleimpl_inscriptions_edit(moduleimpl_id, etuds=[], submitted=False):
    """Formulaire inscription des etudiants a ce module
    * Gestion des inscriptions
         Nom          TD     TA    TP  (triable)
     [x] M. XXX YYY   -      -     -


     ajouter TD A, TD B, TP 1, TP 2 ...
     supprimer TD A, TD B, TP 1, TP 2 ...

     * Si pas les droits: idem en readonly
    """
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    formsemestre_id = M["formsemestre_id"]
    mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # -- check lock
    if not sem["etat"]:
        raise ScoValueError("opération impossible: semestre verrouille")
    header = html_sco_header.sco_header(
        page_title="Inscription au module",
        init_qtip=True,
        javascripts=["js/etud_info.js"],
    )
    footer = html_sco_header.sco_footer()
    H = [
        header,
        """<h2>Inscriptions au module <a href="moduleimpl_status?moduleimpl_id=%s">%s</a> (%s)</a></h2>
    <p class="help">Cette page permet d'éditer les étudiants inscrits à ce module
    (ils doivent évidemment être inscrits au semestre).
    Les étudiants cochés sont (ou seront) inscrits. Vous pouvez facilement inscrire ou
    désinscrire tous les étudiants d'un groupe à l'aide des menus "Ajouter" et "Enlever".
    </p>
    <p class="help">Aucune modification n'est prise en compte tant que l'on n'appuie pas sur le bouton
    "Appliquer les modifications".
    </p>
    """
        % (moduleimpl_id, mod["titre"], mod["code"]),
    ]
    # Liste des inscrits à ce semestre
    inscrits = sco_formsemestre_inscriptions.do_formsemestre_inscription_listinscrits(
        formsemestre_id
    )
    for ins in inscrits:
        etuds_info = sco_etud.get_etud_info(etudid=ins["etudid"], filled=1)
        if not etuds_info:
            log(
                "moduleimpl_inscriptions_edit: incoherency for etudid=%s !"
                % ins["etudid"]
            )
            raise ScoValueError(
                "Etudiant %s inscrit mais inconnu dans la base !!!!!" % ins["etudid"]
            )
        ins["etud"] = etuds_info[0]
    inscrits.sort(key=lambda x: x["etud"]["nom"])
    in_m = sco_moduleimpl.do_moduleimpl_inscription_list(
        moduleimpl_id=M["moduleimpl_id"]
    )
    in_module = set([x["etudid"] for x in in_m])
    #
    partitions = sco_groups.get_partitions_list(formsemestre_id)
    #
    if not submitted:
        H.append(
            """<script type="text/javascript">
    function group_select(groupName, partitionIdx, check) {
    var nb_inputs_to_skip = 2; // nb d'input avant les checkbox !!!
    var elems = document.getElementById("mi_form").getElementsByTagName("input");

    if (partitionIdx==-1) {
      for (var i =nb_inputs_to_skip; i < elems.length; i++) {
         elems[i].checked=check;
      }
    } else {
     for (var i =nb_inputs_to_skip; i < elems.length; i++) {
       var cells = elems[i].parentNode.parentNode.getElementsByTagName("td")[partitionIdx].childNodes;
       if (cells.length && cells[0].nodeValue == groupName) {
          elems[i].checked=check;
       }      
     }
    }
    }

    </script>"""
        )
        H.append("""<form method="post" id="mi_form" action="%s">""" % request.base_url)
        H.append(
            """        
        <input type="hidden" name="moduleimpl_id" value="%(moduleimpl_id)s"/>
        <input type="submit" name="submitted" value="Appliquer les modifications"/><p></p>
        """
            % M
        )
        H.append("<table><tr>")
        H.append(_make_menu(partitions, "Ajouter", "true"))
        H.append(_make_menu(partitions, "Enlever", "false"))
        H.append("</tr></table>")
        H.append(
            """
        <p><br/></p>
        <table class="sortable" id="mi_table"><tr>
        <th>Nom</th>"""
            % sem
        )
        for partition in partitions:
            if partition["partition_name"]:
                H.append("<th>%s</th>" % partition["partition_name"])
        H.append("</tr>")

        for ins in inscrits:
            etud = ins["etud"]
            if etud["etudid"] in in_module:
                checked = 'checked="checked"'
            else:
                checked = ""
            H.append(
                """<tr><td><input type="checkbox" name="etuds:list" value="%s" %s>"""
                % (etud["etudid"], checked)
            )
            H.append(
                """<a class="discretelink etudinfo" href="%s" id="%s">%s</a>"""
                % (
                    url_for(
                        "scolar.ficheEtud",
                        scodoc_dept=g.scodoc_dept,
                        etudid=etud["etudid"],
                    ),
                    etud["etudid"],
                    etud["nomprenom"],
                )
            )
            H.append("""</input></td>""")

            groups = sco_groups.get_etud_groups(etud["etudid"], sem)
            for partition in partitions:
                if partition["partition_name"]:
                    gr_name = ""
                    for group in groups:
                        if group["partition_id"] == partition["partition_id"]:
                            gr_name = group["group_name"]
                            break
                    # gr_name == '' si etud non inscrit dans un groupe de cette partition
                    H.append("<td>%s</td>" % gr_name)
        H.append("""</table></form>""")
    else:  # SUBMISSION
        # inscrit a ce module tous les etuds selectionnes
        sco_moduleimpl.do_moduleimpl_inscrit_etuds(
            moduleimpl_id, formsemestre_id, etuds, reset=True
        )
        return flask.redirect("moduleimpl_status?moduleimpl_id=%s" % (moduleimpl_id))
    #
    H.append(footer)
    return "\n".join(H)


def _make_menu(partitions, title="", check="true"):
    """Menu with list of all groups"""
    items = [{"title": "Tous", "attr": "onclick=\"group_select('', -1, %s)\"" % check}]
    p_idx = 0
    for partition in partitions:
        if partition["partition_name"] != None:
            p_idx += 1
            for group in sco_groups.get_partition_groups(partition):
                items.append(
                    {
                        "title": "%s %s"
                        % (partition["partition_name"], group["group_name"]),
                        "attr": "onclick=\"group_select('%s', %s, %s)\""
                        % (group["group_name"], p_idx, check),
                    }
                )
    return (
        '<td class="inscr_addremove_menu">'
        + htmlutils.make_menu(title, items, alone=True)
        + "</td>"
    )


def moduleimpl_inscriptions_stats(formsemestre_id):
    """Affiche quelques informations sur les inscriptions
    aux modules de ce semestre.

    Inscrits au semestre: <nb>

    Modules communs (tous inscrits): <liste des modules (codes)

    Autres modules: (regroupés par UE)
    UE 1
    <code du module>: <nb inscrits> (<description en termes de groupes>)
    ...


    descriptions:
      groupes de TD A, B et C
      tous sauf groupe de TP Z (?)
      tous sauf <liste d'au plus 7 noms>

    """
    authuser = current_user

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    inscrits = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id}
    )
    set_all = set([x["etudid"] for x in inscrits])
    partitions, partitions_etud_groups = sco_groups.get_formsemestre_groups(
        formsemestre_id
    )

    can_change = authuser.has_permission(Permission.ScoEtudInscrit) and sem["etat"]

    # Liste des modules
    Mlist = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)
    # Decrit les inscriptions aux modules:
    commons = []  # modules communs a tous les etuds du semestre
    options = []  # modules ou seuls quelques etudiants sont inscrits
    for mod in Mlist:
        tous_inscrits, nb_inscrits, descr = descr_inscrs_module(
            sem,
            mod["moduleimpl_id"],
            set_all,
            partitions,
            partitions_etud_groups,
        )
        if tous_inscrits:
            commons.append(mod)
        else:
            mod["descri"] = descr
            mod["nb_inscrits"] = nb_inscrits
            options.append(mod)
    # Page HTML:
    H = [html_sco_header.html_sem_header("Inscriptions aux modules du semestre")]

    H.append("<h3>Inscrits au semestre: %d étudiants</h3>" % len(inscrits))

    if options:
        H.append("<h3>Modules auxquels tous les étudiants ne sont pas inscrits:</h3>")
        H.append(
            '<table class="formsemestre_status formsemestre_inscr"><tr><th>UE</th><th>Code</th><th>Inscrits</th><th></th></tr>'
        )
        for mod in options:
            if can_change:
                c_link = (
                    '<a class="discretelink" href="moduleimpl_inscriptions_edit?moduleimpl_id=%s">%s</a>'
                    % (mod["moduleimpl_id"], mod["descri"])
                )
            else:
                c_link = mod["descri"]
            H.append(
                '<tr class="formsemestre_status"><td>%s</td><td class="formsemestre_status_code">%s</td><td class="formsemestre_status_inscrits">%s</td><td>%s</td></tr>'
                % (
                    mod["ue"]["acronyme"],
                    mod["module"]["code"],
                    mod["nb_inscrits"],
                    c_link,
                )
            )
        H.append("</table>")
    else:
        H.append(
            '<span style="font-size:110%; font-style:italic; color: red;"">Tous les étudiants sont inscrits à tous les modules.</span>'
        )

    if commons:
        H.append(
            "<h3>Modules communs (auxquels tous les étudiants sont inscrits):</h3>"
        )
        H.append(
            '<table class="formsemestre_status formsemestre_inscr"><tr><th>UE</th><th>Code</th><th>Module</th></tr>'
        )
        for mod in commons:
            if can_change:
                c_link = (
                    '<a class="discretelink" href="moduleimpl_inscriptions_edit?moduleimpl_id=%s">%s</a>'
                    % (mod["moduleimpl_id"], mod["module"]["titre"])
                )
            else:
                c_link = mod["module"]["titre"]
            H.append(
                '<tr class="formsemestre_status_green"><td>%s</td><td class="formsemestre_status_code">%s</td><td>%s</td></tr>'
                % (mod["ue"]["acronyme"], mod["module"]["code"], c_link)
            )
        H.append("</table>")

    # Etudiants "dispensés" d'une UE (capitalisée)
    UECaps = get_etuds_with_capitalized_ue(formsemestre_id)
    if UECaps:
        H.append('<h3>Etudiants avec UEs capitalisées:</h3><ul class="ue_inscr_list">')
        ues = [sco_edit_ue.ue_list({"ue_id": ue_id})[0] for ue_id in UECaps.keys()]
        ues.sort(key=lambda u: u["numero"])
        for ue in ues:
            H.append(
                '<li class="tit"><span class="tit">%(acronyme)s: %(titre)s</span>' % ue
            )
            H.append("<ul>")
            for info in UECaps[ue["ue_id"]]:
                etud = sco_etud.get_etud_info(etudid=info["etudid"], filled=True)[0]
                H.append(
                    '<li class="etud"><a class="discretelink" href="%s">%s</a>'
                    % (
                        url_for(
                            "scolar.ficheEtud",
                            scodoc_dept=g.scodoc_dept,
                            etudid=etud["etudid"],
                        ),
                        etud["nomprenom"],
                    )
                )
                if info["ue_status"]["event_date"]:
                    H.append(
                        "(cap. le %s)"
                        % (info["ue_status"]["event_date"]).strftime("%d/%m/%Y")
                    )

                if info["is_ins"]:
                    dm = ", ".join(
                        [
                            m["code"] or m["abbrev"] or "pas_de_code"
                            for m in info["is_ins"]
                        ]
                    )
                    H.append(
                        'actuellement inscrit dans <a title="%s" class="discretelink">%d modules</a>'
                        % (dm, len(info["is_ins"]))
                    )
                    if info["ue_status"]["is_capitalized"]:
                        H.append(
                            """<div><em style="font-size: 70%">UE actuelle moins bonne que l'UE capitalisée</em></div>"""
                        )
                    else:
                        H.append(
                            """<div><em style="font-size: 70%">UE actuelle meilleure que l'UE capitalisée</em></div>"""
                        )
                    if can_change:
                        H.append(
                            '<div><a class="stdlink" href="etud_desinscrit_ue?etudid=%s&formsemestre_id=%s&ue_id=%s">désinscrire des modules de cette UE</a></div>'
                            % (etud["etudid"], formsemestre_id, ue["ue_id"])
                        )
                else:
                    H.append("(non réinscrit dans cette UE)")
                    if can_change:
                        H.append(
                            '<div><a class="stdlink" href="etud_inscrit_ue?etudid=%s&formsemestre_id=%s&ue_id=%s">inscrire à tous les modules de cette UE</a></div>'
                            % (etud["etudid"], formsemestre_id, ue["ue_id"])
                        )
                H.append("</li>")
            H.append("</ul></li>")
        H.append("</ul>")

        H.append(
            """<hr/><p class="help">Cette page décrit les inscriptions actuelles. 
        Vous pouvez changer (si vous en avez le droit) les inscrits dans chaque module en 
        cliquant sur la ligne du module.</p>
        <p  class="help">Note: la déinscription d'un module ne perd pas les notes. Ainsi, si 
        l'étudiant est ensuite réinscrit au même module, il retrouvera ses notes.</p>
        """
        )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def descr_inscrs_module(
    sem, moduleimpl_id, set_all, partitions, partitions_etud_groups
):
    """returns tous_inscrits, nb_inscrits, descr"""
    ins = sco_moduleimpl.do_moduleimpl_inscription_list(moduleimpl_id=moduleimpl_id)
    set_m = set([x["etudid"] for x in ins])  # ens. des inscrits au module
    non_inscrits = set_all - set_m
    if len(non_inscrits) == 0:
        return True, len(ins), ""  # tous inscrits
    if len(non_inscrits) <= 7:  # seuil arbitraire
        return False, len(ins), "tous sauf " + _fmt_etud_set(non_inscrits)
    # Cherche les groupes:
    gr = []  #  [ ( partition_name , [ group_names ] ) ]
    for partition in partitions:
        grp = []  # groupe de cette partition
        for group in sco_groups.get_partition_groups(partition):
            members = sco_groups.get_group_members(group["group_id"])
            set_g = set([m["etudid"] for m in members])
            if set_g.issubset(set_m):
                grp.append(group["group_name"])
                set_m = set_m - set_g
        gr.append((partition["partition_name"], grp))
    #
    d = []
    for (partition_name, grp) in gr:
        if grp:
            d.append("groupes de %s: %s" % (partition_name, ", ".join(grp)))
    r = []
    if d:
        r.append(", ".join(d))
    if set_m:
        r.append(_fmt_etud_set(set_m))
    #
    return False, len(ins), " et ".join(r)


def _fmt_etud_set(ins, max_list_size=7):
    # max_list_size est le nombre max de noms d'etudiants listés
    # au delà, on indique juste le nombre, sans les noms.
    if len(ins) > max_list_size:
        return "%d étudiants" % len(ins)
    etuds = []
    for etudid in ins:
        etuds.append(sco_etud.get_etud_info(etudid=etudid, filled=True)[0])
    etuds.sort(key=itemgetter("nom"))
    return ", ".join(
        [
            '<a class="discretelink" href="%s">%s</a>'
            % (
                url_for(
                    "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
                ),
                etud["nomprenom"],
            )
            for etud in etuds
        ]
    )


def get_etuds_with_capitalized_ue(formsemestre_id):
    """For each UE, computes list of students capitalizing the UE.
    returns { ue_id : [ { infos } ] }
    """
    UECaps = scu.DictDefault(defaultvalue=[])
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_ues, get_etud_ue_status
    inscrits = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id}
    )
    ues = nt.get_ues()
    for ue in ues:
        for etud in inscrits:
            status = nt.get_etud_ue_status(etud["etudid"], ue["ue_id"])
            if status["was_capitalized"]:
                UECaps[ue["ue_id"]].append(
                    {
                        "etudid": etud["etudid"],
                        "ue_status": status,
                        "is_ins": is_inscrit_ue(
                            etud["etudid"], formsemestre_id, ue["ue_id"]
                        ),
                    }
                )
    return UECaps


def is_inscrit_ue(etudid, formsemestre_id, ue_id):
    """Modules de cette UE dans ce semestre
    auxquels l'étudiant est inscrit.
    """
    r = ndb.SimpleDictFetch(
        """SELECT mod.id AS module_id, mod.*
    FROM notes_moduleimpl mi, notes_modules mod,
         notes_formsemestre sem, notes_moduleimpl_inscription i
    WHERE sem.id = %(formsemestre_id)s
    AND mi.formsemestre_id = sem.id
    AND mod.id = mi.module_id
    AND mod.ue_id = %(ue_id)s
    AND i.moduleimpl_id = mi.id
    AND i.etudid = %(etudid)s
    ORDER BY mod.numero
    """,
        {"etudid": etudid, "formsemestre_id": formsemestre_id, "ue_id": ue_id},
    )
    return r


def do_etud_desinscrit_ue(etudid, formsemestre_id, ue_id):
    """Desincrit l'etudiant de tous les modules de cette UE dans ce semestre."""
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """DELETE FROM notes_moduleimpl_inscription
    WHERE id IN (
      SELECT i.id FROM
        notes_moduleimpl mi, notes_modules mod,
        notes_formsemestre sem, notes_moduleimpl_inscription i
      WHERE sem.id = %(formsemestre_id)s
      AND mi.formsemestre_id = sem.id
      AND mod.id = mi.module_id
      AND mod.ue_id = %(ue_id)s
      AND i.moduleimpl_id = mi.id
      AND i.etudid = %(etudid)s
    )
    """,
        {"etudid": etudid, "formsemestre_id": formsemestre_id, "ue_id": ue_id},
    )
    logdb(
        cnx,
        method="etud_desinscrit_ue",
        etudid=etudid,
        msg="desinscription UE %s" % ue_id,
        commit=False,
    )
    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > desinscription etudiant des modules


def do_etud_inscrit_ue(etudid, formsemestre_id, ue_id):
    """Incrit l'etudiant de tous les modules de cette UE dans ce semestre."""
    # Verifie qu'il est bien inscrit au semestre
    insem = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id, "etudid": etudid}
    )
    if not insem:
        raise ScoValueError("%s n'est pas inscrit au semestre !" % etudid)

    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT mi.moduleimpl_id 
      FROM notes_moduleimpl mi, notes_modules mod, notes_formsemestre sem
      WHERE sem.formsemestre_id = %(formsemestre_id)s
      AND mi.formsemestre_id = sem.formsemestre_id
      AND mod.module_id = mi.module_id
      AND mod.ue_id = %(ue_id)s
     """,
        {"formsemestre_id": formsemestre_id, "ue_id": ue_id},
    )
    res = cursor.dictfetchall()
    for moduleimpl_id in [x["moduleimpl_id"] for x in res]:
        sco_moduleimpl.do_moduleimpl_inscription_create(
            {"moduleimpl_id": moduleimpl_id, "etudid": etudid},
            formsemestre_id=formsemestre_id,
        )
