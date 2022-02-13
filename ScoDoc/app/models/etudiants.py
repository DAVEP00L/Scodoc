# -*- coding: UTF-8 -*

"""Définition d'un étudiant
    et données rattachées (adresses, annotations, ...)
"""

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN


class Identite(db.Model):
    """étudiant"""

    __tablename__ = "identite"
    __table_args__ = (
        db.UniqueConstraint("dept_id", "code_nip"),
        db.UniqueConstraint("dept_id", "code_ine"),
    )

    id = db.Column(db.Integer, primary_key=True)
    etudid = db.synonym("id")
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)

    nom = db.Column(db.Text())
    prenom = db.Column(db.Text())
    nom_usuel = db.Column(db.Text())
    # optionnel (si present, affiché à la place du nom)
    civilite = db.Column(db.String(1), nullable=False)
    __table_args__ = (db.CheckConstraint("civilite IN ('M', 'F', 'X')"),)

    date_naissance = db.Column(db.Date)
    lieu_naissance = db.Column(db.Text())
    dept_naissance = db.Column(db.Text())
    nationalite = db.Column(db.Text())
    statut = db.Column(db.Text())
    boursier = db.Column(db.Boolean())  # True si boursier ('O' en ScoDoc7)
    photo_filename = db.Column(db.Text())
    # Codes INE et NIP pas unique car le meme etud peut etre ds plusieurs dept
    code_nip = db.Column(db.Text())
    code_ine = db.Column(db.Text())
    # Ancien id ScoDoc7 pour les migrations de bases anciennes
    # ne pas utiliser après migrate_scodoc7_dept_archives
    scodoc7_id = db.Column(db.Text(), nullable=True)
    #
    billets = db.relationship("BilletAbsence", backref="etudiant", lazy="dynamic")


class Adresse(db.Model):
    """Adresse d'un étudiant
    (le modèle permet plusieurs adresses, mais l'UI n'en gère qu'une seule)
    """

    __tablename__ = "adresse"

    id = db.Column(db.Integer, primary_key=True)
    adresse_id = db.synonym("id")
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    email = db.Column(db.Text())  # mail institutionnel
    emailperso = db.Column(db.Text)  # email personnel (exterieur)
    domicile = db.Column(db.Text)
    codepostaldomicile = db.Column(db.Text)
    villedomicile = db.Column(db.Text)
    paysdomicile = db.Column(db.Text)
    telephone = db.Column(db.Text)
    telephonemobile = db.Column(db.Text)
    fax = db.Column(db.Text)
    typeadresse = db.Column(
        db.Text, default="domicile", server_default="domicile", nullable=False
    )
    description = db.Column(db.Text)


class Admission(db.Model):
    """Informations liées à l'admission d'un étudiant"""

    __tablename__ = "admissions"

    id = db.Column(db.Integer, primary_key=True)
    adm_id = db.synonym("id")
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    # Anciens champs de ScoDoc7, à revoir pour être plus générique et souple
    # notamment dans le cadre du bac 2021
    # de plus, certaines informations liées à APB ne sont plus disponibles
    # avec Parcoursup
    contrat = db.Column(db.Boolean())       #contrat d'etude
    annee = db.Column(db.Integer)
    bac = db.Column(db.Text)
    specialite = db.Column(db.Text)
    annee_bac = db.Column(db.Integer)
    math = db.Column(db.Text)
    physique = db.Column(db.Float)
    anglais = db.Column(db.Float)
    francais = db.Column(db.Float)
    # Qualité et décision du jury d'admission (ou de l'examinateur)
    qualite = db.Column(db.Float)
    rapporteur = db.Column(db.Text)
    decision = db.Column(db.Text)
    score = db.Column(db.Float)
    commentaire = db.Column(db.Text)
    # Rang dans les voeux du candidat (inconnu avec APB et PS)
    rang = db.Column(db.Integer)
    # 'APB', 'APC-PC', 'CEF', 'Direct', '?' (autre)
    type_admission = db.Column(db.Text)
    #Etablissement d'origine:
    nomlycee = db.Column(db.Text)
    villelycee = db.Column(db.Text)
    codepostallycee = db.Column(db.Text)
    codelycee = db.Column(db.Text)
    # était boursier dans le cycle precedent (lycee) ?
    boursier_prec = db.Column(db.Boolean())
    # classement par le jury d'admission (1 à N),
    # global (pas celui d'APB si il y a des groupes)
    classement = db.Column(db.Integer)
    # code du groupe APB
    apb_groupe = db.Column(db.Text)
    # classement (1..Ngr) par le jury dans le groupe APB
    apb_classement_gr = db.Column(db.Integer)


# Suivi scolarité / débouchés
class ItemSuivi(db.Model):
    __tablename__ = "itemsuivi"

    id = db.Column(db.Integer, primary_key=True)
    itemsuivi_id = db.synonym("id")
    etudid = db.Column(
        db.Integer,
        db.ForeignKey("identite.id"),
    )
    item_date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    situation = db.Column(db.Text)


class ItemSuiviTag(db.Model):
    __tablename__ = "itemsuivi_tags"
    id = db.Column(db.Integer, primary_key=True)
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)
    tag_id = db.synonym("id")
    title = db.Column(db.Text(), nullable=False, unique=True)


# Association tag <-> module
itemsuivi_tags_assoc = db.Table(
    "itemsuivi_tags_assoc",
    db.Column(
        "tag_id", db.Integer, db.ForeignKey("itemsuivi_tags.id", ondelete="CASCADE")
    ),
    db.Column(
        "itemsuivi_id", db.Integer, db.ForeignKey("itemsuivi.id", ondelete="CASCADE")
    ),
)


class EtudAnnotation(db.Model):
    """Annotation sur un étudiant"""

    __tablename__ = "etud_annotations"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    etudid = db.Column(db.Integer)  # sans contrainte (compat ScoDoc 7))
    author = db.Column(db.Text)  # le pseudo (user_name), was zope_authenticated_user
    comment = db.Column(db.Text)
