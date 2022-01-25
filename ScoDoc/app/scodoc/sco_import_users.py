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

"""Import d'utilisateurs via fichier Excel
"""
import random
import time

from email.mime.multipart import MIMEMultipart
from flask import g, url_for
from flask_login import current_user

from app import db
from app import email
from app.auth.models import User, UserRole
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
from app.scodoc import sco_excel
from app.scodoc import sco_preferences
from app.scodoc import sco_users


TITLES = ("user_name", "nom", "prenom", "email", "roles", "dept")
COMMENTS = (
    """user_name:
    Composé de lettres (minuscules ou majuscules), de chiffres ou du caractère _
    """,
    """nom:
    Maximum 64 caractères""",
    """prenom:
    Maximum 64 caractères""",
    """email:
    Maximum 120 caractères""",
    """roles:
    un plusieurs rôles séparés par ','
    chaque role est fait de 2 composantes séparées par _:
    1. Le role (Ens, Secr ou Admin)
    2. Le département (en majuscule)
    Exemple: "Ens_RT,Admin_INFO"
    """,
    """dept:
    Le département d'appartenance du l'utillsateur. Laisser vide si l'utilisateur intervient dans plusieurs dépatements
    """,
)


def generate_excel_sample():
    """generates an excel document suitable to import users"""
    style = sco_excel.excel_make_style(bold=True)
    titles = TITLES
    titles_styles = [style] * len(titles)
    return sco_excel.excel_simple_table(
        titles=titles,
        titles_styles=titles_styles,
        sheet_name="Utilisateurs ScoDoc",
        comments=COMMENTS,
    )


def import_excel_file(datafile, force=""):
    """
    Import scodoc users from Excel file.
    This method:
        * checks that the current_user has the ability to do so (at the moment only a SuperAdmin). He may thereoff import users with any well formed role into any department (or all)
        * Once the check is done ans successfull, build the list of users (does not check the data)
        * call :func:`import_users` to actually do the job
    history: scodoc7 with no SuperAdmin every Admin_XXX could import users.
    :param datafile:  the stream from to the to be imported
    :return: same as import users
    """
    # Check current user privilege
    auth_name = str(current_user)
    if not current_user.is_administrator():
        raise AccessDenied("invalid user (%s) must be SuperAdmin" % auth_name)
    # Récupération des informations sur l'utilisateur courant
    log("sco_import_users.import_excel_file by %s" % auth_name)
    # Read the data from the stream
    exceldata = datafile.read()
    if not exceldata:
        raise ScoValueError("Ficher excel vide ou invalide")
    _, data = sco_excel.excel_bytes_to_list(exceldata)
    if not data:
        raise ScoValueError(
            """Le fichier xlsx attendu semble vide !
            """
        )
    # 1-  --- check title line
    fs = [scu.stripquotes(s).lower() for s in data[0]]
    log("excel: fs='%s'\ndata=%s" % (str(fs), str(data)))
    # check cols
    cols = {}.fromkeys(TITLES)
    unknown = []
    for tit in fs:
        if tit not in cols:
            unknown.append(tit)
        else:
            del cols[tit]
    if cols or unknown:
        raise ScoValueError(
            """colonnes incorrectes (on attend %d, et non %d) <br/>
            (colonnes manquantes: %s, colonnes invalides: %s)"""
            % (len(TITLES), len(fs), list(cols.keys()), unknown)
        )
    # ok, same titles... : build the list of dictionaries
    users = []
    for line in data[1:]:
        d = {}
        for i in range(len(fs)):
            d[fs[i]] = line[i]
        users.append(d)

    return import_users(users=users, force=force)


def import_users(users, force=""):
    """
    Import users from a list of users_descriptors.

    descriptors are dictionaries hosting users's data.
    The operation is atomic (all the users are imported or none)

    :param users: list of descriptors to be imported

    :return: a tuple that describe the result of the import:
        * ok: import ok or aborted
        * messages: the list of messages
        * the # of users created
    """
    """ Implémentation:
    Pour chaque utilisateur à créer:
        * vérifier données (y compris que le même nom d'utilisateur n'est pas utilisé plusieurs fois)
        * générer mot de passe aléatoire
        * créer utilisateur et mettre le mot de passe
        * envoyer mot de passe par mail
    Les utilisateurs à créer sont stockés dans un dictionnaire. 
    L'ajout effectif ne se fait qu'en fin de fonction si aucune erreur n'a été détectée
    """

    if len(users) == 0:
        import_ok = False
        msg_list = ["Feuille vide ou illisible"]
    else:
        created = {}  # liste de uid créés
        msg_list = []
        line = 1  # start from excel line #2
        import_ok = True

        def append_msg(msg):
            msg_list.append("Ligne %s : %s" % (line, msg))

        try:
            for u in users:
                line = line + 1
                user_ok, msg = sco_users.check_modif_user(
                    0,
                    enforce_optionals=not force,
                    user_name=u["user_name"],
                    nom=u["nom"],
                    prenom=u["prenom"],
                    email=u["email"],
                    roles=[r for r in u["roles"].split(",") if r],
                    dept=u["dept"],
                )
                if not user_ok:
                    append_msg("identifiant '%s' %s" % (u["user_name"], msg))

                u["passwd"] = generate_password()
                #
                # check identifiant
                if u["user_name"] in created.keys():
                    user_ok = False
                    append_msg(
                        "l'utilisateur '%s' a déjà été décrit ligne %s"
                        % (u["user_name"], created[u["user_name"]]["line"])
                    )
                # check roles / ignore whitespaces around roles / build roles_string
                # roles_string (expected by User) appears as column 'roles' in excel file
                roles_list = []
                for role in u["roles"].split(","):
                    try:
                        role = role.strip()
                        if role:
                            _, _ = UserRole.role_dept_from_string(role)
                            roles_list.append(role)
                    except ScoValueError as value_error:
                        user_ok = False
                        append_msg("role %s : %s" % (role, value_error))
                u["roles_string"] = ",".join(roles_list)
                if user_ok:
                    u["line"] = line
                    created[u["user_name"]] = u
                else:
                    import_ok = False
        except ScoValueError as value_error:
            log("import_users: exception: abort create %s" % str(created.keys()))
            raise ScoValueError(msg) from value_error
        if import_ok:
            for u in created.values():
                # Création de l'utilisateur (via SQLAlchemy)
                user = User()
                user.from_dict(u, new_user=True)
                db.session.add(user)
                db.session.commit()
                mail_password(u)
        else:
            created = []  # reset # of created users to 0
    return import_ok, msg_list, len(created)


#  --------- Génération du mot de passe initial -----------
# Adapté de http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/440564
# Alphabet tres simple pour des mots de passe simples...


ALPHABET = r"""ABCDEFGHIJKLMNPQRSTUVWXYZ123456789123456789AEIOU"""
PASSLEN = 8
RNG = random.Random(time.time())


def generate_password():
    """This function creates a pseudo random number generator object, seeded with
    the cryptographic hash of the passString. The contents of the character set
    is then shuffled and a selection of passLength words is made from this list.
    This selection is returned as the generated password."""
    l = list(ALPHABET)  # make this mutable so that we can shuffle the characters
    RNG.shuffle(l)  # shuffle the character set
    # pick up only a subset from the available characters:
    return "".join(RNG.sample(l, PASSLEN))


def mail_password(user: dict, reset=False) -> None:
    "Send password by email"
    if not user["email"]:
        return

    user["url"] = url_for("scodoc.index", _external=True)
    txt = (
        """
Bonjour %(prenom)s %(nom)s,

"""
        % user
    )
    if reset:
        txt += (
            """
votre mot de passe ScoDoc a été ré-initialisé.

Le nouveau mot de passe est:  %(passwd)s
Votre nom d'utilisateur est %(user_name)s

Vous devrez changer ce mot de passe lors de votre première connexion
sur %(url)s
"""
            % user
        )
    else:
        txt += (
            """
vous avez été déclaré comme utilisateur du logiciel de gestion de scolarité ScoDoc.

Votre nom d'utilisateur est %(user_name)s
Votre mot de passe est: %(passwd)s

Le logiciel est accessible sur: %(url)s

Vous êtes invité à changer ce mot de passe au plus vite (cliquez sur votre nom en haut à gauche de la page d'accueil).
"""
            % user
        )

    txt += (
        """
_______
ScoDoc est un logiciel libre développé par Emmanuel Viennet et l'association ScoDoc.
Pour plus d'informations sur ce logiciel, voir %s

"""
        % scu.SCO_WEBSITE
    )
    msg = MIMEMultipart()
    if reset:
        subject = "Mot de passe ScoDoc"
    else:
        subject = "Votre accès ScoDoc"
    sender = sco_preferences.get_preference("email_from_addr")
    email.send_email(subject, sender, [user["email"]], txt)
