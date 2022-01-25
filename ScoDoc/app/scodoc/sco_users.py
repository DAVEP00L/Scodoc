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

"""Fonctions sur les utilisateurs
"""

# Anciennement ZScoUsers.py, fonctions de gestion des données réécrite avec flask/SQLAlchemy
import re

from flask import url_for, g, request
from flask.templating import render_template
from flask_login import current_user


from app import db, Departement

from app.auth.models import Permission
from app.auth.models import User

from app.scodoc import html_sco_header
from app.scodoc import sco_etud
from app.scodoc import sco_excel
from app.scodoc import sco_preferences
from app.scodoc.gen_tables import GenTable
from app import log, cache
from app.scodoc.scolog import logdb
import app.scodoc.sco_utils as scu

from app.scodoc.sco_exceptions import (
    AccessDenied,
    ScoValueError,
)


# ---------------

# ---------------


def index_html(all_depts=False, with_inactives=False, format="html"):
    "gestion utilisateurs..."
    all_depts = int(all_depts)
    with_inactives = int(with_inactives)

    H = [html_sco_header.html_sem_header("Gestion des utilisateurs")]

    if current_user.has_permission(Permission.ScoUsersAdmin, g.scodoc_dept):
        H.append(
            '<p><a href="{}" class="stdlink">Ajouter un utilisateur</a>'.format(
                url_for("users.create_user_form", scodoc_dept=g.scodoc_dept)
            )
        )
        if current_user.is_administrator():
            H.append(
                '&nbsp;&nbsp; <a href="{}" class="stdlink">Importer des utilisateurs</a></p>'.format(
                    url_for("users.import_users_form", scodoc_dept=g.scodoc_dept)
                )
            )
        else:
            H.append(
                "&nbsp;&nbsp; Pour importer des utilisateurs en masse (via xlsx file) contactez votre administrateur scodoc."
            )
    if all_depts:
        checked = "checked"
    else:
        checked = ""
    if with_inactives:
        olds_checked = "checked"
    else:
        olds_checked = ""
    H.append(
        """<p><form name="f" action="%s" method="get">
    <input type="checkbox" name="all_depts" value="1" onchange="document.f.submit();" %s>Tous les départements</input>
    <input type="checkbox" name="with_inactives" value="1" onchange="document.f.submit();" %s>Avec anciens utilisateurs</input>
    </form></p>"""
        % (request.base_url, checked, olds_checked)
    )

    L = list_users(
        g.scodoc_dept,
        all_depts=all_depts,
        with_inactives=with_inactives,
        format=format,
        with_links=current_user.has_permission(Permission.ScoUsersAdmin, g.scodoc_dept),
    )
    if format != "html":
        return L
    H.append(L)

    F = html_sco_header.sco_footer()
    return "\n".join(H) + F


def list_users(
    dept,
    all_depts=False,  # tous les departements
    with_inactives=False,  # inclut les anciens utilisateurs (status "old")
    format="html",
    with_links=True,
):
    "List users, returns a table in the specified format"
    from app.scodoc.sco_permissions_check import can_handle_passwd

    if dept and not all_depts:
        users = get_user_list(dept=dept, with_inactives=with_inactives)
        comm = "dept. %s" % dept
    else:
        users = get_user_list(with_inactives=with_inactives)
        comm = "tous"
    if with_inactives:
        comm += ", avec anciens"
    comm = "(" + comm + ")"
    # -- Add some information and links:
    r = []
    for u in users:
        # Can current user modify this user ?
        can_modify = can_handle_passwd(u, allow_admindepts=True)

        d = u.to_dict()
        r.append(d)
        # Add links
        if with_links and can_modify:
            target = url_for(
                "users.user_info_page", scodoc_dept=dept, user_name=u.user_name
            )
            d["_user_name_target"] = target
            d["_nom_target"] = target
            d["_prenom_target"] = target

        # Hide passwd modification date (depending on visitor's permission)
        if not can_modify:
            d["date_modif_passwd"] = "(non visible)"

    columns_ids = [
        "user_name",
        "nom_fmt",
        "prenom_fmt",
        "email",
        "dept",
        "roles_string",
        "date_expiration",
        "date_modif_passwd",
        "passwd_temp",
        "status_txt",
    ]
    # Seul l'admin peut voir les dates de dernière connexion
    if current_user.is_administrator():
        columns_ids.append("last_seen")
    title = "Utilisateurs définis dans ScoDoc"
    tab = GenTable(
        rows=r,
        columns_ids=columns_ids,
        titles={
            "user_name": "Login",
            "nom_fmt": "Nom",
            "prenom_fmt": "Prénom",
            "email": "Mail",
            "dept": "Dept.",
            "roles_string": "Rôles",
            "date_expiration": "Expiration",
            "date_modif_passwd": "Modif. mot de passe",
            "last_seen": "Dernière cnx.",
            "passwd_temp": "Temp.",
            "status_txt": "Etat",
        },
        caption=title,
        page_title="title",
        html_title="""<h2>%d utilisateurs %s</h2>
        <p class="help">Cliquer sur un nom pour changer son mot de passe</p>"""
        % (len(r), comm),
        html_class="table_leftalign list_users",
        html_with_td_classes=True,
        html_sortable=True,
        base_url="%s?all_depts=%s" % (request.base_url, 1 if all_depts else 0),
        pdf_link=False,  # table is too wide to fit in a paper page => disable pdf
        preferences=sco_preferences.SemPreferences(),
    )

    return tab.make_page(format=format, with_html_headers=False)


def get_user_list(dept=None, with_inactives=False):
    """Returns list of users.
    If dept, select users from this dept,
    else return all users.
    """
    # was get_userlist
    q = User.query
    if dept is not None:
        q = q.filter_by(dept=dept)
    if not with_inactives:
        q = q.filter_by(active=True)
    return q.order_by(User.nom, User.user_name).all()


def _user_list(user_name):
    "return user as a dict"
    u = User.query.filter_by(user_name=user_name).first()
    if u:
        return u.to_dict()
    else:
        return None


@cache.memoize(timeout=50)  # seconds
def user_info(user_name_or_id=None, user=None):
    """Dict avec infos sur l'utilisateur (qui peut ne pas etre dans notre base).
    Si user_name est specifie (string ou id), interroge la BD. Sinon, user doit etre une instance
    de User.
    """
    if user_name_or_id is not None:
        if isinstance(user_name_or_id, int):
            u = User.query.filter_by(id=user_name_or_id).first()
        else:
            u = User.query.filter_by(user_name=user_name_or_id).first()
        if u:
            user_name = u.user_name
            info = u.to_dict()
        else:
            info = None
            user_name = "inconnu"
    else:
        info = user.to_dict()
        user_name = user.user_name

    if not info:
        # special case: user is not in our database
        return {
            "user_name": user_name,
            "nom": user_name,
            "prenom": "",
            "email": "",
            "dept": "",
            "nomprenom": user_name,
            "prenomnom": user_name,
            "prenom_fmt": "",
            "nom_fmt": user_name,
            "nomcomplet": user_name,
            "nomplogin": user_name,
            # "nomnoacc": scu.suppress_accents(user_name),
            "passwd_temp": 0,
            "status": "",
            "date_expiration": None,
        }
    else:
        # Ensure we never publish password hash
        if "password_hash" in info:
            del info["password_hash"]
        return info


def check_modif_user(
    edit,
    enforce_optionals=False,
    user_name="",
    nom="",
    prenom="",
    email="",
    dept="",
    roles=[],
):
    """Vérifie que cet utilisateur peut être créé (edit=0) ou modifié (edit=1)
    Cherche homonymes.
    returns (ok, msg)
        - ok : si vrai, peut continuer avec ces parametres
            (si ok est faux, l'utilisateur peut quand même forcer la creation)
        - msg: message warning à presenter à l'utilisateur
    """
    MSG_OPT = """<br/>Attention: (vous pouvez forcer l'opération en cochant "<em>Ignorer les avertissements</em>" en bas de page)"""
    # ce login existe ?
    user = _user_list(user_name)
    if edit and not user:  # safety net, le user_name ne devrait pas changer
        return False, "identifiant %s inexistant" % user_name
    if not edit and user:
        return False, "identifiant %s déjà utilisé" % user_name
    if not user_name or not nom or not prenom:
        return False, "champ requis vide"
    if not re.match(r"^[a-zA-Z0-9@\\\-_\\\.]*$", user_name):
        return (
            False,
            "identifiant '%s' invalide (pas d'accents ni de caractères spéciaux)"
            % user_name,
        )
    if enforce_optionals and len(user_name) > 64:
        return False, "identifiant '%s' trop long (64 caractères)" % user_name
    if enforce_optionals and len(nom) > 64:
        return False, "nom '%s' trop long (64 caractères)" % nom + MSG_OPT
    if enforce_optionals and len(prenom) > 64:
        return False, "prenom '%s' trop long (64 caractères)" % prenom + MSG_OPT
    # check that tha same user_name has not already been described in this import
    if not email:
        return False, "vous devriez indiquer le mail de l'utilisateur créé !"
    if len(email) > 120:
        return False, "email '%s' trop long (120 caractères)" % email
    if not re.fullmatch(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", email):
        return False, "l'adresse mail semble incorrecte"
    # check département
    if (
        enforce_optionals
        and dept != ""
        and Departement.query.filter_by(acronym=dept).first() is None
    ):
        return False, "département '%s' inexistant" % dept + MSG_OPT
    if enforce_optionals and not roles:
        return False, "aucun rôle sélectionné, êtes vous sûr ?" + MSG_OPT
    # Unicité du mail
    users_with_this_mail = User.query.filter_by(email=email).all()
    if edit:  # modification
        if email != user["email"] and len(users_with_this_mail) > 0:
            return False, "un autre utilisateur existe déjà avec cette adresse mail"
    else:  # création utilisateur
        if len(users_with_this_mail) > 0:
            return False, "un autre utilisateur existe déjà avec cette adresse mail"

    # ok
    # Des noms/prénoms semblables existent ?
    nom = nom.lower().strip()
    prenom = prenom.lower().strip()
    similar_users = User.query.filter(
        User.nom.ilike(nom), User.prenom.ilike(prenom)
    ).all()
    if edit:
        minmatch = 1
    else:
        minmatch = 0
    if enforce_optionals and len(similar_users) > minmatch:
        return (
            False,
            "des utilisateurs proches existent: "
            + ", ".join(
                [
                    "%s %s (pseudo=%s)" % (x.prenom, x.nom, x.user_name)
                    for x in similar_users
                ]
            )
            + MSG_OPT,
        )
    # Roles ?
    return True, ""


def user_edit(user_name, vals):
    """Edit the user specified by user_name
    (ported from Zope to SQLAlchemy, hence strange !)
    """
    u = User.query.filter_by(user_name=user_name).first()
    if not u:
        raise ScoValueError("Invalid user_name")
    u.from_dict(vals)
    db.session.add(u)
    db.session.commit()
