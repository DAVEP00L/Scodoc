# -*- mode: python -*-
# -*- coding: utf-8 -*-

""" Test creation/edition/import/export formations
"""

# test écrit par Fares Amer, mai 2021 et porté sur ScoDoc 8 en juillet 2021

# Créer 2 formations, une test et une normale. Créer 2 semestres dans la formation normale et un
# dans la formation test, créer 2 semestres dans la formation normale (un test et un normal),
# 2 ue (un test et un normal), 2 modules (un test et un normal) et 2 matieres (test et normal).
#  Et dans la formations test, un semestre, un module, un ue et une matiere.
#  Afficher la liste de tout ca puis supprimer les ue, mod, mat et sem test ainsi
#  que la formation test. Afficher la liste des UE, formations et modules restante.
#
#  Vérification :
#
#  - Les listes initiales comprennent bien tout les éléments créés avec les bon noms etc
#  - La supression s'est bien effectué au niveau de scodoc web et en python
#  - Vérifier que les fonctions listes font bien la mise à jour après supression
#
# Fonction de l'API utilisé :
#
# - create_formation
# - create_ue
# - create_matiere
# - create_module
# - create_formsemestre
# - create_moduleimpl
# - formation_list
# - formation_export
# - formsemestre_list
# - moduleimpl_list
# - do_module_impl_with_module_list
# - do_formsemestre_delete
# - module_list
# - do_module_delete
# - matiere_list
# - do_matiere_delete
# - ue_list
# - do_ue_delete
# - do_formation_delete

import json
import xml.dom.minidom

import flask
from flask import g

from tests.unit import sco_fake_gen

from app.scodoc import sco_edit_formation
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre_edit
from app.scodoc import sco_moduleimpl
from app.views import notes


def test_formations(test_client):
    """Test création/édition/import/export formations"""
    G = sco_fake_gen.ScoFake(verbose=False)

    # --- Création de formations

    f = G.create_formation(
        acronyme="F1", titre="Formation 1", titre_officiel="Titre officiel 1"
    )

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

    ue2 = G.create_ue(formation_id=f["formation_id"], acronyme="TST2", titre="ue test2")
    mat2 = G.create_matiere(ue_id=ue2["ue_id"], titre="matière test2")
    mod2 = G.create_module(
        matiere_id=mat2["matiere_id"],
        code="TSM2",
        coefficient=1.0,
        titre="module test",
        ue_id=ue2["ue_id"],  # faiblesse de l'API
        formation_id=f["formation_id"],  # faiblesse de l'API
    )

    uet = G.create_ue(formation_id=f["formation_id"], acronyme="TSTt", titre="ue testt")
    matt = G.create_matiere(ue_id=uet["ue_id"], titre="matière testt")
    modt = G.create_module(
        matiere_id=matt["matiere_id"],
        code="TSMt",
        coefficient=1.0,
        titre="module test",
        ue_id=uet["ue_id"],  # faiblesse de l'API
        formation_id=f["formation_id"],  # faiblesse de l'API
    )

    f2 = G.create_formation(acronyme="", titre="Formation test")

    ue3 = G.create_ue(
        formation_id=f2["formation_id"], acronyme="TST3", titre="ue test3"
    )
    mat3 = G.create_matiere(ue_id=ue3["ue_id"], titre="matière test3")
    mod3 = G.create_module(
        matiere_id=mat3["matiere_id"],
        code="TSM3",
        coefficient=1.0,
        titre="module test3",
        ue_id=ue3["ue_id"],  # faiblesse de l'API
        formation_id=f2["formation_id"],  # faiblesse de l'API
    )

    # --- Création et implémentation des semestres

    sem1 = G.create_formsemestre(
        formation_id=f["formation_id"],
        semestre_id=1,
        date_debut="01/01/2021",
        date_fin="30/06/2021",
    )

    sem2 = G.create_formsemestre(
        formation_id=f["formation_id"],
        semestre_id=2,
        date_debut="01/09/2020",
        date_fin="31/12/2020",
    )

    mi = G.create_moduleimpl(
        module_id=mod["module_id"],
        formsemestre_id=sem1["formsemestre_id"],
    )

    mi2 = G.create_moduleimpl(
        module_id=mod2["module_id"],
        formsemestre_id=sem1["formsemestre_id"],
    )

    mit = G.create_moduleimpl(
        module_id=modt["module_id"],
        formsemestre_id=sem2["formsemestre_id"],
    )

    semt = G.create_formsemestre(
        formation_id=f2["formation_id"],
        semestre_id=3,
        date_debut="01/01/2021",
        date_fin="30/06/2021",
    )

    mi3 = G.create_moduleimpl(
        module_id=mod3["module_id"],
        formsemestre_id=semt["formsemestre_id"],
    )

    # --- Afficher la liste des formations

    lif = notes.formation_list(format="json", formation_id=f["formation_id"])
    # lif est une Response car on a appelé une vue (1er appel)
    assert isinstance(lif, flask.Response)
    load_lif = json.loads(lif.get_data().decode("utf-8"))
    assert len(load_lif) == 1
    assert load_lif[0]["acronyme"] == f["acronyme"]
    assert load_lif[0]["titre_officiel"] == f["titre_officiel"]
    assert load_lif[0]["formation_id"] == f["formation_id"]
    assert load_lif[0]["titre"] == f["titre"]

    lif2 = notes.formation_list(format="json").get_data(as_text=True)
    # lif2 est un chaine
    assert isinstance(lif2, str)
    load_lif2 = json.loads(lif2)
    assert len(load_lif2) == 2
    assert load_lif2[0] == load_lif[0]
    assert load_lif2[1]["titre"] == f2["titre"]

    # --- Export de formation_id

    exp = sco_formations.formation_export(
        formation_id=f["formation_id"], format="json"
    ).get_data(as_text=True)
    assert isinstance(exp, str)
    load_exp = json.loads(exp)

    assert load_exp["acronyme"] == "F1"
    assert load_exp["titre_officiel"] == "Titre officiel 1"
    assert load_exp["titre"] == "Formation 1"
    assert load_exp["formation_code"] == f["formation_code"]
    assert len(load_exp["ue"]) == 3
    assert load_exp["ue"][0]["acronyme"] == "TST1"
    assert load_exp["ue"][0]["titre"] == "ue test"
    assert load_exp["formation_id"] == f["formation_id"]
    assert load_exp["formation_code"] == f["formation_code"]

    # --- Liste des semestres

    li_sem1 = notes.formsemestre_list(
        formsemestre_id=sem1["formsemestre_id"], format="json"
    ).get_data(as_text=True)
    assert isinstance(li_sem1, str)
    load_li_sem1 = json.loads(li_sem1)  # uniquement le semestre 1 dans la liste

    assert len(load_li_sem1) == 1
    assert load_li_sem1[0]["date_fin"] == sem1["date_fin"]
    assert load_li_sem1[0]["semestre_id"] == sem1["semestre_id"]
    assert load_li_sem1[0]["formation_id"] == sem1["formation_id"]

    li_semf = notes.formsemestre_list(
        formation_id=f["formation_id"],
        format="json",
    ).get_data(as_text=True)
    assert isinstance(li_semf, str)
    load_li_semf = json.loads(li_semf)

    assert load_li_sem1[0] in load_li_semf
    assert len(load_li_semf) == 2
    assert load_li_semf[1]["semestre_id"] == sem2["semestre_id"]

    li_sem = notes.formsemestre_list(format="json").get_data(as_text=True)
    load_li_sem = json.loads(li_sem)

    assert len(load_li_sem) == 3
    assert load_li_semf[0] and load_li_semf[1] in load_li_sem
    assert load_li_sem[0]["semestre_id"] == semt["semestre_id"]

    # --- Liste des modules

    lim_sem1 = sco_moduleimpl.moduleimpl_list(formsemestre_id=sem1["formsemestre_id"])

    assert len(lim_sem1) == 2
    assert mod["module_id"] in (lim_sem1[0]["module_id"], lim_sem1[1]["module_id"])
    assert mod2["module_id"] in (lim_sem1[0]["module_id"], lim_sem1[1]["module_id"])

    lim_modid = sco_moduleimpl.moduleimpl_list(module_id=mod["module_id"])

    assert len(lim_modid) == 1

    lim_modimpl_id = sco_moduleimpl.moduleimpl_list(moduleimpl_id=mi["moduleimpl_id"])
    # print(lim_modimpl_id)

    # ---- Test de moduleimpl_withmodule_list

    assert lim_modid == lim_modimpl_id  # doit etre le meme resultat

    liimp_sem1 = sco_moduleimpl.moduleimpl_withmodule_list(
        formsemestre_id=sem1["formsemestre_id"]
    )

    assert len(liimp_sem1) == 2
    assert mod["module_id"] in (liimp_sem1[0]["module_id"], liimp_sem1[1]["module_id"])
    assert mod2["module_id"] in (
        liimp_sem1[0]["module_id"],
        liimp_sem1[1]["module_id"],
    )
    liimp_sem2 = sco_moduleimpl.moduleimpl_withmodule_list(
        formsemestre_id=sem2["formsemestre_id"]
    )
    assert modt["module_id"] == liimp_sem2[0]["module_id"]
    liimp_modid = sco_moduleimpl.moduleimpl_withmodule_list(module_id=mod["module_id"])
    assert len(liimp_modid) == 1

    liimp_modimplid = sco_moduleimpl.moduleimpl_withmodule_list(
        moduleimpl_id=mi["moduleimpl_id"]
    )

    assert liimp_modid == liimp_modimplid

    # --- Suppression du module, matiere et ue test du semestre 2

    # on doit d'abbord supprimer le semestre

    # sco_formsemestre_edit.formsemestre_delete( formsemestre_id=sem2["formsemestre_id"])
    # sco_formsemestre_edit.formsemestre_createwithmodules( formsemestre_id=sem2["formsemestre_id"])

    # RIEN NE SE PASSE AVEC CES FONCTIONS

    sco_formsemestre_edit.do_formsemestre_delete(
        formsemestre_id=sem2["formsemestre_id"]
    )

    # sco_edit_module.module_delete( module_id=modt["module_id"])
    # sco_edit_matiere.matiere_delete( matiere_id=matt["matiere_id"])
    # sco_edit_ue.ue_delete( ue_id=uet["ue_id"])

    # RIEN NE SE PASSE AVEC CES FONCTIONS

    li_module = sco_edit_module.module_list()
    assert len(li_module) == 4
    sco_edit_module.do_module_delete(oid=modt["module_id"])  # on supprime le semestre
    # sco_formsemestre_edit.formsemestre_delete_moduleimpls( formsemestre_id=sem2["formsemestre_id"], module_ids_to_del=[modt["module_id"]])
    # deuxieme methode de supression d'un module
    li_module2 = sco_edit_module.module_list()

    assert len(li_module2) == 3  # verification de la suppression du module

    lim_sem2 = sco_moduleimpl.moduleimpl_list(formsemestre_id=sem2["formsemestre_id"])

    assert len(lim_sem2) == 0  # deuxieme vérification si le module s'est bien sup

    li_mat = sco_edit_matiere.matiere_list()
    assert len(li_mat) == 4
    sco_edit_matiere.do_matiere_delete(oid=matt["matiere_id"])  # on supprime la matiere
    li_mat2 = sco_edit_matiere.matiere_list()
    assert len(li_mat2) == 3  # verification de la suppression de la matiere

    li_ue = sco_edit_ue.ue_list()
    assert len(li_ue) == 4
    sco_edit_ue.ue_delete(ue_id=uet["ue_id"], dialog_confirmed=True)
    li_ue2 = sco_edit_ue.ue_list()
    assert len(li_ue2) == 3  # verification de la suppression de l'UE

    # --- Suppression d'une formation
    # Il faut d'abbord supprimer le semestre aussi.
    sco_formsemestre_edit.do_formsemestre_delete(
        formsemestre_id=semt["formsemestre_id"]
    )

    sco_edit_formation.do_formation_delete(oid=f2["formation_id"])
    lif3 = notes.formation_list(format="json").get_data(as_text=True)
    assert isinstance(lif3, str)
    load_lif3 = json.loads(lif3)
    assert len(load_lif3) == 1


def test_import_formation(test_client):
    """Test import/export formations"""
    G = sco_fake_gen.ScoFake(verbose=False)
    # Lecture fichier XML local:
    with open("tests/unit/formation-exemple-1.xml") as f:
        doc = f.read()

    # --- Création de la formation
    f = sco_formations.formation_import_xml(doc)
    assert len(f) == 3  # 3-uple
    formation_id = f[0]
    # --- Vérification des UE
    ues = sco_edit_ue.ue_list({"formation_id": formation_id})
    assert len(ues) == 10
    assert all(not ue["is_external"] for ue in ues)  # aucune UE externe dans le XML
    # --- Mise en place de 4 semestres
    sems = [
        G.create_formsemestre(
            formation_id=formation_id,
            semestre_id=x[0],
            date_debut=x[1],
            date_fin=x[2],
        )
        for x in (
            (1, "05/09/2019", "05/01/2020"),
            (2, "06/01/2020", "30/06/2020"),
            (3, "01/09/2020", "05/01/2021"),
            (4, "06/01/2021", "30/06/2021"),
        )
    ]
    # et les modules
    modules = sco_edit_module.module_list({"formation_id": formation_id})
    for mod in modules:
        mi = G.create_moduleimpl(
            module_id=mod["module_id"],
            formsemestre_id=sems[mod["semestre_id"] - 1]["formsemestre_id"],
        )
        assert mi["ens"] == []
        assert mi["module_id"] == mod["module_id"]

    # --- Export formation en XML
    doc1 = sco_formations.formation_export(formation_id, format="xml").get_data(
        as_text=True
    )
    assert isinstance(doc1, str)
