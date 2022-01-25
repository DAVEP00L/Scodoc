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

"""Recherche d'étudiants
"""
import flask
from flask import url_for, g, request
from flask_login import current_user

import app
from app.models import Departement
import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.gen_tables import GenTable
from app.scodoc import html_sco_header
from app.scodoc import sco_etud
from app.scodoc import sco_groups
from app.scodoc.sco_permissions import Permission
from app.scodoc import sco_preferences


def form_search_etud(
    dest_url=None,
    parameters=None,
    parameters_keys=None,
    title="Rechercher un étudiant par nom&nbsp;: ",
    add_headers=False,  # complete page
):
    "form recherche par nom"
    H = []
    if title:
        H.append("<h2>%s</h2>" % title)
    H.append(
        f"""<form action="{ url_for("scolar.search_etud_in_dept", scodoc_dept=g.scodoc_dept) }" method="POST">
    <b>{title}</b>
    <input type="text" name="expnom" width="12" spellcheck="false" value="">
    <input type="submit" value="Chercher">
    <br/>(entrer une partie du nom)
    """
    )
    if dest_url:
        H.append('<input type="hidden" name="dest_url" value="%s"/>' % dest_url)
    if parameters:
        for param in parameters.keys():
            H.append(
                '<input type="hidden" name="%s" value="%s"/>'
                % (param, parameters[param])
            )
        H.append(
            '<input type="hidden" name="parameters_keys" value="%s"/>'
            % (",".join(parameters.keys()))
        )
    elif parameters_keys:
        if request.method == "POST":
            vals = request.form
        elif request.method == "GET":
            vals = request.args
        else:
            vals = {}
        for key in parameters_keys.split(","):
            v = vals.get(key, False)
            if v:
                H.append('<input type="hidden" name="%s" value="%s"/>' % (key, v))
        H.append(
            '<input type="hidden" name="parameters_keys" value="%s"/>' % parameters_keys
        )
    H.append("</form>")

    if add_headers:
        return (
            html_sco_header.sco_header(page_title="Choix d'un étudiant")
            + "\n".join(H)
            + html_sco_header.sco_footer()
        )
    else:
        return "\n".join(H)


def search_etud_in_dept(expnom=""):
    """Page recherche d'un etudiant.

    Affiche la fiche de l'étudiant, ou, si la recherche donne plusieurs résultats,
    la liste des étudiants correspondants.
    Appelée par:
    - boite de recherche barre latérale gauche.
    - choix d'un étudiant à inscrire (en POST avec dest_url  et parameters_keys)

    Args:
        expnom: string, regexp sur le nom ou un code_nip ou un etudid
    """
    if isinstance(expnom, int) or len(expnom) > 1:
        try:
            etudid = int(expnom)
        except ValueError:
            etudid = None
        if etudid is not None:
            etuds = sco_etud.get_etud_info(filled=True, etudid=expnom)
        if (etudid is None) or len(etuds) != 1:
            expnom_str = str(expnom)
            if scu.is_valid_code_nip(expnom_str):
                etuds = search_etuds_infos(code_nip=expnom_str)
            else:
                etuds = search_etuds_infos(expnom=expnom_str)
    else:
        etuds = []  # si expnom est trop court, n'affiche rien

    if request.method == "POST":
        vals = request.form
    elif request.method == "GET":
        vals = request.args
    else:
        vals = {}

    url_args = {"scodoc_dept": g.scodoc_dept}
    if "dest_url" in vals:
        endpoint = vals["dest_url"]
    else:
        endpoint = "scolar.ficheEtud"
    if "parameters_keys" in vals:
        for key in vals["parameters_keys"].split(","):
            url_args[key] = vals[key]

    if len(etuds) == 1:
        # va directement a la fiche
        url_args["etudid"] = etuds[0]["etudid"]
        return flask.redirect(url_for(endpoint, **url_args))

    H = [
        html_sco_header.sco_header(
            page_title="Recherche d'un étudiant",
            no_side_bar=False,
            init_qtip=True,
            javascripts=["js/etud_info.js"],
        )
    ]
    if len(etuds) == 0 and len(etuds) <= 1:
        H.append("""<h2>chercher un étudiant:</h2>""")
    else:
        H.append(
            f"""<h2>{len(etuds)} résultats pour "<tt>{expnom}</tt>": choisissez un étudiant:</h2>"""
        )
    H.append(
        form_search_etud(
            dest_url=endpoint,
            parameters=vals.get("parameters"),
            parameters_keys=vals.get("parameters_keys"),
            title="Autre recherche",
        )
    )
    if len(etuds) > 0:
        # Choix dans la liste des résultats:
        for e in etuds:
            url_args["etudid"] = e["etudid"]
            target = url_for(endpoint, **url_args)
            e["_nomprenom_target"] = target
            e["inscription_target"] = target
            e["_nomprenom_td_attrs"] = 'id="%s" class="etudinfo"' % (e["etudid"])
            sco_groups.etud_add_group_infos(e, e["cursem"])

        tab = GenTable(
            columns_ids=("nomprenom", "code_nip", "inscription", "groupes"),
            titles={
                "nomprenom": "Etudiant",
                "code_nip": "NIP",
                "inscription": "Inscription",
                "groupes": "Groupes",
            },
            rows=etuds,
            html_sortable=True,
            html_class="table_leftalign",
            preferences=sco_preferences.SemPreferences(),
        )
        H.append(tab.html())
        if len(etuds) > 20:  # si la page est grande
            H.append(
                form_search_etud(
                    dest_url=endpoint,
                    parameters=vals.get("parameters"),
                    parameters_keys=vals.get("parameters_keys"),
                    title="Autre recherche",
                )
            )
    else:
        H.append('<h2 style="color: red;">Aucun résultat pour "%s".</h2>' % expnom)
    H.append(
        """<p class="help">La recherche porte sur tout ou partie du NOM ou du NIP de l'étudiant. Saisir au moins deux caractères.</p>"""
    )
    return "\n".join(H) + html_sco_header.sco_footer()


# Was chercheEtudsInfo()
def search_etuds_infos(expnom=None, code_nip=None):
    """recherche les étudiants correspondants à expnom ou au code_nip
    et ramene liste de mappings utilisables en DTML.
    """
    may_be_nip = scu.is_valid_code_nip(expnom)
    cnx = ndb.GetDBConnexion()
    if expnom and not may_be_nip:
        expnom = expnom.upper()  # les noms dans la BD sont en uppercase
        etuds = sco_etud.etudident_list(cnx, args={"nom": expnom}, test="~")
    else:
        code_nip = code_nip or expnom
        if code_nip:
            etuds = sco_etud.etudident_list(cnx, args={"code_nip": str(code_nip)})
        else:
            etuds = []
    sco_etud.fill_etuds_info(etuds)
    return etuds


def search_etud_by_name(term: str) -> list:
    """Recherche noms étudiants par début du nom, pour autocomplete
    Accepte aussi un début de code NIP (au moins 6 caractères)
    Renvoie une liste de dicts
         { "label" : "<nip> <nom> <prenom>", "value" : etudid }
    """
    may_be_nip = scu.is_valid_code_nip(term)
    # term = term.upper() # conserve les accents
    term = term.upper()
    if (
        not scu.ALPHANUM_EXP.match(term)  #  n'autorise pas les caractères spéciaux
        and not may_be_nip
    ):
        data = []
    else:
        if may_be_nip:
            r = ndb.SimpleDictFetch(
                """SELECT nom, prenom, code_nip
                FROM identite
                WHERE
                dept_id = %(dept_id)s 
                AND code_nip LIKE %(beginning)s 
                ORDER BY nom
                """,
                {"beginning": term + "%", "dept_id": g.scodoc_dept_id},
            )
            data = [
                {
                    "label": "%s %s %s"
                    % (x["code_nip"], x["nom"], sco_etud.format_prenom(x["prenom"])),
                    "value": x["code_nip"],
                }
                for x in r
            ]
        else:
            r = ndb.SimpleDictFetch(
                """SELECT id AS etudid, nom, prenom
                FROM identite
                WHERE 
                dept_id = %(dept_id)s 
                AND nom LIKE %(beginning)s
                ORDER BY nom
                """,
                {"beginning": term + "%", "dept_id": g.scodoc_dept_id},
            )

            data = [
                {
                    "label": "%s %s" % (x["nom"], sco_etud.format_prenom(x["prenom"])),
                    "value": x["etudid"],
                }
                for x in r
            ]
    return data


# ---------- Recherche sur plusieurs département


def search_etud_in_accessible_depts(expnom=None, code_nip=None):
    """
    result is a list of (sorted) etuds, one list per dept.
    """
    result = []
    accessible_depts = []
    depts = Departement.query.filter_by(visible=True).all()
    for dept in depts:
        if current_user.has_permission(Permission.ScoView, dept=dept.acronym):
            if expnom or code_nip:
                accessible_depts.append(dept.acronym)
                app.set_sco_dept(dept.acronym)
                etuds = search_etuds_infos(expnom=expnom, code_nip=code_nip)
            else:
                etuds = []
            result.append(etuds)
    return result, accessible_depts


def table_etud_in_accessible_depts(expnom=None):
    """
    Page avec table étudiants trouvés, dans tous les departements.
    Attention: nous sommes ici au niveau de ScoDoc, pas dans un département
    """
    result, accessible_depts = search_etud_in_accessible_depts(expnom=expnom)
    H = [
        """<div class="table_etud_in_accessible_depts">""",
        """<h3>Recherche multi-département de "<tt>%s</tt>"</h3>""" % expnom,
    ]
    for etuds in result:
        if etuds:
            dept_id = etuds[0]["dept"]
            # H.append('<h3>Département %s</h3>' % DeptId)
            for e in etuds:
                e["_nomprenom_target"] = url_for(
                    "scolar.ficheEtud", scodoc_dept=dept_id, etudid=e["etudid"]
                )
                e["_nomprenom_td_attrs"] = 'id="%s" class="etudinfo"' % (e["etudid"])

            tab = GenTable(
                titles={"nomprenom": "Etudiants en " + dept_id},
                columns_ids=("nomprenom",),
                rows=etuds,
                html_sortable=True,
                html_class="table_leftalign",
            )

            H.append('<div class="table_etud_in_dept">')
            H.append(tab.html())
            H.append("</div>")
    if len(accessible_depts) > 1:
        ss = "s"
    else:
        ss = ""
    H.append(
        f"""<p>(recherche menée dans le{ss} département{ss}: 
        {", ".join(accessible_depts)})
        </p>
        <p>
            <a href="{url_for("scodoc.index")}" class="stdlink">Retour à l'accueil</a>
        </p>
        </div>
        """
    )
    return (
        html_sco_header.scodoc_top_html_header(page_title="Choix d'un étudiant")
        + "\n".join(H)
        + html_sco_header.standard_html_footer()
    )


def search_inscr_etud_by_nip(code_nip, format="json"):
    """Recherche multi-departement d'un étudiant par son code NIP
    Seuls les départements accessibles par l'utilisateur sont cherchés.

    Renvoie une liste des inscriptions de l'étudiants dans tout ScoDoc:
    code_nip, nom, prenom, civilite_str, dept, formsemestre_id, date_debut_sem, date_fin_sem
    """
    result, _ = search_etud_in_accessible_depts(code_nip=code_nip)

    T = []
    for etuds in result:
        if etuds:
            DeptId = etuds[0]["dept"]
            for e in etuds:
                for sem in e["sems"]:
                    T.append(
                        {
                            "dept": DeptId,
                            "etudid": e["etudid"],
                            "code_nip": e["code_nip"],
                            "civilite_str": e["civilite_str"],
                            "nom": e["nom"],
                            "prenom": e["prenom"],
                            "formsemestre_id": sem["formsemestre_id"],
                            "date_debut_iso": sem["date_debut_iso"],
                            "date_fin_iso": sem["date_fin_iso"],
                        }
                    )

    columns_ids = (
        "dept",
        "etudid",
        "code_nip",
        "civilite_str",
        "nom",
        "prenom",
        "formsemestre_id",
        "date_debut_iso",
        "date_fin_iso",
    )
    tab = GenTable(columns_ids=columns_ids, rows=T)

    return tab.make_page(format=format, with_html_headers=False, publish=True)
