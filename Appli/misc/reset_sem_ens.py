#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Affecte tous les modules d'un semestre à l'utilisateur indiqué en argument
Utile uniquement pour certains tests.

(à lancer en tant qu'utilisateur postgres)
Emmanuel Viennet, 2020
"""
from __future__ import print_function

import pdb, os, sys
import psycopg2


if len(sys.argv) != 4:
    print("Usage: %s database formsemestre_id user_name" % sys.argv[0])
    print("Exemple: reset_sem_ens.py SCOGEII SEM34534 toto")
    sys.exit(1)

dbname = sys.argv[1]
formsemestre_id = sys.argv[2]
user_name = sys.argv[3]

DBCNXSTRING = "dbname=%s" % dbname

cnx = psycopg2.connect(DBCNXSTRING)

cursor = cnx.cursor()

print('affecting all modules of semestre %s to "%s"' % (formsemestre_id, user_name))

req = "update notes_moduleimpl set responsable_id=%(responsable_id)s where formsemestre_id=%(formsemestre_id)s"
cursor.execute(req, {"formsemestre_id": formsemestre_id, "responsable_id": user_name})
cnx.commit()
