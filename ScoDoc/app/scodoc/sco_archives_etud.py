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

"""ScoDoc : gestion des fichiers archivés associés aux étudiants
     Il s'agit de fichiers quelconques, généralement utilisés pour conserver
     les dossiers d'admission et autres pièces utiles.
"""
import flask
from flask import url_for, render_template
from flask import g, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
from app.scodoc import sco_import_etuds
from app.scodoc import sco_groups
from app.scodoc import sco_trombino
from app.scodoc import sco_excel
from app.scodoc import sco_archives
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc import html_sco_header
from app.scodoc import sco_etud


class EtudsArchiver(sco_archives.BaseArchiver):
    def __init__(self):
        sco_archives.BaseArchiver.__init__(self, archive_type="docetuds")


EtudsArchive = EtudsArchiver()


def can_edit_etud_archive(authuser):
    """True si l'utilisateur peut modifier les archives etudiantes"""
    return authuser.has_permission(Permission.ScoEtudAddAnnotations)


def etud_list_archives_html(etudid):
    """HTML snippet listing archives"""
    can_edit = can_edit_etud_archive(current_user)
    etuds = sco_etud.get_etud_info(etudid=etudid)
    if not etuds:
        raise ScoValueError("étudiant inexistant")
    etud = etuds[0]
    etud_archive_id = etudid
    L = []
    for archive_id in EtudsArchive.list_obj_archives(etud_archive_id):
        a = {
            "archive_id": archive_id,
            "description": EtudsArchive.get_archive_description(archive_id),
            "date": EtudsArchive.get_archive_date(archive_id),
            "content": EtudsArchive.list_archive(archive_id),
        }
        L.append(a)
    delete_icon = scu.icontag(
        "delete_small_img", title="Supprimer fichier", alt="supprimer"
    )
    delete_disabled_icon = scu.icontag(
        "delete_small_dis_img", title="Suppression non autorisée"
    )
    H = ['<div class="etudarchive"><ul>']
    for a in L:
        archive_name = EtudsArchive.get_archive_name(a["archive_id"])
        H.append(
            """<li><span class ="etudarchive_descr" title="%s">%s</span>"""
            % (a["date"].strftime("%d/%m/%Y %H:%M"), a["description"])
        )
        for filename in a["content"]:
            H.append(
                """<a class="stdlink etudarchive_link" href="etud_get_archived_file?etudid=%s&archive_name=%s&filename=%s">%s</a>"""
                % (etudid, archive_name, filename, filename)
            )
        if not a["content"]:
            H.append("<em>aucun fichier !</em>")
        if can_edit:
            H.append(
                '<span class="deletudarchive"><a class="smallbutton" href="etud_delete_archive?etudid=%s&archive_name=%s">%s</a></span>'
                % (etudid, archive_name, delete_icon)
            )
        else:
            H.append('<span class="deletudarchive">' + delete_disabled_icon + "</span>")
        H.append("</li>")
    if can_edit:
        H.append(
            '<li class="addetudarchive"><a class="stdlink" href="etud_upload_file_form?etudid=%s">ajouter un fichier</a></li>'
            % etudid
        )
    H.append("</ul></div>")
    return "".join(H)


def add_archives_info_to_etud_list(etuds):
    """Add key 'etudarchive' describing archive of etuds
    (used to list all archives of a group)
    """
    for etud in etuds:
        l = []
        etud_archive_id = etud["etudid"]
        for archive_id in EtudsArchive.list_obj_archives(etud_archive_id):
            l.append(
                "%s (%s)"
                % (
                    EtudsArchive.get_archive_description(archive_id),
                    EtudsArchive.list_archive(archive_id)[0],
                )
            )
            etud["etudarchive"] = ", ".join(l)


def etud_upload_file_form(etudid):
    """Page with a form to choose and upload a file, with a description."""
    # check permission
    if not can_edit_etud_archive(current_user):
        raise AccessDenied("opération non autorisée pour %s" % current_user)
    etuds = sco_etud.get_etud_info(filled=True)
    if not etuds:
        raise ScoValueError("étudiant inexistant")
    etud = etuds[0]
    H = [
        html_sco_header.sco_header(
            page_title="Chargement d'un document associé à %(nomprenom)s" % etud,
        ),
        """<h2>Chargement d'un document associé à %(nomprenom)s</h2>                     
         """
        % etud,
        """<p>Le fichier ne doit pas dépasser %sMo.</p>             
         """
        % (scu.CONFIG.ETUD_MAX_FILE_SIZE // (1024 * 1024)),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("etudid", {"default": etudid, "input_type": "hidden"}),
            ("datafile", {"input_type": "file", "title": "Fichier", "size": 30}),
            (
                "description",
                {
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 77,
                    "title": "Description",
                },
            ),
        ),
        submitlabel="Valider",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )
    else:
        data = tf[2]["datafile"].read()
        descr = tf[2]["description"]
        filename = tf[2]["datafile"].filename
        etud_archive_id = etud["etudid"]
        _store_etud_file_to_new_archive(
            etud_archive_id, data, filename, description=descr
        )
        return flask.redirect(
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )


def _store_etud_file_to_new_archive(etud_archive_id, data, filename, description=""):
    """Store data to new archive."""
    filesize = len(data)
    if filesize < 10 or filesize > scu.CONFIG.ETUD_MAX_FILE_SIZE:
        return 0, "Fichier image de taille invalide ! (%d)" % filesize
    archive_id = EtudsArchive.create_obj_archive(etud_archive_id, description)
    EtudsArchive.store(archive_id, filename, data)


def etud_delete_archive(etudid, archive_name, dialog_confirmed=False):
    """Delete an archive"""
    # check permission
    if not can_edit_etud_archive(current_user):
        raise AccessDenied("opération non autorisée pour %s" % str(current_user))
    etuds = sco_etud.get_etud_info(filled=True)
    if not etuds:
        raise ScoValueError("étudiant inexistant")
    etud = etuds[0]
    etud_archive_id = etud["etudid"]
    archive_id = EtudsArchive.get_id_from_name(etud_archive_id, archive_name)
    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Confirmer la suppression des fichiers ?</h2>
            <p>Fichier associé le %s à l'étudiant %s</p>
               <p>La suppression sera définitive.</p>"""
            % (
                EtudsArchive.get_archive_date(archive_id).strftime("%d/%m/%Y %H:%M"),
                etud["nomprenom"],
            ),
            dest_url="",
            cancel_url=url_for(
                "scolar.ficheEtud",
                scodoc_dept=g.scodoc_dept,
                etudid=etudid,
                head_message="annulation",
            ),
            parameters={"etudid": etudid, "archive_name": archive_name},
        )

    EtudsArchive.delete_archive(archive_id)
    return flask.redirect(
        url_for(
            "scolar.ficheEtud",
            scodoc_dept=g.scodoc_dept,
            etudid=etudid,
            head_message="Archive%20supprimée",
        )
    )


def etud_get_archived_file(etudid, archive_name, filename):
    """Send file to client."""
    etuds = sco_etud.get_etud_info(etudid=etudid, filled=True)
    if not etuds:
        raise ScoValueError("étudiant inexistant")
    etud = etuds[0]
    etud_archive_id = etud["etudid"]
    return EtudsArchive.get_archived_file(etud_archive_id, archive_name, filename)


# --- Upload d'un ensemble de fichiers (pour un groupe d'étudiants)
def etudarchive_generate_excel_sample(group_id=None):
    """Feuille excel pour import fichiers etudiants (utilisé pour admissions)"""
    fmt = sco_import_etuds.sco_import_format()
    data = sco_import_etuds.sco_import_generate_excel_sample(
        fmt,
        group_ids=[group_id],
        only_tables=["identite"],
        exclude_cols=[
            "date_naissance",
            "lieu_naissance",
            "nationalite",
            "statut",
            "photo_filename",
        ],
        extra_cols=["fichier_a_charger"],
    )
    return scu.send_file(
        data,
        "ImportFichiersEtudiants",
        suffix=scu.XLSX_SUFFIX,
        mime=scu.XLSX_MIMETYPE,
    )


def etudarchive_import_files_form(group_id):
    """Formulaire pour importation fichiers d'un groupe"""
    H = [
        html_sco_header.sco_header(
            page_title="Import de fichiers associés aux étudiants"
        ),
        """<h2 class="formsemestre">Téléchargement de fichier associés aux étudiants</h2>
        <p>Les fichiers associés (dossiers d'admission, certificats, ...), de 
        types quelconques (pdf, doc, images) sont accessibles aux utilisateurs via 
        la fiche individuelle de l'étudiant.
        </p>
        <p class="warning">Ne pas confondre avec les photos des étudiants, qui se
        chargent via l'onglet "Photos".</p>
         <p><b>Vous pouvez aussi charger à tout moment de nouveaux fichiers, ou en
        supprimer, via la fiche de chaque étudiant.</b>
         </p>
         <p class="help">Cette page permet de charger en une seule fois les fichiers
        de plusieurs étudiants.<br/>
          Il faut d'abord remplir une feuille excel donnant les noms
          des fichiers (un fichier par étudiant).
         </p>
         <p class="help">Ensuite, réunir vos fichiers dans un fichier zip, puis
        télécharger simultanément le fichier excel et le fichier zip.
         </p>
        <ol>
        <li><a class="stdlink" href="etudarchive_generate_excel_sample?group_id=%s">
        Obtenir la feuille excel à remplir</a>
        </li>
        <li style="padding-top: 2em;">
         """
        % group_id,
    ]
    F = html_sco_header.sco_footer()
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("xlsfile", {"title": "Fichier Excel:", "input_type": "file", "size": 40}),
            ("zipfile", {"title": "Fichier zip:", "input_type": "file", "size": 40}),
            (
                "description",
                {
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 77,
                    "title": "Description",
                },
            ),
            ("group_id", {"input_type": "hidden"}),
        ),
    )

    if tf[0] == 0:
        return "\n".join(H) + tf[1] + "</li></ol>" + F
    # retrouve le semestre à partir du groupe:
    group = sco_groups.get_group(group_id)
    if tf[0] == -1:
        return flask.redirect(
            url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=group["formsemestre_id"],
            )
        )
    else:
        return etudarchive_import_files(
            formsemestre_id=group["formsemestre_id"],
            xlsfile=tf[2]["xlsfile"],
            zipfile=tf[2]["zipfile"],
            description=tf[2]["description"],
        )


def etudarchive_import_files(
    formsemestre_id=None, xlsfile=None, zipfile=None, description=""
):
    "Importe des fichiers"

    def callback(etud, data, filename):
        _store_etud_file_to_new_archive(etud["etudid"], data, filename, description)

    # Utilise la fontion developpée au depart pour les photos
    (
        ignored_zipfiles,
        unmatched_files,
        stored_etud_filename,
    ) = sco_trombino.zip_excel_import_files(
        xlsfile=xlsfile,
        zipfile=zipfile,
        callback=callback,
        filename_title="fichier_a_charger",
    )
    return render_template(
        "scolar/photos_import_files.html",
        page_title="Téléchargement de fichiers associés aux étudiants",
        ignored_zipfiles=ignored_zipfiles,
        unmatched_files=unmatched_files,
        stored_etud_filename=stored_etud_filename,
        next_page=url_for(
            "scolar.groups_view",
            scodoc_dept=g.scodoc_dept,
            formsemestre_id=formsemestre_id,
        ),
    )
