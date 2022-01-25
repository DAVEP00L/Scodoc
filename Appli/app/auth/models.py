# -*- coding: UTF-8 -*

"""Users and Roles models for ScoDoc
"""

import base64
from datetime import datetime, timedelta
import os
import re
from time import time
from typing import Optional

import cracklib  # pylint: disable=import-error
from flask import current_app, url_for, g
from flask_login import UserMixin, AnonymousUserMixin

from werkzeug.security import generate_password_hash, check_password_hash

import jwt

from app import db, login

from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_roles_default import SCO_ROLES_DEFAULTS
import app.scodoc.sco_utils as scu
from app.scodoc import sco_etud  # a deplacer dans scu

VALID_LOGIN_EXP = re.compile(r"^[a-zA-Z0-9@\\\-_\.]+$")


def is_valid_password(cleartxt):
    """Check password.
    returns True if OK.
    """
    if (
        hasattr(scu.CONFIG, "MIN_PASSWORD_LENGTH")
        and scu.CONFIG.MIN_PASSWORD_LENGTH > 0
        and len(cleartxt) < scu.CONFIG.MIN_PASSWORD_LENGTH
    ):
        return False  # invalid: too short
    try:
        _ = cracklib.FascistCheck(cleartxt)
        return True
    except ValueError:
        return False


class User(UserMixin, db.Model):
    """ScoDoc users, handled by Flask / SQLAlchemy"""

    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120))

    nom = db.Column(db.String(64))
    prenom = db.Column(db.String(64))
    dept = db.Column(db.String(32), index=True)
    active = db.Column(db.Boolean, default=True, index=True)

    password_hash = db.Column(db.String(128))
    password_scodoc7 = db.Column(db.String(42))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    date_modif_passwd = db.Column(db.DateTime, default=datetime.utcnow)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    date_expiration = db.Column(db.DateTime, default=None)
    passwd_temp = db.Column(db.Boolean, default=False)
    token = db.Column(db.String(32), index=True, unique=True)
    token_expiration = db.Column(db.DateTime)

    roles = db.relationship("Role", secondary="user_role", viewonly=True)
    Permission = Permission

    def __init__(self, **kwargs):
        self.roles = []
        self.user_roles = []
        # check login:
        if kwargs.get("user_name") and not VALID_LOGIN_EXP.match(kwargs["user_name"]):
            raise ValueError(f"invalid user_name: {kwargs['user_name']}")
        super(User, self).__init__(**kwargs)
        # Ajoute roles:
        if (
            not self.roles
            and self.email
            and self.email == current_app.config["SCODOC_ADMIN_MAIL"]
        ):
            # super-admin
            admin_role = Role.query.filter_by(name="SuperAdmin").first()
            assert admin_role
            self.add_role(admin_role, None)
            db.session.commit()
        # current_app.logger.info("creating user with roles={}".format(self.roles))

    def __repr__(self):
        return f"<User {self.user_name} id={self.id} dept={self.dept}{' (inactive)' if not self.active else ''}>"

    def __str__(self):
        return self.user_name

    def set_password(self, password):
        "Set password"
        current_app.logger.info(f"set_password({self})")
        if password:
            self.password_hash = generate_password_hash(password)
        else:
            self.password_hash = None

    def check_password(self, password):
        """Check given password vs current one.
        Returns `True` if the password matched, `False` otherwise.
        """
        if not self.active:  # inactived users can't login
            return False
        if (not self.password_hash) and self.password_scodoc7:
            # Special case: user freshly migrated from ScoDoc7
            if scu.check_scodoc7_password(self.password_scodoc7, password):
                current_app.logger.warning(
                    f"migrating legacy ScoDoc7 password for {self}"
                )
                self.set_password(password)
                self.password_scodoc7 = None
                db.session.add(self)
                db.session.commit()
                return True
            return False
        if not self.password_hash:  # user without password can't login
            return False
        return check_password_hash(self.password_hash, password)

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {"reset_password": self.id, "exp": time() + expires_in},
            current_app.config["SECRET_KEY"],
            algorithm="HS256",
        )

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(
                token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
            )["reset_password"]
        except:
            return
        return User.query.get(id)

    def to_dict(self, include_email=True):
        data = {
            "date_expiration": self.date_expiration.isoformat() + "Z"
            if self.date_expiration
            else "",
            "date_modif_passwd": self.date_modif_passwd.isoformat() + "Z"
            if self.date_modif_passwd
            else "",
            "date_created": self.date_created.isoformat() + "Z"
            if self.date_created
            else "",
            "dept": (self.dept or ""),  # sco8
            "id": self.id,
            "active": self.active,
            "status_txt": "actif" if self.active else "fermé",
            "last_seen": self.last_seen.isoformat() + "Z",
            "nom": (self.nom or ""),  # sco8
            "prenom": (self.prenom or ""),  # sco8
            "roles_string": self.get_roles_string(),  # eg "Ens_RT, Ens_Info"
            "user_name": self.user_name,  # sco8
            # Les champs calculés:
            "nom_fmt": self.get_nom_fmt(),
            "prenom_fmt": self.get_prenom_fmt(),
            "nomprenom": self.get_nomprenom(),
            "prenomnom": self.get_prenomnom(),
            "nomplogin": self.get_nomplogin(),
            "nomcomplet": self.get_nomcomplet(),
        }
        if include_email:
            data["email"] = self.email or ""
        return data

    def from_dict(self, data, new_user=False):
        """Set users' attributes from given dict values.
        Roles must be encoded as "roles_string", like "Ens_RT, Secr_CJ"
        """
        for field in ["nom", "prenom", "dept", "active", "email", "date_expiration"]:
            if field in data:
                setattr(self, field, data[field] or None)
        if new_user:
            if "user_name" in data:
                # never change name of existing users
                self.user_name = data["user_name"]
            if "password" in data:
                self.set_password(data["password"])
        if not VALID_LOGIN_EXP.match(self.user_name):
            raise ValueError(f"invalid user_name: {self.user_name}")
        # Roles: roles_string is "Ens_RT, Secr_RT, ..."
        if "roles_string" in data:
            self.user_roles = []
            for r_d in data["roles_string"].split(","):
                if r_d:
                    role, dept = UserRole.role_dept_from_string(r_d)
                    self.add_role(role, dept)

    def get_token(self, expires_in=3600):
        now = datetime.utcnow()
        if self.token and self.token_expiration > now + timedelta(seconds=60):
            return self.token
        self.token = base64.b64encode(os.urandom(24)).decode("utf-8")
        self.token_expiration = now + timedelta(seconds=expires_in)
        db.session.add(self)
        return self.token

    def revoke_token(self):
        self.token_expiration = datetime.utcnow() - timedelta(seconds=1)

    @staticmethod
    def check_token(token):
        """Retreive user for given token, chek token's validity
        and returns the user object.
        """
        user = User.query.filter_by(token=token).first()
        if user is None or user.token_expiration < datetime.utcnow():
            return None
        return user

    # Permissions management:
    def has_permission(self, perm: int, dept=False):
        """Check if user has permission `perm` in given `dept`.
        Similar to Zope ScoDoc7 `has_permission``

        Args:
            perm: integer, one of the value defined in Permission class.
            dept: dept id (eg 'RT'), default to current departement.
        """
        if not self.active:
            return False
        if dept is False:
            dept = g.scodoc_dept
        # les role liés à ce département, et les roles avec dept=None (super-admin)
        roles_in_dept = (
            UserRole.query.filter_by(user_id=self.id)
            .filter((UserRole.dept == dept) | (UserRole.dept == None))
            .all()
        )
        for user_role in roles_in_dept:
            if user_role.role.has_permission(perm):
                return True
        return False

    # Role management
    def add_role(self, role, dept):
        """Add a role to this user.
        :param role: Role to add.
        """
        self.user_roles.append(UserRole(user=self, role=role, dept=dept))

    def add_roles(self, roles, dept):
        """Add roles to this user.
        :param roles: Roles to add.
        """
        for role in roles:
            self.add_role(role, dept)

    def set_roles(self, roles, dept):
        "set roles in the given dept"
        self.user_roles = [UserRole(user=self, role=r, dept=dept) for r in roles]

    def get_roles(self):
        "iterator on my roles"
        for role in self.roles:
            yield role

    def get_roles_string(self):
        """string repr. of user's roles (with depts)
        e.g. "Ens_RT, Ens_Info, Secr_CJ"
        """
        return ",".join(f"{r.role.name}_{r.dept or ''}" for r in self.user_roles)

    def is_administrator(self):
        "True if i'm an active SuperAdmin"
        return self.active and self.has_permission(Permission.ScoSuperAdmin, dept=None)

    # Some useful strings:
    def get_nomplogin(self):
        """nomplogin est le nom en majuscules suivi du prénom et du login
        e.g. Dupont Pierre (dupont)
        """
        if self.nom:
            n = sco_etud.format_nom(self.nom)
        else:
            n = self.user_name.upper()
        return "%s %s (%s)" % (
            n,
            sco_etud.format_prenom(self.prenom),
            self.user_name,
        )

    @staticmethod
    def get_user_id_from_nomplogin(nomplogin: str) -> Optional[int]:
        """Returns id from the string "Dupont Pierre (dupont)"
        or None if user does not exist
        """
        m = re.match(r".*\((.*)\)", nomplogin.strip())
        if m:
            user_name = m.group(1)
            u = User.query.filter_by(user_name=user_name).first()
            if u:
                return u.id
        return None

    def get_nom_fmt(self):
        """Nom formatté: "Martin" """
        if self.nom:
            return sco_etud.format_nom(self.nom, uppercase=False)
        else:
            return self.user_name

    def get_prenom_fmt(self):
        """Prénom formaté (minuscule capitalisées)"""
        return sco_etud.format_prenom(self.prenom)

    def get_nomprenom(self):
        """Nom capitalisé suivi de l'initiale du prénom:
        Viennet E.
        """
        prenom_abbrv = scu.abbrev_prenom(sco_etud.format_prenom(self.prenom))
        return (self.get_nom_fmt() + " " + prenom_abbrv).strip()

    def get_prenomnom(self):
        """L'initiale du prénom suivie du nom: "J.-C. Dupont" """
        prenom_abbrv = scu.abbrev_prenom(sco_etud.format_prenom(self.prenom))
        return (prenom_abbrv + " " + self.get_nom_fmt()).strip()

    def get_nomcomplet(self):
        "Prénom et nom complets"
        return sco_etud.format_prenom(self.prenom) + " " + self.get_nom_fmt()

    # nomnoacc était le nom en minuscules sans accents (inutile)


class AnonymousUser(AnonymousUserMixin):
    def has_permission(self, perm, dept=None):
        return False

    def is_administrator(self):
        return False


login.anonymous_user = AnonymousUser


class Role(db.Model):
    """Roles for ScoDoc"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)  # TODO: , nullable=False))
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.BigInteger)  # 64 bits
    users = db.relationship("User", secondary="user_role", viewonly=True)
    # __table_args__ = (db.UniqueConstraint("name", "dept", name="_rolename_dept_uc"),)

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    def __repr__(self):
        return "<Role {} perm={:0{w}b}>".format(
            self.name,
            self.permissions & ((1 << Permission.NBITS) - 1),
            w=Permission.NBITS,
        )

    def add_permission(self, perm):
        self.permissions |= perm

    def remove_permission(self, perm):
        self.permissions = self.permissions & ~perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    @staticmethod
    def insert_roles():
        """Create default roles"""
        default_role = "Observateur"
        for role_name, permissions in SCO_ROLES_DEFAULTS.items():
            role = Role.query.filter_by(name=role_name).first()
            if role is None:
                role = Role(name=role_name)
            role.reset_permissions()
            for perm in permissions:
                role.add_permission(perm)
            role.default = role.name == default_role
            db.session.add(role)
        db.session.commit()

    @staticmethod
    def get_named_role(name):
        """Returns existing role with given name, or None."""
        return Role.query.filter_by(name=name).first()


class UserRole(db.Model):
    """Associate user to role, in a dept.
    If dept is None, the role applies to all departments (eg super admin).
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"))
    dept = db.Column(db.String(64))  # dept acronym ou NULL
    user = db.relationship(
        User, backref=db.backref("user_roles", cascade="all, delete-orphan")
    )
    role = db.relationship(
        Role, backref=db.backref("user_roles", cascade="all, delete-orphan")
    )

    def __repr__(self):
        return "<UserRole u={} r={} dept={}>".format(self.user, self.role, self.dept)

    @staticmethod
    def role_dept_from_string(role_dept: str):
        """Return tuple (role, dept) from the string
        role_dept, of the forme "Role_Dept".
        role is a Role instance, dept is a string, or None.
        """
        fields = role_dept.split("_", 1)  # maxsplit=1, le dept peut contenir un "_"
        if len(fields) != 2:
            current_app.logger.warning(
                f"role_dept_from_string:  Invalid role_dept '{role_dept}'"
            )
            raise ScoValueError("Invalid role_dept")
        role_name, dept = fields
        if dept == "":
            dept = None
        role = Role.query.filter_by(name=role_name).first()
        if role is None:
            raise ScoValueError("role %s does not exists" % role_name)
        return (role, dept)


def get_super_admin():
    """L'utilisateur admin (ou le premier, s'il y en a plusieurs).
    Utilisé par les tests unitaires et le script de migration.
    """
    admin_role = Role.query.filter_by(name="SuperAdmin").first()
    assert admin_role
    admin_user = (
        User.query.join(UserRole)
        .filter((UserRole.user_id == User.id) & (UserRole.role_id == admin_role.id))
        .first()
    )
    assert admin_user
    return admin_user


@login.user_loader
def load_user(id):
    return User.query.get(int(id))
