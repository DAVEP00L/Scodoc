# -*- coding: UTF-8 -*

"""Gestion des absences
"""

from app import db
from app.models import APO_CODE_STR_LEN
from app.models import SHORT_STR_LEN
from app.models import CODE_STR_LEN


class Entreprise(db.Model):
    """une entreprise"""

    __tablename__ = "entreprises"
    id = db.Column(db.Integer, primary_key=True)
    entreprise_id = db.synonym("id")
    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"), index=True)
    nom = db.Column(db.Text)
    adresse = db.Column(db.Text)
    ville = db.Column(db.Text)
    codepostal = db.Column(db.Text)
    pays = db.Column(db.Text)
    contact_origine = db.Column(db.Text)
    secteur = db.Column(db.Text)
    note = db.Column(db.Text)
    privee = db.Column(db.Text)
    localisation = db.Column(db.Text)
    # -1 inconnue, 0, 25, 50, 75, 100:
    qualite_relation = db.Column(db.Integer)
    plus10salaries = db.Column(db.Boolean())
    date_creation = db.Column(db.DateTime(timezone=True), server_default=db.func.now())


class EntrepriseCorrespondant(db.Model):
    """Personne contact en entreprise"""

    __tablename__ = "entreprise_correspondant"
    id = db.Column(db.Integer, primary_key=True)
    entreprise_corresp_id = db.synonym("id")
    entreprise_id = db.Column(db.Integer, db.ForeignKey("entreprises.id"))
    nom = db.Column(db.Text)
    prenom = db.Column(db.Text)
    civilite = db.Column(db.Text)
    fonction = db.Column(db.Text)
    phone1 = db.Column(db.Text)
    phone2 = db.Column(db.Text)
    mobile = db.Column(db.Text)
    mail1 = db.Column(db.Text)
    mail2 = db.Column(db.Text)
    fax = db.Column(db.Text)
    note = db.Column(db.Text)


class EntrepriseContact(db.Model):
    """Evènement (contact) avec une entreprise"""

    __tablename__ = "entreprise_contact"
    id = db.Column(db.Integer, primary_key=True)
    entreprise_contact_id = db.synonym("id")
    date = db.Column(db.DateTime(timezone=True))
    type_contact = db.Column(db.Text)
    entreprise_id = db.Column(db.Integer, db.ForeignKey("entreprises.id"))
    entreprise_corresp_id = db.Column(
        db.Integer, db.ForeignKey("entreprise_correspondant.id")
    )
    etudid = db.Column(db.Integer)  # sans contrainte pour garder logs après suppression
    description = db.Column(db.Text)
    enseignant = db.Column(db.Text)
