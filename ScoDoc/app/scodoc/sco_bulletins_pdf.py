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

"""Génération des bulletins de notes en format PDF

On peut installer plusieurs classes générant des bulletins de formats différents.
La préférence (par semestre) 'bul_pdf_class_name' conserve le nom de la classe Python
utilisée pour générer les bulletins en PDF. Elle doit être une sous-classe de PDFBulletinGenerator
et définir les méthodes fabriquant les éléments PDF:
 gen_part_title
 gen_table
 gen_part_below
 gen_signatures

Les éléments PDF sont des objets PLATYPUS de la bibliothèque Reportlab.
Voir la documentation (Reportlab's User Guide), chapitre 5 et suivants.

Pour définir un nouveau type de bulletin:
 - créer un fichier source sco_bulletins_pdf_xxxx.py où xxxx est le nom (court) de votre type;
 - dans ce fichier, sous-classer PDFBulletinGenerator ou PDFBulletinGeneratorDefault
    (s'inspirer de sco_bulletins_pdf_default);
 - en fin du fichier sco_bulletins_pdf.py, ajouter la ligne
    import sco_bulletins_pdf_xxxx
 - votre type sera alors (après redémarrage de ScoDoc) proposé dans le formulaire de paramètrage ScoDoc.

Chaque semestre peut si nécessaire utiliser un type de bulletin différent.

"""
import io
import os
import re
import time
import traceback

from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate

from flask import g, url_for, request

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import sco_cache
from app.scodoc import sco_formsemestre
from app.scodoc import sco_pdf
from app.scodoc import sco_preferences
from app.scodoc import sco_etud
import sco_version


def pdfassemblebulletins(
    formsemestre_id,
    objects,
    bul_title,
    infos,
    pagesbookmarks,
    filigranne=None,
    server_name="",
):
    "generate PDF document from a list of PLATYPUS objects"
    if not objects:
        return ""
    # Paramètres de mise en page
    margins = (
        sco_preferences.get_preference("left_margin", formsemestre_id),
        sco_preferences.get_preference("top_margin", formsemestre_id),
        sco_preferences.get_preference("right_margin", formsemestre_id),
        sco_preferences.get_preference("bottom_margin", formsemestre_id),
    )

    report = io.BytesIO()  # in-memory document, no disk file
    document = BaseDocTemplate(report)
    document.addPageTemplates(
        sco_pdf.ScolarsPageTemplate(
            document,
            author="%s %s (E. Viennet)" % (sco_version.SCONAME, sco_version.SCOVERSION),
            title="Bulletin %s" % bul_title,
            subject="Bulletin de note",
            server_name=server_name,
            margins=margins,
            pagesbookmarks=pagesbookmarks,
            filigranne=filigranne,
            preferences=sco_preferences.SemPreferences(formsemestre_id),
        )
    )
    document.build(objects)
    data = report.getvalue()
    return data


def process_field(field, cdict, style, suppress_empty_pars=False, format="pdf"):
    """Process a field given in preferences, returns
    - if format = 'pdf': a list of Platypus objects
    - if format = 'html' : a string

    Substitutes all %()s markup
    Remove potentialy harmful <img> tags
    Replaces <logo name="header" width="xxx" height="xxx">
    by <img src=".../logos/logo_header" width="xxx" height="xxx">

    If format = 'html', replaces <para> by <p>. HTML does not allow logos.
    """
    try:
        text = (field or "") % scu.WrapDict(
            cdict
        )  # note that None values are mapped to empty strings
    except:
        log("process_field: invalid format=%s" % field)
        text = (
            "<para><i>format invalide !<i></para><para>"
            + traceback.format_exc()
            + "</para>"
        )
    # remove unhandled or dangerous tags:
    text = re.sub(r"<\s*img", "", text)
    if format == "html":
        # convert <para>
        text = re.sub(r"<\s*para(\s*)(.*?)>", r"<p>", text)
        return text
    # --- PDF format:
    # handle logos:
    image_dir = scu.SCODOC_LOGOS_DIR + "/logos_" + g.scodoc_dept + "/"
    if not os.path.exists(image_dir):
        image_dir = scu.SCODOC_LOGOS_DIR + "/"  # use global logos
        if not os.path.exists(image_dir):
            log(f"Warning: missing global logo directory ({image_dir})")
            image_dir = None

    text = re.sub(
        r"<(\s*)logo(.*?)src\s*=\s*(.*?)>", r"<\1logo\2\3>", text
    )  # remove forbidden src attribute
    if image_dir is not None:
        text = re.sub(
            r'<\s*logo(.*?)name\s*=\s*"(\w*?)"(.*?)/?>',
            r'<img\1src="%s/logo_\2.jpg"\3/>' % image_dir,
            text,
        )
        # nota: le match sur \w*? donne le nom du logo et interdit les .. et autres
        # tentatives d'acceder à d'autres fichiers !

    # log('field: %s' % (text))
    return sco_pdf.makeParas(text, style, suppress_empty=suppress_empty_pars)


def get_formsemestre_bulletins_pdf(formsemestre_id, version="selectedevals"):
    "document pdf et filename"
    from app.scodoc import sco_bulletins

    cached = sco_cache.SemBulletinsPDFCache.get(str(formsemestre_id) + "_" + version)
    if cached:
        return cached[1], cached[0]
    fragments = []
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # Make each bulletin
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etudids, get_sexnom
    bookmarks = {}
    filigrannes = {}
    i = 1
    for etudid in nt.get_etudids():
        frag, filigranne = sco_bulletins.do_formsemestre_bulletinetud(
            formsemestre_id,
            etudid,
            format="pdfpart",
            version=version,
        )
        fragments += frag
        filigrannes[i] = filigranne
        bookmarks[i] = scu.suppress_accents(nt.get_sexnom(etudid))
        i = i + 1
    #
    infos = {"DeptName": sco_preferences.get_preference("DeptName", formsemestre_id)}
    if request:
        server_name = request.url_root
    else:
        server_name = ""
    try:
        sco_pdf.PDFLOCK.acquire()
        pdfdoc = pdfassemblebulletins(
            formsemestre_id,
            fragments,
            sem["titremois"],
            infos,
            bookmarks,
            filigranne=filigrannes,
            server_name=server_name,
        )
    finally:
        sco_pdf.PDFLOCK.release()
    #
    dt = time.strftime("%Y-%m-%d")
    filename = "bul-%s-%s.pdf" % (sem["titre_num"], dt)
    filename = scu.unescape_html(filename).replace(" ", "_").replace("&", "")
    # fill cache
    sco_cache.SemBulletinsPDFCache.set(
        str(formsemestre_id) + "_" + version, (filename, pdfdoc)
    )
    return pdfdoc, filename


def get_etud_bulletins_pdf(etudid, version="selectedevals"):
    "Bulletins pdf de tous les semestres de l'étudiant, et filename"
    from app.scodoc import sco_bulletins

    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    fragments = []
    bookmarks = {}
    filigrannes = {}
    i = 1
    for sem in etud["sems"]:
        frag, filigranne = sco_bulletins.do_formsemestre_bulletinetud(
            sem["formsemestre_id"],
            etudid,
            format="pdfpart",
            version=version,
        )
        fragments += frag
        filigrannes[i] = filigranne
        bookmarks[i] = sem["session_id"]  # eg RT-DUT-FI-S1-2015
        i = i + 1
    infos = {"DeptName": sco_preferences.get_preference("DeptName")}
    if request:
        server_name = request.url_root
    else:
        server_name = ""
    try:
        sco_pdf.PDFLOCK.acquire()
        pdfdoc = pdfassemblebulletins(
            None,
            fragments,
            etud["nomprenom"],
            infos,
            bookmarks,
            filigranne=filigrannes,
            server_name=server_name,
        )
    finally:
        sco_pdf.PDFLOCK.release()
    #
    filename = "bul-%s" % (etud["nomprenom"])
    filename = (
        scu.unescape_html(filename).replace(" ", "_").replace("&", "").replace(".", "")
        + ".pdf"
    )

    return pdfdoc, filename
