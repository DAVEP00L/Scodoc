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

"""Géneration de tables aux formats XHTML, PDF, Excel, XML et JSON.

Les données sont fournies comme une liste de dictionnaires, chaque élément de
cette liste décrivant une ligne du tableau.

Chaque colonne est identifiée par une clé du dictionnaire.

Voir exemple en fin de ce fichier.

Les clés commençant par '_' sont réservées. Certaines altèrent le traitement, notamment
pour spécifier les styles de mise en forme.
Par exemple, la clé '_css_row_class' spécifie le style CSS de la ligne.

"""

from __future__ import print_function
import random
from collections import OrderedDict
from xml.etree import ElementTree
import json

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageBreak
from reportlab.platypus import Table, TableStyle, Image, KeepInFrame
from reportlab.lib.colors import Color
from reportlab.lib import styles
from reportlab.lib.units import inch, cm, mm
from reportlab.rl_config import defaultPageSize  # pylint: disable=no-name-in-module

from app.scodoc import html_sco_header
from app.scodoc import sco_utils as scu
from app.scodoc import sco_excel
from app.scodoc import sco_pdf
from app.scodoc import sco_xml
from app.scodoc.sco_pdf import SU
from app import log


def mark_paras(L, tags):
    """Put each (string) element of L between  <b>"""
    for tag in tags:
        b = "<" + tag + ">"
        c = "</" + tag.split()[0] + ">"
        L = [b + (x or "") + c for x in L]
    return L


class DEFAULT_TABLE_PREFERENCES(object):
    """Default preferences for tables created without preferences argument"""

    values = {
        "SCOLAR_FONT": "Helvetica",  # used for PDF, overriden by preferences argument
        "SCOLAR_FONT_SIZE": 10,
        "SCOLAR_FONT_SIZE_FOOT": 6,
        "bul_pdf_with_background": False,
    }

    def __getitem__(self, k):
        return self.values[k]


class GenTable(object):
    """Simple 2D tables with export to HTML, PDF, Excel, CSV.
    Can be sub-classed to generate fancy formats.
    """

    default_css_class = "gt_table stripe cell-border compact hover order-column"

    def __init__(
        self,
        rows=[{}],  # liste de dict { column_id : value }
        columns_ids=[],  # id des colonnes a afficher, dans l'ordre
        titles={},  # titres (1ere ligne)
        bottom_titles={},  # titres derniere ligne (optionnel)
        caption=None,
        page_title="",  # titre fenetre html
        pdf_link=True,
        xls_link=True,
        xml_link=False,
        table_id=None,  # for html and xml
        html_class=None,  # class de l'element <table> (en plus des classes par defaut,
        html_class_ignore_default=False,  # sauf si html_class_ignore_default est vrai)
        html_sortable=False,
        html_highlight_n=2,  # une ligne sur 2 de classe "gt_hl"
        html_col_width=None,  # force largeur colonne
        html_generate_cells=True,  # generate empty <td> cells even if not in rows (useless?)
        html_title="",  # avant le tableau en html
        html_caption=None,  # override caption if specified
        html_header=None,
        html_next_section="",  # html fragment to put after the table
        html_with_td_classes=False,  # put class=column_id in each <td>
        html_before_table="",  # html snippet to put before the <table> in the page
        html_empty_element="",  # replace table when empty
        base_url=None,
        origin=None,  # string added to excel and xml versions
        filename="table",  # filename, without extension
        xls_sheet_name="feuille",
        xls_before_table=[],  # liste de cellules a placer avant la table
        pdf_title="",  # au dessus du tableau en pdf
        pdf_table_style=None,
        pdf_col_widths=None,
        xml_outer_tag="table",
        xml_row_tag="row",
        text_with_titles=False,  # CSV with header line
        text_fields_separator="\t",
        preferences=None,
    ):
        self.rows = rows  # [ { col_id : value } ]
        self.columns_ids = columns_ids  # ordered list of col_id
        self.titles = titles  # { col_id : title }
        self.bottom_titles = bottom_titles
        self.origin = origin
        self.base_url = base_url
        self.filename = filename
        self.caption = caption
        self.html_header = html_header
        self.html_before_table = html_before_table
        self.html_empty_element = html_empty_element
        self.page_title = page_title
        self.pdf_link = pdf_link
        self.xls_link = xls_link
        self.xml_link = xml_link
        # HTML parameters:
        if not table_id:  # random id
            self.table_id = "gt_" + str(random.randint(0, 1000000))
        else:
            self.table_id = table_id
        self.html_generate_cells = html_generate_cells
        self.html_title = html_title
        self.html_caption = html_caption
        self.html_next_section = html_next_section
        self.html_with_td_classes = html_with_td_classes
        if html_class is None:
            html_class = self.default_css_class
        if html_class_ignore_default:
            self.html_class = html_class
        else:
            self.html_class = self.default_css_class + " " + html_class

        self.sortable = html_sortable
        self.html_highlight_n = html_highlight_n
        self.html_col_width = html_col_width
        # XLS parameters
        self.xls_sheet_name = xls_sheet_name
        self.xls_before_table = xls_before_table
        # PDF parameters
        self.pdf_table_style = pdf_table_style
        self.pdf_col_widths = pdf_col_widths
        self.pdf_title = pdf_title
        # XML parameters
        self.xml_outer_tag = xml_outer_tag
        self.xml_row_tag = xml_row_tag
        # TEXT parameters
        self.text_fields_separator = text_fields_separator
        self.text_with_titles = text_with_titles
        #
        if preferences:
            self.preferences = preferences
        else:
            self.preferences = DEFAULT_TABLE_PREFERENCES()

    def __repr__(self):
        return f"<gen_table( nrows={self.get_nb_rows()}, ncols={self.get_nb_cols()} )>"

    def get_nb_cols(self):
        return len(self.columns_ids)

    def get_nb_rows(self):
        return len(self.rows)

    def is_empty(self):
        return len(self.rows) == 0

    def get_data_list(
        self,
        with_titles=False,
        with_lines_titles=True,
        with_bottom_titles=True,
        omit_hidden_lines=False,
        pdf_mode=False,  # apply special pdf reportlab processing
        pdf_style_list=[],  # modified: list of platypus table style commands
    ):
        "table data as a list of lists (rows)"
        T = []
        line_num = 0  # line number in input data
        out_line_num = 0  # line number in output list
        if with_titles and self.titles:
            l = []
            if with_lines_titles:
                if "row_title" in self.titles:
                    l = [self.titles["row_title"]]

            T.append(l + [self.titles.get(cid, "") for cid in self.columns_ids])

        for row in self.rows:
            line_num += 1
            l = []
            if with_lines_titles:
                if "row_title" in row:
                    l = [row["row_title"]]

            if not (omit_hidden_lines and row.get("_hidden", False)):
                colspan_count = 0
                col_num = len(l)
                for cid in self.columns_ids:
                    colspan_count -= 1
                    # if colspan_count > 0:
                    #    continue # skip cells after a span
                    content = row.get(cid, "") or ""  # nota: None converted to ''
                    colspan = row.get("_%s_colspan" % cid, 0)
                    if colspan > 1:
                        pdf_style_list.append(
                            (
                                "SPAN",
                                (col_num, out_line_num),
                                (col_num + colspan - 1, out_line_num),
                            )
                        )
                        colspan_count = colspan
                    l.append(content)
                    col_num += 1
                if pdf_mode:
                    mk = row.get("_pdf_row_markup", [])  # a list of tags
                    if mk:
                        l = mark_paras(l, mk)
                T.append(l)
                #
                for cmd in row.get("_pdf_style", []):  # relocate line numbers
                    pdf_style_list.append(
                        (
                            cmd[0],
                            (cmd[1][0], cmd[1][1] + out_line_num),
                            (cmd[2][0], cmd[2][1] + out_line_num),
                        )
                        + cmd[3:]
                    )

                out_line_num += 1
        if with_bottom_titles and self.bottom_titles:
            line_num += 1
            l = []
            if with_lines_titles:
                if "row_title" in self.bottom_titles:
                    l = [self.bottom_titles["row_title"]]

            T.append(l + [self.bottom_titles.get(cid, "") for cid in self.columns_ids])
        return T

    def get_titles_list(self):
        "list of titles"
        return [self.titles.get(cid, "") for cid in self.columns_ids]

    def gen(self, format="html", columns_ids=None):
        """Build representation of the table in the specified format.
        See make_page() for more sophisticated output.
        """
        if format == "html":
            return self.html()
        elif format == "xls" or format == "xlsx":
            return self.excel()
        elif format == "text" or format == "csv":
            return self.text()
        elif format == "pdf":
            return self.pdf()
        elif format == "xml":
            return self.xml()
        elif format == "json":
            return self.json()
        raise ValueError("GenTable: invalid format: %s" % format)

    def _gen_html_row(self, row, line_num=0, elem="td", css_classes=""):
        "row is a dict, returns a string <tr...>...</tr>"
        if not row:
            return "<tr></tr>"  # empty row

        if self.html_col_width:
            std = ' style="width:%s;"' % self.html_col_width
        else:
            std = ""

        cla = css_classes + " " + row.get("_css_row_class", "")
        if line_num % self.html_highlight_n:
            cls = ' class="gt_hl %s"' % cla
        else:
            if cla:
                cls = ' class="%s"' % cla
            else:
                cls = ""
        H = ["<tr%s %s>" % (cls, row.get("_tr_attrs", ""))]
        # titre ligne
        if "row_title" in row:
            content = str(row["row_title"])
            help = row.get("row_title_help", "")
            if help:
                content = '<a class="discretelink" href="" title="%s">%s</a>' % (
                    help,
                    content,
                )
            H.append('<th class="gt_linetit">' + content + "</th>")
        r = []
        colspan_count = 0
        for cid in self.columns_ids:
            if not cid in row and not self.html_generate_cells:
                continue  # skip cell
            colspan_count -= 1
            if colspan_count > 0:
                continue  # skip cells after a span
            content = row.get("_" + str(cid) + "_html", row.get(cid, ""))
            if content is None:
                content = ""
            else:
                content = str(content)
            help = row.get("_%s_help" % cid, "")
            if help:
                target = row.get("_%s_target" % cid, "#")
            else:
                target = row.get("_%s_target" % cid, "")
            cell_id = row.get("_%s_id" % cid, None)
            if cell_id:
                idstr = ' id="%s"' % cell_id
            else:
                idstr = ""
            cell_link_class = row.get("_%s_link_class" % cid, "discretelink")
            if help or target:
                content = '<a class="%s" href="%s" title="%s"%s>%s</a>' % (
                    cell_link_class,
                    target,
                    help,
                    idstr,
                    content,
                )
            klass = row.get("_%s_class" % cid, "")
            if self.html_with_td_classes:
                c = cid
            else:
                c = ""
            if c or klass:
                klass = ' class="%s"' % (" ".join((klass, c)))
            else:
                klass = ""
            colspan = row.get("_%s_colspan" % cid, 0)
            if colspan > 1:
                colspan_txt = ' colspan="%d" ' % colspan
                colspan_count = colspan
            else:
                colspan_txt = ""
            r.append(
                "<%s%s %s%s%s>%s</%s>"
                % (
                    elem,
                    std,
                    row.get("_%s_td_attrs" % cid, ""),
                    klass,
                    colspan_txt,
                    content,
                    elem,
                )
            )

        H.append("".join(r) + "</tr>")
        return "".join(H)

    def html(self):
        "Simple HTML representation of the table"
        if self.is_empty() and self.html_empty_element:
            return self.html_empty_element + "\n" + self.html_next_section
        hid = ' id="%s"' % self.table_id
        tablclasses = []
        if self.html_class:
            tablclasses.append(self.html_class)
        if self.sortable:
            tablclasses.append("sortable")
        if tablclasses:
            cls = ' class="%s"' % " ".join(tablclasses)
        else:
            cls = ""

        H = [self.html_before_table, "<table%s%s>" % (hid, cls)]

        line_num = 0
        # thead
        H.append("<thead>")
        if self.titles:
            H.append(
                self._gen_html_row(
                    self.titles, line_num, elem="th", css_classes="gt_firstrow"
                )
            )
        # autres lignes à placer dans la tête:
        for row in self.rows:
            if row.get("_table_part") == "head":
                line_num += 1
                H.append(self._gen_html_row(row, line_num))  # uses td elements
        H.append("</thead>")

        H.append("<tbody>")
        for row in self.rows:
            if row.get("_table_part", "body") == "body":
                line_num += 1
                H.append(self._gen_html_row(row, line_num))
        H.append("</tbody>")

        H.append("<tfoot>")
        for row in self.rows:
            if row.get("_table_part") == "foot":
                line_num += 1
                H.append(self._gen_html_row(row, line_num))
        if self.bottom_titles:
            H.append(
                self._gen_html_row(
                    self.bottom_titles,
                    line_num + 1,
                    elem="th",
                    css_classes="gt_lastrow sortbottom",
                )
            )
        H.append("</tfoot>")

        H.append("</table>")

        caption = self.html_caption or self.caption
        if caption or self.base_url:
            H.append('<p class="gt_caption">')
            if caption:
                H.append(caption)
            if self.base_url:
                H.append('<span class="gt_export_icons">')
                if self.xls_link:
                    H.append(
                        ' <a href="%s&format=xls">%s</a>'
                        % (self.base_url, scu.ICON_XLS)
                    )
                if self.xls_link and self.pdf_link:
                    H.append("&nbsp;")
                if self.pdf_link:
                    H.append(
                        ' <a href="%s&format=pdf">%s</a>'
                        % (self.base_url, scu.ICON_PDF)
                    )
                H.append("</span>")
            H.append("</p>")

        H.append(self.html_next_section)
        return "\n".join(H)

    def excel(self, wb=None):
        """Simple Excel representation of the table"""
        if wb is None:
            ses = sco_excel.ScoExcelSheet(sheet_name=self.xls_sheet_name, wb=wb)
        else:
            ses = wb.create_sheet(sheet_name=self.xls_sheet_name)
        ses.rows += self.xls_before_table
        style_bold = sco_excel.excel_make_style(bold=True)
        style_base = sco_excel.excel_make_style()
        ses.append_row(ses.make_row(self.get_titles_list(), style_bold))
        for line in self.get_data_list():
            ses.append_row(ses.make_row(line, style_base))
        if self.caption:
            ses.append_blank_row()  # empty line
            ses.append_single_cell_row(self.caption, style_base)
        if self.origin:
            ses.append_blank_row()  # empty line
            ses.append_single_cell_row(self.origin, style_base)
        if wb is None:
            return ses.generate()

    def text(self):
        "raw text representation of the table"
        if self.text_with_titles:
            headline = [self.get_titles_list()]
        else:
            headline = []
        return "\n".join(
            [
                self.text_fields_separator.join([str(x) for x in line])
                for line in headline + self.get_data_list()
            ]
        )

    def pdf(self):
        "PDF representation: returns a ReportLab's platypus Table instance"
        r = []
        try:
            sco_pdf.PDFLOCK.acquire()
            r = self._pdf()
        finally:
            sco_pdf.PDFLOCK.release()
        return r

    def _pdf(self):
        """PDF representation: returns a list of ReportLab's platypus objects
        (notably a Table instance)
        """
        if not self.pdf_table_style:
            LINEWIDTH = 0.5
            self.pdf_table_style = [
                ("FONTNAME", (0, 0), (-1, 0), self.preferences["SCOLAR_FONT"]),
                ("LINEBELOW", (0, 0), (-1, 0), LINEWIDTH, Color(0, 0, 0)),
                ("GRID", (0, 0), (-1, -1), LINEWIDTH, Color(0, 0, 0)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        nb_cols = len(self.columns_ids)
        if self.rows and "row_title" in self.rows[0]:
            nb_cols += 1
        if not self.pdf_col_widths:
            self.pdf_col_widths = (None,) * nb_cols
        #
        CellStyle = styles.ParagraphStyle({})
        CellStyle.fontSize = self.preferences["SCOLAR_FONT_SIZE"]
        CellStyle.fontName = self.preferences["SCOLAR_FONT"]
        CellStyle.leading = 1.0 * self.preferences["SCOLAR_FONT_SIZE"]  # vertical space
        LINEWIDTH = 0.5
        #
        # titles = ["<para><b>%s</b></para>" % x for x in self.get_titles_list()]
        pdf_style_list = []
        Pt = [
            [Paragraph(SU(str(x)), CellStyle) for x in line]
            for line in (
                self.get_data_list(
                    pdf_mode=True,
                    pdf_style_list=pdf_style_list,
                    with_titles=True,
                    omit_hidden_lines=True,
                )
            )
        ]
        pdf_style_list += self.pdf_table_style
        T = Table(Pt, repeatRows=1, colWidths=self.pdf_col_widths, style=pdf_style_list)

        objects = []
        StyleSheet = styles.getSampleStyleSheet()
        if self.pdf_title:
            objects.append(Paragraph(SU(self.pdf_title), StyleSheet["Heading3"]))
        if self.caption:
            objects.append(Paragraph(SU(self.caption), StyleSheet["Normal"]))
            objects.append(Spacer(0, 0.4 * cm))
        objects.append(T)

        return objects

    def xml(self):
        """XML representation of the table.
        The schema is very simple:
        <table origin="" id="" caption="">
        <row title="">
        <column_id value=""/>
        </row>
        </table>
        The tag names <table> and <row> can be changed using
        xml_outer_tag and xml_row_tag
        """
        doc = ElementTree.Element(
            self.xml_outer_tag,
            id=str(self.table_id),
            origin=self.origin or "",
            caption=self.caption or "",
        )
        for row in self.rows:
            x_row = ElementTree.Element(self.xml_row_tag)
            row_title = row.get("row_title", "")
            if row_title:
                x_row.set("title", row_title)
            doc.append(x_row)
            for cid in self.columns_ids:
                v = row.get(cid, "")
                if v is None:
                    v = ""
                x_cell = ElementTree.Element(str(cid), value=str(v))
                x_row.append(x_cell)
        return sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING)

    def json(self):
        """JSON representation of the table."""
        d = []
        for row in self.rows:
            r = {}
            for cid in self.columns_ids:
                v = row.get(cid, None)
                # if v != None:
                #    v = str(v)
                r[cid] = v
            d.append(r)
        return json.dumps(d, cls=scu.ScoDocJSONEncoder)

    def make_page(
        self,
        title="",
        format="html",
        page_title="",
        filename=None,
        javascripts=[],
        with_html_headers=True,
        publish=True,
        init_qtip=False,
    ):
        """
        Build page at given format
        This is a simple page with only a title and the table.
        If not publish, does not set response header
        """
        if not filename:
            filename = self.filename
        page_title = page_title or self.page_title
        html_title = self.html_title or title
        if format == "html":
            H = []
            if with_html_headers:
                H.append(
                    self.html_header
                    or html_sco_header.sco_header(
                        page_title=page_title,
                        javascripts=javascripts,
                        init_qtip=init_qtip,
                    )
                )
            if html_title:
                H.append(html_title)
            H.append(self.html())
            if with_html_headers:
                H.append(html_sco_header.sco_footer())
            return "\n".join(H)
        elif format == "pdf":
            pdf_objs = self.pdf()
            pdf_doc = sco_pdf.pdf_basic_page(
                pdf_objs, title=title, preferences=self.preferences
            )
            if publish:
                return scu.send_file(
                    pdf_doc,
                    filename,
                    suffix=".pdf",
                    mime=scu.PDF_MIMETYPE,
                )
            else:
                return pdf_doc
        elif format == "xls" or format == "xlsx":  # dans les 2 cas retourne du xlsx
            xls = self.excel()
            if publish:
                return scu.send_file(
                    xls,
                    filename,
                    suffix=scu.XLSX_SUFFIX,
                    mime=scu.XLSX_MIMETYPE,
                )
            else:
                return xls
        elif format == "text":
            return self.text()
        elif format == "csv":
            return scu.send_file(
                self.text(),
                filename,
                suffix=".csv",
                mime=scu.CSV_MIMETYPE,
                attached=True,
            )
        elif format == "xml":
            xml = self.xml()
            if publish:
                return scu.send_file(
                    xml, filename, suffix=".xml", mime=scu.XML_MIMETYPE
                )
            return xml
        elif format == "json":
            js = self.json()
            if publish:
                return scu.send_file(
                    js, filename, suffix=".json", mime=scu.JSON_MIMETYPE
                )
            return js
        else:
            log("make_page: format=%s" % format)
            raise ValueError("_make_page: invalid format")


# -----
class SeqGenTable(object):
    """Sequence de GenTable: permet de générer un classeur excel avec un tab par table.
    L'ordre des tabs est conservé (1er tab == 1ere table ajoutée)
    """

    def __init__(self):
        self.genTables = OrderedDict()

    def add_genTable(self, name, gentable):
        self.genTables[name] = gentable

    def get_genTable(self, name):
        return self.genTables.get(name)

    def excel(self):
        """Export des genTables dans un unique fichier excel avec plusieurs feuilles tagguées"""
        book = sco_excel.ScoExcelBook()  # pylint: disable=no-member
        for (_, gt) in self.genTables.items():
            gt.excel(wb=book)  # Ecrit dans un fichier excel
        return book.generate()


# ----- Exemple d'utilisation minimal.
if __name__ == "__main__":
    T = GenTable(
        rows=[{"nom": "Hélène", "age": 26}, {"nom": "Titi&çà§", "age": 21}],
        columns_ids=("nom", "age"),
    )
    print("--- HTML:")
    print(T.gen(format="html"))
    print("\n--- XML:")
    print(T.gen(format="xml"))
    print("\n--- JSON:")
    print(T.gen(format="json"))
    # Test pdf:
    import io
    from reportlab.platypus import KeepInFrame
    from app.scodoc import sco_preferences, sco_pdf

    preferences = sco_preferences.SemPreferences()
    T.preferences = preferences
    objects = T.gen(format="pdf")
    objects = [KeepInFrame(0, 0, objects, mode="shrink")]
    doc = io.BytesIO()
    document = sco_pdf.BaseDocTemplate(doc)
    document.addPageTemplates(
        sco_pdf.ScolarsPageTemplate(
            document,
        )
    )
    document.build(objects)
    data = doc.getvalue()
    with open("/tmp/gen_table.pdf", "wb") as f:
        f.write(data)
    p = T.make_page(format="pdf")
    with open("toto.pdf", "wb") as f:
        f.write(p)
