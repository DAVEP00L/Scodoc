# -*- coding: UTF-8 -*

"""Gestion des absences
"""

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN


class Absence(db.Model):
    """une absence (sur une demi-journée)"""

    __tablename__ = "absences"
    id = db.Column(db.Integer, primary_key=True)
    etudid = db.Column(db.Integer, db.ForeignKey("identite.id"), index=True)
    jour = db.Column(db.Date)
    estabs = db.Column(db.Boolean())
    estjust = db.Column(db.Boolean())
    matin = db.Column(db.Boolean())
    # motif de l'absence:
    description = db.Column(db.Text())
    entry_date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    # moduleimpid concerne (optionnel):
    moduleimpl_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_moduleimpl.id"),
    )
    # XXX TODO: contrainte ajoutée: vérifier suppression du module
    # (mettre à NULL sans supprimer)


class AbsenceNotification(db.Model):
    """Notification d'absence émise"""

    __tablename__ = "absences_notifications"

    id = db.Column(db.Integer, primary_key=True)
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    notification_date = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now()
    )
    email = db.Column(db.Text())
    nbabs = db.Column(db.Integer)
    nbabsjust = db.Column(db.Integer)
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id", ondelete="CASCADE"),
    )


class BilletAbsence(db.Model):
    """Billet d'absence (signalement par l'étudiant)"""

    __tablename__ = "billet_absence"

    id = db.Column(db.Integer, primary_key=True)
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
        index=True,
    )
    abs_begin = db.Column(db.DateTime(timezone=True))
    abs_end = db.Column(db.DateTime(timezone=True))
    # raison de l'absence:
    description = db.Column(db.Text())
    # False: new, True: processed
    etat = db.Column(db.Boolean(), default=False, server_default="false")
    entry_date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    # true si l'absence _pourrait_ etre justifiée
    justified = db.Column(db.Boolean(), default=False, server_default="false")

    def to_dict(self):
        data = {
            "id": self.id,
            "billet_id": self.id,
            "etudid": self.etudid,
            "abs_begin": self.abs_begin,
            "abs_end": self.abs_begin,
            "description": self.description,
            "etat": self.etat,
            "entry_date": self.entry_date,
            "justified": self.justified,
        }
        return data
