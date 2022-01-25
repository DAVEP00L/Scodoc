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

""" Gestion des relations avec les entreprises

Note: Code très ancien, porté de Zope/DTML, peu utilisable

=> Voir si des départements utilisent encore ce module et envisager de le supprimer.

"""


import time
import urllib

from flask import request
from flask_login import current_user

from app.scodoc import sco_utils as scu

# MIGRATION EN COURS => MODULE DESACTIVE !

# A REVOIR
# from sco_permissions import ScoEntrepriseView, ScoEntrepriseChange
# from app import log
# from scolog import logdb
# from sco_utils import SCO_ENCODING
# import app.scodoc.sco_utils as scu
# import html_sidebar
# from app.scodoc.gen_tables import GenTable
# from app.scodoc.TrivialFormulator import TrivialFormulator, TF
# import sco_etud
# import sco_entreprises


def entreprise_header(page_title=""):
    "common header for all Entreprises pages"
    return html_sco_header.sco_header(page_title=page_title)


def entreprise_footer():
    "common entreprise footer"
    return html_sco_header.sco_footer()


security.declareProtected(ScoEntrepriseView, "sidebar")


def sidebar():
    "barre gauche (overide std sco sidebar)"
    # rewritten from legacy DTML code
    # XXX rare cas restant d'utilisation de l'acquisition Zope2: à revoir
    params = {"ScoURL": scu.ScoURL()}
    H = [
        """<div id="sidebar-container">
        <div class="sidebar">""",
        html_sidebar.sidebar_common(),
        """<h2 class="insidebar"><a href="%(ScoURL)s/Entreprises" class="sidebar">Entreprises</a></h2>
<ul class="insidebar">"""
        % params,
    ]
    if current_user.has_permission(Permission.ScoEntrepriseChange):
        H.append(
            """<li class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_create" class="sidebar">Nouvelle entreprise</a> </li>"""
            % params
        )

    H.append(
        """<li class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_contact_list" class="sidebar">Contacts</a> </li></ul> """
        % params
    )

    # --- entreprise selectionnée:
    vals = scu.get_request_args()
    if "entreprise_id" in vals:
        entreprise_id = vals["entreprise_id"]
        E = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})
        if E:
            E = E[0]
            params.update(E)
            H.append(
                """<div class="entreprise-insidebar">
    <h3 class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_edit?entreprise_id=%(entreprise_id)s" class="sidebar">%(nom)s</a></h2>
    <ul class="insidebar">
    <li class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_correspondant_list?entreprise_id=%(entreprise_id)s" class="sidebar">Corresp.</a></li>"""
                % params
            )
            if current_user.has_permission(Permission.ScoEntrepriseChange):
                H.append(
                    """<li class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_correspondant_create?entreprise_id=%(entreprise_id)s" class="sidebar">Nouveau Corresp.</a></li>"""
                    % params
                )
            H.append(
                """<li class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_contact_list?entreprise_id=%(entreprise_id)s" class="sidebar">Contacts</a></li>"""
                % params
            )
            if current_user.has_permission(Permission.ScoEntrepriseChange):
                H.append(
                    """<li class="insidebar"><a href="%(ScoURL)s/Entreprises/entreprise_contact_create?entreprise_id=%(entreprise_id)s" class="sidebar">Nouveau "contact"</a></li>"""
                    % params
                )
            H.append("</ul></div>")

    #
    H.append("""<br/><br/>%s""" % scu.icontag("entreprise_side_img"))
    if not current_user.has_permission(Permission.ScoEntrepriseChange):
        H.append("""<br/><em>(Lecture seule)</em>""")
    H.append("""</div> </div> <!-- end of sidebar -->""")
    return "".join(H)


# --------------------------------------------------------------------
#
#   Entreprises : Vues
#
# --------------------------------------------------------------------
security.declareProtected(ScoEntrepriseView, "index_html")


def index_html(etud_nom=None, limit=50, offset="", format="html"):
    """Accueil module entreprises"""
    # Traduit du DTML - utilise table standard
    if limit:
        limit = int(limit)
    if offset:
        offset = int(offset or 0)
    vals = scu.get_request_args()
    if etud_nom:
        entreprises = sco_entreprises.do_entreprise_list_by_etud(
            args=vals, sort_on_contact=True
        )
        table_navigation = ""
    else:
        entreprises = sco_entreprises.do_entreprise_list(
            args=vals,
            test="~*",
            sort_on_contact=True,
            limit=limit,
            offset=offset,
        )
        # Liens navigation précédent/suivant
        webparams = {"limit": limit}
        if offset:
            webparams["offset"] = max((offset or 0) - limit, 0)
            prev_lnk = '<a class="stdlink" href="%s">précédentes</a>' % (
                request.base_url + "?" + urllib.parse.urlencode(webparams)
            )
        else:
            prev_lnk = ""
        if len(entreprises) >= limit:
            webparams["offset"] = (offset or 0) + limit
            next_lnk = '<a class="stdlink" href="%s">suivantes</a>' % (
                request.base_url + "?" + urllib.parse.urlencode(webparams)
            )
        else:
            next_lnk = ""
        table_navigation = (
            '<div class="table_nav"><span class="table_nav_prev">'
            + prev_lnk
            + '</span><span class="table_nav_mid"></span><span class="table_nav_next">'
            + next_lnk
            + "</span></div>"
        )
    # Ajout des liens sur la table:
    for e in entreprises:
        e["_nom_target"] = "entreprise_edit?entreprise_id=%(entreprise_id)s" % e
        e["correspondants"] = sco_entreprises.do_entreprise_correspondant_list(
            args={"entreprise_id": e["entreprise_id"]}
        )
        e["nbcorr"] = "%d corr." % len(e["correspondants"])
        e["_nbcorr_target"] = (
            "entreprise_correspondant_list?entreprise_id=%(entreprise_id)s" % e
        )
        e["contacts"] = sco_entreprises.do_entreprise_contact_list(
            args={"entreprise_id": e["entreprise_id"]}
        )
        e["nbcontact"] = "%d contacts." % len(e["contacts"])
        e["_nbcontact_target"] = (
            "entreprise_contact_list?entreprise_id=%(entreprise_id)s" % e
        )
    tab = GenTable(
        rows=entreprises,
        columns_ids=("nom", "ville", "secteur", "nbcorr", "nbcontact"),
        titles={
            "nom": "Entreprise",
            "ville": "Ville",
            "secteur": "Secteur",
            "nbcorr": "Corresp.",
            "contacts": "Contacts",
        },
        origin="Généré par %s le " % sco_version.SCONAME + scu.timedate_human_repr(),
        filename=scu.make_filename(
            "entreprises_%s" % context.get_preference("DeptName")
        ),
        caption="Entreprises du département %s" % context.get_preference("DeptName"),
        html_sortable=True,
        html_class="entreprise_list table_leftalign",
        html_with_td_classes=True,
        html_next_section=table_navigation,
        base_url=request.base_url + "?",
        preferences=context.get_preferences(),
    )
    if format != "html":
        return tab.make_page(format=format)
    else:
        H = [
            entreprise_header(page_title="Suivi entreprises"),
            """<h2>Suivi relations entreprises</h2>""",
            """<div class="entreprise_list_table">""",
            tab.html(),
            """</div>""",
            entreprise_footer(),
        ]
        return "\n".join(H)


security.declareProtected(ScoEntrepriseView, "entreprise_contact_list")


def entreprise_contact_list(entreprise_id=None, format="html"):
    """Liste des contacts de l'entreprise"""
    H = [entreprise_header(page_title="Suivi entreprises")]
    if entreprise_id:
        E = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})[0]
        C = sco_entreprises.do_entreprise_contact_list(
            args={"entreprise_id": entreprise_id}
        )
        H.append(
            """<h2 class="entreprise_contact">Listes des contacts avec l'entreprise %(nom)s</h2>
        """
            % E
        )
    else:
        C = sco_entreprises.do_entreprise_contact_list(args={})
        H.append(
            """<h2 class="entreprise_contact">Listes des contacts</h2>
        """
        )
    for c in C:
        c["_date_target"] = "%s/entreprise_contact_edit?entreprise_contact_id=%s" % (
            scu.EntreprisesURL(),
            c["entreprise_contact_id"],
        )
        c["entreprise"] = sco_entreprises.do_entreprise_list(
            args={"entreprise_id": c["entreprise_id"]}
        )[0]
        if c["etudid"]:
            c["etud"] = context.getEtudInfo(etudid=c["etudid"], filled=1)[0]
            c["etudnom"] = c["etud"]["nomprenom"]
            c["_etudnom_target"] = "%s/ficheEtud?etudid=%s" % (
                scu.ScoURL(),
                c["etudid"],
            )
        else:
            c["etud"] = None
            c["etudnom"] = ""

    tab = GenTable(
        rows=C,
        columns_ids=("date", "type_contact", "etudnom", "description"),
        titles={
            "date": "Date",
            "type_contact": "Object",
            "etudnom": "Étudiant",
            "description": "Description",
        },
        origin="Généré par %s le " % sco_version.SCONAME + scu.timedate_human_repr(),
        filename=scu.make_filename("contacts_%s" % context.get_preference("DeptName")),
        caption="",
        html_sortable=True,
        html_class="contact_list table_leftalign",
        html_with_td_classes=True,
        base_url=request.base_url + "?",
        preferences=context.get_preferences(),
    )
    if format != "html":
        return tab.make_page(format=format)

    H.append(tab.html())

    if current_user.has_permission(Permission.ScoEntrepriseChange):
        if entreprise_id:
            H.append(
                """<p class="entreprise_create"><a class="entreprise_create" href="entreprise_contact_create?entreprise_id=%(entreprise_id)s">nouveau "contact"</a></p>
            """
                % E
            )

    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseView, "entreprise_correspondant_list")


def entreprise_correspondant_list(
    entreprise_id=None,
    format="html",
):
    """Liste des correspondants de l'entreprise"""
    E = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})[0]
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """
        <h2>Listes des correspondants  dans l'entreprise %(nom)s</h2>
        """
        % E,
    ]
    correspondants = sco_entreprises.do_entreprise_correspondant_list(
        args={"entreprise_id": entreprise_id}
    )
    for c in correspondants:
        c["nomprenom"] = c["nom"].upper() + " " + c["nom"].capitalize()
        c[
            "_nomprenom_target"
        ] = "%s/entreprise_correspondant_edit?entreprise_corresp_id=%s" % (
            scu.EntreprisesURL(),
            c["entreprise_corresp_id"],
        )

        c["nom_entreprise"] = E["nom"]
        l = []
        if c["phone1"]:
            l.append(c["phone1"])
        if c["phone2"]:
            l.append(c["phone2"])
        if c["mobile"]:
            l.append(c["mobile"])
        c["telephones"] = " / ".join(l)
        c["mails"] = " ".join(
            [
                '<a href="mailto:%s">%s</a>' % (c["mail1"], c["mail1"])
                if c["mail1"]
                else "",
                '<a href="mailto:%s">%s</a>' % (c["mail2"], c["mail2"])
                if c["mail2"]
                else "",
            ]
        )
        c["modifier"] = (
            '<a class="corr_delete" href="entreprise_correspondant_edit?entreprise_corresp_id=%s">modifier</a>'
            % c["entreprise_corresp_id"]
        )
        c["supprimer"] = (
            '<a class="corr_delete" href="entreprise_correspondant_delete?entreprise_corresp_id=%s">supprimer</a>'
            % c["entreprise_corresp_id"]
        )
    tab = GenTable(
        rows=correspondants,
        columns_ids=(
            "nomprenom",
            "nom_entreprise",
            "fonction",
            "telephones",
            "mails",
            "note",
            "modifier",
            "supprimer",
        ),
        titles={
            "nomprenom": "Nom",
            "nom_entreprise": "Entreprise",
            "fonction": "Fonction",
            "telephones": "Téléphone",
            "mails": "Mail",
            "note": "Note",
            "modifier": "",
            "supprimer": "",
        },
        origin="Généré par %s le " % sco_version.SCONAME + scu.timedate_human_repr(),
        filename=scu.make_filename(
            "correspondants_%s_%s" % (E["nom"], context.get_preference("DeptName"))
        ),
        caption="",
        html_sortable=True,
        html_class="contact_list table_leftalign",
        html_with_td_classes=True,
        base_url=request.base_url + "?",
        preferences=context.get_preferences(),
    )
    if format != "html":
        return tab.make_page(format=format)

    H.append(tab.html())

    if current_user.has_permission(Permission.ScoEntrepriseChange):
        H.append(
            """<p class="entreprise_create"><a class="entreprise_create" href="entreprise_correspondant_create?entreprise_id=%(entreprise_id)s">Ajouter un correspondant dans l'entreprise %(nom)s</a></p>
            """
            % E
        )

    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseView, "entreprise_contact_edit")


def entreprise_contact_edit(entreprise_contact_id):
    """Form edit contact"""
    c = sco_entreprises.do_entreprise_contact_list(
        args={"entreprise_contact_id": entreprise_contact_id}
    )[0]
    link_create_corr = (
        '<a href="%s/entreprise_correspondant_create?entreprise_id=%s">créer un nouveau correspondant</a>'
        % (scu.EntreprisesURL(), c["entreprise_id"])
    )
    E = sco_entreprises.do_entreprise_list(args={"entreprise_id": c["entreprise_id"]})[
        0
    ]
    correspondants = sco_entreprises.do_entreprise_correspondant_listnames(
        args={"entreprise_id": c["entreprise_id"]}
    ) + [("inconnu", "")]

    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2 class="entreprise_contact">Suivi entreprises</h2>
            <h3>Contact avec entreprise %(nom)s</h3>"""
        % E,
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "entreprise_contact_id",
                {"default": entreprise_contact_id, "input_type": "hidden"},
            ),
            (
                "entreprise_id",
                {"input_type": "hidden", "default": c["entreprise_id"]},
            ),
            (
                "type_contact",
                {
                    "input_type": "menu",
                    "title": "Objet",
                    "allowed_values": (
                        "Prospection",
                        "Stage étudiant",
                        "Contrat Apprentissage",
                        "Projet",
                        "Autre",
                    ),
                },
            ),
            (
                "date",
                {
                    "size": 12,
                    "title": "Date du contact (j/m/a)",
                    "allow_null": False,
                },
            ),
            (
                "entreprise_corresp_id",
                {
                    "input_type": "menu",
                    "title": "Correspondant entreprise",
                    "explanation": link_create_corr,
                    "allow_null": True,
                    "labels": [x[0] for x in correspondants],
                    "allowed_values": [x[1] for x in correspondants],
                },
            ),
            (
                "etudiant",
                {
                    "size": 16,
                    "title": "Etudiant concerné",
                    "allow_null": True,
                    "default": c["etudid"],
                    "explanation": "nom (si pas ambigu) ou code",
                },
            ),
            (
                "enseignant",
                {"size": 16, "title": "Enseignant (tuteur)", "allow_null": True},
            ),
            (
                "description",
                {
                    "input_type": "textarea",
                    "rows": 3,
                    "cols": 40,
                    "title": "Description",
                },
            ),
        ),
        cancelbutton="Annuler",
        initvalues=c,
        submitlabel="Modifier les valeurs",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )

    if tf[0] == 0:
        H.append(tf[1])
        if current_user.has_permission(
            Permission.ScoEntrepriseChange,
        ):
            H.append(
                """<p class="entreprise_descr"><a class="entreprise_delete" href="entreprise_contact_delete?entreprise_contact_id=%s">Supprimer ce contact</a> </p>"""
                % entreprise_contact_id
            )
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL(context))
    else:
        etudok = sco_entreprises.do_entreprise_check_etudiant(tf[2]["etudiant"])
        if etudok[0] == 0:
            H.append("""<p class="entreprise_warning">%s</p>""" % etudok[1])
        else:
            tf[2].update({"etudid": etudok[1]})
            sco_entreprises.do_entreprise_contact_edit(tf[2])
            return flask.redirect(
                scu.EntreprisesURL()
                + "/entreprise_contact_list?entreprise_id="
                + str(c["entreprise_id"])
            )
    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseView, "entreprise_correspondant_edit")


def entreprise_correspondant_edit(entreprise_corresp_id):
    """Form édition d'un correspondant"""
    c = sco_entreprises.do_entreprise_correspondant_list(
        args={"entreprise_corresp_id": entreprise_corresp_id}
    )[0]
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2 class="entreprise_correspondant">Édition contact entreprise</h2>""",
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "entreprise_corresp_id",
                {"default": entreprise_corresp_id, "input_type": "hidden"},
            ),
            (
                "civilite",
                {
                    "input_type": "menu",
                    "labels": ["M.", "Mme"],
                    "allowed_values": ["M.", "Mme"],
                },
            ),
            ("nom", {"size": 25, "title": "Nom", "allow_null": False}),
            ("prenom", {"size": 25, "title": "Prénom"}),
            (
                "fonction",
                {
                    "input_type": "menu",
                    "allowed_values": (
                        "Directeur",
                        "RH",
                        "Resp. Administratif",
                        "Tuteur",
                        "Autre",
                    ),
                    "explanation": "fonction via à vis de l'IUT",
                },
            ),
            (
                "phone1",
                {
                    "size": 14,
                    "title": "Téléphone 1",
                },
            ),
            (
                "phone2",
                {
                    "size": 14,
                    "title": "Téléphone 2",
                },
            ),
            (
                "mobile",
                {
                    "size": 14,
                    "title": "Tél. mobile",
                },
            ),
            (
                "fax",
                {
                    "size": 14,
                    "title": "Fax",
                },
            ),
            (
                "mail1",
                {
                    "size": 25,
                    "title": "e-mail",
                },
            ),
            (
                "mail2",
                {
                    "size": 25,
                    "title": "e-mail 2",
                },
            ),
            (
                "note",
                {"input_type": "textarea", "rows": 3, "cols": 40, "title": "Note"},
            ),
        ),
        cancelbutton="Annuler",
        initvalues=c,
        submitlabel="Modifier les valeurs",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )
    if tf[0] == 0:
        H.append(tf[1])
    elif tf[0] == -1:
        return flask.redirect(
            "%s/entreprise_correspondant_list?entreprise_id=%s"
            % (scu.EntreprisesURL(), c["entreprise_id"])
        )
    else:
        sco_entreprises.do_entreprise_correspondant_edit(tf[2])
        return flask.redirect(
            "%s/entreprise_correspondant_list?entreprise_id=%s"
            % (scu.EntreprisesURL(), c["entreprise_id"])
        )
    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseChange, "entreprise_contact_create")


def entreprise_contact_create(entreprise_id):
    """Form création contact"""
    E = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})[0]
    correspondants = sco_entreprises.do_entreprise_correspondant_listnames(
        args={"entreprise_id": entreprise_id}
    )
    if not correspondants:
        correspondants = [("inconnu", "")]
    curtime = time.strftime("%d/%m/%Y")
    link_create_corr = (
        '<a href="%s/entreprise_correspondant_create?entreprise_id=%s">créer un nouveau correspondant</a>'
        % (scu.EntreprisesURL(), entreprise_id)
    )
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2 class="entreprise_contact">Nouveau "contact" avec l'entreprise %(nom)s</h2>"""
        % E,
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("entreprise_id", {"input_type": "hidden", "default": entreprise_id}),
            (
                "type_contact",
                {
                    "input_type": "menu",
                    "title": "Objet",
                    "allowed_values": (
                        "Prospection",
                        "Stage étudiant",
                        "Contrat Apprentissage DUT GTR1",
                        "Contrat Apprentissage DUT GTR2",
                        "Contrat Apprentissage Licence SQRT",
                        "Projet",
                        "Autre",
                    ),
                    "default": "Stage étudiant",
                },
            ),
            (
                "date",
                {
                    "size": 12,
                    "title": "Date du contact (j/m/a)",
                    "allow_null": False,
                    "default": curtime,
                },
            ),
            (
                "entreprise_corresp_id",
                {
                    "input_type": "menu",
                    "title": "Correspondant entreprise",
                    "explanation": link_create_corr,
                    "allow_null": True,
                    "labels": [x[0] for x in correspondants],
                    "allowed_values": [x[1] for x in correspondants],
                },
            ),
            (
                "etudiant",
                {
                    "size": 16,
                    "title": "Etudiant concerné",
                    "allow_null": True,
                    "explanation": "nom (si pas ambigu) ou code",
                },
            ),
            (
                "enseignant",
                {"size": 16, "title": "Enseignant (tuteur)", "allow_null": True},
            ),
            (
                "description",
                {
                    "input_type": "textarea",
                    "rows": 3,
                    "cols": 40,
                    "title": "Description",
                },
            ),
        ),
        cancelbutton="Annuler",
        submitlabel="Ajouter ce contact",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )
    if tf[0] == 0:
        H.append(tf[1])
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL(context))
    else:
        etudok = sco_entreprises.do_entreprise_check_etudiant(tf[2]["etudiant"])
        if etudok[0] == 0:
            H.append("""<p class="entreprise_warning">%s</p>""" % etudok[1])
        else:
            tf[2].update({"etudid": etudok[1]})
            sco_entreprises.do_entreprise_contact_create(tf[2])
            return flask.redirect(scu.EntreprisesURL())
    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseChange, "entreprise_contact_delete")


def entreprise_contact_delete(entreprise_contact_id):
    """Form delete contact"""
    c = sco_entreprises.do_entreprise_contact_list(
        args={"entreprise_contact_id": entreprise_contact_id}
    )[0]
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2>Suppression du contact</h2>""",
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("entreprise_contact_id", {"input_type": "hidden"}),),
        initvalues=c,
        submitlabel="Confirmer la suppression",
        cancelbutton="Annuler",
        readonly=not current_user.has_permission(ScoEntrepriseChange),
    )
    if tf[0] == 0:
        H.append(tf[1])
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL(context))
    else:
        sco_entreprises.do_entreprise_contact_delete(c["entreprise_contact_id"])
        return flask.redirect(scu.EntreprisesURL(context))
    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseChange, "entreprise_correspondant_create")


def entreprise_correspondant_create(entreprise_id):
    """Form création correspondant"""
    E = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})[0]
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2 class="entreprise_contact">Nouveau correspondant l'entreprise %(nom)s</h2>"""
        % E,
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("entreprise_id", {"input_type": "hidden", "default": entreprise_id}),
            (
                "civilite",
                {
                    "input_type": "menu",
                    "labels": ["M.", "Mme"],
                    "allowed_values": ["M.", "Mme"],
                },
            ),
            ("nom", {"size": 25, "title": "Nom", "allow_null": False}),
            ("prenom", {"size": 25, "title": "Prénom"}),
            (
                "fonction",
                {
                    "input_type": "menu",
                    "allowed_values": (
                        "Directeur",
                        "RH",
                        "Resp. Administratif",
                        "Tuteur",
                        "Autre",
                    ),
                    "default": "Tuteur",
                    "explanation": "fonction via à vis de l'IUT",
                },
            ),
            (
                "phone1",
                {
                    "size": 14,
                    "title": "Téléphone 1",
                },
            ),
            (
                "phone2",
                {
                    "size": 14,
                    "title": "Téléphone 2",
                },
            ),
            (
                "mobile",
                {
                    "size": 14,
                    "title": "Tél. mobile",
                },
            ),
            (
                "fax",
                {
                    "size": 14,
                    "title": "Fax",
                },
            ),
            (
                "mail1",
                {
                    "size": 25,
                    "title": "e-mail",
                },
            ),
            (
                "mail2",
                {
                    "size": 25,
                    "title": "e-mail 2",
                },
            ),
            (
                "note",
                {"input_type": "textarea", "rows": 3, "cols": 40, "title": "Note"},
            ),
        ),
        cancelbutton="Annuler",
        submitlabel="Ajouter ce correspondant",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )
    if tf[0] == 0:
        H.append(tf[1])
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL(context))
    else:
        sco_entreprises.do_entreprise_correspondant_create(tf[2])
        return flask.redirect(scu.EntreprisesURL(context))
    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseChange, "entreprise_correspondant_delete")


def entreprise_correspondant_delete(entreprise_corresp_id):
    """Form delete correspondant"""
    c = sco_entreprises.do_entreprise_correspondant_list(
        args={"entreprise_corresp_id": entreprise_corresp_id}
    )[0]
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2>Suppression du correspondant %(nom)s %(prenom)s</h2>""" % c,
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("entreprise_corresp_id", {"input_type": "hidden"}),),
        initvalues=c,
        submitlabel="Confirmer la suppression",
        cancelbutton="Annuler",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )
    if tf[0] == 0:
        H.append(tf[1])
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL())
    else:
        sco_entreprises.do_entreprise_correspondant_delete(c["entreprise_corresp_id"])
        return flask.redirect(scu.EntreprisesURL())
    H.append(entreprise_footer())
    return "\n".join(H)


security.declareProtected(ScoEntrepriseChange, "entreprise_delete")


def entreprise_delete(entreprise_id):
    """Form delete entreprise"""
    E = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})[0]
    H = [
        entreprise_header(page_title="Suivi entreprises"),
        """<h2>Suppression de l'entreprise %(nom)s</h2>
        <p class="entreprise_warning">Attention: supression définitive de l'entreprise, de ses correspondants et contacts.
        </p>"""
        % E,
    ]
    Cl = sco_entreprises.do_entreprise_correspondant_list(
        args={"entreprise_id": entreprise_id}
    )
    if Cl:
        H.append(
            """<h3>Correspondants dans l'entreprise qui seront <em>supprimés</em>:</h3><ul>"""
        )
        for c in Cl:
            H.append("""<li>%(nom)s %(prenom)s (%(fonction)s)</li>""" % c)
        H.append("""</ul>""")

    Cts = sco_entreprises.do_entreprise_contact_list(
        args={"entreprise_id": entreprise_id}
    )
    if Cts:
        H.append(
            """<h3>Contacts avec l'entreprise qui seront <em>supprimés</em>:</h3><ul>"""
        )
        for c in Cts:
            H.append("""<li>%(date)s %(description)s</li>""" % c)
        H.append("""</ul>""")
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("entreprise_id", {"input_type": "hidden"}),),
        initvalues=E,
        submitlabel="Confirmer la suppression",
        cancelbutton="Annuler",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )
    if tf[0] == 0:
        H.append(tf[1])
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL())
    else:
        sco_entreprises.do_entreprise_delete(E["entreprise_id"])
        return flask.redirect(scu.EntreprisesURL())
    H.append(entreprise_footer())
    return "\n".join(H)


# -------- Formulaires: traductions du DTML
security.declareProtected(ScoEntrepriseChange, "entreprise_create")


def entreprise_create():
    """Form. création entreprise"""
    H = [
        entreprise_header(page_title="Création d'une entreprise"),
        """<h2 class="entreprise_new">Création d'une entreprise</h2>""",
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("nom", {"size": 25, "title": "Nom de l'entreprise"}),
            (
                "adresse",
                {"size": 30, "title": "Adresse", "explanation": "(numéro, rue)"},
            ),
            ("codepostal", {"size": 8, "title": "Code Postal"}),
            ("ville", {"size": 30, "title": "Ville"}),
            ("pays", {"size": 30, "title": "Pays", "default": "France"}),
            (
                "localisation",
                {
                    "input_type": "menu",
                    "labels": ["Ile de France", "Province", "Etranger"],
                    "allowed_values": ["IDF", "Province", "Etranger"],
                },
            ),
            ("secteur", {"size": 30, "title": "Secteur d'activités"}),
            (
                "privee",
                {
                    "input_type": "menu",
                    "title": "Statut",
                    "labels": [
                        "Entreprise privee",
                        "Entreprise Publique",
                        "Association",
                    ],
                    "allowed_values": ["privee", "publique", "association"],
                },
            ),
            (
                "plus10salaries",
                {
                    "title": "Masse salariale",
                    "type": "integer",
                    "input_type": "menu",
                    "labels": [
                        "10 salariés ou plus",
                        "Moins de 10 salariés",
                        "Inconnue",
                    ],
                    "allowed_values": [1, 0, -1],
                },
            ),
            (
                "qualite_relation",
                {
                    "title": "Qualité relation IUT/Entreprise",
                    "input_type": "menu",
                    "default": "-1",
                    "labels": [
                        "Très bonne",
                        "Bonne",
                        "Moyenne",
                        "Mauvaise",
                        "Inconnue",
                    ],
                    "allowed_values": ["100", "75", "50", "25", "-1"],
                },
            ),
            ("contact_origine", {"size": 30, "title": "Origine du contact"}),
            (
                "note",
                {"input_type": "textarea", "rows": 3, "cols": 40, "title": "Note"},
            ),
        ),
        cancelbutton="Annuler",
        submitlabel="Ajouter cette entreprise",
        readonly=not current_user.has_permission(Permission.ScoEntrepriseChange),
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + entreprise_footer()
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL())
    else:
        sco_entreprises.do_entreprise_create(tf[2])
        return flask.redirect(scu.EntreprisesURL())


security.declareProtected(ScoEntrepriseView, "entreprise_edit")


def entreprise_edit(entreprise_id, start=1):
    """Form. edit entreprise"""
    authuser = current_user
    readonly = not authuser.has_permission(Permission.ScoEntrepriseChange)
    F = sco_entreprises.do_entreprise_list(args={"entreprise_id": entreprise_id})[0]
    H = [
        entreprise_header(page_title="Entreprise"),
        """<h2 class="entreprise">%(nom)s</h2>""" % F,
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("entreprise_id", {"default": entreprise_id, "input_type": "hidden"}),
            ("start", {"default": 1, "input_type": "hidden"}),
            (
                "date_creation",
                {"default": time.strftime("%Y-%m-%d"), "input_type": "hidden"},
            ),
            ("nom", {"size": 25, "title": "Nom de l'entreprise"}),
            (
                "adresse",
                {"size": 30, "title": "Adresse", "explanation": "(numéro, rue)"},
            ),
            ("codepostal", {"size": 8, "title": "Code Postal"}),
            ("ville", {"size": 30, "title": "Ville"}),
            ("pays", {"size": 30, "title": "Pays", "default": "France"}),
            (
                "localisation",
                {
                    "input_type": "menu",
                    "labels": ["Ile de France", "Province", "Etranger"],
                    "allowed_values": ["IDF", "Province", "Etranger"],
                },
            ),
            ("secteur", {"size": 30, "title": "Secteur d'activités"}),
            (
                "privee",
                {
                    "input_type": "menu",
                    "title": "Statut",
                    "labels": [
                        "Entreprise privee",
                        "Entreprise Publique",
                        "Association",
                    ],
                    "allowed_values": ["privee", "publique", "association"],
                },
            ),
            (
                "plus10salaries",
                {
                    "title": "Masse salariale",
                    "input_type": "menu",
                    "labels": [
                        "10 salariés ou plus",
                        "Moins de 10 salariés",
                        "Inconnue",
                    ],
                    "allowed_values": ["1", "0", "-1"],
                },
            ),
            (
                "qualite_relation",
                {
                    "title": "Qualité relation IUT/Entreprise",
                    "input_type": "menu",
                    "labels": [
                        "Très bonne",
                        "Bonne",
                        "Moyenne",
                        "Mauvaise",
                        "Inconnue",
                    ],
                    "allowed_values": ["100", "75", "50", "25", "-1"],
                },
            ),
            ("contact_origine", {"size": 30, "title": "Origine du contact"}),
            (
                "note",
                {"input_type": "textarea", "rows": 3, "cols": 40, "title": "Note"},
            ),
        ),
        cancelbutton="Annuler",
        initvalues=F,
        submitlabel="Modifier les valeurs",
        readonly=readonly,
    )

    if tf[0] == 0:
        H.append(tf[1])
        Cl = sco_entreprises.do_entreprise_correspondant_list(
            args={"entreprise_id": F["entreprise_id"]}
        )
        Cts = sco_entreprises.do_entreprise_contact_list(
            args={"entreprise_id": F["entreprise_id"]}
        )
        if not readonly:
            H.append(
                """<p>%s&nbsp;<a class="entreprise_delete" href="entreprise_delete?entreprise_id=%s">Supprimer cette entreprise</a> </p>"""
                % (
                    scu.icontag("delete_img", title="delete", border="0"),
                    F["entreprise_id"],
                )
            )
        if len(Cl):
            H.append(
                """<h3>%d correspondants dans l'entreprise %s (<a href="entreprise_correspondant_list?entreprise_id=%s">liste complète</a>) :</h3>
<ul>"""
                % (len(Cl), F["nom"], F["entreprise_id"])
            )
            for c in Cl:
                H.append(
                    """<li><a href="entreprise_correspondant_edit?entreprise_corresp_id=%s">"""
                    % c["entreprise_corresp_id"]
                )
                if c["nom"]:
                    nom = (
                        c["nom"]
                        .decode(SCO_ENCODING)
                        .lower()
                        .capitalize()
                        .encode(SCO_ENCODING)
                    )
                else:
                    nom = ""
                if c["prenom"]:
                    prenom = (
                        c["prenom"]
                        .decode(SCO_ENCODING)
                        .lower()
                        .capitalize()
                        .encode(SCO_ENCODING)
                    )
                else:
                    prenom = ""
                H.append("""%s %s</a>&nbsp;(%s)</li>""" % (nom, prenom, c["fonction"]))
            H.append("</ul>")
        if len(Cts):
            H.append(
                """<h3>%d contacts avec l'entreprise %s (<a href="entreprise_contact_list?entreprise_id=%s">liste complète</a>) :</h3><ul>"""
                % (len(Cts), F["nom"], F["entreprise_id"])
            )
            for c in Cts:
                H.append(
                    """<li><a href="entreprise_contact_edit?entreprise_contact_id=%s">%s</a>&nbsp;&nbsp;&nbsp;"""
                    % (c["entreprise_contact_id"], c["date"])
                )
                if c["type_contact"]:
                    H.append(c["type_contact"])
                if c["etudid"]:
                    etud = context.getEtudInfo(etudid=c["etudid"], filled=1)
                    if etud:
                        etud = etud[0]
                        H.append(
                            """<a href="%s/ficheEtud?etudid=%s">%s</a>"""
                            % (scu.ScoURL(), c["etudid"], etud["nomprenom"])
                        )
                if c["description"]:
                    H.append("(%s)" % c["description"])
                H.append("</li>")
            H.append("</ul>")
        return "\n".join(H) + entreprise_footer()
    elif tf[0] == -1:
        return flask.redirect(scu.EntreprisesURL() + "?start=" + str(start))
    else:
        sco_entreprises.do_entreprise_edit(tf[2])
        return flask.redirect(scu.EntreprisesURL() + "?start=" + str(start))
