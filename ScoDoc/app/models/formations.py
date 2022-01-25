"""ScoDoc8 models : Formations (hors BUT)
"""
from typing import Any

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN


class NotesFormation(db.Model):
    """Programme pédagogique d'une formation"""

    __tablename__ = "notes_formations"
    __table_args__ = (db.UniqueConstraint("dept_id", "acronyme", "titre", "version"),)

    id = db.Column(db.Integer, primary_key=True)
    formation_id = db.synonym("id")
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)

    acronyme = db.Column(db.Text(), nullable=False)
    titre = db.Column(db.Text(), nullable=False)
    titre_officiel = db.Column(db.Text(), nullable=False)
    version = db.Column(db.Integer, default=1, server_default="1")
    formation_code = db.Column(
        db.String(SHORT_STR_LEN),
        server_default=db.text("notes_newid_fcod()"),
        nullable=False,
    )
    # nb: la fonction SQL notes_newid_fcod doit être créée à part
    type_parcours = db.Column(db.Integer, default=0, server_default="0")
    code_specialite = db.Column(db.String(SHORT_STR_LEN))

    ues = db.relationship("NotesUE", backref="formation", lazy="dynamic")
    formsemestres = db.relationship("FormSemestre", lazy="dynamic", backref="formation")
    ues = db.relationship("NotesUE", lazy="dynamic", backref="formation")

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id}, dept_id={self.dept_id}, acronyme='{self.acronyme}')>"


class NotesUE(db.Model):
    """Unité d'Enseignement"""

    __tablename__ = "notes_ue"

    id = db.Column(db.Integer, primary_key=True)
    ue_id = db.synonym("id")
    formation_id = db.Column(db.Integer, db.ForeignKey("notes_formations.id"))
    acronyme = db.Column(db.Text(), nullable=False)
    numero = db.Column(db.Integer)  # ordre de présentation
    titre = db.Column(db.Text())
    # Type d'UE: 0 normal ("fondamentale"), 1 "sport", 2 "projet et stage (LP)",
    # 4 "élective"
    type = db.Column(db.Integer, default=0, server_default="0")
    # Les UE sont "compatibles" (pour la capitalisation) ssi elles ont ^m code
    # note: la fonction SQL notes_newid_ucod doit être créée à part
    ue_code = db.Column(
        db.String(SHORT_STR_LEN),
        server_default=db.text("notes_newid_ucod()"),
        nullable=False,
    )
    ects = db.Column(db.Float)  # nombre de credits ECTS
    is_external = db.Column(db.Boolean(), default=False, server_default="false")
    # id de l'element pedagogique Apogee correspondant:
    code_apogee = db.Column(db.String(APO_CODE_STR_LEN))
    # coef UE, utilise seulement si l'option use_ue_coefs est activée:
    coefficient = db.Column(db.Float)

    # relations
    matieres = db.relationship("NotesMatiere", lazy="dynamic", backref="ue")
    modules = db.relationship("NotesModule", lazy="dynamic", backref="ue")

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id}, formation_id={self.formation_id}, acronyme='{self.acronyme}')>"


class NotesMatiere(db.Model):
    """Matières: regroupe les modules d'une UE
    La matière a peu d'utilité en dehors de la présentation des modules
    d'une UE.
    """

    __tablename__ = "notes_matieres"
    __table_args__ = (db.UniqueConstraint("ue_id", "titre"),)

    id = db.Column(db.Integer, primary_key=True)
    matiere_id = db.synonym("id")
    ue_id = db.Column(db.Integer, db.ForeignKey("notes_ue.id"))
    titre = db.Column(db.Text())
    numero = db.Column(db.Integer)  # ordre de présentation

    modules = db.relationship("NotesModule", lazy="dynamic", backref="matiere")


class NotesModule(db.Model):
    """Module"""

    __tablename__ = "notes_modules"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.synonym("id")
    titre = db.Column(db.Text())
    abbrev = db.Column(db.Text())  # nom court
    # certains départements ont des codes infiniment longs: donc Text !
    code = db.Column(db.Text(), nullable=False)
    heures_cours = db.Column(db.Float)
    heures_td = db.Column(db.Float)
    heures_tp = db.Column(db.Float)
    coefficient = db.Column(db.Float)  # coef PPN
    ects = db.Column(db.Float)  # Crédits ECTS
    ue_id = db.Column(db.Integer, db.ForeignKey("notes_ue.id"), index=True)
    formation_id = db.Column(db.Integer, db.ForeignKey("notes_formations.id"))
    matiere_id = db.Column(db.Integer, db.ForeignKey("notes_matieres.id"))
    # pas un id mais le numéro du semestre: 1, 2, ...
    semestre_id = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    numero = db.Column(db.Integer)  # ordre de présentation
    # id de l'element pedagogique Apogee correspondant:
    code_apogee = db.Column(db.String(APO_CODE_STR_LEN))
    module_type = db.Column(db.Integer)  # NULL ou 0:defaut, 1: malus (NOTES_MALUS)
    # Relations:
    modimpls = db.relationship("NotesModuleImpl", backref="module", lazy="dynamic")


class NotesTag(db.Model):
    """Tag sur un module"""

    __tablename__ = "notes_tags"
    __table_args__ = (db.UniqueConstraint("title", "dept_id"),)

    id = db.Column(db.Integer, primary_key=True)
    tag_id = db.synonym("id")

    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)
    title = db.Column(db.Text(), nullable=False)


# Association tag <-> module
notes_modules_tags = db.Table(
    "notes_modules_tags",
    db.Column(
        "tag_id",
        db.Integer,
        db.ForeignKey("notes_tags.id", ondelete="CASCADE"),
    ),
    db.Column(
        "module_id", db.Integer, db.ForeignKey("notes_modules.id", ondelete="CASCADE")
    ),
)
