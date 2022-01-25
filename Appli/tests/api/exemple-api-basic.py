#!/usr/bin/env python3
# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Exemple utilisation API ScoDoc 9 avec jeton obtenu par basic athentication


Utilisation: créer les variables d'environnement: (indiquer les valeurs
pour le serveur ScoDoc que vous voulez interroger)

export SCODOC_URL="https://scodoc.xxx.net/"
export SCODOC_USER="xxx"
export SCODOC_PASSWD="xxx"
export CHECK_CERTIFICATE=0 # ou 1 si serveur de production avec certif SSL valide

(on peut aussi placer ces valeurs dans un fichier .env du répertoire tests/api).


Travail en cours, un seul point d'API (list_depts).
"""

from dotenv import load_dotenv
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
DEPT_URL = SCODOC_URL + "/ScoDoc/" + SCODOC_DEPT + "/Scolarite/"
SCODOC_USER = os.environ["SCODOC_USER"]
SCODOC_PASSWORD = os.environ["SCODOC_PASSWD"]
print(f"SCODOC_URL={SCODOC_URL}")

# ---
if not CHECK_CERTIFICATE:
    urllib3.disable_warnings()


class ScoError(Exception):
    pass


def GET(path: str, headers={}, errmsg=None):
    """Get and returns as JSON"""
    r = requests.get(
        DEPT_URL + "/" + path, headers=headers or HEADERS, verify=CHECK_CERTIFICATE
    )
    if r.status_code != 200:
        raise ScoError(errmsg or "erreur !")
    return r.json()  # decode la reponse JSON


def POST(s, path: str, data: dict, errmsg=None):
    """Post"""
    r = s.post(DEPT_URL + "/" + path, data=data, verify=CHECK_CERTIFICATE)
    if r.status_code != 200:
        raise ScoError(errmsg or "erreur !")
    return r.text


# --- Obtention du jeton (token)
r = requests.post(
    SCODOC_URL + "/ScoDoc/api/tokens", auth=(SCODOC_USER, SCODOC_PASSWORD)
)
assert r.status_code == 200
token = r.json()["token"]
HEADERS = {"Authorization": f"Bearer {token}"}

r = requests.get(
    SCODOC_URL + "/ScoDoc/api/list_depts", headers=HEADERS, verify=CHECK_CERTIFICATE
)
if r.status_code != 200:
    raise ScoError("erreur de connexion: vérifier adresse et identifiants")

pp(r.json())


# # --- Recupere la liste de tous les semestres:
# sems = GET(s, "Notes/formsemestre_list?format=json", "Aucun semestre !")

# # sems est une liste de semestres (dictionnaires)
# for sem in sems:
#     if sem["etat"]:
#         break

# if sem["etat"] == "0":
#     raise ScoError("Aucun semestre non verrouillé !")

# # Affiche le  semestre trouvé:
# pp(sem)

# # ---- Récupère la description de ce semestre:
# # semdescr = GET(s, f"Notes/formsemestre_description?formsemestre_id={sem['formsemestre_id']}&with_evals=0&format=json" )

# # ---- Liste les modules et prend le premier
# mods = GET(s, f"/Notes/moduleimpl_list?formsemestre_id={sem['formsemestre_id']}")
# print(f"{len(mods)} modules dans le semestre {sem['titre']}")

# mod = mods[0]

# # ---- Etudiants inscrits dans ce module
# inscrits = GET(
#     s, f"Notes/do_moduleimpl_inscription_list?moduleimpl_id={mod['moduleimpl_id']}"
# )
# print(f"{len(inscrits)} inscrits dans ce module")
# # prend le premier inscrit, au hasard:
# etudid = inscrits[0]["etudid"]

# # ---- Création d'une evaluation le dernier jour du semestre
# jour = sem["date_fin"]
# evaluation_id = POST(
#     s,
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
#     s,
#     "/Notes/save_note",
#     data={
#         "etudid": etudid,
#         "evaluation_id": evaluation_id,
#         "value": 16.66,  # la note !
#         "comment": "test API",
#     },
# )
