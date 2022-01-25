# -*- coding: UTF-8 -*

"""Notes, décisions de jury, évènements scolaires
"""

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN


class ScolarEvent(db.Model):
    """Evenement dans le parcours scolaire d'un étudiant"""

    __tablename__ = "scolar_events"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.synonym("id")
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    event_date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    ue_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_ue.id"),
    )
    # 'CREATION', 'INSCRIPTION', 'DEMISSION',
    # 'AUT_RED', 'EXCLUS', 'VALID_UE', 'VALID_SEM'
    # 'ECHEC_SEM'
    # 'UTIL_COMPENSATION'
    event_type = db.Column(db.String(SHORT_STR_LEN))
    # Semestre compensé par formsemestre_id:
    comp_formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )


class ScolarFormsemestreValidation(db.Model):
    """Décisions de jury"""

    __tablename__ = "scolar_formsemestre_validation"
    # Assure unicité de la décision:
    __table_args__ = (db.UniqueConstraint("etudid", "formsemestre_id", "ue_id"),)

    id = db.Column(db.Integer, primary_key=True)
    formsemestre_validation_id = db.synonym("id")
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    ue_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_ue.id"),
    )
    code = db.Column(db.String(CODE_STR_LEN), nullable=False)
    # NULL pour les UE, True|False pour les semestres:
    assidu = db.Column(db.Boolean)
    event_date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    # NULL sauf si compense un semestre:
    compense_formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    moy_ue = db.Column(db.Float)
    # (normalement NULL) indice du semestre, utile seulement pour
    # UE "antérieures" et si la formation définit des UE utilisées
    # dans plusieurs semestres (cas R&T IUTV v2)
    semestre_id = db.Column(db.Integer)
    # Si UE validée dans le cursus d'un autre etablissement
    is_external = db.Column(db.Boolean, default=False, server_default="false")


class ScolarAutorisationInscription(db.Model):
    """Autorisation d'inscription dans un semestre"""

    __tablename__ = "scolar_autorisation_inscription"
    id = db.Column(db.Integer, primary_key=True)
    autorisation_inscription_id = db.synonym("id")

    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    formation_code = db.Column(db.String(SHORT_STR_LEN), nullable=False)
    # semestre ou on peut s'inscrire:
    semestre_id = db.Column(db.Integer)
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    origin_formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )


class NotesAppreciations(db.Model):
    """Appréciations sur bulletins"""

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
        index=True,
    )
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    author = db.Column(db.Text)  # le pseudo (user_name), sans contrainte
    comment = db.Column(db.Text)  # texte libre


class NotesNotes(db.Model):
    """Une note"""

    __tablename__ = "notes_notes"
    __table_args__ = (db.UniqueConstraint("etudid", "evaluation_id"),)
    id = db.Column(db.Integer, primary_key=True)
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    evaluation_id = db.Column(
        db.Integer, db.ForeignKey("notes_evaluation.id"), index=True
    )
    value = db.Column(db.Float)
    # infos sur saisie de cette note:
    comment = db.Column(db.Text)  # texte libre
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    uid = db.Column(db.Integer, db.ForeignKey("user.id"))


class NotesNotesLog(db.Model):
    """Historique des modifs sur notes (anciennes entrees de notes_notes)"""

    __tablename__ = "notes_notes_log"
    id = db.Column(db.Integer, primary_key=True)

    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    evaluation_id = db.Column(
        db.Integer,
        # db.ForeignKey("notes_evaluation.id"),
        index=True,
    )
    value = db.Column(db.Float)
    # infos sur saisie de cette note:
    comment = db.Column(db.Text)  # texte libre
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    uid = db.Column(db.Integer, db.ForeignKey("user.id"))
