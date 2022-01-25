# -*- mode: python -*-
# -*- coding: utf-8 -*-

##############################################################################
#
# ScoDoc
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
Module users: interface gestion utilisateurs
ré-écriture pour Flask ScoDoc7 / ZScoUsers.py

Vues s'appuyant sur auth et sco_users

Emmanuel Viennet, 2021
"""
import datetime
import re
from enum import auto, IntEnum
from xml.etree import ElementTree

import flask
from flask import g, url_for, request, current_app, flash
from flask import redirect, render_template

from flask_login import current_user
from wtforms import HiddenField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError, EqualTo

from app import db
from app.auth.forms import DeactivateUserForm
from app.auth.models import Permission
from app.auth.models import User
from app.auth.models import Role
from app.auth.models import UserRole
from app.auth.models import is_valid_password
from app.email import send_email
from app.models import Departement

from app.decorators import (
    scodoc,
    scodoc7func,
    permission_required,
)

from app.scodoc import html_sco_header, sco_import_users, sco_excel
from app.scodoc import sco_users
from app.scodoc import sco_utils as scu
from app.scodoc import sco_xml
from app import log
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
from app.scodoc.sco_import_users import generate_password
from app.scodoc.sco_permissions_check import can_handle_passwd
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message
from app.views import users_bp as bp
from flask_wtf import FlaskForm

_ = lambda x: x  # sans babel
_l = _


class ChangePasswordForm(FlaskForm):
    user_name = HiddenField()
    old_password = PasswordField(_l("Identifiez-vous"))
    new_password = PasswordField(_l("Nouveau mot de passe"))
    bis_password = PasswordField(
        _l("Répéter"),
        validators=[
            EqualTo(
                "new_password",
                message="Les deux saisies sont " "différentes, recommencez",
            ),
        ],
    )
    email = StringField(
        _l("Email"),
        validators=[
            DataRequired(),
            Email(message="adresse email invalide, recommencez"),
        ],
    )
    submit = SubmitField()
    cancel = SubmitField("Annuler")

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.strip()).first()
        if user is not None and self.user_name.data != user.user_name:
            raise ValidationError(
                _("Cette adresse e-mail est déjà attribuée à un autre compte")
            )

    def validate_new_password(self, new_password):
        if new_password.data != "" and not is_valid_password(new_password.data):
            raise ValidationError(f"Mot de passe trop simple, recommencez")

    def validate_old_password(self, old_password):
        if not current_user.check_password(old_password.data):
            raise ValidationError("Mot de passe actuel incorrect, ré-essayez")


class Mode(IntEnum):
    WELCOME_AND_CHANGE_PASSWORD = auto()
    WELCOME_ONLY = auto()
    SILENT = auto()


@bp.route("/")
@bp.route("/index_html")
@scodoc
@permission_required(Permission.ScoUsersView)
@scodoc7func
def index_html(all_depts=False, with_inactives=False, format="html"):
    return sco_users.index_html(
        all_depts=all_depts,
        with_inactives=with_inactives,
        format=format,
    )


@bp.route("/user_info")
@scodoc
@permission_required(Permission.ScoUsersView)
@scodoc7func
def user_info(user_name, format="json"):
    info = sco_users.user_info(user_name)
    return scu.sendResult(info, name="user", format=format)


@bp.route("/create_user_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoUsersAdmin)
@scodoc7func
def create_user_form(user_name=None, edit=0, all_roles=1):
    "form. création ou edition utilisateur"
    auth_dept = current_user.dept
    auth_username = current_user.user_name
    from_mail = current_user.email
    initvalues = {}
    edit = int(edit)
    all_roles = int(all_roles)
    H = [
        html_sco_header.sco_header(
            bodyOnLoad="init_tf_form('')",
            javascripts=["js/user_form.js"],
        )
    ]
    F = html_sco_header.sco_footer()
    if edit:
        if not user_name:
            raise ValueError("missing argument: user_name")
        u = User.query.filter_by(user_name=user_name).first()
        if not u:
            raise ScoValueError("utilisateur inexistant")
        initvalues = u.to_dict()
        H.append("<h2>Modification de l'utilisateur %s</h2>" % user_name)
    else:
        H.append("<h2>Création d'un utilisateur</h2>")

    is_super_admin = False
    if current_user.has_permission(Permission.ScoSuperAdmin, g.scodoc_dept):
        H.append("""<p class="warning">Vous êtes super administrateur !</p>""")
        is_super_admin = True

    if all_roles:
        # tous sauf SuperAdmin
        standard_roles = [
            r
            for r in Role.query.all()
            if r.permissions != Permission.ALL_PERMISSIONS[0]
        ]
    else:
        # Les rôles standards créés à l'initialisation de ScoDoc:
        standard_roles = [
            Role.get_named_role(r) for r in ("Ens", "Secr", "Admin", "RespPe")
        ]
    # Départements auxquels ont peut associer des rôles via ce dialogue:
    #    si  SuperAdmin, tous les rôles standards dans tous les départements
    #    sinon, les départements dans lesquels l'utilisateur a le droit
    if is_super_admin:
        log("create_user_form called by %s (super admin)" % (current_user.user_name,))
        dept_ids = [d.acronym for d in Departement.query.all()]
    else:
        # Si on n'est pas SuperAdmin, liste les départements dans lesquels on a la
        # permission ScoUsersAdmin
        dept_ids = sorted(
            set(
                [
                    x.dept
                    for x in UserRole.query.filter_by(user=current_user)
                    if x.role.has_permission(Permission.ScoUsersAdmin) and x.dept
                ]
            )
        )

    editable_roles_set = {(r, dept) for r in standard_roles for dept in dept_ids}
    #
    if not edit:
        submitlabel = "Créer utilisateur"
        orig_roles = set()
    else:
        submitlabel = "Modifier utilisateur"
        if "roles_string" in initvalues:
            initvalues["roles"] = initvalues["roles_string"].split(",")
        else:
            initvalues["roles"] = []
        if "date_expiration" in initvalues:
            initvalues["date_expiration"] = (
                u.date_expiration.strftime("%d/%m/%Y") if u.date_expiration else ""
            )
        initvalues["status"] = "" if u.active else "old"
        orig_roles = {  # set des roles existants avant édition
            UserRole.role_dept_from_string(role_dept)
            for role_dept in initvalues["roles"]
            if role_dept
        }
        if not initvalues["active"]:
            editable_roles_set = set()  # can't change roles of a disabled user
    editable_roles_strings = {
        r.name + "_" + (dept or "") for (r, dept) in editable_roles_set
    }
    orig_roles_strings = {r.name + "_" + (dept or "") for (r, dept) in orig_roles}
    # add existing user roles
    displayed_roles = list(editable_roles_set.union(orig_roles))
    displayed_roles.sort(key=lambda x: (x[1] or "", x[0].name or ""))
    displayed_roles_strings = [
        r.name + "_" + (dept or "") for (r, dept) in displayed_roles
    ]
    displayed_roles_labels = [f"{dept}: {r.name}" for (r, dept) in displayed_roles]
    disabled_roles = {}  # pour desactiver les roles que l'on ne peut pas editer
    for i in range(len(displayed_roles_strings)):
        if displayed_roles_strings[i] not in editable_roles_strings:
            disabled_roles[i] = True

    descr = [
        ("edit", {"input_type": "hidden", "default": edit}),
        ("nom", {"title": "Nom", "size": 20, "allow_null": False}),
        ("prenom", {"title": "Prénom", "size": 20, "allow_null": False}),
    ]
    if current_user.user_name != user_name:
        # no one can change its own status
        descr.append(
            (
                "status",
                {
                    "title": "Statut",
                    "input_type": "radio",
                    "labels": ("actif", "ancien"),
                    "allowed_values": ("", "old"),
                },
            )
        )
    if not edit:
        descr += [
            (
                "user_name",
                {
                    "title": "Pseudo (login)",
                    "size": 20,
                    "allow_null": False,
                    "explanation": "nom utilisé pour la connexion. Doit être unique parmi tous les utilisateurs. "
                    "Lettres ou chiffres uniquement.",
                },
            ),
            ("formsemestre_id", {"input_type": "hidden"}),
            (
                "password",
                {
                    "title": "Mot de passe",
                    "input_type": "password",
                    "size": 14,
                    "allow_null": True,
                    "explanation": "optionnel, l'utilisateur pourra le saisir avec son mail",
                },
            ),
            (
                "password2",
                {
                    "title": "Confirmer mot de passe",
                    "input_type": "password",
                    "size": 14,
                    "allow_null": True,
                },
            ),
        ]
    else:
        descr += [
            (
                "user_name",
                {"input_type": "hidden", "default": initvalues["user_name"]},
            ),
            ("user_name", {"input_type": "hidden", "default": initvalues["user_name"]}),
        ]
    descr += [
        (
            "email",
            {
                "title": "e-mail",
                "input_type": "text",
                "explanation": "requis, doit fonctionner",
                "size": 20,
                "allow_null": False,
            },
        )
    ]
    if not edit:  # options création utilisateur
        descr += [
            (
                "welcome",
                {
                    "title": "Message d'accueil",
                    "input_type": "checkbox",
                    "explanation": "Envoie un mail d'accueil à l'utilisateur.",
                    "labels": ("",),
                    "allowed_values": ("1",),
                    "default": "1",
                },
            ),
            (
                "reset_password",
                {
                    "title": "",
                    "input_type": "checkbox",
                    "explanation": "indiquer par mail de changer le mot de passe initial",
                    "labels": ("",),
                    "allowed_values": ("1",),
                    "default": "1",
                    # "attributes": ["style='margin-left:20pt'"],
                },
            ),
        ]

    if not auth_dept:
        # si auth n'a pas de departement (admin global)
        # propose de choisir le dept du nouvel utilisateur
        # sinon, il sera créé dans le même département que auth
        descr.append(
            (
                "dept",
                {
                    "title": "Département",
                    "input_type": "text",
                    "size": 12,
                    "allow_null": True,
                    "explanation": """département d\'appartenance de l\'utilisateur (s'il s'agit d'un administrateur, laisser vide si vous voulez qu'il puisse créer des utilisateurs dans d'autres départements)""",
                },
            )
        )
        can_choose_dept = True
    else:
        can_choose_dept = False
        if edit:
            descr.append(
                (
                    "d",
                    {
                        "input_type": "separator",
                        "title": "L'utilisateur appartient au département %s"
                        % auth_dept,
                    },
                )
            )
        else:
            descr.append(
                (
                    "d",
                    {
                        "input_type": "separator",
                        "title": "L'utilisateur  sera crée dans le département %s"
                        % auth_dept,
                    },
                )
            )

    descr += [
        (
            "date_expiration",
            {
                "title": "Date d'expiration",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a, laisser vide si pas de limite",
                "size": 9,
                "allow_null": True,
            },
        ),
        (
            "roles",
            {
                "title": "Rôles",
                "input_type": "checkbox",
                "vertical": True,
                "labels": displayed_roles_labels,
                "allowed_values": displayed_roles_strings,
                "disabled_items": disabled_roles,
            },
        ),
        (
            "force",
            {
                "title": "Ignorer les avertissements",
                "input_type": "checkbox",
                "explanation": "passer outre les avertissements (homonymes, etc)",
                "labels": ("",),
                "allowed_values": ("1",),
            },
        ),
    ]
    vals = scu.get_request_args()
    if "tf_submitted" in vals and not "roles" in vals:
        vals["roles"] = []
    if "tf_submitted" in vals:
        # Ajoute roles existants mais non modifiables (disabled dans le form)
        vals["roles"] = list(
            set(vals["roles"]).union(orig_roles_strings - editable_roles_strings)
        )

    tf = TrivialFormulator(
        request.base_url,
        vals,
        descr,
        initvalues=initvalues,
        submitlabel=submitlabel,
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + F
    elif tf[0] == -1:
        return flask.redirect(scu.UsersURL())
    else:
        vals = tf[2]
        roles = set(vals["roles"]).intersection(editable_roles_strings)
        if "edit" in vals:
            edit = int(vals["edit"])
        else:
            edit = 0
        try:
            force = int(vals["force"][0])
        except (IndexError, ValueError, TypeError):
            force = 0

        if edit:
            user_name = initvalues["user_name"]
        else:
            user_name = vals["user_name"]
        # ce login existe ?
        err = None
        users = sco_users._user_list(user_name)
        if edit and not users:  # safety net, le user_name ne devrait pas changer
            err = "identifiant %s inexistant" % user_name
        if not edit and users:
            err = "identifiant %s déjà utilisé" % user_name
        if err:
            H.append(tf_error_message("""Erreur: %s""" % err))
            return "\n".join(H) + "\n" + tf[1] + F
        ok, msg = sco_users.check_modif_user(
            edit,
            enforce_optionals=not force,
            user_name=user_name,
            nom=vals["nom"],
            prenom=vals["prenom"],
            email=vals["email"],
            dept=vals.get("dept", auth_dept),
            roles=vals["roles"],
        )
        if not ok:
            H.append(tf_error_message(msg))
            return "\n".join(H) + "\n" + tf[1] + F

        if "date_expiration" in vals:
            try:
                if vals["date_expiration"]:
                    vals["date_expiration"] = datetime.datetime.strptime(
                        vals["date_expiration"], "%d/%m/%Y"
                    )
                    if vals["date_expiration"] < datetime.datetime.now():
                        H.append(tf_error_message("date expiration passée"))
                        return "\n".join(H) + "\n" + tf[1] + F
                else:
                    vals["date_expiration"] = None
            except ValueError:
                H.append(tf_error_message("date expiration invalide"))
                return "\n".join(H) + "\n" + tf[1] + F

        if edit:  # modif utilisateur (mais pas password ni user_name !)
            if (not can_choose_dept) and "dept" in vals:
                del vals["dept"]
            if "password" in vals:
                del vals["passwordd"]
            if "date_modif_passwd" in vals:
                del vals["date_modif_passwd"]
            if "user_name" in vals:
                del vals["user_name"]
            if (current_user.user_name == user_name) and "status" in vals:
                del vals["status"]  # no one can't change its own status
            if "status" in vals:
                vals["active"] = vals["status"] == ""
            # traitement des roles: ne doit pas affecter les roles
            # que l'on en controle pas:
            for role in orig_roles_strings:  # { "Ens_RT", "Secr_CJ", ... }
                if role and not role in editable_roles_strings:
                    roles.add(role)

            vals["roles_string"] = ",".join(roles)

            # ok, edit
            log("sco_users: editing %s by %s" % (user_name, current_user.user_name))
            log("sco_users: previous_values=%s" % initvalues)
            log("sco_users: new_values=%s" % vals)
            sco_users.user_edit(user_name, vals)
            return flask.redirect(
                "user_info_page?user_name=%s&head_message=Utilisateur %s modifié"
                % (user_name, user_name)
            )
        else:  # creation utilisateur
            vals["roles_string"] = ",".join(vals["roles"])
            # check identifiant
            if not re.match(r"^[a-zA-Z0-9@\\\-_\\\.]+$", vals["user_name"]):
                msg = tf_error_message(
                    "identifiant invalide (pas d'accents ni de caractères spéciaux)"
                )
                return "\n".join(H) + msg + "\n" + tf[1] + F
            # Traitement initial (mode) : 3 cas
            # cf énumération Mode
            # A: envoi de welcome + procedure de reset
            # B: envoi de welcome seulement (mot de passe saisie dans le formulaire)
            # C: Aucun envoi (mot de passe saisi dans le formulaire)
            if vals["welcome:list"] == "1":
                if vals["reset_password:list"] == "1":
                    mode = Mode.WELCOME_AND_CHANGE_PASSWORD
                else:
                    mode = Mode.WELCOME_ONLY
            else:
                mode = Mode.SILENT

            # check passwords
            if mode == Mode.WELCOME_AND_CHANGE_PASSWORD:
                vals["password"] = generate_password()
            else:
                if vals["password"]:
                    if vals["password"] != vals["password2"]:
                        msg = tf_error_message(
                            """Les deux mots de passes ne correspondent pas !"""
                        )
                        return "\n".join(H) + msg + "\n" + tf[1] + F
                    if not is_valid_password(vals["password"]):
                        msg = tf_error_message(
                            """Mot de passe trop simple, recommencez !"""
                        )
                        return "\n".join(H) + msg + "\n" + tf[1] + F
            if not can_choose_dept:
                vals["dept"] = auth_dept
            # ok, go
            log(
                "sco_users: new_user %s by %s"
                % (vals["user_name"], current_user.user_name)
            )
            u = User()
            u.from_dict(vals, new_user=True)
            db.session.add(u)
            db.session.commit()
            # envoi éventuel d'un message
            if mode == Mode.WELCOME_AND_CHANGE_PASSWORD or mode == Mode.WELCOME_ONLY:
                if mode == Mode.WELCOME_AND_CHANGE_PASSWORD:
                    token = u.get_reset_password_token()
                else:
                    token = None
                send_email(
                    "[ScoDoc] Création de votre compte",
                    sender=from_mail,  # current_app.config["ADMINS"][0],
                    recipients=[u.email],
                    text_body=render_template("email/welcome.txt", user=u, token=token),
                    html_body=render_template(
                        "email/welcome.html", user=u, token=token
                    ),
                )

            return flask.redirect(
                url_for(
                    "users.user_info_page",
                    scodoc_dept=g.scodoc_dept,
                    user_name=user_name,
                    head_message="Nouvel utilisateur créé",
                )
            )


@bp.route("/import_users_generate_excel_sample")
@scodoc
@permission_required(Permission.ScoUsersAdmin)
@scodoc7func
def import_users_generate_excel_sample():
    "une feuille excel pour importation utilisateurs"
    data = sco_import_users.generate_excel_sample()
    return scu.send_file(data, "ImportUtilisateurs", scu.XLSX_SUFFIX, scu.XLSX_MIMETYPE)


@bp.route("/import_users_form", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoUsersAdmin)
@scodoc7func
def import_users_form():
    """Import utilisateurs depuis feuille Excel"""
    head = html_sco_header.sco_header(page_title="Import utilisateurs")
    H = [
        head,
        """<h2>Téléchargement d'une nouvelle liste d'utilisateurs</h2>
         <p style="color: red">A utiliser pour importer de <b>nouveaux</b> utilisateurs (enseignants ou secrétaires)
         </p>
         <p>
         L'opération se déroule en deux étapes. Dans un premier temps,
         vous téléchargez une feuille Excel type. Vous devez remplir
         cette feuille, une ligne décrivant chaque utilisateur. Ensuite,
         vous indiquez le nom de votre fichier dans la case "Fichier Excel"
         ci-dessous, et cliquez sur "Télécharger" pour envoyer au serveur
         votre liste.
         </p>
         """,
    ]
    help = """<p class="help">
    Lors de la creation des utilisateurs, les opérations suivantes sont effectuées:
    </p>
    <ol class="help">
    <li>vérification des données;</li>
    <li>génération d'un mot de passe alétoire pour chaque utilisateur;</li>
    <li>création de chaque utilisateur;</li>
    <li>envoi à chaque utilisateur de son <b>mot de passe initial par mail</b>.</li>
    </ol>"""
    H.append(
        """<ol><li><a class="stdlink" href="import_users_generate_excel_sample">
    Obtenir la feuille excel à remplir</a></li><li>"""
    )
    F = html_sco_header.sco_footer()
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "xlsfile",
                {"title": "Fichier Excel:", "input_type": "file", "size": 40},
            ),
            (
                "force",
                {
                    "title": "Ignorer les avertissements",
                    "input_type": "checkbox",
                    "explanation": "passer outre les avertissements (homonymes, etc)",
                    "labels": ("",),
                    "allowed_values": ("1",),
                },
            ),
            ("formsemestre_id", {"input_type": "hidden"}),
        ),
        submitlabel="Télécharger",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + "</li></ol>" + help + F
    elif tf[0] == -1:
        return flask.redirect(url_for("scolar.index_html", docodc_dept=g.scodoc_dept))
    else:
        # IMPORT
        ok, diag, nb_created = sco_import_users.import_excel_file(
            tf[2]["xlsfile"], tf[2]["force"]
        )
        H = [html_sco_header.sco_header(page_title="Import utilisateurs")]
        H.append("<ul>")
        for d in diag:
            H.append("<li>%s</li>" % d)
        H.append("</ul>")
        if ok:
            dest = url_for("users.index_html", scodoc_dept=g.scodoc_dept, all_depts=1)
            H.append("<p>Ok, Import terminé (%s utilisateurs créés)!</p>" % nb_created)
            H.append('<p><a class="stdlink" href="%s">Continuer</a></p>' % dest)
        else:
            dest = url_for("users.import_users_form", scodoc_dept=g.scodoc_dept)
            H.append("<p>Erreur, importation annulée !</p>")
            H.append('<p><a class="stdlink" href="%s">Continuer</a></p>' % dest)
        return "\n".join(H) + html_sco_header.sco_footer()


@bp.route("/user_info_page")
@scodoc
@permission_required(Permission.ScoUsersView)
@scodoc7func
def user_info_page(user_name=None):
    """Display page of info about given user.
    If user_name not specified, user current_user
    """
    from app.scodoc.sco_permissions_check import can_handle_passwd

    # peut on divulguer ces infos ?
    if not can_handle_passwd(current_user, allow_admindepts=True):
        raise AccessDenied("Vous n'avez pas la permission de voir cette page")

    dept = g.scodoc_dept
    if not user_name:
        user = current_user
    else:
        user = User.query.filter_by(user_name=user_name).first()
    if not user:
        raise ScoValueError("invalid user_name")

    return render_template(
        "auth/user_info_page.html",
        user=user,
        title=f"Utilisateur {user.user_name}",
        Permission=Permission,
        dept=dept,
    )


@bp.route("/get_user_list_xml")
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def get_user_list_xml(dept=None, start="", limit=25):
    """Returns XML list of users with name (nomplogin) starting with start.
    Used for forms auto-completion.
    """
    # suggère seulement seulement les utilisateurs actifs:
    userlist = sco_users.get_user_list(dept=dept)
    start = scu.suppress_accents(str(start)).lower()
    # TODO : à refaire avec une requete SQL #py3
    # (et en json)
    userlist = [
        user
        for user in userlist
        if scu.suppress_accents((user.nom or "").lower()).startswith(start)
    ]
    doc = ElementTree.Element("results")
    for user in userlist[:limit]:
        x_rs = ElementTree.Element("rs", id=str(user.id), info="")
        x_rs.text = user.get_nomplogin()
        doc.append(x_rs)

    data = sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING)
    return scu.send_file(data, mime=scu.XML_MIMETYPE)


@bp.route("/form_change_password", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def form_change_password(user_name=None):
    """Formulaire de changement mot de passe de l'utilisateur user_name.
    Un utilisateur peut toujours changer son propre mot de passe.
    """
    if not user_name:
        user = current_user
    else:
        user = User.query.filter_by(user_name=user_name).first()

    # check access
    if not can_handle_passwd(user):
        return "\n".join(
            [
                html_sco_header.sco_header(user_check=False),
                "<p>Vous n'avez pas la permission de changer ce mot de passe</p>",
                html_sco_header.sco_footer(),
            ]
        )
    form = ChangePasswordForm(user_name=user.user_name, email=user.email)
    destination = url_for(
        "users.user_info_page",
        scodoc_dept=g.scodoc_dept,
        user_name=user_name,
    )
    if request.method == "POST" and form.cancel.data:  # cancel button clicked
        return redirect(destination)
    if form.validate_on_submit():
        messages = []
        if form.new_password.data != "":  # change password
            user.set_password(form.new_password.data)
            messages.append("Mot de passe modifié")
        if form.email.data.strip() != user.email:  # change email
            user.email = form.email.data.strip()
            messages.append("Adresse email modifiée")
        db.session.commit()
        flash("\n".join(messages))
        return redirect(destination)

    return render_template(
        "auth/change_password.html",
        form=form,
        title="Modification compte ScoDoc",
        auth_username=current_user.user_name,
    )


@bp.route("/change_password", methods=["POST"])
@scodoc
@permission_required(Permission.ScoView)
@scodoc7func
def change_password(user_name, password, password2):
    "Change the password for user given by user_name"
    u = User.query.filter_by(user_name=user_name).first()
    # Check access permission
    if not can_handle_passwd(u):
        # access denied
        log(
            "change_password: access denied (authuser=%s, user_name=%s)"
            % (current_user, user_name)
        )
        raise AccessDenied("vous n'avez pas la permission de changer ce mot de passe")
    H = []
    F = html_sco_header.sco_footer()
    # check password
    if password != password2:
        H.append(
            """<p>Les deux mots de passes saisis sont différents !</p>
        <p><a href="form_change_password?user_name=%s" class="stdlink">Recommencer</a></p>"""
            % user_name
        )
    else:
        if not is_valid_password(password):
            H.append(
                """<p><b>ce mot de passe n\'est pas assez compliqué !</b><br/>(oui, il faut un mot de passe vraiment compliqué !)</p>
            <p><a href="form_change_password?user_name=%s" class="stdlink">Recommencer</a></p>
            """
                % user_name
            )
        else:
            # ok, strong password
            db.session.add(u)
            u.set_password(password)
            db.session.commit()
            #
            # ici page simplifiee car on peut ne plus avoir
            # le droit d'acceder aux feuilles de style
            H.append(
                "<h2>Changement effectué !</h2><p>Ne notez pas ce mot de passe, mais mémorisez le !</p><p>Rappel: il est <b>interdit</b> de communiquer son mot de passe à un tiers, même si c'est un collègue de confiance !</p><p><b>Si vous n'êtes pas administrateur, le système va vous redemander votre login et nouveau mot de passe au prochain accès.</b></p>"
            )
            return (
                """<?xml version="1.0" encoding="%s"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html>
<head>
<title>Mot de passe changé</title>
<meta http-equiv="Content-Type" content="text/html; charset=%s" />
<body><h1>Mot de passe changé !</h1>
"""
                % (scu.SCO_ENCODING, scu.SCO_ENCODING)
                + "\n".join(H)
                + '<a href="%s"  class="stdlink">Continuer</a></body></html>'
                % scu.ScoURL()
            )
    return html_sco_header.sco_header() + "\n".join(H) + F


@bp.route("/toggle_active_user/<user_name>", methods=["GET", "POST"])
@scodoc
@permission_required(Permission.ScoUsersAdmin)
def toggle_active_user(user_name: str = None):
    """Change active status of a user account"""
    u = User.query.filter_by(user_name=user_name).first()
    if not u:
        raise ScoValueError("invalid user_name")
    form = DeactivateUserForm()
    if (
        request.method == "POST" and form.cancel.data
    ):  # if cancel button is clicked, the form.cancel.data will be True
        # flash
        return redirect(url_for("users.index_html", scodoc_dept=g.scodoc_dept))
    if form.validate_on_submit():
        u.active = not u.active
        db.session.add(u)
        db.session.commit()
        return redirect(url_for("users.index_html", scodoc_dept=g.scodoc_dept))
    return render_template("auth/toogle_active_user.html", form=form, u=u)
