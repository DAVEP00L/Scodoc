#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Outils pour environnements de démo.

Change aléatoirement les identites (nip, civilite, nom, prenom) des étudiants d'un semestre.

Le NIP est choisi aléatoirement (nombre entier à 8 chiffres).
Les noms et prénoms sont issus des fichiers noms.txt, prenoms-h.txt, prenoms-f.txt
(ce sont simlement les plus fréquemment rencontrés en France).
La civilité est choisie aléatoirement 50-50 Homme/Femme.
"""

import sys
import random
import psycopg2

from gen_nomprenoms import nomprenom


def usage():
    print(f"Usage: {sys.argv[0]} dbname formsemestre_id")
    sys.exit(1)


if len(sys.argv) != 3:
    usage()

dbname = sys.argv[1]
formsemestre_id = sys.argv[2]
DBCNXSTRING = f"dbname={dbname}"

# Liste des etudiants inscrits à ce semestre
cnx = psycopg2.connect(DBCNXSTRING)
cursor = cnx.cursor()

cursor.execute(
    "select count(*) from notes_formsemestre where formsemestre_id=%(formsemestre_id)s",
    {"formsemestre_id": formsemestre_id},
)
nsem = cursor.fetchone()[0]
if nsem != 1:
    print(f"{nsem} formsemestre matching {formsemestre_id} in {dbname}")
    sys.exit(2)

cursor.execute(
    """select i.etudid
    from identite i, notes_formsemestre_inscription ins 
    where i.etudid=ins.etudid and ins.formsemestre_id=%(formsemestre_id)s
    """,
    {"formsemestre_id": formsemestre_id},
)

wcursor = cnx.cursor()
n = 0
for (etudid,) in cursor:
    civilite = random.choice(("M", "F"))  # pas de neutre, on pourrait ajouter 'X'
    nom, prenom = nomprenom(civilite)
    print(f"{etudid}: {nom}\t{prenom}")
    args = {
        "nom": nom,
        "prenom": prenom,
        "civilite": civilite,
        "etudid": etudid,
        "code_nip": random.randrange(10000000, 99999999),
    }
    req = "update identite set nom=%(nom)s, prenom=%(prenom)s, civilite=%(civilite)s where etudid=%(etudid)s"
    # print( req % args)
    wcursor.execute(req, args)
    n += 1


cnx.commit()
cnx.close()

print(f"changed {n} identities", file=sys.stderr)
