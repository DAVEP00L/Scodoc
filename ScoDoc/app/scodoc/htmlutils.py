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

"""Various HTML generation functions
"""
from html.parser import HTMLParser
from html.entities import name2codepoint
import re

from flask import g, url_for

from . import listhistogram


def horizontal_bargraph(value, mark):
    """html drawing an horizontal bar and a mark
    used to vizualize the relative level of a student
    """
    tmpl = """
    <span class="graph">
    <span class="bar" style="width: %(value)d%%;"></span>
    <span class="mark" style="left: %(mark)d%%; "></span>
    </span>
    """
    return tmpl % {"value": int(value), "mark": int(mark)}


def histogram_notes(notes):
    "HTML code drawing histogram"
    if not notes:
        return ""
    _, H = listhistogram.ListHistogram(notes, 21, minmax=(0, 20))
    D = ['<ul id="vhist-q-graph"><li class="vhist-qtr" id="vhist-q1"><ul>']
    left = 5
    colwidth = 16  # must match #q-graph li.bar width in stylesheet
    if max(H) <= 0:
        return ""
    hfactor = 95.0 / max(H)  # garde une marge de 5% pour l'esthetique
    for i in range(len(H)):
        if H[i] >= 0:
            x = left + i * (4 + colwidth)
            heightpercent = H[i] * hfactor
            if H[i] > 0:
                nn = "<p>%d</p>" % H[i]
            else:
                nn = ""
            D.append(
                '<li class="vhist-bar" style="left:%dpx;height:%f%%">%s<p class="leg">%d</p></li>'
                % (x, heightpercent, nn, i)
            )
    D.append("</ul></li></ul>")
    return "\n".join(D)


def make_menu(title, items, css_class="", alone=False):
    """HTML snippet to render a simple drop down menu.
    items is a list of dicts:
    { 'title' :
      'endpoint' : flask endpoint (name of the function)
      'args' : url query args
      'id'  :
      'attr' : "" # optional html <a> attributes
      'enabled' : # True by default
      'helpmsg' :
      'submenu' : [ list of sub-items ]
    }
    """

    def gen_menu_items(items):
        H.append("<ul>")
        for item in items:
            if not item.get("enabled", True):
                cls = ' class="ui-state-disabled"'
            else:
                cls = ""
            the_id = item.get("id", "")
            if the_id:
                li_id = 'id="%s" ' % the_id
            else:
                li_id = ""
            if "endpoint" in item:
                args = item.get("args", {})
                item["urlq"] = url_for(
                    item["endpoint"], scodoc_dept=g.scodoc_dept, **args
                )
            elif "url" in item:
                item["urlq"] = item["url"]
            else:
                item["urlq"] = "#"
            item["attr"] = item.get("attr", "")
            submenu = item.get("submenu", None)
            H.append(
                "<li "
                + li_id
                + cls
                + '><a href="%(urlq)s" %(attr)s>%(title)s</a>' % item
            )
            if submenu:
                gen_menu_items(submenu)
            H.append("</li>")
        H.append("</ul>")

    H = []
    if alone:
        H.append('<ul class="sco_dropdown_menu %s">' % css_class)
    H.append("""<li><a href="#">%s</a>""" % title)
    gen_menu_items(items)
    H.append("</li>")
    if alone:
        H.append("</ul>")
    return "".join(H)


"""
HTML <-> text conversions.
http://stackoverflow.com/questions/328356/extracting-text-from-html-file-using-python
"""


class _HTMLToText(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self._buf = []
        self.hide_output = False

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br") and not self.hide_output:
            self._buf.append("\n")
        elif tag in ("script", "style"):
            self.hide_output = True

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag == "p":
            self._buf.append("\n")
        elif tag in ("script", "style"):
            self.hide_output = False

    def handle_data(self, text):
        if text and not self.hide_output:
            self._buf.append(re.sub(r"\s+", " ", text))

    def handle_entityref(self, name):
        if name in name2codepoint and not self.hide_output:
            c = chr(name2codepoint[name])
            self._buf.append(c)

    def handle_charref(self, name):
        if not self.hide_output:
            n = int(name[1:], 16) if name.startswith("x") else int(name)
            self._buf.append(chr(n))

    def get_text(self):
        return re.sub(r" +", " ", "".join(self._buf))


def html_to_text(html):
    """
    Given a piece of HTML, return the plain text it contains.
    This handles entities and char refs, but not javascript and stylesheets.
    """
    parser = _HTMLToText()
    try:
        parser.feed(html)
        parser.close()
    except:  # HTMLParseError: No good replacement?
        pass
    return parser.get_text()
