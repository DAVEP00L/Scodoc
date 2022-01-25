# -*- coding: utf-8 -*-

"""Test ORM departement/formation/preferences


Utiliser comme: 
    pytest tests/unit/test_departements.py

"""
from flask import g
import app
from app import db
from app.models import Departement, ScoPreference, FormSemestre, formsemestre
from app.scodoc import notesdb as ndb
from app.scodoc import sco_formsemestre
from app.scodoc import sco_preferences
from tests.unit import test_sco_basic


def test_preferences_orm(test_client):
    """preferences, via ORM and legacy ScoDoc"""
    d = Departement(acronym="TT")
    p1 = ScoPreference(name="temperature", value="24", departement=d)
    p2 = ScoPreference(name="couleur", value="bleue", departement=d)
    db.session.add(d)
    db.session.add(p1)
    db.session.add(p2)
    db.session.commit()
    prefs = d.preferences.all()
    assert isinstance(prefs, list)
    assert len(prefs) == 2


def test_preferences(test_client):
    """ScoDoc preferences"""
    # preferences "globales" d'un département:
    current_dept = Departement.query.filter_by(acronym=g.scodoc_dept).first()
    prefs = sco_preferences.get_base_preferences()
    assert isinstance(prefs, sco_preferences.BasePreferences)
    assert prefs.dept_id == current_dept.id
    # Compare nombre de d'items
    assert len(ScoPreference.query.filter_by(dept_id=current_dept.id).all()) == len(
        prefs
    )
    # Accès à une valeur via ORM
    assert (
        len(
            ScoPreference.query.filter_by(
                dept_id=current_dept.id, name="abs_notification_mail_tmpl"
            ).all()
        )
        == 1
    )
    orm_val = (
        ScoPreference.query.filter_by(
            dept_id=current_dept.id, name="abs_notification_mail_tmpl"
        )
        .first()
        .value
    )
    # Compare valeurs
    sco_val = prefs.get(None, "abs_notification_mail_tmpl")
    assert orm_val.strip() == sco_val.strip()
    # nb: I don't understand why SQLAlchemy strips the string ?!

    # --- Charge dans un autre département
    # departement fictif créé ici:
    d = Departement(acronym="D2")
    db.session.add(d)
    db.session.commit()
    app.set_sco_dept("D2")
    prefs2 = sco_preferences.get_base_preferences()
    assert len(prefs2) == len(prefs)
    prefs2.set(None, "abs_notification_mail_tmpl", "toto")
    assert prefs2.get(None, "abs_notification_mail_tmpl") == "toto"
    # Vérifie que les prefs sont bien sur un seul département:
    app.set_sco_dept(current_dept.acronym)
    assert prefs.get(None, "abs_notification_mail_tmpl") != "toto"
    orm_val = (
        ScoPreference.query.filter_by(dept_id=d.id, name="abs_notification_mail_tmpl")
        .first()
        .value
    )
    assert orm_val == "toto"
    # --- Preferences d'un semestre
    # rejoue ce test pour avoir un semestre créé
    app.set_sco_dept("D2")
    test_sco_basic.run_sco_basic()
    sem = sco_formsemestre.do_formsemestre_list()[0]
    formsemestre_id = sem["formsemestre_id"]
    semp = sco_preferences.SemPreferences(formsemestre_id=formsemestre_id)
    assert semp["abs_notification_mail_tmpl"] == "toto"
    assert semp.is_global("abs_notification_mail_tmpl")
    # donne une valeur pour le semestre:
    prefs2.set(formsemestre_id, "abs_notification_mail_tmpl", "foo")
    assert not semp.is_global("abs_notification_mail_tmpl")
    assert semp["abs_notification_mail_tmpl"] == "foo"
