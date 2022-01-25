# -*- coding: utf-8 -*-

"""
Scenario: préparation base de données pour tests Selenium

S'utilise comme un test avec pytest, mais n'est pas un test !
Modifie la base de données du département TEST00

Usage: pytest tests/scenarios/test_scenario1_formation.py
"""
# code écrit par Fares Amer, mai 2021 et porté sur ScoDoc 8 en août 2021

import random

from tests.unit import sco_fake_gen
from app.scodoc import sco_edit_module
from app.scodoc import sco_formations
from app.scodoc import sco_moduleimpl


def test_scenario1(test_client):
    """Applique "scenario 1"""
    run_scenario1()


def run_scenario1():
    G = sco_fake_gen.ScoFake(verbose=False)

    # Lecture fichier XML local:
    with open("tests/unit/formation-exemple-1.xml") as f:
        doc = f.read()

    # --- Création de la formation
    f = sco_formations.formation_import_xml(doc=doc)

    # --- Création des semestres
    formation_id = f[0]
    # --- Mise en place de 4 semestres
    sems = [
        G.create_formsemestre(
            formation_id=formation_id,
            semestre_id=x[0],
            date_debut=x[1],
            date_fin=x[2],
        )
        for x in (
            (1, "01/09/2020", "01/02/2021"),
            (2, "02/02/2021", "01/06/2021"),
            (3, "01/09/2020", "01/02/2021"),
            (4, "02/02/2021", "01/06/2021"),
        )
    ]

    # --- Implémentation des modules
    modules = sco_edit_module.module_list({"formation_id": formation_id})
    mods_imp = []
    for mod in modules:
        mi = G.create_moduleimpl(
            module_id=mod["module_id"],
            formsemestre_id=sems[mod["semestre_id"] - 1]["formsemestre_id"],
        )
        mods_imp.append(mi)
