#!/opt/scodoc/venv/bin/python
# -*- coding: utf-8 -*-
# -*- mode: python -*-

##############################################################################
#
# Gestion scolarite IUT
#
# Copyright (c) 1999 - 2019 Emmanuel Viennet.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#   Emmanuel Viennet      emmanuel.viennet@viennet.net
#
##############################################################################

# TODO à tester avec ScoDoc9, devrait fonctionner sans problème majeur ?

"""Anonymize une base de données ScoDoc

Runned as user "scodoc" with scodoc and postgresql up.

E. Viennet, Jan 2019
"""

import os
import psycopg2
import sys
import traceback


def log(msg):
    sys.stdout.flush()
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# --- Fonctions d'Anonymisation, en SQL

anonymize_name = "random_text_md5(8)"
anonymize_date = "'1970-01-01'"
anonymize_question_str = "'?'"
anonymize_null = "NULL"

# aggregate_length = lambda column, _: 'length({})'.format(column)


# --- Champs à anonymiser (cette configuration pourrait être placé dans
#     un fichier séparé et le code serait alors générique pour toute base
#      posgresql.
#
# On essaie de retirer les données personnelles des étudiants et des entreprises
# TODO: L'identité (login) des enseignants n'est pas modifiée
#
#
ANONYMIZED_FIELDS = {
    "identite.nom": anonymize_name,
    "identite.prenom": anonymize_name,
    "identite.nom_usuel": anonymize_null,
    "identite.civilite": "'X'",
    "identite.date_naissance": anonymize_date,
    "identite.lieu_naissance": anonymize_question_str,
    "identite.dept_naissance": anonymize_question_str,
    "identite.nationalite": anonymize_question_str,
    "identite.statut": anonymize_null,
    "identite.boursier": anonymize_null,
    "identite.photo_filename": anonymize_null,
    "identite.code_nip": anonymize_null,
    "identite.code_ine": anonymize_null,
    "identite.scodoc7_id": anonymize_null,
    "adresse.email": "'ano@nyme.fr'",
    "adresse.emailperso": anonymize_null,
    "adresse.domicile": anonymize_null,
    "adresse.codepostaldomicile": anonymize_null,
    "adresse.villedomicile": anonymize_null,
    "adresse.paysdomicile": anonymize_null,
    "adresse.telephone": anonymize_null,
    "adresse.telephonemobile": anonymize_null,
    "adresse.fax": anonymize_null,
    "admissions.nomlycee": anonymize_name,
    "billet_absence.description": anonymize_null,
    "etud_annotations.comment": anonymize_name,
    # "entreprises.nom": anonymize_name,
    # "entreprises.adresse": anonymize_null,
    # "entreprises.ville": anonymize_null,
    # "entreprises.codepostal": anonymize_null,
    # "entreprises.pays": anonymize_null,
    # "entreprises.contact_origine": anonymize_null,
    # "entreprises.secteur": anonymize_null,
    # "entreprises.note": anonymize_null,
    # "entreprises.privee": anonymize_null,
    # "entreprises.localisation": anonymize_null,
    # "entreprise_correspondant.nom": anonymize_name,
    # "entreprise_correspondant.prenom": anonymize_name,
    # "entreprise_correspondant.phone1": anonymize_null,
    # "entreprise_correspondant.phone2": anonymize_null,
    # "entreprise_correspondant.mobile": anonymize_null,
    # "entreprise_correspondant.mail1": anonymize_null,
    # "entreprise_correspondant.mail2": anonymize_null,
    # "entreprise_correspondant.note": anonymize_null,
    # "entreprise_correspondant.fax": anonymize_null,
    # "entreprise_contact.description": anonymize_null,
    # "entreprise_contact.enseignant": anonymize_null,
    "notes_appreciations.comment": anonymize_name,
}


def anonymize_column(cursor, tablecolumn):
    """Anonymise une colonne
    tablecolumn est de la forme nom_de_table.nom_de_colonne, par exemple "identite.nom"
    key_name est le nom de la colonne (clé) à utiliser pour certains remplacements
    (cette clé doit être anonyme et unique). Par exemple, un nom propre pourrait être
    remplacé par nom_valeur_de_la_clé.
    """
    table, column = tablecolumn.split(".")
    anonymization = ANONYMIZED_FIELDS[tablecolumn]
    log("processing {}".format(tablecolumn))
    cursor.execute(
        "UPDATE {table} SET {column} = {value};".format(
            table=table,
            column=column,
            value=anonymization(column, key_name)
            if callable(anonymization)
            else anonymization,
        )
    )


def anonymize_db(cursor):
    """Traite, une à une, les colonnes indiquées dans ANONYMIZED_FIELDS"""
    for tablecolumn in ANONYMIZED_FIELDS:
        anonymize_column(cursor, tablecolumn)


dbname = sys.argv[1]

log("\nAnonymizing database %s" % dbname)
cnx_string = "dbname=" + dbname
try:
    cnx = psycopg2.connect(cnx_string)
except:
    log("\n*** Error: can't connect to database %s ***\n" % dbname)
    log('connexion string was "%s"' % cnx_string)
    traceback.print_exc()

cnx.set_session(autocommit=False)
cursor = cnx.cursor()

anonymize_db(cursor)

cnx.commit()
cnx.close()
