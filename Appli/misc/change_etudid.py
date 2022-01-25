#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Change un etudid

Suite a de fausses manips, il arrive que l'on est des "doublons":
le même étudiant est enregistré sous deux "etudid" différents !

Normalement, l'utilisation d'imports basés sur le code NIP (Apogée)
évite le problème (qui ne se pose qu'en cas d'inscriptions manuelles
mal gérées).

Ce script permet de changer un etudid, typiquement pour associer à un
etudiant le code d'un autre étudiant (son doublon).

Ne traite que les inscriptions, les notes, absences, annotations, mais
évidemment pas les tables uniques (identité, adresse, admission).

Attention: script a lancer en tant que "www-data", avec ScoDoc arrete
et postgresql lance

Emmanuel Viennet, 2007-2020
"""

from __future__ import print_function
import pdb
import sys
import psycopg2

if len(sys.argv) != 4:
    print("Usage: %s database orig_etudid dest_etudid" % sys.argv[0])
    print(" Fusionne l'étudiant orig dans l'étudiant dest.")
    print(" L'identité, adresse et admission de dest restent inchangées.")
    print(" Les inscriptions, notes, absences etc. d'orig sont associées à dest.")
    print(" Après cette operation, orig_etudid peut être supprimé.")
    print("Exemple: change_etudid.py SCOGEII E1234 E87654")
    sys.exit(1)

dbname = sys.argv[1]
OLD_ID = sys.argv[2]  # etudid qui est en double (que l'on supprime)
NEW_ID = sys.argv[3]  # etudid destination (celui d'origine)

DBCNXSTRING = "dbname=%s" % dbname

cnx = psycopg2.connect(DBCNXSTRING)

cursor = cnx.cursor()
req = "update %s set etudid=%%(new_etudid)s where etudid=%%(old_etudid)s"
args = {"old_etudid": OLD_ID, "new_etudid": NEW_ID}

tables = (
    "absences",
    "absences_notifications",
    "billet_absence",
    "scolog",
    "etud_annotations",
    "entreprise_contact",
    "notes_formsemestre_inscription",
    "notes_moduleimpl_inscription",
    "notes_notes",
    "notes_notes_log",
    "scolar_events",
    "scolar_formsemestre_validation",
    "scolar_autorisation_inscription",
    "notes_appreciations",
    "itemsuivi",
    "group_membership",
    # nouvelles absences
    #'abs_absences',
    #'abs_presences',
    #'abs_justifs',
)

for table in tables:
    cursor.execute(req % table, args)
    print("table %s:  %s" % (table, cursor.statusmessage))

cnx.commit()
