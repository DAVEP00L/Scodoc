# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""
Créer et justifier des absences en utilisant le parametre demijournee
"""
# test écrit par Fares Amer, mai 2021 et porté sur ScoDoc 8 en juillet 2021

import json

from tests.unit import sco_fake_gen

from app.scodoc import sco_abs
from app.scodoc import sco_abs_views
from app.scodoc import sco_groups
from app.views import absences


def test_abs_demijournee(test_client):
    """Opération élémentaires sur les absences, tests demi-journées
    Travaille dans base TEST00 (defaut)
    """
    G = sco_fake_gen.ScoFake(verbose=False)

    # --- Création d'étudiants
    etud = G.create_etud(code_nip=None)

    # --- Création d'une formation
    f = G.create_formation(acronyme="")
    ue = G.create_ue(formation_id=f["formation_id"], acronyme="TST1", titre="ue test")
    mat = G.create_matiere(ue_id=ue["ue_id"], titre="matière test")
    mod = G.create_module(
        matiere_id=mat["matiere_id"],
        code="TSM1",
        coefficient=1.0,
        titre="module test",
        ue_id=ue["ue_id"],  # faiblesse de l'API
        formation_id=f["formation_id"],  # faiblesse de l'API
    )

    # --- Mise place d'un semestre
    sem = G.create_formsemestre(
        formation_id=f["formation_id"],
        semestre_id=1,
        date_debut="01/01/2021",
        date_fin="30/06/2021",
    )

    mi = G.create_moduleimpl(
        module_id=mod["module_id"],
        formsemestre_id=sem["formsemestre_id"],
    )

    # --- Inscription des étudiants
    G.inscrit_etudiant(sem, etud)

    # --- Saisie absences
    etudid = etud["etudid"]

    _ = sco_abs_views.doSignaleAbsence(
        "15/01/2021",
        "15/01/2021",
        demijournee=2,
        etudid=etudid,
    )

    _ = sco_abs_views.doSignaleAbsence(
        "18/01/2021",
        "18/01/2021",
        demijournee=1,
        etudid=etudid,
    )

    _ = sco_abs_views.doSignaleAbsence(
        "19/01/2021",
        "19/01/2021",
        demijournee=0,
        etudid=etudid,
    )

    # --- Justification de certaines absences

    _ = sco_abs_views.doJustifAbsence(
        "18/01/2021",
        "18/01/2021",
        demijournee=1,
        etudid=etudid,
    )

    _ = sco_abs_views.doJustifAbsence(
        "19/01/2021",
        "19/01/2021",
        demijournee=2,
        etudid=etudid,
    )

    # NE JUSTIFIE QUE LE MATIN MALGRES LE PARAMETRE demijournee = 2

    # --- Test

    nbabs, nbabs_just = sco_abs.get_abs_count(etudid, sem)
    assert (
        nbabs == 4
    )  # l'étudiant a été absent le 15 journée compléte (2 abs : 1 matin, 1 apres midi) et le 18 (1 matin), et le 19 (1 apres midi).
    assert nbabs_just == 2  # Justifie abs du matin + abs après midi


def test_abs_basic(test_client):
    """creation de 10 étudiants, formation, semestre, ue, module, absences le matin, l'apres midi, la journée compléte
    et justification d'absences, supression d'absences, création d'une liste etat absences, creation d'un groupe afin
    de tester la fonction EtatAbsencesGroupes

    Fonctions de l'API utilisé :
     - doSignaleAbsence
     - doAnnuleAbsence
     - doJustifAbsence
     - get_partition_groups
     - get_partitions_list
     - sco_abs.get_abs_count(etudid, sem)
     - ListeAbsEtud
     - partition_create
     - create_group
     - set_group
     - EtatAbsenceGr
     - AddBilletAbsence
     - listeBilletsEtud
    """
    G = sco_fake_gen.ScoFake(verbose=False)

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
        ue_id=ue["ue_id"],  # faiblesse de l'API
        formation_id=f["formation_id"],  # faiblesse de l'API
    )

    # --- Mise place d'un semestre
    sem = G.create_formsemestre(
        formation_id=f["formation_id"],
        semestre_id=1,
        date_debut="01/01/2021",
        date_fin="30/06/2021",
    )

    mi = G.create_moduleimpl(
        module_id=mod["module_id"],
        formsemestre_id=sem["formsemestre_id"],
    )

    # --- Inscription des étudiants
    for etud in etuds:
        G.inscrit_etudiant(sem, etud)

    # --- Création d'une évaluation
    e = G.create_evaluation(
        moduleimpl_id=mi["moduleimpl_id"],
        jour="22/01/2021",
        description="evaluation test",
        coefficient=1.0,
    )

    # --- Saisie absences
    etudid = etuds[0]["etudid"]

    _ = sco_abs_views.doSignaleAbsence(
        "15/01/2021",
        "15/01/2021",
        demijournee=1,
        etudid=etudid,
    )

    _ = sco_abs_views.doSignaleAbsence(
        "18/01/2021",
        "18/01/2021",
        demijournee=0,
        etudid=etudid,
    )

    _ = sco_abs_views.doSignaleAbsence(
        "19/01/2021",
        "19/01/2021",
        demijournee=2,
        etudid=etudid,
    )

    _ = sco_abs_views.doSignaleAbsence(
        "22/01/2021",
        "22/01/2021",
        demijournee=1,
        etudid=etudid,
    )

    # --- Justification de certaines absences

    _ = sco_abs_views.doJustifAbsence(
        "15/01/2021",
        "15/01/2021",
        demijournee=1,
        etudid=etudid,
    )

    _ = sco_abs_views.doJustifAbsence(
        "18/01/2021",
        "18/01/2021",
        demijournee=0,
        etudid=etudid,
    )

    _ = sco_abs_views.doJustifAbsence(
        "19/01/2021",
        "19/01/2021",
        demijournee=2,
        etudid=etudid,
    )

    # --- Test

    b = sco_abs.is_work_saturday()
    assert b == 0  # samedi ne sont pas compris
    nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
    # l'étudiant a été absent le 15 (apres midi) , (16 et 17 we),
    # 18 (matin) et 19 janvier (matin et apres midi), et 22 (matin)
    assert nbabs == 5
    # l'étudiant justifie ses abs du 15, 18 et 19
    assert nbabsjust == 4

    # --- Suppression d'une absence et d'une justification

    _ = sco_abs_views.doAnnuleAbsence("19/01/2021", "19/01/2021", 2, etudid=etudid)
    nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
    assert nbabs == 3
    assert nbabsjust == 2

    # --- suppression d'une justification pas encore disponible à l'aide de python.

    # --- Création d'une liste d'abs

    liste_abs = sco_abs_views.ListeAbsEtud(
        etudid, format="json", absjust_only=1, sco_year="2020"
    ).get_data(as_text=True)
    liste_abs2 = sco_abs_views.ListeAbsEtud(
        etudid, format="json", sco_year="2020"
    ).get_data(as_text=True)

    load_liste_abs = json.loads(liste_abs)
    load_liste_abs2 = json.loads(liste_abs2)

    assert len(load_liste_abs2) == 1
    assert len(load_liste_abs) == 2
    assert load_liste_abs2[0]["ampm"] == 1
    assert load_liste_abs2[0]["datedmy"] == "22/01/2021"
    assert load_liste_abs2[0]["exams"] == mod["code"]
    # absjust_only -> seulement les abs justifiés

    # --- Création d'un groupe

    _ = sco_groups.partition_create(
        formsemestre_id=sem["formsemestre_id"],
        partition_name="Eleve",
    )
    li1 = sco_groups.get_partitions_list(sem["formsemestre_id"])
    _ = sco_groups.create_group(li1[0]["partition_id"], "Groupe 1")

    # --- Affectation des élèves dans des groupes

    li_grp1 = sco_groups.get_partition_groups(li1[0])
    for etud in etuds:
        sco_groups.set_group(etud["etudid"], li_grp1[0]["group_id"])

    # --- Test de EtatAbsencesGroupes

    grp1_abs = absences.EtatAbsencesGr(
        group_ids=[li_grp1[0]["group_id"]],
        debut="01/01/2021",
        fin="30/06/2021",
        format="json",
    )
    # grp1_abs est une Response car on a appelé une vue (1er appel)
    load_grp1_abs = json.loads(grp1_abs.get_data(as_text=True))

    assert len(load_grp1_abs) == 10

    tab_id = []  # tab des id present dans load_grp1_abs
    for un_etud in load_grp1_abs:
        tab_id.append(un_etud["etudid"])

    for (
        etud
    ) in (
        etuds
    ):  # verification si tous les etudiants sont present dans la liste du groupe d'absence
        assert etud["etudid"] in tab_id

    for un_etud in load_grp1_abs:
        if un_etud["etudid"] == etudid:
            assert un_etud["nbabs"] == 3
            assert un_etud["nbjustifs_noabs"] == 2
            assert un_etud["nbabsjust"] == 2
            assert un_etud["nbabsnonjust"] == 1
            assert un_etud["nomprenom"] == etuds[0]["nomprenom"]

    # --- Création de billets

    b1 = absences.AddBilletAbsence(
        begin="2021-01-22 00:00",
        end="2021-01-22 23:59",
        etudid=etudid,
        description="abs du 22",
        justified=False,
        code_nip=etuds[0]["code_nip"],
        code_ine=etuds[0]["code_ine"],
    )

    b2 = absences.AddBilletAbsence(
        begin="2021-01-15 00:00",
        end="2021-01-15 23:59",
        etudid=etudid,
        description="abs du 15",
        code_nip=etuds[0]["code_nip"],
        code_ine=etuds[0]["code_ine"],
    )

    li_bi = absences.listeBilletsEtud(etudid=etudid, format="json").get_data(
        as_text=True
    )
    assert isinstance(li_bi, str)
    load_li_bi = json.loads(li_bi)

    assert len(load_li_bi) == 2
    assert load_li_bi[1]["description"] == "abs du 22"
