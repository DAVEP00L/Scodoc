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

"""Bacs: noms de séries et spécialités, nomenclatures, abbréviations

Types prédéfinis:
G bacs généraux (S, L, ES, ...)
T bacs technologiques (STI2D, STG, ...)
P bacs professionnels
E diplômes étrangers (équivalences)
X divers
"""

_BACS = (  # tuples (bac, specialite, abbrev, type
    # --- Reçus d'APB de 2013 à 2015 (tel qu'observé à IUTV)
    #  merci d'envoyer vos mises à jour
    ("A1 LETTRES-SCIENCES", "", "A1", "G"),
    ("B ECONOMIQUE ET SOCIAL", "", "B", "G"),
    ("B", "ÉCONOMIQUE ET SOCIAL", "B", "G"),
    ("C MATHÉMATIQUES ET SCIENCES PHYSIQUES", "", "C", "G"),
    ("C MATHEMATIQUES ET SCIENCES PHYSIQUES", "", "C", "G"),
    ("D", "", "D", "G"),
    ("E", "", "E", "G"),
    ("L LITTERATURE", "", "L", "G"),
    ("L LITTÉRATURE", "", "L", "G"),
    ("L LITTÉRATURE", "LITTÉRATURE", "L", "G"),
    ("L", "LITTÉRATURE", "L", "G"),
    ("L", "", "L", "G"),
    ("S", "SCIENTIFIQUE", "S", "G"),
    ("S SCIENTIFIQUE", "", "S", "G"),
    ("S SCIENTIFIQUE", "SCIENTIFIQUE", "S", "G"),
    ("ES ECONOMIQUE ET SOCIAL", "", "ES", "G"),
    ("ES ECONOMIQUE ET SOCIAL", "ECONOMIQUE ET SOCIAL", "ES", "G"),
    ("ES", "ECONOMIQUE ET SOCIAL", "ES", "G"),
    ("0000 SANS BAC", "", "SANS", "X"),
    ("0001 BAC INTERNATIONAL", "", "Int.", "X"),
    ("0021 BACS PROFESSIONNELS INDUSTRIELS", "", "Pro I", "P"),
    ("0021", "BACS PROFESSIONNELS INDUSTRIELS", "Pro I", "P"),
    ("0022 BACS PROFESSIONNELS TERTIAIRES", "", "Pro T", "P"),
    ("0022", "BACS PROFESSIONNELS TERTIAIRES", "Pro T", "P"),
    ("0030 CAPACITE DE DROIT", "", "C.D.", "X"),
    ("0030 CAPACITÉ DE DROIT", "", "C.D.", "X"),
    ("0031 TITRE ÉTRANGER ADMIS EN ÉQUIVALENCE", "", "Etr.", "E"),  # accentué
    ("0031 TITRE ETRANGER ADMIS EN EQUIVALENCE", "", "Etr.", "E"),  # non acc
    (
        "0031 TITRE ETRANGER ADMIS EN EQUIVALENCE",
        "TITRE ETRANGER ADMIS EN EQUIVALENCE",
        "Etr.",
        "E",
    ),
    ("0031", "TITRE ÉTRANGER ADMIS EN ÉQUIVALENCE", "Etr.", "E"),
    ("31", "", "Etr.", "E"),
    ("0032 TITRE FRANCAIS ADMIS EN DISPENSE", "", "Disp.", "X"),
    ("0032", "TITRE FRANCAIS ADMIS EN DISPENSE", "Disp.", "X"),
    ("0033 DAEU A OU ESEU A", "", "DAEU", "X"),
    ("0034 DAEU B OU ESEU B", "", "DAEU", "X"),
    ("0036 VALIDATION ETUDES EXPERIENCES PROF.", "", "VAE", "X"),
    ("0036", "VALIDATION ÉTUDES EXPÉRIENCES PROF.", "VAE", "X"),
    ("0037 AUTRES CAS DE NON BACHELIERS", "", "Non", "X"),
    ("ST DE L'AGRONOMIE ET DU VIVANT", "", "STAV", "T"),
    ("ST DE L'INDUSTRIE ET DU DEVT DURABLE", "", "STI2D", "T"),
    ("ST DU MANAGEMENT ET DE LA GESTION", "", "STMG", "T"),
    ("ST2S SCIENCES ET TECHNO SANTE ET SOCIAL", "", "ST2S", "T"),
    ("ST2S", "SCIENCES ET TECHNO SANTÉ ET SOCIAL", "ST2S", "T"),
    ("STI SCIENCES ET TECHNIQUES INDUSTRIELLES", "", "STI", "T"),
    (
        "STI SCIENCES ET TECHNIQUES INDUSTRIELLES",
        "SCIENCES ET TECHNIQUES INDUSTRIELLES",
        "STI",
        "T",
    ),
    ("STI", "SCIENCES ET TECHNIQUES INDUSTRIELLES", "STI", "T"),
    ("STG SCIENCES ET TECHNOLOGIES DE GESTION", "", "STG", "T"),
    (
        "STG SCIENCES ET TECHNOLOGIES DE GESTION",
        "SCIENCES ET TECHNOLOGIES DE GESTION",
        "STG",
        "T",
    ),
    ("STG", "SCIENCES ET TECHNOLOGIES DE GESTION", "STG", "T"),
    ("STL", "SCIENCES ET TECHNO. DE LABORATOIRE", "STL", "T"),
    ("STL SCIENCES ET TECHNO. DE LABORATOIRE", "", "STL", "T"),
    ("STT SCIENCES ET TECHNOLOGIES TERTIAIRES", "", "STT", "T"),
    ("STT", "SCIENCES ET TECHNOLOGIES TERTIAIRES", "STT", "T"),
    ("STT", "", "STT", "T"),
    ("F3", "", "F3", "T"),
    ("SMS SCIENCES MEDICO-SOCIALES", "", "SMS", "T"),
    ("SMS", "SCIENCES MÉDICO-SOCIALES", "SMS", "T"),
    ("G1 TECHNIQUES ADMINISTRATIVES", "", "G1", "T"),
    ("G2", "", "G2", "T"),
    ("G2 TECHNIQUES QUANTITATIVES DE GESTION", "", "G2", "T"),
    (
        "G2 TECHNIQUES QUANTITATIVES DE GESTION",
        "TECHNIQUES QUANTITATIVES DE GESTION",
        "G2",
        "T",
    ),
    ("G3", "TECHNIQUES COMMERCIALES", "G3", "T"),
    ("HOT", "HÔTELLERIE", "HOT", "P"),
)

# { (bac, specialite) : (abbrev, type) }
BACS_SSP = {(t[0], t[1]): t[2:] for t in _BACS}

# bac :  (abbrev, type) (retient la derniere)
BACS_S = {t[0]: t[2:] for t in _BACS}


class Baccalaureat(object):
    def __init__(self, bac, specialite=""):
        self.bac = bac
        self.specialite = specialite
        self._abbrev, self._type = BACS_SSP.get((bac, specialite), (None, None))
        # Parfois, la specialite commence par la serie: essaye
        if self._type is None and specialite and specialite.startswith(bac):
            specialite = specialite[len(bac) :].strip(" -")
            self._abbrev, self._type = BACS_SSP.get((bac, specialite), (None, None))
        # Cherche la forme serie specialite
        if self._type is None and specialite:
            self._abbrev, self._type = BACS_S.get(bac + " " + specialite, (None, None))
        # Cherche avec juste le bac, sans specialite
        if self._type is None:
            self._abbrev, self._type = BACS_S.get(bac, (None, None))

    def abbrev(self):
        "abbreviation for this bac"
        if self._abbrev is None:
            return (
                self.bac
            )  # could try to build an abbrev, either from bac/specialite or using a user-supplied lookup table (not implemented)
        return self._abbrev

    def type(self):
        "type de bac (une lettre: G, T, P, E, X)"
        return self._type or "X"

    def is_general(self):
        return self.type() == "G"

    def is_techno(self):
        return self.type() == "T"
