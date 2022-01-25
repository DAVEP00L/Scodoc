# -*- mode: python -*-
# -*- coding: utf-8 -*-

##############################################################################
#
# Gestion scolarite IUT
#
# Copyright (c) 1999 - 2021 Emmanuel Viennet.  All rights reserved.
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

"""ScoDoc : stockage et vérifications des "maquettes" Apogée 
   (fichiers CSV pour l'export vers Apogée)
   associées aux années scolaires

   Voir sco_apogee_csv.py pour la structure du fichier Apogée.

   Stockage: utilise sco_archive.py
   => /opt/scodoc/var/scodoc/archives/apo_csv/<dept_id>/2016-1/2016-07-03-16-12-19/V3ASR.csv 
   pour une maquette de l'année scolaire 2016, semestre 1, etape V3ASR

   ou bien (à partir de ScoDoc 1678) :
   /opt/scodoc/var/scodoc/archives/apo_csv/<dept_id>/2016-1/2016-07-03-16-12-19/V3ASR!111.csv 
   pour une maquette de l'étape V3ASR version VDI 111.

   La version VDI sera ignorée sauf si elle est indiquée dans l'étape du semestre.
   apo_csv_get() 
   
   API:
   apo_csv_store( annee_scolaire, sem_id)        
      store maq file (archive)
      
   apo_csv_get(etape_apo, annee_scolaire, sem_id, vdi_apo=None)
      get maq data (read stored file and returns string)
      if vdi_apo, get maq for this etape/vdi, else returns the first matching etape.

   apo_csv_delete(etape_apo, annee_scolaire, sem_id)

   apo_csv_list_stored_etapes(annee_scolaire=None, sem_id=None, etapes=None) 
       returns: liste des codes etapes et version vdi stockés (pour l'annee_scolaire et le sem_id indiqués)

   apo_csv_semset_check(semset)
      check students in stored maqs vs students in sem
      Cas à détecter:
      - etudiants ScoDoc sans code NIP
      - etudiants dans sem (ScoDoc) mais dans aucun CSV
      - etudiants dans un CSV mais pas dans sem ScoDoc
      - etudiants dans plusieurs CSV (argh!)
      detecte aussi si on a plusieurs années scolaires
      
      returns: etuds_ok (in ScoDoc and CSVs)
               etuds_no_apo
               unknown_apo : liste de { 'NIP', 'nom', 'prenom' }
               dups_apo : liste de { 'NIP', 'nom', 'prenom', 'etapes_apo' }
               etapes_missing_csv : liste des étapes du semestre sans maquette CSV

   apo_csv_check_etape(semset, set_nips, etape_apo)
      check une etape
      
"""

import re

import app.scodoc.sco_utils as scu
from app.scodoc import sco_archives
from app.scodoc import sco_apogee_csv
from app.scodoc.sco_exceptions import ScoValueError


class ApoCSVArchiver(sco_archives.BaseArchiver):
    def __init__(self):
        sco_archives.BaseArchiver.__init__(self, archive_type="apo_csv")


ApoCSVArchive = ApoCSVArchiver()


# def get_sem_apo_archive(formsemestre_id):
#     """Get, or create if necessary, the archive for apo CSV files"""

#     archive_id

#     return archive_id


def apo_csv_store(csv_data: str, annee_scolaire, sem_id):
    """
    csv_data: maquette content (string)
    annee_scolaire: int (2016)
    sem_id: 0 (année ?), 1 (premier semestre de l'année) ou 2 (deuxième semestre)
    :return: etape_apo du fichier CSV stocké

    Note: le fichier CSV est stocké encodé en APO_OUTPUT_ENCODING
    """
    # sanity check
    filesize = len(csv_data)
    if filesize < 10 or filesize > scu.CONFIG.ETUD_MAX_FILE_SIZE:
        raise ScoValueError("Fichier csv de taille invalide ! (%d)" % filesize)

    if not annee_scolaire:
        raise ScoValueError("Impossible de déterminer l'année scolaire !")

    apo_data = sco_apogee_csv.ApoData(
        csv_data, periode=sem_id
    )  # parse le fichier -> exceptions

    filename = str(apo_data.etape) + ".csv"  # will concatenate VDI to etape

    if str(apo_data.etape) in apo_csv_list_stored_etapes(annee_scolaire, sem_id=sem_id):
        raise ScoValueError(
            "Etape %s déjà stockée pour cette année scolaire !" % apo_data.etape
        )

    oid = "%d-%d" % (annee_scolaire, sem_id)
    description = "%s;%s;%s" % (str(apo_data.etape), annee_scolaire, sem_id)
    archive_id = ApoCSVArchive.create_obj_archive(oid, description)
    csv_data_bytes = csv_data.encode(sco_apogee_csv.APO_OUTPUT_ENCODING)
    ApoCSVArchive.store(archive_id, filename, csv_data_bytes)

    return apo_data.etape


def apo_csv_list_stored_archives(annee_scolaire=None, sem_id=None, etapes=None):
    """
    :return: list of informations about stored CSV
    [ { } ]
    """
    oids = ApoCSVArchive.list_oids()  # [ '2016-1', ... ]
    # filter
    if annee_scolaire:
        e = re.compile(str(annee_scolaire) + "-.+")
        oids = [x for x in oids if e.match(x)]
    if sem_id:
        e = re.compile(r"[0-9]{4}-" + str(sem_id))
        oids = [x for x in oids if e.match(x)]

    infos = []  # liste d'infos
    for oid in oids:
        archive_ids = ApoCSVArchive.list_obj_archives(oid)
        for archive_id in archive_ids:
            description = ApoCSVArchive.get_archive_description(archive_id)
            fs = tuple(description.split(";"))
            if len(fs) == 3:
                arch_etape_apo, arch_annee_scolaire, arch_sem_id = fs
            else:
                raise ValueError("Archive invalide: " + archive_id)

            if (etapes is None) or (arch_etape_apo in etapes):
                infos.append(
                    {
                        "archive_id": archive_id,
                        "annee_scolaire": int(arch_annee_scolaire),
                        "sem_id": int(arch_sem_id),
                        "etape_apo": arch_etape_apo,  # qui contient éventuellement le VDI
                        "date": ApoCSVArchive.get_archive_date(archive_id),
                    }
                )
    infos.sort(key=lambda x: x["etape_apo"])

    return infos


def apo_csv_list_stored_etapes(annee_scolaire, sem_id=None, etapes=None):
    """
    :return: list of stored etapes [ ApoEtapeVDI, ... ]
    """
    infos = apo_csv_list_stored_archives(
        annee_scolaire=annee_scolaire, sem_id=sem_id, etapes=etapes
    )
    return [info["etape_apo"] for info in infos]


def apo_csv_delete(archive_id):
    """Delete archived CSV"""
    ApoCSVArchive.delete_archive(archive_id)


def apo_csv_get_archive(etape_apo, annee_scolaire="", sem_id=""):
    """Get archive"""
    stored_archives = apo_csv_list_stored_archives(
        annee_scolaire=annee_scolaire, sem_id=sem_id
    )
    for info in stored_archives:
        if info["etape_apo"] == etape_apo:
            return info
    return None


def apo_csv_get(etape_apo="", annee_scolaire="", sem_id="") -> str:
    """Get CSV data for given etape_apo
    :return: CSV, as a data string
    """
    info = apo_csv_get_archive(etape_apo, annee_scolaire, sem_id)
    if not info:
        raise ScoValueError(
            "Etape %s non enregistree (%s, %s)" % (etape_apo, annee_scolaire, sem_id)
        )
    archive_id = info["archive_id"]
    data = ApoCSVArchive.get(archive_id, etape_apo + ".csv")
    # ce fichier a été archivé donc généré par ScoDoc
    # son encodage est donc APO_OUTPUT_ENCODING
    return data.decode(sco_apogee_csv.APO_OUTPUT_ENCODING)


# ------------------------------------------------------------------------


def apo_get_sem_etapes(sem):
    """Etapes de ce semestre: pour l'instant, celles déclarées
    Dans une future version, on pourrait aussi utiliser les étapes
    d'inscription des étudiants, recupérées via le portail,
    voir check_paiement_etuds().

    :return: list of etape_apo (ApoEtapeVDI instances)
    """
    return sem["etapes"]


def apo_csv_check_etape(semset, set_nips, etape_apo):
    """Check etape vs set of sems"""
    # Etudiants dans la maquette CSV:
    csv_data = apo_csv_get(etape_apo, semset["annee_scolaire"], semset["sem_id"])
    apo_data = sco_apogee_csv.ApoData(csv_data, periode=semset["sem_id"])
    apo_nips = {e["nip"] for e in apo_data.etuds}
    #
    nips_ok = set_nips.intersection(apo_nips)
    nips_no_apo = set_nips - apo_nips  # dans ScoDoc mais pas dans cette maquette Apogée
    nips_no_sco = apo_nips - set_nips  # dans Apogée mais pas dans ScoDoc

    # Elements Apogee vs ScoDoc
    apo_data.setup()
    maq_elems, sem_elems = apo_data.list_elements()

    return nips_ok, apo_nips, nips_no_apo, nips_no_sco, maq_elems, sem_elems


def apo_csv_semset_check(
    semset, allow_missing_apo=False, allow_missing_csv=False
):  # was apo_csv_check
    """
    check students in stored maqs vs students in semset
      Cas à détecter:
      - étapes sans maquette CSV (etapes_missing_csv)
      - etudiants ScoDoc sans code NIP (etuds_without_nip)
      - etudiants dans semset (ScoDoc) mais dans aucun CSV (nips_no_apo)
      - etudiants dans un CSV mais pas dans semset ScoDoc (nips_no_sco)
      - etudiants dans plusieurs CSV (argh!)
      + si plusieurs annees scolaires
    """
    # Etapes du semestre sans maquette CSV:
    etapes_apo = apo_csv_list_stored_etapes(
        semset["annee_scolaire"], semset["sem_id"], etapes=semset.list_etapes()
    )
    etapes_missing_csv = []
    for e in semset.list_etapes():
        if not e in etapes_apo:
            etapes_missing_csv.append(e)

    # Etudiants inscrits dans ce semset:
    semset.load_etuds()

    set_nips = set().union(*[s["nips"] for s in semset.sems])
    #
    nips_ok = set()  # codes nip des etudiants dans ScoDoc et Apogée
    nips_no_apo = set_nips.copy()  # dans ScoDoc mais pas dans Apogée
    nips_no_sco = set()  # dans Apogée mais pas dans ScoDoc
    etapes_apo_nips = []  # liste des nip de chaque maquette
    maq_elems = set()
    sem_elems = set()
    for etape_apo in etapes_apo:
        (
            et_nips_ok,
            et_apo_nips,
            et_nips_no_apo,
            et_nips_no_sco,
            et_maq_elems,
            et_sem_elems,
        ) = apo_csv_check_etape(semset, set_nips, etape_apo)
        nips_ok |= et_nips_ok
        nips_no_apo -= et_apo_nips
        nips_no_sco |= et_nips_no_sco
        etapes_apo_nips.append(et_apo_nips)
        maq_elems |= et_maq_elems
        sem_elems |= et_sem_elems

    # doublons: etudiants mentionnés dans plusieurs maquettes Apogée:
    apo_dups = set()
    if len(etapes_apo_nips) > 1:
        all_nips = etapes_apo_nips[0]
        for etape_apo_nips in etapes_apo_nips[1:]:
            apo_dups |= all_nips & etape_apo_nips
            all_nips |= etape_apo_nips

    # All ok ?
    ok_for_export = (
        ((not etapes_missing_csv) or allow_missing_csv)
        and (not semset["etuds_without_nip"])
        and ((not nips_no_apo) or allow_missing_apo)
        and (not apo_dups)
        and len(semset.annees_scolaires()) <= 1
    )

    return (
        ok_for_export,
        etapes_missing_csv,
        semset["etuds_without_nip"],
        nips_ok,
        nips_no_apo,
        nips_no_sco,
        apo_dups,
        maq_elems,
        sem_elems,
    )


def apo_csv_retreive_etuds_by_nip(semset, nips):
    """
    Search info about listed nips in stored CSV
    :return: list [ { 'etape_apo', 'nip', 'nom', 'prenom' } ]
    """
    apo_etuds_by_nips = {}
    etapes_apo = apo_csv_list_stored_etapes(semset["annee_scolaire"], semset["sem_id"])
    for etape_apo in etapes_apo:
        csv_data = apo_csv_get(etape_apo, semset["annee_scolaire"], semset["sem_id"])
        apo_data = sco_apogee_csv.ApoData(csv_data, periode=semset["sem_id"])
        etape_apo = apo_data.etape_apogee
        for e in apo_data.etuds:
            e["etape_apo"] = etape_apo
        apo_etuds_by_nips.update(dict([(e["nip"], e) for e in apo_data.etuds]))

    etuds = {}  # { nip : etud or None }
    for nip in nips:
        etuds[nip] = apo_etuds_by_nips.get(nip, {"nip": nip, "etape_apo": "?"})

    return etuds


"""
Tests:

from debug import *
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_formsemestre
from app.scodoc.sco_etape_apogee import *
from app.scodoc.sco_apogee_csv import *
from app.scodoc.sco_semset import *

app.set_sco_dept('RT')
csv_data = open('/opt/misc/VDTRT_V1RT.TXT').read()
annee_scolaire=2015
sem_id=1

apo_data = sco_apogee_csv.ApoData(csv_data, periode=sem_id)
print apo_data.etape_apogee

apo_data.setup()
e = apo_data.etuds[0]
e.lookup_scodoc( apo_data.etape_formsemestre_ids)
e.associate_sco( apo_data)

print apo_csv_list_stored_archives()


apo_csv_store(csv_data, annee_scolaire, sem_id)



groups_infos = sco_groups_view.DisplayedGroupsInfos( [sco_groups.get_default_group(formsemestre_id)], formsemestre_id=formsemestre_id)

nt = sco_cache.NotesTableCache.get( formsemestre_id)

#
s = SemSet('NSS29902')
apo_data = sco_apogee_csv.ApoData(open('/opt/scodoc/var/scodoc/archives/apo_csv/RT/2015-2/2016-07-10-11-26-15/V1RT.csv').read(), periode=1) 

# cas Tiziri K. (inscrite en S1, démission en fin de S1, pas inscrite en S2)
# => pas de décision, ce qui est voulu (?)
#

apo_data.setup()
e = [ e for e in apo_data.etuds if e['nom'] == 'XYZ' ][0]
e.lookup_scodoc( apo_data.etape_formsemestre_ids)
e.associate_sco(apo_data)

self=e
col_id='apoL_c0129'

# --
from app.scodoc import sco_portal_apogee
_ = go_dept(app, 'GEA').Notes
#csv_data = sco_portal_apogee.get_maquette_apogee(etape='V1GE', annee_scolaire=2015)
csv_data = open('/tmp/V1GE.txt').read()
apo_data = sco_apogee_csv.ApoData(csv_data, periode=1)


# ------
# les elements inconnus:

from debug import *
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_formsemestre
from app.scodoc.sco_etape_apogee import *
from app.scodoc.sco_apogee_csv import *
from app.scodoc.sco_semset import *

_ = go_dept(app, 'RT').Notes
csv_data = open('/opt/misc/V2RT.csv').read()
annee_scolaire=2015
sem_id=1

apo_data = sco_apogee_csv.ApoData(csv_data, periode=1)
print apo_data.etape_apogee

apo_data.setup()
for e in apo_data.etuds:
    e.lookup_scodoc( apo_data.etape_formsemestre_ids)
    e.associate_sco(apo_data)

# ------
# test export jury intermediaire
from debug import *
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_formsemestre
from app.scodoc.sco_etape_apogee import *
from app.scodoc.sco_apogee_csv import *
from app.scodoc.sco_semset import *

_ = go_dept(app, 'CJ').Notes
csv_data = open('/opt/scodoc/var/scodoc/archives/apo_csv/CJ/2016-1/2017-03-06-21-46-32/V1CJ.csv').read()
annee_scolaire=2016
sem_id=1

apo_data = sco_apogee_csv.ApoData(csv_data, periode=1)
print apo_data.etape_apogee

apo_data.setup()
e = [ e for e in apo_data.etuds if e['nom'] == 'XYZ' ][0] #
e.lookup_scodoc( apo_data.etape_formsemestre_ids)
e.associate_sco(apo_data)

self=e

sco_elts = {}
col_id='apoL_c0001'
code = apo_data.cols[col_id]['Code'] # 'V1RT'

sem = apo_data.sems_periode[0] # le S1

"""
