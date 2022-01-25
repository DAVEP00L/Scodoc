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

from html.parser import HTMLParser


"""HTML sanitizing function
   used to clean user submitted HTML
   (Python 3 only)
"""

# permet de conserver les liens
def html_to_safe_html(text, convert_br=True):  # was HTML2SafeHTML
    # text = html_to_safe_html(text, valid_tags=("b", "a", "i", "br", "p"))
    # New version (jul 2021) with our own parser
    text = convert_html_to_text(text)
    if convert_br:
        return newline_to_br(text)
    else:
        return text


def convert_html_to_text(s):
    parser = HTMLSanitizer()
    parser.feed(s)
    return parser.text


def newline_to_br(text):
    return text.replace("\n", "<br/>")


class HTMLSanitizer(HTMLParser):
    def __init__(self, allowed_tags=("i", "b", "em", "br", "p"), **kwargs):
        super(HTMLSanitizer, self).__init__(**kwargs)
        self.allowed_tags = set(allowed_tags)
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag in self.allowed_tags:
            self.text += "<{} {}>".format(
                tag, ", ".join(['{}="{}"'.format(k, v) for (k, v) in attrs])
            )

    def handle_endtag(self, tag):
        if tag in self.allowed_tags:
            self.text += "</" + tag + ">"

    def handle_data(self, data):
        self.text += data


if __name__ == "__main__":
    test_parser = HTMLSanitizer()
    test_parser.feed("""<p>Hello world <b z="1" >gras</b> <i a="2">italique</i></p>""")
    print(test_parser.text)
