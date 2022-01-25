import pytest

from flask import g
from flask_login import login_user, logout_user, current_user

from config import TestConfig
import app
from app import db, create_app
from app import initialize_scodoc_database, clear_scodoc_cache
from app import models
from app.auth.models import User, Role, UserRole, Permission
from app.auth.models import get_super_admin
from app.scodoc import sco_bulletins_standard
from app.scodoc import notesdb as ndb


@pytest.fixture()
def test_client():
    # Setup
    apptest = create_app(TestConfig)
    # Run tests:
    with apptest.test_client() as client:
        with apptest.app_context():
            with apptest.test_request_context():
                # initialize scodoc "g":
                g.stored_get_formsemestre = {}
                # erase and reset database:
                initialize_scodoc_database(erase=True, create_all=True)
                # Loge l'utilisateur super-admin
                admin_user = get_super_admin()
                login_user(admin_user)
                # Vérifie que l'utilisateur "bach" existe
                u = User.query.filter_by(user_name="bach").first()
                if u is None:
                    u = User(user_name="bach")
                if not "Admin" in {r.name for r in u.roles}:
                    admin_role = Role.query.filter_by(name="Admin").first()
                    u.add_role(admin_role, TestConfig.DEPT_TEST)
                db.session.add(u)
                db.session.commit()
                # Creation département de Test
                d = models.Departement(acronym=TestConfig.DEPT_TEST)
                db.session.add(d)
                db.session.commit()
                app.set_sco_dept(TestConfig.DEPT_TEST)  # set db connection
                yield client
                ndb.close_db_connection()
                # Teardown:
                db.session.commit()
                db.session.remove()
                clear_scodoc_cache()
                # db.drop_all()
                # => laisse la base en état (l'efface au début)
                # utile pour les tests en cours de développement
