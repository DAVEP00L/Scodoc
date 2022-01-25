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

"""Génération des bulletins de notes

"""
from app.models import formsemestre
import time
import pprint
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import Header
from reportlab.lib.colors import Color
import urllib

from flask import g, request
from flask import url_for
from flask_login import current_user
from flask_mail import Message

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_abs
from app.scodoc import sco_abs_views
from app.scodoc import sco_bulletins_generator
from app.scodoc import sco_bulletins_json
from app.scodoc import sco_bulletins_xml
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_etud
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_permissions_check
from app.scodoc import sco_photos
from app.scodoc import sco_preferences
from app.scodoc import sco_pvjury
from app.scodoc import sco_users
from app import email

# ----- CLASSES DE BULLETINS DE NOTES
from app.scodoc import sco_bulletins_standard
from app.scodoc import sco_bulletins_legacy

# import sco_bulletins_example # format exemple (à désactiver en production)

# ... ajouter ici vos modules ...
from app.scodoc import sco_bulletins_ucac  # format expérimental UCAC Cameroun


def make_context_dict(sem, etud):
    """Construit dictionnaire avec valeurs pour substitution des textes
    (preferences bul_pdf_*)
    """
    C = sem.copy()
    C["responsable"] = " ,".join(
        [
            sco_users.user_info(responsable_id)["prenomnom"]
            for responsable_id in sem["responsables"]
        ]
    )

    annee_debut = sem["date_debut"].split("/")[2]
    annee_fin = sem["date_fin"].split("/")[2]
    if annee_debut != annee_fin:
        annee = "%s - %s" % (annee_debut, annee_fin)
    else:
        annee = annee_debut
    C["anneesem"] = annee
    C.update(etud)
    # copie preferences
    # XXX devrait acceder directement à un dict de preferences, à revoir
    for name in sco_preferences.get_base_preferences().prefs_name:
        C[name] = sco_preferences.get_preference(name, sem["formsemestre_id"])

    # ajoute groupes et group_0, group_1, ...
    sco_groups.etud_add_group_infos(etud, sem)
    C["groupes"] = etud["groupes"]
    n = 0
    for partition_id in etud["partitions"]:
        C["group_%d" % n] = etud["partitions"][partition_id]["group_name"]
        n += 1

    # ajoute date courante
    t = time.localtime()
    C["date_dmy"] = time.strftime("%d/%m/%Y", t)
    C["date_iso"] = time.strftime("%Y-%m-%d", t)

    return C


def formsemestre_bulletinetud_dict(formsemestre_id, etudid, version="long"):
    """Collecte informations pour bulletin de notes
    Retourne un dictionnaire (avec valeur par défaut chaine vide).
    Le contenu du dictionnaire dépend des options (rangs, ...)
    et de la version choisie (short, long, selectedevals).

    Cette fonction est utilisée pour les bulletins HTML et PDF, mais pas ceux en XML.
    """
    from app.scodoc import sco_abs

    if not version in scu.BULLETINS_VERSIONS:
        raise ValueError("invalid version code !")

    prefs = sco_preferences.SemPreferences(formsemestre_id)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > toutes notes
    if not nt.get_etud_etat(etudid):
        raise ScoValueError("Etudiant non inscrit à ce semestre")
    I = scu.DictDefault(defaultvalue="")
    I["etudid"] = etudid
    I["formsemestre_id"] = formsemestre_id
    I["sem"] = nt.sem
    I["server_name"] = request.url_root

    # Formation et parcours
    I["formation"] = sco_formations.formation_list(
        args={"formation_id": I["sem"]["formation_id"]}
    )[0]
    I["parcours"] = sco_codes_parcours.get_parcours_from_code(
        I["formation"]["type_parcours"]
    )
    # Infos sur l'etudiant
    I["etud"] = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    I["descr_situation"] = I["etud"]["inscriptionstr"]
    if I["etud"]["inscription_formsemestre_id"]:
        I[
            "descr_situation_html"
        ] = f"""<a href="{url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=I["etud"]["inscription_formsemestre_id"],
            )}">{I["descr_situation"]}</a>"""
    else:
        I["descr_situation_html"] = I["descr_situation"]
    # Groupes:
    partitions = sco_groups.get_partitions_list(formsemestre_id, with_default=False)
    partitions_etud_groups = {}  # { partition_id : { etudid : group } }
    for partition in partitions:
        pid = partition["partition_id"]
        partitions_etud_groups[pid] = sco_groups.get_etud_groups_in_partition(pid)
    # --- Absences
    I["nbabs"], I["nbabsjust"] = sco_abs.get_abs_count(etudid, nt.sem)

    # --- Decision Jury
    infos, dpv = etud_descr_situation_semestre(
        etudid,
        formsemestre_id,
        format="html",
        show_date_inscr=prefs["bul_show_date_inscr"],
        show_decisions=prefs["bul_show_decision"],
        show_uevalid=prefs["bul_show_uevalid"],
        show_mention=prefs["bul_show_mention"],
    )

    if dpv:
        I["decision_sem"] = dpv["decisions"][0]["decision_sem"]
    else:
        I["decision_sem"] = ""
    I.update(infos)

    I["etud_etat_html"] = nt.get_etud_etat_html(etudid)
    I["etud_etat"] = nt.get_etud_etat(etudid)
    I["filigranne"] = ""
    I["demission"] = ""
    if I["etud_etat"] == "D":
        I["demission"] = "(Démission)"
        I["filigranne"] = "Démission"
    elif I["etud_etat"] == sco_codes_parcours.DEF:
        I["demission"] = "(Défaillant)"
        I["filigranne"] = "Défaillant"
    elif (prefs["bul_show_temporary"] and not I["decision_sem"]) or prefs[
        "bul_show_temporary_forced"
    ]:
        I["filigranne"] = prefs["bul_temporary_txt"]

    # --- Appreciations
    cnx = ndb.GetDBConnexion()
    apprecs = sco_etud.appreciations_list(
        cnx, args={"etudid": etudid, "formsemestre_id": formsemestre_id}
    )
    I["appreciations_list"] = apprecs
    I["appreciations_txt"] = [x["date"] + ": " + x["comment"] for x in apprecs]
    I["appreciations"] = I[
        "appreciations_txt"
    ]  # deprecated / keep it for backward compat in templates

    # --- Notes
    ues = nt.get_ues()
    modimpls = nt.get_modimpls()
    moy_gen = nt.get_etud_moy_gen(etudid)
    I["nb_inscrits"] = len(nt.rangs)
    I["moy_gen"] = scu.fmt_note(moy_gen)
    I["moy_min"] = scu.fmt_note(nt.moy_min)
    I["moy_max"] = scu.fmt_note(nt.moy_max)
    I["mention"] = ""
    if dpv:
        decision_sem = dpv["decisions"][0]["decision_sem"]
        if decision_sem and sco_codes_parcours.code_semestre_validant(
            decision_sem["code"]
        ):
            I["mention"] = scu.get_mention(moy_gen)

    if dpv and dpv["decisions"][0]:
        I["sum_ects"] = dpv["decisions"][0]["sum_ects"]
        I["sum_ects_capitalises"] = dpv["decisions"][0]["sum_ects_capitalises"]
    else:
        I["sum_ects"] = 0
        I["sum_ects_capitalises"] = 0
    I["moy_moy"] = scu.fmt_note(nt.moy_moy)  # moyenne des moyennes generales
    if (not isinstance(moy_gen, str)) and (not isinstance(nt.moy_moy, str)):
        I["moy_gen_bargraph_html"] = "&nbsp;" + htmlutils.horizontal_bargraph(
            moy_gen * 5, nt.moy_moy * 5
        )
    else:
        I["moy_gen_bargraph_html"] = ""

    if prefs["bul_show_rangs"]:
        rang = str(nt.get_etud_rang(etudid))
    else:
        rang = ""

    rang_gr, ninscrits_gr, gr_name = get_etud_rangs_groups(
        etudid, formsemestre_id, partitions, partitions_etud_groups, nt
    )

    if nt.get_moduleimpls_attente():
        # n'affiche pas le rang sur le bulletin s'il y a des
        # notes en attente dans ce semestre
        rang = scu.RANG_ATTENTE_STR
        rang_gr = scu.DictDefault(defaultvalue=scu.RANG_ATTENTE_STR)
    I["rang"] = rang
    I["rang_gr"] = rang_gr
    I["gr_name"] = gr_name
    I["ninscrits_gr"] = ninscrits_gr
    I["nbetuds"] = len(nt.rangs)
    I["nb_demissions"] = nt.nb_demissions
    I["nb_defaillants"] = nt.nb_defaillants
    if prefs["bul_show_rangs"]:
        I["rang_nt"] = "%s / %d" % (
            rang,
            I["nbetuds"] - nt.nb_demissions - nt.nb_defaillants,
        )
        I["rang_txt"] = "Rang " + I["rang_nt"]
    else:
        I["rang_nt"], I["rang_txt"] = "", ""
    I["note_max"] = 20.0  # notes toujours sur 20
    I["bonus_sport_culture"] = nt.bonus[etudid]
    # Liste les UE / modules /evals
    I["ues"] = []
    I["matieres_modules"] = {}
    I["matieres_modules_capitalized"] = {}
    for ue in ues:
        u = ue.copy()
        ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
        u["ue_status"] = ue_status  # { 'moy', 'coef_ue', ...}
        if ue["type"] != sco_codes_parcours.UE_SPORT:
            u["cur_moy_ue_txt"] = scu.fmt_note(ue_status["cur_moy_ue"])
        else:
            x = scu.fmt_note(nt.bonus[etudid], keep_numeric=True)
            if isinstance(x, str):
                u["cur_moy_ue_txt"] = "pas de bonus"
            else:
                u["cur_moy_ue_txt"] = "bonus de %.3g points" % x
        u["moy_ue_txt"] = scu.fmt_note(ue_status["moy"])
        if ue_status["coef_ue"] != None:
            u["coef_ue_txt"] = scu.fmt_coef(ue_status["coef_ue"])
        else:
            # C'est un bug:
            log("u=" + pprint.pformat(u))
            raise Exception("invalid None coef for ue")

        if (
            dpv
            and dpv["decisions"][0]["decisions_ue"]
            and ue["ue_id"] in dpv["decisions"][0]["decisions_ue"]
        ):
            u["ects"] = dpv["decisions"][0]["decisions_ue"][ue["ue_id"]]["ects"]
            if ue["type"] == sco_codes_parcours.UE_ELECTIVE:
                u["ects"] = (
                    "%g+" % u["ects"]
                )  # ajoute un "+" pour indiquer ECTS d'une UE élective
        else:
            if ue_status["is_capitalized"]:
                u["ects"] = ue_status["ue"].get("ects", "-")
            else:
                u["ects"] = "-"
        modules, ue_attente = _ue_mod_bulletin(
            etudid, formsemestre_id, ue["ue_id"], modimpls, nt, version
        )
        #
        u["modules"] = modules  # detail des modules de l'UE (dans le semestre courant)
        # auparavant on filtrait les modules sans notes
        #   si ue_status['cur_moy_ue'] != 'NA' alors u['modules'] = [] (pas de moyenne => pas de modules)

        u[
            "modules_capitalized"
        ] = []  # modules de l'UE capitalisée (liste vide si pas capitalisée)
        if ue_status["is_capitalized"]:
            sem_origin = sco_formsemestre.get_formsemestre(ue_status["formsemestre_id"])
            u["ue_descr_txt"] = "Capitalisée le %s" % ndb.DateISOtoDMY(
                ue_status["event_date"]
            )
            u[
                "ue_descr_html"
            ] = '<a href="formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s" title="%s" class="bull_link">%s</a>' % (
                sem_origin["formsemestre_id"],
                etudid,
                sem_origin["titreannee"],
                u["ue_descr_txt"],
            )
            # log('cap details   %s' % ue_status['moy'])
            if ue_status["moy"] != "NA" and ue_status["formsemestre_id"]:
                # detail des modules de l'UE capitalisee
                nt_cap = sco_cache.NotesTableCache.get(
                    ue_status["formsemestre_id"]
                )  # > toutes notes

                u["modules_capitalized"], _ = _ue_mod_bulletin(
                    etudid,
                    formsemestre_id,
                    ue_status["capitalized_ue_id"],
                    nt_cap.get_modimpls(),
                    nt_cap,
                    version,
                )
                I["matieres_modules_capitalized"].update(
                    _sort_mod_by_matiere(u["modules_capitalized"], nt_cap, etudid)
                )
        else:
            if prefs["bul_show_ue_rangs"] and ue["type"] != sco_codes_parcours.UE_SPORT:
                if ue_attente:  # nt.get_moduleimpls_attente():
                    u["ue_descr_txt"] = "%s/%s" % (
                        scu.RANG_ATTENTE_STR,
                        nt.ue_rangs[ue["ue_id"]][1],
                    )
                else:
                    u["ue_descr_txt"] = "%s/%s" % (
                        nt.ue_rangs[ue["ue_id"]][0][etudid],
                        nt.ue_rangs[ue["ue_id"]][1],
                    )
                u["ue_descr_html"] = u["ue_descr_txt"]
            else:
                u["ue_descr_txt"] = u["ue_descr_html"] = ""

        if ue_status["is_capitalized"] or modules:
            I["ues"].append(u)  # ne montre pas les UE si non inscrit

        # Accès par matieres
        I["matieres_modules"].update(_sort_mod_by_matiere(modules, nt, etudid))

    #
    C = make_context_dict(I["sem"], I["etud"])
    C.update(I)
    #
    # log( 'C = \n%s\n' % pprint.pformat(C) ) # tres pratique pour voir toutes les infos dispo
    return C


def _sort_mod_by_matiere(modlist, nt, etudid):
    matmod = {}  # { matiere_id : [] }
    for mod in modlist:
        matiere_id = mod["module"]["matiere_id"]
        if matiere_id not in matmod:
            moy = nt.get_etud_mat_moy(matiere_id, etudid)
            matmod[matiere_id] = {
                "titre": mod["mat"]["titre"],
                "modules": mod,
                "moy": moy,
                "moy_txt": scu.fmt_note(moy),
            }
    return matmod


def _ue_mod_bulletin(etudid, formsemestre_id, ue_id, modimpls, nt, version):
    """Infos sur les modules (et évaluations) dans une UE
    (ajoute les informations aux modimpls)
    Result: liste de modules de l'UE avec les infos dans chacun (seulement ceux où l'étudiant est inscrit).
    """
    bul_show_mod_rangs = sco_preferences.get_preference(
        "bul_show_mod_rangs", formsemestre_id
    )
    bul_show_abs_modules = sco_preferences.get_preference(
        "bul_show_abs_modules", formsemestre_id
    )
    if bul_show_abs_modules:
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        debut_sem = ndb.DateDMYtoISO(sem["date_debut"])
        fin_sem = ndb.DateDMYtoISO(sem["date_fin"])

    ue_modimpls = [mod for mod in modimpls if mod["module"]["ue_id"] == ue_id]
    mods = []  # result
    ue_attente = False  # true si une eval en attente dans cette UE
    for modimpl in ue_modimpls:
        mod_attente = False
        mod = modimpl.copy()
        mod_moy = nt.get_etud_mod_moy(
            modimpl["moduleimpl_id"], etudid
        )  # peut etre 'NI'
        is_malus = mod["module"]["module_type"] == scu.MODULE_MALUS
        if bul_show_abs_modules:
            nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
            mod_abs = [nbabs, nbabsjust]
            mod["mod_abs_txt"] = scu.fmt_abs(mod_abs)
        else:
            mod["mod_abs_txt"] = ""

        mod["mod_moy_txt"] = scu.fmt_note(mod_moy)
        if mod["mod_moy_txt"][:2] == "NA":
            mod["mod_moy_txt"] = "-"
        if is_malus:
            if isinstance(mod_moy, str):
                mod["mod_moy_txt"] = "-"
                mod["mod_coef_txt"] = "-"
            elif mod_moy > 0:
                mod["mod_moy_txt"] = scu.fmt_note(mod_moy)
                mod["mod_coef_txt"] = "Malus"
            elif mod_moy < 0:
                mod["mod_moy_txt"] = scu.fmt_note(-mod_moy)
                mod["mod_coef_txt"] = "Bonus"
            else:
                mod["mod_moy_txt"] = "-"
                mod["mod_coef_txt"] = "-"
        else:
            mod["mod_coef_txt"] = scu.fmt_coef(modimpl["module"]["coefficient"])
        if mod["mod_moy_txt"] != "NI":  # ne montre pas les modules 'non inscrit'
            mods.append(mod)
            if is_malus:  # n'affiche pas les statistiques sur les modules malus
                mod["stats"] = {
                    "moy": "",
                    "max": "",
                    "min": "",
                    "nb_notes": "",
                    "nb_missing": "",
                    "nb_valid_evals": "",
                }
            else:
                mod["stats"] = nt.get_mod_stats(modimpl["moduleimpl_id"])
            mod["mod_descr_txt"] = "Module %s, coef. %s (%s)" % (
                modimpl["module"]["titre"],
                scu.fmt_coef(modimpl["module"]["coefficient"]),
                sco_users.user_info(modimpl["responsable_id"])["nomcomplet"],
            )
            link_mod = (
                '<a class="bull_link" href="moduleimpl_status?moduleimpl_id=%s" title="%s">'
                % (modimpl["moduleimpl_id"], mod["mod_descr_txt"])
            )
            if sco_preferences.get_preference("bul_show_codemodules", formsemestre_id):
                mod["code"] = modimpl["module"]["code"]
                mod["code_html"] = link_mod + mod["code"] + "</a>"
            else:
                mod["code"] = mod["code_html"] = ""
            mod["name"] = (
                modimpl["module"]["abbrev"] or modimpl["module"]["titre"] or ""
            )
            mod["name_html"] = link_mod + mod["name"] + "</a>"

            mod_descr = "Module %s, coef. %s (%s)" % (
                modimpl["module"]["titre"],
                scu.fmt_coef(modimpl["module"]["coefficient"]),
                sco_users.user_info(modimpl["responsable_id"])["nomcomplet"],
            )
            link_mod = (
                '<a class="bull_link" href="moduleimpl_status?moduleimpl_id=%s" title="%s">'
                % (modimpl["moduleimpl_id"], mod_descr)
            )
            if sco_preferences.get_preference("bul_show_codemodules", formsemestre_id):
                mod["code_txt"] = modimpl["module"]["code"]
                mod["code_html"] = link_mod + mod["code_txt"] + "</a>"
            else:
                mod["code_txt"] = ""
                mod["code_html"] = ""
            # Evaluations: notes de chaque eval
            evals = nt.get_evals_in_mod(modimpl["moduleimpl_id"])
            mod["evaluations"] = []
            for e in evals:
                e = e.copy()
                if e["visibulletin"] or version == "long":
                    # affiche "bonus" quand les points de malus sont négatifs
                    if is_malus:
                        val = e["notes"].get(etudid, {"value": "NP"})[
                            "value"
                        ]  # NA si etud demissionnaire
                        if val == "NP" or val > 0:
                            e["name"] = "Points de malus sur cette UE"
                        else:
                            e["name"] = "Points de bonus sur cette UE"
                    else:
                        e["name"] = e["description"] or "le %s" % e["jour"]
                e["target_html"] = (
                    "evaluation_listenotes?evaluation_id=%s&format=html&tf_submitted=1"
                    % e["evaluation_id"]
                )
                e["name_html"] = '<a class="bull_link" href="%s">%s</a>' % (
                    e["target_html"],
                    e["name"],
                )
                val = e["notes"].get(etudid, {"value": "NP"})[
                    "value"
                ]  # NA si etud demissionnaire
                if val == "NP":
                    e["note_txt"] = "nd"
                    e["note_html"] = '<span class="note_nd">nd</span>'
                    e["coef_txt"] = scu.fmt_coef(e["coefficient"])
                else:
                    # (-0.15) s'affiche "bonus de 0.15"
                    if is_malus:
                        val = abs(val)
                    e["note_txt"] = scu.fmt_note(val, note_max=e["note_max"])
                    e["note_html"] = e["note_txt"]
                    if is_malus:
                        e["coef_txt"] = ""
                    else:
                        e["coef_txt"] = scu.fmt_coef(e["coefficient"])
                if e["evaluation_type"] == scu.EVALUATION_RATTRAPAGE:
                    e["coef_txt"] = "rat."
                elif e["evaluation_type"] == scu.EVALUATION_SESSION2:
                    e["coef_txt"] = "sess. 2"
                if e["etat"]["evalattente"]:
                    mod_attente = True  # une eval en attente dans ce module
                if (not is_malus) or (val != "NP"):
                    mod["evaluations"].append(
                        e
                    )  # ne liste pas les eval malus sans notes

            # Evaluations incomplètes ou futures:
            mod["evaluations_incompletes"] = []
            if sco_preferences.get_preference("bul_show_all_evals", formsemestre_id):
                complete_eval_ids = set([e["evaluation_id"] for e in evals])
                all_evals = sco_evaluations.do_evaluation_list(
                    args={"moduleimpl_id": modimpl["moduleimpl_id"]}
                )
                all_evals.reverse()  # plus ancienne d'abord
                for e in all_evals:
                    if e["evaluation_id"] not in complete_eval_ids:
                        e = e.copy()
                        mod["evaluations_incompletes"].append(e)
                        e["name"] = (e["description"] or "") + " (%s)" % e["jour"]
                        e["target_html"] = url_for(
                            "notes.evaluation_listenotes",
                            scodoc_dept=g.scodoc_dept,
                            evaluation_id=e["evaluation_id"],
                            tf_submitted=1,
                            format="html",
                        )
                        e["name_html"] = '<a class="bull_link" href="%s">%s</a>' % (
                            e["target_html"],
                            e["name"],
                        )
                        e["note_txt"] = e["note_html"] = ""
                        e["coef_txt"] = scu.fmt_coef(e["coefficient"])
            # Classement
            if bul_show_mod_rangs and mod["mod_moy_txt"] != "-" and not is_malus:
                rg = nt.mod_rangs[modimpl["moduleimpl_id"]]
                if mod_attente:  # nt.get_moduleimpls_attente():
                    mod["mod_rang"] = scu.RANG_ATTENTE_STR
                else:
                    mod["mod_rang"] = rg[0][etudid]
                mod["mod_eff"] = rg[1]  # effectif dans ce module
                mod["mod_rang_txt"] = "%s/%s" % (mod["mod_rang"], mod["mod_eff"])
            else:
                mod["mod_rang_txt"] = ""
        if mod_attente:
            ue_attente = True
    return mods, ue_attente


def get_etud_rangs_groups(
    etudid, formsemestre_id, partitions, partitions_etud_groups, nt
):
    """Ramene rang et nb inscrits dans chaque partition"""
    rang_gr, ninscrits_gr, gr_name = {}, {}, {}
    for partition in partitions:
        if partition["partition_name"] != None:
            partition_id = partition["partition_id"]

            if etudid in partitions_etud_groups[partition_id]:
                group = partitions_etud_groups[partition_id][etudid]

                (
                    rang_gr[partition_id],
                    ninscrits_gr[partition_id],
                ) = nt.get_etud_rang_group(etudid, group["group_id"])
                gr_name[partition_id] = group["group_name"]
            else:  # etudiant non present dans cette partition
                rang_gr[partition_id], ninscrits_gr[partition_id] = "", ""
                gr_name[partition_id] = ""

    return rang_gr, ninscrits_gr, gr_name


def etud_descr_situation_semestre(
    etudid,
    formsemestre_id,
    ne="",
    format="html",  # currently unused
    show_decisions=True,
    show_uevalid=True,
    show_date_inscr=True,
    show_mention=False,
):
    """Dict décrivant la situation de l'étudiant dans ce semestre.
    Si format == 'html', peut inclure du balisage html (actuellement inutilisé)

    situation : chaine résumant en français la situation de l'étudiant.
                Par ex. "Inscrit le 31/12/1999. Décision jury: Validé. ..."

    date_inscription : (vide si show_date_inscr est faux)
    date_demission   : (vide si pas demission ou si show_date_inscr est faux)
    descr_inscription : "Inscrit" ou "Pas inscrit[e]"
    descr_demission   : "Démission le 01/02/2000" ou vide si pas de démission
    descr_defaillance  : "Défaillant" ou vide si non défaillant.
    decision_jury     :  "Validé", "Ajourné", ... (code semestre)
    descr_decision_jury : "Décision jury: Validé" (une phrase)
    decisions_ue        : noms (acronymes) des UE validées, séparées par des virgules.
    descr_decisions_ue  : ' UE acquises: UE1, UE2', ou vide si pas de dec. ou si pas show_uevalid
    descr_mention : 'Mention Bien', ou vide si pas de mention ou si pas show_mention
    """
    cnx = ndb.GetDBConnexion()
    infos = scu.DictDefault(defaultvalue="")

    # --- Situation et décisions jury

    # demission/inscription ?
    events = sco_etud.scolar_events_list(
        cnx, args={"etudid": etudid, "formsemestre_id": formsemestre_id}
    )
    date_inscr = None
    date_dem = None
    date_def = None
    for event in events:
        event_type = event["event_type"]
        if event_type == "INSCRIPTION":
            if date_inscr:
                # plusieurs inscriptions ???
                # date_inscr += ', ' +   event['event_date'] + ' (!)'
                # il y a eu une erreur qui a laissé un event 'inscription'
                # on l'efface:
                log(
                    "etud_descr_situation_semestre: removing duplicate INSCRIPTION event for etudid=%s !"
                    % etudid
                )
                sco_etud.scolar_events_delete(cnx, event["event_id"])
            else:
                date_inscr = event["event_date"]
        elif event_type == "DEMISSION":
            # assert date_dem == None, 'plusieurs démissions !'
            if date_dem:  # cela ne peut pas arriver sauf bug (signale a Evry 2013?)
                log(
                    "etud_descr_situation_semestre: removing duplicate DEMISSION event for etudid=%s !"
                    % etudid
                )
                sco_etud.scolar_events_delete(cnx, event["event_id"])
            else:
                date_dem = event["event_date"]
        elif event_type == "DEFAILLANCE":
            if date_def:
                log(
                    "etud_descr_situation_semestre: removing duplicate DEFAILLANCE event for etudid=%s !"
                    % etudid
                )
                sco_etud.scolar_events_delete(cnx, event["event_id"])
            else:
                date_def = event["event_date"]
    if show_date_inscr:
        if not date_inscr:
            infos["date_inscription"] = ""
            infos["descr_inscription"] = "Pas inscrit%s." % ne
        else:
            infos["date_inscription"] = date_inscr
            infos["descr_inscription"] = "Inscrit%s le %s." % (ne, date_inscr)
    else:
        infos["date_inscription"] = ""
        infos["descr_inscription"] = ""

    infos["situation"] = infos["descr_inscription"]

    if date_dem:
        infos["descr_demission"] = "Démission le %s." % date_dem
        infos["date_demission"] = date_dem
        infos["descr_decision_jury"] = "Démission"
        infos["situation"] += " " + infos["descr_demission"]
        return infos, None  # ne donne pas les dec. de jury pour les demissionnaires
    if date_def:
        infos["descr_defaillance"] = "Défaillant%s" % ne
        infos["date_defaillance"] = date_def
        infos["descr_decision_jury"] = "Défaillant%s" % ne
        infos["situation"] += " " + infos["descr_defaillance"]

    dpv = sco_pvjury.dict_pvjury(formsemestre_id, etudids=[etudid])

    if not show_decisions:
        return infos, dpv

    # Decisions de jury:
    pv = dpv["decisions"][0]
    dec = ""
    if pv["decision_sem_descr"]:
        infos["decision_jury"] = pv["decision_sem_descr"]
        infos["descr_decision_jury"] = (
            "Décision jury: " + pv["decision_sem_descr"] + ". "
        )
        dec = infos["descr_decision_jury"]
    else:
        infos["descr_decision_jury"] = ""

    if pv["decisions_ue_descr"] and show_uevalid:
        infos["decisions_ue"] = pv["decisions_ue_descr"]
        infos["descr_decisions_ue"] = " UE acquises: " + pv["decisions_ue_descr"] + ". "
        dec += infos["descr_decisions_ue"]
    else:
        # infos['decisions_ue'] = None
        infos["descr_decisions_ue"] = ""

    infos["mention"] = pv["mention"]
    if pv["mention"] and show_mention:
        dec += "Mention " + pv["mention"] + ". "

    infos["situation"] += " " + dec
    if not pv["validation_parcours"]:  # parcours non terminé
        if pv["autorisations_descr"]:
            infos["situation"] += (
                " Autorisé à s'inscrire en %s." % pv["autorisations_descr"]
            )
    else:
        infos["situation"] += " Diplôme obtenu."
    return infos, dpv


# ------ Page bulletin
def formsemestre_bulletinetud(
    etudid=None,
    formsemestre_id=None,
    format="html",
    version="long",
    xml_with_decisions=False,
    force_publishing=False,  # force publication meme si semestre non publie sur "portail"
    prefer_mail_perso=False,
):
    "page bulletin de notes"
    try:
        etud = sco_etud.get_etud_info(filled=True)[0]
        etudid = etud["etudid"]
    except:
        sco_etud.log_unknown_etud()
        raise ScoValueError("étudiant inconnu")
    # API, donc erreurs admises en ScoValueError
    sem = sco_formsemestre.get_formsemestre(formsemestre_id, raise_soft_exc=True)

    bulletin = do_formsemestre_bulletinetud(
        formsemestre_id,
        etudid,
        format=format,
        version=version,
        xml_with_decisions=xml_with_decisions,
        force_publishing=force_publishing,
        prefer_mail_perso=prefer_mail_perso,
    )[0]
    if format not in {"html", "pdfmail"}:
        filename = scu.bul_filename(sem, etud, format)
        return scu.send_file(bulletin, filename, mime=scu.get_mime_suffix(format)[0])

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    H = [
        _formsemestre_bulletinetud_header_html(
            etud, etudid, sem, formsemestre_id, format, version
        ),
        bulletin,
    ]

    H.append("""<p>Situation actuelle: """)
    if etud["inscription_formsemestre_id"]:
        H.append(
            f"""<a class="stdlink" href="{url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=etud["inscription_formsemestre_id"])
                }">"""
        )
    H.append(etud["inscriptionstr"])
    if etud["inscription_formsemestre_id"]:
        H.append("""</a>""")
    H.append("""</p>""")
    if sem["modalite"] == "EXT":
        H.append(
            """<p><a 
        href="formsemestre_ext_edit_ue_validations?formsemestre_id=%s&etudid=%s" 
        class="stdlink">
        Editer les validations d'UE dans ce semestre extérieur
        </a></p>"""
            % (formsemestre_id, etudid)
        )
    # Place du diagramme radar
    H.append(
        """<form id="params">
    <input type="hidden" name="etudid" id="etudid" value="%s"/>
    <input type="hidden" name="formsemestre_id" id="formsemestre_id" value="%s"/>
    </form>"""
        % (etudid, formsemestre_id)
    )
    H.append('<div id="radar_bulletin"></div>')

    # --- Pied de page
    H.append(html_sco_header.sco_footer())

    return "".join(H)


def can_send_bulletin_by_mail(formsemestre_id):
    """True if current user is allowed to send a bulletin by mail"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    return (
        sco_preferences.get_preference("bul_mail_allowed_for_all", formsemestre_id)
        or current_user.has_permission(Permission.ScoImplement)
        or current_user.id in sem["responsables"]
    )


def do_formsemestre_bulletinetud(
    formsemestre_id,
    etudid,
    version="long",  # short, long, selectedevals
    format="html",
    nohtml=False,
    xml_with_decisions=False,  # force decisions dans XML
    force_publishing=False,  # force publication meme si semestre non publie sur "portail"
    prefer_mail_perso=False,  # mails envoyes sur adresse perso si non vide
):
    """Génère le bulletin au format demandé.
    Retourne: (bul, filigranne)
    où bul est str ou bytes au format demandé (html, pdf, pdfmail, pdfpart, xml, json)
    et filigranne est un message à placer en "filigranne" (eg "Provisoire").
    """
    if format == "xml":
        bul = sco_bulletins_xml.make_xml_formsemestre_bulletinetud(
            formsemestre_id,
            etudid,
            xml_with_decisions=xml_with_decisions,
            force_publishing=force_publishing,
            version=version,
        )

        return bul, ""

    elif format == "json":
        bul = sco_bulletins_json.make_json_formsemestre_bulletinetud(
            formsemestre_id,
            etudid,
            xml_with_decisions=xml_with_decisions,
            force_publishing=force_publishing,
            version=version,
        )
        return bul, ""

    I = formsemestre_bulletinetud_dict(formsemestre_id, etudid)
    etud = I["etud"]

    if format == "html":
        htm, _ = sco_bulletins_generator.make_formsemestre_bulletinetud(
            I, version=version, format="html"
        )
        return htm, I["filigranne"]

    elif format == "pdf" or format == "pdfpart":
        bul, filename = sco_bulletins_generator.make_formsemestre_bulletinetud(
            I,
            version=version,
            format="pdf",
            stand_alone=(format != "pdfpart"),
        )
        if format == "pdf":
            return (
                scu.sendPDFFile(bul, filename),
                I["filigranne"],
            )  # unused ret. value
        else:
            return bul, I["filigranne"]

    elif format == "pdfmail":
        # format pdfmail: envoie le pdf par mail a l'etud, et affiche le html
        # check permission
        if not can_send_bulletin_by_mail(formsemestre_id):
            raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")

        if nohtml:
            htm = ""  # speed up if html version not needed
        else:
            htm, _ = sco_bulletins_generator.make_formsemestre_bulletinetud(
                I, version=version, format="html"
            )

        pdfdata, filename = sco_bulletins_generator.make_formsemestre_bulletinetud(
            I, version=version, format="pdf"
        )

        if prefer_mail_perso:
            recipient_addr = etud.get("emailperso", "") or etud.get("email", "")
        else:
            recipient_addr = etud["email_default"]

        if not recipient_addr:
            if nohtml:
                h = ""  # permet de compter les non-envois
            else:
                h = (
                    "<div class=\"boldredmsg\">%s n'a pas d'adresse e-mail !</div>"
                    % etud["nomprenom"]
                ) + htm
            return h, I["filigranne"]
        #
        mail_bulletin(formsemestre_id, I, pdfdata, filename, recipient_addr)
        emaillink = '<a class="stdlink" href="mailto:%s">%s</a>' % (
            recipient_addr,
            recipient_addr,
        )
        return (
            ('<div class="head_message">Message mail envoyé à %s</div>' % (emaillink))
            + htm,
            I["filigranne"],
        )

    else:
        raise ValueError("do_formsemestre_bulletinetud: invalid format (%s)" % format)


def mail_bulletin(formsemestre_id, I, pdfdata, filename, recipient_addr):
    """Send bulletin by email to etud
    If bul_mail_list_abs pref is true, put list of absences in mail body (text).
    """
    etud = I["etud"]
    webmaster = sco_preferences.get_preference("bul_mail_contact_addr", formsemestre_id)
    dept = scu.unescape_html(
        sco_preferences.get_preference("DeptName", formsemestre_id)
    )
    copy_addr = sco_preferences.get_preference("email_copy_bulletins", formsemestre_id)
    intro_mail = sco_preferences.get_preference("bul_intro_mail", formsemestre_id)

    if intro_mail:
        hea = intro_mail % {
            "nomprenom": etud["nomprenom"],
            "dept": dept,
            "webmaster": webmaster,
        }
    else:
        hea = ""

    if sco_preferences.get_preference("bul_mail_list_abs"):
        hea += "\n\n" + sco_abs_views.ListeAbsEtud(
            etud["etudid"], with_evals=False, format="text"
        )

    subject = "Relevé de notes de %s" % etud["nomprenom"]
    recipients = [recipient_addr]
    sender = sco_preferences.get_preference("email_from_addr", formsemestre_id)
    if copy_addr:
        bcc = copy_addr.strip()
    else:
        bcc = ""
    msg = Message(subject, sender=sender, recipients=recipients, bcc=[bcc])
    msg.body = hea

    # Attach pdf
    msg.attach(filename, scu.PDF_MIMETYPE, pdfdata)
    log("mail bulletin a %s" % recipient_addr)
    email.send_message(msg)


def _formsemestre_bulletinetud_header_html(
    etud,
    etudid,
    sem,
    formsemestre_id=None,
    format=None,
    version=None,
):
    H = [
        html_sco_header.sco_header(
            page_title="Bulletin de %(nomprenom)s" % etud,
            javascripts=[
                "js/bulletin.js",
                "libjs/d3.v3.min.js",
                "js/radar_bulletin.js",
            ],
            cssstyles=["css/radar_bulletin.css"],
        ),
        """<table class="bull_head"><tr><td>
          <h2><a class="discretelink" href="%s">%s</a></h2>
          """
        % (
            url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
            ),
            etud["nomprenom"],
        ),
        """
          <form name="f" method="GET" action="%s">"""
        % request.base_url,
        f"""Bulletin <span class="bull_liensemestre"><a href="{
            url_for("notes.formsemestre_status", 
            scodoc_dept=g.scodoc_dept, 
            formsemestre_id=sem["formsemestre_id"])}
            ">{sem["titremois"]}</a></span> 
          <br/>"""
        % sem,
        """<table><tr>""",
        """<td>établi le %s (notes sur 20)</td>""" % time.strftime("%d/%m/%Y à %Hh%M"),
        """<td><span class="rightjust">
             <input type="hidden" name="formsemestre_id" value="%s"></input>"""
        % formsemestre_id,
        """<input type="hidden" name="etudid" value="%s"></input>""" % etudid,
        """<input type="hidden" name="format" value="%s"></input>""" % format,
        """<select name="version" onchange="document.f.submit()" class="noprint">""",
    ]
    for (v, e) in (
        ("short", "Version courte"),
        ("selectedevals", "Version intermédiaire"),
        ("long", "Version complète"),
    ):
        if v == version:
            selected = " selected"
        else:
            selected = ""
        H.append('<option value="%s"%s>%s</option>' % (v, selected, e))
    H.append("""</select></td>""")
    # Menu
    endpoint = "notes.formsemestre_bulletinetud"

    menuBul = [
        {
            "title": "Réglages bulletins",
            "endpoint": "notes.formsemestre_edit_options",
            "args": {
                "formsemestre_id": formsemestre_id,
                # "target_url": url_for(
                #     "notes.formsemestre_bulletinetud",
                #     scodoc_dept=g.scodoc_dept,
                #     formsemestre_id=formsemestre_id,
                #     etudid=etudid,
                # ),
            },
            "enabled": (current_user.id in sem["responsables"])
            or current_user.has_permission(Permission.ScoImplement),
        },
        {
            "title": 'Version papier (pdf, format "%s")'
            % sco_bulletins_generator.bulletin_get_class_name_displayed(
                formsemestre_id
            ),
            "endpoint": endpoint,
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
                "version": version,
                "format": "pdf",
            },
        },
        {
            "title": "Envoi par mail à %s" % etud["email"],
            "endpoint": endpoint,
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
                "version": version,
                "format": "pdfmail",
            },
            # possible slt si on a un mail...
            "enabled": etud["email"] and can_send_bulletin_by_mail(formsemestre_id),
        },
        {
            "title": "Envoi par mail à %s (adr. personnelle)" % etud["emailperso"],
            "endpoint": endpoint,
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
                "version": version,
                "format": "pdfmail",
                "prefer_mail_perso": 1,
            },
            # possible slt si on a un mail...
            "enabled": etud["emailperso"]
            and can_send_bulletin_by_mail(formsemestre_id),
        },
        {
            "title": "Version json",
            "endpoint": endpoint,
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
                "version": version,
                "format": "json",
            },
        },
        {
            "title": "Version XML",
            "endpoint": endpoint,
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
                "version": version,
                "format": "xml",
            },
        },
        {
            "title": "Ajouter une appréciation",
            "endpoint": "notes.appreciation_add_form",
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
            },
            "enabled": (
                (current_user.id in sem["responsables"])
                or (current_user.has_permission(Permission.ScoEtudInscrit))
            ),
        },
        {
            "title": "Enregistrer un semestre effectué ailleurs",
            "endpoint": "notes.formsemestre_ext_create_form",
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
            },
            "enabled": current_user.has_permission(Permission.ScoImplement),
        },
        {
            "title": "Enregistrer une validation d'UE antérieure",
            "endpoint": "notes.formsemestre_validate_previous_ue",
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
            },
            "enabled": sco_permissions_check.can_validate_sem(formsemestre_id),
        },
        {
            "title": "Enregistrer note d'une UE externe",
            "endpoint": "notes.external_ue_create_form",
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
            },
            "enabled": sco_permissions_check.can_validate_sem(formsemestre_id),
        },
        {
            "title": "Entrer décisions jury",
            "endpoint": "notes.formsemestre_validation_etud_form",
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
            },
            "enabled": sco_permissions_check.can_validate_sem(formsemestre_id),
        },
        {
            "title": "Editer PV jury",
            "endpoint": "notes.formsemestre_pvjury_pdf",
            "args": {
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
            },
            "enabled": True,
        },
    ]

    H.append("""<td class="bulletin_menubar"><div class="bulletin_menubar">""")
    H.append(htmlutils.make_menu("Autres opérations", menuBul, alone=True))
    H.append("""</div></td>""")
    H.append(
        '<td> <a href="%s">%s</a></td>'
        % (
            url_for(
                "notes.formsemestre_bulletinetud",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
                etudid=etudid,
                format="pdf",
                version=version,
            ),
            scu.ICON_PDF,
        )
    )
    H.append("""</tr></table>""")
    #
    H.append(
        """</form></span></td><td class="bull_photo"><a href="%s">%s</a>
        """
        % (
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            sco_photos.etud_photo_html(etud, title="fiche de " + etud["nom"]),
        )
    )
    H.append(
        """</td></tr>
    </table>
    """
    )

    return "".join(H)
