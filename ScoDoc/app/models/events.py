# -*- coding: UTF-8 -*

"""Evenements et logs divers
"""

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN


class Scolog(db.Model):
    """Log des actions (journal modif etudiants)"""

    __tablename__ = "scolog"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    method = db.Column(db.Text)
    msg = db.Column(db.Text)
    etudid = db.Column(db.Integer)  # sans contrainte pour garder logs après suppression
    authenticated_user = db.Column(db.Text)  # login, sans contrainte
    # zope_remote_addr suppressed


class ScolarNews(db.Model):
    """Nouvelles pour page d'accueil"""

    __tablename__ = "scolar_news"
    id = db.Column(db.Integer, primary_key=True)
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    authenticated_user = db.Column(db.Text)  # login, sans contrainte
    # type in 'INSCR', 'NOTES', 'FORM', 'SEM', 'MISC'
    type = db.Column(db.String(SHORT_STR_LEN))
    object = db.Column(db.Integer)  # moduleimpl_id, formation_id, formsemestre_id
    text = db.Column(db.Text)
    url = db.Column(db.Text)
