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


""" Exports XML
"""

from xml.etree import ElementTree
import xml.sax.saxutils
from xml.dom import minidom

from app.scodoc import sco_utils as scu
from app.scodoc.sco_vdi import ApoEtapeVDI

XML_HEADER = """<?xml version="1.0" encoding="utf-8"?>"""


def quote_xml_attr(data):
    """Escape &, <, >, quotes and double quotes"""
    return xml.sax.saxutils.escape(str(data), {"'": "&apos;", '"': "&quot;"})


# ScoDoc7 legacy function:
def simple_dictlist2xml(dictlist, tagname=None, quote=False, pretty=True):
    """Represent a dict as XML data.
    All keys with string or numeric values are attributes (numbers converted to strings).
    All list values converted to list of childs (recursively).
    *** all other values are ignored ! ***
    Values (xml entities) are not quoted, except if requested by quote argument.

    Exemple:
     simple_dictlist2xml([ { 'id' : 1, 'ues' : [{'note':10},{}] } ], tagname='infos')

    <?xml version="1.0" encoding="utf-8"?>
    <infos id="1">
      <ues note="10" />
      <ues />
    </infos>

    """
    if not tagname:
        raise ValueError("invalid empty tagname !")
    elements = _dictlist2xml(dictlist, root=[], tagname=tagname, quote=quote)
    ans = XML_HEADER + b"\n".join([ElementTree.tostring(x) for x in elements]).decode(
        scu.SCO_ENCODING
    )
    if pretty:
        # solution peu satisfaisante car on doit reparser le XML
        # de plus, on encode/decode pour avoir le tag <?xml version="1.0" encoding="utf-8"?>
        try:
            ans = (
                minidom.parseString(ans)
                .toprettyxml(indent="\t", encoding="utf-8")
                .decode("utf-8")
            )
        except xml.parsers.expat.ExpatError:
            pass
    return ans


def _repr_as_xml(v):
    if isinstance(v, bool):
        return str(int(v))  # booleans as "0" / "1"
    return str(v)


def _dictlist2xml(dictlist, root=None, tagname=None, quote=False):
    scalar_types = (bytes, str, int, float, bool)
    for d in dictlist:
        elem = ElementTree.Element(tagname)
        root.append(elem)
        if isinstance(d, scalar_types) or isinstance(d, ApoEtapeVDI):
            elem.set("code", _repr_as_xml(d))
        else:
            if quote:
                d_scalar = dict(
                    [
                        (k, quote_xml_attr(_repr_as_xml(v)))
                        for (k, v) in d.items()
                        if isinstance(v, scalar_types)
                    ]
                )
            else:
                d_scalar = dict(
                    [
                        (k, _repr_as_xml(v))
                        for (k, v) in d.items()
                        if isinstance(v, scalar_types)
                    ]
                )
            for k in d_scalar:
                elem.set(k, d_scalar[k])
            d_list = dict([(k, v) for (k, v) in d.items() if isinstance(v, list)])
            if d_list:
                for (k, v) in d_list.items():
                    _dictlist2xml(v, tagname=k, root=elem, quote=quote)
    return root


ELEMENT_NODE = 1
TEXT_NODE = 3


def xml_to_dicts(element):
    """Represent dom element as a dict
    Example:
       <foo x="1" y="2"><bar z="2"/></foo>
    will give us:
       ('foo', {'y': '2', 'x': '1'}, [('bar', {'z': '2'}, [])])
    """
    d = {}
    # attributes
    if element.attributes:
        for i in range(len(element.attributes)):
            a = element.attributes.item(i).nodeName
            v = element.getAttribute(element.attributes.item(i).nodeName)
            d[a] = v
    # descendants
    childs = []
    for child in element.childNodes:
        if child.nodeType == ELEMENT_NODE:
            childs.append(xml_to_dicts(child))
    return (element.nodeName, d, childs)
