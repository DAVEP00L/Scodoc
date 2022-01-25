# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""
Comptage des absences
"""
# test écrit par Fares Amer, mai 2021 et porté sur ScoDoc 8 en juillet 2021

import json

from tests.unit import sco_fake_gen

from app.scodoc import sco_abs
from app.scodoc import sco_abs_views
from app.scodoc import sco_groups
from app.views import absences


def test_abs_counts(test_client):
    """Comptage des absences"""
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

    for debut, fin, demijournee in [
        ("01/01/2020", "31/01/2020", 2),  # hors semestre
        ("15/01/2021", "15/01/2021", 1),
        ("18/01/2021", "18/01/2021", 0),
        ("19/01/2021", "19/01/2021", 2),
        ("22/01/2021", "22/01/2021", 1),
        ("30/06/2021", "30/06/2021", 2),  # dernier jour
    ]:
        sco_abs_views.doSignaleAbsence(
            datedebut=debut,
            datefin=fin,
            demijournee=demijournee,
            etudid=etudid,
        )

    # --- Justification de certaines absences

    for debut, fin, demijournee in [
        ("15/01/2021", "15/01/2021", 1),
        ("18/01/2021", "18/01/2021", 0),
        ("19/01/2021", "19/01/2021", 2),
    ]:
        sco_abs_views.doJustifAbsence(
            datedebut=debut,
            datefin=fin,
            demijournee=demijournee,
            etudid=etudid,
        )

    # --- Utilisation de get_abs_count() de sco_abs

    nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)

    # --- Utilisation de sco_abs.count_abs()

    nb_abs2 = sco_abs.count_abs(etudid=etudid, debut="2021-01-01", fin="2021-06-30")
    nb_absj2 = sco_abs.count_abs_just(
        etudid=etudid, debut="2021-01-01", fin="2021-06-30"
    )

    assert nbabs == nb_abs2 == 7
    assert nbabsjust == nb_absj2 == 4

    # --- Nombre de justificatifs:
    justifs = sco_abs.list_abs_justifs(etudid, "2021-01-01", datefin="2021-06-30")
    assert len(justifs) == 4

    # --- Suppression d'absence
    _ = sco_abs_views.doAnnuleAbsence("19/01/2021", "19/01/2021", 2, etudid=etudid)

    # --- Vérification
    justifs_2 = sco_abs.list_abs_justifs(etudid, "2021-01-01", datefin="2021-06-30")
    assert len(justifs_2) == len(justifs)
    new_nbabs, _ = sco_abs.get_abs_count(etudid, sem)  # version cachée
    new_nbabs2 = sco_abs.count_abs(etudid=etudid, debut="2021-01-01", fin="2021-06-30")

    assert new_nbabs == new_nbabs2
    assert new_nbabs == (nbabs - 2)  # on a supprimé deux absences

    # --- annulation absence sans supprimer le justificatif
    sco_abs_views.AnnuleAbsencesDatesNoJust(etudid, ["2021-01-15"])
    nbabs_3, nbjust_3 = sco_abs.get_abs_count(etudid, sem)
    assert nbabs_3 == new_nbabs
    justifs_3 = sco_abs.list_abs_justifs(etudid, "2021-01-01", datefin="2021-06-30")
    assert len(justifs_3) == len(justifs_2)
    # XXX à continuer