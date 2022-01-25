# -*- coding: UTF-8 -*

"""ScoDoc models : departements
"""
from typing import Any

from app import db
from app.models import SHORT_STR_LEN


class Departement(db.Model):
    """Un département ScoDoc"""

    id = db.Column(db.Integer, primary_key=True)
    acronym = db.Column(db.String(SHORT_STR_LEN), nullable=False, index=True)
    description = db.Column(db.Text())
    date_creation = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    visible = db.Column(
        db.Boolean(), nullable=False, default=True, server_default="true"
    )  # sur page d'accueil

    entreprises = db.relationship("Entreprise", lazy="dynamic", backref="departement")
    etudiants = db.relationship("Identite", lazy="dynamic", backref="departement")
    formations = db.relationship(
        "NotesFormation", lazy="dynamic", backref="departement"
    )
    formsemestres = db.relationship(
        "FormSemestre", lazy="dynamic", backref="departement"
    )
    preferences = db.relationship(
        "ScoPreference", lazy="dynamic", backref="departement"
    )
    semsets = db.relationship("NotesSemSet", lazy="dynamic", backref="departement")

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id}, acronym='{self.acronym}')>"

    def to_dict(self):
        data = {
            "id": self.id,
            "acronym": self.acronym,
            "description": self.description,
            "visible": self.visible,
            "date_creation": self.date_creation,
        }
        return data
