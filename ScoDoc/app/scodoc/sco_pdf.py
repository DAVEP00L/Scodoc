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

"""Generation de PDF: définitions diverses et gestion du verrou

    reportlab n'est pas réentrante: il ne faut qu'une seule opération PDF au même moment.
    Tout accès à ReportLab doit donc être précédé d'un PDFLOCK.acquire()
    et terminé par un PDFLOCK.release()

    En ScoDoc 9, ce n'est pas nécessaire car on est multiptocessus / monothread.
"""
import html
import io
import os
import queue
import re
import threading
import time
import traceback
import unicodedata

import reportlab
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageBreak
from reportlab.platypus import Table, TableStyle, Image, KeepInFrame
from reportlab.platypus.flowables import Flowable
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.rl_config import defaultPageSize  # pylint: disable=no-name-in-module
from reportlab.lib.units import inch, cm, mm
from reportlab.lib.colors import pink, black, red, blue, green, magenta, red
from reportlab.lib.colors import Color
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import styles
from reportlab.lib.pagesizes import letter, A4, landscape

from flask import g

import app.scodoc.sco_utils as scu
from app.scodoc.sco_utils import (
    CONFIG,
    SCODOC_LOGOS_DIR,
    LOGOS_IMAGES_ALLOWED_TYPES,
)
from app import log
from app.scodoc.sco_exceptions import ScoGenError, ScoValueError
import sco_version

PAGE_HEIGHT = defaultPageSize[1]
PAGE_WIDTH = defaultPageSize[0]


DEFAULT_PDF_FOOTER_TEMPLATE = CONFIG.DEFAULT_PDF_FOOTER_TEMPLATE


def SU(s):
    "convert s from string to string suitable for ReportLab"
    if not s:
        return ""
    else:
        # Remplace caractères composés
        #  eg 'e\xcc\x81' COMBINING ACUTE ACCENT  par '\xc3\xa9' LATIN SMALL LETTER E WITH ACUTE
        # car les "combining accents" ne sont pas traités par ReportLab mais peuvent
        # nous être envoyés par certains navigateurs ou imports
        # (on en a dans les bases de données)
        s = unicodedata.normalize("NFC", s)
        # Remplace les entité XML/HTML
        # reportlab ne les supporte pas non plus.
        s = html.unescape(s)
        return s


def _splitPara(txt):
    "split a string, returns a list of <para > ... </para>"
    L = []
    closetag = "</para>"
    l = len(closetag)
    start = 0
    e = -1
    while 1:
        b = txt.find("<para", start)
        if b < 0:
            if e < 0:
                L.append(txt)  # no para, just return text
            break
        e = txt.find(closetag, b)
        if e < 0:
            raise ValueError("unbalanced para tags")
        L.append(txt[b : e + l])
        start = e
    # fix para: must be followed by a newline (? Reportlab bug turnaround ?)
    L = [re.sub("<para(.*?)>([^\n\r])", "<para\\1>\n\\2", p) for p in L]

    return L


def makeParas(txt, style, suppress_empty=False):
    """Returns a list of Paragraph instances from a text
    with one or more <para> ... </para>
    """
    result = []
    try:
        paras = _splitPara(txt)
        if suppress_empty:
            r = []
            for para in paras:
                m = re.match(r"\s*<\s*para.*>\s*(.*)\s*<\s*/\s*para\s*>\s*", para)
                if not m:
                    r.append(para)  # not a paragraph, keep it
                else:
                    if m.group(1):  # non empty paragraph
                        r.append(para)
            paras = r
        result = [Paragraph(SU(s), style) for s in paras]
    except OSError as e:
        msg = str(e)
        # If a file is missing, try to display the invalid name
        m = re.match(r".*\sfilename=\'(.*?)\'.*", msg, re.DOTALL)
        if m:
            filename = os.path.split(m.group(1))[1]
            if filename.startswith("logo_"):
                filename = filename[len("logo_") :]
            raise ScoValueError(
                f"Erreur dans le format PDF paramétré: fichier logo <b>{filename}</b> non trouvé"
            ) from e
        else:
            raise e
    except Exception as e:
        log(traceback.format_exc())
        log("Invalid pdf para format: %s" % txt)
        result = [
            Paragraph(
                SU('<font color="red"><i>Erreur: format invalide</i></font>'),
                style,
            )
        ]
    return result


def bold_paras(L, tag="b", close=None):
    """Put each (string) element of L between  <b>
    L is a dict or sequence. (if dict, elements with key begining by _ are unaffected)
    """
    b = "<" + tag + ">"
    if not close:
        close = "</" + tag + ">"
    if hasattr(L, "keys"):
        # L is a dict
        for k in L:
            x = L[k]
            if k[0] != "_":
                L[k] = b + L[k] or "" + close
        return L
    else:
        # L is a sequence
        return [b + (x or "") + close for x in L]


class ScolarsPageTemplate(PageTemplate):
    """Our own page template."""

    def __init__(
        self,
        document,
        pagesbookmarks={},
        author=None,
        title=None,
        subject=None,
        margins=(0, 0, 0, 0),  # additional margins in mm (left,top,right, bottom)
        server_name="",
        footer_template=DEFAULT_PDF_FOOTER_TEMPLATE,
        filigranne=None,
        preferences=None,  # dictionnary with preferences, required
    ):
        """Initialise our page template."""
        self.preferences = preferences
        self.pagesbookmarks = pagesbookmarks
        self.pdfmeta_author = author
        self.pdfmeta_title = title
        self.pdfmeta_subject = subject
        self.server_name = server_name
        self.filigranne = filigranne
        self.footer_template = footer_template
        if self.preferences:
            self.with_page_background = self.preferences["bul_pdf_with_background"]
        else:
            self.with_page_background = False
        self.background_image_filename = None
        # Our doc is made of a single frame
        left, top, right, bottom = [float(x) for x in margins]
        content = Frame(
            10.0 * mm + left * mm,
            13.0 * mm + bottom * mm,
            document.pagesize[0] - 20.0 * mm - left * mm - right * mm,
            document.pagesize[1] - 18.0 * mm - top * mm - bottom * mm,
        )
        PageTemplate.__init__(self, "ScolarsPageTemplate", [content])
        self.logo = None
        # XXX COPIED from sco_pvpdf, to be refactored (no time now)
        # Search background in dept specific dir, then in global config dir
        for image_dir in (
            SCODOC_LOGOS_DIR + "/logos_" + g.scodoc_dept + "/",
            SCODOC_LOGOS_DIR + "/",  # global logos
        ):
            for suffix in LOGOS_IMAGES_ALLOWED_TYPES:
                fn = image_dir + "/bul_pdf_background" + "." + suffix
                if not self.background_image_filename and os.path.exists(fn):
                    self.background_image_filename = fn
                # Also try to use PV background
                fn = image_dir + "/letter_background" + "." + suffix
                if not self.background_image_filename and os.path.exists(fn):
                    self.background_image_filename = fn

    def beforeDrawPage(self, canvas, doc):
        """Draws (optional) background, logo and contribution message on each page.

        day   : Day of the month as a decimal number [01,31]
        month : Month as a decimal number [01,12].
        year  : Year without century as a decimal number [00,99].
        Year  : Year with century as a decimal number.
        hour  : Hour (24-hour clock) as a decimal number [00,23].
        minute: Minute as a decimal number [00,59].

        server_url: URL du serveur ScoDoc

        """
        if not self.preferences:
            return
        canvas.saveState()
        # ---- Background image
        if self.background_image_filename and self.with_page_background:
            canvas.drawImage(
                self.background_image_filename, 0, 0, doc.pagesize[0], doc.pagesize[1]
            )

        # ---- Logo: a small image, positionned at top left of the page
        if self.logo is not None:
            # draws the logo if it exists
            (  # pylint: disable=unpacking-non-sequence
                (width, height),
                image,
            ) = self.logo
            canvas.drawImage(image, inch, doc.pagesize[1] - inch, width, height)

        # ---- Filigranne (texte en diagonal en haut a gauche de chaque page)
        if self.filigranne:
            if isinstance(self.filigranne, str):
                filigranne = self.filigranne  # same for all pages
            else:
                filigranne = self.filigranne.get(doc.page, None)
            if filigranne:
                canvas.saveState()
                canvas.translate(9 * cm, 27.6 * cm)
                canvas.rotate(30)
                canvas.scale(4.5, 4.5)
                canvas.setFillColorRGB(1.0, 0.65, 0.65)
                canvas.drawRightString(0, 0, SU(filigranne))
                canvas.restoreState()

        # ---- Add some meta data and bookmarks
        if self.pdfmeta_author:
            canvas.setAuthor(SU(self.pdfmeta_author))
        if self.pdfmeta_title:
            canvas.setTitle(SU(self.pdfmeta_title))
        if self.pdfmeta_subject:
            canvas.setSubject(SU(self.pdfmeta_subject))
        bm = self.pagesbookmarks.get(doc.page, None)
        if bm != None:
            key = bm
            txt = SU(bm)
            canvas.bookmarkPage(key)
            canvas.addOutlineEntry(txt, bm)
        # ---- Footer
        canvas.setFont(
            self.preferences["SCOLAR_FONT"], self.preferences["SCOLAR_FONT_SIZE_FOOT"]
        )
        d = _makeTimeDict()
        d["scodoc_name"] = sco_version.SCONAME
        d["server_url"] = self.server_name
        footer_str = SU(self.footer_template % d)
        canvas.drawString(
            self.preferences["pdf_footer_x"] * mm,
            self.preferences["pdf_footer_y"] * mm,
            footer_str,
        )
        canvas.restoreState()


def _makeTimeDict():
    # ... suboptimal but we don't care
    return {
        "day": time.strftime("%d"),
        "month": time.strftime("%m"),
        "year": time.strftime("%y"),
        "Year": time.strftime("%Y"),
        "hour": time.strftime("%H"),
        "minute": time.strftime("%M"),
    }


def pdf_basic_page(
    objects,
    title="",
    preferences=None,
):  # used by gen_table.make_page()
    """Simple convenience fonction: build a page from a list of platypus objects,
    adding a title if specified.
    """
    StyleSheet = styles.getSampleStyleSheet()
    report = io.BytesIO()  # in-memory document, no disk file
    document = BaseDocTemplate(report)
    document.addPageTemplates(
        ScolarsPageTemplate(
            document,
            title=title,
            author="%s %s (E. Viennet)" % (sco_version.SCONAME, sco_version.SCOVERSION),
            footer_template="Edité par %(scodoc_name)s le %(day)s/%(month)s/%(year)s à %(hour)sh%(minute)s",
            preferences=preferences,
        )
    )
    if title:
        head = Paragraph(SU(title), StyleSheet["Heading3"])
        objects = [head] + objects
    document.build(objects)
    data = report.getvalue()
    return data


# Gestion du lock pdf


class PDFLock(object):
    def __init__(self, timeout=15):
        self.Q = queue.Queue(1)
        self.timeout = timeout
        self.current_thread = None
        self.nref = 0

    def release(self):
        "Release lock. Raise Empty if not acquired first"
        if self.current_thread == threading.get_ident():
            self.nref -= 1
            if self.nref == 0:
                log("PDFLock: release from %s" % self.current_thread)
                self.current_thread = None
                self.Q.get(False)
            return
        else:
            self.Q.get(False)

    def acquire(self):
        "Acquire lock. Raise ScoGenError if can't lock after timeout."
        if self.current_thread == threading.get_ident():
            self.nref += 1
            return  # deja lock pour ce thread
        try:
            self.Q.put(1, True, self.timeout)
        except queue.Full:
            raise ScoGenError(msg="Traitement PDF occupé: ré-essayez")
        self.current_thread = threading.get_ident()
        self.nref = 1
        log("PDFLock: granted to %s" % self.current_thread)


class WatchLock:
    "Surveille threads (mais ne verrouille pas)"

    def __init__(self, timeout=None):
        self.timeout = timeout
        t = threading.current_thread()
        self.native_id = t.native_id
        self.ident = t.ident

    def acquire(self):
        t = threading.current_thread()
        if (self.native_id != t.native_id) or (self.ident != t.ident):
            log(
                f"Warning: LOCK detected several threads ! (native_id {self.native_id} -> {t.native_id}, ident {self.ident} -> {t.ident}"
            )
        self.native_id = t.native_id
        self.ident = t.ident

    def release(self):
        t = threading.current_thread()
        assert (self.native_id == t.native_id) and (self.ident == t.ident)
        pass


class FakeLock:
    "Pour ScoDoc 9: pas de verrou"

    def __init__(self, timeout=None):
        pass

    def acquire(self):
        pass

    def release(self):
        pass


PDFLOCK = FakeLock()
