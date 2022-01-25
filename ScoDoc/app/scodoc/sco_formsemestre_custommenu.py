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

"""Menu "custom" (défini par l'utilisateur) dans les semestres
"""
import flask
from flask import g, url_for, request

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_formsemestre
from app.scodoc import sco_edt_cal

_custommenuEditor = ndb.EditableTable(
    "notes_formsemestre_custommenu",
    "custommenu_id",
    ("custommenu_id", "formsemestre_id", "title", "url", "idx"),
    sortkey="idx",
)


notes_formsemestre_custommenu_create = _custommenuEditor.create
notes_formsemestre_custommenu_list = _custommenuEditor.list
notes_formsemestre_custommenu_edit = _custommenuEditor.edit


def formsemestre_custommenu_get(formsemestre_id):
    "returns dict [ { 'title' :  xxx, 'url' : xxx } ]"
    cnx = ndb.GetDBConnexion()
    vals = notes_formsemestre_custommenu_list(cnx, {"formsemestre_id": formsemestre_id})
    return vals


def formsemestre_custommenu_html(formsemestre_id):
    "HTML code for custom menu"
    menu = []
    # Calendrier électronique ?
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    ics_url = sco_edt_cal.formsemestre_get_ics_url(sem)
    if ics_url:
        menu.append({"title": "Emploi du temps (ics)", "url": ics_url})
    menu += formsemestre_custommenu_get(formsemestre_id)
    menu.append(
        {
            "title": "Modifier ce menu...",
            "endpoint": "notes.formsemestre_custommenu_edit",
            "args": {"formsemestre_id": formsemestre_id},
        }
    )
    return htmlutils.make_menu("Liens", menu)


def formsemestre_custommenu_edit(formsemestre_id):
    """Dialog to edit the custom menu"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    dest_url = (
        scu.NotesURL() + "/formsemestre_status?formsemestre_id=%s" % formsemestre_id
    )
    H = [
        html_sco_header.html_sem_header("Modification du menu du semestre ", sem),
        """<p class="help">Ce menu, spécifique à chaque semestre, peut être utilisé pour placer des liens vers vos applications préférées.</p>
          <p class="help">Procédez en plusieurs fois si vous voulez ajouter plusieurs items.</p>""",
    ]
    descr = [
        ("formsemestre_id", {"input_type": "hidden"}),
        (
            "sep",
            {
                "input_type": "separator",
                "template": "<tr><td><b>Titre</b></td><td><b>URL</b></td></tr>",
            },
        ),
    ]
    menu = formsemestre_custommenu_get(formsemestre_id)
    menu.append({"custommenu_id": "new", "url": "", "title": ""})
    initvalues = {}
    for item in menu:
        descr.append(
            (
                "title_" + str(item["custommenu_id"]),
                {"size": 40, "template": '<tr><td class="tf-field">%(elem)s</td>'},
            )
        )
        descr.append(
            (
                "url_" + str(item["custommenu_id"]),
                {"size": 80, "template": '<td class="tf-field">%(elem)s</td></tr>'},
            )
        )
        initvalues["title_" + str(item["custommenu_id"])] = item["title"]
        initvalues["url_" + str(item["custommenu_id"])] = item["url"]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        initvalues=initvalues,
        cancelbutton="Annuler",
        method="GET",
        submitlabel="Enregistrer",
        name="tf",
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        # form submission
        cnx = ndb.GetDBConnexion()
        # add new
        if tf[2]["title_new"]:
            notes_formsemestre_custommenu_create(
                cnx,
                {
                    "formsemestre_id": formsemestre_id,
                    "title": tf[2]["title_new"],
                    "url": tf[2]["url_new"],
                },
            )
        # edit existings
        s = "title_"
        for x in tf[2].keys():
            if x[: len(s)] == s and x != "title_new":
                custommenu_id = x[len(s) :]
                notes_formsemestre_custommenu_edit(
                    cnx,
                    {
                        "custommenu_id": custommenu_id,
                        "title": tf[2]["title_" + custommenu_id],
                        "url": tf[2]["url_" + custommenu_id],
                    },
                )
        return flask.redirect(dest_url)
