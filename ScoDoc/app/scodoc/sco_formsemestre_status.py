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

"""Tableau de bord semestre
"""

from flask import current_app
from flask import g
from flask import request
from flask import url_for
from flask_login import current_user

from app import log
import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import ScoValueError, ScoInvalidDateError
import sco_version
from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_abs
from app.scodoc import sco_archives
from app.scodoc import sco_bulletins
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_compute_moy
from app.scodoc import sco_cache
from app.scodoc import sco_edit_ue
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_edit
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_permissions_check
from app.scodoc import sco_preferences
from app.scodoc import sco_users
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_formsemestre_custommenu import formsemestre_custommenu_html


def _build_menu_stats(formsemestre_id):
    "Définition du menu 'Statistiques'"
    return [
        {
            "title": "Statistiques...",
            "endpoint": "notes.formsemestre_report_counts",
            "args": {"formsemestre_id": formsemestre_id},
        },
        {
            "title": "Suivi de cohortes",
            "endpoint": "notes.formsemestre_suivi_cohorte",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
        },
        {
            "title": "Graphe des parcours",
            "endpoint": "notes.formsemestre_graph_parcours",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
        },
        {
            "title": "Codes des parcours",
            "endpoint": "notes.formsemestre_suivi_parcours",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
        },
        {
            "title": "Lycées d'origine",
            "endpoint": "notes.formsemestre_etuds_lycees",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
        },
        {
            "title": 'Table "poursuite"',
            "endpoint": "notes.formsemestre_poursuite_report",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
        },
        {
            "title": "Documents Avis Poursuite Etudes",
            "endpoint": "notes.pe_view_sem_recap",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_app.config["TESTING"] or current_app.config["DEBUG"],
        },
        {
            "title": 'Table "débouchés"',
            "endpoint": "notes.report_debouche_date",
            "enabled": True,
        },
        {
            "title": "Estimation du coût de la formation",
            "endpoint": "notes.formsemestre_estim_cost",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
        },
    ]


def formsemestre_status_menubar(sem):
    """HTML to render menubar"""
    formsemestre_id = sem["formsemestre_id"]
    if int(sem["etat"]):
        change_lock_msg = "Verrouiller"
    else:
        change_lock_msg = "Déverrouiller"

    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]

    menuSemestre = [
        {
            "title": "Tableau de bord",
            "endpoint": "notes.formsemestre_status",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
            "helpmsg": "Tableau de bord du semestre",
        },
        {
            "title": "Voir la formation %(acronyme)s (v%(version)s)" % F,
            "endpoint": "notes.ue_table",
            "args": {"formation_id": sem["formation_id"]},
            "enabled": True,
            "helpmsg": "Tableau de bord du semestre",
        },
        {
            "title": "Modifier le semestre",
            "endpoint": "notes.formsemestre_editwithmodules",
            "args": {
                "formation_id": sem["formation_id"],
                "formsemestre_id": formsemestre_id,
            },
            "enabled": (
                current_user.has_permission(Permission.ScoImplement)
                or (current_user.id in sem["responsables"] and sem["resp_can_edit"])
            )
            and (sem["etat"]),
            "helpmsg": "Modifie le contenu du semestre (modules)",
        },
        {
            "title": "Préférences du semestre",
            "endpoint": "scolar.formsemestre_edit_preferences",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": (
                current_user.has_permission(Permission.ScoImplement)
                or (current_user.id in sem["responsables"] and sem["resp_can_edit"])
            )
            and (sem["etat"]),
            "helpmsg": "Préférences du semestre",
        },
        {
            "title": "Réglages bulletins",
            "endpoint": "notes.formsemestre_edit_options",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": (current_user.id in sem["responsables"])
            or current_user.has_permission(Permission.ScoImplement),
            "helpmsg": "Change les options",
        },
        {
            "title": change_lock_msg,
            "endpoint": "notes.formsemestre_change_lock",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": (current_user.id in sem["responsables"])
            or current_user.has_permission(Permission.ScoImplement),
            "helpmsg": "",
        },
        {
            "title": "Description du semestre",
            "endpoint": "notes.formsemestre_description",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
            "helpmsg": "",
        },
        {
            "title": "Vérifier absences aux évaluations",
            "endpoint": "notes.formsemestre_check_absences_html",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
            "helpmsg": "",
        },
        {
            "title": "Lister tous les enseignants",
            "endpoint": "notes.formsemestre_enseignants_list",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
            "helpmsg": "",
        },
        {
            "title": "Cloner ce semestre",
            "endpoint": "notes.formsemestre_clone",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoImplement),
            "helpmsg": "",
        },
        {
            "title": "Associer à une nouvelle version du programme",
            "endpoint": "notes.formsemestre_associate_new_version",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoChangeFormation)
            and (sem["etat"]),
            "helpmsg": "",
        },
        {
            "title": "Supprimer ce semestre",
            "endpoint": "notes.formsemestre_delete",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoImplement),
            "helpmsg": "",
        },
    ]
    # debug :
    if current_app.config["ENV"] == "development":
        menuSemestre.append(
            {
                "title": "Vérifier l'intégrité",
                "endpoint": "notes.check_sem_integrity",
                "args": {"formsemestre_id": formsemestre_id},
                "enabled": True,
            }
        )

    menuInscriptions = [
        {
            "title": "Voir les inscriptions aux modules",
            "endpoint": "notes.moduleimpl_inscriptions_stats",
            "args": {"formsemestre_id": formsemestre_id},
        }
    ]
    menuInscriptions += [
        {
            "title": "Passage des étudiants depuis d'autres semestres",
            "endpoint": "notes.formsemestre_inscr_passage",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoEtudInscrit)
            and (sem["etat"]),
        },
        {
            "title": "Synchroniser avec étape Apogée",
            "endpoint": "notes.formsemestre_synchro_etuds",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoView)
            and sco_preferences.get_preference("portal_url")
            and (sem["etat"]),
        },
        {
            "title": "Inscrire un étudiant",
            "endpoint": "notes.formsemestre_inscription_with_modules_etud",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoEtudInscrit)
            and (sem["etat"]),
        },
        {
            "title": "Importer des étudiants dans ce semestre (table Excel)",
            "endpoint": "scolar.form_students_import_excel",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoEtudInscrit)
            and (sem["etat"]),
        },
        {
            "title": "Import/export des données admission",
            "endpoint": "scolar.form_students_import_infos_admissions",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoView),
        },
        {
            "title": "Resynchroniser données identité",
            "endpoint": "scolar.formsemestre_import_etud_admission",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": current_user.has_permission(Permission.ScoEtudChangeAdr)
            and sco_preferences.get_preference("portal_url"),
        },
        {
            "title": "Exporter table des étudiants",
            "endpoint": "scolar.groups_view",
            "args": {
                "format": "allxls",
                "group_ids": sco_groups.get_default_group(
                    formsemestre_id, fix_if_missing=True
                ),
            },
        },
        {
            "title": "Vérifier inscriptions multiples",
            "endpoint": "notes.formsemestre_inscrits_ailleurs",
            "args": {"formsemestre_id": formsemestre_id},
        },
    ]

    menuGroupes = [
        {
            "title": "Listes, photos, feuilles...",
            "endpoint": "scolar.groups_view",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
            "helpmsg": "Accès aux listes des groupes d'étudiants",
        },
        {
            "title": "Créer/modifier les partitions...",
            "endpoint": "scolar.editPartitionForm",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": sco_groups.sco_permissions_check.can_change_groups(
                formsemestre_id
            ),
        },
    ]
    # 1 item / partition:
    partitions = sco_groups.get_partitions_list(formsemestre_id, with_default=False)
    submenu = []
    enabled = (
        sco_groups.sco_permissions_check.can_change_groups(formsemestre_id)
        and partitions
    )
    for partition in partitions:
        submenu.append(
            {
                "title": "%s" % partition["partition_name"],
                "endpoint": "scolar.affect_groups",
                "args": {"partition_id": partition["partition_id"]},
                "enabled": enabled,
            }
        )
    menuGroupes.append(
        {"title": "Modifier les groupes", "submenu": submenu, "enabled": enabled}
    )

    menuNotes = [
        {
            "title": "Tableau des moyennes (et liens bulletins)",
            "endpoint": "notes.formsemestre_recapcomplet",
            "args": {"formsemestre_id": formsemestre_id},
        },
        {
            "title": "Saisie des notes",
            "endpoint": "notes.formsemestre_status",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": True,
            "helpmsg": "Tableau de bord du semestre",
        },
        {
            "title": "Classeur PDF des bulletins",
            "endpoint": "notes.formsemestre_bulletins_pdf_choice",
            "args": {"formsemestre_id": formsemestre_id},
            "helpmsg": "PDF regroupant tous les bulletins",
        },
        {
            "title": "Envoyer à chaque étudiant son bulletin par e-mail",
            "endpoint": "notes.formsemestre_bulletins_mailetuds_choice",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": sco_bulletins.can_send_bulletin_by_mail(formsemestre_id),
        },
        {
            "title": "Calendrier des évaluations",
            "endpoint": "notes.formsemestre_evaluations_cal",
            "args": {"formsemestre_id": formsemestre_id},
        },
        {
            "title": "Lister toutes les saisies de notes",
            "endpoint": "notes.formsemestre_list_saisies_notes",
            "args": {"formsemestre_id": formsemestre_id},
        },
    ]
    menuJury = [
        {
            "title": "Voir les décisions du jury",
            "endpoint": "notes.formsemestre_pvjury",
            "args": {"formsemestre_id": formsemestre_id},
        },
        {
            "title": "Générer feuille préparation Jury",
            "endpoint": "notes.feuille_preparation_jury",
            "args": {"formsemestre_id": formsemestre_id},
        },
        {
            "title": "Saisie des décisions du jury",
            "endpoint": "notes.formsemestre_recapcomplet",
            "args": {
                "formsemestre_id": formsemestre_id,
                "modejury": 1,
                "hidemodules": 1,
                "hidebac": 1,
                "pref_override": 0,
            },
            "enabled": sco_permissions_check.can_validate_sem(formsemestre_id),
        },
        {
            "title": "Editer les PV et archiver les résultats",
            "endpoint": "notes.formsemestre_archive",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": sco_permissions_check.can_edit_pv(formsemestre_id),
        },
        {
            "title": "Documents archivés",
            "endpoint": "notes.formsemestre_list_archives",
            "args": {"formsemestre_id": formsemestre_id},
            "enabled": sco_archives.PVArchive.list_obj_archives(formsemestre_id),
        },
    ]

    menuStats = _build_menu_stats(formsemestre_id)
    H = [
        # <table><tr><td>',
        '<ul id="sco_menu">',
        htmlutils.make_menu("Semestre", menuSemestre),
        htmlutils.make_menu("Inscriptions", menuInscriptions),
        htmlutils.make_menu("Groupes", menuGroupes),
        htmlutils.make_menu("Notes", menuNotes),
        htmlutils.make_menu("Jury", menuJury),
        htmlutils.make_menu("Statistiques", menuStats),
        formsemestre_custommenu_html(formsemestre_id),
        "</ul>",
        #'</td></tr></table>'
    ]
    return "\n".join(H)


def retreive_formsemestre_from_request() -> int:
    """Cherche si on a de quoi déduire le semestre affiché à partir des
    arguments de la requête:
    formsemestre_id ou moduleimpl ou evaluation ou group_id ou partition_id
    """
    if request.method == "GET":
        args = request.args
    elif request.method == "POST":
        args = request.form
    else:
        return None
    formsemestre_id = None
    # Search formsemestre
    group_ids = args.get("group_ids", [])
    if "formsemestre_id" in args:
        formsemestre_id = args["formsemestre_id"]
    elif "moduleimpl_id" in args and args["moduleimpl_id"]:
        modimpl = sco_moduleimpl.moduleimpl_list(moduleimpl_id=args["moduleimpl_id"])
        if not modimpl:
            return None  # suppressed ?
        modimpl = modimpl[0]
        formsemestre_id = modimpl["formsemestre_id"]
    elif "evaluation_id" in args:
        E = sco_evaluations.do_evaluation_list({"evaluation_id": args["evaluation_id"]})
        if not E:
            return None  # evaluation suppressed ?
        E = E[0]
        modimpl = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
        formsemestre_id = modimpl["formsemestre_id"]
    elif "group_id" in args:
        group = sco_groups.get_group(args["group_id"])
        formsemestre_id = group["formsemestre_id"]
    elif group_ids:
        if group_ids:
            if isinstance(group_ids, str):
                group_id = group_ids
            else:
                # prend le semestre du 1er groupe de la liste:
                group_id = group_ids[0]
            group = sco_groups.get_group(group_id)
        formsemestre_id = group["formsemestre_id"]
    elif "partition_id" in args:
        partition = sco_groups.get_partition(args["partition_id"])
        formsemestre_id = partition["formsemestre_id"]

    if not formsemestre_id:
        return None  # no current formsemestre

    return int(formsemestre_id)


# Element HTML decrivant un semestre (barre de menu et infos)
def formsemestre_page_title():
    """Element HTML decrivant un semestre (barre de menu et infos)
    Cherche dans la requete si un semestre est défini (formsemestre_id ou moduleimpl ou evaluation ou group)
    """
    formsemestre_id = retreive_formsemestre_from_request()
    #
    if not formsemestre_id:
        return ""
    try:
        formsemestre_id = int(formsemestre_id)
        sem = sco_formsemestre.get_formsemestre(formsemestre_id).copy()
    except:
        log("can't find formsemestre_id %s" % formsemestre_id)
        return ""

    fill_formsemestre(sem)

    h = f"""<div class="formsemestre_page_title">
    <div class="infos">
        <span class="semtitle"><a class="stdlink" title="{sem['session_id']}"
        href="{url_for('notes.formsemestre_status', 
            scodoc_dept=g.scodoc_dept, formsemestre_id=sem['formsemestre_id'])}"
        >{sem['titre']}</a><a
        title="{sem['etape_apo_str']}">{sem['num_sem']}</a>{sem['modalitestr']}</span><span
        class="dates"><a 
        title="du {sem['date_debut']} au {sem['date_fin']} "
        >{sem['mois_debut']} - {sem['mois_fin']}</a></span><span 
        class="resp"><a title="{sem['nomcomplet']}">{sem['resp']}</a></span><span 
        class="nbinscrits"><a class="discretelink" 
        href="{url_for("scolar.groups_view", 
            scodoc_dept=g.scodoc_dept, formsemestre_id=sem['formsemestre_id'])}"
        >{sem['nbinscrits']} inscrits</a></span><span 
        class="lock">{sem['locklink']}</span><span 
        class="eye">{sem['eyelink']}</span>
    </div>
    {formsemestre_status_menubar(sem)}
    </div>
    """

    return h


def fill_formsemestre(sem):
    """Add some useful fields to help display formsemestres"""
    notes_url = scu.NotesURL()
    sem["notes_url"] = notes_url
    formsemestre_id = sem["formsemestre_id"]
    if not sem["etat"]:
        sem[
            "locklink"
        ] = """<a href="%s/formsemestre_change_lock?formsemestre_id=%s">%s</a>""" % (
            notes_url,
            sem["formsemestre_id"],
            scu.icontag("lock_img", border="0", title="Semestre verrouillé"),
        )
    else:
        sem["locklink"] = ""
    if sco_preferences.get_preference("bul_display_publication", formsemestre_id):
        if sem["bul_hide_xml"]:
            eyeicon = scu.icontag("hide_img", border="0", title="Bulletins NON publiés")
        else:
            eyeicon = scu.icontag("eye_img", border="0", title="Bulletins publiés")
        sem["eyelink"] = (
            """<a href="%s/formsemestre_change_publication_bul?formsemestre_id=%s">%s</a>"""
            % (notes_url, sem["formsemestre_id"], eyeicon)
        )
    else:
        sem["eyelink"] = ""
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    sem["formation"] = F
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
    if sem["semestre_id"] != -1:
        sem["num_sem"] = ", %s %s" % (parcours.SESSION_NAME, sem["semestre_id"])
    else:
        sem["num_sem"] = ""  # formation sans semestres
    if sem["modalite"]:
        sem["modalitestr"] = " en %s" % sem["modalite"]
    else:
        sem["modalitestr"] = ""

    sem["etape_apo_str"] = "Code étape Apogée: " + (
        sco_formsemestre.formsemestre_etape_apo_str(sem) or "Pas de code étape"
    )

    inscrits = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id}
    )
    sem["nbinscrits"] = len(inscrits)
    uresps = [
        sco_users.user_info(responsable_id) for responsable_id in sem["responsables"]
    ]
    sem["resp"] = ", ".join([u["prenomnom"] for u in uresps])
    sem["nomcomplet"] = ", ".join([u["nomcomplet"] for u in uresps])


# Description du semestre sous forme de table exportable
def formsemestre_description_table(formsemestre_id, with_evals=False):
    """Description du semestre sous forme de table exportable
    Liste des modules et de leurs coefficients
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > liste evaluations
    use_ue_coefs = sco_preferences.get_preference("use_ue_coefs", formsemestre_id)
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
    Mlist = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)

    R = []
    sum_coef = 0
    sum_ects = 0
    last_ue_id = None
    for M in Mlist:
        # Ligne UE avec ECTS:
        ue = M["ue"]
        if ue["ue_id"] != last_ue_id:
            last_ue_id = ue["ue_id"]
            if ue["ects"] is None:
                ects_str = "-"
            else:
                sum_ects += ue["ects"]
                ects_str = ue["ects"]
            ue_info = {
                "UE": ue["acronyme"],
                "ects": ects_str,
                "Module": ue["titre"],
                "_css_row_class": "table_row_ue",
            }
            if use_ue_coefs:
                ue_info["Coef."] = ue["coefficient"]
                ue_info["Coef._class"] = "ue_coef"
            R.append(ue_info)

        ModInscrits = sco_moduleimpl.do_moduleimpl_inscription_list(
            moduleimpl_id=M["moduleimpl_id"]
        )
        enseignants = ", ".join(
            [sco_users.user_info(m["ens_id"])["nomprenom"] for m in M["ens"]]
        )
        l = {
            "UE": M["ue"]["acronyme"],
            "Code": M["module"]["code"],
            "Module": M["module"]["abbrev"] or M["module"]["titre"],
            "_Module_class": "scotext",
            "Inscrits": len(ModInscrits),
            "Responsable": sco_users.user_info(M["responsable_id"])["nomprenom"],
            "_Responsable_class": "scotext",
            "Enseignants": enseignants,
            "_Enseignants_class": "scotext",
            "Coef.": M["module"]["coefficient"],
            # 'ECTS' : M['module']['ects'],
            # Lien sur titre -> module
            "_Module_target": url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=M["moduleimpl_id"],
            ),
            "_Code_target": url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=M["moduleimpl_id"],
            ),
        }
        R.append(l)
        if M["module"]["coefficient"]:
            sum_coef += M["module"]["coefficient"]

        if with_evals:
            # Ajoute lignes pour evaluations
            evals = nt.get_mod_evaluation_etat_list(M["moduleimpl_id"])
            evals.reverse()  # ordre chronologique
            # Ajoute etat:
            for e in evals:
                # Cosmetic: conversions pour affichage
                if e["etat"]["evalcomplete"]:
                    e["evalcomplete_str"] = "Oui"
                    e["_evalcomplete_str_td_attrs"] = 'style="color: green;"'
                else:
                    e["evalcomplete_str"] = "Non"
                    e["_evalcomplete_str_td_attrs"] = 'style="color: red;"'

                if e["publish_incomplete"]:
                    e["publish_incomplete_str"] = "Oui"
                    e["_publish_incomplete_str_td_attrs"] = 'style="color: green;"'
                else:
                    e["publish_incomplete_str"] = "Non"
                    e["_publish_incomplete_str_td_attrs"] = 'style="color: red;"'
            R += evals

    sums = {"_css_row_class": "moyenne sortbottom", "ects": sum_ects, "Coef.": sum_coef}
    R.append(sums)
    columns_ids = ["UE", "Code", "Module", "Coef."]
    if sco_preferences.get_preference("bul_show_ects", formsemestre_id):
        columns_ids += ["ects"]
    columns_ids += ["Inscrits", "Responsable", "Enseignants"]
    if with_evals:
        columns_ids += [
            "jour",
            "description",
            "coefficient",
            "evalcomplete_str",
            "publish_incomplete_str",
        ]

    titles = {title: title for title in columns_ids}

    titles["ects"] = "ECTS"
    titles["jour"] = "Evaluation"
    titles["description"] = ""
    titles["coefficient"] = "Coef. éval."
    titles["evalcomplete_str"] = "Complète"
    titles["publish_incomplete_str"] = "Toujours Utilisée"
    title = "%s %s" % (parcours.SESSION_NAME.capitalize(), sem["titremois"])

    return GenTable(
        columns_ids=columns_ids,
        rows=R,
        titles=titles,
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption=title,
        html_caption=title,
        html_class="table_leftalign formsemestre_description",
        base_url="%s?formsemestre_id=%s&with_evals=%s"
        % (request.base_url, formsemestre_id, with_evals),
        page_title=title,
        html_title=html_sco_header.html_sem_header(
            "Description du semestre", sem, with_page_header=False
        ),
        pdf_title=title,
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )


def formsemestre_description(formsemestre_id, format="html", with_evals=False):
    """Description du semestre sous forme de table exportable
    Liste des modules et de leurs coefficients
    """
    with_evals = int(with_evals)
    tab = formsemestre_description_table(formsemestre_id, with_evals=with_evals)
    tab.html_before_table = """<form name="f" method="get" action="%s">
    <input type="hidden" name="formsemestre_id" value="%s"></input>
    <input type="checkbox" name="with_evals" value="1" onchange="document.f.submit()" """ % (
        request.base_url,
        formsemestre_id,
    )
    if with_evals:
        tab.html_before_table += "checked"
    tab.html_before_table += ">indiquer les évaluations</input></form>"

    return tab.make_page(format=format)


# genere liste html pour accès aux groupes de ce semestre
def _make_listes_sem(sem, with_absences=True):
    # construit l'URL "destination"
    # (a laquelle on revient apres saisie absences)
    destination = url_for(
        "notes.formsemestre_status",
        scodoc_dept=g.scodoc_dept,
        formsemestre_id=sem["formsemestre_id"],
    )
    #
    H = []
    # pas de menu absences si pas autorise:
    if with_absences and not current_user.has_permission(Permission.ScoAbsChange):
        with_absences = False

    #
    H.append(
        '<h3>Listes de %(titre)s <span class="infostitresem">(%(mois_debut)s - %(mois_fin)s)</span></h3>'
        % sem
    )

    formsemestre_id = sem["formsemestre_id"]

    # calcule dates 1er jour semaine pour absences
    try:
        if with_absences:
            first_monday = sco_abs.ddmmyyyy(sem["date_debut"]).prev_monday()
            form_abs_tmpl = f"""
            <td><form action="{url_for(
                        "absences.SignaleAbsenceGrSemestre", scodoc_dept=g.scodoc_dept
                    )}" method="get">
                <input type="hidden" name="datefin" value="{sem['date_fin']}"/>
                <input type="hidden" name="group_ids" value="%(group_id)s"/>
                <input type="hidden" name="destination" value="{destination}"/>
                <input type="submit" value="Saisir absences du" />
                <select name="datedebut" class="noprint">
            """
            date = first_monday
            for jour in sco_abs.day_names():
                form_abs_tmpl += '<option value="%s">%s</option>' % (date, jour)
                date = date.next_day()
            form_abs_tmpl += """
                </select>
                <a href="%(url_etat)s">état</a>
                </form></td>
            """
        else:
            form_abs_tmpl = ""
    except ScoInvalidDateError:  # dates incorrectes dans semestres ?
        form_abs_tmpl = ""
    #
    H.append('<div id="grouplists">')
    # Genere liste pour chaque partition (categorie de groupes)
    for partition in sco_groups.get_partitions_list(sem["formsemestre_id"]):
        if not partition["partition_name"]:
            H.append("<h4>Tous les étudiants</h4>" % partition)
        else:
            H.append("<h4>Groupes de %(partition_name)s</h4>" % partition)
        groups = sco_groups.get_partition_groups(partition)
        if groups:
            H.append("<table>")
            for group in groups:
                n_members = len(sco_groups.get_group_members(group["group_id"]))
                group["url_etat"] = url_for(
                    "absences.EtatAbsencesGr",
                    group_ids=group["group_id"],
                    debut=sem["date_debut"],
                    fin=sem["date_fin"],
                    scodoc_dept=g.scodoc_dept,
                )
                if group["group_name"]:
                    group["label"] = "groupe %(group_name)s" % group
                else:
                    group["label"] = "liste"
                H.append(
                    f"""
                    <tr class="listegroupelink">
                    <td>
                    <a href="{
                        url_for("scolar.groups_view",
                            group_ids=group["group_id"],
                            scodoc_dept=g.scodoc_dept,
                        )
                    }">{group["label"]}</a>
                    </td><td>
                    (<a href="{
                        url_for("scolar.groups_view",
                            group_ids=group["group_id"],
                            format="xls",
                            scodoc_dept=g.scodoc_dept,
                        )
                    }">tableur</a>)
                    <a href="{
                        url_for("scolar.groups_view",
                            curtab="tab-photos",
                            group_ids=group["group_id"],
                            scodoc_dept=g.scodoc_dept,
                        )
                    }">Photos</a>
                    </td>
                    <td>({n_members} étudiants)</td>
                    """
                )

                if with_absences:
                    H.append(form_abs_tmpl % group)

                H.append("</tr>")
            H.append("</table>")
        else:
            H.append('<p class="help indent">Aucun groupe dans cette partition')
            if sco_groups.sco_permissions_check.can_change_groups(formsemestre_id):
                H.append(
                    f""" (<a href="{url_for("scolar.affect_groups",
                    scodoc_dept=g.scodoc_dept,
                    partition_id=partition["partition_id"])
                    }" class="stdlink">créer</a>)"""
                )
            H.append("</p>")
    if sco_groups.sco_permissions_check.can_change_groups(formsemestre_id):
        H.append(
            f"""<h4><a 
            href="{
                url_for("scolar.editPartitionForm", 
                formsemestre_id=formsemestre_id, 
                scodoc_dept=g.scodoc_dept,
                )
            }">Ajouter une partition</a></h4>"""
        )

    H.append("</div>")
    return "\n".join(H)


def html_expr_diagnostic(diagnostics):
    """Affiche messages d'erreur des formules utilisateurs"""
    H = []
    H.append('<div class="ue_warning">Erreur dans des formules utilisateurs:<ul>')
    last_id, last_msg = None, None
    for diag in diagnostics:
        if "moduleimpl_id" in diag:
            mod = sco_moduleimpl.moduleimpl_withmodule_list(
                moduleimpl_id=diag["moduleimpl_id"]
            )[0]
            H.append(
                '<li>module <a href="moduleimpl_status?moduleimpl_id=%s">%s</a>: %s</li>'
                % (
                    diag["moduleimpl_id"],
                    mod["module"]["abbrev"] or mod["module"]["code"] or "?",
                    diag["msg"],
                )
            )
        else:
            if diag["ue_id"] != last_id or diag["msg"] != last_msg:
                ue = sco_edit_ue.ue_list({"ue_id": diag["ue_id"]})[0]
                H.append(
                    '<li>UE "%s": %s</li>'
                    % (ue["acronyme"] or ue["titre"] or "?", diag["msg"])
                )
                last_id, last_msg = diag["ue_id"], diag["msg"]

    H.append("</ul></div>")
    return "".join(H)


def formsemestre_status_head(formsemestre_id=None, page_title=None):
    """En-tête HTML des pages "semestre" """
    semlist = sco_formsemestre.do_formsemestre_list(
        args={"formsemestre_id": formsemestre_id}
    )
    if not semlist:
        raise ScoValueError("Session inexistante (elle a peut être été supprimée ?)")
    sem = semlist[0]
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])

    page_title = page_title or "Modules de "

    H = [
        html_sco_header.html_sem_header(
            page_title, sem, with_page_header=False, with_h2=False
        ),
        f"""<table>
          <tr><td class="fichetitre2">Formation: </td><td>
         <a href="{url_for('notes.ue_table', scodoc_dept=g.scodoc_dept, formation_id=F['formation_id'])}"
         class="discretelink" title="Formation {F['acronyme']}, v{F['version']}">{F['titre']}</a>""",
    ]
    if sem["semestre_id"] >= 0:
        H.append(", %s %s" % (parcours.SESSION_NAME, sem["semestre_id"]))
    if sem["modalite"]:
        H.append("&nbsp;en %(modalite)s" % sem)
    if sem["etapes"]:
        H.append(
            "&nbsp;&nbsp;&nbsp;(étape <b><tt>%s</tt></b>)"
            % (sem["etapes_apo_str"] or "-")
        )
    H.append("</td></tr>")

    evals = sco_evaluations.do_evaluation_etat_in_sem(formsemestre_id)
    H.append(
        '<tr><td class="fichetitre2">Evaluations: </td><td> %(nb_evals_completes)s ok, %(nb_evals_en_cours)s en cours, %(nb_evals_vides)s vides'
        % evals
    )
    if evals["last_modif"]:
        H.append(
            " <em>(dernière note saisie le %s)</em>"
            % evals["last_modif"].strftime("%d/%m/%Y à %Hh%M")
        )
    H.append("</td></tr>")
    if evals["attente"]:
        H.append(
            """<tr><td class="fichetitre2"></td><td class="redboldtext">
Il y a des notes en attente ! Le classement des étudiants n'a qu'une valeur indicative. 
</td></tr>"""
        )
    H.append("</table>")
    sem_warning = ""
    if sem["bul_hide_xml"]:
        sem_warning += "Bulletins non publiés sur le portail. "
    if sem["block_moyennes"]:
        sem_warning += "Calcul des moyennes bloqué !"
    if sem_warning:
        H.append('<p class="fontorange"><em>' + sem_warning + "</em></p>")
    if sem["semestre_id"] >= 0 and not sco_formsemestre.sem_une_annee(sem):
        H.append(
            '<p class="fontorange"><em>Attention: ce semestre couvre plusieurs années scolaires !</em></p>'
        )
    # elif sco_preferences.get_preference( 'bul_display_publication', formsemestre_id):
    #    H.append('<p><em>Bulletins publiés sur le portail</em></p>')

    return "".join(H)


def formsemestre_status(formsemestre_id=None):
    """Tableau de bord semestre HTML"""
    # porté du DTML
    cnx = ndb.GetDBConnexion()
    sem = sco_formsemestre.get_formsemestre(formsemestre_id, raise_soft_exc=True)
    Mlist = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)
    # inscrits = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
    #    args={"formsemestre_id": formsemestre_id}
    # )
    prev_ue_id = None

    can_edit = sco_formsemestre_edit.can_edit_sem(formsemestre_id, sem=sem)

    H = [
        html_sco_header.sco_header(page_title="Semestre %s" % sem["titreannee"]),
        '<div class="formsemestre_status">',
        formsemestre_status_head(
            formsemestre_id=formsemestre_id, page_title="Tableau de bord"
        ),
        """<p><b style="font-size: 130%">Tableau de bord: </b><span class="help">cliquez sur un module pour saisir des notes</span></p>""",
    ]
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    if nt.expr_diagnostics:
        H.append(html_expr_diagnostic(nt.expr_diagnostics))
    H.append(
        """
<p>
<table class="formsemestre_status">
<tr>
<th class="formsemestre_status">Code</th>
<th class="formsemestre_status">Module</th>
<th class="formsemestre_status">Inscrits</th>
<th class="resp">Responsable</th>
<th class="evals">Evaluations</th></tr>"""
    )
    mails_enseignants = set(
        [sco_users.user_info(ens_id)["email"] for ens_id in sem["responsables"]]
    )  # adr. mail des enseignants
    for M in Mlist:
        Mod = M["module"]
        ModDescr = (
            "Module "
            + M["module"]["titre"]
            + ", coef. "
            + str(M["module"]["coefficient"])
        )
        ModEns = sco_users.user_info(M["responsable_id"])["nomcomplet"]
        if M["ens"]:
            ModEns += " (resp.), " + ", ".join(
                [sco_users.user_info(e["ens_id"])["nomcomplet"] for e in M["ens"]]
            )
        ModInscrits = sco_moduleimpl.do_moduleimpl_inscription_list(
            moduleimpl_id=M["moduleimpl_id"]
        )
        mails_enseignants.add(sco_users.user_info(M["responsable_id"])["email"])
        mails_enseignants |= set(
            [sco_users.user_info(m["ens_id"])["email"] for m in M["ens"]]
        )
        ue = M["ue"]
        if prev_ue_id != ue["ue_id"]:
            prev_ue_id = ue["ue_id"]
            acronyme = ue["acronyme"]
            titre = ue["titre"]
            if sco_preferences.get_preference("use_ue_coefs", formsemestre_id):
                titre += " <b>(coef. %s)</b>" % (ue["coefficient"] or 0.0)
            H.append(
                """<tr class="formsemestre_status_ue"><td colspan="4">
<span class="status_ue_acro">%s</span>
<span class="status_ue_title">%s</span>
</td><td>"""
                % (acronyme, titre)
            )

            expr = sco_compute_moy.get_ue_expression(
                formsemestre_id, ue["ue_id"], cnx, html_quote=True
            )

            if can_edit:
                H.append(
                    ' <a href="edit_ue_expr?formsemestre_id=%s&ue_id=%s">'
                    % (formsemestre_id, ue["ue_id"])
                )
            H.append(
                scu.icontag(
                    "formula",
                    title="Mode calcul moyenne d'UE",
                    style="vertical-align:middle",
                )
            )
            if can_edit:
                H.append("</a>")
            if expr:
                H.append(
                    """ <span class="formula" title="mode de calcul de la moyenne d'UE">%s</span>"""
                    % expr
                )

            H.append("</td></tr>")

        if M["ue"]["type"] != sco_codes_parcours.UE_STANDARD:
            fontorange = " fontorange"  # style css additionnel
        else:
            fontorange = ""

        etat = sco_evaluations.do_evaluation_etat_in_mod(nt, M["moduleimpl_id"])
        if (
            etat["nb_evals_completes"] > 0
            and etat["nb_evals_en_cours"] == 0
            and etat["nb_evals_vides"] == 0
        ):
            H.append('<tr class="formsemestre_status_green%s">' % fontorange)
        else:
            H.append('<tr class="formsemestre_status%s">' % fontorange)

        H.append(
            '<td class="formsemestre_status_code"><a href="moduleimpl_status?moduleimpl_id=%s" title="%s" class="stdlink">%s</a></td>'
            % (M["moduleimpl_id"], ModDescr, Mod["code"])
        )
        H.append(
            '<td class="scotext"><a href="moduleimpl_status?moduleimpl_id=%s" title="%s" class="formsemestre_status_link">%s</a></td>'
            % (M["moduleimpl_id"], ModDescr, Mod["abbrev"] or Mod["titre"])
        )
        H.append('<td class="formsemestre_status_inscrits">%s</td>' % len(ModInscrits))
        H.append(
            '<td class="resp scotext"><a class="discretelink" href="moduleimpl_status?moduleimpl_id=%s" title="%s">%s</a></td>'
            % (
                M["moduleimpl_id"],
                ModEns,
                sco_users.user_info(M["responsable_id"])["prenomnom"],
            )
        )

        if Mod["module_type"] == scu.MODULE_STANDARD:
            H.append('<td class="evals">')
            nb_evals = (
                etat["nb_evals_completes"]
                + etat["nb_evals_en_cours"]
                + etat["nb_evals_vides"]
            )
            if nb_evals != 0:
                H.append(
                    '<a href="moduleimpl_status?moduleimpl_id=%s" class="formsemestre_status_link">%s prévues, %s ok</a>'
                    % (M["moduleimpl_id"], nb_evals, etat["nb_evals_completes"])
                )
                if etat["nb_evals_en_cours"] > 0:
                    H.append(
                        ', <span><a class="redlink" href="moduleimpl_status?moduleimpl_id=%s" title="Il manque des notes">%s en cours</a></span>'
                        % (M["moduleimpl_id"], etat["nb_evals_en_cours"])
                    )
                    if etat["attente"]:
                        H.append(
                            ' <span><a class="redlink" href="moduleimpl_status?moduleimpl_id=%s" title="Il y a des notes en attente">[en attente]</a></span>'
                            % M["moduleimpl_id"]
                        )
        elif Mod["module_type"] == scu.MODULE_MALUS:
            nb_malus_notes = sum(
                [
                    e["etat"]["nb_notes"]
                    for e in nt.get_mod_evaluation_etat_list(M["moduleimpl_id"])
                ]
            )
            H.append(
                """<td class="malus">
            <a href="moduleimpl_status?moduleimpl_id=%s" class="formsemestre_status_link">malus (%d notes)</a>
            """
                % (M["moduleimpl_id"], nb_malus_notes)
            )
        else:
            raise ValueError("Invalid module_type")  # a bug

        H.append("</td></tr>")
    H.append("</table></p>")
    if sco_preferences.get_preference("use_ue_coefs", formsemestre_id):
        H.append(
            """
        <p class="infop">utilise les coefficients d'UE pour calculer la moyenne générale.</p>
        """
        )
    # --- LISTE DES ETUDIANTS
    H += [
        '<div id="groupes">',
        _make_listes_sem(sem),
        "</div>",
    ]
    # --- Lien mail enseignants:
    adrlist = list(mails_enseignants - set([""]))
    if adrlist:
        H.append(
            '<p><a class="stdlink" href="mailto:?cc=%s">Courrier aux %d enseignants du semestre</a></p>'
            % (",".join(adrlist), len(adrlist))
        )
    return "".join(H) + html_sco_header.sco_footer()
