#!/usr/bin/env python3
# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Exemple connexion sur ScoDoc 9 et utilisation de l'ancienne API ScoDoc 7
à la mode "PHP": les gens passaient directement __ac_name et __ac_password 
dans chaque requête, en POST ou en GET.

Cela n'a jamais été documenté mais était implicitement supporté. C'est "deprecated" 
et ne sera plus supporté à partir de juillet 2022.

Ce script va tester:
- Liste semestres
- Liste modules
- Creation d'une évaluation
- Saisie d'une note

Utilisation: créer les variables d'environnement: (indiquer les valeurs
pour le serveur ScoDoc que vous voulez interroger)

export SCODOC_URL="https://scodoc.xxx.net/"
export SCODOC_USER="xxx"
export SCODOC_PASSWD="xxx"
export CHECK_CERTIFICATE=0 # ou 1 si serveur de production avec certif SSL valide

(on peut aussi placer ces valeurs dans un fichier .env du répertoire tests/api).
"""

from dotenv import load_dotenv
import json
import os
import pdb
import requests
import urllib3
from pprint import pprint as pp

# --- Lecture configuration (variables d'env ou .env)
BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASEDIR, ".env"))
CHECK_CERTIFICATE = bool(int(os.environ.get("CHECK_CERTIFICATE", False)))
SCODOC_URL = os.environ["SCODOC_URL"]
SCODOC_DEPT = os.environ["SCODOC_DEPT"]
DEPT_URL = SCODOC_URL + "/ScoDoc/" + SCODOC_DEPT + "/Scolarite"
SCODOC_USER = os.environ["SCODOC_USER"]
SCODOC_PASSWORD = os.environ["SCODOC_PASSWD"]
print(f"SCODOC_URL={SCODOC_URL}")

# ---
if not CHECK_CERTIFICATE:
    urllib3.disable_warnings()


class ScoError(Exception):
    pass


def GET(path: str, params=None, errmsg=None):
    """Get and returns as JSON"""
    # ajoute auth
    params["__ac_name"] = SCODOC_USER
    params["__ac_password"] = SCODOC_PASSWORD
    r = requests.get(DEPT_URL + "/" + path, params=params, verify=CHECK_CERTIFICATE)
    if r.status_code != 200:
        raise ScoError(errmsg or "erreur !")
    return r.json()  # decode la reponse JSON


def POST(path: str, data: dict, errmsg=None):
    """Post"""
    data["__ac_name"] = data.get("__ac_name", SCODOC_USER)
    data["__ac_password"] = data.get("__ac_password", SCODOC_PASSWORD)
    r = requests.post(DEPT_URL + "/" + path, data=data, verify=CHECK_CERTIFICATE)
    return r


# ---
# pas besoin d'ouvrir une session, on y va directement:

# --- Recupere la liste de tous les semestres:
sems = GET("Notes/formsemestre_list", params={"format": "json"})

# sems est une liste de semestres (dictionnaires)
for sem in sems:
    if sem["etat"]:
        break

if sem["etat"] == "0":
    raise ScoError("Aucun semestre non verrouillé !")

# Affiche le  semestre trouvé:
pp(sem)

# Liste des étudiants dans le 1er semestre non verrouillé:
group_list = GET(
    "groups_view",
    params={
        "formsemestre_id": sem["formsemestre_id"],
        "with_codes": 1,
        "format": "json",
    },
)
if not group_list:
    # config inadaptée pour les tests...
    raise ScoError("aucun étudiant inscrit dans le semestre")

etud = group_list[0]  # le premier étudiant inscrit ici
# test un POST
r = POST(
    "Absences/AddBilletAbsence",
    {
        "begin": "2021-10-25",
        "end": "2021-10-26",
        "description": "test API scodoc7",
        "etudid": etud["etudid"],
    },
)
assert r.status_code == 200
assert r.text.startswith('<?xml version="1.0" encoding="utf-8"?>')
assert "billet_id" in r.text
# Essai avec un compte invalide
r_invalid = POST(
    "Absences/AddBilletAbsence",
    {
        "__ac_name": "xxx",
        "begin": "2021-10-25",
        "end": "2021-10-26",
        "description": "test API scodoc7",
        "etudid": etud["etudid"],
    },
)
assert r_invalid.status_code == 403  # compte invalide => not authorized

# AddBilletAbsence en json
r = POST(
    "Absences/AddBilletAbsence",
    {
        "begin": "2021-10-25",
        "end": "2021-10-26",
        "description": "test API scodoc7",
        "etudid": etud["etudid"],
        "xml_reply": 0,
    },
)
assert r.status_code == 200
assert isinstance(json.loads(r.text)[0]["billet_id"], int)

# Les fonctions ci-dessous ne fonctionnent plus en ScoDoc 9
# Voir https://scodoc.org/git/viennet/ScoDoc/issues/149

# # ---- Liste les modules et prend le premier
# mods = GET("/Notes/moduleimpl_list", params={"formsemestre_id": sem["formsemestre_id"]})
# print(f"{len(mods)} modules dans le semestre {sem['titre']}")

# mod = mods[0]

# # ---- Etudiants inscrits dans ce module
# inscrits = GET(
#     "Notes/do_moduleimpl_inscription_list",
#     params={"moduleimpl_id": mod["moduleimpl_id"]},
# )
# print(f"{len(inscrits)} inscrits dans ce module")
# # prend le premier inscrit, au hasard:
# etudid = inscrits[0]["etudid"]

# # ---- Création d'une evaluation le dernier jour du semestre
# jour = sem["date_fin"]
# evaluation_id = POST(
#     "/Notes/do_evaluation_create",
#     data={
#         "moduleimpl_id": mod["moduleimpl_id"],
#         "coefficient": 1,
#         "jour": jour,  # "5/9/2019",
#         "heure_debut": "9h00",
#         "heure_fin": "10h00",
#         "note_max": 20,  # notes sur 20
#         "description": "essai",
#     },
#     errmsg="échec création évaluation",
# )

# print(
#     f"Evaluation créée dans le module {mod['moduleimpl_id']}, evaluation_id={evaluation_id}"
# )
# print(
#     f"Pour vérifier, aller sur: {DEPT_URL}/Notes/moduleimpl_status?moduleimpl_id={mod['moduleimpl_id']}",
# )

# # ---- Saisie d'une note
# junk = POST(
#     "/Notes/save_note",
#     data={
#         "etudid": etudid,
#         "evaluation_id": evaluation_id,
#         "value": 16.66,  # la note !
#         "comment": "test API",
#     },
# )
