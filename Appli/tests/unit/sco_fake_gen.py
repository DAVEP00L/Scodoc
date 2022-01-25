# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Creation environnement pour test.
A utiliser avec debug.py (côté serveur).

La classe ScoFake offre un ensemble de raccourcis permettant d'écrire
facilement des tests ou de reproduire des bugs.
"""

from functools import wraps
import random
import sys
import string
import typing


from config import Config
from app.auth.models import User
from app.models import NotesFormModalite
from app.scodoc import notesdb as ndb
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_edit_formation
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_etud
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_formsemestre_validation
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_saisie_notes
from app.scodoc import sco_synchro_etuds
from app.scodoc import sco_utils as scu
from app import log
from app.scodoc.sco_exceptions import ScoValueError

random.seed(12345)  # tests reproductibles


NOMS_DIR = Config.SCODOC_DIR + "/tools/fakeportal/nomsprenoms"
NOMS = [x.strip() for x in open(NOMS_DIR + "/noms.txt").readlines()]
PRENOMS_H = [x.strip() for x in open(NOMS_DIR + "/prenoms-h.txt").readlines()]
PRENOMS_F = [x.strip() for x in open(NOMS_DIR + "/prenoms-f.txt").readlines()]
PRENOMS_X = [x.strip() for x in open(NOMS_DIR + "/prenoms-x.txt").readlines()]


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def logging_meth(func):
    @wraps(func)
    def wrapper_logging_meth(self, *args, **kwargs):
        r = func(self, *args, **kwargs)
        # self.log("%s(%s) -> \n%s" % (func.__name__, kwargs, pprint.pformat(r)))
        return r

    return wrapper_logging_meth


class ScoFake(object):
    """Helper for ScoDoc tests"""

    def __init__(self, verbose=True):
        self.verbose = verbose
        self.default_user = User.query.filter_by(user_name="bach").first()
        if not self.default_user:
            raise ScoValueError('User test "bach" not found !')

    def log(self, msg):
        if self.verbose:
            print("ScoFake: " + str(msg), file=sys.stderr)
            sys.stderr.flush()
        log("ScoFake: " + str(msg))

    def civilitenomprenom(self):
        """un nom et un prenom au hasard,
        toujours en majuscules.
        """
        civilite = random.choice(("M", "M", "M", "F", "F", "F", "X"))
        if civilite == "F":
            prenom = random.choice(PRENOMS_F)
        elif civilite == "M":
            prenom = random.choice(PRENOMS_H)
        elif civilite == "X":
            prenom = random.choice(PRENOMS_X)
        else:
            raise ValueError("invalid civilite value")
        return civilite, random.choice(NOMS).upper(), prenom.upper()

    @logging_meth
    def create_etud(
        self,
        cnx=None,
        code_nip="",
        nom="",
        prenom="",
        code_ine="",
        civilite="",
        etape="TST1",
        email="test@localhost",
        emailperso="perso@localhost",
        date_naissance="01/01/2001",
        lieu_naissance="Paris",
        dept_naissance="75",
        domicile="1, rue du test",
        codepostaldomicile="75123",
        villedomicile="TestCity",
        paysdomicile="France",
        telephone="0102030405",
        typeadresse="domicile",
        boursier=None,
        description="etudiant test",
    ):
        """Crée un étudiant"""
        if not cnx:
            cnx = ndb.GetDBConnexion()
        if code_nip == "":
            code_nip = str(random.randint(10000, 99999))
        if not civilite or not nom or not prenom:
            r_civilite, r_nom, r_prenom = self.civilitenomprenom()
            if not civilite:
                civilite = r_civilite
            if not nom:
                nom = r_nom
            if not prenom:
                prenom = r_prenom
        etud = sco_etud.create_etud(cnx, args=locals())
        inscription = "2020"  # pylint: disable=possibly-unused-variable
        sco_synchro_etuds.do_import_etud_admission(cnx, etud["etudid"], locals())
        return etud

    @logging_meth
    def create_formation(
        self,
        acronyme="test",
        titre="Formation test",
        titre_officiel="Le titre officiel de la formation test",
        type_parcours=sco_codes_parcours.ParcoursDUT.TYPE_PARCOURS,
        formation_code=None,
        code_specialite=None,
    ):
        """Crée une formation"""
        if not acronyme:
            acronyme = "TEST" + str(random.randint(100000, 999999))
        oid = sco_edit_formation.do_formation_create(locals())
        oids = sco_formations.formation_list(formation_id=oid)
        if not oids:
            raise ScoValueError("formation not created !")
        return oids[0]

    @logging_meth
    def create_ue(
        self,
        formation_id=None,
        acronyme=None,
        numero=None,
        titre="",
        type=None,
        ue_code=None,
        ects=None,
        is_external=None,
        code_apogee=None,
        coefficient=None,
    ):
        """Crée une UE"""
        if numero is None:
            numero = sco_edit_ue.next_ue_numero(formation_id, 0)
        oid = sco_edit_ue.do_ue_create(locals())
        oids = sco_edit_ue.ue_list(args={"ue_id": oid})
        if not oids:
            raise ScoValueError("ue not created !")
        return oids[0]

    @logging_meth
    def create_matiere(self, ue_id=None, titre=None, numero=None):
        oid = sco_edit_matiere.do_matiere_create(locals())
        oids = sco_edit_matiere.matiere_list(args={"matiere_id": oid})
        if not oids:
            raise ScoValueError("matiere not created !")
        return oids[0]

    @logging_meth
    def create_module(
        self,
        titre=None,
        code=None,
        heures_cours=None,
        heures_td=None,
        heures_tp=None,
        coefficient=None,
        ue_id=None,
        formation_id=None,
        matiere_id=None,
        semestre_id=1,
        numero=None,
        abbrev=None,
        ects=None,
        code_apogee=None,
        module_type=None,
    ):
        oid = sco_edit_module.do_module_create(locals())
        oids = sco_edit_module.module_list(args={"module_id": oid})
        if not oids:
            raise ScoValueError("module not created ! (oid=%s)" % oid)
        return oids[0]

    @logging_meth
    def create_formsemestre(
        self,
        formation_id=None,
        semestre_id=None,
        titre=None,
        date_debut=None,
        date_fin=None,
        etat=None,
        gestion_compensation=None,
        bul_hide_xml=None,
        block_moyennes=None,
        gestion_semestrielle=None,
        bul_bgcolor=None,
        modalite=NotesFormModalite.DEFAULT_MODALITE,
        resp_can_edit=None,
        resp_can_change_ens=None,
        ens_can_edit_eval=None,
        elt_sem_apo=None,
        elt_annee_apo=None,
        etapes=None,
        responsables=None,  # sequence of resp. ids
    ):
        if responsables is None:
            responsables = (self.default_user.id,)
        oid = sco_formsemestre.do_formsemestre_create(locals())
        oids = sco_formsemestre.do_formsemestre_list(
            args={"formsemestre_id": oid}
        )  # API inconsistency
        if not oids:
            raise ScoValueError("formsemestre not created !")
        return oids[0]

    @logging_meth
    def create_moduleimpl(
        self,
        module_id: int = None,
        formsemestre_id: int = None,
        responsable_id: typing.Optional[int] = None,
    ):
        if not responsable_id:
            responsable_id = self.default_user.id
        oid = sco_moduleimpl.do_moduleimpl_create(locals())
        oids = sco_moduleimpl.moduleimpl_list(moduleimpl_id=oid)  # API inconsistency
        if not oids:
            raise ScoValueError("moduleimpl not created !")
        return oids[0]

    @logging_meth
    def inscrit_etudiant(self, sem, etud):
        sco_formsemestre_inscriptions.do_formsemestre_inscription_with_modules(
            sem["formsemestre_id"],
            etud["etudid"],
            etat="I",
            etape=etud.get("etape", None),
            method="test_inscrit_etudiant",
        )

    @logging_meth
    def create_evaluation(
        self,
        moduleimpl_id=None,
        jour=None,
        heure_debut="8h00",
        heure_fin="9h00",
        description=None,
        note_max=20,
        coefficient=None,
        visibulletin=None,
        publish_incomplete=None,
        evaluation_type=None,
        numero=None,
    ):
        args = locals()
        del args["self"]
        oid = sco_evaluations.do_evaluation_create(**args)
        oids = sco_evaluations.do_evaluation_list(args={"evaluation_id": oid})
        if not oids:
            raise ScoValueError("evaluation not created !")
        return oids[0]

    @logging_meth
    def create_note(
        self,
        evaluation=None,
        etud=None,
        note=None,
        comment=None,
        user=None,  # User instance
    ):
        if user is None:
            user = self.default_user
        return sco_saisie_notes._notes_add(
            user,
            evaluation["evaluation_id"],
            [(etud["etudid"], note)],
            comment=comment,
        )

    def setup_formation(
        self,
        nb_semestre=1,
        nb_ue_per_semestre=2,
        nb_module_per_ue=2,
        acronyme=None,
        titre=None,
    ):
        """Création d'une formation, avec UE, modules et évaluations.

        Formation avec `nb_semestre` comportant chacun `nb_ue_per_semestre` UE
        et dans chaque UE `nb_module_per_ue` modules (on a une seule matière par UE).

        Returns:
            formation (dict), liste d'ue (dicts), liste de modules.
        """
        f = self.create_formation(acronyme=acronyme, titre=titre)
        ues = []
        mod_list = []
        for semestre_id in range(1, nb_semestre + 1):
            for n in range(1, nb_ue_per_semestre + 1):
                ue = self.create_ue(
                    formation_id=f["formation_id"],
                    acronyme="TSU%s%s" % (semestre_id, n),
                    titre="ue test %s%s" % (semestre_id, n),
                )
                ues.append(ue)
                mat = self.create_matiere(ue_id=ue["ue_id"], titre="matière test")
                for _ in range(nb_module_per_ue):
                    mod = self.create_module(
                        matiere_id=mat["matiere_id"],
                        semestre_id=semestre_id,
                        code="TSM%s" % len(mod_list),
                        coefficient=1.0,
                        titre="module test",
                        ue_id=ue["ue_id"],  # faiblesse de l'API
                        formation_id=f["formation_id"],  # faiblesse de l'API
                    )
                    mod_list.append(mod)
        return f, ues, mod_list

    def setup_formsemestre(
        self,
        f,
        mod_list,
        semestre_id=1,
        date_debut="01/01/2020",
        date_fin="30/06/2020",
        nb_evaluations_per_module=1,
        titre=None,
        responsables=None,  # list of users ids
        modalite=None,
    ):
        """Création semestre, avec modules et évaluations."""
        sem = self.create_formsemestre(
            formation_id=f["formation_id"],
            semestre_id=semestre_id,
            date_debut=date_debut,
            date_fin=date_fin,
            titre=titre,
            responsables=responsables,
            modalite=modalite,
        )
        eval_list = []
        for mod in mod_list:
            if mod["semestre_id"] == semestre_id:
                mi = self.create_moduleimpl(
                    module_id=mod["module_id"],
                    formsemestre_id=sem["formsemestre_id"],
                    responsable_id="bach",
                )
                for e_idx in range(1, nb_evaluations_per_module + 1):
                    e = self.create_evaluation(
                        moduleimpl_id=mi["moduleimpl_id"],
                        jour=date_debut,
                        description="evaluation test %s" % e_idx,
                        coefficient=1.0,
                    )
                    eval_list.append(e)
        return sem, eval_list

    def set_etud_notes_sem(
        self, sem, eval_list, etuds, notes=None, random_min=0, random_max=20
    ):
        """Met des notes aux étudiants indiqués des evals indiquées.

        Args:
            sem: dict
            eval_list: list of dicts
            etuds: list of dicts
            notes: liste des notes (float).
            Si non spécifié, tire au hasard dans `[random_min, random_max]`
        """
        set_random = notes is None
        for e in eval_list:
            if set_random:
                notes = [float(random.randint(random_min, random_max)) for _ in etuds]
            for etud, note in zip(etuds, notes):
                self.create_note(evaluation=e, etud=etud, note=note)

    def set_code_jury(
        self,
        sem,
        etud,
        code_etat=sco_codes_parcours.ADM,
        devenir=sco_codes_parcours.NEXT,
        assidu=True,
    ):
        """Affecte décision de jury"""
        sco_formsemestre_validation.formsemestre_validation_etud_manu(
            formsemestre_id=sem["formsemestre_id"],
            etudid=etud["etudid"],
            code_etat=code_etat,
            devenir=devenir,
            assidu=assidu,
        )
