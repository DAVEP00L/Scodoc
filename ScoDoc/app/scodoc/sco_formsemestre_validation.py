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

"""Semestres: validation semestre et UE dans parcours
"""
import time

import flask
from flask import url_for, g, request

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.scolog import logdb
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message
from app.scodoc.sco_exceptions import ScoValueError

from app.scodoc.sco_codes_parcours import *
from app.scodoc import html_sco_header
from app.scodoc import sco_abs
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_edit_ue
from app.scodoc import sco_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_edit
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_photos
from app.scodoc import sco_preferences
from app.scodoc import sco_pvjury

# ------------------------------------------------------------------------------------
def formsemestre_validation_etud_form(
    formsemestre_id=None,  # required
    etudid=None,  # one of etudid or etud_index is required
    etud_index=None,
    check=0,  # opt: si true, propose juste une relecture du parcours
    desturl=None,
    sortcol=None,
    readonly=True,
):
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_table_moyennes_triees, get_etud_decision_sem
    T = nt.get_table_moyennes_triees()
    if not etudid and etud_index is None:
        raise ValueError("formsemestre_validation_etud_form: missing argument etudid")
    if etud_index is not None:
        etud_index = int(etud_index)
        # cherche l'etudid correspondant
        if etud_index < 0 or etud_index >= len(T):
            raise ValueError(
                "formsemestre_validation_etud_form: invalid etud_index value"
            )
        etudid = T[etud_index][-1]
    else:
        # cherche index pour liens navigation
        etud_index = len(T) - 1
        while etud_index >= 0 and T[etud_index][-1] != etudid:
            etud_index -= 1
        if etud_index < 0:
            raise ValueError(
                "formsemestre_validation_etud_form: can't retreive etud_index !"
            )
    # prev, next pour liens navigation
    etud_index_next = etud_index + 1
    if etud_index_next >= len(T):
        etud_index_next = None
    etud_index_prev = etud_index - 1
    if etud_index_prev < 0:
        etud_index_prev = None
    if readonly:
        check = True

    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
    if not Se.sem["etat"]:
        raise ScoValueError("validation: semestre verrouille")

    H = [
        html_sco_header.sco_header(
            page_title="Parcours %(nomprenom)s" % etud,
            javascripts=["js/recap_parcours.js"],
        )
    ]

    Footer = ["<p>"]
    # Navigation suivant/precedent
    if etud_index_prev != None:
        etud_p = sco_etud.get_etud_info(etudid=T[etud_index_prev][-1], filled=True)[0]
        Footer.append(
            '<span><a href="formsemestre_validation_etud_form?formsemestre_id=%s&etud_index=%s">Etud. précédent (%s)</a></span>'
            % (formsemestre_id, etud_index_prev, etud_p["nomprenom"])
        )
    if etud_index_next != None:
        etud_n = sco_etud.get_etud_info(etudid=T[etud_index_next][-1], filled=True)[0]
        Footer.append(
            '<span style="padding-left: 50px;"><a href="formsemestre_validation_etud_form?formsemestre_id=%s&etud_index=%s">Etud. suivant (%s)</a></span>'
            % (formsemestre_id, etud_index_next, etud_n["nomprenom"])
        )
    Footer.append("</p>")
    Footer.append(html_sco_header.sco_footer())

    H.append('<table style="width: 100%"><tr><td>')
    if not check:
        H.append(
            '<h2 class="formsemestre">%s: validation %s%s</h2>Parcours: %s'
            % (
                etud["nomprenom"],
                Se.parcours.SESSION_NAME_A,
                Se.parcours.SESSION_NAME,
                Se.get_parcours_descr(),
            )
        )
    else:
        H.append(
            '<h2 class="formsemestre">Parcours de %s</h2>%s'
            % (etud["nomprenom"], Se.get_parcours_descr())
        )

    H.append(
        '</td><td style="text-align: right;"><a href="%s">%s</a></td></tr></table>'
        % (
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            sco_photos.etud_photo_html(etud, title="fiche de %s" % etud["nom"]),
        )
    )

    etud_etat = nt.get_etud_etat(etudid)
    if etud_etat == "D":
        H.append('<div class="ue_warning"><span>Etudiant démissionnaire</span></div>')
    if etud_etat == DEF:
        H.append('<div class="ue_warning"><span>Etudiant défaillant</span></div>')
    if etud_etat != "I":
        H.append(
            tf_error_message(
                f"""Impossible de statuer sur cet étudiant:
                il est démissionnaire ou défaillant (voir <a href="{
                    url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
                }">sa fiche</a>)
                """
            )
        )
        return "\n".join(H + Footer)

    H.append(
        formsemestre_recap_parcours_table(
            Se, etudid, with_links=(check and not readonly)
        )
    )
    if check:
        if not desturl:
            desturl = url_for(
                "notes.formsemestre_recapcomplet",
                scodoc_dept=g.scodoc_dept,
                modejury=1,
                hidemodules=1,
                hidebac=1,
                pref_override=0,
                formsemestre_id=formsemestre_id,
                sortcol=sortcol
                or None,  # pour refaire tri sorttable du tableau de notes
                _anchor="etudid%s" % etudid,  # va a la bonne ligne
            )
        H.append(f'<ul><li><a href="{desturl}">Continuer</a></li></ul>')

        return "\n".join(H + Footer)

    decision_jury = Se.nt.get_etud_decision_sem(etudid)

    # Bloque si note en attente
    if nt.etud_has_notes_attente(etudid):
        H.append(
            tf_error_message(
                f"""Impossible de statuer sur cet étudiant: il a des notes en
                attente dans des évaluations de ce semestre (voir <a href="{
                    url_for( "notes.formsemestre_status",
                    scodoc_dept=g.scodoc_dept, formsemestre_id=formsemestre_id)
                }">tableau de bord</a>)
                """
            )
        )
        return "\n".join(H + Footer)

    # Infos si pas de semestre précédent
    if not Se.prev:
        if Se.sem["semestre_id"] == 1:
            H.append("<p>Premier semestre (pas de précédent)</p>")
        else:
            H.append("<p>Pas de semestre précédent !</p>")
    else:
        if not Se.prev_decision:
            H.append(
                tf_error_message(
                    f"""Le jury n'a pas statué sur le semestre précédent ! (<a href="{
                    url_for("notes.formsemestre_validation_etud_form",
                        scodoc_dept=g.scodoc_dept,
                        formsemestre_id=Se.prev["formsemestre_id"],
                        etudid=etudid)
                    }">le faire maintenant</a>)
                    """
                )
            )
            if decision_jury:
                H.append(
                    f"""<a href="{
                    url_for("notes.formsemestre_validation_suppress_etud",
                        scodoc_dept=g.scodoc_dept,
                        etudid=etudid, formsemestre_id=formsemestre_id
                    )
                    }" class="stdlink">Supprimer décision existante</a>
                    """
                )
            H.append(html_sco_header.sco_footer())
            return "\n".join(H)

    # Infos sur decisions déjà saisies
    if decision_jury:
        if decision_jury["assidu"]:
            ass = "assidu"
        else:
            ass = "non assidu"
        H.append("<p>Décision existante du %(event_date)s: %(code)s" % decision_jury)
        H.append(" (%s)" % ass)
        auts = sco_parcours_dut.formsemestre_get_autorisation_inscription(
            etudid, formsemestre_id
        )
        if auts:
            H.append(". Autorisé%s à s'inscrire en " % etud["ne"])
            alist = []
            for aut in auts:
                alist.append(str(aut["semestre_id"]))
            H.append(", ".join(["S%s" % x for x in alist]) + ".")
        H.append("</p>")

    # Cas particulier pour ATJ: corriger precedent avant de continuer
    if Se.prev_decision and Se.prev_decision["code"] == ATJ:
        H.append(
            """<div class="sfv_warning"><p>La décision du semestre précédent est en
        <b>attente</b> à cause d\'un <b>problème d\'assiduité<b>.</p>
        <p>Vous devez la corriger avant de continuer ce jury. Soit vous considérez que le
        problème d'assiduité n'est pas réglé et choisissez de ne pas valider le semestre
        précédent (échec), soit vous entrez une décision sans prendre en compte
        l'assiduité.</p>
        <form method="get" action="formsemestre_validation_etud_form">
        <input type="submit" value="Statuer sur le semestre précédent"/>
        <input type="hidden" name="formsemestre_id" value="%s"/>
        <input type="hidden" name="etudid" value="%s"/>
        <input type="hidden" name="desturl" value="formsemestre_validation_etud_form?etudid=%s&formsemestre_id=%s"/>
        """
            % (Se.prev["formsemestre_id"], etudid, etudid, formsemestre_id)
        )
        if sortcol:
            H.append('<input type="hidden" name="sortcol" value="%s"/>' % sortcol)
        H.append("</form></div>")

        H.append(html_sco_header.sco_footer())
        return "\n".join(H)

    # Explication sur barres actuelles
    H.append('<p class="sfv_explication">L\'étudiant ')
    if Se.barre_moy_ok:
        H.append("a la moyenne générale, ")
    else:
        H.append("<b>n'a pas</b> la moyenne générale, ")

    H.append(Se.barres_ue_diag)  # eg 'les UEs sont au dessus des barres'

    if (not Se.barre_moy_ok) and Se.can_compensate_with_prev:
        H.append(", et ce semestre peut se <b>compenser</b> avec le précédent")
    H.append(".</p>")

    # Décisions possibles
    rows_assidu = decisions_possible_rows(
        Se, True, subtitle="Etudiant assidu:", trclass="sfv_ass"
    )
    rows_non_assidu = decisions_possible_rows(
        Se, False, subtitle="Si problème d'assiduité:", trclass="sfv_pbass"
    )
    # s'il y a des decisions recommandees issues des regles:
    if rows_assidu or rows_non_assidu:
        H.append(
            """<form method="get" action="formsemestre_validation_etud" id="formvalid" class="sfv_decisions">
        <input type="hidden" name="etudid" value="%s"/>
        <input type="hidden" name="formsemestre_id" value="%s"/>"""
            % (etudid, formsemestre_id)
        )
        if desturl:
            H.append('<input type="hidden" name="desturl" value="%s"/>' % desturl)
        if sortcol:
            H.append('<input type="hidden" name="sortcol" value="%s"/>' % sortcol)

        H.append('<h3 class="sfv">Décisions <em>recommandées</em> :</h3>')
        H.append("<table>")
        H.append(rows_assidu)
        if rows_non_assidu:
            H.append("<tr><td>&nbsp;</td></tr>")  # spacer
            H.append(rows_non_assidu)

        H.append("</table>")
        H.append(
            '<p><br/></p><input type="submit" value="Valider ce choix" disabled="1" id="subut"/>'
        )
        H.append("</form>")

    H.append(form_decision_manuelle(Se, formsemestre_id, etudid))

    H.append(
        f"""<div class="link_defaillance">Ou <a class="stdlink" href="{
            url_for("scolar.formDef", scodoc_dept=g.scodoc_dept, etudid=etudid, 
                    formsemestre_id=formsemestre_id)
            }">déclarer l'étudiant comme défaillant dans ce semestre</a></div>"""
    )

    H.append('<p style="font-size: 50%;">Formation ')
    if Se.sem["gestion_semestrielle"]:
        H.append("avec semestres décalés</p>")
    else:
        H.append("sans semestres décalés</p>")

    return "".join(H + Footer)


def formsemestre_validation_etud(
    formsemestre_id=None,  # required
    etudid=None,  # required
    codechoice=None,  # required
    desturl="",
    sortcol=None,
):
    """Enregistre validation"""
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
    # retrouve la decision correspondant au code:
    choices = Se.get_possible_choices(assiduite=True)
    choices += Se.get_possible_choices(assiduite=False)
    selected_choice = None
    for choice in choices:
        if choice.codechoice == codechoice:
            selected_choice = choice
            break
    if not selected_choice:
        raise ValueError("code choix invalide ! (%s)" % codechoice)
    #
    Se.valide_decision(selected_choice)  # enregistre
    return _redirect_valid_choice(
        formsemestre_id, etudid, Se, selected_choice, desturl, sortcol
    )


def formsemestre_validation_etud_manu(
    formsemestre_id=None,  # required
    etudid=None,  # required
    code_etat="",
    new_code_prev="",
    devenir="",  # required (la decision manuelle)
    assidu=False,
    desturl="",
    sortcol=None,
    redirect=True,
):
    """Enregistre validation"""
    if assidu:
        assidu = True
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
    if code_etat in Se.parcours.UNUSED_CODES:
        raise ScoValueError("code decision invalide dans ce parcours")
    # Si code ADC, extrait le semestre utilisé:
    if code_etat[:3] == ADC:
        formsemestre_id_utilise_pour_compenser = code_etat.split("_")[1]
        if not formsemestre_id_utilise_pour_compenser:
            formsemestre_id_utilise_pour_compenser = (
                None  # compense avec semestre hors ScoDoc
            )
        code_etat = ADC
    else:
        formsemestre_id_utilise_pour_compenser = None

    # Construit le choix correspondant:
    choice = sco_parcours_dut.DecisionSem(
        code_etat=code_etat,
        new_code_prev=new_code_prev,
        devenir=devenir,
        assiduite=assidu,
        formsemestre_id_utilise_pour_compenser=formsemestre_id_utilise_pour_compenser,
    )
    #
    Se.valide_decision(choice)  # enregistre
    if redirect:
        return _redirect_valid_choice(
            formsemestre_id, etudid, Se, choice, desturl, sortcol
        )


def _redirect_valid_choice(formsemestre_id, etudid, Se, choice, desturl, sortcol):
    adr = "formsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s&check=1" % (
        formsemestre_id,
        etudid,
    )
    if sortcol:
        adr += "&sortcol=" + str(sortcol)
    # if desturl:
    #    desturl += "&desturl=" + desturl
    return flask.redirect(adr)
    # Si le precedent a été modifié, demande relecture du parcours.
    # sinon  renvoie au listing general,


#     if choice.new_code_prev:
#         flask.redirect( 'formsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s&check=1&desturl=%s' % (formsemestre_id, etudid, desturl) )
#     else:
#         if not desturl:
#             desturl = 'formsemestre_recapcomplet?modejury=1&hidemodules=1&formsemestre_id=' + str(formsemestre_id)
#         flask.redirect(desturl)


def _dispcode(c):
    if not c:
        return ""
    return c


def decisions_possible_rows(Se, assiduite, subtitle="", trclass=""):
    "Liste HTML des decisions possibles"
    choices = Se.get_possible_choices(assiduite=assiduite)
    if not choices:
        return ""
    TitlePrev = ""
    if Se.prev:
        if Se.prev["semestre_id"] >= 0:
            TitlePrev = "%s%d" % (Se.parcours.SESSION_ABBRV, Se.prev["semestre_id"])
        else:
            TitlePrev = "Prec."

    if Se.sem["semestre_id"] >= 0:
        TitleCur = "%s%d" % (Se.parcours.SESSION_ABBRV, Se.sem["semestre_id"])
    else:
        TitleCur = Se.parcours.SESSION_NAME

    H = [
        '<tr class="%s titles"><th class="sfv_subtitle">%s</em></th>'
        % (trclass, subtitle)
    ]
    if Se.prev:
        H.append("<th>Code %s</th>" % TitlePrev)
    H.append("<th>Code %s</th><th>Devenir</th></tr>" % TitleCur)
    for ch in choices:
        H.append(
            """<tr class="%s"><td title="règle %s"><input type="radio" name="codechoice" value="%s" onClick="document.getElementById('subut').disabled=false;">"""
            % (trclass, ch.rule_id, ch.codechoice)
        )
        H.append("%s </input></td>" % ch.explication)
        if Se.prev:
            H.append('<td class="centercell">%s</td>' % _dispcode(ch.new_code_prev))
        H.append(
            '<td class="centercell">%s</td><td>%s</td>'
            % (_dispcode(ch.code_etat), Se.explique_devenir(ch.devenir))
        )
        H.append("</tr>")

    return "\n".join(H)


def formsemestre_recap_parcours_table(
    Se,
    etudid,
    with_links=False,
    with_all_columns=True,
    a_url="",
    sem_info=None,
    show_details=False,
):
    """Tableau HTML recap parcours
    Si with_links, ajoute liens pour modifier decisions (colonne de droite)
    sem_info = { formsemestre_id : txt } permet d'ajouter des informations associées à chaque semestre
    with_all_columns: si faux, pas de colonne "assiduité".
    """
    sem_info = sem_info or {}
    H = []
    linktmpl = '<span onclick="toggle_vis(this);" class="toggle_sem sem_%%s">%s</span>'
    minuslink = linktmpl % scu.icontag("minus_img", border="0", alt="-")
    pluslink = linktmpl % scu.icontag("plus_img", border="0", alt="+")
    if show_details:
        sd = " recap_show_details"
        plusminus = minuslink
    else:
        sd = " recap_hide_details"
        plusminus = pluslink
    H.append('<table class="recap_parcours%s"><tr>' % sd)
    H.append(
        '<th><span onclick="toggle_all_sems(this);" title="Ouvrir/fermer tous les semestres">%s</span></th><th></th><th>Semestre</th>'
        % scu.icontag("plus18_img", width=18, height=18, border=0, title="", alt="+")
    )
    H.append("<th>Etat</th><th>Abs</th>")
    # titres des UE
    H.append("<th></th>" * Se.nb_max_ue)
    #
    if with_links:
        H.append("<th></th>")
    H.append("<th></th></tr>")
    num_sem = 0

    for sem in Se.get_semestres():
        is_prev = Se.prev and (Se.prev["formsemestre_id"] == sem["formsemestre_id"])
        is_cur = Se.formsemestre_id == sem["formsemestre_id"]
        num_sem += 1

        dpv = sco_pvjury.dict_pvjury(sem["formsemestre_id"], etudids=[etudid])
        pv = dpv["decisions"][0]
        decision_sem = pv["decision_sem"]
        decisions_ue = pv["decisions_ue"]
        if with_all_columns and decision_sem and not decision_sem["assidu"]:
            ass = " (non ass.)"
        else:
            ass = ""

        nt = sco_cache.NotesTableCache.get(
            sem["formsemestre_id"]
        )  # > get_ues, get_etud_moy_gen, get_etud_ue_status
        if is_cur:
            type_sem = "*"  # now unused
            class_sem = "sem_courant"
        elif is_prev:
            type_sem = "p"
            class_sem = "sem_precedent"
        else:
            type_sem = ""
            class_sem = "sem_autre"
        if sem["formation_code"] != Se.formation["formation_code"]:
            class_sem += " sem_autre_formation"
        if sem["bul_bgcolor"]:
            bgcolor = sem["bul_bgcolor"]
        else:
            bgcolor = "background-color: rgb(255,255,240)"
        # 1ere ligne: titre sem, decision, acronymes UE
        H.append('<tr class="%s rcp_l1 sem_%s">' % (class_sem, sem["formsemestre_id"]))
        if is_cur:
            pm = ""
        elif is_prev:
            pm = minuslink % sem["formsemestre_id"]
        else:
            pm = plusminus % sem["formsemestre_id"]

        H.append(
            '<td class="rcp_type_sem" style="background-color:%s;">%s%s</td>'
            % (bgcolor, num_sem, pm)
        )
        H.append('<td class="datedebut">%(mois_debut)s</td>' % sem)
        H.append(
            '<td class="rcp_titre_sem"><a class="formsemestre_status_link" href="%sformsemestre_bulletinetud?formsemestre_id=%s&etudid=%s" title="Bulletin de notes">%s</a></td>'
            % (a_url, sem["formsemestre_id"], etudid, sem["titreannee"])
        )
        if decision_sem:
            H.append('<td class="rcp_dec">%s</td>' % decision_sem["code"])
        else:
            H.append('<td colspan="%d"><em>en cours</em></td>')
        H.append('<td class="rcp_nonass">%s</td>' % ass)  # abs
        # acronymes UEs
        ues = nt.get_ues(filter_sport=True, filter_non_inscrit=True, etudid=etudid)
        for ue in ues:
            H.append('<td class="ue_acro"><span>%s</span></td>' % ue["acronyme"])
        if len(ues) < Se.nb_max_ue:
            H.append('<td colspan="%d"></td>' % (Se.nb_max_ue - len(ues)))
        # indique le semestre compensé par celui ci:
        if decision_sem and decision_sem["compense_formsemestre_id"]:
            csem = sco_formsemestre.get_formsemestre(
                decision_sem["compense_formsemestre_id"]
            )
            H.append("<td><em>compense S%s</em></td>" % csem["semestre_id"])
        else:
            H.append("<td></td>")
        if with_links:
            H.append("<td></td>")
        H.append("</tr>")
        # 2eme ligne: notes
        H.append('<tr class="%s rcp_l2 sem_%s">' % (class_sem, sem["formsemestre_id"]))
        H.append(
            '<td class="rcp_type_sem" style="background-color:%s;">&nbsp;</td>'
            % (bgcolor)
        )
        if is_prev:
            default_sem_info = '<span class="fontred">[sem. précédent]</span>'
        else:
            default_sem_info = ""
        if not sem["etat"]:  # locked
            lockicon = scu.icontag("lock32_img", title="verrouillé", border="0")
            default_sem_info += lockicon
        if sem["formation_code"] != Se.formation["formation_code"]:
            default_sem_info += "Autre formation: %s" % sem["formation_code"]
        H.append(
            '<td class="datefin">%s</td><td class="sem_info">%s</td>'
            % (sem["mois_fin"], sem_info.get(sem["formsemestre_id"], default_sem_info))
        )
        # Moy Gen (sous le code decision)
        H.append(
            '<td class="rcp_moy">%s</td>' % scu.fmt_note(nt.get_etud_moy_gen(etudid))
        )
        # Absences (nb d'abs non just. dans ce semestre)
        nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
        H.append('<td class="rcp_abs">%d</td>' % (nbabs - nbabsjust))

        # UEs
        for ue in ues:
            if decisions_ue and ue["ue_id"] in decisions_ue:
                code = decisions_ue[ue["ue_id"]]["code"]
            else:
                code = ""
            ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
            moy_ue = ue_status["moy"]
            explanation_ue = []  # list of strings
            if code == ADM:
                class_ue = "ue_adm"
            elif code == CMP:
                class_ue = "ue_cmp"
            else:
                class_ue = "ue"
            if ue_status["is_external"]:  # validation externe
                explanation_ue.append("UE externe.")
                # log('x'*12+' EXTERNAL %s' % notes_table.fmt_note(moy_ue)) XXXXXXX
                # log('UE=%s' % pprint.pformat(ue))
                # log('explanation_ue=%s\n'%explanation_ue)
            if ue_status["is_capitalized"]:
                class_ue += " ue_capitalized"
                explanation_ue.append(
                    "Capitalisée le %s." % (ue_status["event_date"] or "?")
                )
                # log('x'*12+' CAPITALIZED %s' % notes_table.fmt_note(moy_ue))
                # log('UE=%s' % pprint.pformat(ue))
                # log('UE_STATUS=%s'  % pprint.pformat(ue_status)) XXXXXX
                # log('')

            H.append(
                '<td class="%s" title="%s">%s</td>'
                % (class_ue, " ".join(explanation_ue), scu.fmt_note(moy_ue))
            )
        if len(ues) < Se.nb_max_ue:
            H.append('<td colspan="%d"></td>' % (Se.nb_max_ue - len(ues)))

        H.append("<td></td>")
        if with_links:
            H.append(
                '<td><a href="%sformsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s">modifier</a></td>'
                % (a_url, sem["formsemestre_id"], etudid)
            )

        H.append("</tr>")
        # 3eme ligne: ECTS
        if (
            sco_preferences.get_preference("bul_show_ects", sem["formsemestre_id"])
            or nt.parcours.ECTS_ONLY
        ):
            etud_moy_infos = nt.get_etud_moy_infos(etudid)
            H.append(
                '<tr class="%s rcp_l2 sem_%s">' % (class_sem, sem["formsemestre_id"])
            )
            H.append(
                '<td class="rcp_type_sem" style="background-color:%s;">&nbsp;</td><td></td>'
                % (bgcolor)
            )
            # total ECTS (affiché sous la moyenne générale)
            H.append(
                '<td class="sem_ects_tit"><a title="crédit potentiels (dont nb de fondamentaux)">ECTS:</a></td><td class="sem_ects">%g <span class="ects_fond">%g</span></td>'
                % (etud_moy_infos["ects_pot"], etud_moy_infos["ects_pot_fond"])
            )
            H.append('<td class="rcp_abs"></td>')
            # ECTS validables dans chaque UE
            for ue in ues:
                ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
                H.append(
                    '<td class="ue">%g <span class="ects_fond">%g</span></td>'
                    % (ue_status["ects_pot"], ue_status["ects_pot_fond"])
                )
            H.append("<td></td></tr>")

    H.append("</table>")
    return "\n".join(H)


def form_decision_manuelle(Se, formsemestre_id, etudid, desturl="", sortcol=None):
    """Formulaire pour saisie décision manuelle"""
    H = [
        """
    <script type="text/javascript">
    function IsEmpty(aTextField) {
    if ((aTextField.value.length==0) || (aTextField.value==null)) {
        return true;
     } else { return false; }
    }
    function check_sfv_form() {
    if (IsEmpty(document.forms.formvalidmanu.code_etat)) {
       alert('Choisir un code semestre !');
       return false;
    }
    return true;
    }
    </script>
    
    <form method="get" action="formsemestre_validation_etud_manu" name="formvalidmanu" id="formvalidmanu" class="sfv_decisions sfv_decisions_manuelles" onsubmit="return check_sfv_form()">
    <input type="hidden" name="etudid" value="%s"/>
    <input type="hidden" name="formsemestre_id" value="%s"/>
    """
        % (etudid, formsemestre_id)
    ]
    if desturl:
        H.append('<input type="hidden" name="desturl" value="%s"/>' % desturl)
    if sortcol:
        H.append('<input type="hidden" name="sortcol" value="%s"/>' % sortcol)

    H.append(
        '<h3 class="sfv">Décisions manuelles : <em>(vérifiez bien votre choix !)</em></h3><table>'
    )

    # Choix code semestre:
    codes = list(sco_codes_parcours.CODES_EXPL.keys())
    codes.sort()  # fortuitement, cet ordre convient bien !

    H.append(
        '<tr><td>Code semestre: </td><td><select name="code_etat"><option value="" selected>Choisir...</option>'
    )
    for cod in codes:
        if cod in Se.parcours.UNUSED_CODES:
            continue
        if cod != ADC:
            H.append(
                '<option value="%s">%s (code %s)</option>'
                % (cod, sco_codes_parcours.CODES_EXPL[cod], cod)
            )
        elif Se.sem["gestion_compensation"]:
            # traitement spécial pour ADC (compensation)
            # ne propose que les semestres avec lesquels on peut compenser
            # le code transmis est ADC_formsemestre_id
            # on propose aussi une compensation sans utiliser de semestre, pour les cas ou le semestre
            # précédent n'est pas géré dans ScoDoc (code ADC_)
            # log(str(Se.sems))
            for sem in Se.sems:
                if sem["can_compensate"]:
                    H.append(
                        '<option value="%s_%s">Admis par compensation avec S%s (%s)</option>'
                        % (
                            cod,
                            sem["formsemestre_id"],
                            sem["semestre_id"],
                            sem["date_debut"],
                        )
                    )
            if Se.could_be_compensated():
                H.append(
                    '<option value="ADC_">Admis par compensation (avec un semestre hors ScoDoc)</option>'
                )
    H.append("</select></td></tr>")

    # Choix code semestre precedent:
    if Se.prev:
        H.append(
            '<tr><td>Code semestre précédent: </td><td><select name="new_code_prev"><option value="">Choisir une décision...</option>'
        )
        for cod in codes:
            if cod == ADC:  # ne propose pas ce choix
                continue
            if Se.prev_decision and cod == Se.prev_decision["code"]:
                sel = "selected"
            else:
                sel = ""
            H.append(
                '<option value="%s" %s>%s (code %s)</option>'
                % (cod, sel, sco_codes_parcours.CODES_EXPL[cod], cod)
            )
        H.append("</select></td></tr>")

    # Choix code devenir
    codes = list(sco_codes_parcours.DEVENIR_EXPL.keys())
    codes.sort()  # fortuitement, cet ordre convient aussi bien !

    if Se.sem["semestre_id"] == -1:
        allowed_codes = sco_codes_parcours.DEVENIRS_MONO
    else:
        allowed_codes = set(sco_codes_parcours.DEVENIRS_STD)
        # semestres decales ?
        if Se.sem["gestion_semestrielle"]:
            allowed_codes = allowed_codes.union(sco_codes_parcours.DEVENIRS_DEC)
        # n'autorise les codes NEXT2 que si semestres décalés et s'il ne manque qu'un semestre avant le n+2
        if Se.can_jump_to_next2():
            allowed_codes = allowed_codes.union(sco_codes_parcours.DEVENIRS_NEXT2)

    H.append(
        '<tr><td>Devenir: </td><td><select name="devenir"><option value="" selected>Choisir...</option>'
    )
    for cod in codes:
        if cod in allowed_codes:  # or Se.sem['gestion_semestrielle'] == '1'
            H.append('<option value="%s">%s</option>' % (cod, Se.explique_devenir(cod)))
    H.append("</select></td></tr>")

    H.append(
        '<tr><td><input type="checkbox" name="assidu" checked="checked">assidu</input></td></tr>'
    )

    H.append(
        """</table>
    <input type="submit" name="formvalidmanu_submit" value="Valider décision manuelle"/>
    <span style="padding-left: 5em;"><a href="formsemestre_validation_suppress_etud?etudid=%s&formsemestre_id=%s" class="stdlink">Supprimer décision existante</a></span>
    </form>
    """
        % (etudid, formsemestre_id)
    )
    return "\n".join(H)


# -----------
def formsemestre_validation_auto(formsemestre_id):
    "Formulaire saisie automatisee des decisions d'un semestre"
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    H = [
        html_sco_header.html_sem_header(
            "Saisie automatique des décisions du semestre", sem
        ),
        """
    <ul>
    <li>Seuls les étudiants qui obtiennent le semestre seront affectés (code ADM, moyenne générale et
    toutes les barres, semestre précédent validé);</li>
    <li>le semestre précédent, s'il y en a un, doit avoir été validé;</li>
    <li>les décisions du semestre précédent ne seront pas modifiées;</li>
    <li>l'assiduité n'est <b>pas</b> prise en compte;</li>
    <li>les étudiants avec des notes en attente sont ignorés.</li>
    </ul>
    <p>Il est donc vivement conseillé de relire soigneusement les décisions à l'issue
    de cette procédure !</p>
    <form action="do_formsemestre_validation_auto">
    <input type="hidden" name="formsemestre_id" value="%s"/>
    <input type="submit" value="Calculer automatiquement ces décisions"/>
    <p><em>Le calcul prend quelques minutes, soyez patients !</em></p>
    </form>
    """
        % formsemestre_id,
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def do_formsemestre_validation_auto(formsemestre_id):
    "Saisie automatisee des decisions d'un semestre"
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    next_semestre_id = sem["semestre_id"] + 1
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etudids, get_etud_decision_sem,
    etudids = nt.get_etudids()
    nb_valid = 0
    conflicts = []  # liste des etudiants avec decision differente déjà saisie
    for etudid in etudids:
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
        ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            {"etudid": etudid, "formsemestre_id": formsemestre_id}
        )[0]

        # Conditions pour validation automatique:
        if ins["etat"] == "I" and (
            (
                (not Se.prev)
                or (Se.prev_decision and Se.prev_decision["code"] in (ADM, ADC, ADJ))
            )
            and Se.barre_moy_ok
            and Se.barres_ue_ok
            and not nt.etud_has_notes_attente(etudid)
        ):
            # check: s'il existe une decision ou autorisation et qu'elles sont differentes,
            # warning (et ne fait rien)
            decision_sem = nt.get_etud_decision_sem(etudid)
            ok = True
            if decision_sem and decision_sem["code"] != ADM:
                ok = False
                conflicts.append(etud)
            autorisations = sco_parcours_dut.formsemestre_get_autorisation_inscription(
                etudid, formsemestre_id
            )
            if (
                len(autorisations) != 0
            ):  # accepte le cas ou il n'y a pas d'autorisation : BUG 23/6/7, A RETIRER ENSUITE
                if (
                    len(autorisations) != 1
                    or autorisations[0]["semestre_id"] != next_semestre_id
                ):
                    if ok:
                        conflicts.append(etud)
                        ok = False

            # ok, valide !
            if ok:
                formsemestre_validation_etud_manu(
                    formsemestre_id,
                    etudid,
                    code_etat=ADM,
                    devenir="NEXT",
                    assidu=True,
                    redirect=False,
                )
                nb_valid += 1
    log(
        "do_formsemestre_validation_auto: %d validations, %d conflicts"
        % (nb_valid, len(conflicts))
    )
    H = [html_sco_header.sco_header(page_title="Saisie automatique")]
    H.append(
        """<h2>Saisie automatique des décisions du semestre %s</h2>
    <p>Opération effectuée.</p>
    <p>%d étudiants validés (sur %s)</p>"""
        % (sem["titreannee"], nb_valid, len(etudids))
    )
    if conflicts:
        H.append(
            """<p><b>Attention:</b> %d étudiants non modifiés car décisions différentes
        déja saisies :<ul>"""
            % len(conflicts)
        )
        for etud in conflicts:
            H.append(
                '<li><a href="formsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s&check=1">%s</li>'
                % (formsemestre_id, etud["etudid"], etud["nomprenom"])
            )
        H.append("</ul>")
    H.append(
        '<a href="formsemestre_recapcomplet?formsemestre_id=%s&modejury=1&hidemodules=1&hidebac=1&pref_override=0">continuer</a>'
        % formsemestre_id
    )
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def formsemestre_validation_suppress_etud(formsemestre_id, etudid):
    """Suppression des decisions de jury pour un etudiant."""
    log("formsemestre_validation_suppress_etud( %s, %s)" % (formsemestre_id, etudid))
    cnx = ndb.GetDBConnexion(autocommit=False)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    args = {"formsemestre_id": formsemestre_id, "etudid": etudid}
    try:
        # -- Validation du semestre et des UEs
        cursor.execute(
            """delete from scolar_formsemestre_validation
        where etudid = %(etudid)s and formsemestre_id=%(formsemestre_id)s""",
            args,
        )
        # -- Autorisations d'inscription
        cursor.execute(
            """delete from scolar_autorisation_inscription
        where etudid = %(etudid)s and origin_formsemestre_id=%(formsemestre_id)s""",
            args,
        )
        cnx.commit()
    except:
        cnx.rollback()
        raise

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    _invalidate_etud_formation_caches(
        etudid, sem["formation_id"]
    )  # > suppr. decision jury (peut affecter de plusieurs semestres utilisant UE capitalisée)


def formsemestre_validate_previous_ue(formsemestre_id, etudid):
    """Form. saisie UE validée hors ScoDoc
    (pour étudiants arrivant avec un UE antérieurement validée).
    """
    from app.scodoc import sco_formations

    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    Fo = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]

    H = [
        html_sco_header.sco_header(
            page_title="Validation UE",
            javascripts=["js/validate_previous_ue.js"],
        ),
        '<table style="width: 100%"><tr><td>',
        """<h2 class="formsemestre">%s: validation d'une UE antérieure</h2>"""
        % etud["nomprenom"],
        (
            '</td><td style="text-align: right;"><a href="%s">%s</a></td></tr></table>'
            % (
                url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
                sco_photos.etud_photo_html(etud, title="fiche de %s" % etud["nom"]),
            )
        ),
        """<p class="help">Utiliser cette page pour enregistrer une UE validée antérieurement, 
    <em>dans un semestre hors ScoDoc</em>.</p>
    <p><b>Les UE validées dans ScoDoc sont déjà
    automatiquement prises en compte</b>. Cette page n'est utile que pour les étudiants ayant 
    suivi un début de cursus dans <b>un autre établissement</b>, ou bien dans un semestre géré <b>sans 
    ScoDoc</b> et qui <b>redouble</b> ce semestre (<em>ne pas utiliser pour les semestres précédents !</em>). 
    </p>
    <p>Notez que l'UE est validée, avec enregistrement immédiat de la décision et 
    l'attribution des ECTS.</p>""",
        "<p>On ne peut prendre en compte ici que les UE du cursus <b>%(titre)s</b></p>"
        % Fo,
    ]

    # Toutes les UE de cette formation sont présentées (même celles des autres semestres)
    ues = sco_edit_ue.ue_list({"formation_id": Fo["formation_id"]})
    ue_names = ["Choisir..."] + ["%(acronyme)s %(titre)s" % ue for ue in ues]
    ue_ids = [""] + [ue["ue_id"] for ue in ues]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("etudid", {"input_type": "hidden"}),
            ("formsemestre_id", {"input_type": "hidden"}),
            (
                "ue_id",
                {
                    "input_type": "menu",
                    "title": "Unité d'Enseignement (UE)",
                    "allow_null": False,
                    "allowed_values": ue_ids,
                    "labels": ue_names,
                },
            ),
            (
                "semestre_id",
                {
                    "input_type": "menu",
                    "title": "Indice du semestre",
                    "explanation": "Facultatif: indice du semestre dans la formation",
                    "allow_null": True,
                    "allowed_values": [""] + [str(x) for x in range(11)],
                    "labels": ["-"] + list(range(11)),
                },
            ),
            (
                "date",
                {
                    "input_type": "date",
                    "size": 9,
                    "explanation": "j/m/a",
                    "default": time.strftime("%d/%m/%Y"),
                },
            ),
            (
                "moy_ue",
                {
                    "type": "float",
                    "allow_null": False,
                    "min_value": 0,
                    "max_value": 20,
                    "title": "Moyenne (/20) obtenue dans cette UE:",
                },
            ),
        ),
        cancelbutton="Annuler",
        submitlabel="Enregistrer validation d'UE",
    )
    if tf[0] == 0:
        X = """
           <div id="ue_list_etud_validations"><!-- filled by get_etud_ue_cap_html --></div>
           <div id="ue_list_code"><!-- filled by ue_sharing_code --></div>
        """
        warn, ue_multiples = check_formation_ues(Fo["formation_id"])
        return "\n".join(H) + tf[1] + X + warn + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(
            scu.NotesURL()
            + "/formsemestre_status?formsemestre_id="
            + str(formsemestre_id)
        )
    else:
        if tf[2]["semestre_id"]:
            semestre_id = int(tf[2]["semestre_id"])
        else:
            semestre_id = None
        do_formsemestre_validate_previous_ue(
            formsemestre_id,
            etudid,
            tf[2]["ue_id"],
            tf[2]["moy_ue"],
            tf[2]["date"],
            semestre_id=semestre_id,
        )
        return flask.redirect(
            scu.ScoURL()
            + "/Notes/formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s&head_message=Validation%%20d'UE%%20enregistree"
            % (formsemestre_id, etudid)
        )


def do_formsemestre_validate_previous_ue(
    formsemestre_id,
    etudid,
    ue_id,
    moy_ue,
    date,
    code=ADM,
    semestre_id=None,
    ue_coefficient=None,
):
    """Enregistre (ou modifie) validation d'UE (obtenue hors ScoDoc).
    Si le coefficient est spécifié, modifie le coefficient de
    cette UE (utile seulement pour les semestres extérieurs).
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    cnx = ndb.GetDBConnexion(autocommit=False)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etud_ue_status
    if ue_coefficient != None:
        sco_formsemestre.do_formsemestre_uecoef_edit_or_create(
            cnx, formsemestre_id, ue_id, ue_coefficient
        )
    else:
        sco_formsemestre.do_formsemestre_uecoef_delete(cnx, formsemestre_id, ue_id)
    sco_parcours_dut.do_formsemestre_validate_ue(
        cnx,
        nt,
        formsemestre_id,  # "importe" cette UE dans le semestre (new 3/2015)
        etudid,
        ue_id,
        code,
        moy_ue=moy_ue,
        date=date,
        semestre_id=semestre_id,
        is_external=True,
    )

    logdb(
        cnx,
        method="formsemestre_validate_previous_ue",
        etudid=etudid,
        msg="Validation UE %s" % ue_id,
        commit=False,
    )
    _invalidate_etud_formation_caches(etudid, sem["formation_id"])
    cnx.commit()


def _invalidate_etud_formation_caches(etudid, formation_id):
    "Invalide tous les semestres de cette formation où l'etudiant est inscrit..."
    r = ndb.SimpleDictFetch(
        """SELECT sem.id
        FROM notes_formsemestre sem, notes_formsemestre_inscription i
        WHERE sem.formation_id = %(formation_id)s
        AND i.formsemestre_id = sem.id
        AND i.etudid = %(etudid)s
        """,
        {"etudid": etudid, "formation_id": formation_id},
    )
    for fsid in [s["id"] for s in r]:
        sco_cache.invalidate_formsemestre(
            formsemestre_id=fsid
        )  # > modif decision UE (inval tous semestres avec cet etudiant, ok mais conservatif)


def get_etud_ue_cap_html(etudid, formsemestre_id, ue_id):
    """Ramene bout de HTML pour pouvoir supprimer une validation de cette UE"""
    valids = ndb.SimpleDictFetch(
        """SELECT SFV.* 
        FROM scolar_formsemestre_validation SFV
        WHERE ue_id=%(ue_id)s 
        AND etudid=%(etudid)s""",
        {"etudid": etudid, "ue_id": ue_id},
    )
    if not valids:
        return ""
    H = [
        '<div class="existing_valids"><span>Validations existantes pour cette UE:</span><ul>'
    ]
    for valid in valids:
        valid["event_date"] = ndb.DateISOtoDMY(valid["event_date"])
        if valid["moy_ue"] != None:
            valid["m"] = ", moyenne %(moy_ue)g/20" % valid
        else:
            valid["m"] = ""
        if valid["formsemestre_id"]:
            sem = sco_formsemestre.get_formsemestre(valid["formsemestre_id"])
            valid["s"] = ", du semestre %s" % sem["titreannee"]
        else:
            valid["s"] = " enregistrée d'un parcours antérieur (hors ScoDoc)"
        if valid["semestre_id"]:
            valid["s"] += " (<b>S%d</b>)" % valid["semestre_id"]
        valid["ds"] = formsemestre_id
        H.append(
            '<li>%(code)s%(m)s%(s)s, le %(event_date)s  <a class="stdlink" href="etud_ue_suppress_validation?etudid=%(etudid)s&ue_id=%(ue_id)s&formsemestre_id=%(ds)s" title="supprime cette validation">effacer</a></li>'
            % valid
        )
    H.append("</ul></div>")
    return "\n".join(H)


def etud_ue_suppress_validation(etudid, formsemestre_id, ue_id):
    """Suppress a validation (ue_id, etudid) and redirect to formsemestre"""
    log("etud_ue_suppress_validation( %s, %s, %s)" % (etudid, formsemestre_id, ue_id))
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        "DELETE FROM scolar_formsemestre_validation WHERE etudid=%(etudid)s and ue_id=%(ue_id)s",
        {"etudid": etudid, "ue_id": ue_id},
    )

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    _invalidate_etud_formation_caches(etudid, sem["formation_id"])

    return flask.redirect(
        scu.NotesURL()
        + "/formsemestre_validate_previous_ue?etudid=%s&formsemestre_id=%s"
        % (etudid, formsemestre_id)
    )


def check_formation_ues(formation_id):
    """Verifie que les UE d'une formation sont chacune utilisée dans un seul semestre_id
    Si ce n'est pas le cas, c'est probablement (mais pas forcément) une erreur de
    définition du programme: cette fonction retourne un bout de HTML
    à afficher pour prévenir l'utilisateur, ou '' si tout est ok.
    """
    ues = sco_edit_ue.ue_list({"formation_id": formation_id})
    ue_multiples = {}  # { ue_id : [ liste des formsemestre ] }
    for ue in ues:
        # formsemestres utilisant cette ue ?
        sems = ndb.SimpleDictFetch(
            """SELECT DISTINCT sem.id AS formsemestre_id, sem.* 
             FROM notes_formsemestre sem, notes_modules mod, notes_moduleimpl mi
             WHERE sem.formation_id = %(formation_id)s
             AND mod.id = mi.module_id
             AND mi.formsemestre_id = sem.id
             AND mod.ue_id = %(ue_id)s
             """,
            {"ue_id": ue["ue_id"], "formation_id": formation_id},
        )
        semestre_ids = set([x["semestre_id"] for x in sems])
        if (
            len(semestre_ids) > 1
        ):  # plusieurs semestres d'indices differents dans le cursus
            ue_multiples[ue["ue_id"]] = sems

    if not ue_multiples:
        return "", {}
    # Genere message HTML:
    H = [
        """<div class="ue_warning"><span>Attention:</span> les UE suivantes de cette formation 
        sont utilisées dans des
        semestres de rangs différents (eg S1 et S3). <br/>Cela peut engendrer des problèmes pour 
        la capitalisation des UE. Il serait préférable d'essayer de rectifier cette situation: 
        soit modifier le programme de la formation (définir des UE dans chaque semestre), 
        soit veiller à saisir le bon indice de semestre dans le menu lors de la validation d'une
        UE extérieure.
        <ul>
        """
    ]
    for ue in ues:
        if ue["ue_id"] in ue_multiples:
            sems = [
                sco_formsemestre.get_formsemestre(x["formsemestre_id"])
                for x in ue_multiples[ue["ue_id"]]
            ]
            slist = ", ".join(
                ["%(titreannee)s (<em>semestre %(semestre_id)s</em>)" % s for s in sems]
            )
            H.append("<li><b>%s</b> : %s</li>" % (ue["acronyme"], slist))
    H.append("</ul></div>")

    return "\n".join(H), ue_multiples
