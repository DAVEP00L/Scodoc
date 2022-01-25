# -*- mode: python -*-
# -*- coding: utf-8 -*-

import pdb
import re

import psycopg2
import psycopg2.extras

from flask import current_app
from app import db
from app.auth.models import User, Role
from app.scodoc import sco_utils as scu
from tools.import_scodoc7_dept import setup_log


def import_scodoc7_user_db(scodoc7_db="dbname=SCOUSERS"):
    """Create users from existing ScoDoc7 db (SCOUSERS)
    The resulting users are in SCO8USERS,
    handled via Flask/SQLAlchemy ORM.
    """
    setup_log("USERS")
    current_app.logger.info("Importation des utilisateurs...")
    messages = []
    cnx = psycopg2.connect(scodoc7_db)
    cursor = cnx.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM sco_users;")
    for u7 in cursor:
        user_name = scu.sanitize_string(u7["user_name"].strip())
        # ensure that user_name will match VALID_LOGIN_EXP
        user_name = scu.purge_chars(
            user_name,
            allowed_chars="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@\\-_.",
        )
        if user_name != u7["user_name"]:
            msg = f"""Changing login '{u7["user_name"]}' to '{user_name}'"""
            current_app.logger.warning(msg)
            messages.append(msg)
        if User.query.filter_by(user_name=user_name).first():
            # user with same name exists !
            msg = f"""User {user_name} (de {u7["user_name"]})  exists and is left unchanged"""
            current_app.logger.warning(msg)
            messages.append(msg)
        else:
            u = User(
                user_name=user_name,
                email=u7["email"],
                date_modif_passwd=u7["date_modif_passwd"],
                nom=u7["nom"],
                prenom=u7["prenom"],
                dept=u7["dept"],
                passwd_temp=u7["passwd_temp"],
                date_expiration=u7["date_expiration"],
                password_scodoc7=u7["passwd"],
                active=(u7["status"] == None),
            )
            # Set roles:
            # ScoDoc7 roles are stored as 'AdminRT,EnsRT'
            # ou, dans les rares cas où le dept est en minuscules
            # "Ensgeii,Admingeii"
            if u7["roles"]:
                roles7 = u7["roles"].split(",")
            else:
                roles7 = []
            for role_dept in roles7:
                # Migre les rôles RespPeX, EnsX, AdminX, SecrX et ignore les autres
                m = re.match(r"^(-?Ens|-?Secr|-?RespPe|-?Admin)(.*)$", role_dept)
                if not m:
                    msg = f"User {user_name}: role inconnu '{role_dept}' (ignoré)"
                    current_app.logger.warning(msg)
                    messages.append(msg)
                else:
                    role_name = m.group(1)
                    if role_name.startswith("-"):
                        # disabled users in ScoDoc7
                        role_name = role_name[1:]
                        assert not u.active
                        # silently ignore old (disabled) role
                    else:
                        dept = m.group(2)
                        role = Role.query.filter_by(name=role_name).first()
                        if not role:
                            msg = f"Role '{role_name}' introuvable. User {user_name}: ignoring role '{role_dept}'"
                            current_app.logger.warning(msg)
                            messages.append(msg)
                        else:
                            u.add_role(role, dept)
            db.session.add(u)
            current_app.logger.info("imported user {}".format(u))
    db.session.commit()
    return messages
