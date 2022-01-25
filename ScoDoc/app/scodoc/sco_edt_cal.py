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

"""Accès aux emplois du temps

XXX usage uniquement experimental pour tests implémentations

XXX incompatible avec les ics HyperPlanning Paris 13 (était pour GPU).

"""

import icalendar
import pprint
import traceback
import urllib

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_preferences


def formsemestre_get_ics_url(sem):
    """
    edt_sem_ics_url est un template
    utilisé avec .format(sem=sem)
    Par exemple:
    https://example.fr/agenda/{sem[etapes][0]}
    """
    ics_url_tmpl = sco_preferences.get_preference(
        "edt_sem_ics_url", sem["formsemestre_id"]
    )
    if not ics_url_tmpl:
        return None
    try:
        ics_url = ics_url_tmpl.format(sem=sem)
    except:
        log(
            "Exception in formsemestre_get_ics_url(formsemestre_id=%s)"
            % sem["formsemestre_id"]
        )
        log("ics_url_tmpl='%s'" % ics_url_tmpl)
        log(traceback.format_exc())
        return None
    return ics_url


def formsemestre_load_ics(sem):
    """Load ics data, from our cache or, when necessary, from external provider"""
    # TODO: cacher le résultat
    ics_url = formsemestre_get_ics_url(sem)
    if not ics_url:
        ics_data = ""
    else:
        log("Loading edt from %s" % ics_url)
        f = urllib.request.urlopen(
            ics_url, timeout=5
        )  # 5s TODO: add config parameter, eg for slow networks
        ics_data = f.read()
        f.close()

    cal = icalendar.Calendar.from_ical(ics_data)
    return cal


# def formsemestre_edt_groups_used(sem):
#    """L'ensemble des groupes EDT utilisés dans l'emploi du temps publié"""
#    cal = formsemestre_load_ics(sem)
#    return {e["X-GROUP-ID"].decode("utf8") for e in events}


def get_edt_transcodage_groups(formsemestre_id):
    """-> { nom_groupe_edt : nom_groupe_scodoc }"""
    # TODO: valider ces données au moment où on enregistre les préférences
    edt2sco = {}
    sco2edt = {}
    msg = ""  # message erreur, '' si ok
    txt = sco_preferences.get_preference("edt_groups2scodoc", formsemestre_id)
    if not txt:
        return edt2sco, sco2edt, msg

    line_num = 1
    for line in txt.split("\n"):
        fs = [s.strip() for s in line.split(";")]
        if len(fs) == 1:  # groupe 'tous'
            edt2sco[fs[0]] = None
            sco2edt[None] = fs[0]
        elif len(fs) == 2:
            edt2sco[fs[0]] = fs[1]
            sco2edt[fs[1]] = fs[0]
        else:
            msg = "ligne %s invalide" % line_num
        line_num += 1

    log("sco2edt=%s" % pprint.pformat(sco2edt))
    return edt2sco, sco2edt, msg


def group_edt_json(group_id, start="", end=""):  # actuellement inutilisé
    """EDT complet du semestre, au format JSON
    TODO: indiquer un groupe
    TODO: utiliser start et end (2 dates au format ISO YYYY-MM-DD)
    TODO: cacher
    """
    group = sco_groups.get_group(group_id)
    sem = sco_formsemestre.get_formsemestre(group["formsemestre_id"])
    edt2sco, sco2edt, msg = get_edt_transcodage_groups(group["formsemestre_id"])

    edt_group_name = sco2edt.get(group["group_name"], group["group_name"])
    log("group scodoc=%s : edt=%s" % (group["group_name"], edt_group_name))

    cal = formsemestre_load_ics(sem)
    events = [e for e in cal.walk() if e.name == "VEVENT"]
    J = []
    for e in events:
        # if e['X-GROUP-ID'].strip() == edt_group_name:
        if "DESCRIPTION" in e:
            d = {
                "title": e.decoded("DESCRIPTION"),  # + '/' + e['X-GROUP-ID'],
                "start": e.decoded("dtstart").isoformat(),
                "end": e.decoded("dtend").isoformat(),
            }
            J.append(d)

    return scu.sendJSON(J)


"""XXX
for e in events:
    if 'DESCRIPTION' in e:
        print e.decoded('DESCRIPTION')
"""


def experimental_calendar(group_id=None, formsemestre_id=None):  # inutilisé
    """experimental page"""
    return "\n".join(
        [
            html_sco_header.sco_header(
                javascripts=[
                    "libjs/purl.js",
                    "libjs/moment.min.js",
                    "libjs/fullcalendar/fullcalendar.min.js",
                ],
                cssstyles=[
                    #                'libjs/bootstrap-3.1.1-dist/css/bootstrap.min.css',
                    #                'libjs/bootstrap-3.1.1-dist/css/bootstrap-theme.min.css',
                    #                'libjs/bootstrap-multiselect/bootstrap-multiselect.css'
                    "libjs/fullcalendar/fullcalendar.css",
                    # media='print' 'libjs/fullcalendar/fullcalendar.print.css'
                ],
            ),
            """<style>
        #loading {
        display: none;
        position: absolute;
        top: 10px;
        right: 10px;
        }
        </style>
        """,
            """<form id="group_selector" method="get">
        <span style="font-weight: bold; font-size:120%">Emplois du temps du groupe</span>""",
            sco_groups_view.menu_group_choice(
                group_id=group_id, formsemestre_id=formsemestre_id
            ),
            """</form><div id="loading">loading...</div>
        <div id="calendar"></div>
        """,
            html_sco_header.sco_footer(),
            """<script>
$(document).ready(function() {

var group_id = $.url().param()['group_id'];

$('#calendar').fullCalendar({
  events: {
    url: 'group_edt_json?group_id=' + group_id,
    error: function() {
      $('#script-warning').show();
    }
   },
  timeFormat: 'HH:mm',
  timezone: 'local', // heure locale du client
  loading: function(bool) {
    $('#loading').toggle(bool);
  }
});
});
</script>
        """,
        ]
    )
