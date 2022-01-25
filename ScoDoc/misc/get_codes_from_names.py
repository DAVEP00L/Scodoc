#!/usr/bin/env python

"""Pour un semestre, Affiche colonnes code_nip, code_ine
   etant donnes les noms/prenoms dans un CSV
   (ne change pas la BD)

   XXX TODO: OBSOLETE, a moderniser (psycopg2, python 3, encoding)
"""

import pdb, os, sys, psycopg
import csv


CSVFILENAME = "/tmp/aaa.csv"
formsemestre_id = "SEM229"
DBCNXSTRING = "host=localhost user=scoinfo dbname=SCOINFO password=XXX"

idx_prenom = 1
idx_nom = 0


# en general, pas d'accents dans le CSV
SCO_ENCODING = "iso8859-15"
# from SuppressAccents import suppression_diacritics

# XXX a revoir si ce script est utile: en python3, unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode(SCO_ENCODING)
def suppr_acc_and_ponct(s):
    s = s.replace(" ", "")
    s = s.replace("-", " ")
    return str(suppression_diacritics(unicode(s, SCO_ENCODING)))


def make_key(nom, prenom):
    nom = suppr_acc_and_ponct(nom).upper()
    prenom = suppr_acc_and_ponct(prenom).upper()
    return nom + " " + prenom[:4]


reader = csv.reader(open(CSVFILENAME, "rb"))
noms = {}
for row in reader:
    if row[0][0] != "#":
        key = make_key(row[idx_nom], row[idx_prenom])
        if noms.has_key(key):
            raise ValueError, "duplicate key: %s" % key
        noms[key] = row

cnx = psycopg.connect(DBCNXSTRING)

cursor = cnx.cursor()
cursor.execute(
    "select * from identite i, notes_formsemestre_inscription ins where i.etudid = ins.etudid and ins.formsemestre_id = '%s'"
    % formsemestre_id
)
R = cursor.dictfetchall()

nok = 0
print "nom,prenom,ine,nip"
for e in R:
    key = make_key(e["nom"], e["prenom"])
    if not noms.has_key(key):
        print "** no match for %s (%s)" % (key, e["etudid"])
    else:
        info = noms[key]
        print "%s,%s,%s,%s" % (e["nom"], e["prenom"], e["code_ine"], e["code_nip"])
        nok += 1

cnx.commit()

print "%d etudiants, %d ok" % (len(R), nok)
