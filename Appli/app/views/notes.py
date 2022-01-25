# -*- mode: python -*-
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
Module notes: issu de ScoDoc7 / ZNotes.py

Emmanuel Viennet, 2021
"""
import sys
import time
import datetime
import pprint
from operator import itemgetter
from xml.etree import ElementTree

import flask
from flask import url_for
from flask import current_app, g, request
from flask_login import current_user
from werkzeug.utils import redirect

from config import Config

from app import api
from app import db
from app import models
from app.auth.models import User

from app.decorators import (
    scodoc,
    scodoc7func,
    permission_required,
    permission_required_compat_scodoc7,
    admin_required,
    login_required,
)

from app.views import notes_bp as bp

# ---------------

from app.scodoc import sco_utils as scu
from app.scodoc import notesdb as ndb
from app import log, send_scodoc_alarm

from app.scodoc import scolog
from app.scodoc.scolog import logdb

from app.scodoc.sco_exceptions import (
    ScoValueError,
    ScoLockedFormError,
    ScoGenError,
    AccessDenied,
)
from app.scodoc import html_sco_header
from app.pe import pe_view
from app.scodoc import sco_abs
from app.scodoc import sco_apogee_compare
from app.scodoc import sco_archives
from app.scodoc import sco_bulletins
from app.scodoc import sco_bulletins_pdf
from app.scodoc import sco_cache
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_compute_moy
from app.scodoc import sco_cost_formation
from app.scodoc import sco_debouche
from app.scodoc import sco_edit_formation
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_etape_apogee_view
from app.scodoc import sco_etud
from app.scodoc import sco_evaluations
from app.scodoc import sco_excel
from app.scodoc import sco_export_results
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_custommenu
from app.scodoc import sco_formsemestre_edit
from app.scodoc import sco_formsemestre_exterieurs
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_formsemestre_validation
from app.scodoc import sco_groups
from app.scodoc import sco_inscr_passage
from app.scodoc import sco_liste_notes
from app.scodoc import sco_lycee
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_moduleimpl_inscriptions
from app.scodoc import sco_moduleimpl_status
from app.scodoc import sco_news
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_permissions_check
from app.scodoc import sco_placement
from app.scodoc import sco_poursuite_dut
from app.scodoc import sco_preferences
from app.scodoc import sco_prepajury
from app.scodoc import sco_pvjury
from app.scodoc import sco_pvpdf
from app.scodoc import sco_recapcomplet
from app.scodoc import sco_report
from app.scodoc import sco_saisie_notes
from app.scodoc import sco_semset
from app.scodoc import sco_synchro_etuds
from app.scodoc import sco_tag_module
from app.scodoc import sco_ue_external
from app.scodoc import sco_undo_notes
from app.scodoc import sco_users
from app.scodoc import sco_xml
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_pdf import PDFLOCK
from app.scodoc.sco_permissions import Permission
from app.scodoc.TrivialFormulator import TrivialFormulator


def sco_publish(route, function, permission, methods=["GET"]):
    """Declare a route for a python function,
    protected by permission and called following ScoDoc 7 Zope standards.
    """
    return bp.route(route, methods=methods)(
        scodoc(permission_required(permission)(scodoc7func(function)))
    )


# ---------------------  Quelques essais élémentaires:
# @bp.route("/essai")
# @scodoc
# @permission_required(Permission.ScoView)
# @scodoc7func
# def essai():
#     return essai_()


# def essai_():
#     return "<html><body><h2>essai !</h2><p>%s</p></body></html>" % ()


# def essai2():
#     err_page = f"""<h3>Destruction du module impossible car il est utilisé dans des semestres existants !</h3>
#     <p class="help">Il faut d'abord supprimer le semestre. Mais il est peut être préférable de
#     laisser ce programme intact et d'en créer une nouvelle version pour la modifier.
#     </p>
#     <a href="url_for('notes.ue_table', scodoc-dept=g.scodoc_dept, formation_id='XXX')">reprendre</a>
#     """
#     raise ScoGenError(err_page)
#     # raise ScoGenError("une erreur banale")
#     return essai_("sans request")


# sco_publish("/essai2", essai2, Permission.ScoImplement)


# --------------------------------------------------------------------
#
#    Notes/ methods
#
# --------------------------------------------------------------------

sco_publish(
    "/formsemestre_status",
    sco_formsemestre_status.formsemestre_status,
    Permission.ScoView,
)

sco_publish(
    "/formsemestre_createwithmodules",
    sco_formsemestre_edit.formsemestre_createwithmodules,
    Permission.ScoImplement,
    methods=["GET", "POST"],
)

# controle d'acces specifique pour dir. etud:
sco_publish(
    "/formsemestre_editwithmodules",
    sco_formsemestre_edit.formsemestre_editwithmodules,
    Permission.ScoView,
    methods=["GET", "POST"],
)

sco_publish(
    "/formsemestre_clone",
    sco_formsemestre_edit.formsemestre_clone,
    Permission.ScoImplement,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_associate_new_version",
    sco_formsemestre_edit.formsemestre_associate_new_version,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_delete",
    sco_formsemestre_edit.formsemestre_delete,
    Permission.ScoImplement,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_delete2",
    sco_formsemestre_edit.formsemestre_delete2,
    Permission.ScoImplement,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_recapcomplet",
    sco_recapcomplet.formsemestre_recapcomplet,
    Permission.ScoView,
)
sco_publish(
    "/formsemestres_bulletins",
    sco_recapcomplet.formsemestres_bulletins,
    Permission.ScoObservateur,
)
sco_publish(
    "/moduleimpl_status", sco_moduleimpl_status.moduleimpl_status, Permission.ScoView
)
sco_publish(
    "/formsemestre_description",
    sco_formsemestre_status.formsemestre_description,
    Permission.ScoView,
)

sco_publish(
    "/formation_create",
    sco_edit_formation.formation_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/formation_delete",
    sco_edit_formation.formation_delete,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/formation_edit",
    sco_edit_formation.formation_edit,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)


@bp.route(
    "/formsemestre_bulletinetud", methods=["GET", "POST"]
)  # POST pour compat anciens clients PHP (deprecated)
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def formsemestre_bulletinetud(
    etudid=None,
    formsemestre_id=None,
    format="html",
    version="long",
    xml_with_decisions=False,
    force_publishing=False,
    prefer_mail_perso=False,
    code_nip=None,
):
    if not (etudid or code_nip):
        raise ScoValueError("Paramètre manquant: spécifier code_nip ou etudid")
    if not formsemestre_id:
        raise ScoValueError("Paramètre manquant: formsemestre_id est requis")
    return sco_bulletins.formsemestre_bulletinetud(
        etudid=etudid,
        formsemestre_id=formsemestre_id,
        format=format,
        version=version,
        xml_with_decisions=xml_with_decisions,
        force_publishing=force_publishing,
        prefer_mail_perso=prefer_mail_perso,
    )


sco_publish(
    "/formsemestre_evaluations_cal",
    sco_evaluations.formsemestre_evaluations_cal,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_evaluations_delai_correction",
    sco_evaluations.formsemestre_evaluations_delai_correction,
    Permission.ScoView,
)
sco_publish(
    "/module_evaluation_renumber",
    sco_evaluations.module_evaluation_renumber,
    Permission.ScoView,
)
sco_publish(
    "/module_evaluation_move",
    sco_evaluations.module_evaluation_move,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_list_saisies_notes",
    sco_undo_notes.formsemestre_list_saisies_notes,
    Permission.ScoView,
)
sco_publish(
    "/ue_create",
    sco_edit_ue.ue_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/ue_delete",
    sco_edit_ue.ue_delete,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/ue_edit",
    sco_edit_ue.ue_edit,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)


@bp.route("/ue_list")  # backward compat
@bp.route("/ue_table")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def ue_table(formation_id=None, msg=""):
    return sco_edit_ue.ue_table(formation_id=formation_id, msg=msg)


@bp.route("/ue_set_internal", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoChangeFormation)
@scodoc7func
def ue_set_internal(ue_id):
    """"""
    ue = models.formations.NotesUE.query.get(ue_id)
    if not ue:
        raise ScoValueError("invalid ue_id")
    ue.is_external = False
    db.session.add(ue)
    db.session.commit()
    # Invalide les semestres de cette formation
    sco_edit_formation.invalidate_sems_in_formation(ue.formation_id)
    return redirect(
        url_for(
            "notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=ue.formation_id
        )
    )


sco_publish("/ue_sharing_code", sco_edit_ue.ue_sharing_code, Permission.ScoView)
sco_publish(
    "/edit_ue_set_code_apogee",
    sco_edit_ue.edit_ue_set_code_apogee,
    Permission.ScoChangeFormation,
)
sco_publish(
    "/formsemestre_edit_uecoefs",
    sco_formsemestre_edit.formsemestre_edit_uecoefs,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/formation_table_recap", sco_edit_ue.formation_table_recap, Permission.ScoView
)
sco_publish(
    "/formation_add_malus_modules",
    sco_edit_module.formation_add_malus_modules,
    Permission.ScoChangeFormation,
)
sco_publish(
    "/matiere_create",
    sco_edit_matiere.matiere_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/matiere_delete",
    sco_edit_matiere.matiere_delete,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/matiere_edit",
    sco_edit_matiere.matiere_edit,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/module_create",
    sco_edit_module.module_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/module_delete",
    sco_edit_module.module_delete,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/module_edit",
    sco_edit_module.module_edit,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/edit_module_set_code_apogee",
    sco_edit_module.edit_module_set_code_apogee,
    Permission.ScoChangeFormation,
)
sco_publish("/module_list", sco_edit_module.module_table, Permission.ScoView)
sco_publish("/module_tag_search", sco_tag_module.module_tag_search, Permission.ScoView)
sco_publish(
    "/module_tag_set",
    sco_tag_module.module_tag_set,
    Permission.ScoEditFormationTags,
    methods=["GET", "POST"],
)

#
@bp.route("/")
@bp.route("/index_html")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def index_html():
    "Page accueil formations"

    editable = current_user.has_permission(Permission.ScoChangeFormation)

    H = [
        html_sco_header.sco_header(page_title="Programmes formations"),
        """<h2>Programmes pédagogiques</h2>
            """,
    ]
    T = sco_formations.formation_list_table()

    H.append(T.html())

    if editable:
        H.append(
            """<p><a class="stdlink" href="formation_create" id="link-create-formation">Créer une formation</a></p>
    <p><a class="stdlink" href="formation_import_xml_form">Importer une formation (xml)</a></p>
        <p class="help">Une "formation" est un programme pédagogique structuré en UE, matières et modules. Chaque semestre se réfère à une formation. La modification d'une formation affecte tous les semestres qui s'y réfèrent.</p>
        """
        )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


# --------------------------------------------------------------------
#
#    Notes Methods
#
# --------------------------------------------------------------------

# --- Formations

sco_publish(
    "/do_formation_create",
    sco_edit_formation.do_formation_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)

sco_publish(
    "/do_formation_delete",
    sco_edit_formation.do_formation_delete,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)


@bp.route("/formation_list")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formation_list(format=None, formation_id=None, args={}):
    """List formation(s) with given id, or matching args
    (when args is given, formation_id is ignored).
    """
    r = sco_formations.formation_list(formation_id=formation_id, args=args)
    return scu.sendResult(r, name="formation", format=format)


@bp.route("/formation_export")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formation_export(formation_id, export_ids=False, format=None):
    "Export de la formation au format indiqué (xml ou json)"
    return sco_formations.formation_export(
        formation_id, export_ids=export_ids, format=format
    )


@bp.route("/formation_import_xml")
@scodoc
@permission_required(Permission.ScoChangeFormation)
@scodoc7func
def formation_import_xml(file):
    "import d'une formation en XML"
    log("formation_import_xml")
    doc = file.read()
    return sco_formations.formation_import_xml(doc)


@bp.route("/formation_import_xml_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoChangeFormation)
@scodoc7func
def formation_import_xml_form():
    "form import d'une formation en XML"
    H = [
        html_sco_header.sco_header(page_title="Import d'une formation"),
        """<h2>Import d'une formation</h2>
    <p>Création d'une formation (avec UE, matières, modules)
    à partir un fichier XML (réservé aux utilisateurs avertis)</p>
    """,
    ]
    footer = html_sco_header.sco_footer()
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("xmlfile", {"input_type": "file", "title": "Fichier XML", "size": 30}),),
        submitlabel="Importer",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + footer
    elif tf[0] == -1:
        return flask.redirect(scu.NotesURL())
    else:
        formation_id, _, _ = sco_formations.formation_import_xml(
            tf[2]["xmlfile"].read()
        )

        return (
            "\n".join(H)
            + """<p>Import effectué !</p>
        <p><a class="stdlink" href="ue_list?formation_id=%s">Voir la formation</a></p>"""
            % formation_id
            + footer
        )


sco_publish(
    "/formation_create_new_version",
    sco_formations.formation_create_new_version,
    Permission.ScoChangeFormation,
)

# --- UE
sco_publish(
    "/do_ue_create",
    sco_edit_ue.do_ue_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)

sco_publish(
    "/ue_list",
    sco_edit_ue.ue_list,
    Permission.ScoView,
)


# --- Matieres
sco_publish(
    "/do_matiere_create",
    sco_edit_matiere.do_matiere_create,
    Permission.ScoChangeFormation,
    methods=["GET", "POST"],
)
sco_publish(
    "/do_matiere_delete",
    sco_edit_matiere.do_matiere_delete,
    Permission.ScoChangeFormation,
)


# --- Modules
sco_publish(
    "/do_module_delete",
    sco_edit_module.do_module_delete,
    Permission.ScoChangeFormation,
)


@bp.route("/formation_count_sems")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formation_count_sems(formation_id):
    "Number of formsemestre in this formation (locked or not)"
    sems = sco_formsemestre.do_formsemestre_list(args={"formation_id": formation_id})
    return len(sems)


sco_publish(
    "/module_count_moduleimpls",
    sco_edit_module.module_count_moduleimpls,
    Permission.ScoView,
)

sco_publish("/module_is_locked", sco_edit_module.module_is_locked, Permission.ScoView)

sco_publish(
    "/matiere_is_locked", sco_edit_matiere.matiere_is_locked, Permission.ScoView
)

sco_publish(
    "/module_move", sco_edit_formation.module_move, Permission.ScoChangeFormation
)
sco_publish("/ue_move", sco_edit_formation.ue_move, Permission.ScoChangeFormation)


# --- Semestres de formation


@bp.route(
    "/formsemestre_list", methods=["GET", "POST"]
)  # pour compat anciens clients PHP
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def formsemestre_list(
    format="json",
    formsemestre_id=None,
    formation_id=None,
    etape_apo=None,
):
    """List formsemestres in given format.
    kw can specify some conditions: examples:
        formsemestre_list( format='json', formation_id='F777')
    """
    try:
        formsemestre_id = int(formsemestre_id) if formsemestre_id is not None else None
        formation_id = int(formation_id) if formation_id is not None else None
    except ValueError:
        return api.errors.error_response(404, "invalid id")
    # XAPI: new json api
    args = {}
    L = locals()
    for argname in ("formsemestre_id", "formation_id", "etape_apo"):
        if L[argname] is not None:
            args[argname] = L[argname]
    sems = sco_formsemestre.do_formsemestre_list(args=args)
    # log('formsemestre_list: format="%s", %s semestres found' % (format,len(sems)))
    return scu.sendResult(sems, name="formsemestre", format=format)


@bp.route(
    "/XMLgetFormsemestres", methods=["GET", "POST"]
)  # pour compat anciens clients PHP
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def XMLgetFormsemestres(etape_apo=None, formsemestre_id=None):
    """List all formsemestres matching etape, XML format
    DEPRECATED: use formsemestre_list()
    """
    current_app.logger.debug("Warning: calling deprecated XMLgetFormsemestres")
    args = {}
    if etape_apo:
        args["etape_apo"] = etape_apo
    if formsemestre_id:
        args["formsemestre_id"] = formsemestre_id

    doc = ElementTree.Element("formsemestrelist")
    for sem in sco_formsemestre.do_formsemestre_list(args=args):
        for k in sem:
            if isinstance(sem[k], int):
                sem[k] = str(sem[k])
        sem_elt = ElementTree.Element("formsemestre", **sem)
        doc.append(sem_elt)

    data = sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING)
    return scu.send_file(data, mime=scu.XML_MIMETYPE)


sco_publish(
    "/do_formsemestre_edit",
    sco_formsemestre.do_formsemestre_edit,
    Permission.ScoImplement,
)
sco_publish(
    "/formsemestre_edit_options",
    sco_formsemestre_edit.formsemestre_edit_options,
    Permission.ScoView,
    methods=["GET", "POST"],
)


@bp.route("/formsemestre_change_lock", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)  # acces vérifié dans la fonction
@scodoc7func
def formsemestre_change_lock(formsemestre_id, dialog_confirmed=False):
    "Changement de l'état de verrouillage du semestre"

    if not dialog_confirmed:
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        etat = not sem["etat"]
        if etat:
            msg = "déverrouillage"
        else:
            msg = "verrouillage"
        return scu.confirm_dialog(
            "<h2>Confirmer le %s du semestre ?</h2>" % msg,
            helpmsg="""Les notes d'un semestre verrouillé ne peuvent plus être modifiées.
            Un semestre verrouillé peut cependant être déverrouillé facilement à tout moment
            (par son responsable ou un administrateur).
            <br/>
            Le programme d'une formation qui a un semestre verrouillé ne peut plus être modifié.
            """,
            dest_url="",
            cancel_url="formsemestre_status?formsemestre_id=%s" % formsemestre_id,
            parameters={"formsemestre_id": formsemestre_id},
        )

    sco_formsemestre_edit.formsemestre_change_lock(formsemestre_id)

    return flask.redirect(
        url_for(
            "notes.formsemestre_status",
            scodoc_dept=g.scodoc_dept,
            formsemestre_id=formsemestre_id,
        )
    )


sco_publish(
    "/formsemestre_change_publication_bul",
    sco_formsemestre_edit.formsemestre_change_publication_bul,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/view_formsemestre_by_etape",
    sco_formsemestre.view_formsemestre_by_etape,
    Permission.ScoView,
)


@bp.route("/formsemestre_custommenu_edit", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_custommenu_edit(formsemestre_id):
    "Dialogue modif menu"
    # accessible à tous !
    return sco_formsemestre_custommenu.formsemestre_custommenu_edit(formsemestre_id)


# --- dialogue modif enseignants/moduleimpl
@bp.route("/edit_enseignants_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def edit_enseignants_form(moduleimpl_id):
    "modif liste enseignants/moduleimpl"
    M, sem = sco_moduleimpl.can_change_ens(moduleimpl_id)
    # --
    header = html_sco_header.html_sem_header(
        'Enseignants du <a href="moduleimpl_status?moduleimpl_id=%s">module %s</a>'
        % (moduleimpl_id, M["module"]["titre"]),
        page_title="Enseignants du module %s" % M["module"]["titre"],
        javascripts=["libjs/AutoSuggest.js"],
        cssstyles=["css/autosuggest_inquisitor.css"],
        bodyOnLoad="init_tf_form('')",
    )
    footer = html_sco_header.sco_footer()

    # Liste des enseignants avec forme pour affichage / saisie avec suggestion
    userlist = sco_users.get_user_list()
    uid2display = {}  # uid : forme pour affichage = "NOM Prenom (login)"(login)"
    for u in userlist:
        uid2display[u.id] = u.get_nomplogin()
        allowed_user_names = list(uid2display.values())

    H = [
        "<ul><li><b>%s</b> (responsable)</li>"
        % uid2display.get(M["responsable_id"], M["responsable_id"])
    ]
    for ens in M["ens"]:
        u = User.query.get(ens["ens_id"])
        if u:
            nom = u.get_nomcomplet()
        else:
            nom = "? (compte inconnu)"
        H.append(
            f"""
            <li>{nom} (<a class="stdlink" href="{
                url_for('notes.edit_enseignants_form_delete', scodoc_dept=g.scodoc_dept, moduleimpl_id=moduleimpl_id, ens_id=ens["ens_id"])
                }">supprimer</a>)
            </li>"""
        )
    H.append("</ul>")
    F = """<p class="help">Les enseignants d'un module ont le droit de
    saisir et modifier toutes les notes des évaluations de ce module.
    </p>
    <p class="help">Pour changer le responsable du module, passez par la
    page "<a class="stdlink" href="formsemestre_editwithmodules?formation_id=%s&formsemestre_id=%s">Modification du semestre</a>", accessible uniquement au responsable de la formation (chef de département)
    </p>
    """ % (
        sem["formation_id"],
        M["formsemestre_id"],
    )

    modform = [
        ("moduleimpl_id", {"input_type": "hidden"}),
        (
            "ens_id",
            {
                "input_type": "text_suggest",
                "size": 50,
                "title": "Ajouter un enseignant",
                "allowed_values": allowed_user_names,
                "allow_null": False,
                "text_suggest_options": {
                    "script": url_for(
                        "users.get_user_list_xml", scodoc_dept=g.scodoc_dept
                    )
                    + "?",
                    "varname": "start",
                    "json": False,
                    "noresults": "Valeur invalide !",
                    "timeout": 60000,
                },
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        modform,
        submitlabel="Ajouter enseignant",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return header + "\n".join(H) + tf[1] + F + footer
    elif tf[0] == -1:
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=moduleimpl_id,
            )
        )
    else:
        ens_id = User.get_user_id_from_nomplogin(tf[2]["ens_id"])
        if not ens_id:
            H.append(
                '<p class="help">Pour ajouter un enseignant, choisissez un nom dans le menu</p>'
            )
        else:
            # et qu'il n'est pas deja:
            if (
                ens_id in [x["ens_id"] for x in M["ens"]]
                or ens_id == M["responsable_id"]
            ):
                H.append(
                    '<p class="help">Enseignant %s déjà dans la liste !</p>' % ens_id
                )
            else:
                sco_moduleimpl.do_ens_create(
                    {"moduleimpl_id": moduleimpl_id, "ens_id": ens_id}
                )
                return flask.redirect(
                    "edit_enseignants_form?moduleimpl_id=%s" % moduleimpl_id
                )
        return header + "\n".join(H) + tf[1] + F + footer


@bp.route("/edit_moduleimpl_resp", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def edit_moduleimpl_resp(moduleimpl_id):
    """Changement d'un enseignant responsable de module
    Accessible par Admin et dir des etud si flag resp_can_change_ens
    """
    M, sem = sco_moduleimpl.can_change_module_resp(moduleimpl_id)
    H = [
        html_sco_header.html_sem_header(
            'Modification du responsable du <a href="moduleimpl_status?moduleimpl_id=%s">module %s</a>'
            % (moduleimpl_id, M["module"]["titre"]),
            sem,
            javascripts=["libjs/AutoSuggest.js"],
            cssstyles=["css/autosuggest_inquisitor.css"],
            bodyOnLoad="init_tf_form('')",
        )
    ]
    help_str = """<p class="help">Taper le début du nom de l'enseignant.</p>"""
    # Liste des enseignants avec forme pour affichage / saisie avec suggestion
    userlist = [sco_users.user_info(user=u) for u in sco_users.get_user_list()]
    uid2display = {}  # uid : forme pour affichage = "NOM Prenom (login)"
    for u in userlist:
        uid2display[u["id"]] = u["nomplogin"]
    allowed_user_names = list(uid2display.values())

    initvalues = M
    initvalues["responsable_id"] = uid2display.get(
        M["responsable_id"], M["responsable_id"]
    )
    form = [
        ("moduleimpl_id", {"input_type": "hidden"}),
        (
            "responsable_id",
            {
                "input_type": "text_suggest",
                "size": 50,
                "title": "Responsable du module",
                "allowed_values": allowed_user_names,
                "allow_null": False,
                "text_suggest_options": {
                    "script": url_for(
                        "users.get_user_list_xml", scodoc_dept=g.scodoc_dept
                    )
                    + "?",
                    "varname": "start",
                    "json": False,
                    "noresults": "Valeur invalide !",
                    "timeout": 60000,
                },
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        form,
        submitlabel="Changer responsable",
        cancelbutton="Annuler",
        initvalues=initvalues,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + help_str + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=moduleimpl_id,
            )
        )
    else:
        responsable_id = User.get_user_id_from_nomplogin(tf[2]["responsable_id"])
        if (
            not responsable_id
        ):  # presque impossible: tf verifie les valeurs (mais qui peuvent changer entre temps)
            return flask.redirect(
                url_for(
                    "notes.moduleimpl_status",
                    scodoc_dept=g.scodoc_dept,
                    moduleimpl_id=moduleimpl_id,
                )
            )

        sco_moduleimpl.do_moduleimpl_edit(
            {"moduleimpl_id": moduleimpl_id, "responsable_id": responsable_id},
            formsemestre_id=sem["formsemestre_id"],
        )
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=moduleimpl_id,
                head_message="responsable modifié",
            )
        )


_EXPR_HELP = """<p class="help">Expérimental: formule de calcul de la moyenne %(target)s</p>
    <p class="help">Attention: l'utilisation de formules ralentit considérablement
    les traitements. A utiliser uniquement dans les cas ne pouvant pas être traités autrement.</p>
    <p class="help">Dans la formule, les variables suivantes sont définies:</p>
    <ul class="help">
    <li><tt>moy</tt> la moyenne, calculée selon la règle standard (moyenne pondérée)</li>
    <li><tt>moy_is_valid</tt> vrai si la moyenne est valide (numérique)</li>
    <li><tt>moy_val</tt> la valeur de la moyenne (nombre, valant 0 si invalide)</li>
    <li><tt>notes</tt> vecteur des notes (/20) aux %(objs)s</li>
    <li><tt>coefs</tt> vecteur des coefficients des %(objs)s, les coefs des %(objs)s sans notes (ATT, EXC) étant mis à zéro</li>
    <li><tt>cmask</tt> vecteur de 0/1, 0 si le coef correspondant a été annulé</li>
    <li>Nombre d'absences: <tt>nb_abs</tt>, <tt>nb_abs_just</tt>, <tt>nb_abs_nojust</tt> (en demi-journées)</li>
    </ul>
    <p class="help">Les éléments des vecteurs sont ordonnés dans l'ordre des %(objs)s%(ordre)s.</p>
    <p class="help">Les fonctions suivantes sont utilisables: <tt>abs, cmp, dot, len, map, max, min, pow, reduce, round, sum, ifelse</tt>.</p>
    <p class="help">La notation <tt>V(1,2,3)</tt> représente un vecteur <tt>(1,2,3)</tt>.</p>
    <p class="help"></p>Pour indiquer que la note calculée n'existe pas, utiliser la chaîne <tt>'NA'</tt>.</p>
    <p class="help">Vous pouvez désactiver la formule (et revenir au mode de calcul "classique") 
    en supprimant le texte ou en faisant précéder la première ligne par <tt>#</tt></p>
"""


@bp.route("/edit_moduleimpl_expr", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def edit_moduleimpl_expr(moduleimpl_id):
    """Edition formule calcul moyenne module
    Accessible par Admin, dir des etud et responsable module
    """
    M, sem = sco_moduleimpl.can_change_ens(moduleimpl_id)
    H = [
        html_sco_header.html_sem_header(
            'Modification règle de calcul du <a href="moduleimpl_status?moduleimpl_id=%s">module %s</a>'
            % (moduleimpl_id, M["module"]["titre"]),
            sem,
        ),
        _EXPR_HELP
        % {
            "target": "du module",
            "objs": "évaluations",
            "ordre": " (le premier élément est la plus ancienne évaluation)",
        },
    ]
    initvalues = M
    form = [
        ("moduleimpl_id", {"input_type": "hidden"}),
        (
            "computation_expr",
            {
                "title": "Formule de calcul",
                "input_type": "textarea",
                "rows": 4,
                "cols": 60,
                "explanation": "formule de calcul (expérimental)",
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        form,
        submitlabel="Modifier formule de calcul",
        cancelbutton="Annuler",
        initvalues=initvalues,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=moduleimpl_id,
            )
        )
    else:
        sco_moduleimpl.do_moduleimpl_edit(
            {
                "moduleimpl_id": moduleimpl_id,
                "computation_expr": tf[2]["computation_expr"],
            },
            formsemestre_id=sem["formsemestre_id"],
        )
        sco_cache.invalidate_formsemestre(
            formsemestre_id=sem["formsemestre_id"]
        )  # > modif regle calcul
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=moduleimpl_id,
                head_message="règle%20de%20calcul%20modifiée",
            )
        )


@bp.route("/view_module_abs")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def view_module_abs(moduleimpl_id, format="html"):
    """Visualisation des absences a un module"""
    M = sco_moduleimpl.moduleimpl_withmodule_list(moduleimpl_id=moduleimpl_id)[0]
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
    debut_sem = ndb.DateDMYtoISO(sem["date_debut"])
    fin_sem = ndb.DateDMYtoISO(sem["date_fin"])
    list_insc = sco_moduleimpl.moduleimpl_listeetuds(moduleimpl_id)

    T = []
    for etudid in list_insc:
        nb_abs = sco_abs.count_abs(
            etudid=etudid,
            debut=debut_sem,
            fin=fin_sem,
            moduleimpl_id=moduleimpl_id,
        )
        if nb_abs:
            nb_abs_just = sco_abs.count_abs_just(
                etudid=etudid,
                debut=debut_sem,
                fin=fin_sem,
                moduleimpl_id=moduleimpl_id,
            )
            etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
            T.append(
                {
                    "nomprenom": etud["nomprenom"],
                    "just": nb_abs_just,
                    "nojust": nb_abs - nb_abs_just,
                    "total": nb_abs,
                    "_nomprenom_target": url_for(
                        "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
                    ),
                }
            )

    H = [
        html_sco_header.html_sem_header(
            'Absences du <a href="moduleimpl_status?moduleimpl_id=%s">module %s</a>'
            % (moduleimpl_id, M["module"]["titre"]),
            page_title="Absences du module %s" % (M["module"]["titre"]),
            sem=sem,
        )
    ]
    if not T and format == "html":
        return (
            "\n".join(H)
            + "<p>Aucune absence signalée</p>"
            + html_sco_header.sco_footer()
        )

    tab = GenTable(
        titles={
            "nomprenom": "Nom",
            "just": "Just.",
            "nojust": "Non Just.",
            "total": "Total",
        },
        columns_ids=("nomprenom", "just", "nojust", "total"),
        rows=T,
        html_class="table_leftalign",
        base_url="%s?moduleimpl_id=%s" % (request.base_url, moduleimpl_id),
        filename="absmodule_" + scu.make_filename(M["module"]["titre"]),
        caption="Absences dans le module %s" % M["module"]["titre"],
        preferences=sco_preferences.SemPreferences(),
    )

    if format != "html":
        return tab.make_page(format=format)

    return "\n".join(H) + tab.html() + html_sco_header.sco_footer()


@bp.route("/edit_ue_expr", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def edit_ue_expr(formsemestre_id, ue_id):
    """Edition formule calcul moyenne UE"""
    # Check access
    sem = sco_formsemestre_edit.can_edit_sem(formsemestre_id)
    if not sem:
        raise AccessDenied("vous n'avez pas le droit d'effectuer cette opération")
    cnx = ndb.GetDBConnexion()
    #
    ue = sco_edit_ue.ue_list({"ue_id": ue_id})[0]
    H = [
        html_sco_header.html_sem_header(
            "Modification règle de calcul de l'UE %s (%s)"
            % (ue["acronyme"], ue["titre"]),
            sem,
        ),
        _EXPR_HELP % {"target": "de l'UE", "objs": "modules", "ordre": ""},
    ]
    el = sco_compute_moy.formsemestre_ue_computation_expr_list(
        cnx, {"formsemestre_id": formsemestre_id, "ue_id": ue_id}
    )
    if el:
        initvalues = el[0]
    else:
        initvalues = {}
    form = [
        ("ue_id", {"input_type": "hidden"}),
        ("formsemestre_id", {"input_type": "hidden"}),
        (
            "computation_expr",
            {
                "title": "Formule de calcul",
                "input_type": "textarea",
                "rows": 4,
                "cols": 60,
                "explanation": "formule de calcul (expérimental)",
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        form,
        submitlabel="Modifier formule de calcul",
        cancelbutton="Annuler",
        initvalues=initvalues,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(
            "formsemestre_status?formsemestre_id=" + str(formsemestre_id)
        )
    else:
        if el:
            el[0]["computation_expr"] = tf[2]["computation_expr"]
            sco_compute_moy.formsemestre_ue_computation_expr_edit(cnx, el[0])
        else:
            sco_compute_moy.formsemestre_ue_computation_expr_create(cnx, tf[2])

        sco_cache.invalidate_formsemestre(
            formsemestre_id=formsemestre_id
        )  # > modif regle calcul
        return flask.redirect(
            "formsemestre_status?formsemestre_id="
            + str(formsemestre_id)
            + "&head_message=règle%20de%20calcul%20modifiée"
        )


@bp.route("/formsemestre_enseignants_list")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_enseignants_list(formsemestre_id, format="html"):
    """Liste les enseignants intervenants dans le semestre (resp. modules et chargés de TD)
    et indique les absences saisies par chacun.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # resp. de modules:
    mods = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)
    sem_ens = {}
    for mod in mods:
        if not mod["responsable_id"] in sem_ens:
            sem_ens[mod["responsable_id"]] = {"mods": [mod]}
        else:
            sem_ens[mod["responsable_id"]]["mods"].append(mod)
    # charges de TD:
    for mod in mods:
        for ensd in mod["ens"]:
            if not ensd["ens_id"] in sem_ens:
                sem_ens[ensd["ens_id"]] = {"mods": [mod]}
            else:
                sem_ens[ensd["ens_id"]]["mods"].append(mod)
    # compte les absences ajoutées par chacun dans tout le semestre
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    for ens in sem_ens:
        u = User.query.filter_by(id=ens).first()
        if not u:
            continue
        cursor.execute(
            """SELECT * FROM scolog L, notes_formsemestre_inscription I 
            WHERE method = 'AddAbsence' 
            and authenticated_user = %(authenticated_user)s 
            and L.etudid = I.etudid 
            and  I.formsemestre_id = %(formsemestre_id)s 
            and date > %(date_debut)s 
            and date < %(date_fin)s
            """,
            {
                "authenticated_user": u.user_name,
                "formsemestre_id": formsemestre_id,
                "date_debut": ndb.DateDMYtoISO(sem["date_debut"]),
                "date_fin": ndb.DateDMYtoISO(sem["date_fin"]),
            },
        )

        events = cursor.dictfetchall()
        sem_ens[ens]["nbabsadded"] = len(events)

    # description textuelle des modules
    for ens in sem_ens:
        sem_ens[ens]["descr_mods"] = ", ".join(
            [x["module"]["code"] for x in sem_ens[ens]["mods"]]
        )

    # ajoute infos sur enseignant:
    for ens in sem_ens:
        sem_ens[ens].update(sco_users.user_info(ens))
        if sem_ens[ens]["email"]:
            sem_ens[ens]["_email_target"] = "mailto:%s" % sem_ens[ens]["email"]

    sem_ens_list = list(sem_ens.values())
    sem_ens_list.sort(key=itemgetter("nomprenom"))

    # --- Generate page with table
    title = "Enseignants de " + sem["titremois"]
    T = GenTable(
        columns_ids=["nom_fmt", "prenom_fmt", "descr_mods", "nbabsadded", "email"],
        titles={
            "nom_fmt": "Nom",
            "prenom_fmt": "Prénom",
            "email": "Mail",
            "descr_mods": "Modules",
            "nbabsadded": "Saisies Abs.",
        },
        rows=sem_ens_list,
        html_sortable=True,
        html_class="table_leftalign",
        filename=scu.make_filename("Enseignants-" + sem["titreannee"]),
        html_title=html_sco_header.html_sem_header(
            "Enseignants du semestre", sem, with_page_header=False
        ),
        base_url="%s?formsemestre_id=%s" % (request.base_url, formsemestre_id),
        caption="Tous les enseignants (responsables ou associés aux modules de ce semestre) apparaissent. Le nombre de saisies d'absences est le nombre d'opérations d'ajout effectuées sur ce semestre, sans tenir compte des annulations ou double saisies.",
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )
    return T.make_page(page_title=title, title=title, format=format)


@bp.route("/edit_enseignants_form_delete", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def edit_enseignants_form_delete(moduleimpl_id, ens_id: int):
    """remove ens from this modueimpl

    ens_id:  user.id
    """
    M, _ = sco_moduleimpl.can_change_ens(moduleimpl_id)
    # search ens_id
    ok = False
    for ens in M["ens"]:
        if ens["ens_id"] == ens_id:
            ok = True
            break
    if not ok:
        raise ScoValueError("invalid ens_id (%s)" % ens_id)
    ndb.SimpleQuery(
        """DELETE FROM notes_modules_enseignants
    WHERE moduleimpl_id = %(moduleimpl_id)s 
    AND ens_id = %(ens_id)s
    """,
        {"moduleimpl_id": moduleimpl_id, "ens_id": ens_id},
    )
    return flask.redirect("edit_enseignants_form?moduleimpl_id=%s" % moduleimpl_id)


# --- Gestion des inscriptions aux semestres

# Ancienne API, pas certain de la publier en ScoDoc8
# sco_publish(
#     "/do_formsemestre_inscription_create",
#     sco_formsemestre_inscriptions.do_formsemestre_inscription_create,
#     Permission.ScoEtudInscrit,
# )
# sco_publish(
#     "/do_formsemestre_inscription_edit",
#     sco_formsemestre_inscriptions.do_formsemestre_inscription_edit,
#     Permission.ScoEtudInscrit,
# )

sco_publish(
    "/do_formsemestre_inscription_list",
    sco_formsemestre_inscriptions.do_formsemestre_inscription_list,
    Permission.ScoView,
)


@bp.route("/do_formsemestre_inscription_listinscrits")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def do_formsemestre_inscription_listinscrits(formsemestre_id, format=None):
    """Liste les inscrits (état I) à ce semestre et cache le résultat"""
    r = sco_formsemestre_inscriptions.do_formsemestre_inscription_listinscrits(
        formsemestre_id
    )
    return scu.sendResult(r, format=format, name="inscrits")


@bp.route("/formsemestre_desinscription", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoImplement)
@scodoc7func
def formsemestre_desinscription(etudid, formsemestre_id, dialog_confirmed=False):
    """desinscrit l'etudiant de ce semestre (et donc de tous les modules).
    A n'utiliser qu'en cas d'erreur de saisie.
    S'il s'agit d'un semestre extérieur et qu'il n'y a plus d'inscrit,
    le semestre sera supprimé.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # -- check lock
    if not sem["etat"]:
        raise ScoValueError("desinscription impossible: semestre verrouille")

    # -- Si décisions de jury, désinscription interdite
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    if nt.etud_has_decision(etudid):
        raise ScoValueError(
            """Désinscription impossible: l'étudiant a une décision de jury 
            (la supprimer avant si nécessaire: 
            <a href="formsemestre_validation_suppress_etud?etudid=%s&formsemestre_id=%s">
            supprimer décision jury</a>
            )
            """
            % (etudid, formsemestre_id)
        )
    if not dialog_confirmed:
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        if sem["modalite"] != "EXT":
            msg_ext = """
            <p>%s sera désinscrit de tous les modules du semestre %s (%s - %s).</p>
            <p>Cette opération ne doit être utilisée que pour corriger une <b>erreur</b> !
            Un étudiant réellement inscrit doit le rester, le faire éventuellement <b>démissionner<b>.
            </p>
            """ % (
                etud["nomprenom"],
                sem["titre_num"],
                sem["date_debut"],
                sem["date_fin"],
            )
        else:  # semestre extérieur
            msg_ext = """
            <p>%s sera désinscrit du semestre extérieur %s (%s - %s).</p>
            """ % (
                etud["nomprenom"],
                sem["titre_num"],
                sem["date_debut"],
                sem["date_fin"],
            )
            inscrits = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
                args={"formsemestre_id": formsemestre_id}
            )
            nbinscrits = len(inscrits)
            if nbinscrits <= 1:
                msg_ext = """<p class="warning">Attention: le semestre extérieur sera supprimé
                car il n'a pas d'autre étudiant inscrit.
                </p>
                """
        return scu.confirm_dialog(
            """<h2>Confirmer la demande de desinscription ?</h2>""" + msg_ext,
            dest_url="",
            cancel_url="formsemestre_status?formsemestre_id=%s" % formsemestre_id,
            parameters={"etudid": etudid, "formsemestre_id": formsemestre_id},
        )

    sco_formsemestre_inscriptions.do_formsemestre_desinscription(
        etudid, formsemestre_id
    )

    return (
        html_sco_header.sco_header()
        + '<p>Etudiant désinscrit !</p><p><a class="stdlink" href="%s">retour à la fiche</a>'
        % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        + html_sco_header.sco_footer()
    )


sco_publish(
    "/do_formsemestre_desinscription",
    sco_formsemestre_inscriptions.do_formsemestre_desinscription,
    Permission.ScoEtudInscrit,
    methods=["GET", "POST"],
)


@bp.route("/etud_desinscrit_ue")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def etud_desinscrit_ue(etudid, formsemestre_id, ue_id):
    """Desinscrit l'etudiant de tous les modules de cette UE dans ce semestre."""
    sco_moduleimpl_inscriptions.do_etud_desinscrit_ue(etudid, formsemestre_id, ue_id)
    return flask.redirect(
        scu.ScoURL()
        + "/Notes/moduleimpl_inscriptions_stats?formsemestre_id="
        + str(formsemestre_id)
    )


@bp.route("/etud_inscrit_ue")
@scodoc
@permission_required(Permission.ScoEtudInscrit)
@scodoc7func
def etud_inscrit_ue(etudid, formsemestre_id, ue_id):
    """Inscrit l'etudiant de tous les modules de cette UE dans ce semestre."""
    sco_moduleimpl_inscriptions.do_etud_inscrit_ue(etudid, formsemestre_id, ue_id)
    return flask.redirect(
        scu.ScoURL()
        + "/Notes/moduleimpl_inscriptions_stats?formsemestre_id="
        + str(formsemestre_id)
    )


# --- Inscriptions
sco_publish(
    "/formsemestre_inscription_with_modules_form",
    sco_formsemestre_inscriptions.formsemestre_inscription_with_modules_form,
    Permission.ScoEtudInscrit,
)
sco_publish(
    "/formsemestre_inscription_with_modules_etud",
    sco_formsemestre_inscriptions.formsemestre_inscription_with_modules_etud,
    Permission.ScoEtudInscrit,
)
sco_publish(
    "/formsemestre_inscription_with_modules",
    sco_formsemestre_inscriptions.formsemestre_inscription_with_modules,
    Permission.ScoEtudInscrit,
)
sco_publish(
    "/formsemestre_inscription_option",
    sco_formsemestre_inscriptions.formsemestre_inscription_option,
    Permission.ScoEtudInscrit,
    methods=["GET", "POST"],
)
sco_publish(
    "/do_moduleimpl_incription_options",
    sco_formsemestre_inscriptions.do_moduleimpl_incription_options,
    Permission.ScoEtudInscrit,
)
sco_publish(
    "/formsemestre_inscrits_ailleurs",
    sco_formsemestre_inscriptions.formsemestre_inscrits_ailleurs,
    Permission.ScoView,
)
sco_publish(
    "/moduleimpl_inscriptions_edit",
    sco_moduleimpl_inscriptions.moduleimpl_inscriptions_edit,
    Permission.ScoEtudInscrit,
    methods=["GET", "POST"],
)
sco_publish(
    "/moduleimpl_inscriptions_stats",
    sco_moduleimpl_inscriptions.moduleimpl_inscriptions_stats,
    Permission.ScoView,
)


# --- Evaluations


@bp.route("/evaluation_delete", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEnsView)
@scodoc7func
def evaluation_delete(evaluation_id):
    """Form delete evaluation"""
    El = sco_evaluations.do_evaluation_list(args={"evaluation_id": evaluation_id})
    if not El:
        raise ScoValueError("Evalution inexistante ! (%s)" % evaluation_id)
    E = El[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    tit = "Suppression de l'évaluation %(description)s (%(jour)s)" % E
    etat = sco_evaluations.do_evaluation_etat(evaluation_id)
    H = [
        html_sco_header.html_sem_header(tit, with_h2=False),
        """<h2 class="formsemestre">Module <tt>%(code)s</tt> %(titre)s</h2>""" % Mod,
        """<h3>%s</h3>""" % tit,
        """<p class="help">Opération <span class="redboldtext">irréversible</span>. Si vous supprimez l'évaluation, vous ne pourrez pas retrouver les notes associées.</p>""",
    ]
    warning = False
    if etat["nb_notes_total"]:
        warning = True
        nb_desinscrits = etat["nb_notes_total"] - etat["nb_notes"]
        H.append(
            """<div class="ue_warning"><span>Il y a %s notes""" % etat["nb_notes_total"]
        )
        if nb_desinscrits:
            H.append(
                """ (dont %s d'étudiants qui ne sont plus inscrits)""" % nb_desinscrits
            )
        H.append(""" dans l'évaluation</span>""")
        if etat["nb_notes"] == 0:
            H.append(
                """<p>Vous pouvez quand même supprimer l'évaluation, les notes des étudiants désincrits seront effacées.</p>"""
            )

    if etat["nb_notes"]:
        H.append(
            """<p>Suppression impossible (effacer les notes d'abord)</p><p><a class="stdlink" href="moduleimpl_status?moduleimpl_id=%s">retour au tableau de bord du module</a></p></div>"""
            % E["moduleimpl_id"]
        )
        return "\n".join(H) + html_sco_header.sco_footer()
    if warning:
        H.append("""</div>""")

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("evaluation_id", {"input_type": "hidden"}),),
        initvalues=E,
        submitlabel="Confirmer la suppression",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=E["moduleimpl_id"],
            )
        )
    else:
        sco_evaluations.do_evaluation_delete(E["evaluation_id"])
        return (
            "\n".join(H)
            + f"""<p>OK, évaluation supprimée.</p>
        <p><a class="stdlink" href="{
            url_for("notes.moduleimpl_status", scodoc_dept=g.scodoc_dept, 
            moduleimpl_id=E["moduleimpl_id"])
            }">Continuer</a></p>"""
            + html_sco_header.sco_footer()
        )


sco_publish(
    "/do_evaluation_list",
    sco_evaluations.do_evaluation_list,
    Permission.ScoView,
)


@bp.route("/evaluation_edit", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEnsView)
@scodoc7func
def evaluation_edit(evaluation_id):
    "form edit evaluation"
    return sco_evaluations.evaluation_create_form(
        evaluation_id=evaluation_id, edit=True
    )


@bp.route("/evaluation_create", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEnsView)
@scodoc7func
def evaluation_create(moduleimpl_id):
    "form create evaluation"
    return sco_evaluations.evaluation_create_form(
        moduleimpl_id=moduleimpl_id, edit=False
    )


@bp.route("/evaluation_listenotes", methods=["GET", "POST"])  # API ScoDoc 7 compat
@scodoc
@permission_required_compat_scodoc7(Permission.ScoView)
@scodoc7func
def evaluation_listenotes():
    """Affichage des notes d'une évaluation"""
    if request.args.get("format", "html") == "html":
        H = html_sco_header.sco_header(
            cssstyles=["css/verticalhisto.css"],
            javascripts=["js/etud_info.js"],
            init_qtip=True,
        )
        F = html_sco_header.sco_footer()
    else:
        H, F = "", ""
    B = sco_liste_notes.do_evaluation_listenotes()
    if H:
        return H + B + F
    else:
        return B


sco_publish(
    "/do_evaluation_listenotes",
    sco_liste_notes.do_evaluation_listenotes,
    Permission.ScoView,
)
sco_publish(
    "/evaluation_list_operations",
    sco_undo_notes.evaluation_list_operations,
    Permission.ScoView,
)
sco_publish(
    "/evaluation_check_absences_html",
    sco_liste_notes.evaluation_check_absences_html,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_check_absences_html",
    sco_liste_notes.formsemestre_check_absences_html,
    Permission.ScoView,
)

# --- Placement des étudiants pour l'évaluation
sco_publish(
    "/placement_eval_selectetuds",
    sco_placement.placement_eval_selectetuds,
    Permission.ScoEnsView,
    methods=["GET", "POST"],
)

# --- Saisie des notes
sco_publish(
    "/saisie_notes_tableur",
    sco_saisie_notes.saisie_notes_tableur,
    Permission.ScoEnsView,
    methods=["GET", "POST"],
)
sco_publish(
    "/feuille_saisie_notes",
    sco_saisie_notes.feuille_saisie_notes,
    Permission.ScoEnsView,
)
sco_publish("/saisie_notes", sco_saisie_notes.saisie_notes, Permission.ScoEnsView)
sco_publish(
    "/save_note",
    sco_saisie_notes.save_note,
    Permission.ScoEnsView,
    methods=["GET", "POST"],
)
sco_publish(
    "/do_evaluation_set_missing",
    sco_saisie_notes.do_evaluation_set_missing,
    Permission.ScoEnsView,
    methods=["GET", "POST"],
)
sco_publish(
    "/evaluation_suppress_alln",
    sco_saisie_notes.evaluation_suppress_alln,
    Permission.ScoView,
    methods=["GET", "POST"],
)


# --- Bulletins
@bp.route("/formsemestre_bulletins_pdf")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_bulletins_pdf(formsemestre_id, version="selectedevals"):
    "Publie les bulletins dans un classeur PDF"
    pdfdoc, filename = sco_bulletins_pdf.get_formsemestre_bulletins_pdf(
        formsemestre_id, version=version
    )
    return scu.sendPDFFile(pdfdoc, filename)


_EXPL_BULL = """Versions des bulletins:<ul><li><bf>courte</bf>: moyennes des modules</li><li><bf>intermédiaire</bf>: moyennes des modules et notes des évaluations sélectionnées</li><li><bf>complète</bf>: toutes les notes</li><ul>"""


@bp.route("/formsemestre_bulletins_pdf_choice")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_bulletins_pdf_choice(formsemestre_id, version=None):
    """Choix version puis envois classeur bulletins pdf"""
    if version:
        pdfdoc, filename = sco_bulletins_pdf.get_formsemestre_bulletins_pdf(
            formsemestre_id, version=version
        )
        return scu.sendPDFFile(pdfdoc, filename)
    return formsemestre_bulletins_choice(
        formsemestre_id,
        title="Choisir la version des bulletins à générer",
        explanation=_EXPL_BULL,
    )


@bp.route("/etud_bulletins_pdf")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def etud_bulletins_pdf(etudid, version="selectedevals"):
    "Publie tous les bulletins d'un etudiants dans un classeur PDF"
    pdfdoc, filename = sco_bulletins_pdf.get_etud_bulletins_pdf(etudid, version=version)
    return scu.sendPDFFile(pdfdoc, filename)


@bp.route("/formsemestre_bulletins_mailetuds_choice")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_bulletins_mailetuds_choice(
    formsemestre_id,
    version=None,
    dialog_confirmed=False,
    prefer_mail_perso=0,
):
    """Choix version puis envoi classeur bulletins pdf"""
    if version:
        # XXX à tester
        return flask.redirect(
            url_for(
                "notes.formsemestre_bulletins_mailetuds",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
                version=version,
                dialog_confirmed=dialog_confirmed,
                prefer_mail_perso=prefer_mail_perso,
            )
        )

    expl_bull = """Versions des bulletins:<ul><li><bf>courte</bf>: moyennes des modules</li><li><bf>intermédiaire</bf>: moyennes des modules et notes des évaluations sélectionnées</li><li><bf>complète</bf>: toutes les notes</li><ul>"""
    return formsemestre_bulletins_choice(
        formsemestre_id,
        title="Choisir la version des bulletins à envoyer par mail",
        explanation="Chaque étudiant ayant une adresse mail connue de ScoDoc recevra une copie PDF de son bulletin de notes, dans la version choisie.</p><p>"
        + expl_bull,
        choose_mail=True,
    )


# not published
def formsemestre_bulletins_choice(
    formsemestre_id, title="", explanation="", choose_mail=False
):
    """Choix d'une version de bulletin"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    H = [
        html_sco_header.html_sem_header(title, sem),
        """
      <form name="f" method="GET" action="%s">
      <input type="hidden" name="formsemestre_id" value="%s"></input>
      """
        % (request.base_url, formsemestre_id),
    ]
    H.append("""<select name="version" class="noprint">""")
    for (v, e) in (
        ("short", "Version courte"),
        ("selectedevals", "Version intermédiaire"),
        ("long", "Version complète"),
    ):
        H.append('<option value="%s">%s</option>' % (v, e))

    H.append("""</select>&nbsp;&nbsp;<input type="submit" value="Générer"/>""")
    if choose_mail:
        H.append(
            """<div><input type="checkbox" name="prefer_mail_perso" value="1">Utiliser si possible les adresses personnelles</div>"""
        )

    H.append("""<p class="help">""" + explanation + """</p>""")

    return "\n".join(H) + html_sco_header.sco_footer()


@bp.route("/formsemestre_bulletins_mailetuds")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_bulletins_mailetuds(
    formsemestre_id,
    version="long",
    dialog_confirmed=False,
    prefer_mail_perso=0,
):
    "envoi a chaque etudiant (inscrit et ayant un mail) son bulletin"
    prefer_mail_perso = int(prefer_mail_perso)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etudids
    etudids = nt.get_etudids()
    #
    if not sco_bulletins.can_send_bulletin_by_mail(formsemestre_id):
        raise AccessDenied("vous n'avez pas le droit d'envoyer les bulletins")
    # Confirmation dialog
    if not dialog_confirmed:
        return scu.confirm_dialog(
            "<h2>Envoyer les %d bulletins par e-mail aux étudiants ?" % len(etudids),
            dest_url="",
            cancel_url="formsemestre_status?formsemestre_id=%s" % formsemestre_id,
            parameters={
                "version": version,
                "formsemestre_id": formsemestre_id,
                "prefer_mail_perso": prefer_mail_perso,
            },
        )

    # Make each bulletin
    nb_send = 0
    for etudid in etudids:
        h, _ = sco_bulletins.do_formsemestre_bulletinetud(
            formsemestre_id,
            etudid,
            version=version,
            prefer_mail_perso=prefer_mail_perso,
            format="pdfmail",
            nohtml=True,
        )
        if h:
            nb_send += 1
    #
    return (
        html_sco_header.sco_header()
        + '<p>%d bulletins sur %d envoyés par mail !</p><p><a class="stdlink" href="formsemestre_status?formsemestre_id=%s">continuer</a></p>'
        % (nb_send, len(etudids), formsemestre_id)
        + html_sco_header.sco_footer()
    )


sco_publish(
    "/external_ue_create_form",
    sco_ue_external.external_ue_create_form,
    Permission.ScoView,
    methods=["GET", "POST"],
)


@bp.route("/appreciation_add_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoEnsView)
@scodoc7func
def appreciation_add_form(
    etudid=None,
    formsemestre_id=None,
    id=None,  # si id, edit
    suppress=False,  # si true, supress id
):
    "form ajout ou edition d'une appreciation"
    cnx = ndb.GetDBConnexion()
    if id:  # edit mode
        apps = sco_etud.appreciations_list(cnx, args={"id": id})
        if not apps:
            raise ScoValueError("id d'appreciation invalide !")
        app = apps[0]
        formsemestre_id = app["formsemestre_id"]
        etudid = app["etudid"]
    vals = scu.get_request_args()
    if "edit" in vals:
        edit = int(vals["edit"])
    elif id:
        edit = 1
    else:
        edit = 0
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # check custom access permission
    can_edit_app = (current_user.id in sem["responsables"]) or (
        current_user.has_permission(Permission.ScoEtudInscrit)
    )
    if not can_edit_app:
        raise AccessDenied("vous n'avez pas le droit d'ajouter une appreciation")
    #
    bull_url = "formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s" % (
        formsemestre_id,
        etudid,
    )
    if suppress:
        sco_etud.appreciations_delete(cnx, id)
        logdb(cnx, method="appreciation_suppress", etudid=etudid, msg="")
        return flask.redirect(bull_url)
    #
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    if id:
        a = "Edition"
    else:
        a = "Ajout"
    H = [
        html_sco_header.sco_header()
        + "<h2>%s d'une appréciation sur %s</h2>" % (a, etud["nomprenom"])
    ]
    F = html_sco_header.sco_footer()
    descr = [
        ("edit", {"input_type": "hidden", "default": edit}),
        ("etudid", {"input_type": "hidden"}),
        ("formsemestre_id", {"input_type": "hidden"}),
        ("id", {"input_type": "hidden"}),
        ("comment", {"title": "", "input_type": "textarea", "rows": 4, "cols": 60}),
    ]
    if id:
        initvalues = {
            "etudid": etudid,
            "formsemestre_id": formsemestre_id,
            "comment": app["comment"],
        }
    else:
        initvalues = {}
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        initvalues=initvalues,
        cancelbutton="Annuler",
        submitlabel="Ajouter appréciation",
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + F
    elif tf[0] == -1:
        return flask.redirect(bull_url)
    else:
        args = {
            "etudid": etudid,
            "formsemestre_id": formsemestre_id,
            "author": current_user.user_name,
            "comment": tf[2]["comment"],
        }
        if edit:
            args["id"] = id
            sco_etud.appreciations_edit(cnx, args)
        else:  # nouvelle
            sco_etud.appreciations_create(cnx, args)
        # log
        logdb(
            cnx,
            method="appreciation_add",
            etudid=etudid,
            msg=tf[2]["comment"],
        )
        # ennuyeux mais necessaire (pour le PDF seulement)
        sco_cache.invalidate_formsemestre(
            pdfonly=True, formsemestre_id=formsemestre_id
        )  # > appreciation_add
        return flask.redirect(bull_url)


# --- FORMULAIRE POUR VALIDATION DES UE ET SEMESTRES


@bp.route("/formsemestre_validation_etud_form")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_validation_etud_form(
    formsemestre_id,
    etudid=None,
    etud_index=None,
    check=0,
    desturl="",
    sortcol=None,
):
    "Formulaire choix jury pour un étudiant"
    readonly = not sco_permissions_check.can_validate_sem(formsemestre_id)
    return sco_formsemestre_validation.formsemestre_validation_etud_form(
        formsemestre_id,
        etudid=etudid,
        etud_index=etud_index,
        check=check,
        readonly=readonly,
        desturl=desturl,
        sortcol=sortcol,
    )


@bp.route("/formsemestre_validation_etud")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_validation_etud(
    formsemestre_id,
    etudid=None,
    codechoice=None,
    desturl="",
    sortcol=None,
):
    "Enregistre choix jury pour un étudiant"
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )

    return sco_formsemestre_validation.formsemestre_validation_etud(
        formsemestre_id,
        etudid=etudid,
        codechoice=codechoice,
        desturl=desturl,
        sortcol=sortcol,
    )


@bp.route("/formsemestre_validation_etud_manu")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_validation_etud_manu(
    formsemestre_id,
    etudid=None,
    code_etat="",
    new_code_prev="",
    devenir="",
    assidu=False,
    desturl="",
    sortcol=None,
):
    "Enregistre choix jury pour un étudiant"
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )

    return sco_formsemestre_validation.formsemestre_validation_etud_manu(
        formsemestre_id,
        etudid=etudid,
        code_etat=code_etat,
        new_code_prev=new_code_prev,
        devenir=devenir,
        assidu=assidu,
        desturl=desturl,
        sortcol=sortcol,
    )


@bp.route("/formsemestre_validate_previous_ue")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_validate_previous_ue(formsemestre_id, etudid=None):
    "Form. saisie UE validée hors ScoDoc"
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )
    return sco_formsemestre_validation.formsemestre_validate_previous_ue(
        formsemestre_id, etudid
    )


sco_publish(
    "/formsemestre_ext_create_form",
    sco_formsemestre_exterieurs.formsemestre_ext_create_form,
    Permission.ScoView,
    methods=["GET", "POST"],
)


@bp.route("/formsemestre_ext_edit_ue_validations", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_ext_edit_ue_validations(formsemestre_id, etudid=None):
    "Form. edition UE semestre extérieur"
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )
    return sco_formsemestre_exterieurs.formsemestre_ext_edit_ue_validations(
        formsemestre_id, etudid
    )


sco_publish(
    "/get_etud_ue_cap_html",
    sco_formsemestre_validation.get_etud_ue_cap_html,
    Permission.ScoView,
)


@bp.route("/etud_ue_suppress_validation")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def etud_ue_suppress_validation(etudid, formsemestre_id, ue_id):
    """Suppress a validation (ue_id, etudid) and redirect to formsemestre"""
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )
    return sco_formsemestre_validation.etud_ue_suppress_validation(
        etudid, formsemestre_id, ue_id
    )


@bp.route("/formsemestre_validation_auto")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_validation_auto(formsemestre_id):
    "Formulaire saisie automatisee des decisions d'un semestre"
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )

    return sco_formsemestre_validation.formsemestre_validation_auto(formsemestre_id)


@bp.route("/do_formsemestre_validation_auto")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def do_formsemestre_validation_auto(formsemestre_id):
    "Formulaire saisie automatisee des decisions d'un semestre"
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )

    return sco_formsemestre_validation.do_formsemestre_validation_auto(formsemestre_id)


@bp.route("/formsemestre_validation_suppress_etud", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def formsemestre_validation_suppress_etud(
    formsemestre_id, etudid, dialog_confirmed=False
):
    """Suppression des decisions de jury pour un etudiant."""
    if not sco_permissions_check.can_validate_sem(formsemestre_id):
        return scu.confirm_dialog(
            message="<p>Opération non autorisée pour %s</h2>" % current_user,
            dest_url=scu.ScoURL(),
        )
    if not dialog_confirmed:
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etud_decision_sem
        decision_jury = nt.get_etud_decision_sem(etudid)
        if decision_jury:
            existing = (
                "<p>Décision existante: %(code)s du %(event_date)s</p>" % decision_jury
            )
        else:
            existing = ""
        return scu.confirm_dialog(
            """<h2>Confirmer la suppression des décisions du semestre %s (%s - %s) pour %s ?</h2>%s
            <p>Cette opération est irréversible.
            </p>
            """
            % (
                sem["titre_num"],
                sem["date_debut"],
                sem["date_fin"],
                etud["nomprenom"],
                existing,
            ),
            OK="Supprimer",
            dest_url="",
            cancel_url="formsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s"
            % (formsemestre_id, etudid),
            parameters={"etudid": etudid, "formsemestre_id": formsemestre_id},
        )

    sco_formsemestre_validation.formsemestre_validation_suppress_etud(
        formsemestre_id, etudid
    )
    return flask.redirect(
        scu.ScoURL()
        + "/Notes/formsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s&head_message=Décision%%20supprimée"
        % (formsemestre_id, etudid)
    )


# ------------- PV de JURY et archives
sco_publish("/formsemestre_pvjury", sco_pvjury.formsemestre_pvjury, Permission.ScoView)
sco_publish(
    "/formsemestre_lettres_individuelles",
    sco_pvjury.formsemestre_lettres_individuelles,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_pvjury_pdf", sco_pvjury.formsemestre_pvjury_pdf, Permission.ScoView
)
sco_publish(
    "/feuille_preparation_jury",
    sco_prepajury.feuille_preparation_jury,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_archive",
    sco_archives.formsemestre_archive,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_delete_archive",
    sco_archives.formsemestre_delete_archive,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_list_archives",
    sco_archives.formsemestre_list_archives,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_get_archived_file",
    sco_archives.formsemestre_get_archived_file,
    Permission.ScoView,
)
sco_publish("/view_apo_csv", sco_etape_apogee_view.view_apo_csv, Permission.ScoEditApo)
sco_publish(
    "/view_apo_csv_store",
    sco_etape_apogee_view.view_apo_csv_store,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/view_apo_csv_download_and_store",
    sco_etape_apogee_view.view_apo_csv_download_and_store,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/view_apo_csv_delete",
    sco_etape_apogee_view.view_apo_csv_delete,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/view_scodoc_etuds", sco_etape_apogee_view.view_scodoc_etuds, Permission.ScoEditApo
)
sco_publish(
    "/view_apo_etuds", sco_etape_apogee_view.view_apo_etuds, Permission.ScoEditApo
)
sco_publish(
    "/apo_semset_maq_status",
    sco_etape_apogee_view.apo_semset_maq_status,
    Permission.ScoEditApo,
)
sco_publish(
    "/apo_csv_export_results",
    sco_etape_apogee_view.apo_csv_export_results,
    Permission.ScoEditApo,
)

# sco_semset
sco_publish("/semset_page", sco_semset.semset_page, Permission.ScoEditApo)
sco_publish(
    "/do_semset_create",
    sco_semset.do_semset_create,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/do_semset_delete",
    sco_semset.do_semset_delete,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/edit_semset_set_title",
    sco_semset.edit_semset_set_title,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/do_semset_add_sem",
    sco_semset.do_semset_add_sem,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)
sco_publish(
    "/do_semset_remove_sem",
    sco_semset.do_semset_remove_sem,
    Permission.ScoEditApo,
    methods=["GET", "POST"],
)

# sco_export_result
sco_publish(
    "/scodoc_table_results",
    sco_export_results.scodoc_table_results,
    Permission.ScoEditApo,
)

sco_publish(
    "/apo_compare_csv_form",
    sco_apogee_compare.apo_compare_csv_form,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/apo_compare_csv",
    sco_apogee_compare.apo_compare_csv,
    Permission.ScoView,
    methods=["GET", "POST"],
)

# ------------- INSCRIPTIONS: PASSAGE D'UN SEMESTRE A UN AUTRE
sco_publish(
    "/formsemestre_inscr_passage",
    sco_inscr_passage.formsemestre_inscr_passage,
    Permission.ScoEtudInscrit,
    methods=["GET", "POST"],
)
sco_publish(
    "/formsemestre_synchro_etuds",
    sco_synchro_etuds.formsemestre_synchro_etuds,
    Permission.ScoView,
    methods=["GET", "POST"],
)

# ------------- RAPPORTS STATISTIQUES
sco_publish(
    "/formsemestre_report_counts",
    sco_report.formsemestre_report_counts,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_suivi_cohorte",
    sco_report.formsemestre_suivi_cohorte,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_suivi_parcours",
    sco_report.formsemestre_suivi_parcours,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_etuds_lycees",
    sco_lycee.formsemestre_etuds_lycees,
    Permission.ScoView,
)
sco_publish(
    "/scodoc_table_etuds_lycees",
    sco_lycee.scodoc_table_etuds_lycees,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_graph_parcours",
    sco_report.formsemestre_graph_parcours,
    Permission.ScoView,
)
sco_publish(
    "/formsemestre_poursuite_report",
    sco_poursuite_dut.formsemestre_poursuite_report,
    Permission.ScoView,
)
sco_publish(
    "/pe_view_sem_recap",
    pe_view.pe_view_sem_recap,
    Permission.ScoView,
    methods=["GET", "POST"],
)
sco_publish(
    "/report_debouche_date", sco_debouche.report_debouche_date, Permission.ScoView
)
sco_publish(
    "/formsemestre_estim_cost",
    sco_cost_formation.formsemestre_estim_cost,
    Permission.ScoView,
)

# --------------------------------------------------------------------
# DEBUG


@bp.route("/check_sem_integrity")
@scodoc
@permission_required(Permission.ScoImplement)
@scodoc7func
def check_sem_integrity(formsemestre_id, fix=False):
    """Debug.
    Check that ue and module formations are consistents
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)

    modimpls = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
    bad_ue = []
    bad_sem = []
    formations_set = set()  # les formations mentionnées dans les UE et modules
    for modimpl in modimpls:
        mod = sco_edit_module.module_list({"module_id": modimpl["module_id"]})[0]
        formations_set.add(mod["formation_id"])
        ue = sco_edit_ue.ue_list({"ue_id": mod["ue_id"]})[0]
        formations_set.add(ue["formation_id"])
        if ue["formation_id"] != mod["formation_id"]:
            modimpl["mod"] = mod
            modimpl["ue"] = ue
            bad_ue.append(modimpl)
        if sem["formation_id"] != mod["formation_id"]:
            bad_sem.append(modimpl)
            modimpl["mod"] = mod

    H = [
        html_sco_header.sco_header(),
        "<p>formation_id=%s" % sem["formation_id"],
    ]
    if bad_ue:
        H += [
            "<h2>Modules d'une autre formation que leur UE:</h2>",
            "<br/>".join([str(x) for x in bad_ue]),
        ]
    if bad_sem:
        H += [
            "<h2>Module du semestre dans une autre formation:</h2>",
            "<br/>".join([str(x) for x in bad_sem]),
        ]
    if not bad_ue and not bad_sem:
        H.append("<p>Aucun problème à signaler !</p>")
    else:
        log("check_sem_integrity: problem detected: formations_set=%s" % formations_set)
        if sem["formation_id"] in formations_set:
            formations_set.remove(sem["formation_id"])
        if len(formations_set) == 1:
            if fix:
                log("check_sem_integrity: trying to fix %s" % formsemestre_id)
                formation_id = formations_set.pop()
                if sem["formation_id"] != formation_id:
                    sem["formation_id"] = formation_id
                    sco_formsemestre.do_formsemestre_edit(sem)
                H.append("""<p class="alert">Problème réparé: vérifiez</p>""")
            else:
                H.append(
                    """
                <p class="alert">Problème détecté réparable: 
                <a href="check_sem_integrity?formsemestre_id=%s&fix=1">réparer maintenant</a></p>
                """
                    % (formsemestre_id,)
                )
        else:
            H.append("""<p class="alert">Problème détecté !</p>""")

    return "\n".join(H) + html_sco_header.sco_footer()


@bp.route("/check_form_integrity")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def check_form_integrity(formation_id, fix=False):
    "debug"
    log("check_form_integrity: formation_id=%s  fix=%s" % (formation_id, fix))
    ues = sco_edit_ue.ue_list(args={"formation_id": formation_id})
    bad = []
    for ue in ues:
        mats = sco_edit_matiere.matiere_list(args={"ue_id": ue["ue_id"]})
        for mat in mats:
            mods = sco_edit_module.module_list({"matiere_id": mat["matiere_id"]})
            for mod in mods:
                if mod["ue_id"] != ue["ue_id"]:
                    if fix:
                        # fix mod.ue_id
                        log(
                            "fix: mod.ue_id = %s (was %s)" % (ue["ue_id"], mod["ue_id"])
                        )
                        mod["ue_id"] = ue["ue_id"]
                        sco_edit_module.do_module_edit(mod)
                    bad.append(mod)
                if mod["formation_id"] != formation_id:
                    bad.append(mod)
    if bad:
        txth = "<br/>".join([str(x) for x in bad])
        txt = "\n".join([str(x) for x in bad])
        log("check_form_integrity: formation_id=%s\ninconsistencies:" % formation_id)
        log(txt)
        # Notify by e-mail
        send_scodoc_alarm("Notes: formation incoherente !", txt)
    else:
        txth = "OK"
        log("ok")
    return html_sco_header.sco_header() + txth + html_sco_header.sco_footer()


@bp.route("/check_formsemestre_integrity")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def check_formsemestre_integrity(formsemestre_id):
    "debug"
    log("check_formsemestre_integrity: formsemestre_id=%s" % (formsemestre_id))
    # verifie que tous les moduleimpl d'un formsemestre
    # se réfèrent à un module dont l'UE appartient a la même formation
    # Ancien bug: les ue_id étaient mal copiés lors des création de versions
    # de formations
    diag = []

    Mlist = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)
    for mod in Mlist:
        if mod["module"]["ue_id"] != mod["matiere"]["ue_id"]:
            diag.append(
                "moduleimpl %s: module.ue_id=%s != matiere.ue_id=%s"
                % (
                    mod["moduleimpl_id"],
                    mod["module"]["ue_id"],
                    mod["matiere"]["ue_id"],
                )
            )
        if mod["ue"]["formation_id"] != mod["module"]["formation_id"]:
            diag.append(
                "moduleimpl %s: ue.formation_id=%s != mod.formation_id=%s"
                % (
                    mod["moduleimpl_id"],
                    mod["ue"]["formation_id"],
                    mod["module"]["formation_id"],
                )
            )
    if diag:
        send_scodoc_alarm(
            "Notes: formation incoherente dans semestre %s !" % formsemestre_id,
            "\n".join(diag),
        )
        log("check_formsemestre_integrity: formsemestre_id=%s" % formsemestre_id)
        log("inconsistencies:\n" + "\n".join(diag))
    else:
        diag = ["OK"]
        log("ok")
    return (
        html_sco_header.sco_header() + "<br/>".join(diag) + html_sco_header.sco_footer()
    )


@bp.route("/check_integrity_all")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def check_integrity_all():
    "debug: verifie tous les semestres et tt les formations"
    # formations
    for F in sco_formations.formation_list():
        check_form_integrity(F["formation_id"])
    # semestres
    for sem in sco_formsemestre.do_formsemestre_list():
        check_formsemestre_integrity(sem["formsemestre_id"])
    return (
        html_sco_header.sco_header()
        + "<p>empty page: see logs and mails</p>"
        + html_sco_header.sco_footer()
    )


# --------------------------------------------------------------------
#     Support for legacy ScoDoc 7 API
# --------------------------------------------------------------------
@bp.route("/moduleimpl_list")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def moduleimpl_list(
    moduleimpl_id=None, formsemestre_id=None, module_id=None, format="json"
):
    data = sco_moduleimpl.moduleimpl_list(
        moduleimpl_id=moduleimpl_id,
        formsemestre_id=formsemestre_id,
        module_id=module_id,
    )
    return scu.sendResult(data, format=format)


@bp.route("/do_moduleimpl_withmodule_list")  # ancien nom
@bp.route("/moduleimpl_withmodule_list")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def moduleimpl_withmodule_list(
    moduleimpl_id=None, formsemestre_id=None, module_id=None
):
    """API ScoDoc 7"""
    data = sco_moduleimpl.moduleimpl_withmodule_list(
        moduleimpl_id=moduleimpl_id,
        formsemestre_id=formsemestre_id,
        module_id=module_id,
    )
    return scu.sendResult(data, format=format)
