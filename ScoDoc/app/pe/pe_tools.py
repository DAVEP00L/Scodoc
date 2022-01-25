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

##############################################################################
#  Module "Avis de poursuite d'étude"
#  conçu et développé par Cléo Baras (IUT de Grenoble)
##############################################################################

"""
Created on Thu Sep  8 09:36:33 2016

@author: barasc
"""
from __future__ import print_function

import os
import datetime
import re
import unicodedata

import app.scodoc.sco_utils as scu
from app import log

PE_DEBUG = 0

if not PE_DEBUG:
    # log to notes.log
    def pe_print(*a, **kw):
        # kw is ignored. log always add a newline
        log(" ".join(a))


else:
    pe_print = print  # print function


# Generated LaTeX files are encoded as:
PE_LATEX_ENCODING = "utf-8"

# /opt/scodoc/tools/doc_poursuites_etudes
REP_DEFAULT_AVIS = os.path.join(scu.SCO_TOOLS_DIR, "doc_poursuites_etudes/")
REP_LOCAL_AVIS = os.path.join(scu.SCODOC_CFG_DIR, "doc_poursuites_etudes/")

PE_DEFAULT_AVIS_LATEX_TMPL = REP_DEFAULT_AVIS + "distrib/modeles/un_avis.tex"
PE_LOCAL_AVIS_LATEX_TMPL = REP_LOCAL_AVIS + "local/modeles/un_avis.tex"
PE_DEFAULT_FOOTER_TMPL = REP_DEFAULT_AVIS + "distrib/modeles/un_footer.tex"
PE_LOCAL_FOOTER_TMPL = REP_LOCAL_AVIS + "local/modeles/un_footer.tex"

# ----------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------
def print_semestres_description(sems, avec_affichage_debug=False):
    """Dediee a l'affichage d'un semestre pour debug du module"""

    def chaine_semestre(sem):
        desc = (
            "S"
            + str(sem["semestre_id"])
            + " "
            + sem["modalite"]
            + " "
            + sem["anneescolaire"]
        )
        desc += " (" + sem["annee_debut"] + "/" + sem["annee_fin"] + ") "
        desc += str(sem["formation_id"]) + " / " + str(sem["formsemestre_id"])
        desc += " - " + sem["titre_num"]
        return desc

    if avec_affichage_debug == True:
        if isinstance(sems, list):
            for sem in sems:
                pe_print(chaine_semestre(sem))
        else:
            pe_print(chaine_semestre(sems))


# ----------------------------------------------------------------------------------------
def calcul_age(born):
    """Calcule l'age à partir de la date de naissance sous forme d'une chaine de caractère 'jj/mm/aaaa'.
    Aucun test de validité sur le format de la date n'est fait.
    """
    if not isinstance(born, str) or born == "":
        return ""

    donnees = born.split("/")
    naissance = datetime.datetime(int(donnees[2]), int(donnees[1]), int(donnees[0]))
    today = datetime.date.today()
    return (
        today.year
        - naissance.year
        - ((today.month, today.day) < (naissance.month, naissance.day))
    )


# ----------------------------------------------------------------------------------------
def remove_accents(input_unicode_str):
    """Supprime les accents d'une chaine unicode"""
    nfkd_form = unicodedata.normalize("NFKD", input_unicode_str)
    only_ascii = nfkd_form.encode("ASCII", "ignore")
    return only_ascii


def escape_for_latex(s):
    """Protège les caractères pour inclusion dans du source LaTeX"""
    if not s:
        return ""
    conv = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\^{}",
        "\\": r"\textbackslash{}",
        "<": r"\textless ",
        ">": r"\textgreater ",
    }
    exp = re.compile(
        "|".join(
            re.escape(key)
            for key in sorted(list(conv.keys()), key=lambda item: -len(item))
        )
    )
    return exp.sub(lambda match: conv[match.group()], s)


# ----------------------------------------------------------------------------------------
def list_directory_filenames(path):
    """List of regular filenames in a directory (recursive)
    Excludes files and directories begining with .
    """
    R = []
    for root, dirs, files in os.walk(path, topdown=True):
        dirs[:] = [d for d in dirs if d[0] != "."]
        R += [os.path.join(root, fn) for fn in files if fn[0] != "."]
    return R


def add_local_file_to_zip(zipfile, ziproot, pathname, path_in_zip):
    """Read pathname server file and add content to zip under path_in_zip"""
    rooted_path_in_zip = os.path.join(ziproot, path_in_zip)
    zipfile.write(filename=pathname, arcname=rooted_path_in_zip)
    # data = open(pathname).read()
    # zipfile.writestr(rooted_path_in_zip, data)


def add_refs_to_register(register, directory):
    """Ajoute les fichiers trouvés dans directory au registre (dictionaire) sous la forme
    filename => pathname
    """
    length = len(directory)
    for pathname in list_directory_filenames(directory):
        filename = pathname[length + 1 :]
        register[filename] = pathname


def add_pe_stuff_to_zip(zipfile, ziproot):
    """Add auxiliary files to (already opened) zip
    Put all local files found under config/doc_poursuites_etudes/local
    and config/doc_poursuites_etudes/distrib
    If a file is present in both subtrees, take the one in local.

    Also copy logos
    """
    register = {}
    # first add standard (distrib references)
    distrib_dir = os.path.join(REP_DEFAULT_AVIS, "distrib")
    add_refs_to_register(register=register, directory=distrib_dir)
    # then add local references (some oh them may overwrite distrib refs)
    local_dir = os.path.join(REP_LOCAL_AVIS, "local")
    add_refs_to_register(register=register, directory=local_dir)
    # at this point register contains all refs (filename, pathname) to be saved
    for filename, pathname in register.items():
        add_local_file_to_zip(zipfile, ziproot, pathname, "avis/" + filename)

    # Logos: (add to logos/ directory in zip)
    logos_names = ["logo_header.jpg", "logo_footer.jpg"]
    for f in logos_names:
        logo = os.path.join(scu.SCODOC_LOGOS_DIR, f)
        if os.path.isfile(logo):
            add_local_file_to_zip(zipfile, ziproot, logo, "avis/logos/" + f)


# ----------------------------------------------------------------------------------------
# Variable pour le debug des avislatex (en squeezant le calcul du jury souvent long)
JURY_SYNTHESE_POUR_DEBUG = {
    "EID1810": {
        "nom": "ROUX",
        "entree": "2016",
        "civilite_str": "M.",
        "promo": 2016,
        "S2": {
            "groupe": {
                "informatique": (
                    13.184230769230767,
                    0.21666666666666667,
                    "18",
                    78,
                    9.731491508491509,
                    18.46846153846154,
                    18.46846153846154,
                ),
                "technique": (
                    12.975409073359078,
                    0.6166666666666666,
                    "16",
                    78,
                    9.948540264387688,
                    18.29285714285714,
                    18.29285714285714,
                ),
                "pe": (
                    12.016584900684544,
                    1.116666666666667,
                    "20",
                    78,
                    9.83147528118408,
                    17.691755169172936,
                    17.691755169172936,
                ),
                "mathematiques": (
                    12.25,
                    0.1,
                    "15 ex",
                    78,
                    8.45153073717949,
                    19.0625,
                    19.0625,
                ),
                "dut": (
                    12.43750128724589,
                    1.0,
                    "19",
                    78,
                    10.151630181286441,
                    17.881104750512645,
                    17.881104750512645,
                ),
            },
            "promo": {
                "informatique": (
                    13.184230769230767,
                    0.21666666666666667,
                    "25",
                    73,
                    11.696187214611871,
                    18.51346153846154,
                    18.51346153846154,
                ),
                "technique": (
                    12.975409073359078,
                    0.6166666666666666,
                    "23",
                    73,
                    11.862307379173147,
                    17.616047267953675,
                    17.616047267953675,
                ),
                "pe": (
                    12.016584900684544,
                    1.116666666666667,
                    "28",
                    73,
                    11.571004424603757,
                    16.706338951857248,
                    16.706338951857248,
                ),
                "mathematiques": (
                    12.25,
                    0.1,
                    "18 ex",
                    73,
                    10.00886454908676,
                    19.0625,
                    19.0625,
                ),
                "dut": (
                    12.43750128724589,
                    1.0,
                    "25",
                    73,
                    11.88798432763965,
                    17.397627309377608,
                    17.397627309377608,
                ),
            },
        },
        "S1": {
            "groupe": {
                "informatique": (
                    16.064999999999998,
                    0.16666666666666669,
                    "11",
                    82,
                    11.020296296296294,
                    19.325999999999997,
                    19.325999999999997,
                ),
                "technique": (
                    14.513007894736845,
                    0.6333333333333333,
                    "11",
                    82,
                    11.195082967479676,
                    18.309764912280702,
                    18.309764912280702,
                ),
                "pe": (
                    13.260301515151516,
                    1.1,
                    "19",
                    82,
                    10.976036277232245,
                    17.7460505050505,
                    17.7460505050505,
                ),
                "mathematiques": (
                    11.142850000000001,
                    0.13333333333333333,
                    "34",
                    82,
                    10.314605121951217,
                    19.75,
                    19.75,
                ),
                "dut": (
                    13.54367375,
                    1.0,
                    "19",
                    82,
                    11.22193801880508,
                    18.226902529333334,
                    18.226902529333334,
                ),
            },
            "promo": {
                "informatique": (
                    16.064999999999998,
                    0.16666666666666669,
                    "15",
                    73,
                    13.265276712328768,
                    19.325999999999997,
                    19.325999999999997,
                ),
                "technique": (
                    14.513007894736845,
                    0.6333333333333333,
                    "16",
                    73,
                    12.996048795361693,
                    18.309764912280702,
                    18.309764912280702,
                ),
                "pe": (
                    13.260301515151516,
                    1.1,
                    "25",
                    73,
                    12.4107195879539,
                    17.7460505050505,
                    17.7460505050505,
                ),
                "mathematiques": (
                    11.142850000000001,
                    0.13333333333333333,
                    "39",
                    73,
                    11.320606952054794,
                    19.75,
                    19.75,
                ),
                "dut": (
                    13.54367375,
                    1.0,
                    "25",
                    73,
                    12.730581289342638,
                    18.226902529333334,
                    18.226902529333334,
                ),
            },
        },
        "4S": {
            "groupe": {
                "informatique": (
                    14.84359375,
                    0.5333333333333333,
                    "2",
                    19,
                    10.69933552631579,
                    18.28646875,
                    18.28646875,
                ),
                "pe": (
                    12.93828572598162,
                    3.75,
                    "4",
                    19,
                    11.861967145815218,
                    15.737718967605682,
                    15.737718967605682,
                ),
                "mathematiques": (None, None, "1 ex", 19, None, None, None),
                "ptut": (None, None, "1 ex", 19, None, None, None),
                "dut": (
                    13.511767410105122,
                    4.0,
                    "4",
                    19,
                    12.573349864933606,
                    15.781651391587998,
                    15.781651391587998,
                ),
            },
            "promo": {
                "informatique": (
                    16.075,
                    0.1,
                    "4",
                    73,
                    10.316541095890413,
                    19.333333333333336,
                    19.333333333333336,
                ),
                "pe": (
                    13.52416666666667,
                    0.49999999999999994,
                    "13",
                    73,
                    11.657102668465479,
                    16.853208080808084,
                    16.853208080808084,
                ),
                "mathematiques": (
                    None,
                    None,
                    "55 ex",
                    73,
                    7.705091805555555,
                    19.8,
                    19.8,
                ),
                "dut": (
                    14.425416666666665,
                    1.0,
                    "12",
                    73,
                    13.188168241098825,
                    16.612613522048612,
                    16.612613522048612,
                ),
            },
        },
        "S4": {
            "groupe": {
                "informatique": (
                    16.075,
                    0.1,
                    "1",
                    19,
                    8.799078947368422,
                    16.075,
                    16.075,
                ),
                "technique": (
                    13.835576923076923,
                    0.4333333333333333,
                    "4",
                    19,
                    12.238304655870447,
                    16.521153846153847,
                    16.521153846153847,
                ),
                "pe": (
                    13.52416666666667,
                    0.49999999999999994,
                    "4",
                    19,
                    12.292846491228072,
                    16.25833333333334,
                    16.25833333333334,
                ),
                "dut": (
                    14.425416666666665,
                    1.0,
                    "6",
                    19,
                    13.628367861842106,
                    15.267566666666665,
                    15.267566666666665,
                ),
            },
            "promo": {
                "informatique": (
                    16.075,
                    0.1,
                    "4",
                    73,
                    10.316541095890413,
                    19.333333333333336,
                    19.333333333333336,
                ),
                "pe": (
                    13.52416666666667,
                    0.49999999999999994,
                    "13",
                    73,
                    11.657102668465479,
                    16.853208080808084,
                    16.853208080808084,
                ),
                "technique": (
                    13.835576923076923,
                    0.4333333333333333,
                    "11",
                    73,
                    12.086685508009952,
                    17.25909420289855,
                    17.25909420289855,
                ),
                "mathematiques": (
                    None,
                    None,
                    "55 ex",
                    73,
                    7.705091805555555,
                    19.8,
                    19.8,
                ),
                "ptut": (
                    13.5,
                    0.13333333333333333,
                    "50",
                    73,
                    13.898173515981734,
                    17.083333333333332,
                    17.083333333333332,
                ),
                "dut": (
                    14.425416666666665,
                    1.0,
                    "12",
                    73,
                    13.188168241098825,
                    16.612613522048612,
                    16.612613522048612,
                ),
            },
        },
        "1A": {
            "groupe": {
                "informatique": (
                    14.43673913043478,
                    0.38333333333333336,
                    "16",
                    78,
                    11.046040002787066,
                    18.85992173913043,
                    18.85992173913043,
                ),
                "technique": (
                    13.754459142857144,
                    1.25,
                    "14",
                    78,
                    11.179785631638866,
                    18.493250340136054,
                    18.493250340136054,
                ),
                "pe": (
                    12.633767581547854,
                    2.216666666666667,
                    "18",
                    78,
                    10.912253971396854,
                    18.39547581699347,
                    18.39547581699347,
                ),
                "mathematiques": (
                    11.617342857142857,
                    0.23333333333333334,
                    "24",
                    78,
                    9.921286855287565,
                    19.375000000000004,
                    19.375000000000004,
                ),
                "dut": (
                    12.990587518622945,
                    2.0,
                    "18",
                    78,
                    11.2117147027821,
                    18.391345156695156,
                    18.391345156695156,
                ),
            },
            "promo": {
                "informatique": (
                    13.184230769230767,
                    0.21666666666666667,
                    "25",
                    73,
                    11.696187214611871,
                    18.51346153846154,
                    18.51346153846154,
                ),
                "technique": (
                    12.975409073359078,
                    0.6166666666666666,
                    "23",
                    73,
                    11.862307379173147,
                    17.616047267953675,
                    17.616047267953675,
                ),
                "pe": (
                    12.016584900684544,
                    1.116666666666667,
                    "28",
                    73,
                    11.571004424603757,
                    16.706338951857248,
                    16.706338951857248,
                ),
                "mathematiques": (
                    12.25,
                    0.1,
                    "18 ex",
                    73,
                    10.00886454908676,
                    19.0625,
                    19.0625,
                ),
                "dut": (
                    12.43750128724589,
                    1.0,
                    "25",
                    73,
                    11.88798432763965,
                    17.397627309377608,
                    17.397627309377608,
                ),
            },
        },
        "2A": {
            "groupe": {
                "informatique": (
                    15.88333333333333,
                    0.15000000000000002,
                    "2",
                    19,
                    9.805818713450288,
                    17.346666666666668,
                    17.346666666666668,
                ),
                "pe": (
                    13.378513043478259,
                    1.5333333333333334,
                    "6",
                    19,
                    12.099566454042717,
                    16.06209927536232,
                    16.06209927536232,
                ),
                "technique": (
                    13.965093333333336,
                    1.1666666666666665,
                    "5",
                    19,
                    12.51068332957394,
                    16.472092380952386,
                    16.472092380952386,
                ),
                "mathematiques": (None, None, "1 ex", 19, None, None, None),
                "dut": (
                    14.032947301587301,
                    2.0,
                    "4",
                    19,
                    13.043386086541773,
                    15.574706269841268,
                    15.574706269841268,
                ),
            },
            "promo": {
                "informatique": (
                    16.075,
                    0.1,
                    "4",
                    73,
                    10.316541095890413,
                    19.333333333333336,
                    19.333333333333336,
                ),
                "pe": (
                    13.52416666666667,
                    0.49999999999999994,
                    "13",
                    73,
                    11.657102668465479,
                    16.853208080808084,
                    16.853208080808084,
                ),
                "technique": (
                    13.835576923076923,
                    0.4333333333333333,
                    "11",
                    73,
                    12.086685508009952,
                    17.25909420289855,
                    17.25909420289855,
                ),
                "mathematiques": (
                    None,
                    None,
                    "55 ex",
                    73,
                    7.705091805555555,
                    19.8,
                    19.8,
                ),
                "dut": (
                    14.425416666666665,
                    1.0,
                    "12",
                    73,
                    13.188168241098825,
                    16.612613522048612,
                    16.612613522048612,
                ),
            },
        },
        "nbSemestres": 4,
        "nip": "21414563",
        "prenom": "Baptiste",
        "age": "21",
        "lycee": "PONCET",
        "3S": {
            "groupe": {
                "informatique": (
                    14.559423076923077,
                    0.43333333333333335,
                    "3",
                    19,
                    11.137856275303646,
                    18.8095,
                    18.8095,
                ),
                "pe": (
                    12.84815019664546,
                    3.25,
                    "4",
                    19,
                    11.795678015751701,
                    15.657624449801428,
                    15.657624449801428,
                ),
                "technique": (
                    13.860638395358142,
                    1.9833333333333334,
                    "3",
                    19,
                    12.395950358235925,
                    17.340302131732695,
                    17.340302131732695,
                ),
                "mathematiques": (
                    11.494044444444445,
                    0.3,
                    "6",
                    19,
                    9.771571754385965,
                    14.405358333333334,
                    14.405358333333334,
                ),
                "dut": (
                    13.207217657917942,
                    3.0,
                    "4",
                    19,
                    12.221677199297439,
                    15.953012966561774,
                    15.953012966561774,
                ),
            },
            "promo": {
                "informatique": (15.5, 0.05, "13", 73, 10.52222222222222, 20.0, 20.0),
                "pe": (
                    13.308035483870967,
                    1.0333333333333334,
                    "17",
                    73,
                    11.854843423685786,
                    16.191317607526884,
                    16.191317607526884,
                ),
                "technique": (
                    14.041625757575758,
                    0.7333333333333333,
                    "10",
                    73,
                    11.929466899200335,
                    16.6400384469697,
                    16.6400384469697,
                ),
                "mathematiques": (
                    11.0625,
                    0.06666666666666667,
                    "40",
                    73,
                    11.418430205479451,
                    19.53,
                    19.53,
                ),
                "dut": (
                    13.640477936507937,
                    1.0,
                    "14",
                    73,
                    12.097377866597594,
                    16.97088994741667,
                    16.97088994741667,
                ),
            },
        },
        "bac": "STI2D",
        "S3": {
            "groupe": {
                "informatique": (15.5, 0.05, "5", 19, 12.842105263157896, 20.0, 20.0),
                "pe": (
                    13.308035483870967,
                    1.0333333333333334,
                    "8",
                    19,
                    12.339608902093943,
                    15.967147311827956,
                    15.967147311827956,
                ),
                "technique": (
                    14.041625757575758,
                    0.7333333333333333,
                    "7",
                    19,
                    13.128539816586922,
                    16.44310151515152,
                    16.44310151515152,
                ),
                "mathematiques": (
                    11.0625,
                    0.06666666666666667,
                    "6",
                    19,
                    9.280921052631578,
                    16.125,
                    16.125,
                ),
                "dut": (
                    13.640477936507937,
                    1.0,
                    "8",
                    19,
                    12.83638061385213,
                    15.881845873015871,
                    15.881845873015871,
                ),
            },
            "promo": {
                "informatique": (15.5, 0.05, "13", 73, 10.52222222222222, 20.0, 20.0),
                "pe": (
                    13.308035483870967,
                    1.0333333333333334,
                    "17",
                    73,
                    11.854843423685786,
                    16.191317607526884,
                    16.191317607526884,
                ),
                "technique": (
                    14.041625757575758,
                    0.7333333333333333,
                    "10",
                    73,
                    11.929466899200335,
                    16.6400384469697,
                    16.6400384469697,
                ),
                "mathematiques": (
                    11.0625,
                    0.06666666666666667,
                    "40",
                    73,
                    11.418430205479451,
                    19.53,
                    19.53,
                ),
                "dut": (
                    13.640477936507937,
                    1.0,
                    "14",
                    73,
                    12.097377866597594,
                    16.97088994741667,
                    16.97088994741667,
                ),
            },
        },
        "parcours": [
            {
                "nom_semestre_dans_parcours": "semestre 4 FAP  2016",
                "titreannee": "DUT RT UFA (PPN 2013), semestre 4 FAP  2016",
            },
            {
                "nom_semestre_dans_parcours": "semestre 3 FAP  2015-2016",
                "titreannee": "DUT RT UFA (PPN 2013), semestre 3 FAP  2015-2016",
            },
            {
                "nom_semestre_dans_parcours": "semestre 2 FI  2015",
                "titreannee": "DUT RT, semestre 2 FI  2015",
            },
            {
                "nom_semestre_dans_parcours": "semestre 1 FI  2014-2015",
                "titreannee": "DUT RT, semestre 1 FI  2014-2015",
            },
        ],
    }
}
