"""Test calculs rattrapages
"""

from config import TestConfig
from tests.unit import sco_fake_gen

from flask import g

import app
from app.scodoc import sco_bulletins
from app.scodoc import sco_utils as scu

DEPT = TestConfig.DEPT_TEST


def test_notes_rattrapage(test_client):
    """Test quelques opérations élémentaires de ScoDoc
    Création 1 étudiant, formation, semestre, inscription etudiant,
    creation 1 evaluation, saisie notes.
    """
    app.set_sco_dept(DEPT)

    G = sco_fake_gen.ScoFake(verbose=False)
    etuds = [G.create_etud(code_nip=None)]  # un seul

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
    # --- Création d'une évaluation "de rattrapage"
    e_rat = G.create_evaluation(
        moduleimpl_id=mi["moduleimpl_id"],
        jour="02/01/2020",
        description="evaluation rattrapage",
        coefficient=1.0,
        evaluation_type=scu.EVALUATION_RATTRAPAGE,
    )
    etud = etuds[0]
    _, _, _ = G.create_note(evaluation=e, etud=etud, note=12.0)
    _, _, _ = G.create_note(evaluation=e_rat, etud=etud, note=11.0)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    # Vérifie structure du bulletin:
    assert b["etudid"] == etud["etudid"]
    assert len(b["ues"][0]["modules"][0]["evaluations"]) == 2
    assert len(b["ues"][0]["modules"]) == 1
    # Note moyenne: ici le ratrapage est inférieur à la note:
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(12.0)
    # rattrapage > moyenne:
    _, _, _ = G.create_note(evaluation=e_rat, etud=etud, note=18.0)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(18.0)
    # rattrapage vs absences
    _, _, _ = G.create_note(evaluation=e, etud=etud, note=None)  # abs
    _, _, _ = G.create_note(evaluation=e_rat, etud=etud, note=17.0)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(17.0)
    # et sans note de rattrapage
    _, _, _ = G.create_note(evaluation=e, etud=etud, note=10.0)  # abs
    _, _, _ = G.create_note(evaluation=e_rat, etud=etud, note=None)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(10.0)
