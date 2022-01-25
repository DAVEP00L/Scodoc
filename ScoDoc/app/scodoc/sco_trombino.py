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

"""Photos: trombinoscopes
"""

import io
from zipfile import ZipFile, BadZipfile
from flask.templating import render_template
import reportlab
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageBreak
from reportlab.platypus import Table, TableStyle, Image, KeepInFrame
from reportlab.platypus.flowables import Flowable
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import styles
from reportlab.lib.colors import Color
from reportlab.lib import colors
from PIL import Image as PILImage

import flask
from flask import url_for, g, send_file, request

from app import log
import app.scodoc.sco_utils as scu
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_pdf import SU
from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_import_etuds
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_pdf
from app.scodoc import sco_photos
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app.scodoc import sco_etud


def trombino(
    group_ids=[],  # liste des groupes à afficher
    formsemestre_id=None,  # utilisé si pas de groupes selectionné
    etat=None,
    format="html",
    dialog_confirmed=False,
):
    """Trombinoscope"""
    if not etat:
        etat = None  # may be passed as ''
    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, formsemestre_id=formsemestre_id, etat=etat
    )

    #
    if format != "html" and not dialog_confirmed:
        ok, dialog = check_local_photos_availability(groups_infos, format=format)
        if not ok:
            return dialog

    if format == "zip":
        return _trombino_zip(groups_infos)
    elif format == "pdf":
        return _trombino_pdf(groups_infos)
    elif format == "pdflist":
        return _listeappel_photos_pdf(groups_infos)
    else:
        raise Exception("invalid format")
        # return _trombino_html_header() + trombino_html( group, members) + html_sco_header.sco_footer()


def _trombino_html_header():
    return html_sco_header.sco_header(javascripts=["js/trombino.js"])


def trombino_html(groups_infos):
    "HTML snippet for trombino (with title and menu)"
    menuTrombi = [
        {
            "title": "Charger des photos...",
            "endpoint": "scolar.photos_import_files_form",
            "args": {"group_ids": groups_infos.group_ids},
        },
        {
            "title": "Obtenir archive Zip des photos",
            "endpoint": "scolar.trombino",
            "args": {"group_ids": groups_infos.group_ids, "format": "zip"},
        },
        {
            "title": "Recopier les photos depuis le portail",
            "endpoint": "scolar.trombino_copy_photos",
            "args": {"group_ids": groups_infos.group_ids},
        },
    ]

    if groups_infos.members:
        if groups_infos.tous_les_etuds_du_sem:
            ng = "Tous les étudiants"
        else:
            ng = "Groupe %s" % groups_infos.groups_titles
    else:
        ng = "Aucun étudiant inscrit dans ce groupe !"
    H = [
        '<table style="padding-top: 10px; padding-bottom: 10px;"><tr><td><span style="font-style: bold; font-size: 150%%; padding-right: 20px;">%s</span></td>'
        % (ng)
    ]
    if groups_infos.members:
        H.append(
            "<td>"
            + htmlutils.make_menu("Gérer les photos", menuTrombi, alone=True)
            + "</td>"
        )
    H.append("</tr></table>")
    H.append("<div>")
    i = 0
    for t in groups_infos.members:
        H.append(
            '<span class="trombi_box"><span class="trombi-photo" id="trombi-%s">'
            % t["etudid"]
        )
        if sco_photos.etud_photo_is_local(t, size="small"):
            foto = sco_photos.etud_photo_html(t, title="")
        else:  # la photo n'est pas immédiatement dispo
            foto = (
                '<span class="unloaded_img" id="%s"><img border="0" height="90" alt="en cours" src="/ScoDoc/static/icons/loading.jpg"/></span>'
                % t["etudid"]
            )
        H.append(
            '<a href="%s">%s</a>'
            % (
                url_for(
                    "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=t["etudid"]
                ),
                foto,
            )
        )
        H.append("</span>")
        H.append(
            '<span class="trombi_legend"><span class="trombi_prenom">'
            + sco_etud.format_prenom(t["prenom"])
            + '</span><span class="trombi_nom">'
            + sco_etud.format_nom(t["nom"])
            + (" <i>(dem.)</i>" if t["etat"] == "D" else "")
        )
        H.append("</span></span></span>")
        i += 1

    H.append("</div>")
    H.append(
        '<div style="margin-bottom:15px;"><a class="stdlink" href="trombino?format=pdf&%s">Version PDF</a></div>'
        % groups_infos.groups_query_args
    )
    return "\n".join(H)


def check_local_photos_availability(groups_infos, format=""):
    """Verifie que toutes les photos (des gropupes indiqués) sont copiées localement
    dans ScoDoc (seules les photos dont nous disposons localement peuvent être exportées
    en pdf ou en zip).
    Si toutes ne sont pas dispo, retourne un dialogue d'avertissement pour l'utilisateur.
    """
    nb_missing = 0
    for t in groups_infos.members:
        _ = sco_photos.etud_photo_url(t)  # -> copy distant files if needed
        if not sco_photos.etud_photo_is_local(t):
            nb_missing += 1
    if nb_missing > 0:
        parameters = {"group_ids": groups_infos.group_ids, "format": format}
        return (
            False,
            scu.confirm_dialog(
                """<p>Attention: %d photos ne sont pas disponibles et ne peuvent pas être exportées.</p><p>Vous pouvez <a class="stdlink" href="%s">exporter seulement les photos existantes</a>"""
                % (
                    nb_missing,
                    groups_infos.base_url + "&dialog_confirmed=1&format=%s" % format,
                ),
                dest_url="trombino",
                OK="Exporter seulement les photos existantes",
                cancel_url="groups_view?curtab=tab-photos&"
                + groups_infos.groups_query_args,
                parameters=parameters,
            ),
        )
    else:
        return True, ""


def _trombino_zip(groups_infos):
    "Send photos as zip archive"
    data = io.BytesIO()
    Z = ZipFile(data, "w")
    # assume we have the photos (or the user acknowledged the fact)
    # Archive originals (not reduced) images, in JPEG
    for t in groups_infos.members:
        im_path = sco_photos.photo_pathname(t, size="orig")
        if not im_path:
            continue
        img = open(im_path, "rb").read()
        code_nip = t["code_nip"]
        if code_nip:
            filename = code_nip + ".jpg"
        else:
            filename = t["nom"] + "_" + t["prenom"] + "_" + t["etudid"] + ".jpg"
        Z.writestr(filename, img)
    Z.close()
    size = data.tell()
    log("trombino_zip: %d bytes" % size)
    data.seek(0)
    return send_file(
        data,
        mimetype="application/zip",
        download_name="trombi.zip",
        as_attachment=True,
    )


# Copy photos from portal to ScoDoc
def trombino_copy_photos(group_ids=[], dialog_confirmed=False):
    "Copy photos from portal to ScoDoc (overwriting local copy)"
    groups_infos = sco_groups_view.DisplayedGroupsInfos(group_ids)
    back_url = "groups_view?%s&curtab=tab-photos" % groups_infos.groups_query_args

    portal_url = sco_portal_apogee.get_portal_url()
    header = html_sco_header.sco_header(page_title="Chargement des photos")
    footer = html_sco_header.sco_footer()
    if not portal_url:
        return (
            header
            + '<p>portail non configuré</p><p><a href="%s">Retour au trombinoscope</a></p>'
            % back_url
            + footer
        )
    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Copier les photos du portail vers ScoDoc ?</h2>
                <p>Les photos du groupe %s présentes dans ScoDoc seront remplacées par celles du portail (si elles existent).</p>
                <p>(les photos sont normalement automatiquement copiées lors de leur première utilisation, l'usage de cette fonction n'est nécessaire que si les photos du portail ont été modifiées)</p>
                """
            % (groups_infos.groups_titles),
            dest_url="",
            cancel_url=back_url,
            parameters={"group_ids": group_ids},
        )

    msg = []
    nok = 0
    for etud in groups_infos.members:
        path, diag = sco_photos.copy_portal_photo_to_fs(etud)
        msg.append(diag)
        if path:
            nok += 1

    msg.append("<b>%d photos correctement chargées</b>" % nok)

    return (
        header
        + "<h2>Chargement des photos depuis le portail</h2><ul><li>"
        + "</li><li>".join(msg)
        + "</li></ul>"
        + '<p><a href="%s">retour au trombinoscope</a>' % back_url
        + footer
    )


def _get_etud_platypus_image(t, image_width=2 * cm):
    """Returns aplatypus object for the photo of student t"""
    try:
        path = sco_photos.photo_pathname(t, size="small")
        if not path:
            # log('> unknown')
            path = sco_photos.UNKNOWN_IMAGE_PATH
        im = PILImage.open(path)
        w0, h0 = im.size[0], im.size[1]
        if w0 > h0:
            W = image_width
            H = h0 * W / w0
        else:
            H = image_width
            W = w0 * H / h0
        return reportlab.platypus.Image(path, width=W, height=H)
    except:
        log(
            "*** exception while processing photo of %s (%s) (path=%s)"
            % (t["nom"], t["etudid"], path)
        )
        raise


def _trombino_pdf(groups_infos):
    "Send photos as pdf page"
    # Generate PDF page
    filename = "trombino_%s" % groups_infos.groups_filename + ".pdf"
    sem = groups_infos.formsemestre  # suppose 1 seul semestre

    PHOTOWIDTH = 3 * cm
    COLWIDTH = 3.6 * cm
    N_PER_ROW = 5  # XXX should be in ScoDoc preferences

    StyleSheet = styles.getSampleStyleSheet()
    report = io.BytesIO()  # in-memory document, no disk file
    objects = [
        Paragraph(
            SU("Trombinoscope " + sem["titreannee"] + " " + groups_infos.groups_titles),
            StyleSheet["Heading3"],
        )
    ]
    L = []
    n = 0
    currow = []
    log("_trombino_pdf %d elements" % len(groups_infos.members))
    for t in groups_infos.members:
        img = _get_etud_platypus_image(t, image_width=PHOTOWIDTH)
        elem = Table(
            [
                [img],
                [
                    Paragraph(
                        SU(sco_etud.format_nomprenom(t)),
                        StyleSheet["Normal"],
                    )
                ],
            ],
            colWidths=[PHOTOWIDTH],
        )
        currow.append(elem)
        if n == (N_PER_ROW - 1):
            L.append(currow)
            currow = []
        n = (n + 1) % N_PER_ROW
    if currow:
        currow += [" "] * (N_PER_ROW - len(currow))
        L.append(currow)
    if not L:
        table = Paragraph(SU("Aucune photo à exporter !"), StyleSheet["Normal"])
    else:
        table = Table(
            L,
            colWidths=[COLWIDTH] * N_PER_ROW,
            style=TableStyle(
                [
                    # ('RIGHTPADDING', (0,0), (-1,-1), -5*mm),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ]
            ),
        )
    objects.append(table)
    # Build document
    document = BaseDocTemplate(report)
    document.addPageTemplates(
        sco_pdf.ScolarsPageTemplate(
            document,
            preferences=sco_preferences.SemPreferences(sem["formsemestre_id"]),
        )
    )
    document.build(objects)
    report.seek(0)
    return send_file(
        report,
        mimetype=scu.PDF_MIMETYPE,
        download_name=scu.sanitize_filename(filename),
        as_attachment=True,
    )


# --------------------- Sur une idée de l'IUT d'Orléans:
def _listeappel_photos_pdf(groups_infos):
    "Doc pdf pour liste d'appel avec photos"
    filename = "trombino_%s" % groups_infos.groups_filename + ".pdf"
    sem = groups_infos.formsemestre  # suppose 1 seul semestre

    PHOTOWIDTH = 2 * cm
    # COLWIDTH = 3.6 * cm
    # ROWS_PER_PAGE = 26  # XXX should be in ScoDoc preferences

    StyleSheet = styles.getSampleStyleSheet()
    report = io.BytesIO()  # in-memory document, no disk file
    objects = [
        Paragraph(
            SU(
                sem["titreannee"]
                + " "
                + groups_infos.groups_titles
                + " (%d)" % len(groups_infos.members)
            ),
            StyleSheet["Heading3"],
        )
    ]
    L = []
    n = 0
    currow = []
    log("_listeappel_photos_pdf %d elements" % len(groups_infos.members))
    n = len(groups_infos.members)
    # npages = n / 2*ROWS_PER_PAGE + 1 # nb de pages papier
    # for page in range(npages):
    for i in range(n):  # page*2*ROWS_PER_PAGE, (page+1)*2*ROWS_PER_PAGE):
        t = groups_infos.members[i]
        img = _get_etud_platypus_image(t, image_width=PHOTOWIDTH)
        txt = Paragraph(
            SU(sco_etud.format_nomprenom(t)),
            StyleSheet["Normal"],
        )
        if currow:
            currow += [""]
        currow += [img, txt, ""]
        if i % 2:
            L.append(currow)
            currow = []
    if currow:
        currow += [" "] * 3
        L.append(currow)
    if not L:
        table = Paragraph(SU("Aucune photo à exporter !"), StyleSheet["Normal"])
    else:
        table = Table(
            L,
            colWidths=[2 * cm, 4 * cm, 27 * mm, 5 * mm, 2 * cm, 4 * cm, 27 * mm],
            style=TableStyle(
                [
                    # ('RIGHTPADDING', (0,0), (-1,-1), -5*mm),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (2, -1), 0.25, colors.grey),
                    ("GRID", (4, 0), (-1, -1), 0.25, colors.grey),
                ]
            ),
        )
    objects.append(table)
    # Build document
    document = BaseDocTemplate(report)
    document.addPageTemplates(
        sco_pdf.ScolarsPageTemplate(
            document,
            preferences=sco_preferences.SemPreferences(sem["formsemestre_id"]),
        )
    )
    document.build(objects)
    data = report.getvalue()

    return scu.sendPDFFile(data, filename)


# ---------------------    Upload des photos de tout un groupe
def photos_generate_excel_sample(group_ids=[]):
    """Feuille excel pour import fichiers photos"""
    fmt = sco_import_etuds.sco_import_format()
    data = sco_import_etuds.sco_import_generate_excel_sample(
        fmt,
        group_ids=group_ids,
        only_tables=["identite"],
        exclude_cols=[
            "date_naissance",
            "lieu_naissance",
            "nationalite",
            "statut",
            "photo_filename",
        ],
        extra_cols=["fichier_photo"],
    )
    return scu.send_file(
        data, "ImportPhotos", scu.XLSX_SUFFIX, scu.XLSX_MIMETYPE, attached=True
    )
    # return sco_excel.send_excel_file(data, "ImportPhotos" + scu.XLSX_SUFFIX)


def photos_import_files_form(group_ids=[]):
    """Formulaire pour importation photos"""
    if not group_ids:
        raise ScoValueError("paramètre manquant !")
    groups_infos = sco_groups_view.DisplayedGroupsInfos(group_ids)
    back_url = "groups_view?%s&curtab=tab-photos" % groups_infos.groups_query_args

    H = [
        html_sco_header.sco_header(page_title="Import des photos des étudiants"),
        """<h2 class="formsemestre">Téléchargement des photos des étudiants</h2>
         <p><b>Vous pouvez aussi charger les photos individuellement via la fiche de chaque étudiant (menu "Etudiant" / "Changer la photo").</b></p>
         <p class="help">Cette page permet de charger en une seule fois les photos de plusieurs étudiants.<br/>
          Il faut d'abord remplir une feuille excel donnant les noms 
          des fichiers images (une image par étudiant).
         </p>
         <p class="help">Ensuite, réunir vos images dans un fichier zip, puis télécharger 
         simultanément le fichier excel et le fichier zip.
         </p>
        <ol>
        <li><a class="stdlink" href="photos_generate_excel_sample?%s">
        Obtenir la feuille excel à remplir</a>
        </li>
        <li style="padding-top: 2em;">
         """
        % groups_infos.groups_query_args,
    ]
    F = html_sco_header.sco_footer()
    vals = scu.get_request_args()
    vals["group_ids"] = groups_infos.group_ids
    tf = TrivialFormulator(
        request.base_url,
        vals,
        (
            ("xlsfile", {"title": "Fichier Excel:", "input_type": "file", "size": 40}),
            ("zipfile", {"title": "Fichier zip:", "input_type": "file", "size": 40}),
            ("group_ids", {"input_type": "hidden", "type": "list"}),
        ),
    )

    if tf[0] == 0:
        return "\n".join(H) + tf[1] + "</li></ol>" + F
    elif tf[0] == -1:
        return flask.redirect(back_url)
    else:

        def callback(etud, data, filename):
            sco_photos.store_photo(etud, data)

        (
            ignored_zipfiles,
            unmatched_files,
            stored_etud_filename,
        ) = zip_excel_import_files(
            xlsfile=tf[2]["xlsfile"],
            zipfile=tf[2]["zipfile"],
            callback=callback,
            filename_title="fichier_photo",
        )
        return render_template(
            "scolar/photos_import_files.html",
            page_title="Téléchargement des photos des étudiants",
            ignored_zipfiles=ignored_zipfiles,
            unmatched_files=unmatched_files,
            stored_etud_filename=stored_etud_filename,
            next_page=url_for(
                "scolar.groups_view",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=groups_infos.formsemestre_id,
                curtab="tab-photos",
            ),
        )


def zip_excel_import_files(
    xlsfile=None,
    zipfile=None,
    callback=None,
    filename_title="",  # doit obligatoirement etre specifié
):
    """Importation de fichiers à partir d'un excel et d'un zip
    La fonction
       callback()
    est appelée pour chaque fichier trouvé.
    Fonction utilisée pour les photos et les fichiers étudiants (archives).
    """
    # 1- build mapping etudid -> filename
    exceldata = xlsfile.read()
    if not exceldata:
        raise ScoValueError("Fichier excel vide ou invalide")
    _, data = sco_excel.excel_bytes_to_list(exceldata)
    if not data:
        raise ScoValueError("Fichier excel vide !")
    # on doit avoir une colonne etudid et une colonne filename_title ('fichier_photo')
    titles = data[0]
    try:
        etudid_idx = titles.index("etudid")
        filename_idx = titles.index(filename_title)
    except:
        raise ScoValueError(
            "Fichier excel incorrect (il faut une colonne etudid et une colonne %s) !"
            % filename_title
        )

    def normfilename(fn, lowercase=True):
        "normalisation used to match filenames"
        fn = fn.replace("\\", "/")  # not sure if this is necessary ?
        fn = fn.strip()
        if lowercase:
            fn = fn.lower()
        fn = fn.split("/")[-1]  # use only last component, not directories
        return fn

    filename_to_etud = {}  # filename : etudid
    for l in data[1:]:
        filename = l[filename_idx].strip()
        if filename:
            filename_to_etud[normfilename(filename)] = l[etudid_idx]

    # 2- Ouvre le zip et
    try:
        z = ZipFile(zipfile)
    except BadZipfile:
        raise ScoValueError("Fichier ZIP incorrect !") from BadZipfile
    ignored_zipfiles = []
    stored_etud_filename = []  # [ (etud, filename) ]
    for name in z.namelist():
        if len(name) > 4 and name[-1] != "/" and "." in name:
            data = z.read(name)
            # match zip filename with name given in excel
            normname = normfilename(name)
            if normname in filename_to_etud:
                etudid = filename_to_etud[normname]
                # ok, store photo
                try:
                    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
                    del filename_to_etud[normname]
                except:
                    raise ScoValueError("ID étudiant invalide: %s" % etudid)

                callback(
                    etud,
                    data,
                    normfilename(name, lowercase=False),
                )

                stored_etud_filename.append((etud, name))
            else:
                log("zip: zip name %s not in excel !" % name)
                ignored_zipfiles.append(name)
        else:
            if name[-1] != "/":
                ignored_zipfiles.append(name)
            log("zip: ignoring %s" % name)
    if filename_to_etud:
        # lignes excel non traitées
        unmatched_files = list(filename_to_etud.keys())
    else:
        unmatched_files = []
    return ignored_zipfiles, unmatched_files, stored_etud_filename
