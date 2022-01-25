# -*- coding: UTF-8 -*

"""Unit tests for auth (users/roles/permission management)

Ré-écriture de test_users avec pytest.

Usage: pytest tests/unit/test_users.py 
"""

import pytest
from tests.conftest import test_client
from flask import current_app

from app import db
from app.auth.models import User, Role, Permission
from app.scodoc.sco_roles_default import SCO_ROLES_DEFAULTS


DEPT = "XX"


def test_password_hashing(test_client):
    u = User(user_name="susan")
    db.session.add(u)
    db.session.commit()
    # nota: default attributes values, like active,
    # are not set before the first commit() (?)
    assert u.active
    u.set_password("cat")
    assert not u.check_password("dog")
    assert u.check_password("cat")


def test_roles_permissions(test_client):
    perm = Permission.ScoAbsChange  # une permission au hasard
    role = Role(name="test")
    assert not role.has_permission(perm)
    role.add_permission(perm)
    assert role.has_permission(perm)
    role.remove_permission(perm)
    assert not role.has_permission(perm)
    # Default roles:
    Role.insert_roles()
    # Bien présents ?
    role_names = [r.name for r in Role.query.filter_by().all()]
    assert len(role_names) == len(SCO_ROLES_DEFAULTS)
    assert "Ens" in role_names
    assert "Secr" in role_names
    assert "Admin" in role_names
    # Les permissions de "Ens":
    role = Role.query.filter_by(name="Ens").first()
    assert role
    assert role.has_permission(Permission.ScoView)
    assert role.has_permission(Permission.ScoAbsChange)
    # Permissions de Admin
    role = Role.query.filter_by(name="Admin").first()
    assert role.has_permission(Permission.ScoEtudChangeAdr)
    # Permissions de Secr
    role = Role.query.filter_by(name="Secr").first()
    assert role.has_permission(Permission.ScoEtudChangeAdr)
    assert not role.has_permission(Permission.ScoEditAllNotes)


def test_users_roles(test_client):
    dept = "XX"
    perm = Permission.ScoAbsChange
    perm2 = Permission.ScoView
    u = User(user_name="un_enseignant")
    db.session.add(u)
    assert not u.has_permission(perm, dept)
    r = Role.get_named_role("Ens")
    if not r:
        r = Role(name="Ens", permissions=perm)
    u.add_role(r, dept)
    assert u.has_permission(perm, dept)
    u = User(user_name="un_autre")
    u.add_role(r, dept)
    db.session.add(u)
    db.session.commit()
    assert u.has_permission(perm, dept)
    r2 = Role.get_named_role("Secr")
    if not r2:
        r2 = Role(name="Secr", dept=dept, permissions=perm2)
    u.add_roles([r, r2], dept)
    assert len(u.roles) == 2
    u = User(user_name="encore_un")
    db.session.add(u)
    db.session.commit()
    u.set_roles([r, r2], dept)
    print(u.roles)
    assert len(u.roles) == 2
    assert u.has_permission(perm, dept)
    assert u.has_permission(perm2, dept)
    # et pas accès aux autres dept:
    assert not u.has_permission(perm, dept + "X")
    assert not u.has_permission(perm, None)


def test_user_admin(test_client):
    dept = "XX"
    perm = 0x1234  # a random perm
    u = User(user_name="un_admin", email=current_app.config["SCODOC_ADMIN_MAIL"])
    db.session.add(u)
    assert len(u.roles) == 1
    assert u.has_permission(perm, dept)
    # Le grand admin a accès à tous les départements:
    assert u.has_permission(perm, dept + "XX")
    assert u.roles[0].name == "SuperAdmin"


def test_create_delete(test_client):
    u = User(user_name="dupont", nom="Dupont", prenom="Pierre")
    db.session.add(u)
    db.session.commit()
    u = User(user_name="dupond", nom="Dupond", prenom="Pierre")
    db.session.add(u)
    db.session.commit()
    ul = User.query.filter_by(prenom="Pierre").all()
    assert len(ul) == 2
    ul = User.query.filter_by(user_name="dupont").all()
    assert len(ul) == 1
    db.session.delete(ul[0])
    db.session.commit()
    ul = User.query.filter_by(prenom="Pierre").all()
    assert len(ul) == 1
