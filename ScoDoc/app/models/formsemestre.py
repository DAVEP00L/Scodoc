# -*- coding: UTF-8 -*

"""ScoDoc models
"""
from typing import Any

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN


class FormSemestre(db.Model):
    """Mise en oeuvre d'un semestre de formation
    was notes_formsemestre
    """

    __tablename__ = "notes_formsemestre"

    id = db.Column(db.Integer, primary_key=True)
    formsemestre_id = db.synonym("id")
    # dept_id est aussi dans la formation, ajouté ici pour
    # simplifier et accélérer les selects dans notesdb
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)
    formation_id = db.Column(db.Integer, db.ForeignKey("notes_formations.id"))
    semestre_id = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    titre = db.Column(db.Text())
    date_debut = db.Column(db.Date())
    date_fin = db.Column(db.Date())
    etat = db.Column(
        db.Boolean(), nullable=False, default=True, server_default="true"
    )  # False si verrouillé
    modalite = db.Column(
        db.String(SHORT_STR_LEN), db.ForeignKey("notes_form_modalites.modalite")
    )
    # gestion compensation sem DUT:
    gestion_compensation = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="false"
    )
    # ne publie pas le bulletin XML:
    bul_hide_xml = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="false"
    )
    # Bloque le calcul des moyennes (générale et d'UE)
    block_moyennes = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="false"
    )
    # semestres decales (pour gestion jurys):
    gestion_semestrielle = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="false"
    )
    # couleur fond bulletins HTML:
    bul_bgcolor = db.Column(
        db.String(SHORT_STR_LEN), default="white", server_default="white"
    )
    # autorise resp. a modifier semestre:
    resp_can_edit = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="false"
    )
    # autorise resp. a modifier slt les enseignants:
    resp_can_change_ens = db.Column(
        db.Boolean(), nullable=False, default=True, server_default="true"
    )
    # autorise les ens a creer des evals:
    ens_can_edit_eval = db.Column(
        db.Boolean(), nullable=False, default=False, server_default="False"
    )
    # code element semestre Apogee, eg 'VRTW1' ou 'V2INCS4,V2INLS4,...'
    elt_sem_apo = db.Column(db.Text())  # peut être fort long !
    # code element annee Apogee, eg 'VRT1A' ou 'V2INLA,V2INCA,...'
    elt_annee_apo = db.Column(db.Text())

    # Relations:
    etapes = db.relationship(
        "NotesFormsemestreEtape", cascade="all,delete", backref="formsemestre"
    )
    formsemestres = db.relationship(
        "NotesModuleImpl", backref="formsemestre", lazy="dynamic"
    )

    # Ancien id ScoDoc7 pour les migrations de bases anciennes
    # ne pas utiliser après migrate_scodoc7_dept_archives
    scodoc7_id = db.Column(db.Text(), nullable=True)

    def __init__(self, **kwargs):
        super(FormSemestre, self).__init__(**kwargs)
        if self.modalite is None:
            self.modalite = NotesFormModalite.DEFAULT_MODALITE


# Association id des utilisateurs responsables (aka directeurs des etudes) du semestre
notes_formsemestre_responsables = db.Table(
    "notes_formsemestre_responsables",
    db.Column(
        "formsemestre_id",
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    ),
    db.Column("responsable_id", db.Integer, db.ForeignKey("user.id")),
)


class NotesFormsemestreEtape(db.Model):
    """Étape Apogée associées au semestre"""

    __tablename__ = "notes_formsemestre_etapes"
    id = db.Column(db.Integer, primary_key=True)
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    etape_apo = db.Column(db.String(APO_CODE_STR_LEN))


class NotesFormModalite(db.Model):
    """Modalités de formation, utilisées pour la présentation
    (grouper les semestres, générer des codes, etc.)
    """

    __tablename__ = "notes_form_modalites"

    DEFAULT_MODALITE = "FI"

    id = db.Column(db.Integer, primary_key=True)
    modalite = db.Column(
        db.String(SHORT_STR_LEN),
        unique=True,
        index=True,
        default=DEFAULT_MODALITE,
        server_default=DEFAULT_MODALITE,
    )  # code
    titre = db.Column(db.Text())  # texte explicatif
    # numero = ordre de presentation)
    numero = db.Column(db.Integer)

    @staticmethod
    def insert_modalites():
        """Create default modalities"""
        numero = 0
        try:
            for (code, titre) in (
                (NotesFormModalite.DEFAULT_MODALITE, "Formation Initiale"),
                ("FAP", "Apprentissage"),
                ("FC", "Formation Continue"),
                ("DEC", "Formation Décalées"),
                ("LIC", "Licence"),
                ("CPRO", "Contrats de Professionnalisation"),
                ("DIST", "À distance"),
                ("ETR", "À l'étranger"),
                ("EXT", "Extérieur"),
                ("OTHER", "Autres formations"),
            ):
                modalite = NotesFormModalite.query.filter_by(modalite=code).first()
                if modalite is None:
                    modalite = NotesFormModalite(
                        modalite=code, titre=titre, numero=numero
                    )
                    db.session.add(modalite)
                    numero += 1
            db.session.commit()
        except:
            db.session.rollback()
            raise


class NotesFormsemestreUECoef(db.Model):
    """Coef des UE capitalisees arrivant dans ce semestre"""

    __tablename__ = "notes_formsemestre_uecoef"
    __table_args__ = (db.UniqueConstraint("formsemestre_id", "ue_id"),)

    id = db.Column(db.Integer, primary_key=True)
    formsemestre_uecoef_id = db.synonym("id")
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    ue_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_ue.id"),
    )
    coefficient = db.Column(db.Float, nullable=False)


class NotesFormsemestreUEComputationExpr(db.Model):
    """Formules utilisateurs pour calcul moyenne UE"""

    __tablename__ = "notes_formsemestre_ue_computation_expr"
    __table_args__ = (db.UniqueConstraint("formsemestre_id", "ue_id"),)

    id = db.Column(db.Integer, primary_key=True)
    notes_formsemestre_ue_computation_expr_id = db.synonym("id")
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    ue_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_ue.id"),
    )
    # formule de calcul moyenne
    computation_expr = db.Column(db.Text())


class NotesFormsemestreCustomMenu(db.Model):
    """Menu custom associe au semestre"""

    __tablename__ = "notes_formsemestre_custommenu"

    id = db.Column(db.Integer, primary_key=True)
    custommenu_id = db.synonym("id")
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    title = db.Column(db.Text())
    url = db.Column(db.Text())
    idx = db.Column(db.Integer, default=0, server_default="0")  #  rang dans le menu


class NotesFormsemestreInscription(db.Model):
    """Inscription à un semestre de formation"""

    __tablename__ = "notes_formsemestre_inscription"
    __table_args__ = (db.UniqueConstraint("formsemestre_id", "etudid"),)

    id = db.Column(db.Integer, primary_key=True)
    formsemestre_inscription_id = db.synonym("id")

    etudid = db.Column(db.Integer, db.ForeignKey("identite.id"))
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
    )
    # I inscrit, D demission en cours de semestre, DEF si "defaillant"
    etat = db.Column(db.String(CODE_STR_LEN))
    # etape apogee d'inscription (experimental 2020)
    etape = db.Column(db.String(APO_CODE_STR_LEN))


class NotesModuleImpl(db.Model):
    """Mise en oeuvre d'un module pour une annee/semestre"""

    __tablename__ = "notes_moduleimpl"
    __table_args__ = (db.UniqueConstraint("formsemestre_id", "module_id"),)

    id = db.Column(db.Integer, primary_key=True)
    moduleimpl_id = db.synonym("id")
    module_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_modules.id"),
    )
    formsemestre_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_formsemestre.id"),
        index=True,
    )
    responsable_id = db.Column("responsable_id", db.Integer, db.ForeignKey("user.id"))
    # formule de calcul moyenne:
    computation_expr = db.Column(db.Text())


# Enseignants (chargés de TD ou TP) d'un moduleimpl
notes_modules_enseignants = db.Table(
    "notes_modules_enseignants",
    db.Column(
        "moduleimpl_id",
        db.Integer,
        db.ForeignKey("notes_moduleimpl.id"),
    ),
    db.Column("ens_id", db.Integer, db.ForeignKey("user.id")),
    # ? db.UniqueConstraint("moduleimpl_id", "ens_id"),
)
# XXX il manque probablement une relation pour gérer cela


class NotesModuleImplInscription(db.Model):
    """Inscription à un module  (etudiants,moduleimpl)"""

    __tablename__ = "notes_moduleimpl_inscription"
    __table_args__ = (db.UniqueConstraint("moduleimpl_id", "etudid"),)

    id = db.Column(db.Integer, primary_key=True)
    moduleimpl_inscription_id = db.synonym("id")
    moduleimpl_id = db.Column(
        db.Integer,
        db.ForeignKey("notes_moduleimpl.id"),
        index=True,
    )
    etudid = db.Column(db.Integer, db.ForeignKey("identite.id"), index=True)


class NotesEvaluation(db.Model):
    """Evaluation (contrôle, examen, ...)"""

    __tablename__ = "notes_evaluation"

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.synonym("id")
    moduleimpl_id = db.Column(
        db.Integer, db.ForeignKey("notes_moduleimpl.id"), index=True
    )
    jour = db.Column(db.Date)
    heure_debut = db.Column(db.Time)
    heure_fin = db.Column(db.Time)
    description = db.Column(db.Text)
    note_max = db.Column(db.Float)
    coefficient = db.Column(db.Float)
    visibulletin = db.Column(
        db.Boolean, nullable=False, default=True, server_default="true"
    )
    publish_incomplete = db.Column(
        db.Boolean, nullable=False, default=False, server_default="false"
    )
    # type d'evaluation: 0 normale, 1 rattrapage, 2 "2eme session"
    evaluation_type = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    # ordre de presentation (par défaut, le plus petit numero
    # est la plus ancienne eval):
    numero = db.Column(db.Integer)


class NotesSemSet(db.Model):
    """semsets: ensemble de formsemestres pour exports Apogée"""

    __tablename__ = "notes_semset"

    id = db.Column(db.Integer, primary_key=True)
    semset_id = db.synonym("id")
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"))

    title = db.Column(db.Text)
    annee_scolaire = db.Column(db.Integer, nullable=True, default=None)
    # periode: 0 (année), 1 (Simpair), 2 (Spair)
    sem_id = db.Column(db.Integer, nullable=True, default=None)


# Association: many to many
notes_semset_formsemestre = db.Table(
    "notes_semset_formsemestre",
    db.Column("formsemestre_id", db.Integer, db.ForeignKey("notes_formsemestre.id")),
    db.Column(
        "semset_id",
        db.Integer,
        db.ForeignKey("notes_semset.id", ondelete="CASCADE"),
        nullable=False,
    ),
    db.UniqueConstraint("formsemestre_id", "semset_id"),
)
