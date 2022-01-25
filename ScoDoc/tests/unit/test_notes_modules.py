"""Test calculs moyennes de modules
    Vérif moyennes de modules des bulletins
    et aussi moyennes modules et UE internes (via nt)
"""

from re import X
from config import TestConfig
from tests.unit import sco_fake_gen

from flask import g

import app
from app.scodoc import sco_bulletins
from app.scodoc import sco_cache
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_utils as scu
from app.views import scolar

DEPT = TestConfig.DEPT_TEST


def check_nt(
    etudid,
    formsemestre_id,
    ue_id,
    moduleimpl_id,
    expected_moy_ue=False,
    expected_mod_moy=False,
    expected_sum_coefs_ue=False,
):
    """Vérification bas niveau: vérif resultat avec l'API internet "nt"
    (peut changer dans le futur, ne pas utiliser hors ScoDoc !)
    ne vérifie que les valeurs expected non False
    """
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    mod_moy = nt.get_etud_mod_moy(moduleimpl_id, etudid)
    if expected_moy_ue is not False:
        ue_status = nt.get_etud_ue_status(etudid, ue_id)
        assert expected_moy_ue == ue_status["moy"]
    if expected_mod_moy is not False:
        assert expected_mod_moy == mod_moy
    if expected_sum_coefs_ue is not False:
        ue_status = nt.get_etud_ue_status(etudid, ue_id)
        assert expected_sum_coefs_ue == ue_status["sum_coefs"]
    return nt


def test_notes_modules(test_client):
    """Test calcul des moyennes de modules et d'UE
    Création étudiant, formation, semestre, inscription etudiant,
    création evaluation, saisie de notes.
    Vérifie calcul moyenne avec absences (ABS), excuse (EXC), attente (ATT)
    """
    app.set_sco_dept(DEPT)

    G = sco_fake_gen.ScoFake(verbose=False)
    etuds = [G.create_etud(code_nip=None) for i in range(2)]  # 2 étudiants

    f = G.create_formation(acronyme="")
    ue = G.create_ue(formation_id=f["formation_id"], acronyme="TST1", titre="ue test")
    ue_id = ue["ue_id"]
    mat = G.create_matiere(ue_id=ue_id, titre="matière test")
    coef_mod_1 = 1.5
    mod = G.create_module(
        matiere_id=mat["matiere_id"],
        code="TSM1",
        coefficient=coef_mod_1,
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
    formsemestre_id = sem["formsemestre_id"]
    mi = G.create_moduleimpl(
        module_id=mod["module_id"],
        formsemestre_id=formsemestre_id,
    )
    moduleimpl_id = mi["moduleimpl_id"]
    # --- Inscription des étudiants
    for etud in etuds:
        G.inscrit_etudiant(sem, etud)
    etud = etuds[0]
    etudid = etud["etudid"]
    # --- Creation évaluations: e1, e2
    coef_1 = 1.0
    coef_2 = 2.0
    e1 = G.create_evaluation(
        moduleimpl_id=moduleimpl_id,
        jour="01/01/2020",
        description="evaluation 1",
        coefficient=coef_1,
    )
    e2 = G.create_evaluation(
        moduleimpl_id=moduleimpl_id,
        jour="01/01/2020",
        description="evaluation 2",
        coefficient=coef_2,
    )
    # --- Notes ordinaires
    note_1 = 12.0
    note_2 = 13.0
    _, _, _ = G.create_note(evaluation=e1, etud=etuds[0], note=note_1)
    _, _, _ = G.create_note(evaluation=e2, etud=etuds[0], note=note_2)
    _, _, _ = G.create_note(evaluation=e1, etud=etuds[1], note=note_1 / 2)
    _, _, _ = G.create_note(evaluation=e2, etud=etuds[1], note=note_2 / 3)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    # Vérifie structure du bulletin:
    assert b["etudid"] == etud["etudid"]
    assert len(b["ues"][0]["modules"][0]["evaluations"]) == 2
    assert len(b["ues"][0]["modules"]) == 1
    # Note moyenne:
    note_th = (coef_1 * note_1 + coef_2 * note_2) / (coef_1 + coef_2)
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(note_th)
    check_nt(
        etudid,
        formsemestre_id,
        ue_id,
        moduleimpl_id,
        expected_mod_moy=note_th,
        expected_moy_ue=note_th,
        expected_sum_coefs_ue=coef_mod_1,
    )

    # Absence à une évaluation
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=None)  # abs
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=note_2)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    note_th = (coef_1 * 0.0 + coef_2 * note_2) / (coef_1 + coef_2)
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(note_th)
    # Absences aux deux évaluations
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=None)  # abs
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=None)  # abs
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(0.0)
    check_nt(
        etudid,
        formsemestre_id,
        ue_id,
        moduleimpl_id,
        expected_mod_moy=0.0,
        expected_moy_ue=0.0,
        expected_sum_coefs_ue=coef_mod_1,  # absences, donc zéros et on garde le coef
    )

    # Note excusée EXC <-> scu.NOTES_NEUTRALISE
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=note_1)
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=scu.NOTES_NEUTRALISE)  # EXC
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(note_1)
    check_nt(
        etudid,
        formsemestre_id,
        ue_id,
        moduleimpl_id,
        expected_mod_moy=note_1,
        expected_moy_ue=note_1,
        expected_sum_coefs_ue=coef_mod_1,
    )
    # Note en attente ATT <-> scu.NOTES_ATTENTE
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=note_1)
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=scu.NOTES_ATTENTE)  # ATT
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == scu.fmt_note(note_1)
    check_nt(
        etudid,
        formsemestre_id,
        ue_id,
        moduleimpl_id,
        expected_mod_moy=note_1,
        expected_moy_ue=note_1,
        expected_sum_coefs_ue=coef_mod_1,
    )
    # Neutralisation (EXC) des 2 évals
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=scu.NOTES_NEUTRALISE)  # EXC
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=scu.NOTES_NEUTRALISE)  # EXC
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == "-"
    check_nt(
        etudid,
        sem["formsemestre_id"],
        ue["ue_id"],
        mi["moduleimpl_id"],
        expected_mod_moy="NA",
        expected_moy_ue=0.0,
        expected_sum_coefs_ue=0.0,
    )
    # Attente (ATT) sur les 2 evals
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=scu.NOTES_ATTENTE)  # ATT
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=scu.NOTES_ATTENTE)  # ATT
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["modules"][0]["mod_moy_txt"] == "-"
    check_nt(
        etudid,
        sem["formsemestre_id"],
        ue["ue_id"],
        mi["moduleimpl_id"],
        expected_mod_moy="NA",
        expected_moy_ue=0.0,
        expected_sum_coefs_ue=0.0,
    )
    # Non inscrit
    # - désinscrit notre étudiant:
    inscr = sco_moduleimpl.do_moduleimpl_inscription_list(
        moduleimpl_id=mi["moduleimpl_id"], etudid=etud["etudid"]
    )
    assert len(inscr) == 1
    oid = inscr[0]["moduleimpl_inscription_id"]
    sco_moduleimpl.do_moduleimpl_inscription_delete(
        oid, formsemestre_id=mi["formsemestre_id"]
    )
    # -
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"] == []  # inscrit à aucune UE !
    check_nt(
        etudid,
        formsemestre_id,
        ue_id,
        moduleimpl_id,
        expected_mod_moy="NI",
        expected_moy_ue=0.0,
        expected_sum_coefs_ue=0.0,
    )
    # --- Maintenant avec 2 modules dans l'UE
    coef_mod_2 = 2.1
    mod2 = G.create_module(
        matiere_id=mat["matiere_id"],
        code="TSM2",
        coefficient=coef_mod_2,
        titre="module test 2",
        ue_id=ue_id,
        formation_id=f["formation_id"],
    )
    mi2 = G.create_moduleimpl(
        module_id=mod2["module_id"],
        formsemestre_id=formsemestre_id,
    )
    # Re-inscription au premier module de l'UE
    sco_moduleimpl.do_moduleimpl_inscription_create(
        {"etudid": etudid, "moduleimpl_id": mi["moduleimpl_id"]},
        formsemestre_id=formsemestre_id,
    )
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=12.5)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    ue_status = nt.get_etud_ue_status(etudid, ue_id)
    assert ue_status["nb_missing"] == 1  # 1 même si etud non inscrit à l'autre module
    assert ue_status["nb_notes"] == 1
    assert not ue_status["was_capitalized"]
    # Inscription au deuxième module de l'UE
    sco_moduleimpl.do_moduleimpl_inscription_create(
        {"etudid": etudid, "moduleimpl_id": mi2["moduleimpl_id"]},
        formsemestre_id=formsemestre_id,
    )
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    ue_status = nt.get_etud_ue_status(etudid, ue_id)
    assert ue_status["nb_missing"] == 1  # mi2 n'a pas encore de note
    assert ue_status["nb_notes"] == 1
    # Note dans module 2:
    e_m2 = G.create_evaluation(
        moduleimpl_id=mi2["moduleimpl_id"],
        jour="01/01/2020",
        description="evaluation mod 2",
        coefficient=1.0,
    )
    _, _, _ = G.create_note(evaluation=e_m2, etud=etud, note=19.5)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    ue_status = nt.get_etud_ue_status(etudid, ue_id)
    assert ue_status["nb_missing"] == 0
    assert ue_status["nb_notes"] == 2

    # Moyenne d'UE si l'un des modules est EXC ("NA")
    # 2 modules, notes EXC dans le premier, note valide n dans le second
    # la moyenne de l'UE doit être n
    _, _, _ = G.create_note(evaluation=e1, etud=etud, note=scu.NOTES_NEUTRALISE)  # EXC
    _, _, _ = G.create_note(evaluation=e2, etud=etud, note=scu.NOTES_NEUTRALISE)  # EXC
    _, _, _ = G.create_note(evaluation=e_m2, etud=etud, note=12.5)
    _, _, _ = G.create_note(evaluation=e1, etud=etuds[1], note=11.0)
    _, _, _ = G.create_note(evaluation=e2, etud=etuds[1], note=11.0)
    _, _, _ = G.create_note(evaluation=e_m2, etud=etuds[1], note=11.0)
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etud["etudid"]
    )
    assert b["ues"][0]["ue_status"]["cur_moy_ue"] == 12.5
    assert b["ues"][0]["ue_status"]["moy"] == 12.5
    b2 = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etuds[1]["etudid"]
    )
    assert b2["ues"][0]["ue_status"]["cur_moy_ue"] == 11.0
    assert b2["ues"][0]["ue_status"]["moy"] == 11


def test_notes_modules_att_dem(test_client):
    """Scénario dit "lyonnais":
    Des étudiants, des notes, plusieurs étudiants avec notes ATT  (ici notes éval en "attente"),
    démission d'un étudiant qui avait ATT. Passage des autres ATT en EXC ou ABS.
    On va tester avec un module, une éval, deux étudiants
    """
    app.set_sco_dept(DEPT)

    G = sco_fake_gen.ScoFake(verbose=False)
    etuds = [G.create_etud(code_nip=None) for i in range(2)]  # 2 étudiants

    f = G.create_formation(acronyme="")
    ue = G.create_ue(formation_id=f["formation_id"], acronyme="TST1", titre="ue test")
    ue_id = ue["ue_id"]
    mat = G.create_matiere(ue_id=ue_id, titre="matière test")
    coef_mod_1 = 1.5
    mod = G.create_module(
        matiere_id=mat["matiere_id"],
        code="TSM1",
        coefficient=coef_mod_1,
        titre="module test",
        ue_id=ue["ue_id"],
        formation_id=f["formation_id"],
    )
    #
    # --------------------------------
    #
    sem = G.create_formsemestre(
        formation_id=f["formation_id"],
        semestre_id=1,
        date_debut="01/01/2020",
        date_fin="30/06/2020",
    )
    formsemestre_id = sem["formsemestre_id"]
    mi = G.create_moduleimpl(
        module_id=mod["module_id"],
        formsemestre_id=formsemestre_id,
    )
    moduleimpl_id = mi["moduleimpl_id"]
    # --- Inscription des étudiants
    for etud in etuds:
        G.inscrit_etudiant(sem, etud)
    # --- Creation évaluation: e1
    coef_1 = 1.0
    e1 = G.create_evaluation(
        moduleimpl_id=moduleimpl_id,
        jour="01/01/2020",
        description="evaluation 1",
        coefficient=coef_1,
    )
    # Attente (ATT) sur les 2 evals
    _, _, _ = G.create_note(evaluation=e1, etud=etuds[0], note=scu.NOTES_ATTENTE)  # ATT
    _, _, _ = G.create_note(evaluation=e1, etud=etuds[1], note=scu.NOTES_ATTENTE)  # ATT
    # Démission du premier étudiant
    sco_formsemestre_inscriptions.do_formsemestre_demission(
        etuds[0]["etudid"],
        sem["formsemestre_id"],
        event_date="02/01/2020",
    )
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etuds[0]["etudid"]
    )
    assert b["etud_etat"] == "D"
    assert b["nb_demissions"] == 1
    assert b["ues"] == []  # inscrit à aucune UE !
    # bulletin de l'étudiant non demissionnaire:
    b = sco_bulletins.formsemestre_bulletinetud_dict(
        sem["formsemestre_id"], etuds[1]["etudid"]
    )
    assert b["etud_etat"] == "I"
    assert b["nb_demissions"] == 1
    assert len(b["ues"]) == 1
    nt = check_nt(
        etuds[1]["etudid"],
        sem["formsemestre_id"],
        ue_id,
        moduleimpl_id,
        expected_mod_moy="NA",
        expected_moy_ue=0.0,
        expected_sum_coefs_ue=0.0,
    )
    note_e1 = nt.get_etud_eval_note(etuds[1]["etudid"], e1["evaluation_id"])
    assert note_e1["value"] == scu.NOTES_ATTENTE
    note_e1 = nt.get_etud_eval_note(etuds[0]["etudid"], e1["evaluation_id"])
    assert note_e1["value"] == scu.NOTES_ATTENTE  # XXXX un peu contestable
    # Saisie note ABS pour le deuxième etud
    _, _, _ = G.create_note(evaluation=e1, etud=etuds[1], note=None)  # ABS
    nt = check_nt(
        etuds[1]["etudid"],
        sem["formsemestre_id"],
        ue_id,
        moduleimpl_id,
        expected_mod_moy=0.0,
        expected_moy_ue=0.0,
        expected_sum_coefs_ue=coef_mod_1,
    )
    note_e1 = nt.get_etud_eval_note(etuds[1]["etudid"], e1["evaluation_id"])
    assert note_e1["value"] is None
