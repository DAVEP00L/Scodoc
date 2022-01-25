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

"""Opérations d'inscriptions aux semestres et modules
"""
import time

import flask
from flask import url_for, g, request

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.scolog import logdb
from app.scodoc.sco_exceptions import ScoException, ScoValueError
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_codes_parcours import UE_STANDARD, UE_SPORT, UE_TYPE_NAME
import app.scodoc.notesdb as ndb
from app.scodoc.TrivialFormulator import TrivialFormulator, TF
from app.scodoc import sco_find_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_groups
from app.scodoc import sco_etud
from app.scodoc import sco_cache
from app.scodoc import html_sco_header


# --- Gestion des inscriptions aux semestres
_formsemestre_inscriptionEditor = ndb.EditableTable(
    "notes_formsemestre_inscription",
    "formsemestre_inscription_id",
    ("formsemestre_inscription_id", "etudid", "formsemestre_id", "etat", "etape"),
    sortkey="formsemestre_id",
    insert_ignore_conflicts=True,
)


def do_formsemestre_inscription_list(*args, **kw):
    "list formsemestre_inscriptions"
    cnx = ndb.GetDBConnexion()
    return _formsemestre_inscriptionEditor.list(cnx, *args, **kw)


def do_formsemestre_inscription_listinscrits(formsemestre_id):
    """Liste les inscrits (état I) à ce semestre et cache le résultat"""
    r = sco_cache.SemInscriptionsCache.get(formsemestre_id)
    if r is None:
        # retreive list
        r = do_formsemestre_inscription_list(
            args={"formsemestre_id": formsemestre_id, "etat": "I"}
        )
        sco_cache.SemInscriptionsCache.set(formsemestre_id, r)
    return r


def do_formsemestre_inscription_create(args, method=None):
    "create a formsemestre_inscription (and sco event)"
    cnx = ndb.GetDBConnexion()
    log("do_formsemestre_inscription_create: args=%s" % str(args))
    sems = sco_formsemestre.do_formsemestre_list(
        {"formsemestre_id": args["formsemestre_id"]}
    )
    if len(sems) != 1:
        raise ScoValueError("code de semestre invalide: %s" % args["formsemestre_id"])
    sem = sems[0]
    # check lock
    if not sem["etat"]:
        raise ScoValueError("inscription: semestre verrouille")
    #
    r = _formsemestre_inscriptionEditor.create(cnx, args)
    # Evenement
    sco_etud.scolar_events_create(
        cnx,
        args={
            "etudid": args["etudid"],
            "event_date": time.strftime("%d/%m/%Y"),
            "formsemestre_id": args["formsemestre_id"],
            "event_type": "INSCRIPTION",
        },
    )
    # Log etudiant
    logdb(
        cnx,
        method=method,
        etudid=args["etudid"],
        msg="inscription en semestre %s" % args["formsemestre_id"],
        commit=False,
    )
    #
    sco_cache.invalidate_formsemestre(
        formsemestre_id=args["formsemestre_id"]
    )  # > inscription au semestre
    return r


def do_formsemestre_inscription_delete(oid, formsemestre_id=None):
    "delete formsemestre_inscription"
    cnx = ndb.GetDBConnexion()
    _formsemestre_inscriptionEditor.delete(cnx, oid)

    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > desinscription du semestre


def do_formsemestre_demission(
    etudid,
    formsemestre_id,
    event_date=None,
    etat_new="D",  # 'D' or DEF
    operation_method="demEtudiant",
    event_type="DEMISSION",
):
    "Démission ou défaillance d'un étudiant"
    # marque 'D' ou DEF dans l'inscription au semestre et ajoute
    # un "evenement" scolarite
    cnx = ndb.GetDBConnexion()
    # check lock
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        raise ScoValueError("Modification impossible: semestre verrouille")
    #
    ins = do_formsemestre_inscription_list(
        {"etudid": etudid, "formsemestre_id": formsemestre_id}
    )[0]
    if not ins:
        raise ScoException("etudiant non inscrit ?!")
    ins["etat"] = etat_new
    do_formsemestre_inscription_edit(args=ins, formsemestre_id=formsemestre_id)
    logdb(cnx, method=operation_method, etudid=etudid)
    sco_etud.scolar_events_create(
        cnx,
        args={
            "etudid": etudid,
            "event_date": event_date,
            "formsemestre_id": formsemestre_id,
            "event_type": event_type,
        },
    )


def do_formsemestre_inscription_edit(args=None, formsemestre_id=None):
    "edit a formsemestre_inscription"
    cnx = ndb.GetDBConnexion()
    _formsemestre_inscriptionEditor.edit(cnx, args)
    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > modif inscription semestre (demission ?)


def do_formsemestre_desinscription(etudid, formsemestre_id):
    """Désinscription d'un étudiant.
    Si semestre extérieur et dernier inscrit, suppression de ce semestre.
    """
    from app.scodoc import sco_formsemestre_edit

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # -- check lock
    if not sem["etat"]:
        raise ScoValueError("desinscription impossible: semestre verrouille")

    # -- Si decisions de jury, desinscription interdite
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    if nt.etud_has_decision(etudid):
        raise ScoValueError(
            "desinscription impossible: l'étudiant a une décision de jury (la supprimer avant si nécessaire)"
        )

    insem = do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id, "etudid": etudid}
    )
    if not insem:
        raise ScoValueError("%s n'est pas inscrit au semestre !" % etudid)
    insem = insem[0]
    # -- desinscription de tous les modules
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT Im.id AS moduleimpl_inscription_id 
        FROM notes_moduleimpl_inscription Im, notes_moduleimpl M  
        WHERE Im.etudid=%(etudid)s 
        and Im.moduleimpl_id = M.id 
        and M.formsemestre_id = %(formsemestre_id)s
        """,
        {"etudid": etudid, "formsemestre_id": formsemestre_id},
    )
    res = cursor.fetchall()
    moduleimpl_inscription_ids = [x[0] for x in res]
    for moduleimpl_inscription_id in moduleimpl_inscription_ids:
        sco_moduleimpl.do_moduleimpl_inscription_delete(
            moduleimpl_inscription_id, formsemestre_id=formsemestre_id
        )
    # -- desincription du semestre
    do_formsemestre_inscription_delete(
        insem["formsemestre_inscription_id"], formsemestre_id=formsemestre_id
    )
    # --- Semestre extérieur
    if sem["modalite"] == "EXT":
        inscrits = do_formsemestre_inscription_list(
            args={"formsemestre_id": formsemestre_id}
        )
        nbinscrits = len(inscrits)
        if nbinscrits == 0:
            log(
                "do_formsemestre_desinscription: suppression du semestre extérieur %s"
                % formsemestre_id
            )
            sco_formsemestre_edit.do_formsemestre_delete(formsemestre_id)

    logdb(
        cnx,
        method="formsemestre_desinscription",
        etudid=etudid,
        msg="desinscription semestre %s" % formsemestre_id,
        commit=False,
    )


def do_formsemestre_inscription_with_modules(
    formsemestre_id,
    etudid,
    group_ids=[],
    etat="I",
    etape=None,
    method="inscription_with_modules",
):
    """Inscrit cet etudiant à ce semestre et TOUS ses modules STANDARDS
    (donc sauf le sport)
    """
    # inscription au semestre
    args = {"formsemestre_id": formsemestre_id, "etudid": etudid}
    if etat is not None:
        args["etat"] = etat
    do_formsemestre_inscription_create(args, method=method)
    log(
        "do_formsemestre_inscription_with_modules: etudid=%s formsemestre_id=%s"
        % (etudid, formsemestre_id)
    )
    # inscriptions aux groupes
    # 1- inscrit au groupe 'tous'
    group_id = sco_groups.get_default_group(formsemestre_id)
    sco_groups.set_group(etudid, group_id)
    gdone = {group_id: 1}  # empeche doublons

    # 2- inscrit aux groupes
    for group_id in group_ids:
        if group_id and not group_id in gdone:
            sco_groups.set_group(etudid, group_id)
            gdone[group_id] = 1

    # inscription a tous les modules de ce semestre
    modimpls = sco_moduleimpl.moduleimpl_withmodule_list(
        formsemestre_id=formsemestre_id
    )
    for mod in modimpls:
        if mod["ue"]["type"] != UE_SPORT:
            sco_moduleimpl.do_moduleimpl_inscription_create(
                {"moduleimpl_id": mod["moduleimpl_id"], "etudid": etudid},
                formsemestre_id=formsemestre_id,
            )


def formsemestre_inscription_with_modules_etud(
    formsemestre_id, etudid=None, group_ids=None
):
    """Form. inscription d'un étudiant au semestre.
    Si etudid n'est pas specifié, form. choix etudiant.
    """
    if etudid is None:
        return sco_find_etud.form_search_etud(
            title="Choix de l'étudiant à inscrire dans ce semestre",
            add_headers=True,
            dest_url="notes.formsemestre_inscription_with_modules_etud",
            parameters={"formsemestre_id": formsemestre_id},
            parameters_keys="formsemestre_id",
        )

    return formsemestre_inscription_with_modules(
        etudid, formsemestre_id, group_ids=group_ids
    )


def formsemestre_inscription_with_modules_form(etudid, only_ext=False):
    """Formulaire inscription de l'etud dans l'un des semestres existants.
    Si only_ext, ne montre que les semestre extérieurs.
    """
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    H = [
        html_sco_header.sco_header(),
        "<h2>Inscription de %s" % etud["nomprenom"],
    ]
    if only_ext:
        H.append(" dans un semestre extérieur")
    H.append(
        """</h2>
    <p class="help">L'étudiant sera inscrit à <em>tous</em> les modules du semestre 
    choisi (sauf Sport &amp; Culture).
    </p>
    <h3>Choisir un semestre:</h3>"""
    )
    F = html_sco_header.sco_footer()
    sems = sco_formsemestre.do_formsemestre_list(args={"etat": "1"})
    insem = do_formsemestre_inscription_list(args={"etudid": etudid, "etat": "I"})
    if sems:
        H.append("<ul>")
        for sem in sems:
            # Ne propose que les semestres ou etudid n'est pas déjà inscrit
            inscrit = False
            for i in insem:
                if i["formsemestre_id"] == sem["formsemestre_id"]:
                    inscrit = True
            if not inscrit:
                if (not only_ext) or (sem["modalite"] == "EXT"):
                    H.append(
                        """
                    <li><a class="stdlink" href="formsemestre_inscription_with_modules?etudid=%s&formsemestre_id=%s">%s</a>
                    """
                        % (etudid, sem["formsemestre_id"], sem["titremois"])
                    )
        H.append("</ul>")
    else:
        H.append("<p>aucune session de formation !</p>")
    H.append(
        '<h3>ou</h3> <a class="stdlink" href="%s">retour à la fiche de %s</a>'
        % (
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            etud["nomprenom"],
        )
    )
    return "\n".join(H) + F


def formsemestre_inscription_with_modules(
    etudid, formsemestre_id, group_ids=None, multiple_ok=False
):
    """
    Inscription de l'etud dans ce semestre.
    Formulaire avec choix groupe.
    """
    log(
        "formsemestre_inscription_with_modules: etudid=%s formsemestre_id=%s group_ids=%s"
        % (etudid, formsemestre_id, group_ids)
    )
    if multiple_ok:
        multiple_ok = int(multiple_ok)
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    H = [
        html_sco_header.html_sem_header(
            "Inscription de %s dans ce semestre" % etud["nomprenom"],
            sem,
        )
    ]
    F = html_sco_header.sco_footer()
    # Check 1: déjà inscrit ici ?
    ins = do_formsemestre_inscription_list({"etudid": etudid})
    already = False
    for i in ins:
        if i["formsemestre_id"] == formsemestre_id:
            already = True
    if already:
        H.append(
            '<p class="warning">%s est déjà inscrit dans le semestre %s</p>'
            % (etud["nomprenom"], sem["titremois"])
        )
        H.append(
            """<ul>
            <li><a href="%s">retour à la fiche de %s</a></li>
            <li><a href="%s">retour au tableau de bord de %s</a></li>
            </ul>"""
            % (
                url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
                etud["nomprenom"],
                url_for(
                    "notes.formsemestre_status",
                    scodoc_dept=g.scodoc_dept,
                    formsemestre_id=formsemestre_id,
                ),
                sem["titremois"],
            )
        )
        return "\n".join(H) + F
    # Check 2: déjà inscrit dans un semestre recouvrant les même dates ?
    # Informe et propose dé-inscriptions
    others = est_inscrit_ailleurs(etudid, formsemestre_id)
    if others and not multiple_ok:
        l = []
        for s in others:
            l.append(
                '<a class="discretelink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titremois)s</a>'
                % s
            )

        H.append(
            '<p class="warning">Attention: %s est déjà inscrit sur la même période dans: %s.</p>'
            % (etud["nomprenom"], ", ".join(l))
        )
        H.append("<ul>")
        for s in others:
            H.append(
                '<li><a href="formsemestre_desinscription?formsemestre_id=%s&etudid=%s">déinscrire de %s</li>'
                % (s["formsemestre_id"], etudid, s["titreannee"])
            )
        H.append("</ul>")
        H.append(
            """<p><a href="formsemestre_inscription_with_modules?etudid=%s&formsemestre_id=%s&multiple_ok=1&%s">Continuer quand même l'inscription</a></p>"""
            % (etudid, formsemestre_id, sco_groups.make_query_groups(group_ids))
        )
        return "\n".join(H) + F
    #
    if group_ids is not None:
        # OK, inscription
        do_formsemestre_inscription_with_modules(
            formsemestre_id,
            etudid,
            group_ids=group_ids,
            etat="I",
            method="formsemestre_inscription_with_modules",
        )
        return flask.redirect(
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )
    else:
        # formulaire choix groupe
        H.append(
            """<form method="GET" name="groupesel" action="%s">
        <input type="hidden" name="etudid" value="%s">
        <input type="hidden" name="formsemestre_id" value="%s">
        """
            % (request.base_url, etudid, formsemestre_id)
        )

        H.append(sco_groups.form_group_choice(formsemestre_id, allow_none=True))

        #
        H.append(
            """
        <input type="submit" value="Inscrire"/>
        <p>Note: l'étudiant sera inscrit dans les groupes sélectionnés</p>
        </form>
        """
        )
        return "\n".join(H) + F


def formsemestre_inscription_option(etudid, formsemestre_id):
    """Dialogue pour (dés)inscription à des modules optionnels."""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        raise ScoValueError("Modification impossible: semestre verrouille")

    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etud_ue_status

    F = html_sco_header.sco_footer()
    H = [
        html_sco_header.sco_header()
        + "<h2>Inscription de %s aux modules de %s (%s - %s)</h2>"
        % (etud["nomprenom"], sem["titre_num"], sem["date_debut"], sem["date_fin"])
    ]

    # Cherche les moduleimpls et les inscriptions
    mods = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)
    inscr = sco_moduleimpl.do_moduleimpl_inscription_list(etudid=etudid)
    # Formulaire
    modimpls_by_ue_ids = scu.DictDefault(defaultvalue=[])  # ue_id : [ moduleimpl_id ]
    modimpls_by_ue_names = scu.DictDefault(
        defaultvalue=[]
    )  # ue_id : [ moduleimpl_name ]
    ues = []
    ue_ids = set()
    initvalues = {}
    for mod in mods:
        ue_id = mod["ue"]["ue_id"]
        if not ue_id in ue_ids:
            ues.append(mod["ue"])
            ue_ids.add(ue_id)
        modimpls_by_ue_ids[ue_id].append(mod["moduleimpl_id"])

        modimpls_by_ue_names[ue_id].append(
            "%s %s" % (mod["module"]["code"], mod["module"]["titre"])
        )
        vals = scu.get_request_args()
        if not vals.get("tf_submitted", False):
            # inscrit ?
            for ins in inscr:
                if ins["moduleimpl_id"] == mod["moduleimpl_id"]:
                    key = "moduleimpls_%s" % ue_id
                    if key in initvalues:
                        initvalues[key].append(str(mod["moduleimpl_id"]))
                    else:
                        initvalues[key] = [str(mod["moduleimpl_id"])]
                    break

    descr = [
        ("formsemestre_id", {"input_type": "hidden"}),
        ("etudid", {"input_type": "hidden"}),
    ]
    for ue in ues:
        ue_id = ue["ue_id"]
        ue_descr = ue["acronyme"]
        if ue["type"] != UE_STANDARD:
            ue_descr += " <em>%s</em>" % UE_TYPE_NAME[ue["type"]]
        ue_status = nt.get_etud_ue_status(etudid, ue_id)
        if ue_status["is_capitalized"]:
            sem_origin = sco_formsemestre.get_formsemestre(ue_status["formsemestre_id"])
            ue_descr += ' <a class="discretelink" href="formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s" title="%s">(capitalisée le %s)' % (
                sem_origin["formsemestre_id"],
                etudid,
                sem_origin["titreannee"],
                ndb.DateISOtoDMY(ue_status["event_date"]),
            )
        descr.append(
            (
                "sec_%s" % ue_id,
                {
                    "input_type": "separator",
                    "title": """<b>%s :</b>  <a href="#" onclick="chkbx_select('%s', true);">inscrire</a> | <a href="#" onclick="chkbx_select('%s', false);">désinscrire</a> à tous les modules"""
                    % (ue_descr, ue_id, ue_id),
                },
            )
        )
        descr.append(
            (
                "moduleimpls_%s" % ue_id,
                {
                    "input_type": "checkbox",
                    "title": "",
                    "dom_id": ue_id,
                    "allowed_values": [str(x) for x in modimpls_by_ue_ids[ue_id]],
                    "labels": modimpls_by_ue_names[ue_id],
                    "vertical": True,
                },
            )
        )

    H.append(
        """<script type="text/javascript">
function chkbx_select(field_id, state) {
   var elems = document.getElementById(field_id).getElementsByTagName("input");
   for (var i=0; i < elems.length; i++) {
      elems[i].checked=state;
   }
}
    </script>
    """
    )
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        initvalues,
        cancelbutton="Annuler",
        method="post",
        submitlabel="Modifier les inscriptions",
        cssclass="inscription",
        name="tf",
    )
    if tf[0] == 0:
        H.append(
            """<p>Voici la liste des modules du semestre choisi.</p><p>
    Les modules cochés sont ceux dans lesquels l'étudiant est inscrit. Vous pouvez l'inscrire ou le désincrire d'un ou plusieurs modules.</p>
    <p>Attention: cette méthode ne devrait être utilisée que pour les modules <b>optionnels</b> (ou les activités culturelles et sportives) et pour désinscrire les étudiants dispensés (UE validées).</p>
    """
        )
        return "\n".join(H) + "\n" + tf[1] + F
    elif tf[0] == -1:
        return flask.redirect(
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )
    else:
        # Inscriptions aux modules choisis
        # il faut desinscrire des modules qui ne figurent pas
        # et inscrire aux autres, sauf si deja inscrit
        a_desinscrire = {}.fromkeys([x["moduleimpl_id"] for x in mods])
        insdict = {}
        for ins in inscr:
            insdict[ins["moduleimpl_id"]] = ins
        for ue in ues:
            ue_id = ue["ue_id"]
            for moduleimpl_id in [int(x) for x in tf[2]["moduleimpls_%s" % ue_id]]:
                if moduleimpl_id in a_desinscrire:
                    del a_desinscrire[moduleimpl_id]
        # supprime ceux auxquel pas inscrit
        moduleimpls_a_desinscrire = list(a_desinscrire.keys())
        for moduleimpl_id in moduleimpls_a_desinscrire:
            if moduleimpl_id not in insdict:
                del a_desinscrire[moduleimpl_id]

        a_inscrire = set()
        for ue in ues:
            ue_id = ue["ue_id"]
            a_inscrire.update(
                int(x) for x in tf[2]["moduleimpls_%s" % ue_id]
            )  # conversion en int !
        # supprime ceux auquel deja inscrit:
        for ins in inscr:
            if ins["moduleimpl_id"] in a_inscrire:
                a_inscrire.remove(ins["moduleimpl_id"])
        # dict des modules:
        modsdict = {}
        for mod in mods:
            modsdict[mod["moduleimpl_id"]] = mod
        #
        if (not a_inscrire) and (not a_desinscrire):
            H.append(
                """<h3>Aucune modification à effectuer</h3>
            <p><a class="stdlink" href="%s">retour à la fiche étudiant</a></p>
            """
                % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
            )
            return "\n".join(H) + F

        H.append("<h3>Confirmer les modifications:</h3>")
        if a_desinscrire:
            H.append(
                "<p>%s va être <b>désinscrit%s</b> des modules:<ul><li>"
                % (etud["nomprenom"], etud["ne"])
            )
            H.append(
                "</li><li>".join(
                    [
                        "%s (%s)"
                        % (
                            modsdict[x]["module"]["titre"],
                            modsdict[x]["module"]["code"],
                        )
                        for x in a_desinscrire
                    ]
                )
                + "</p>"
            )
            H.append("</li></ul>")
        if a_inscrire:
            H.append(
                "<p>%s va être <b>inscrit%s</b> aux modules:<ul><li>"
                % (etud["nomprenom"], etud["ne"])
            )
            H.append(
                "</li><li>".join(
                    [
                        "%s (%s)"
                        % (
                            modsdict[x]["module"]["titre"],
                            modsdict[x]["module"]["code"],
                        )
                        for x in a_inscrire
                    ]
                )
                + "</p>"
            )
            H.append("</li></ul>")
        modulesimpls_ainscrire = ",".join(str(x) for x in a_inscrire)
        modulesimpls_adesinscrire = ",".join(str(x) for x in a_desinscrire)
        H.append(
            """<form action="do_moduleimpl_incription_options">
        <input type="hidden" name="etudid" value="%s"/>
        <input type="hidden" name="modulesimpls_ainscrire" value="%s"/>
        <input type="hidden" name="modulesimpls_adesinscrire" value="%s"/>
        <input type ="submit" value="Confirmer"/>
        <input type ="button" value="Annuler" onclick="document.location='%s';"/>
        </form>
        """
            % (
                etudid,
                modulesimpls_ainscrire,
                modulesimpls_adesinscrire,
                url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            )
        )
        return "\n".join(H) + F


def do_moduleimpl_incription_options(
    etudid, modulesimpls_ainscrire, modulesimpls_adesinscrire
):
    """
    Effectue l'inscription et la description aux modules optionnels
    """
    if isinstance(modulesimpls_ainscrire, int):
        modulesimpls_ainscrire = str(modulesimpls_ainscrire)
    if isinstance(modulesimpls_adesinscrire, int):
        modulesimpls_adesinscrire = str(modulesimpls_adesinscrire)
    if modulesimpls_ainscrire:
        a_inscrire = [int(x) for x in modulesimpls_ainscrire.split(",")]
    else:
        a_inscrire = []
    if modulesimpls_adesinscrire:
        a_desinscrire = [int(x) for x in modulesimpls_adesinscrire.split(",")]
    else:
        a_desinscrire = []
    # inscriptions
    for moduleimpl_id in a_inscrire:
        # verifie que ce module existe bien
        mods = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)
        if len(mods) != 1:
            raise ScoValueError(
                "inscription: invalid moduleimpl_id: %s" % moduleimpl_id
            )
        mod = mods[0]
        sco_moduleimpl.do_moduleimpl_inscription_create(
            {"moduleimpl_id": moduleimpl_id, "etudid": etudid},
            formsemestre_id=mod["formsemestre_id"],
        )
    # desinscriptions
    for moduleimpl_id in a_desinscrire:
        # verifie que ce module existe bien
        mods = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)
        if len(mods) != 1:
            raise ScoValueError(
                "desinscription: invalid moduleimpl_id: %s" % moduleimpl_id
            )
        mod = mods[0]
        inscr = sco_moduleimpl.do_moduleimpl_inscription_list(
            moduleimpl_id=moduleimpl_id, etudid=etudid
        )
        if not inscr:
            raise ScoValueError(
                "pas inscrit a ce module ! (etudid=%s, moduleimpl_id=%s)"
                % (etudid, moduleimpl_id)
            )
        oid = inscr[0]["moduleimpl_inscription_id"]
        sco_moduleimpl.do_moduleimpl_inscription_delete(
            oid, formsemestre_id=mod["formsemestre_id"]
        )

    H = [
        html_sco_header.sco_header(),
        """<h3>Modifications effectuées</h3>
            <p><a class="stdlink" href="%s">
            Retour à la fiche étudiant</a></p>
        """
        % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def est_inscrit_ailleurs(etudid, formsemestre_id):
    """Vrai si l'étudiant est inscrit dans un semestre en même
    temps que celui indiqué (par formsemestre_id).
    Retourne la liste des semestres concernés (ou liste vide).
    """
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    debut_s = sem["dateord"]
    fin_s = ndb.DateDMYtoISO(sem["date_fin"])
    r = []
    for s in etud["sems"]:
        if s["formsemestre_id"] != formsemestre_id:
            debut = s["dateord"]
            fin = ndb.DateDMYtoISO(s["date_fin"])
            if debut < fin_s and fin > debut_s:
                r.append(s)  # intersection
    return r


def list_inscrits_ailleurs(formsemestre_id):
    """Liste des etudiants inscrits ailleurs en même temps que formsemestre_id.
    Pour chacun, donne la liste des semestres.
    { etudid : [ liste de sems ] }
    """
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etudids
    etudids = nt.get_etudids()
    d = {}
    for etudid in etudids:
        d[etudid] = est_inscrit_ailleurs(etudid, formsemestre_id)
    return d


def formsemestre_inscrits_ailleurs(formsemestre_id):
    """Page listant les étudiants inscrits dans un autre semestre
    dont les dates recouvrent le semestre indiqué.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    H = [
        html_sco_header.html_sem_header(
            "Inscriptions multiples parmi les étudiants du semestre ",
            sem,
        )
    ]
    insd = list_inscrits_ailleurs(formsemestre_id)
    # liste ordonnée par nom
    etudlist = [
        sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        for etudid in insd.keys()
        if insd[etudid]
    ]
    etudlist.sort(key=lambda x: x["nom"])
    if etudlist:
        H.append("<ul>")
        for etud in etudlist:
            H.append(
                '<li><a href="%s" class="discretelink">%s</a> : '
                % (
                    url_for(
                        "scolar.ficheEtud",
                        scodoc_dept=g.scodoc_dept,
                        etudid=etud["etudid"],
                    ),
                    etud["nomprenom"],
                )
            )
            l = []
            for s in insd[etud["etudid"]]:
                l.append(
                    '<a class="discretelink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titremois)s</a>'
                    % s
                )
            H.append(", ".join(l))
            H.append("</li>")
        H.append("</ul>")
        H.append("<p>Total: %d étudiants concernés.</p>" % len(etudlist))
        H.append(
            """<p class="help">Ces étudiants sont inscrits dans le semestre sélectionné et aussi dans d'autres semestres qui se déroulent en même temps ! <br/>Sauf exception, cette situation est anormale:</p>
        <ul>
        <li>vérifier que les dates des semestres se suivent sans se chevaucher</li>
        <li>ou si besoin désinscrire le(s) étudiant(s) de l'un des semestres (via leurs fiches individuelles).</li>
        </ul>
        """
        )
    else:
        H.append("""<p>Aucun étudiant en inscription multiple (c'est normal) !</p>""")
    return "\n".join(H) + html_sco_header.sco_footer()
