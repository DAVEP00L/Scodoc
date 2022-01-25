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

"""
Génération de la "sidebar" (marge gauche des pages HTML)
"""
from flask import render_template, url_for
from flask import g, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
from app.scodoc import sco_preferences
from app.scodoc.sco_permissions import Permission


def sidebar_common():
    "partie commune à toutes les sidebar"
    H = [
        f"""<a class="scodoc_title" href="{url_for("scodoc.index", scodoc_dept=g.scodoc_dept)}">ScoDoc 9</a>
        <div id="authuser"><a id="authuserlink" href="{
            url_for("users.user_info_page", 
            scodoc_dept=g.scodoc_dept, user_name=current_user.user_name)
            }">{current_user.user_name}</a>
        <br/><a id="deconnectlink" href="{url_for("auth.logout")}">déconnexion</a>
        </div>
        {sidebar_dept()}
        <h2 class="insidebar">Scolarité</h2>
        <a href="{scu.ScoURL()}" class="sidebar">Semestres</a> <br/> 
        <a href="{scu.NotesURL()}" class="sidebar">Programmes</a> <br/> 
        <a href="{scu.AbsencesURL()}" class="sidebar">Absences</a> <br/>
        """
    ]

    if current_user.has_permission(
        Permission.ScoUsersAdmin
    ) or current_user.has_permission(Permission.ScoUsersView):
        H.append(
            f"""<a href="{scu.UsersURL()}" class="sidebar">Utilisateurs</a> <br/>"""
        )

    if current_user.has_permission(Permission.ScoChangePreferences):
        H.append(
            f"""<a href="{url_for("scolar.edit_preferences", scodoc_dept=g.scodoc_dept)}" 
            class="sidebar">Paramétrage</a> <br/>"""
        )

    return "".join(H)


def sidebar():
    "Main HTML page sidebar"
    # rewritten from legacy DTML code
    from app.scodoc import sco_abs
    from app.scodoc import sco_etud

    params = {}

    H = [
        f"""<div class="sidebar">
        { sidebar_common() }
        <div class="box-chercheetud">Chercher étudiant:<br/>
        <form method="get" id="form-chercheetud" 
              action="{ url_for('scolar.search_etud_in_dept', scodoc_dept=g.scodoc_dept) }">
        <div><input type="text" size="12" id="in-expnom" name="expnom" spellcheck="false"></input></div>
        </form></div>
        <div class="etud-insidebar">
        """
    ]
    # ---- Il y-a-t-il un etudiant selectionné ?
    etudid = g.get("etudid", None)
    if not etudid:
        if request.method == "GET":
            etudid = request.args.get("etudid", None)
        elif request.method == "POST":
            etudid = request.form.get("etudid", None)

    if etudid:
        etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
        params.update(etud)
        params["fiche_url"] = url_for(
            "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
        )
        # compte les absences du semestre en cours
        H.append(
            """<h2 id="insidebar-etud"><a href="%(fiche_url)s" class="sidebar">
    <font color="#FF0000">%(civilite_str)s %(nom_disp)s</font></a>
    </h2>
    <b>Absences</b>"""
            % params
        )
        if etud["cursem"]:
            cur_sem = etud["cursem"]
            nbabs, nbabsjust = sco_abs.get_abs_count(etudid, cur_sem)
            nbabsnj = nbabs - nbabsjust
            H.append(
                f"""<span title="absences du { cur_sem["date_debut"] } au { cur_sem["date_fin"] }">(1/2 j.)
                <br/>{ nbabsjust } J., { nbabsnj } N.J.</span>"""
            )
        H.append("<ul>")
        if current_user.has_permission(Permission.ScoAbsChange):
            H.append(
                f"""
                <li><a href="{ url_for('absences.SignaleAbsenceEtud', scodoc_dept=g.scodoc_dept, etudid=etudid) }">Ajouter</a></li>
                <li><a href="{ url_for('absences.JustifAbsenceEtud', scodoc_dept=g.scodoc_dept, etudid=etudid) }">Justifier</a></li>
                <li><a href="{ url_for('absences.AnnuleAbsenceEtud', scodoc_dept=g.scodoc_dept, etudid=etudid) }">Supprimer</a></li>
                """
            )
            if sco_preferences.get_preference("handle_billets_abs"):
                H.append(
                    f"""<li><a href="{ url_for('absences.listeBilletsEtud', scodoc_dept=g.scodoc_dept, etudid=etudid) }">Billets</a></li>"""
                )
        H.append(
            f"""
            <li><a href="{ url_for('absences.CalAbs', scodoc_dept=g.scodoc_dept, etudid=etudid) }">Calendrier</a></li>
            <li><a href="{ url_for('absences.ListeAbsEtud', scodoc_dept=g.scodoc_dept, etudid=etudid) }">Liste</a></li>
            </ul>
            """
        )
    else:
        pass  # H.append("(pas d'étudiant en cours)")
    # ---------
    H.append("</div>")  # /etud-insidebar
    # Logo
    H.append(
        f"""<div class="logo-insidebar">
        <div class="sidebar-bottom"><a href="{ url_for( 'scodoc.about', scodoc_dept=g.scodoc_dept ) }" class="sidebar">À propos</a><br/>
        <a href="{ scu.SCO_USER_MANUAL }" target="_blank" class="sidebar">Aide</a>
        </div></div>
        <div class="logo-logo">
           <a href="{ url_for( 'scodoc.about', scodoc_dept=g.scodoc_dept ) }">
                    { scu.icontag("scologo_img", no_size=True) }</a>
        </div>
        </div> 
        <!-- end of sidebar -->
        """
    )
    return "".join(H)


def sidebar_dept():
    """Partie supérieure de la marge de gauche"""
    return render_template(
        "sidebar_dept.html",
        prefs=sco_preferences.SemPreferences(),
    )
