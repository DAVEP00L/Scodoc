# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Test de base de ScoDoc


Utiliser comme: 
    pytest tests/unit/test_sco_basic.py

Au besoin, créer un base de test neuve:
    ./tools/create_database.sh SCODOC_TEST

"""
import random

from flask import g

from config import TestConfig
from tests.unit import sco_fake_gen

import app
from app.scodoc import notesdb as ndb
from app.scodoc import sco_abs
from app.scodoc import sco_abs_views
from app.scodoc import sco_bulletins
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_evaluations
from app.scodoc import sco_formsemestre_validation
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_cache
from app.scodoc import sco_saisie_notes
from app.scodoc import sco_utils as scu

DEPT = TestConfig.DEPT_TEST


def test_sco_basic(test_client):
    """Test quelques opérations élémentaires de ScoDoc
    Création 10 étudiants, formation, semestre, inscription etudiant,
    creation 1 evaluation, saisie 10 notes.
    """
    app.set_sco_dept(DEPT)
    run_sco_basic()


def run_sco_basic(verbose=False):
    """Scénario de base: création formation, semestre, étudiants, notes,
    décisions jury
    """
    G = sco_fake_gen.ScoFake(verbose=verbose)

    # --- Création d'étudiants
    etuds = [G.create_etud(code_nip=None) for _ in range(10)]

    # --- Création d'une formation
    f = G.create_formation(acronyme="")
    ue = G.create_ue(formation_id=f["formation_id"], acronyme="TST1", titre="ue test")
    mat = G.create_matiere(ue_id=ue["ue_id"], titre="matière test")
    mod = G.create_module(
        matiere_id=mat["matiere_id"],
        code="TSM1",
        coefficient=1.0,
        titre="module test",
        ue_id=ue["ue_id"],
        formation_id=f["formation_id"],
    )

    # --- Mise place d'un semestre
    sem = G.create_formsemestre(
        formation_id=f["formation_id"],
        semestre_id=1,
        date_debut="01/01/2020",
        date_fin="30/06/2020",
    )

    mi = G.create_moduleimpl(
        module_id=mod["module_id"],
        formsemestre_id=sem["formsemestre_id"],
    )

    # --- Inscription des étudiants
    for etud in etuds:
        G.inscrit_etudiant(sem, etud)

    # --- Creation évaluation
    e = G.create_evaluation(
        moduleimpl_id=mi["moduleimpl_id"],
        jour="01/01/2020",
        description="evaluation test",
        coefficient=1.0,
    )

    # --- Saisie toutes les notes de l'évaluation
    for etud in etuds:
        nb_changed, nb_suppress, existing_decisions = G.create_note(
            evaluation=e, etud=etud, note=float(random.randint(0, 20))
        )

    # --- Vérifie que les notes sont prises en compte:
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    # Toute les notes sont saisies, donc eval complète
    etat = sco_evaluations.do_evaluation_etat(e["evaluation_id"])
    assert etat["evalcomplete"]
    assert etat["nb_inscrits"] == len(etuds)
    assert etat["nb_notes"] == len(etuds)
    # Un seul module, donc moy gen == note module
    assert b["ues"][0]["cur_moy_ue_txt"] == b["ues"][0]["modules"][0]["mod_moy_txt"]
    # Note au module égale à celle de l'éval
    assert (
        b["ues"][0]["modules"][0]["mod_moy_txt"]
        == b["ues"][0]["modules"][0]["evaluations"][0]["note_txt"]
    )

    # --- Une autre évaluation
    e2 = G.create_evaluation(
        moduleimpl_id=mi["moduleimpl_id"],
        jour="02/01/2020",
        description="evaluation test 2",
        coefficient=1.0,
    )
    # Saisie les notes des 5 premiers étudiants:
    for etud in etuds[:5]:
        nb_changed, nb_suppress, existing_decisions = G.create_note(
            evaluation=e2, etud=etud, note=float(random.randint(0, 20))
        )
    # Cette éval n'est pas complète
    etat = sco_evaluations.do_evaluation_etat(e2["evaluation_id"])
    assert etat["evalcomplete"] == False
    # la première éval est toujours complète:
    etat = sco_evaluations.do_evaluation_etat(e["evaluation_id"])
    assert etat["evalcomplete"]

    # Modifie l'évaluation 2 pour "prise en compte immédiate"
    e2["publish_incomplete"] = True
    sco_evaluations.do_evaluation_edit(e2)
    etat = sco_evaluations.do_evaluation_etat(e2["evaluation_id"])
    assert etat["evalcomplete"] == False
    assert etat["nb_att"] == 0  # il n'y a pas de notes (explicitement) en attente
    assert etat["evalattente"]  # mais l'eval est en attente (prise en compte immédiate)

    # Saisie des notes qui manquent:
    for etud in etuds[5:]:
        nb_changed, nb_suppress, existing_decisions = G.create_note(
            evaluation=e2, etud=etud, note=float(random.randint(0, 20))
        )
    etat = sco_evaluations.do_evaluation_etat(e2["evaluation_id"])
    assert etat["evalcomplete"]
    assert etat["nb_att"] == 0
    assert not etat["evalattente"]  # toutes les notes sont présentes

    # --- Suppression des notes
    sco_saisie_notes.evaluation_suppress_alln(e["evaluation_id"], dialog_confirmed=True)
    etat = sco_evaluations.do_evaluation_etat(e["evaluation_id"])
    assert etat["nb_notes"] == 0
    assert not etat["evalcomplete"]
    # --- Saisie des notes manquantes
    ans = sco_saisie_notes.do_evaluation_set_missing(
        e["evaluation_id"], 12.34, dialog_confirmed=True
    )
    assert f'{etat["nb_inscrits"]} notes changées' in ans
    etat = sco_evaluations.do_evaluation_etat(e["evaluation_id"])
    assert etat["evalcomplete"]
    # --- Saisie absences
    etudid = etuds[0]["etudid"]

    _ = sco_abs_views.doSignaleAbsence(
        "15/01/2020", "18/01/2020", demijournee=2, etudid=etudid
    )

    _ = sco_abs_views.doJustifAbsence(
        "17/01/2020",
        "18/01/2020",
        demijournee=2,
        etudid=etudid,
    )

    nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
    assert nbabs == 6, "incorrect nbabs (%d)" % nbabs
    assert nbabsjust == 2, "incorrect nbabsjust (%s)" % nbabsjust

    # --- Permission saisie notes et décisions de jury, avec ou sans démission ou défaillance
    # on n'a pas encore saisi de décisions
    assert not sco_parcours_dut.formsemestre_has_decisions(sem["formsemestre_id"])
    # Saisie d'un décision AJ, non assidu
    etudid = etuds[-1]["etudid"]
    sco_parcours_dut.formsemestre_validate_ues(
        sem["formsemestre_id"], etudid, sco_codes_parcours.AJ, False
    )
    assert sco_parcours_dut.formsemestre_has_decisions(
        sem["formsemestre_id"]
    ), "décisions manquantes"
    # Suppression de la décision
    sco_formsemestre_validation.formsemestre_validation_suppress_etud(
        sem["formsemestre_id"], etudid
    )
    assert not sco_parcours_dut.formsemestre_has_decisions(
        sem["formsemestre_id"]
    ), "décisions non effacées"

    # --- Décision de jury et validations des ECTS d'UE
    for etud in etuds[:5]:  # les etudiants notés
        sco_formsemestre_validation.formsemestre_validation_etud_manu(
            sem["formsemestre_id"],
            etud["etudid"],
            code_etat=sco_codes_parcours.ADJ,
            assidu=True,
            redirect=False,
        )
    # Vérifie que toutes les UE des étudiants notés ont été acquises:
    nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
    for etud in etuds[:5]:
        dec_ues = nt.get_etud_decision_ues(etud["etudid"])
        for ue_id in dec_ues:
            assert dec_ues[ue_id]["code"] in {"ADM", "CMP"}
