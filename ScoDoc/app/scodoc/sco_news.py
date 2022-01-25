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

"""Gestion des "nouvelles"
"""
import re
import time


from operator import itemgetter

from flask import g
from flask_login import current_user

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc import sco_formsemestre
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_preferences
from app.scodoc import sco_users
from app import email


_scolar_news_editor = ndb.EditableTable(
    "scolar_news",
    "news_id",
    ("date", "authenticated_user", "type", "object", "text", "url"),
    filter_dept=True,
    sortkey="date desc",
    output_formators={"date": ndb.DateISOtoDMY},
    input_formators={"date": ndb.DateDMYtoISO},
    html_quote=False,  # no user supplied data, needed to store html links
)

NEWS_INSCR = "INSCR"  # inscription d'étudiants (object=None ou formsemestre_id)
NEWS_NOTE = "NOTES"  # saisie note (object=moduleimpl_id)
NEWS_FORM = "FORM"  # modification formation (object=formation_id)
NEWS_SEM = "SEM"  # creation semestre (object=None)
NEWS_MISC = "MISC"  # unused
NEWS_MAP = {
    NEWS_INSCR: "inscription d'étudiants",
    NEWS_NOTE: "saisie note",
    NEWS_FORM: "modification formation",
    NEWS_SEM: "création semestre",
    NEWS_MISC: "opération",  # unused
}
NEWS_TYPES = list(NEWS_MAP.keys())

scolar_news_create = _scolar_news_editor.create
scolar_news_list = _scolar_news_editor.list

_LAST_NEWS = {}  # { (authuser_name, type, object) : time }


def add(typ, object=None, text="", url=None, max_frequency=False):
    """Ajoute une nouvelle.
    Si max_frequency, ne genere pas 2 nouvelles identiques à moins de max_frequency
    secondes d'intervalle.
    """
    authuser_name = current_user.user_name
    cnx = ndb.GetDBConnexion()
    args = {
        "authenticated_user": authuser_name,
        "user_info": sco_users.user_info(authuser_name),
        "type": typ,
        "object": object,
        "text": text,
        "url": url,
    }
    t = time.time()
    if max_frequency:
        last_news_time = _LAST_NEWS.get((authuser_name, typ, object), False)
        if last_news_time and (t - last_news_time < max_frequency):
            # log("not recording")
            return

    log("news: %s" % args)

    _LAST_NEWS[(authuser_name, typ, object)] = t

    _send_news_by_mail(args)
    return scolar_news_create(cnx, args)


def scolar_news_summary(n=5):
    """Return last n news.
    News are "compressed", ie redondant events are joined.
    """
    from app.scodoc import sco_etud

    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT id AS news_id, *
    FROM scolar_news
    WHERE dept_id=%(dept_id)s
    ORDER BY date DESC LIMIT 100
    """,
        {"dept_id": g.scodoc_dept_id},
    )
    selected_news = {}  # (type,object) : news dict
    news = cursor.dictfetchall()  # la plus récente d'abord

    for r in reversed(news):  # la plus ancienne d'abord
        # si on a deja une news avec meme (type,object)
        # et du meme jour, on la remplace
        dmy = ndb.DateISOtoDMY(r["date"])  # round
        key = (r["type"], r["object"], dmy)
        selected_news[key] = r

    news = list(selected_news.values())
    # sort by date, descending
    news.sort(key=itemgetter("date"), reverse=True)
    news = news[:n]
    # mimic EditableTable.list output formatting:
    for n in news:
        n["date822"] = n["date"].strftime("%a, %d %b %Y %H:%M:%S %z")
        # heure
        n["hm"] = n["date"].strftime("%Hh%M")
        for k in n.keys():
            if n[k] is None:
                n[k] = ""
            if k in _scolar_news_editor.output_formators:
                n[k] = _scolar_news_editor.output_formators[k](n[k])
        # date resumee
        j, m = n["date"].split("/")[:2]
        mois = sco_etud.MONTH_NAMES_ABBREV[int(m) - 1]
        n["formatted_date"] = "%s %s %s" % (j, mois, n["hm"])
        # indication semestre si ajout notes:
        infos = _get_formsemestre_infos_from_news(n)
        if infos:
            n["text"] += (
                ' (<a href="Notes/formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(descr_sem)s</a>)'
                % infos
            )
        n["text"] += (
            " par " + sco_users.user_info(n["authenticated_user"])["nomcomplet"]
        )
    return news


def _get_formsemestre_infos_from_news(n):
    """Informations sur le semestre concerné par la nouvelle n
    {} si inexistant
    """
    formsemestre_id = None
    if n["type"] == NEWS_INSCR:
        formsemestre_id = n["object"]
    elif n["type"] == NEWS_NOTE:
        moduleimpl_id = n["object"]
        if n["object"]:
            mods = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)
            if not mods:
                return {}  # module does not exists anymore
        return {}  # pas d'indication du module
        mod = mods[0]
        formsemestre_id = mod["formsemestre_id"]

    if not formsemestre_id:
        return {}

    try:
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    except:
        # semestre n'existe plus
        return {}

    if sem["semestre_id"] > 0:
        descr_sem = "S%d" % sem["semestre_id"]
    else:
        descr_sem = ""
    if sem["modalite"]:
        descr_sem += " " + sem["modalite"]
    return {"formsemestre_id": formsemestre_id, "sem": sem, "descr_sem": descr_sem}


def scolar_news_summary_html(n=5):
    """News summary, formated in HTML"""
    news = scolar_news_summary(n=n)
    if not news:
        return ""
    H = ['<div class="news"><span class="newstitle">Dernières opérations']
    H.append('</span><ul class="newslist">')

    for n in news:
        H.append(
            '<li class="newslist"><span class="newsdate">%(formatted_date)s</span><span class="newstext">%(text)s</span></li>'
            % n
        )
    H.append("</ul>")

    # Informations générales
    H.append(
        """<div>
    Pour être informé des évolutions de ScoDoc,
    vous pouvez vous
    <a class="stdlink" href="%s">
    abonner à la liste de diffusion</a>.
    </div>
    """
        % scu.SCO_ANNONCES_WEBSITE
    )

    H.append("</div>")
    return "\n".join(H)


def _send_news_by_mail(n):
    """Notify by email"""
    infos = _get_formsemestre_infos_from_news(n)
    formsemestre_id = infos.get("formsemestre_id", None)
    prefs = sco_preferences.SemPreferences(formsemestre_id=formsemestre_id)
    destinations = prefs["emails_notifications"] or ""
    destinations = [x.strip() for x in destinations.split(",")]
    destinations = [x for x in destinations if x]
    if not destinations:
        return
    #
    txt = n["text"]
    if infos:
        txt += "\n\nSemestre %(titremois)s\n\n" % infos["sem"]
        txt += (
            """<a href="Notes/formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(descr_sem)s</a>
            """
            % infos
        )
        txt += "\n\nEffectué par: %(nomcomplet)s\n" % n["user_info"]

    txt = (
        "\n"
        + txt
        + """\n
--- Ceci est un message de notification automatique issu de ScoDoc
--- vous recevez ce message car votre adresse est indiquée dans les paramètres de ScoDoc.
"""
    )

    # Transforme les URL en URL absolue
    base = scu.ScoURL()
    txt = re.sub('href=.*?"', 'href="' + base + "/", txt)

    # Transforme les liens HTML en texte brut: '<a href="url">texte</a>' devient 'texte: url'
    # (si on veut des messages non html)
    txt = re.sub(r'<a.*?href\s*=\s*"(.*?)".*?>(.*?)</a>', r"\2: \1", txt)

    subject = "[ScoDoc] " + NEWS_MAP.get(n["type"], "?")
    sender = prefs["email_from_addr"]

    email.send_email(subject, sender, destinations, txt)
