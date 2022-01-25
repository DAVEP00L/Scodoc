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

"""HTML Header/Footer for ScoDoc pages
"""

import html

from flask import g
from flask import request
from flask_login import current_user

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sidebar
import sco_version


# Some constants:

# Multiselect menus are used on a few pages and not loaded by default
BOOTSTRAP_MULTISELECT_JS = [
    "libjs/bootstrap-3.1.1-dist/js/bootstrap.min.js",
    "libjs/bootstrap-multiselect/bootstrap-multiselect.js",
    "libjs/purl.js",
]

BOOTSTRAP_MULTISELECT_CSS = [
    "libjs/bootstrap-3.1.1-dist/css/bootstrap.min.css",
    "libjs/bootstrap-3.1.1-dist/css/bootstrap-theme.min.css",
    "libjs/bootstrap-multiselect/bootstrap-multiselect.css",
]


def standard_html_header():
    """Standard HTML header for pages outside depts"""
    # not used in ZScolar, see sco_header
    return """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html><head>
<title>ScoDoc: accueil</title>
<META http-equiv="Content-Type" content="text/html; charset=%s">
<META http-equiv="Content-Style-Type" content="text/css">
<META name="LANG" content="fr">
<META name="DESCRIPTION" content="ScoDoc: gestion scolarite">

<link href="/ScoDoc/static/css/scodoc.css" rel="stylesheet" type="text/css"/>

</head><body>%s""" % (
        scu.SCO_ENCODING,
        scu.CUSTOM_HTML_HEADER_CNX,
    )


def standard_html_footer():
    """Le pied de page HTML de la page d'accueil."""
    return """<p class="footer">
Problème de connexion (identifiant, mot de passe): <em>contacter votre responsable ou chef de département</em>.</p>
<p>Probl&egrave;mes et suggestions sur le logiciel: <a href="mailto:%s">%s</a></p>
<p><em>ScoDoc est un logiciel libre développé par Emmanuel Viennet.</em></p>
</body></html>""" % (
        scu.SCO_USERS_LIST,
        scu.SCO_USERS_LIST,
    )


_HTML_BEGIN = """<?xml version="1.0" encoding="%(encoding)s"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<title>%(page_title)s</title>
<meta http-equiv="Content-Type" content="text/html; charset=%(encoding)s" />
<meta http-equiv="Content-Style-Type" content="text/css" />
<meta name="LANG" content="fr" />
<meta name="DESCRIPTION" content="ScoDoc" />

<link type="text/css" rel="stylesheet" href="/ScoDoc/static/libjs/jquery-ui-1.10.4.custom/css/smoothness/jquery-ui-1.10.4.custom.min.css" />
    
<link href="/ScoDoc/static/css/scodoc.css" rel="stylesheet" type="text/css" />
<link href="/ScoDoc/static/css/menu.css" rel="stylesheet" type="text/css" />
<script src="/ScoDoc/static/libjs/menu.js"></script>
<script src="/ScoDoc/static/libjs/sorttable.js"></script>
<script src="/ScoDoc/static/libjs/bubble.js"></script>
<script>
 window.onload=function(){enableTooltips("gtrcontent")};
</script>

<script src="/ScoDoc/static/jQuery/jquery.js"></script>
<script src="/ScoDoc/static/jQuery/jquery-migrate-1.2.0.min.js"></script>
<script src="/ScoDoc/static/libjs/jquery.field.min.js"></script>

<script src="/ScoDoc/static/libjs/jquery-ui-1.10.4.custom/js/jquery-ui-1.10.4.custom.min.js"></script>

<script src="/ScoDoc/static/libjs/qtip/jquery.qtip-3.0.3.min.js"></script>
<link type="text/css" rel="stylesheet" href="/ScoDoc/static/libjs/qtip/jquery.qtip-3.0.3.min.css" />

<script src="/ScoDoc/static/js/scodoc.js"></script>
<script src="/ScoDoc/static/js/etud_info.js"></script>
"""


def scodoc_top_html_header(page_title="ScoDoc: bienvenue"):
    H = [
        _HTML_BEGIN % {"page_title": page_title, "encoding": scu.SCO_ENCODING},
        """</head><body class="gtrcontent" id="gtrcontent">""",
        scu.CUSTOM_HTML_HEADER_CNX,
    ]
    return "\n".join(H)


# Header:
def sco_header(
    # optional args
    page_title="",  # page title
    no_side_bar=False,  # hide sidebar
    cssstyles=[],  # additionals CSS sheets
    javascripts=[],  # additionals JS filenames to load
    scripts=[],  # script to put in page header
    bodyOnLoad="",  # JS
    init_jquery=True,  # load and init jQuery
    init_jquery_ui=True,  # include all stuff for jquery-ui and initialize scripts
    init_qtip=False,  # include qTip
    init_google_maps=False,  # Google maps
    init_datatables=True,
    titrebandeau="",  # titre dans bandeau superieur
    head_message="",  # message action (petit cadre jaune en haut)
    user_check=True,  # verifie passwords temporaires
):
    "Main HTML page header for ScoDoc"
    from app.scodoc.sco_formsemestre_status import formsemestre_page_title

    # Get head message from http request:
    if not head_message:
        if request.method == "POST":
            head_message = request.form.get("head_message", "")
        elif request.method == "GET":
            head_message = request.args.get("head_message", "")

    params = {
        "page_title": page_title or sco_version.SCONAME,
        "no_side_bar": no_side_bar,
        "ScoURL": scu.ScoURL(),
        "encoding": scu.SCO_ENCODING,
        "titrebandeau_mkup": "<td>" + titrebandeau + "</td>",
        "authuser": current_user.user_name,
    }
    if bodyOnLoad:
        params["bodyOnLoad_mkup"] = """onload="%s" """ % bodyOnLoad
    else:
        params["bodyOnLoad_mkup"] = ""
    if no_side_bar:
        params["margin_left"] = "1em"
    else:
        params["margin_left"] = "140px"

    if init_jquery_ui or init_qtip or init_datatables:
        init_jquery = True

    H = [
        """<!DOCTYPE html><html lang="fr">
<head>
<meta charset="utf-8"/>
<title>%(page_title)s</title>
<meta name="LANG" content="fr" />
<meta name="DESCRIPTION" content="ScoDoc" />

"""
        % params
    ]
    # jQuery UI
    if init_jquery_ui:
        # can modify loaded theme here
        H.append(
            '<link type="text/css" rel="stylesheet" href="/ScoDoc/static/libjs/jquery-ui-1.10.4.custom/css/smoothness/jquery-ui-1.10.4.custom.min.css" />\n'
        )
    if init_google_maps:
        # It may be necessary to add an API key:
        H.append('<script src="https://maps.google.com/maps/api/js"></script>')

    # Feuilles de style additionnelles:
    for cssstyle in cssstyles:
        H.append(
            """<link type="text/css" rel="stylesheet" href="/ScoDoc/static/%s" />\n"""
            % cssstyle
        )

    H.append(
        """
<link href="/ScoDoc/static/css/scodoc.css" rel="stylesheet" type="text/css" />
<link href="/ScoDoc/static/css/menu.css" rel="stylesheet" type="text/css" />
<link href="/ScoDoc/static/css/gt_table.css" rel="stylesheet" type="text/css" />

<script src="/ScoDoc/static/libjs/menu.js"></script>
<script src="/ScoDoc/static/libjs/bubble.js"></script>
<script>
 window.onload=function(){enableTooltips("gtrcontent")};

 var SCO_URL="%(ScoURL)s";
</script>"""
        % params
    )

    # jQuery
    if init_jquery:
        H.append(
            """<script src="/ScoDoc/static/jQuery/jquery.js"></script>
                  """
        )
        H.append('<script src="/ScoDoc/static/libjs/jquery.field.min.js"></script>')
    # qTip
    if init_qtip:
        H.append(
            '<script src="/ScoDoc/static/libjs/qtip/jquery.qtip-3.0.3.min.js"></script>'
        )
        H.append(
            '<link type="text/css" rel="stylesheet" href="/ScoDoc/static/libjs/qtip/jquery.qtip-3.0.3.min.css" />'
        )

    if init_jquery_ui:
        H.append(
            '<script src="/ScoDoc/static/libjs/jquery-ui-1.10.4.custom/js/jquery-ui-1.10.4.custom.min.js"></script>'
        )
        # H.append('<script src="/ScoDoc/static/libjs/jquery-ui/js/jquery-ui-i18n.js"></script>')
        H.append('<script src="/ScoDoc/static/js/scodoc.js"></script>')
    if init_google_maps:
        H.append(
            '<script src="/ScoDoc/static/libjs/jquery.ui.map.full.min.js"></script>'
        )
    if init_datatables:
        H.append(
            '<link rel="stylesheet" type="text/css" href="/ScoDoc/static/DataTables/datatables.min.css"/>'
        )
        H.append('<script src="/ScoDoc/static/DataTables/datatables.min.js"></script>')
    # JS additionels
    for js in javascripts:
        H.append("""<script src="/ScoDoc/static/%s"></script>\n""" % js)

    H.append(
        """<style>
.gtrcontent {
   margin-left: %(margin_left)s;
   height: 100%%;
   margin-bottom: 10px;
}
</style>
"""
        % params
    )
    # Scripts de la page:
    if scripts:
        H.append("""<script>""")
        for script in scripts:
            H.append(script)
        H.append("""</script>""")

    H.append("</head>")

    # Body et bandeau haut:
    H.append("""<body %(bodyOnLoad_mkup)s>""" % params)
    H.append(scu.CUSTOM_HTML_HEADER)
    #
    if not no_side_bar:
        H.append(html_sidebar.sidebar())
    H.append("""<div class="gtrcontent" id="gtrcontent">""")
    #
    # Barre menu semestre:
    H.append(formsemestre_page_title())

    # Avertissement si mot de passe à changer
    if user_check:
        if current_user.passwd_temp:
            H.append(
                """<div class="passwd_warn">
    Attention !<br/>
    Vous avez reçu un mot de passe temporaire.<br/>
    Vous devez le changer: <a href="%s/form_change_password?user_name=%s">cliquez ici</a>
    </div>"""
                % (scu.UsersURL, current_user.user_name)
            )
    #
    if head_message:
        H.append('<div class="head_message">' + html.escape(head_message) + "</div>")
    #
    # div pour affichage messages temporaires
    H.append('<div id="sco_msg" class="head_message"></div>')
    #
    return "".join(H)


def sco_footer():
    """Main HTMl pages footer"""
    return (
        """</div><!-- /gtrcontent -->""" + scu.CUSTOM_HTML_FOOTER + """</body></html>"""
    )


def html_sem_header(
    title, sem=None, with_page_header=True, with_h2=True, page_title=None, **args
):
    "Titre d'une page semestre avec lien vers tableau de bord"
    # sem now unused and thus optional...
    if with_page_header:
        h = sco_header(page_title="%s" % (page_title or title), **args)
    else:
        h = ""
    if with_h2:
        return h + """<h2 class="formsemestre">%s</h2>""" % (title)
    else:
        return h
