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
#   Emmanuel Viennet      emmanuel.viennet@univ-paris13.fr
#
##############################################################################

"""Semestres: Codes gestion parcours (constantes)
"""
import collections
from app import log

NOTES_TOLERANCE = 0.00499999999999  # si note >= (BARRE-TOLERANCE), considere ok
# (permet d'eviter d'afficher 10.00 sous barre alors que la moyenne vaut 9.999)

# Barre sur moyenne générale utilisée pour compensations semestres:
NOTES_BARRE_GEN_COMPENSATION = 10.0 - NOTES_TOLERANCE

# ----------------------------------------------------------------
#  Types d'UE:
UE_STANDARD = 0  # UE "fondamentale"
UE_SPORT = 1  # bonus "sport"
UE_STAGE_LP = 2  # ue "projet tuteuré et stage" dans les Lic. Pro.
UE_STAGE_10 = 3  # ue "stage" avec moyenne requise > 10
UE_ELECTIVE = 4  # UE "élective" dans certains parcours (UCAC?, ISCID)
UE_PROFESSIONNELLE = 5  # UE "professionnelle" (ISCID, ...)
UE_OPTIONNELLE = 6  # UE non fondamentales (ILEPS, ...)


def UE_is_fondamentale(ue_type):
    return ue_type in (UE_STANDARD, UE_STAGE_LP, UE_PROFESSIONNELLE)


def UE_is_professionnelle(ue_type):
    return (
        ue_type == UE_PROFESSIONNELLE
    )  # NB: les UE_PROFESSIONNELLE sont à la fois fondamentales et pro


UE_TYPE_NAME = {
    UE_STANDARD: "Standard",
    UE_SPORT: "Sport/Culture (points bonus)",
    UE_STAGE_LP: "Projet tuteuré et stage (Lic. Pro.)",
    UE_STAGE_10: "Stage (moyenne min. 10/20)",
    UE_ELECTIVE: "Elective (ISCID)",
    UE_PROFESSIONNELLE: "Professionnelle (ISCID)",
    UE_OPTIONNELLE: "Optionnelle",
    #                 UE_FONDAMENTALE : '"Fondamentale" (eg UCAC)',
    #                 UE_OPTIONNELLE : '"Optionnelle" (UCAC)'
}

# Couleurs RGB (dans [0.,1.]) des UE pour les bulletins:
UE_DEFAULT_COLOR = (150 / 255.0, 200 / 255.0, 180 / 255.0)
UE_COLORS = {
    UE_STANDARD: UE_DEFAULT_COLOR,
    UE_SPORT: (0.40, 0.90, 0.50),
    UE_STAGE_LP: (0.80, 0.90, 0.90),
}
UE_SEM_DEFAULT = 1000000  # indice semestre des UE sans modules

# ------------------------------------------------------------------
# Codes proposés par ADIUT / Apogee
ADM = "ADM"  # moyenne gen., barres UE, assiduité: sem. validé
ADC = "ADC"  # admis par compensation (eg moy(S1, S2) > 10)
ADJ = "ADJ"  # admis par le jury
ATT = "ATT"  #
ATJ = "ATJ"  # pb assiduité: décision repoussée au semestre suivant
ATB = "ATB"
AJ = "AJ"
CMP = "CMP"  # utile pour UE seulement (indique UE acquise car semestre acquis)
NAR = "NAR"
RAT = "RAT"  # en attente rattrapage, sera ATT dans Apogée
DEF = "DEF"  # défaillance (n'est pas un code jury dans scodoc mais un état, comme inscrit ou demission)

# codes actions
REDOANNEE = "REDOANNEE"  # redouble annee (va en Sn-1)
REDOSEM = "REDOSEM"  # redouble semestre (va en Sn)
RA_OR_NEXT = "RA_OR_NEXT"  # redouble annee ou passe en Sn+1
RA_OR_RS = "RA_OR_RS"  # redouble annee ou semestre
RS_OR_NEXT = "RS_OR_NEXT"  # redouble semestre ou passe en Sn+1
NEXT_OR_NEXT2 = "NEXT_OR_NEXT2"  # passe en suivant (Sn+1) ou sur-suivant (Sn+2)
NEXT = "NEXT"
NEXT2 = "NEXT2"  # passe au sur-suivant (Sn+2)
REO = "REO"
BUG = "BUG"

ALL = "ALL"

CODES_EXPL = {
    ADM: "Validé",
    ADC: "Validé par compensation",
    ADJ: "Validé par le Jury",
    ATT: "Décision en attente d'un autre semestre (faute d'atteindre la moyenne)",
    ATB: "Décision en attente d'un autre semestre (au moins une UE sous la barre)",
    ATJ: "Décision en attente d'un autre semestre (assiduité insuffisante)",
    AJ: "Ajourné",
    NAR: "Echec, non autorisé à redoubler",
    RAT: "En attente d'un rattrapage",
    DEF: "Défaillant",
}
# Nota: ces explications sont personnalisables via le fichier
#       de config locale /opt/scodoc/var/scodoc/config/scodoc_local.py
#  variable: CONFIG.CODES_EXP

CODES_SEM_VALIDES = {ADM: True, ADC: True, ADJ: True}  # semestre validé
CODES_SEM_ATTENTES = {ATT: True, ATB: True, ATJ: True}  # semestre en attente

CODES_SEM_REO = {NAR: 1}  # reorientation

CODES_UE_VALIDES = {ADM: True, CMP: True}  # UE validée


def code_semestre_validant(code):
    "Vrai si ce CODE entraine la validation du semestre"
    return CODES_SEM_VALIDES.get(code, False)


def code_semestre_attente(code):
    "Vrai si ce CODE est un code d'attente (semestre validable plus tard par jury ou compensation)"
    return CODES_SEM_ATTENTES.get(code, False)


def code_ue_validant(code):
    "Vrai si ce code entraine la validation de l'UE"
    return CODES_UE_VALIDES.get(code, False)


DEVENIR_EXPL = {
    NEXT: "Passage au semestre suivant",
    REDOANNEE: "Redoublement année",
    REDOSEM: "Redoublement semestre",
    RA_OR_NEXT: "Passage, ou redoublement année",
    RA_OR_RS: "Redoublement année, ou redoublement semestre",  # slt si sems decales
    RS_OR_NEXT: "Passage, ou redoublement semestre",
    NEXT_OR_NEXT2: "Passage en semestre suivant ou à celui d'après",
    NEXT2: "Passage au sur-suivant",
    REO: "Réorientation",
}

# Devenirs autorises dans les cursus sans semestres décalés:
DEVENIRS_STD = {NEXT: 1, REDOANNEE: 1, RA_OR_NEXT: 1, REO: 1}

# Devenirs autorises dans les cursus en un seul semestre, semestre_id==-1 (licences ?)
DEVENIRS_MONO = {REDOANNEE: 1, REO: 1}

# Devenirs supplementaires (en mode manuel) pour les cursus avec semestres decales
DEVENIRS_DEC = {REDOSEM: 1, RS_OR_NEXT: 1}

# Devenirs en n+2 (sautant un semestre)  (si semestres décalés et s'il ne manque qu'un semestre avant le n+2)
DEVENIRS_NEXT2 = {NEXT_OR_NEXT2: 1, NEXT2: 1}

NO_SEMESTRE_ID = -1  # code semestre si pas de semestres

# Regles gestion parcours
class DUTRule(object):
    def __init__(self, rule_id, premise, conclusion):
        self.rule_id = rule_id
        self.premise = premise
        self.conclusion = conclusion
        # self.code, self.codes_ue, self.devenir, self.action, self.explication = conclusion

    def match(self, state):
        "True if state match rule premise"
        assert len(state) == len(self.premise)
        for i in range(len(state)):
            prem = self.premise[i]
            if isinstance(prem, (list, tuple)):
                if not state[i] in prem:
                    return False
            else:
                if prem != ALL and prem != state[i]:
                    return False
        return True


# Types de parcours
DEFAULT_TYPE_PARCOURS = 100  # pour le menu de creation nouvelle formation


class TypeParcours(object):
    TYPE_PARCOURS = None  # id, utilisé par notes_formation.type_parcours
    NAME = None  # required
    NB_SEM = 1  # Nombre de semestres
    COMPENSATION_UE = True  # inutilisé
    BARRE_MOY = 10.0
    BARRE_UE_DEFAULT = 8.0
    BARRE_UE = {}
    NOTES_BARRE_VALID_UE_TH = 10.0  # seuil pour valider UE
    NOTES_BARRE_VALID_UE = NOTES_BARRE_VALID_UE_TH - NOTES_TOLERANCE  # barre sur UE
    ALLOW_SEM_SKIP = False  # Passage: autorise-t-on les sauts de semestres ?
    SESSION_NAME = "semestre"
    SESSION_NAME_A = "du "
    SESSION_ABBRV = "S"  # S1, S2, ...
    UNUSED_CODES = set()  # Ensemble des codes jury non autorisés dans ce parcours
    UE_IS_MODULE = False  # 1 seul module par UE (si plusieurs modules, etudiants censéments inscrits à un seul d'entre eux)
    ECTS_ONLY = False  # Parcours avec progression basée uniquement sur les ECTS
    ALLOWED_UE_TYPES = list(
        UE_TYPE_NAME.keys()
    )  # par defaut, autorise tous les types d'UE

    def check(self, formation=None):
        return True, ""  # status, diagnostic_message

    def get_barre_ue(self, ue_type, tolerance=True):
        """Barre pour cette UE (la valeur peut dépendre du type d'UE).
        Si tolerance, diminue de epsilon pour éviter les effets d'arrondis.
        """
        if tolerance:
            t = NOTES_TOLERANCE
        else:
            t = 0.0
        return self.BARRE_UE.get(ue_type, self.BARRE_UE_DEFAULT) - t

    def ues_sous_barre(self, ues_status):
        """Filtre les ues: liste celles ayant une moyenne sous la barre

        ues_status est une liste de dict ayant des entrées 'moy' et 'coef_ue'
        """
        return [
            ue_status
            for ue_status in ues_status
            if ue_status["coef_ue"] > 0
            and isinstance(ue_status["moy"], float)
            and ue_status["moy"] < self.get_barre_ue(ue_status["ue"]["type"])
        ]

    def check_barre_ues(self, ues_status):
        """True si la ou les conditions sur les UE sont valides
        Par defaut, vrai si les moyennes d'UE sont au dessus de la barre.
        Le cas des LP2014 est plus compliqué.
        """
        n = len(self.ues_sous_barre(ues_status))
        if n == 0:
            return True, "les UEs sont au dessus des barres"
        else:
            return False, """<b>%d UE sous la barre</b>""" % n


TYPES_PARCOURS = (
    collections.OrderedDict()
)  # liste des parcours définis (instances de sous-classes de TypeParcours)


def register_parcours(Parcours):
    TYPES_PARCOURS[Parcours.TYPE_PARCOURS] = Parcours


class ParcoursDUT(TypeParcours):
    """DUT selon l'arrêté d'août 2005"""

    TYPE_PARCOURS = 100
    NAME = "DUT"
    NB_SEM = 4
    COMPENSATION_UE = True
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_SPORT]


register_parcours(ParcoursDUT())


class ParcoursDUT4(ParcoursDUT):
    """DUT (en 4 semestres sans compensations)"""

    TYPE_PARCOURS = 110
    NAME = "DUT4"
    COMPENSATION_UE = False


register_parcours(ParcoursDUT4())


class ParcoursDUTMono(TypeParcours):
    """DUT en un an (FC, Années spéciales)"""

    TYPE_PARCOURS = 120
    NAME = "DUT"
    NB_SEM = 1
    COMPENSATION_UE = False
    UNUSED_CODES = set((ADC, ATT, ATB))


register_parcours(ParcoursDUTMono())


class ParcoursDUT2(ParcoursDUT):
    """DUT en deux semestres (par ex.: années spéciales semestrialisées)"""

    TYPE_PARCOURS = 130
    NAME = "DUT2"
    NB_SEM = 2


register_parcours(ParcoursDUT2())


class ParcoursLP(TypeParcours):
    """Licence Pro (en un "semestre")
    (pour anciennes LP. Après 2014, préférer ParcoursLP2014)
    """

    TYPE_PARCOURS = 200
    NAME = "LP"
    NB_SEM = 1
    COMPENSATION_UE = False
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_SPORT, UE_STAGE_LP]
    BARRE_UE_DEFAULT = 0.0  # pas de barre sur les UE "normales"
    BARRE_UE = {UE_STAGE_LP: 10.0}
    # pas de codes ATT en LP
    UNUSED_CODES = set((ADC, ATT, ATB))


register_parcours(ParcoursLP())


class ParcoursLP2sem(ParcoursLP):
    """Licence Pro (en deux "semestres")"""

    TYPE_PARCOURS = 210
    NAME = "LP2sem"
    NB_SEM = 2
    COMPENSATION_UE = True
    UNUSED_CODES = set((ADC,))  # autorise les codes ATT et ATB, mais pas ADC.


register_parcours(ParcoursLP2sem())


class ParcoursLP2semEvry(ParcoursLP):
    """Licence Pro (en deux "semestres", U. Evry)"""

    TYPE_PARCOURS = 220
    NAME = "LP2semEvry"
    NB_SEM = 2
    COMPENSATION_UE = True


register_parcours(ParcoursLP2semEvry())


class ParcoursLP2014(TypeParcours):
    """Licence Pro (en un "semestre"), selon arrêté du 22/01/2014"""

    # Note: texte de référence
    # https://www.legifrance.gouv.fr/affichTexte.do?cidTexte=JORFTEXT000000397481

    # Article 7: Le stage et le projet tutoré constituent chacun une unité d'enseignement.
    # Article 10:
    # La licence professionnelle est décernée aux étudiants qui ont obtenu à la fois une moyenne
    # générale égale ou supérieure à 10 sur 20 à l'ensemble des unités d'enseignement, y compris le
    # projet tutoré et le stage, et une moyenne égale ou supérieure à 10 sur 20 à l'ensemble constitué
    # du projet tutoré et du stage.

    # Actuellement, les points suivants de l'article 7 ("Les unités d'enseignement sont affectées par
    # l'établissement d'un coefficient qui peut varier dans un rapport de 1 à 3. ", etc ne sont _pas_
    # vérifiés par ScoDoc)

    TYPE_PARCOURS = 230
    NAME = "LP2014"
    NB_SEM = 1
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_SPORT, UE_STAGE_LP]
    BARRE_UE_DEFAULT = 0.0  # pas de barre sur les UE "normales"
    # pas de codes ATT en LP
    UNUSED_CODES = set((ADC, ATT, ATB))
    # Specifique aux LP
    BARRE_MOY_UE_STAGE_PROJET = 10.0

    def check_barre_ues(self, ues_status):
        """True si la ou les conditions sur les UE sont valides
        Article 10: "une moyenne égale ou supérieure à 10 sur 20 à l'ensemble constitué
                     du projet tutoré et du stage."
        """
        # Les UE de type "projet ou stage" ayant des notes
        mc_stages_proj = [
            (ue_status["moy"], ue_status["coef_ue"])
            for ue_status in ues_status
            if ue_status["ue"]["type"] == UE_STAGE_LP
            and type(ue_status["moy"]) == float
        ]
        # Moyenne des moyennes:
        sum_coef = sum(x[1] for x in mc_stages_proj)
        if sum_coef > 0.0:
            moy = sum([x[0] * x[1] for x in mc_stages_proj]) / sum_coef
            ok = moy > (self.BARRE_MOY_UE_STAGE_PROJET - NOTES_TOLERANCE)
            if ok:
                return True, "moyenne des UE de stages et projets au dessus de 10"
            else:
                return (
                    False,
                    "<b>moyenne des UE de stages et projets inférieure à 10</b>",
                )
        else:
            return True, ""  # pas de coef, condition ok


register_parcours(ParcoursLP2014())


class ParcoursLP2sem2014(ParcoursLP):
    """Licence Pro (en deux "semestres", selon arrêté du 22/01/2014)"""

    TYPE_PARCOURS = 240
    NAME = "LP2014_2sem"
    NB_SEM = 2


register_parcours(ParcoursLP2sem2014())


# Masters: M2 en deux semestres
class ParcoursM2(TypeParcours):
    """Master 2 (en deux "semestres")"""

    TYPE_PARCOURS = 250
    NAME = "M2sem"
    NB_SEM = 2
    COMPENSATION_UE = True
    UNUSED_CODES = set((ATT, ATB))


register_parcours(ParcoursM2())


class ParcoursM2noncomp(ParcoursM2):
    """Master 2 (en deux "semestres") sans compensation"""

    TYPE_PARCOURS = 251
    NAME = "M2noncomp"
    COMPENSATION_UE = False
    UNUSED_CODES = set((ADC, ATT, ATB))


register_parcours(ParcoursM2noncomp())


class ParcoursMono(TypeParcours):
    """Formation générique en une session"""

    TYPE_PARCOURS = 300
    NAME = "Mono"
    NB_SEM = 1
    COMPENSATION_UE = False
    UNUSED_CODES = set((ADC, ATT, ATB))


register_parcours(ParcoursMono())


class ParcoursLegacy(TypeParcours):
    """DUT (ancien ScoDoc, ne plus utiliser)"""

    TYPE_PARCOURS = 0
    NAME = "DUT"
    NB_SEM = 4
    COMPENSATION_UE = None  # backward compat: defini dans formsemestre
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_SPORT]


register_parcours(ParcoursLegacy())


class ParcoursISCID(TypeParcours):
    """Superclasse pour les parcours de l'ISCID"""

    # SESSION_NAME = "année"
    # SESSION_NAME_A = "de l'"
    # SESSION_ABBRV = 'A' # A1, A2, ...
    COMPENSATION_UE = False
    UNUSED_CODES = set((ADC, ATT, ATB, ATJ))
    UE_IS_MODULE = True  # pas de matieres et modules
    ECTS_ONLY = True  # jury basés sur les ECTS (pas moyenne generales, pas de barres, pas de compensations)
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_ELECTIVE, UE_PROFESSIONNELLE]
    NOTES_BARRE_VALID_MODULE_TH = 10.0
    NOTES_BARRE_VALID_MODULE = (
        NOTES_BARRE_VALID_MODULE_TH - NOTES_TOLERANCE
    )  # barre sur module
    ECTS_BARRE_VALID_YEAR = 60
    ECTS_FONDAMENTAUX_PER_YEAR = 42  # mini pour valider l'annee
    ECTS_PROF_DIPL = 0  # crédits professionnels requis pour obtenir le diplôme


class ParcoursBachelorISCID6(ParcoursISCID):
    """ISCID: Bachelor en 3 ans (6 sem.)"""

    NAME = "ParcoursBachelorISCID6"
    TYPE_PARCOURS = 1001
    NAME = ""
    NB_SEM = 6
    ECTS_PROF_DIPL = 8  # crédits professionnels requis pour obtenir le diplôme


register_parcours(ParcoursBachelorISCID6())


class ParcoursMasterISCID4(ParcoursISCID):
    "ISCID: Master en 2 ans (4 sem.)"
    TYPE_PARCOURS = 1002
    NAME = "ParcoursMasterISCID4"
    NB_SEM = 4
    ECTS_PROF_DIPL = 15  # crédits professionnels requis pour obtenir le diplôme


register_parcours(ParcoursMasterISCID4())


class ParcoursILEPS(TypeParcours):
    """Superclasse pour les parcours de l'ILEPS"""

    # SESSION_NAME = "année"
    # SESSION_NAME_A = "de l'"
    # SESSION_ABBRV = 'A' # A1, A2, ...
    COMPENSATION_UE = False
    UNUSED_CODES = set((ADC, ATT, ATB, ATJ))
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_OPTIONNELLE]
    # Barre moy gen. pour validation semestre:
    BARRE_MOY = 10.0
    # Barre pour UE ILEPS: 8/20 pour UE standards ("fondamentales")
    #    et pas de barre (-1.) pour UE élective.
    BARRE_UE = {UE_STANDARD: 8.0, UE_OPTIONNELLE: 0.0}
    BARRE_UE_DEFAULT = 0.0  # pas de barre sur les autres UE


class ParcoursLicenceILEPS6(ParcoursILEPS):
    """ILEPS: Licence 6 semestres"""

    TYPE_PARCOURS = 1010
    NAME = "LicenceILEPS6"
    NB_SEM = 6


register_parcours(ParcoursLicenceILEPS6())


class ParcoursUCAC(TypeParcours):
    """Règles de validation UCAC"""

    SESSION_NAME = "année"
    SESSION_NAME_A = "de l'"
    COMPENSATION_UE = False
    BARRE_MOY = 12.0
    NOTES_BARRE_VALID_UE_TH = 12.0  # seuil pour valider UE
    NOTES_BARRE_VALID_UE = NOTES_BARRE_VALID_UE_TH - NOTES_TOLERANCE  # barre sur UE
    BARRE_UE_DEFAULT = (
        NOTES_BARRE_VALID_UE_TH  # il faut valider tt les UE pour valider l'année
    )


class ParcoursLicenceUCAC3(ParcoursUCAC):
    """UCAC: Licence en 3 sessions d'un an"""

    TYPE_PARCOURS = 501
    NAME = "Licence UCAC en 3 sessions d'un an"
    NB_SEM = 3


register_parcours(ParcoursLicenceUCAC3())


class ParcoursMasterUCAC2(ParcoursUCAC):
    """UCAC: Master en 2 sessions d'un an"""

    TYPE_PARCOURS = 502
    NAME = "Master UCAC en 2 sessions d'un an"
    NB_SEM = 2


register_parcours(ParcoursMasterUCAC2())


class ParcoursMonoUCAC(ParcoursUCAC):
    """UCAC: Formation en 1 session de durée variable"""

    TYPE_PARCOURS = 503
    NAME = "Formation UCAC en 1 session de durée variable"
    NB_SEM = 1
    UNUSED_CODES = set((ADC, ATT, ATB))


register_parcours(ParcoursMonoUCAC())


class Parcours6Sem(TypeParcours):
    """Parcours générique en 6 semestres"""

    TYPE_PARCOURS = 600
    NAME = "Formation en 6 semestres"
    NB_SEM = 6
    COMPENSATION_UE = True


register_parcours(Parcours6Sem())

# # En cours d'implémentation:
# class ParcoursLicenceLMD(TypeParcours):
#     """Licence standard en 6 semestres dans le LMD"""
#     TYPE_PARCOURS = 401
#     NAME = "Licence LMD"
#     NB_SEM = 6
#     COMPENSATION_UE = True

# register_parcours(ParcoursLicenceLMD())


class ParcoursMasterLMD(TypeParcours):
    """Master générique en 4 semestres dans le LMD"""

    TYPE_PARCOURS = 402
    NAME = "Master LMD"
    NB_SEM = 4
    COMPENSATION_UE = True  # variabale inutilisée
    UNUSED_CODES = set((ADC, ATT, ATB))


register_parcours(ParcoursMasterLMD())


class ParcoursMasterIG(ParcoursMasterLMD):
    """Master de l'Institut Galilée (U. Paris 13) en 4 semestres (LMD)"""

    TYPE_PARCOURS = 403
    NAME = "Master IG P13"
    BARRE_MOY = 10.0
    NOTES_BARRE_VALID_UE_TH = 10.0  # seuil pour valider UE
    NOTES_BARRE_VALID_UE = NOTES_BARRE_VALID_UE_TH - NOTES_TOLERANCE  # barre sur UE
    BARRE_UE_DEFAULT = 7.0  # Les UE normales avec moins de 7/20 sont éliminatoires
    # Specifique à l'UE de stage
    BARRE_MOY_UE_STAGE = 10.0
    ALLOWED_UE_TYPES = [UE_STANDARD, UE_SPORT, UE_STAGE_10]

    def check_barre_ues(self, ues_status):  # inspire de la fonction de ParcoursLP2014
        """True si la ou les conditions sur les UE sont valides
        moyenne d'UE > 7, ou > 10 si UE de stage
        """
        # Il y a-t-il une UE standard sous la barre ?
        ue_sb = [
            ue_status
            for ue_status in ues_status
            if ue_status["ue"]["type"] == UE_STANDARD
            and ue_status["coef_ue"] > 0
            and type(ue_status["moy"]) == float
            and ue_status["moy"] < self.get_barre_ue(ue_status["ue"]["type"])
        ]
        if len(ue_sb):
            return (
                False,
                "<b>%d UE sous la barre (%s/20)</b>"
                % (len(ue_sb), self.BARRE_UE_DEFAULT),
            )
        # Les UE de type "stage" ayant des notes
        mc_stages = [
            (ue_status["moy"], ue_status["coef_ue"])
            for ue_status in ues_status
            if ue_status["ue"]["type"] == UE_STAGE_10
            and type(ue_status["moy"]) == float
        ]
        # Moyenne des moyennes:
        sum_coef = sum(x[1] for x in mc_stages)
        if sum_coef > 0.0:
            moy = sum([x[0] * x[1] for x in mc_stages]) / sum_coef
            ok = moy > (self.BARRE_MOY_UE_STAGE - NOTES_TOLERANCE)
            if ok:
                return True, "moyenne des UE de stages au dessus de 10"
            else:
                return False, "<b>moyenne des UE de stages inférieure à 10</b>"
        else:
            return True, ""  # pas de coef, condition ok


register_parcours(ParcoursMasterIG())


# Ajouter ici vos parcours, le TYPE_PARCOURS devant être unique au monde

#Parcours ENSEM
class ParcoursIng(TypeParcours):
    """Parcours Ingénieur"""

    TYPE_PARCOURS = 700
    NAME = "Formation Ingénieur"
    NB_SEM = 6
    COMPENSATION_UE = True

register_parcours(ParcoursIng())


class ParcoursAlternant(TypeParcours):
    """Parcours Ingénieur en Alternance"""

    TYPE_PARCOURS = 701
    NAME = "Formation Ingénieur en alternance"
    NB_SEM = 6
    COMPENSATION_UE = True

register_parcours(ParcoursAlternant())

# ...


# -------------------------
_tp = list(TYPES_PARCOURS.items())
_tp.sort(key=lambda x: x[1].__doc__)  # sort by intitulé
FORMATION_PARCOURS_DESCRS = [p[1].__doc__ for p in _tp]  # intitulés (eg pour menu)
FORMATION_PARCOURS_TYPES = [p[0] for p in _tp]  # codes numeriques (TYPE_PARCOURS)


def get_parcours_from_code(code_parcours):
    parcours = TYPES_PARCOURS.get(code_parcours)
    if parcours is None:
        log(f"Warning: invalid code_parcours: {code_parcours}")
        # default to legacy
        parcours = TYPES_PARCOURS.get(0)
    return parcours
