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

"""Page accueil département (liste des semestres, etc)
"""

from flask import g, request
from flask_login import current_user

import app
import app.scodoc.sco_utils as scu
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_permissions import Permission
from app.scodoc import html_sco_header
import app.scodoc.notesdb as ndb
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_modalites
from app.scodoc import sco_news
from app.scodoc import sco_preferences
from app.scodoc import sco_up_to_date
from app.scodoc import sco_users


def index_html(showcodes=0, showsemtable=0):
    "Page accueil département (liste des semestres)"
    showcodes = int(showcodes)
    showsemtable = int(showsemtable)
    H = []

    # News:
    H.append(sco_news.scolar_news_summary_html())

    # Avertissement de mise à jour:
    H.append(sco_up_to_date.html_up_to_date_box())

    # Liste de toutes les sessions:
    sems = sco_formsemestre.do_formsemestre_list()
    cursems = []  # semestres "courants"
    othersems = []  # autres (verrouillés)
    # icon image:
    groupicon = scu.icontag("groupicon_img", title="Inscrits", border="0")
    emptygroupicon = scu.icontag(
        "emptygroupicon_img", title="Pas d'inscrits", border="0"
    )
    lockicon = scu.icontag("lock32_img", title="verrouillé", border="0")
    # Sélection sur l'etat du semestre
    for sem in sems:
        if sem["etat"] and sem["modalite"] != "EXT":
            sem["lockimg"] = ""
            cursems.append(sem)
        else:
            sem["lockimg"] = lockicon
            othersems.append(sem)
        # Responsable de formation:
        sco_formsemestre.sem_set_responsable_name(sem)

        if showcodes:
            sem["tmpcode"] = "<td><tt>%s</tt></td>" % sem["formsemestre_id"]
        else:
            sem["tmpcode"] = ""
        # Nombre d'inscrits:
        args = {"formsemestre_id": sem["formsemestre_id"]}
        ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(args=args)
        nb = len(ins)  # nb etudiants
        sem["nb_inscrits"] = nb
        if nb > 0:
            sem["groupicon"] = groupicon
        else:
            sem["groupicon"] = emptygroupicon

    # S'il n'y a pas d'utilisateurs dans la base, affiche message
    if not sco_users.get_user_list(dept=g.scodoc_dept):
        H.append(
            """<h2>Aucun utilisateur défini !</h2><p>Pour définir des utilisateurs
        <a href="Users">passez par la page Utilisateurs</a>.
        <br/>
        Définissez au moins un utilisateur avec le rôle AdminXXX (le responsable du département XXX).
        </p>
        """
        )

    # Liste des formsemestres "courants"
    if cursems:
        H.append('<h2 class="listesems">Sessions en cours</h2>')
        H.append(_sem_table(cursems))
    else:
        # aucun semestre courant: affiche aide
        H.append(
            """<h2 class="listesems">Aucune session en cours !</h2>
        <p>Pour ajouter une session, aller dans <a href="Notes" id="link-programmes">Programmes</a>,
        choisissez une formation, puis suivez le lien "<em>UE, modules, semestres</em>".
        </p><p>
        Là, en bas de page, suivez le lien
        "<em>Mettre en place un nouveau semestre de formation...</em>"
        </p>"""
        )

    if showsemtable:
        H.append(
            """<hr/>
        <h2>Semestres de %s</h2>
        """
            % sco_preferences.get_preference("DeptName")
        )
        H.append(_sem_table_gt(sems, showcodes=showcodes).html())
        H.append("</table>")
    if not showsemtable:
        H.append(
            '<hr/><p><a href="%s?showsemtable=1">Voir tous les semestres</a></p>'
            % request.base_url
        )

    H.append(
        """<p><form action="%s/view_formsemestre_by_etape">
Chercher étape courante: <input name="etape_apo" type="text" size="8" spellcheck="false"></input>    
    </form
    </p>
    """
        % scu.NotesURL()
    )
    #
    if current_user.has_permission(Permission.ScoEtudInscrit):
        H.append(
            """<hr>
        <h3>Gestion des étudiants</h3>
        <ul>
        <li><a class="stdlink" href="etudident_create_form">créer <em>un</em> nouvel étudiant</a></li>
        <li><a class="stdlink" href="form_students_import_excel">importer de nouveaux étudiants</a> (ne pas utiliser sauf cas particulier, utilisez plutôt le lien dans
        le tableau de bord semestre si vous souhaitez inscrire les
        étudiants importés à un semestre)</li>
        </ul>
        """
        )
    #
    if current_user.has_permission(Permission.ScoEditApo):
        H.append(
            """<hr>
        <h3>Exports Apogée</h3>
        <ul>
        <li><a class="stdlink" href="%s/semset_page">Années scolaires / exports Apogée</a></li>
        </ul>
        """
            % scu.NotesURL()
        )
    #
    H.append(
        """<hr>
        <h3>Assistance</h3>
        <ul>
        <li><a class="stdlink" href="sco_dump_and_send_db">Envoyer données</a></li>
        </ul>
    """
    )
    #
    return html_sco_header.sco_header() + "\n".join(H) + html_sco_header.sco_footer()


def _sem_table(sems):
    """Affiche liste des semestres, utilisée pour semestres en cours"""
    tmpl = """<tr class="%(trclass)s">%(tmpcode)s
    <td class="semicon">%(lockimg)s <a href="%(notes_url)s/formsemestre_status?formsemestre_id=%(formsemestre_id)s#groupes">%(groupicon)s</a></td>        
    <td class="datesem">%(mois_debut)s <a title="%(session_id)s">-</a> %(mois_fin)s</td>
    <td><a class="stdlink" href="%(notes_url)s/formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titre_num)s</a>
    <span class="respsem">(%(responsable_name)s)</span>
    </td>
    </tr>
    """

    # Liste des semestres, groupés par modalités
    sems_by_mod, modalites = sco_modalites.group_sems_by_modalite(sems)

    H = ['<table class="listesems">']
    for modalite in modalites:
        if len(modalites) > 1:
            H.append('<tr><th colspan="3">%s</th></tr>' % modalite["titre"])

        if sems_by_mod[modalite["modalite"]]:
            cur_idx = sems_by_mod[modalite["modalite"]][0]["semestre_id"]
            for sem in sems_by_mod[modalite["modalite"]]:
                if cur_idx != sem["semestre_id"]:
                    sem["trclass"] = "firstsem"  # separe les groupes de semestres
                    cur_idx = sem["semestre_id"]
                else:
                    sem["trclass"] = ""
                sem["notes_url"] = scu.NotesURL()
                H.append(tmpl % sem)
    H.append("</table>")
    return "\n".join(H)


def _sem_table_gt(sems, showcodes=False):
    """Nouvelle version de la table des semestres"""
    _style_sems(sems)
    columns_ids = (
        "lockimg",
        "semestre_id_n",
        "modalite",
        #'mois_debut',
        "dash_mois_fin",
        "titre_resp",
        "nb_inscrits",
        "etapes_apo_str",
    )
    if showcodes:
        columns_ids = ("formsemestre_id",) + columns_ids

    tab = GenTable(
        titles={
            "formsemestre_id": "id",
            "semestre_id_n": "S#",
            "modalite": "",
            "mois_debut": "Début",
            "dash_mois_fin": "Année",
            "titre_resp": "Semestre",
            "nb_inscrits": "N",  # groupicon,
        },
        columns_ids=columns_ids,
        rows=sems,
        html_class="table_leftalign semlist",
        html_sortable=True,
        # base_url = '%s?formsemestre_id=%s' % (request.base_url, formsemestre_id),
        # caption='Maquettes enregistrées',
        preferences=sco_preferences.SemPreferences(),
    )

    return tab


def _style_sems(sems):
    """ajoute quelques attributs de présentation pour la table"""
    for sem in sems:
        sem["notes_url"] = scu.NotesURL()
        sem["_groupicon_target"] = (
            "%(notes_url)s/formsemestre_status?formsemestre_id=%(formsemestre_id)s"
            % sem
        )
        sem["_formsemestre_id_class"] = "blacktt"
        sem["dash_mois_fin"] = '<a title="%(session_id)s"></a> %(anneescolaire)s' % sem
        sem["_dash_mois_fin_class"] = "datesem"
        sem["titre_resp"] = (
            """<a class="stdlink" href="%(notes_url)s/formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titre_num)s</a>
    <span class="respsem">(%(responsable_name)s)</span>"""
            % sem
        )
        sem["_css_row_class"] = "css_S%d css_M%s" % (
            sem["semestre_id"],
            sem["modalite"],
        )
        sem["_semestre_id_class"] = "semestre_id"
        sem["_modalite_class"] = "modalite"
        if sem["semestre_id"] == -1:
            sem["semestre_id_n"] = ""
        else:
            sem["semestre_id_n"] = sem["semestre_id"]


def delete_dept(dept_id: int):
    """Suppression irréversible d'un département et de tous les objets rattachés"""
    assert isinstance(dept_id, int)

    # Un peu complexe, merci JMP :)
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor()
    try:
        # 1- Create temp tables to store ids
        reqs = [
            "create temp table etudids_temp as select id from identite where dept_id = %(dept_id)s",
            "create temp table formsemestres_temp as select id from notes_formsemestre where dept_id = %(dept_id)s",
            "create temp table moduleimpls_temp as select id from notes_moduleimpl where formsemestre_id in (select id from formsemestres_temp)",
            "create temp table formations_temp as select id from notes_formations where dept_id = %(dept_id)s",
            "create temp table entreprises_temp as select id from entreprises where dept_id = %(dept_id)s",
            "create temp table tags_temp as select id from notes_tags where dept_id = %(dept_id)s",
        ]
        for r in reqs:
            cursor.execute(r, {"dept_id": dept_id})

        # 2- Delete student-related informations
        # ordered list of tables
        etud_tables = [
            "notes_notes",
            "group_membership",
            "admissions",
            "billet_absence",
            "adresse",
            "absences",
            "notes_notes_log",
            "notes_moduleimpl_inscription",
            "itemsuivi",
            "notes_appreciations",
            "scolar_autorisation_inscription",
            "absences_notifications",
            "notes_formsemestre_inscription",
            "scolar_formsemestre_validation",
            "scolar_events",
        ]
        for table in etud_tables:
            cursor.execute(
                f"delete from {table} where etudid in (select id from etudids_temp)"
            )

        reqs = [
            "delete from identite where dept_id = %(dept_id)s",
            "delete from sco_prefs where dept_id = %(dept_id)s",
            "delete from notes_semset_formsemestre where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_evaluation where moduleimpl_id in (select id from moduleimpls_temp)",
            "delete from notes_modules_enseignants where moduleimpl_id in (select id from moduleimpls_temp)",
            "delete from notes_formsemestre_uecoef where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_formsemestre_ue_computation_expr where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_formsemestre_responsables where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_moduleimpl where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_modules_tags where tag_id in (select id from tags_temp)",
            "delete from notes_tags where dept_id = %(dept_id)s",
            "delete from notes_modules where formation_id in (select id from formations_temp)",
            "delete from notes_matieres where ue_id in (select id from notes_ue where formation_id in (select id from formations_temp))",
            "delete from notes_formsemestre_etapes where formsemestre_id in (select id from formsemestres_temp)",
            "delete from group_descr where partition_id in (select id from partition where formsemestre_id in (select id from formsemestres_temp))",
            "delete from partition where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_formsemestre_custommenu where formsemestre_id in (select id from formsemestres_temp)",
            "delete from notes_ue where formation_id in (select id from formations_temp)",
            "delete from notes_formsemestre where dept_id = %(dept_id)s",
            "delete from scolar_news where dept_id = %(dept_id)s",
            "delete from notes_semset where dept_id = %(dept_id)s",
            "delete from entreprise_contact where entreprise_id in (select id from entreprises_temp) ",
            "delete from entreprise_correspondant where entreprise_id in (select id from entreprises_temp) ",
            "delete from entreprises where dept_id = %(dept_id)s",
            "delete from notes_formations where dept_id = %(dept_id)s",
            "delete from departement where id = %(dept_id)s",
            "drop table tags_temp",
            "drop table entreprises_temp",
            "drop table formations_temp",
            "drop table moduleimpls_temp",
            "drop table etudids_temp",
            "drop table formsemestres_temp",
        ]
        for r in reqs:
            cursor.execute(r, {"dept_id": dept_id})
    except:
        cnx.rollback()
    finally:
        cnx.commit()
        app.clear_scodoc_cache()
