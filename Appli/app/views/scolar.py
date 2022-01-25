# -*- coding: utf-8 -*-
##############################################################################
#
# ScoDoc
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
Module scolar: vues de .../ScoDoc/<dept>/Scolarite

issu de ScoDoc7 / ZScolar.py

Emmanuel Viennet, 2021
"""
import os
import time

import flask
from flask import jsonify, url_for, flash, render_template, make_response
from flask import current_app, g, request
from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import SubmitField

from app.decorators import (
    scodoc,
    scodoc7func,
    permission_required,
    permission_required_compat_scodoc7,
    admin_required,
    login_required,
)

from app.views import scolar_bp as bp

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.scolog import logdb
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import (
    AccessDenied,
    ScoException,
    ScoValueError,
)
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message
import app
from app.scodoc.gen_tables import GenTable
from app.scodoc import html_sco_header
from app.scodoc import html_sidebar
from app.scodoc import imageresize
from app.scodoc import sco_import_etuds
from app.scodoc import sco_abs
from app.scodoc import sco_archives_etud
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_debouche
from app.scodoc import sco_dept
from app.scodoc import sco_dump_db
from app.scodoc import sco_edt_cal
from app.scodoc import sco_excel
from app.scodoc import sco_find_etud
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_edit
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_groups_edit
from app.scodoc import sco_groups_view
from app.scodoc import sco_logos
from app.scodoc import sco_news
from app.scodoc import sco_page_etud
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_permissions
from app.scodoc import sco_permissions_check
from app.scodoc import sco_photos
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app.scodoc import sco_report
from app.scodoc import sco_synchro_etuds
from app.scodoc import sco_trombino
from app.scodoc import sco_trombino_tours
from app.scodoc import sco_up_to_date
from app.scodoc import sco_etud


def sco_publish(route, function, permission, methods=["GET"]):
    """Declare a route for a python function,
    protected by permission and called following ScoDoc 7 Zope standards.
    """
    return bp.route(route, methods=methods)(
        scodoc(permission_required(permission)(scodoc7func(function)))
    )


# --------------------------------------------------------------------
#
#    SCOLARITE (/ScoDoc/<dept>/Scolarite/...)
#
# --------------------------------------------------------------------


# --------------------------------------------------------------------
#
#    PREFERENCES
#
# --------------------------------------------------------------------


@bp.route("/edit_preferences", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoChangePreferences)
@scodoc7func
def edit_preferences():
    """Edit global preferences (lien "Paramétrage" département)"""
    return sco_preferences.get_base_preferences().edit()


@bp.route("/formsemestre_edit_preferences", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_edit_preferences(formsemestre_id):
    """Edit preferences for a semestre"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    ok = (
        current_user.has_permission(Permission.ScoImplement)
        or ((current_user.id in sem["responsables"]) and sem["resp_can_edit"])
    ) and (sem["etat"])
    if ok:
        return sco_preferences.SemPreferences(formsemestre_id=formsemestre_id).edit()
    else:
        raise AccessDenied(
            "Modification impossible pour %s" % current_user.get_nomplogin()
        )


@bp.route("/doc_preferences")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def doc_preferences():
    """List preferences for wiki documentation"""
    response = make_response(sco_preferences.doc_preferences())
    response.headers["Content-Type"] = "text/plain"
    return response


class DeptLogosConfigurationForm(FlaskForm):
    "Panneau de configuration logos dept"

    logo_header = FileField(
        label="Modifier l'image:",
        description="logo placé en haut des documents PDF",
        validators=[
            FileAllowed(
                scu.LOGOS_IMAGES_ALLOWED_TYPES,
                f"n'accepte que les fichiers image <tt>{','.join([e for e in scu.LOGOS_IMAGES_ALLOWED_TYPES])}</tt>",
            )
        ],
    )

    logo_footer = FileField(
        label="Modifier l'image:",
        description="logo placé en pied des documents PDF",
        validators=[
            FileAllowed(
                scu.LOGOS_IMAGES_ALLOWED_TYPES,
                f"n'accepte que les fichiers image <tt>{','.join([e for e in scu.LOGOS_IMAGES_ALLOWED_TYPES])}</tt>",
            )
        ],
    )

    submit = SubmitField("Enregistrer")


@bp.route("/config_logos", methods=["GET", "POST"])
@permission_required(Permission.ScoChangePreferences)
def config_logos(scodoc_dept):
    "Panneau de configuration général"
    form = DeptLogosConfigurationForm()
    if form.validate_on_submit():
        if form.logo_header.data:
            sco_logos.store_image(
                form.logo_header.data,
                os.path.join(
                    scu.SCODOC_LOGOS_DIR, "logos_" + scodoc_dept, "logo_header"
                ),
            )
        if form.logo_footer.data:
            sco_logos.store_image(
                form.logo_footer.data,
                os.path.join(
                    scu.SCODOC_LOGOS_DIR, "logos_" + scodoc_dept, "logo_footer"
                ),
            )
        app.clear_scodoc_cache()
        flash(f"Logos enregistrés")
        return flask.redirect(url_for("scolar.index_html", scodoc_dept=scodoc_dept))

    return render_template(
        "configuration.html",
        title="Configuration Logos du département",
        form=form,
        scodoc_dept=scodoc_dept,
    )


# --------------------------------------------------------------------
#
#    ETUDIANTS
#
# --------------------------------------------------------------------


@bp.route("/showEtudLog")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def showEtudLog(etudid, format="html"):
    """Display log of operations on this student"""
    etud = sco_etud.get_etud_info(filled=True)[0]

    ops = sco_etud.list_scolog(etudid)

    tab = GenTable(
        titles={
            "date": "Date",
            "authenticated_user": "Utilisateur",
            "remote_addr": "IP",
            "method": "Opération",
            "msg": "Message",
        },
        columns_ids=("date", "authenticated_user", "remote_addr", "method", "msg"),
        rows=ops,
        html_sortable=True,
        html_class="table_leftalign",
        base_url="%s?etudid=%s" % (request.base_url, etudid),
        page_title="Opérations sur %(nomprenom)s" % etud,
        html_title="<h2>Opérations effectuées sur l'étudiant %(nomprenom)s</h2>" % etud,
        filename="log_" + scu.make_filename(etud["nomprenom"]),
        html_next_section=f"""
        <ul><li>
        <a href="{url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)}">
        fiche de {etud['nomprenom']}</a></li>
        </ul>""",
        preferences=sco_preferences.SemPreferences(),
    )

    return tab.make_page(format=format)


# ----------  PAGE ACCUEIL (listes) --------------


@bp.route("/")
@bp.route("/index_html")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def index_html(showcodes=0, showsemtable=0):
    return sco_dept.index_html(showcodes=showcodes, showsemtable=showsemtable)


sco_publish(
    "/trombino", sco_trombino.trombino, Permission.ScoView, methods=["GET", "POST"]
)

sco_publish(
    "/pdf_trombino_tours", sco_trombino_tours.pdf_trombino_tours, Permission.ScoView
)

sco_publish(
    "/pdf_feuille_releve_absences",
    sco_trombino_tours.pdf_feuille_releve_absences,
    Permission.ScoView,
)

sco_publish(
    "/trombino_copy_photos",
    sco_trombino.trombino_copy_photos,
    Permission.ScoView,
    methods=["GET", "POST"],
)


@bp.route("/groups_view")
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
# @permission_required(Permission.ScoView)
@scodoc7func
def groups_view(
    group_ids=(),
    format="html",
    # Options pour listes:
    with_codes=0,
    etat=None,
    with_paiement=0,  # si vrai, ajoute colonnes infos paiement droits et finalisation inscription (lent car interrogation portail)
    with_archives=0,  # ajoute colonne avec noms fichiers archivés
    with_annotations=0,
    formsemestre_id=None,
):
    return sco_groups_view.groups_view(
        group_ids=group_ids,
        format=format,
        # Options pour listes:
        with_codes=with_codes,
        etat=etat,
        with_paiement=with_paiement,  # si vrai, ajoute colonnes infos paiement droits et finalisation inscription (lent car interrogation portail)
        with_archives=with_archives,  # ajoute colonne avec noms fichiers archivés
        with_annotations=with_annotations,
        formsemestre_id=formsemestre_id,
    )


sco_publish(
    "/export_groups_as_moodle_csv",
    sco_groups_view.export_groups_as_moodle_csv,
    Permission.ScoView,
)


# -------------------------- INFOS SUR ETUDIANTS --------------------------
@bp.route("/getEtudInfo")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def getEtudInfo(etudid=False, code_nip=False, filled=False, format=None):
    """infos sur un etudiant (API)
    On peut specifier etudid ou code_nip
    ou bien cherche dans les arguments de la requête: etudid, code_nip, code_ine
    (dans cet ordre).
    """
    etud = sco_etud.get_etud_info(etudid=etudid, code_nip=code_nip, filled=filled)
    if format is None:
        return etud
    else:
        return scu.sendResult(etud, name="etud", format=format)


sco_publish(
    "/search_etud_in_dept",
    sco_find_etud.search_etud_in_dept,
    Permission.ScoView,
    methods=["GET", "POST"],
)


@bp.route("/search_etud_by_name")
@bp.route("/Notes/search_etud_by_name")  # for JS apis
@scodoc
@permission_required(Permission.ScoView)
def search_etud_by_name():
    term = request.args["term"]
    data = sco_find_etud.search_etud_by_name(term)
    return jsonify(data)


# XMLgetEtudInfos était le nom dans l'ancienne API ScoDoc 6
@bp.route("/etud_info", methods=["GET", "POST"])  # pour compat anciens clients PHP)
@bp.route(
    "/XMLgetEtudInfos", methods=["GET", "POST"]
)  # pour compat anciens clients PHP)
@bp.route(
    "/Absences/XMLgetEtudInfos", methods=["GET", "POST"]
)  # pour compat anciens clients PHP
@bp.route(
    "/Notes/XMLgetEtudInfos", methods=["GET", "POST"]
)  # pour compat anciens clients PHP
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def etud_info(etudid=None, format="xml"):
    "Donne les informations sur un etudiant"
    if not format in ("xml", "json"):
        raise ScoValueError("format demandé non supporté par cette fonction.")
    t0 = time.time()
    args = sco_etud.make_etud_args(etudid=etudid)
    cnx = ndb.GetDBConnexion()
    etuds = sco_etud.etudident_list(cnx, args)
    if not etuds:
        # etudiant non trouvé: message d'erreur
        d = {
            "etudid": etudid,
            "nom": "?",
            "nom_usuel": "",
            "prenom": "?",
            "civilite": "?",
            "sexe": "?",  # for backward compat
            "email": "?",
            "emailperso": "",
            "error": "code etudiant inconnu",
        }
        return scu.sendResult(
            d, name="etudiant", format=format, force_outer_xml_tag=False
        )
    d = {}
    etud = etuds[0]
    sco_etud.fill_etuds_info([etud])
    etud["date_naissance_iso"] = ndb.DateDMYtoISO(etud["date_naissance"])
    for a in (
        "etudid",
        "code_nip",
        "code_ine",
        "nom",
        "nom_usuel",
        "prenom",
        "nomprenom",
        "email",
        "emailperso",
        "domicile",
        "codepostaldomicile",
        "villedomicile",
        "paysdomicile",
        "telephone",
        "telephonemobile",
        "fax",
        "bac",
        "specialite",
        "annee_bac",
        "nomlycee",
        "villelycee",
        "codepostallycee",
        "codelycee",
        "date_naissance_iso",
    ):
        d[a] = etud[a]  # ne pas quoter car ElementTree.tostring quote déjà
    d["civilite"] = etud["civilite_str"]  # exception: ne sort pas la civilite brute
    d["sexe"] = d["civilite"]  # backward compat pour anciens clients
    d["photo_url"] = sco_photos.etud_photo_url(etud)

    sem = etud["cursem"]
    if sem:
        sco_groups.etud_add_group_infos(etud, sem)
        d["insemestre"] = [
            {
                "current": "1",
                "formsemestre_id": sem["formsemestre_id"],
                "date_debut": ndb.DateDMYtoISO(sem["date_debut"]),
                "date_fin": ndb.DateDMYtoISO(sem["date_fin"]),
                "etat": sem["ins"]["etat"],
                "groupes": etud["groupes"],  # slt pour semestre courant
            }
        ]
    else:
        d["insemestre"] = []
    for sem in etud["sems"]:
        if sem != etud["cursem"]:
            d["insemestre"].append(
                {
                    "formsemestre_id": sem["formsemestre_id"],
                    "date_debut": ndb.DateDMYtoISO(sem["date_debut"]),
                    "date_fin": ndb.DateDMYtoISO(sem["date_fin"]),
                    "etat": sem["ins"]["etat"],
                }
            )

    log("etud_info (%gs)" % (time.time() - t0))
    return scu.sendResult(
        d, name="etudiant", format=format, force_outer_xml_tag=False, quote_xml=False
    )


# -------------------------- FICHE ETUDIANT --------------------------
sco_publish("/ficheEtud", sco_page_etud.ficheEtud, Permission.ScoView)

sco_publish(
    "/etud_upload_file_form",
    sco_archives_etud.etud_upload_file_form,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/etud_delete_archive",
    sco_archives_etud.etud_delete_archive,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/etud_get_archived_file",
    sco_archives_etud.etud_get_archived_file,
    Permission.ScoView,
)

sco_publish(
    "/etudarchive_import_files_form",
    sco_archives_etud.etudarchive_import_files_form,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/etudarchive_generate_excel_sample",
    sco_archives_etud.etudarchive_generate_excel_sample,
    Permission.ScoView,
)


# Debouche / devenir etudiant
sco_publish(
    "/itemsuivi_suppress",
    sco_debouche.itemsuivi_suppress,
    Permission.ScoEtudChangeAdr,
    methods=["GET", "POST"],
)
sco_publish(
    "/itemsuivi_create",
    sco_debouche.itemsuivi_create,
    Permission.ScoEtudChangeAdr,
    methods=["GET", "POST"],
)
sco_publish(
    "/itemsuivi_set_date",
    sco_debouche.itemsuivi_set_date,
    Permission.ScoEtudChangeAdr,
    methods=["GET", "POST"],
)
sco_publish(
    "/itemsuivi_set_situation",
    sco_debouche.itemsuivi_set_situation,
    Permission.ScoEtudChangeAdr,
    methods=["GET", "POST"],
)
sco_publish(
    "/itemsuivi_list_etud", sco_debouche.itemsuivi_list_etud, Permission.ScoView
)
sco_publish("/itemsuivi_tag_list", sco_debouche.itemsuivi_tag_list, Permission.ScoView)
sco_publish(
    "/itemsuivi_tag_search", sco_debouche.itemsuivi_tag_search, Permission.ScoView
)
sco_publish(
    "/itemsuivi_tag_set",
    sco_debouche.itemsuivi_tag_set,
    Permission.ScoEtudChangeAdr,
    methods=["GET", "POST"],
)


@bp.route("/doAddAnnotation", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudAddAnnotations)
@scodoc7func
def doAddAnnotation(etudid, comment):
    "ajoute annotation sur etudiant"
    cnx = ndb.GetDBConnexion()
    sco_etud.etud_annotations_create(
        cnx,
        args={
            "etudid": etudid,
            "comment": comment,
            "author": current_user.user_name,
        },
    )
    logdb(cnx, method="addAnnotation", etudid=etudid)
    return flask.redirect(
        url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
    )


@bp.route("/doSuppressAnnotation", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def doSuppressAnnotation(etudid, annotation_id):
    """Suppression annotation."""
    if not sco_permissions_check.can_suppress_annotation(annotation_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")

    cnx = ndb.GetDBConnexion()
    annos = sco_etud.etud_annotations_list(cnx, args={"id": annotation_id})
    if len(annos) != 1:
        raise ScoValueError("annotation inexistante !")
    anno = annos[0]
    log("suppress annotation: %s" % str(anno))
    logdb(cnx, method="SuppressAnnotation", etudid=etudid)
    sco_etud.etud_annotations_delete(cnx, annotation_id)

    return flask.redirect(
        url_for(
            "scolar.ficheEtud",
            scodoc_dept=g.scodoc_dept,
            etudid=etudid,
            head_message="Annotation%%20supprimée",
        )
    )


@bp.route("/formChangeCoordonnees", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudChangeAdr)
@scodoc7func
def formChangeCoordonnees(etudid):
    "edit coordonnees etudiant"
    cnx = ndb.GetDBConnexion()
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    adrs = sco_etud.adresse_list(cnx, {"etudid": etudid})
    if adrs:
        adr = adrs[0]
    else:
        adr = {}  # no data for this student
    H = [
        '<h2><font color="#FF0000">Changement des coordonnées de </font> %(nomprenom)s</h2><p>'
        % etud
    ]
    header = html_sco_header.sco_header(
        page_title="Changement adresse de %(nomprenom)s" % etud
    )

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("adresse_id", {"input_type": "hidden"}),
            ("etudid", {"input_type": "hidden"}),
            (
                "email",
                {
                    "size": 40,
                    "title": "e-mail",
                    "explanation": "adresse institutionnelle",
                },
            ),
            (
                "emailperso",
                {
                    "size": 40,
                    "title": "e-mail",
                    "explanation": "adresse personnelle",
                },
            ),
            (
                "domicile",
                {"size": 65, "explanation": "numéro, rue", "title": "Adresse"},
            ),
            ("codepostaldomicile", {"size": 6, "title": "Code postal"}),
            ("villedomicile", {"size": 20, "title": "Ville"}),
            ("paysdomicile", {"size": 20, "title": "Pays"}),
            ("", {"input_type": "separator", "default": "&nbsp;"}),
            ("telephone", {"size": 13, "title": "Téléphone"}),
            ("telephonemobile", {"size": 13, "title": "Mobile"}),
        ),
        initvalues=adr,
        submitlabel="Valider le formulaire",
    )
    dest_url = url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
    if tf[0] == 0:
        return header + "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        if adrs:
            sco_etud.adresse_edit(cnx, args=tf[2])
        else:
            sco_etud.adresse_create(cnx, args=tf[2])
        logdb(cnx, method="changeCoordonnees", etudid=etudid)
        return flask.redirect(dest_url)


# --- Gestion des groupes:
sco_publish(
    "/affect_groups",
    sco_groups_edit.affect_groups,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/XMLgetGroupsInPartition", sco_groups.XMLgetGroupsInPartition, Permission.ScoView
)

sco_publish(
    "/formsemestre_partition_list",
    sco_groups.formsemestre_partition_list,
    Permission.ScoView,
)

sco_publish("/setGroups", sco_groups.setGroups, Permission.ScoView)

sco_publish("/create_group", sco_groups.create_group, Permission.ScoView)


@bp.route("/suppressGroup")  # backward compat (ScoDoc7 API)
@bp.route("/delete_group")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def delete_group(group_id, partition_id):
    sco_groups.delete_group(group_id=group_id, partition_id=partition_id)
    return "", 204


sco_publish(
    "/group_set_name",
    sco_groups.group_set_name,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/group_rename",
    sco_groups.group_rename,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/groups_auto_repartition",
    sco_groups.groups_auto_repartition,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/editPartitionForm",
    sco_groups.editPartitionForm,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/partition_delete",
    sco_groups.partition_delete,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/partition_set_attr",
    sco_groups.partition_set_attr,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/partition_move",
    sco_groups.partition_move,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/partition_set_name",
    sco_groups.partition_set_name,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/partition_rename",
    sco_groups.partition_rename,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/partition_create",
    sco_groups.partition_create,
    Permission.ScoView,
    methods=["GET", "POST"],
)
# @bp.route("/partition_create", methods=["GET", "POST"])
# @scodoc
# @permission_required(Permission.ScoView)
# @scodoc7func
# def partition_create(
#
#     formsemestre_id,
#     partition_name="",
#     default=False,
#     numero=None,
#     redirect=1):
#     return sco_groups.partition_create( formsemestre_id,


sco_publish("/etud_info_html", sco_page_etud.etud_info_html, Permission.ScoView)

# --- Gestion des photos:
sco_publish("/get_photo_image", sco_photos.get_photo_image, Permission.ScoView)

sco_publish("/etud_photo_html", sco_photos.etud_photo_html, Permission.ScoView)


@bp.route("/etud_photo_orig_page")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def etud_photo_orig_page(etudid=None):
    "Page with photo in orig. size"
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    H = [
        html_sco_header.sco_header(page_title=etud["nomprenom"]),
        "<h2>%s</h2>" % etud["nomprenom"],
        '<div><a href="%s">'
        % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
        sco_photos.etud_photo_orig_html(etud),
        "</a></div>",
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


@bp.route("/formChangePhoto", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudChangeAdr)
@scodoc7func
def formChangePhoto(etudid=None):
    """Formulaire changement photo étudiant"""
    etud = sco_etud.get_etud_info(filled=True)[0]
    if sco_photos.etud_photo_is_local(etud):
        etud["photoloc"] = "dans ScoDoc"
    else:
        etud["photoloc"] = "externe"
    H = [
        html_sco_header.sco_header(page_title="Changement de photo"),
        """<h2>Changement de la photo de %(nomprenom)s</h2>
            <p>Photo actuelle (%(photoloc)s):             
            """
        % etud,
        sco_photos.etud_photo_html(etud, title="photo actuelle"),
        """</p><p>Le fichier ne doit pas dépasser 500Ko (recadrer l'image, format "portrait" de préférence).</p>
            <p>L'image sera automagiquement réduite pour obtenir une hauteur de 90 pixels.</p>
            """,
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("etudid", {"default": etudid, "input_type": "hidden"}),
            (
                "photofile",
                {"input_type": "file", "title": "Fichier image", "size": 20},
            ),
        ),
        submitlabel="Valider",
        cancelbutton="Annuler",
    )
    dest_url = url_for(
        "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
    )
    if tf[0] == 0:
        return (
            "\n".join(H)
            + tf[1]
            + '<p><a class="stdlink" href="formSuppressPhoto?etudid=%s">Supprimer cette photo</a></p>'
            % etudid
            + html_sco_header.sco_footer()
        )
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        data = tf[2]["photofile"].read()
        status, diag = sco_photos.store_photo(etud, data)
        if status != 0:
            return flask.redirect(dest_url)
        else:
            H.append('<p class="warning">Erreur:' + diag + "</p>")
    return "\n".join(H) + html_sco_header.sco_footer()


@bp.route("/formSuppressPhoto", methods=["POST", "GET"])
@scodoc
@permission_required(Permission.ScoEtudChangeAdr)
@scodoc7func
def formSuppressPhoto(etudid=None, dialog_confirmed=False):
    """Formulaire suppression photo étudiant"""
    etud = sco_etud.get_etud_info(filled=True)[0]
    if not dialog_confirmed:
        return scu.confirm_dialog(
            "<p>Confirmer la suppression de la photo de %(nomprenom)s ?</p>" % etud,
            dest_url="",
            cancel_url=url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
            ),
            parameters={"etudid": etudid},
        )

    sco_photos.suppress_photo(etud)

    return flask.redirect(
        url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
    )


#
@bp.route("/formDem")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def formDem(etudid, formsemestre_id):
    "Formulaire Démission Etudiant"
    return _formDem_of_Def(
        etudid,
        formsemestre_id,
        operation_name="Démission",
        operation_method="doDemEtudiant",
    )


@bp.route("/formDef")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def formDef(etudid, formsemestre_id):
    "Formulaire Défaillance Etudiant"
    return _formDem_of_Def(
        etudid,
        formsemestre_id,
        operation_name="Défaillance",
        operation_method="doDefEtudiant",
    )


def _formDem_of_Def(
    etudid,
    formsemestre_id,
    operation_name="",
    operation_method="",
):
    "Formulaire démission ou défaillance Etudiant"
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        raise ScoValueError("Modification impossible: semestre verrouille")

    etud["formsemestre_id"] = formsemestre_id
    etud["semtitre"] = sem["titremois"]
    etud["nowdmy"] = time.strftime("%d/%m/%Y")
    etud["operation_name"] = operation_name
    #
    header = html_sco_header.sco_header(
        page_title="%(operation_name)s de  %(nomprenom)s (du semestre %(semtitre)s)"
        % etud,
    )
    H = [
        '<h2><font color="#FF0000">%(operation_name)s de</font> %(nomprenom)s (semestre %(semtitre)s)</h2><p>'
        % etud
    ]
    H.append(
        """<form action="%s" method="get">
    <b>Date de la %s (J/M/AAAA):&nbsp;</b>
    """
        % (operation_method, operation_name.lower())
    )
    H.append(
        """
<input type="text" name="event_date" width=20 value="%(nowdmy)s">
<input type="hidden" name="etudid" value="%(etudid)s">
<input type="hidden" name="formsemestre_id" value="%(formsemestre_id)s">
<p>
<input type="submit" value="Confirmer">
</form>"""
        % etud
    )
    return header + "\n".join(H) + html_sco_header.sco_footer()


@bp.route("/doDemEtudiant")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def doDemEtudiant(etudid, formsemestre_id, event_date=None):
    "Déclare la démission d'un etudiant dans le semestre"
    return _do_dem_or_def_etud(
        etudid,
        formsemestre_id,
        event_date=event_date,
        etat_new="D",
        operation_method="demEtudiant",
        event_type="DEMISSION",
    )


@bp.route("/doDefEtudiant")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def doDefEtudiant(etudid, formsemestre_id, event_date=None):
    "Déclare la défaillance d'un etudiant dans le semestre"
    return _do_dem_or_def_etud(
        etudid,
        formsemestre_id,
        event_date=event_date,
        etat_new=sco_codes_parcours.DEF,
        operation_method="defailleEtudiant",
        event_type="DEFAILLANCE",
    )


def _do_dem_or_def_etud(
    etudid,
    formsemestre_id,
    event_date=None,
    etat_new="D",  # 'D' or DEF
    operation_method="demEtudiant",
    event_type="DEMISSION",
    redirect=True,
):
    "Démission ou défaillance d'un étudiant"
    sco_formsemestre_inscriptions.do_formsemestre_demission(
        etudid,
        formsemestre_id,
        event_date=event_date,
        etat_new=etat_new,  # 'D' or DEF
        operation_method=operation_method,
        event_type=event_type,
    )
    if redirect:
        return flask.redirect(
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )


@bp.route("/doCancelDem", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def doCancelDem(etudid, formsemestre_id, dialog_confirmed=False, args=None):
    "Annule une démission"
    return _do_cancel_dem_or_def(
        etudid,
        formsemestre_id,
        dialog_confirmed=dialog_confirmed,
        args=args,
        operation_name="démission",
        etat_current="D",
        etat_new="I",
        operation_method="cancelDem",
        event_type="DEMISSION",
    )


@bp.route("/doCancelDef", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def doCancelDef(etudid, formsemestre_id, dialog_confirmed=False, args=None):
    "Annule la défaillance de l'étudiant"
    return _do_cancel_dem_or_def(
        etudid,
        formsemestre_id,
        dialog_confirmed=dialog_confirmed,
        args=args,
        operation_name="défaillance",
        etat_current=sco_codes_parcours.DEF,
        etat_new="I",
        operation_method="cancelDef",
        event_type="DEFAILLANCE",
    )


def _do_cancel_dem_or_def(
    etudid,
    formsemestre_id,
    dialog_confirmed=False,
    args=None,
    operation_name="",  # "démission" ou "défaillance"
    etat_current="D",
    etat_new="I",
    operation_method="cancelDem",
    event_type="DEMISSION",
):
    "Annule une demission ou une défaillance"
    # check lock
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        raise ScoValueError("Modification impossible: semestre verrouille")
    # verif
    info = sco_etud.get_etud_info(etudid, filled=True)[0]
    ok = False
    for i in info["ins"]:
        if i["formsemestre_id"] == formsemestre_id:
            if i["etat"] != etat_current:
                raise ScoValueError("etudiant non %s !" % operation_name)
            ok = True
            break
    if not ok:
        raise ScoValueError("etudiant non inscrit ???")
    if not dialog_confirmed:
        return scu.confirm_dialog(
            "<p>Confirmer l'annulation de la %s ?</p>" % operation_name,
            dest_url="",
            cancel_url=url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
            ),
            parameters={"etudid": etudid, "formsemestre_id": formsemestre_id},
        )
    #
    ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        {"etudid": etudid, "formsemestre_id": formsemestre_id}
    )[0]
    if ins["etat"] != etat_current:
        raise ScoException("etudiant non %s !!!" % etat_current)  # obviously a bug
    ins["etat"] = etat_new
    cnx = ndb.GetDBConnexion()
    sco_formsemestre_inscriptions.do_formsemestre_inscription_edit(
        args=ins, formsemestre_id=formsemestre_id
    )
    logdb(cnx, method=operation_method, etudid=etudid)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        "delete from scolar_events where etudid=%(etudid)s and formsemestre_id=%(formsemestre_id)s and event_type='"
        + event_type
        + "'",
        {"etudid": etudid, "formsemestre_id": formsemestre_id},
    )
    cnx.commit()
    return flask.redirect(
        url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
    )


@bp.route("/etudident_create_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def etudident_create_form():
    "formulaire creation individuelle etudiant"
    return _etudident_create_or_edit_form(edit=False)


@bp.route("/etudident_edit_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def etudident_edit_form():
    "formulaire edition individuelle etudiant"
    return _etudident_create_or_edit_form(edit=True)


def _etudident_create_or_edit_form(edit):
    "Le formulaire HTML"
    H = [html_sco_header.sco_header(init_jquery_ui=True)]
    F = html_sco_header.sco_footer()
    vals = scu.get_request_args()
    etudid = vals.get("etudid", None)
    cnx = ndb.GetDBConnexion()
    descr = []
    if not edit:
        # creation nouvel etudiant
        initvalues = {}
        submitlabel = "Ajouter cet étudiant"
        H.append(
            """<h2>Création d'un étudiant</h2>
        <p>En général, il est <b>recommandé</b> d'importer les étudiants depuis Apogée.
        N'utilisez ce formulaire que <b>pour les cas particuliers</b> ou si votre établissement
        n'utilise pas d'autre logiciel de gestion des inscriptions.</p>
        <p><em>L'étudiant créé ne sera pas inscrit.
        Pensez à l'inscrire dans un semestre !</em></p>
        """
        )
    else:
        # edition donnees d'un etudiant existant
        # setup form init values
        if not etudid:
            raise ValueError("missing etudid parameter")
        descr.append(("etudid", {"default": etudid, "input_type": "hidden"}))
        H.append(
            '<h2>Modification d\'un étudiant (<a href="%s">fiche</a>)</h2>'
            % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )
        initvalues = sco_etud.etudident_list(cnx, {"etudid": etudid})
        assert len(initvalues) == 1
        initvalues = initvalues[0]
        submitlabel = "Modifier les données"

    # recuperation infos Apogee
    # Si on a le code NIP, fait juste une requete, sinon tente de rechercher par nom
    # (la recherche par nom ne fonctionne plus à Paris 13)
    # XXX A terminer
    # code_nip = initvalues.get("code_nip", "")
    # if code_nip:
    #     try:
    #         infos = sco_portal_apogee.get_etud_apogee(code_nip)
    #     except ValueError:
    #         infos = None
    #         pass  # XXX a terminer
    vals = scu.get_request_args()
    nom = vals.get("nom", None)
    if nom is None:
        nom = initvalues.get("nom", None)
    if nom is None:
        infos = []
    else:
        prenom = vals.get("prenom", "")
        if vals.get("tf_submitted", False) and not prenom:
            prenom = initvalues.get("prenom", "")
        infos = sco_portal_apogee.get_infos_apogee(nom, prenom)

    if infos:
        formatted_infos = [
            """
        <script type="text/javascript">
        /* <![CDATA[ */
        function copy_nip(nip) {
        document.tf.code_nip.value = nip;
        }
        /* ]]> */
        </script>
        <ol>"""
        ]
        nanswers = len(infos)
        nmax = 10  # nb max de reponse montrees
        infos = infos[:nmax]
        for i in infos:
            formatted_infos.append("<li><ul>")
            for k in i.keys():
                if k != "nip":
                    item = "<li>%s : %s</li>" % (k, i[k])
                else:
                    item = (
                        '<li><form>%s : %s <input type="button" value="copier ce code" onmousedown="copy_nip(%s);"/></form></li>'
                        % (k, i[k], i[k])
                    )
                formatted_infos.append(item)

            formatted_infos.append("</ul></li>")
        formatted_infos.append("</ol>")
        m = "%d étudiants trouvés" % nanswers
        if len(infos) != nanswers:
            m += " (%d montrés)" % len(infos)
        A = """<div class="infoapogee">
        <h5>Informations Apogée</h5>
        <p>%s</p>
        %s
        </div>""" % (
            m,
            "\n".join(formatted_infos),
        )
    else:
        A = """<div class="infoapogee"><p>Pas d'informations d'Apogée</p></div>"""

    require_ine = sco_preferences.get_preference("always_require_ine")

    descr += [
        ("adm_id", {"input_type": "hidden"}),
        ("nom", {"size": 25, "title": "Nom", "allow_null": False}),
        ("nom_usuel", {"size": 25, "title": "Nom usuel", "allow_null": True}),
        (
            "prenom",
            {
                "size": 25,
                "title": "Prénom",
                "allow_null": scu.CONFIG.ALLOW_NULL_PRENOM,
            },
        ),
        (
            "civilite",
            {
                "input_type": "menu",
                "labels": ["Homme", "Femme", "Autre/neutre"],
                "allowed_values": ["M", "F", "X"],
                "title": "Civilité",
            },
        ),
        (
            "date_naissance",
            {
                "title": "Date de naissance",
                "input_type": "date",
                "explanation": "j/m/a",
            },
        ),
        ("lieu_naissance", {"title": "Lieu de naissance", "size": 32}),
        ("dept_naissance", {"title": "Département de naissance", "size": 5}),
        ("nationalite", {"size": 25, "title": "Nationalité"}),
        (
            "statut",
            {
                "size": 25,
                "title": "Statut",
                "explanation": '("salarie", ...) inutilisé par ScoDoc',
            },
        ),
        (
            "annee",
            {
                "size": 5,
                "title": "Année admission IUT",
                "type": "int",
                "allow_null": False,
                "explanation": "année 1ere inscription (obligatoire)",
            },
        ),
        #
        ("sep", {"input_type": "separator", "title": "Scolarité antérieure:"}),
        ("bac", {"size": 5, "explanation": "série du bac (S, STI, STT, ...)"}),
        (
            "specialite",
            {
                "size": 25,
                "title": "Spécialité",
                "explanation": "spécialité bac: SVT M, GENIE ELECTRONIQUE, ...",
            },
        ),
        (
            "annee_bac",
            {
                "size": 5,
                "title": "Année bac",
                "type": "int",
                "explanation": "année obtention du bac",
            },
        ),
        (
            "math",
            {
                "size": 3,
                "type": "float",
                "title": "Note de mathématiques",
                "explanation": "note sur 20 en terminale",
            },
        ),
        (
            "physique",
            {
                "size": 3,
                "type": "float",
                "title": "Note de physique",
                "explanation": "note sur 20 en terminale",
            },
        ),
        (
            "anglais",
            {
                "size": 3,
                "type": "float",
                "title": "Note d'anglais",
                "explanation": "note sur 20 en terminale",
            },
        ),
        (
            "francais",
            {
                "size": 3,
                "type": "float",
                "title": "Note de français",
                "explanation": "note sur 20 obtenue au bac",
            },
        ),
        (
            "type_admission",
            {
                "input_type": "menu",
                "title": "Voie d'admission",
                "allowed_values": scu.TYPES_ADMISSION,
            },
        ),
        (
            "boursier_prec",
            {
                "input_type": "boolcheckbox",
                "labels": ["non", "oui"],
                "title": "Boursier ?",
                "explanation": "dans le cycle précédent (lycée)",
            },
        ),
        (
            "rang",
            {
                "size": 1,
                "type": "int",
                "title": "Position établissement",
                "explanation": "rang de notre établissement dans les voeux du candidat (si connu)",
            },
        ),
        (
            "qualite",
            {
                "size": 3,
                "type": "float",
                "title": "Qualité",
                "explanation": "Note de qualité attribuée au dossier (par le jury d'adm.)",
            },
        ),
        (
            "decision",
            {
                "input_type": "menu",
                "title": "Décision",
                "allowed_values": [
                    "ADMIS",
                    "ATTENTE 1",
                    "ATTENTE 2",
                    "ATTENTE 3",
                    "REFUS",
                    "?",
                ],
            },
        ),
        (
            "score",
            {
                "size": 3,
                "type": "float",
                "title": "Score",
                "explanation": "score calculé lors de l'admission",
            },
        ),
        (
            "classement",
            {
                "size": 3,
                "type": "int",
                "title": "Classement",
                "explanation": "Classement par le jury d'admission (de 1 à N)",
            },
        ),
        ("apb_groupe", {"size": 15, "title": "Groupe APB ou PS"}),
        (
            "apb_classement_gr",
            {
                "size": 3,
                "type": "int",
                "title": "Classement",
                "explanation": "Classement par le jury dans le groupe ABP ou PS (de 1 à Ng)",
            },
        ),
        ("rapporteur", {"size": 50, "title": "Enseignant rapporteur"}),
        (
            "commentaire",
            {
                "input_type": "textarea",
                "rows": 4,
                "cols": 50,
                "title": "Note du rapporteur",
            },
        ),
        ("nomlycee", {"size": 20, "title": "Lycée d'origine"}),
        ("villelycee", {"size": 15, "title": "Commune du lycée"}),
        ("codepostallycee", {"size": 15, "title": "Code Postal lycée"}),
        (
            "codelycee",
            {
                "size": 15,
                "title": "Code Lycée",
                "explanation": "Code national établissement du lycée ou établissement d'origine",
            },
        ),
        ("sep", {"input_type": "separator", "title": "Codes Apogée: (optionnels)"}),
        (
            "code_nip",
            {
                "size": 25,
                "title": "Numéro NIP",
                "allow_null": True,
                "explanation": "numéro identité étudiant (Apogée)",
            },
        ),
        (
            "code_ine",
            {
                "size": 25,
                "title": "Numéro INE",
                "allow_null": not require_ine,
                "explanation": "numéro INE",
            },
        ),
        (
            "dont_check_homonyms",
            {
                "title": "Autoriser les homonymes",
                "input_type": "boolcheckbox",
                "explanation": "ne vérifie pas les noms et prénoms proches",
            },
        ),
    ]
    initvalues["dont_check_homonyms"] = False
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        submitlabel=submitlabel,
        cancelbutton="Re-interroger Apogee",
        initvalues=initvalues,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + "<p>" + A + F
    elif tf[0] == -1:
        return "\n".join(H) + tf[1] + "<p>" + A + F
        # return '\n'.join(H) + '<h4>annulation</h4>' + F
    else:
        # form submission
        if edit:
            etudid = tf[2]["etudid"]
        else:
            etudid = None
        ok, NbHomonyms = sco_etud.check_nom_prenom(
            cnx, nom=tf[2]["nom"], prenom=tf[2]["prenom"], etudid=etudid
        )
        if not ok:
            return (
                "\n".join(H)
                + tf_error_message("Nom ou prénom invalide")
                + tf[1]
                + "<p>"
                + A
                + F
            )
        # log('NbHomonyms=%s' % NbHomonyms)
        if not tf[2]["dont_check_homonyms"] and NbHomonyms > 0:
            return (
                "\n".join(H)
                + tf_error_message(
                    """Attention: il y a déjà un étudiant portant des noms et prénoms proches. Vous pouvez forcer la présence d'un homonyme en cochant "autoriser les homonymes" en bas du formulaire."""
                )
                + tf[1]
                + "<p>"
                + A
                + F
            )

        if not edit:
            etud = sco_etud.create_etud(cnx, args=tf[2])
            etudid = etud["etudid"]
        else:
            # modif d'un etudiant
            sco_etud.etudident_edit(cnx, tf[2])
            etud = sco_etud.etudident_list(cnx, {"etudid": etudid})[0]
            sco_etud.fill_etuds_info([etud])
        # Inval semesters with this student:
        to_inval = [s["formsemestre_id"] for s in etud["sems"]]
        for formsemestre_id in to_inval:
            sco_cache.invalidate_formsemestre(
                formsemestre_id=formsemestre_id
            )  # > etudident_create_or_edit
        #
        return flask.redirect("ficheEtud?etudid=" + str(etudid))


@bp.route("/etudident_delete", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def etudident_delete(etudid, dialog_confirmed=False):
    "Delete a student"
    cnx = ndb.GetDBConnexion()
    etuds = sco_etud.etudident_list(cnx, {"etudid": etudid})
    if not etuds:
        raise ScoValueError("Etudiant inexistant !")
    else:
        etud = etuds[0]
    sco_etud.fill_etuds_info([etud])
    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Confirmer la suppression de l'étudiant <b>{e[nomprenom]}</b> ?</h2>
            </p>
            <p style="top-margin: 2ex; bottom-margin: 2ex;">Prenez le temps de vérifier 
            que vous devez vraiment supprimer cet étudiant !
            </p>
            <p>Cette opération <font color="red"><b>irréversible</b></font>
            efface toute trace de l'étudiant: inscriptions, <b>notes</b>, absences... 
            dans <b>tous les semestres</b> qu'il a fréquenté.
            </p>
            <p>Dans la plupart des cas, vous avez seulement besoin de le <ul>désinscrire</ul> 
            d'un semestre ? (dans ce cas passez par sa fiche, menu associé au semestre)</p>

            <p><a href="{fiche_url}">Vérifier la fiche de {e[nomprenom]}</a>
            </p>""".format(
                e=etud,
                fiche_url=url_for(
                    "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
                ),
            ),
            dest_url="",
            cancel_url=url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
            ),
            OK="Supprimer définitivement cet étudiant",
            parameters={"etudid": etudid},
        )
    log("etudident_delete: etudid=%(etudid)s nomprenom=%(nomprenom)s" % etud)
    # delete in all tables !
    tables = [
        "notes_appreciations",
        "scolar_autorisation_inscription",
        "scolar_formsemestre_validation",
        "scolar_events",
        "notes_notes_log",
        "notes_notes",
        "notes_moduleimpl_inscription",
        "notes_formsemestre_inscription",
        "group_membership",
        "entreprise_contact",
        "etud_annotations",
        "scolog",
        "admissions",
        "adresse",
        "absences",
        "absences_notifications",
        "billet_absence",
    ]
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    for table in tables:
        cursor.execute("delete from %s where etudid=%%(etudid)s" % table, etud)
    cursor.execute("delete from identite where id=%(etudid)s", etud)
    cnx.commit()
    # Inval semestres où il était inscrit:
    to_inval = [s["formsemestre_id"] for s in etud["sems"]]
    for formsemestre_id in to_inval:
        sco_cache.invalidate_formsemestre(formsemestre_id=formsemestre_id)  # >
    return flask.redirect(scu.ScoURL() + r"?head_message=Etudiant%20supprimé")


@bp.route("/check_group_apogee")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def check_group_apogee(group_id, etat=None, fix=False, fixmail=False):
    """Verification des codes Apogee et mail de tout un groupe.
    Si fix == True, change les codes avec Apogée.

    XXX A re-écrire pour API 2: prendre liste dans l'étape et vérifier à partir de cela.
    """
    etat = etat or None
    members, group, _, sem, _ = sco_groups.get_group_infos(group_id, etat=etat)
    formsemestre_id = group["formsemestre_id"]

    cnx = ndb.GetDBConnexion()
    H = [
        html_sco_header.html_sem_header(
            "Etudiants du %s" % (group["group_name"] or "semestre"),
            sem,
        ),
        '<table class="sortable" id="listegroupe">',
        "<tr><th>Nom</th><th>Nom usuel</th><th>Prénom</th><th>Mail</th><th>NIP (ScoDoc)</th><th>Apogée</th></tr>",
    ]
    nerrs = 0  # nombre d'anomalies détectées
    nfix = 0  # nb codes changes
    nmailmissing = 0  # nb etuds sans mail
    for t in members:
        nom, nom_usuel, prenom, etudid, email, code_nip = (
            t["nom"],
            t["nom_usuel"],
            t["prenom"],
            t["etudid"],
            t["email"],
            t["code_nip"],
        )
        infos = sco_portal_apogee.get_infos_apogee(nom, prenom)
        if not infos:
            info_apogee = (
                '<b>Pas d\'information</b> (<a href="etudident_edit_form?etudid=%s">Modifier identité</a>)'
                % etudid
            )
            nerrs += 1
        else:
            if len(infos) == 1:
                nip_apogee = infos[0]["nip"]
                if code_nip != nip_apogee:
                    if fix:
                        # Update database
                        sco_etud.identite_edit(
                            cnx,
                            args={"etudid": etudid, "code_nip": nip_apogee},
                        )
                        info_apogee = (
                            '<span style="color:green">copié %s</span>' % nip_apogee
                        )
                        nfix += 1
                    else:
                        info_apogee = '<span style="color:red">%s</span>' % nip_apogee
                        nerrs += 1
                else:
                    info_apogee = "ok"
            else:
                info_apogee = (
                    '<b>%d correspondances</b> (<a href="etudident_edit_form?etudid=%s">Choisir</a>)'
                    % (len(infos), etudid)
                )
                nerrs += 1
        # check mail
        if email:
            mailstat = "ok"
        else:
            if fixmail and len(infos) == 1 and "mail" in infos[0]:
                mail_apogee = infos[0]["mail"]
                adrs = sco_etud.adresse_list(cnx, {"etudid": etudid})
                if adrs:
                    adr = adrs[0]  # modif adr existante
                    args = {"adresse_id": adr["adresse_id"], "email": mail_apogee}
                    sco_etud.adresse_edit(cnx, args=args, disable_notify=True)
                else:
                    # creation adresse
                    args = {"etudid": etudid, "email": mail_apogee}
                    sco_etud.adresse_create(cnx, args=args)
                mailstat = '<span style="color:green">copié</span>'
            else:
                mailstat = "inconnu"
                nmailmissing += 1
        H.append(
            '<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            % (
                url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
                nom,
                nom_usuel,
                prenom,
                mailstat,
                code_nip,
                info_apogee,
            )
        )
    H.append("</table>")
    H.append("<ul>")
    if nfix:
        H.append("<li><b>%d</b> codes modifiés</li>" % nfix)
    H.append("<li>Codes NIP: <b>%d</b> anomalies détectées</li>" % nerrs)
    H.append("<li>Adresse mail: <b>%d</b> étudiants sans adresse</li>" % nmailmissing)
    H.append("</ul>")
    H.append(
        """
    <form method="get" action="%s">
    <input type="hidden" name="formsemestre_id" value="%s"/>
    <input type="hidden" name="group_id" value="%s"/>
    <input type="hidden" name="etat" value="%s"/>
    <input type="hidden" name="fix" value="1"/>
    <input type="submit" value="Mettre à jour les codes NIP depuis Apogée"/>
    </form>
    <p><a href="Notes/formsemestre_status?formsemestre_id=%s"> Retour au semestre</a>
    """
        % (
            request.base_url,
            formsemestre_id,
            scu.strnone(group_id),
            scu.strnone(etat),
            formsemestre_id,
        )
    )
    H.append(
        """
    <form method="get" action="%s">
    <input type="hidden" name="formsemestre_id" value="%s"/>
    <input type="hidden" name="group_id" value="%s"/>
    <input type="hidden" name="etat" value="%s"/>
    <input type="hidden" name="fixmail" value="1"/>
    <input type="submit" value="Renseigner les e-mail manquants (adresse institutionnelle)"/>
    </form>
    <p><a href="Notes/formsemestre_status?formsemestre_id=%s"> Retour au semestre</a>
    """
        % (
            request.base_url,
            formsemestre_id,
            scu.strnone(group_id),
            scu.strnone(etat),
            formsemestre_id,
        )
    )

    return "\n".join(H) + html_sco_header.sco_footer()


@bp.route("/form_students_import_excel", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def form_students_import_excel(formsemestre_id=None):
    "formulaire import xls"
    formsemestre_id = int(formsemestre_id) if formsemestre_id else None
    if formsemestre_id:
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        dest_url = (
            # scu.ScoURL() + "/formsemestre_status?formsemestre_id=%s" % formsemestre_id  # TODO: Remplacer par for_url ?
            url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
            )
        )
    else:
        sem = None
        dest_url = scu.ScoURL()
    if sem and not sem["etat"]:
        raise ScoValueError("Modification impossible: semestre verrouille")
    H = [
        html_sco_header.sco_header(page_title="Import etudiants"),
        """<h2 class="formsemestre">Téléchargement d\'une nouvelle liste d\'etudiants</h2>
            <div style="color: red">
            <p>A utiliser pour importer de <b>nouveaux</b> étudiants (typiquement au
            <b>premier semestre</b>).</p>
            <p>Si les étudiants à inscrire sont déjà dans un autre
            semestre, utiliser le menu "<em>Inscriptions (passage des étudiants)
            depuis d'autres semestres</em> à partir du semestre destination.
            </p>
            <p>Si vous avez un portail Apogée, il est en général préférable d'importer les
            étudiants depuis Apogée, via le menu "<em>Synchroniser avec étape Apogée</em>".
            </p>
            </div>
            <p>
            L'opération se déroule en deux étapes. Dans un premier temps,
            vous téléchargez une feuille Excel type. Vous devez remplir
            cette feuille, une ligne décrivant chaque étudiant. Ensuite,
            vous indiquez le nom de votre fichier dans la case "Fichier Excel"
            ci-dessous, et cliquez sur "Télécharger" pour envoyer au serveur
            votre liste.
            </p>
            """,
    ]  # '
    if sem:
        H.append(
            """<p style="color: red">Les étudiants importés seront inscrits dans
        le semestre <b>%s</b></p>"""
            % sem["titremois"]
        )
    else:
        H.append(
            """
            <p>Pour inscrire directement les étudiants dans un semestre de
            formation, il suffit d'indiquer le code de ce semestre
            (qui doit avoir été créé au préalable). <a class="stdlink" href="%s?showcodes=1">Cliquez ici pour afficher les codes</a>
            </p>
            """
            % (scu.ScoURL())
        )

    H.append("""<ol><li>""")
    if formsemestre_id:
        H.append(
            """
        <a class="stdlink" href="import_generate_excel_sample?with_codesemestre=0">
        """
        )
    else:
        H.append("""<a class="stdlink" href="import_generate_excel_sample">""")
    H.append(
        """Obtenir la feuille excel à remplir</a></li>
    <li>"""
    )

    F = html_sco_header.sco_footer()
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "csvfile",
                {"title": "Fichier Excel:", "input_type": "file", "size": 40},
            ),
            (
                "check_homonyms",
                {
                    "title": "Vérifier les homonymes",
                    "input_type": "boolcheckbox",
                    "explanation": "arrète l'importation si plus de 10% d'homonymes",
                },
            ),
            (
                "require_ine",
                {
                    "title": "Importer INE",
                    "input_type": "boolcheckbox",
                    "explanation": "n'importe QUE les étudiants avec nouveau code INE",
                },
            ),
            ("formsemestre_id", {"input_type": "hidden"}),
        ),
        initvalues={"check_homonyms": True, "require_ine": False},
        submitlabel="Télécharger",
    )
    S = [
        """<hr/><p>Le fichier Excel décrivant les étudiants doit comporter les colonnes suivantes.
<p>Les colonnes peuvent être placées dans n'importe quel ordre, mais
le <b>titre</b> exact (tel que ci-dessous) doit être sur la première ligne.
</p>
<p>
Les champs avec un astérisque (*) doivent être présents (nulls non autorisés).
</p>


<p>
<table>
<tr><td><b>Attribut</b></td><td><b>Type</b></td><td><b>Description</b></td></tr>"""
    ]
    for t in sco_import_etuds.sco_import_format(
        with_codesemestre=(formsemestre_id == None)
    ):
        if int(t[3]):
            ast = ""
        else:
            ast = "*"
        S.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (t[0], t[1], t[4], ast)
        )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + "</li></ol>" + "\n".join(S) + F
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        return sco_import_etuds.students_import_excel(
            tf[2]["csvfile"],
            formsemestre_id=int(formsemestre_id) if formsemestre_id else None,
            check_homonyms=tf[2]["check_homonyms"],
            require_ine=tf[2]["require_ine"],
        )


@bp.route("/import_generate_excel_sample")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def import_generate_excel_sample(with_codesemestre="1"):
    "une feuille excel pour importation etudiants"
    if with_codesemestre:
        with_codesemestre = int(with_codesemestre)
    else:
        with_codesemestre = 0
    format = sco_import_etuds.sco_import_format()
    data = sco_import_etuds.sco_import_generate_excel_sample(
        format, with_codesemestre, exclude_cols=["photo_filename"]
    )
    return scu.send_file(
        data, "ImportEtudiants", scu.XLSX_SUFFIX, mime=scu.XLSX_MIMETYPE
    )
    # return sco_excel.send_excel_file(data, "ImportEtudiants" + scu.XLSX_SUFFIX)


# --- Données admission
@bp.route("/import_generate_admission_sample")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def import_generate_admission_sample(formsemestre_id):
    "une feuille excel pour importation données admissions"
    group = sco_groups.get_group(sco_groups.get_default_group(formsemestre_id))
    fmt = sco_import_etuds.sco_import_format()
    data = sco_import_etuds.sco_import_generate_excel_sample(
        fmt,
        only_tables=["identite", "admissions", "adresse"],
        exclude_cols=["nationalite", "foto", "photo_filename"],
        group_ids=[group["group_id"]],
    )
    return scu.send_file(
        data, "AdmissionEtudiants", scu.XLSX_SUFFIX, mime=scu.XLSX_MIMETYPE
    )
    # return sco_excel.send_excel_file(data, "AdmissionEtudiants" + scu.XLSX_SUFFIX)


# --- Données admission depuis fichier excel (version nov 2016)
@bp.route("/form_students_import_infos_admissions", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def form_students_import_infos_admissions(formsemestre_id=None):
    "formulaire import xls"
    authuser = current_user
    F = html_sco_header.sco_footer()
    if not authuser.has_permission(Permission.ScoEtudInscrit):
        # autorise juste l'export
        H = [
            html_sco_header.sco_header(
                page_title="Export données admissions (Parcoursup ou autre)",
            ),
            """<h2 class="formsemestre">Téléchargement des informations sur l'admission des étudiants</h2>
            <p>
            <a href="import_generate_admission_sample?formsemestre_id=%(formsemestre_id)s">Exporter les informations de ScoDoc (classeur Excel)</a> (ce fichier peut être ré-importé après d'éventuelles modifications)
            </p>
            <p class="warning">Vous n'avez pas le droit d'importer les données</p>
            """
            % {"formsemestre_id": formsemestre_id},
        ]
        return "\n".join(H) + F

    # On a le droit d'importer:
    H = [
        html_sco_header.sco_header(page_title="Import données admissions Parcoursup"),
        """<h2 class="formsemestre">Téléchargement des informations sur l'admission des étudiants depuis feuilles import Parcoursup</h2>
            <div style="color: red">
            <p>A utiliser pour renseigner les informations sur l'origine des étudiants (lycées, bac, etc). Ces informations sont facultatives mais souvent utiles pour mieux connaitre les étudiants et aussi pour effectuer des statistiques (résultats suivant le type de bac...). Les données sont affichées sur les fiches individuelles des étudiants.</p>
            </div>
            <p>
            Importer ici la feuille excel utilisée pour envoyer le classement Parcoursup. 
            Seuls les étudiants actuellement inscrits dans ce semestre ScoDoc seront affectés, 
            les autres lignes de la feuille seront ignorées. Et seules les colonnes intéressant ScoDoc 
            seront importées: il est inutile d'éliminer les autres.
            <br/>
            <em>Seules les données "admission" seront modifiées (et pas l'identité de l'étudiant).</em>
            <br/>
            <em>Les colonnes "nom" et "prenom" sont requises, ou bien une colonne "etudid".</em>
            </p>
            <p>
            Avant d'importer vos données, il est recommandé d'enregistrer les informations actuelles:
            <a href="import_generate_admission_sample?formsemestre_id=%(formsemestre_id)s">exporter les données actuelles de ScoDoc</a> (ce fichier peut être ré-importé après d'éventuelles modifications)
            </p>
            """
        % {"formsemestre_id": formsemestre_id},
    ]  # '

    type_admission_list = (
        "Autre",
        "Parcoursup",
        "Parcoursup PC",
        "APB",
        "APB PC",
        "CEF",
        "Direct",
    )

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "csvfile",
                {"title": "Fichier Excel:", "input_type": "file", "size": 40},
            ),
            (
                "type_admission",
                {
                    "title": "Type d'admission",
                    "explanation": "sera attribué aux étudiants modifiés par cet import n'ayant pas déjà un type",
                    "input_type": "menu",
                    "allowed_values": type_admission_list,
                },
            ),
            ("formsemestre_id", {"input_type": "hidden"}),
        ),
        submitlabel="Télécharger",
    )

    help_text = (
        """<p>Les colonnes importables par cette fonction sont indiquées dans la table ci-dessous. 
    Seule la première feuille du classeur sera utilisée.
    <div id="adm_table_description_format">
    """
        + sco_import_etuds.adm_table_description_format().html()
        + """</div>"""
    )

    if tf[0] == 0:
        return "\n".join(H) + tf[1] + help_text + F
    elif tf[0] == -1:
        return flask.redirect(
            scu.ScoURL()
            + "/formsemestre_status?formsemestre_id="
            + str(formsemestre_id)
        )
    else:
        return sco_import_etuds.students_import_admission(
            tf[2]["csvfile"],
            type_admission=tf[2]["type_admission"],
            formsemestre_id=formsemestre_id,
        )


@bp.route("/formsemestre_import_etud_admission")
@scodoc
@permission_required(Permission.ScoEtudChangeAdr)
@scodoc7func
def formsemestre_import_etud_admission(formsemestre_id, import_email=True):
    """Reimporte donnees admissions par synchro Portail Apogée"""
    (
        no_nip,
        unknowns,
        changed_mails,
    ) = sco_synchro_etuds.formsemestre_import_etud_admission(
        formsemestre_id, import_identite=True, import_email=import_email
    )
    H = [
        html_sco_header.html_sem_header("Reimport données admission"),
        "<h3>Opération effectuée</h3>",
    ]
    if no_nip:
        H.append("<p>Attention: étudiants sans NIP: " + str(no_nip) + "</p>")
    if unknowns:
        H.append(
            "<p>Attention: étudiants inconnus du portail: codes NIP="
            + str(unknowns)
            + "</p>"
        )
    if changed_mails:
        H.append("<h3>Adresses mails modifiées:</h3>")
        for (info, new_mail) in changed_mails:
            H.append(
                "%s: <tt>%s</tt> devient <tt>%s</tt><br/>"
                % (info["nom"], info["email"], new_mail)
            )
    return "\n".join(H) + html_sco_header.sco_footer()


sco_publish(
    "/photos_import_files_form",
    sco_trombino.photos_import_files_form,
    Permission.ScoEtudChangeAdr,
    methods=["GET", "POST"],
)
sco_publish(
    "/photos_generate_excel_sample",
    sco_trombino.photos_generate_excel_sample,
    Permission.ScoEtudChangeAdr,
)

# --- Statistiques
@bp.route("/stat_bac")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def stat_bac(formsemestre_id):
    "Renvoie statistisques sur nb d'etudiants par bac"
    cnx = ndb.GetDBConnexion()
    ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id}
    )
    Bacs = {}  # type bac : nb etud
    for i in ins:
        etud = sco_etud.etudident_list(cnx, {"etudid": i["etudid"]})[0]
        typebac = "%(bac)s %(specialite)s" % etud
        Bacs[typebac] = Bacs.get(typebac, 0) + 1
    return Bacs


# --- Dump
sco_publish(
    "/sco_dump_and_send_db", sco_dump_db.sco_dump_and_send_db, Permission.ScoView
)
