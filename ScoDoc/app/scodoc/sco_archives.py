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

"""ScoDoc : gestion des archives des PV et bulletins, et des dossiers etudiants (admission)


 Archives are plain files, stored in 
    <SCODOC_VAR_DIR>/archives/<dept_id>
 (where <SCODOC_VAR_DIR> is usually /opt/scodoc-data, and <dept_id> a departement id (int))

 Les PV de jurys et documents associés sont stockées dans un sous-repertoire de la forme
    <archivedir>/<dept>/<formsemestre_id>/<YYYY-MM-DD-HH-MM-SS>
 (formsemestre_id est ici FormSemestre.id)

 Les documents liés à l'étudiant sont dans
    <archivedir>/docetuds/<dept_id>/<etudid>/<YYYY-MM-DD-HH-MM-SS>
(etudid est ici Identite.id)

 Les maquettes Apogée pour l'export des notes sont dans
    <archivedir>/apo_csv/<dept_id>/<annee_scolaire>-<sem_id>/<YYYY-MM-DD-HH-MM-SS>/<code_etape>.csv
    
 Un répertoire d'archive contient des fichiers quelconques, et un fichier texte nommé _description.txt
 qui est une description (humaine, format libre) de l'archive.

"""
import datetime
import glob
import mimetypes
import os
import re
import shutil
import time

import flask
from flask import g, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
from config import Config
from app import log
from app.models import Departement
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc.sco_exceptions import (
    AccessDenied,
)
from app.scodoc import html_sco_header
from app.scodoc import sco_bulletins_pdf
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_permissions_check
from app.scodoc import sco_pvjury
from app.scodoc import sco_pvpdf


class BaseArchiver(object):
    def __init__(self, archive_type=""):
        self.archive_type = archive_type
        self.initialized = False
        self.root = None

    def initialize(self):
        if self.initialized:
            return
        dirs = [Config.SCODOC_VAR_DIR, "archives"]
        if self.archive_type:
            dirs.append(self.archive_type)

        self.root = os.path.join(*dirs)
        log("initialized archiver, path=" + self.root)
        path = dirs[0]
        for dir in dirs[1:]:
            path = os.path.join(path, dir)
            try:
                scu.GSL.acquire()
                if not os.path.isdir(path):
                    log("creating directory %s" % path)
                    os.mkdir(path)
            finally:
                scu.GSL.release()
                self.initialized = True

    def get_obj_dir(self, oid):
        """
        :return: path to directory of archives for this object (eg formsemestre_id or etudid).
        If directory does not yet exist, create it.
        """
        self.initialize()
        dept = Departement.query.filter_by(acronym=g.scodoc_dept).first()
        dept_dir = os.path.join(self.root, str(dept.id))
        try:
            scu.GSL.acquire()
            if not os.path.isdir(dept_dir):
                log("creating directory %s" % dept_dir)
                os.mkdir(dept_dir)
            obj_dir = os.path.join(dept_dir, str(oid))
            if not os.path.isdir(obj_dir):
                log("creating directory %s" % obj_dir)
                os.mkdir(obj_dir)
        finally:
            scu.GSL.release()
        return obj_dir

    def list_oids(self):
        """
        :return: list of archive oids
        """
        self.initialize()
        dept = Departement.query.filter_by(acronym=g.scodoc_dept).first()
        base = os.path.join(self.root, str(dept.id)) + os.path.sep
        dirs = glob.glob(base + "*")
        return [os.path.split(x)[1] for x in dirs]

    def list_obj_archives(self, oid):
        """Returns
        :return: list of archive identifiers for this object (paths to non empty dirs)
        """
        self.initialize()
        base = self.get_obj_dir(oid) + os.path.sep
        dirs = glob.glob(
            base
            + "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
        )
        dirs = [os.path.join(base, d) for d in dirs]
        dirs = [d for d in dirs if os.path.isdir(d) and os.listdir(d)]  # non empty dirs
        dirs.sort()
        return dirs

    def delete_archive(self, archive_id):
        """Delete (forever) this archive"""
        self.initialize()
        try:
            scu.GSL.acquire()
            shutil.rmtree(archive_id, ignore_errors=True)
        finally:
            scu.GSL.release()

    def get_archive_date(self, archive_id):
        """Returns date (as a DateTime object) of an archive"""
        dt = [int(x) for x in os.path.split(archive_id)[1].split("-")]
        return datetime.datetime(*dt)

    def list_archive(self, archive_id: str) -> str:
        """Return list of filenames (without path) in archive"""
        self.initialize()
        try:
            scu.GSL.acquire()
            files = os.listdir(archive_id)
        finally:
            scu.GSL.release()
        files.sort()
        return [f for f in files if f and f[0] != "_"]

    def get_archive_name(self, archive_id):
        """name identifying archive, to be used in web URLs"""
        return os.path.split(archive_id)[1]

    def is_valid_archive_name(self, archive_name):
        """check if name is valid."""
        return re.match(
            "^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}$", archive_name
        )

    def get_id_from_name(self, oid, archive_name):
        """returns archive id (check that name is valid)"""
        self.initialize()
        if not self.is_valid_archive_name(archive_name):
            raise ValueError("invalid archive name")
        archive_id = os.path.join(self.get_obj_dir(oid), archive_name)
        if not os.path.isdir(archive_id):
            log(
                "invalid archive name: %s, oid=%s, archive_id=%s"
                % (archive_name, oid, archive_id)
            )
            raise ValueError("invalid archive name")
        return archive_id

    def get_archive_description(self, archive_id):
        """Return description of archive"""
        self.initialize()
        with open(os.path.join(archive_id, "_description.txt")) as f:
            descr = f.read()
        return descr

    def create_obj_archive(self, oid: int, description: str):
        """Creates a new archive for this object and returns its id."""
        archive_id = (
            self.get_obj_dir(oid)
            + os.path.sep
            + "-".join(["%02d" % x for x in time.localtime()[:6]])
        )
        log("creating archive: %s" % archive_id)
        try:
            scu.GSL.acquire()
            os.mkdir(archive_id)  # if exists, raises an OSError
        finally:
            scu.GSL.release()
        self.store(archive_id, "_description.txt", description.encode("utf-8"))
        return archive_id

    def store(self, archive_id: str, filename: str, data: bytes):
        """Store data in archive, under given filename.
        Filename may be modified (sanitized): return used filename
        The file is created or replaced.
        """
        self.initialize()
        filename = scu.sanitize_filename(filename)
        log("storing %s (%d bytes) in %s" % (filename, len(data), archive_id))
        try:
            scu.GSL.acquire()
            fname = os.path.join(archive_id, filename)
            with open(fname, "wb") as f:
                f.write(data)
        finally:
            scu.GSL.release()
        return filename

    def get(self, archive_id: str, filename: str):
        """Retreive data"""
        self.initialize()
        if not scu.is_valid_filename(filename):
            log('Archiver.get: invalid filename "%s"' % filename)
            raise ValueError("invalid filename")
        fname = os.path.join(archive_id, filename)
        log("reading archive file %s" % fname)
        with open(fname, "rb") as f:
            data = f.read()
        return data

    def get_archived_file(self, oid, archive_name, filename):
        """Recupere donnees du fichier indiqué et envoie au client"""
        archive_id = self.get_id_from_name(oid, archive_name)
        data = self.get(archive_id, filename)
        mime = mimetypes.guess_type(filename)[0]
        if mime is None:
            mime = "application/octet-stream"

        return scu.send_file(data, filename, mime=mime)


class SemsArchiver(BaseArchiver):
    def __init__(self):
        BaseArchiver.__init__(self, archive_type="")


PVArchive = SemsArchiver()


# ----------------------------------------------------------------------------


def do_formsemestre_archive(
    formsemestre_id,
    group_ids=[],  # si indiqué, ne prend que ces groupes
    description="",
    date_jury="",
    signature=None,  # pour lettres indiv
    date_commission=None,
    numeroArrete=None,
    VDICode=None,
    showTitle=False,
    pv_title=None,
    with_paragraph_nom=False,
    anonymous=False,
    bulVersion="long",
):
    """Make and store new archive for this formsemestre.
    Store:
    - tableau recap (xls), pv jury (xls et pdf), bulletins (xml et pdf), lettres individuelles (pdf)
    """
    from app.scodoc.sco_recapcomplet import make_formsemestre_recapcomplet

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    sem_archive_id = formsemestre_id
    archive_id = PVArchive.create_obj_archive(sem_archive_id, description)
    date = PVArchive.get_archive_date(archive_id).strftime("%d/%m/%Y à %H:%M")

    if not group_ids:
        # tous les inscrits du semestre
        group_ids = [sco_groups.get_default_group(formsemestre_id)]
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, formsemestre_id=formsemestre_id
    )
    groups_filename = "-" + groups_infos.groups_filename
    etudids = [m["etudid"] for m in groups_infos.members]

    # Tableau recap notes en XLS (pour tous les etudiants, n'utilise pas les groupes)
    data, _, _ = make_formsemestre_recapcomplet(formsemestre_id, format="xls")
    if data:
        PVArchive.store(archive_id, "Tableau_moyennes" + scu.XLSX_SUFFIX, data)
    # Tableau recap notes en HTML (pour tous les etudiants, n'utilise pas les groupes)
    data, _, _ = make_formsemestre_recapcomplet(
        formsemestre_id, format="html", disable_etudlink=True
    )
    if data:
        data = "\n".join(
            [
                html_sco_header.sco_header(
                    page_title="Moyennes archivées le %s" % date,
                    head_message="Moyennes archivées le %s" % date,
                    no_side_bar=True,
                ),
                '<h2 class="fontorange">Valeurs archivées le %s</h2>' % date,
                '<style type="text/css">table.notes_recapcomplet tr {  color: rgb(185,70,0); }</style>',
                data,
                html_sco_header.sco_footer(),
            ]
        )
        data = data.encode(scu.SCO_ENCODING)
        PVArchive.store(archive_id, "Tableau_moyennes.html", data)

    # Bulletins en XML (pour tous les etudiants, n'utilise pas les groupes)
    data, _, _ = make_formsemestre_recapcomplet(
        formsemestre_id, format="xml", xml_with_decisions=True
    )
    if data:
        data = data.encode(scu.SCO_ENCODING)
        PVArchive.store(archive_id, "Bulletins.xml", data)
    # Decisions de jury, en XLS
    data = sco_pvjury.formsemestre_pvjury(formsemestre_id, format="xls", publish=False)
    if data:
        PVArchive.store(archive_id, "Decisions_Jury" + scu.XLSX_SUFFIX, data)
    # Classeur bulletins (PDF)
    data, _ = sco_bulletins_pdf.get_formsemestre_bulletins_pdf(
        formsemestre_id, version=bulVersion
    )
    if data:
        PVArchive.store(archive_id, "Bulletins.pdf", data)
    # Lettres individuelles (PDF):
    data = sco_pvpdf.pdf_lettres_individuelles(
        formsemestre_id,
        etudids=etudids,
        date_jury=date_jury,
        date_commission=date_commission,
        signature=signature,
    )
    if data:
        PVArchive.store(archive_id, "CourriersDecisions%s.pdf" % groups_filename, data)
    # PV de jury (PDF):
    dpv = sco_pvjury.dict_pvjury(formsemestre_id, etudids=etudids, with_prev=True)
    data = sco_pvpdf.pvjury_pdf(
        dpv,
        date_commission=date_commission,
        date_jury=date_jury,
        numeroArrete=numeroArrete,
        VDICode=VDICode,
        showTitle=showTitle,
        pv_title=pv_title,
        with_paragraph_nom=with_paragraph_nom,
        anonymous=anonymous,
    )
    if data:
        PVArchive.store(archive_id, "PV_Jury%s.pdf" % groups_filename, data)


def formsemestre_archive(formsemestre_id, group_ids=[]):
    """Make and store new archive for this formsemestre.
    (all students or only selected groups)
    """
    if not sco_permissions_check.can_edit_pv(formsemestre_id):
        raise AccessDenied("opération non autorisée pour %s" % str(current_user))

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not group_ids:
        # tous les inscrits du semestre
        group_ids = [sco_groups.get_default_group(formsemestre_id)]
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, formsemestre_id=formsemestre_id
    )

    H = [
        html_sco_header.html_sem_header(
            "Archiver les PV et résultats du semestre",
            sem=sem,
            javascripts=sco_groups_view.JAVASCRIPTS,
            cssstyles=sco_groups_view.CSSSTYLES,
            init_qtip=True,
        ),
        """<p class="help">Cette page permet de générer et d'archiver tous
les documents résultant de ce semestre: PV de jury, lettres individuelles,
tableaux récapitulatifs.</p><p class="help">Les documents archivés sont
enregistrés et non modifiables, on peut les retrouver ultérieurement.
</p><p class="help">On peut archiver plusieurs versions des documents
(avant et après le jury par exemple).
</p>
        """,
    ]
    F = [
        """<p><em>Note: les documents sont aussi affectés par les réglages sur la page "<a href="edit_preferences">Paramétrage</a>" (accessible à l'administrateur du département).</em>
        </p>""",
        html_sco_header.sco_footer(),
    ]

    descr = [
        (
            "description",
            {"input_type": "textarea", "rows": 4, "cols": 77, "title": "Description"},
        ),
        ("sep", {"input_type": "separator", "title": "Informations sur PV de jury"}),
    ]
    descr += sco_pvjury.descrform_pvjury(sem)
    descr += [
        (
            "signature",
            {
                "input_type": "file",
                "size": 30,
                "explanation": "optionnel: image scannée de la signature pour les lettres individuelles",
            },
        ),
        (
            "bulVersion",
            {
                "input_type": "menu",
                "title": "Version des bulletins archivés",
                "labels": [
                    "Version courte",
                    "Version intermédiaire",
                    "Version complète",
                ],
                "allowed_values": scu.BULLETINS_VERSIONS,
                "default": "long",
            },
        ),
    ]
    menu_choix_groupe = (
        """<div class="group_ids_sel_menu">Groupes d'étudiants à lister: """
        + sco_groups_view.menu_groups_choice(groups_infos)
        + """(pour les PV et lettres)</div>"""
    )

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        cancelbutton="Annuler",
        method="POST",
        submitlabel="Générer et archiver les documents",
        name="tf",
        formid="group_selector",
        html_foot_markup=menu_choix_groupe,
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + "\n".join(F)
    elif tf[0] == -1:
        msg = "Opération%20annulée"
    else:
        # submit
        sf = tf[2]["signature"]
        signature = sf.read()  # image of signature
        if tf[2]["anonymous"]:
            tf[2]["anonymous"] = True
        else:
            tf[2]["anonymous"] = False
        do_formsemestre_archive(
            formsemestre_id,
            group_ids=group_ids,
            description=tf[2]["description"],
            date_jury=tf[2]["date_jury"],
            date_commission=tf[2]["date_commission"],
            signature=signature,
            numeroArrete=tf[2]["numeroArrete"],
            VDICode=tf[2]["VDICode"],
            pv_title=tf[2]["pv_title"],
            showTitle=tf[2]["showTitle"],
            with_paragraph_nom=tf[2]["with_paragraph_nom"],
            anonymous=tf[2]["anonymous"],
            bulVersion=tf[2]["bulVersion"],
        )
        msg = "Nouvelle%20archive%20créée"

    # submitted or cancelled:
    return flask.redirect(
        "formsemestre_list_archives?formsemestre_id=%s&head_message=%s"
        % (formsemestre_id, msg)
    )


def formsemestre_list_archives(formsemestre_id):
    """Page listing archives"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    sem_archive_id = formsemestre_id
    L = []
    for archive_id in PVArchive.list_obj_archives(sem_archive_id):
        a = {
            "archive_id": archive_id,
            "description": PVArchive.get_archive_description(archive_id),
            "date": PVArchive.get_archive_date(archive_id),
            "content": PVArchive.list_archive(archive_id),
        }
        L.append(a)

    H = [html_sco_header.html_sem_header("Archive des PV et résultats ", sem)]
    if not L:
        H.append("<p>aucune archive enregistrée</p>")
    else:
        H.append("<ul>")
        for a in L:
            archive_name = PVArchive.get_archive_name(a["archive_id"])
            H.append(
                '<li>%s : <em>%s</em> (<a href="formsemestre_delete_archive?formsemestre_id=%s&archive_name=%s">supprimer</a>)<ul>'
                % (
                    a["date"].strftime("%d/%m/%Y %H:%M"),
                    a["description"],
                    formsemestre_id,
                    archive_name,
                )
            )
            for filename in a["content"]:
                H.append(
                    '<li><a href="formsemestre_get_archived_file?formsemestre_id=%s&archive_name=%s&filename=%s">%s</a></li>'
                    % (formsemestre_id, archive_name, filename, filename)
                )
            if not a["content"]:
                H.append("<li><em>aucun fichier !</em></li>")
            H.append("</ul></li>")
        H.append("</ul>")

    return "\n".join(H) + html_sco_header.sco_footer()


def formsemestre_get_archived_file(formsemestre_id, archive_name, filename):
    """Send file to client."""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    sem_archive_id = formsemestre_id
    return PVArchive.get_archived_file(sem_archive_id, archive_name, filename)


def formsemestre_delete_archive(formsemestre_id, archive_name, dialog_confirmed=False):
    """Delete an archive"""
    if not sco_permissions_check.can_edit_pv(formsemestre_id):
        raise AccessDenied("opération non autorisée pour %s" % str(current_user))
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    sem_archive_id = formsemestre_id
    archive_id = PVArchive.get_id_from_name(sem_archive_id, archive_name)

    dest_url = "formsemestre_list_archives?formsemestre_id=%s" % (formsemestre_id)

    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Confirmer la suppression de l'archive du %s ?</h2>
               <p>La suppression sera définitive.</p>"""
            % PVArchive.get_archive_date(archive_id).strftime("%d/%m/%Y %H:%M"),
            dest_url="",
            cancel_url=dest_url,
            parameters={
                "formsemestre_id": formsemestre_id,
                "archive_name": archive_name,
            },
        )

    PVArchive.delete_archive(archive_id)
    return flask.redirect(dest_url + "&head_message=Archive%20supprimée")
