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

"""Exportation des résultats des étudiants vers Apogée.

Ce code a été au départ inspiré par les travaux de Damien Mascré, scodoc2apogee (en Java).

A utiliser en fin de semestre, après les jury.

On communique avec Apogée via des fichiers CSV.

Le fichier CSV, champs séparés par des tabulations, a la structure suivante:

 <pre>
 XX-APO_TITRES-XX
 apoC_annee	2007/2008
 apoC_cod_dip	VDTCJ
 apoC_Cod_Exp	1
 apoC_cod_vdi	111
 apoC_Fichier_Exp	VDTCJ_V1CJ.txt
 apoC_lib_dip	DUT CJ
 apoC_Titre1	Export Apogée du 13/06/2008 à 14:29
 apoC_Titre2

 XX-APO_COLONNES-XX
 apoL_a01_code	Type Objet	Code	Version	Année	Session	Admission/Admissibilité	Type Rés.			Etudiant	Numéro
 apoL_a02_nom										1	Nom
 apoL_a03_prenom										1	Prénom
 apoL_a04_naissance									Session	Admissibilité	Naissance
 APO_COL_VAL_DEB
 apoL_c0001	VET	V1CJ	111	2007	0	1	N	V1CJ - DUT CJ an1	0	1	Note
 apoL_c0002	VET	V1CJ	111	2007	0	1	B		0	1	Barème
 apoL_c0003	VET	V1CJ	111	2007	0	1	R		0	1	Résultat
 APO_COL_VAL_FIN
 apoL_c0030	APO_COL_VAL_FIN

 XX-APO_VALEURS-XX
 apoL_a01_code	apoL_a02_nom	apoL_a03_prenom	apoL_a04_naissance	apoL_c0001	apoL_c0002	apoL_c0003	apoL_c0004	apoL_c0005	apoL_c0006	apoL_c0007	apoL_c0008	apoL_c0009	apoL_c0010	apoL_c0011	apoL_c0012	apoL_c0013	apoL_c0014	apoL_c0015	apoL_c0016	apoL_c0017	apoL_c0018	apoL_c0019	apoL_c0020	apoL_c0021	apoL_c0022	apoL_c0023	apoL_c0024	apoL_c0025	apoL_c0026	apoL_c0027	apoL_c0028	apoL_c0029
 10601232	AARIF	MALIKA	 22/09/1986	18	20	ADM	18	20	ADM	18	20	ADM	18	20	ADM	18	20	ADM	18	20	18	20	ADM	18	20	ADM	18	20	ADM	18	20	ADM
 </pre>

 
 On récupère nos éléments pédagogiques dans la section XX-APO-COLONNES-XX et
 notre liste d'étudiants dans la section XX-APO_VALEURS-XX. Les champs de la
 section XX-APO_VALEURS-XX sont décrits par les lignes successives de la
 section XX-APO_COLONNES-XX.

 Le fichier CSV correspond à une étape, qui est récupérée sur la ligne
 <pre>
 apoL_c0001	VET	V1CJ ...
 </pre>


XXX A vérifier:
 AJAC car 1 sem. validé et pas de NAR 
 
"""

import collections
import datetime
from functools import reduce
import io
import os
import pprint
import re
import time
from zipfile import ZipFile

from flask import send_file

# Pour la détection auto de l'encodage des fichiers Apogée:
from chardet import detect as chardet_detect

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.sco_exceptions import ScoValueError, FormatError
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_vdi import ApoEtapeVDI
from app.scodoc.sco_codes_parcours import code_semestre_validant
from app.scodoc.sco_codes_parcours import (
    ADC,
    ADJ,
    ADM,
    AJ,
    ATB,
    ATJ,
    ATT,
    CMP,
    DEF,
    NAR,
    RAT,
)
from app.scodoc import sco_cache
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_etud

APO_PORTAL_ENCODING = (
    "utf8"  # encodage du fichier CSV Apogée (était 'ISO-8859-1' avant jul. 2016)
)
APO_INPUT_ENCODING = "ISO-8859-1"  #
APO_OUTPUT_ENCODING = APO_INPUT_ENCODING  # encodage des fichiers Apogee générés
APO_DECIMAL_SEP = ","  # separateur décimal: virgule
APO_SEP = "\t"
APO_NEWLINE = "\r\n"


def code_scodoc_to_apo(code):
    """Conversion code jury ScoDoc en code Apogée"""
    return {
        ATT: "AJAC",
        ATB: "AJAC",
        ATJ: "AJAC",
        ADM: "ADM",
        ADJ: "ADM",
        ADC: "ADMC",
        AJ: "AJ",
        CMP: "COMP",
        "DEM": "NAR",
        DEF: "NAR",
        NAR: "NAR",
        RAT: "ATT",
    }.get(code, "DEF")


def _apo_fmt_note(note):
    "Formatte une note pour Apogée (séparateur décimal: ',')"
    if not note and isinstance(note, float):
        return ""
    try:
        val = float(note)
    except ValueError:
        return ""
    return ("%3.2f" % val).replace(".", APO_DECIMAL_SEP)


def guess_data_encoding(text, threshold=0.6):
    """Guess string encoding, using chardet heuristics.
    Returns encoding, or None if detection failed (confidence below threshold)
    """
    r = chardet_detect(text)
    if r["confidence"] < threshold:
        return None
    else:
        return r["encoding"]


def fix_data_encoding(
    text, default_source_encoding=APO_INPUT_ENCODING, dest_encoding=APO_INPUT_ENCODING
):
    """Try to ensure that text is using dest_encoding
    returns converted text, and a message describing the conversion.
    """
    message = ""
    detected_encoding = guess_data_encoding(text)
    if not detected_encoding:
        if default_source_encoding != dest_encoding:
            message = "converting from %s to %s" % (
                default_source_encoding,
                dest_encoding,
            )
            text = text.decode(default_source_encoding).encode(
                dest_encoding
            )  # XXX #py3 #sco8 à tester
    else:
        if detected_encoding != dest_encoding:
            message = "converting from detected %s to %s" % (
                detected_encoding,
                dest_encoding,
            )
            text = text.decode(detected_encoding).encode(dest_encoding)  # XXX
    return text, message


class StringIOFileLineWrapper(object):
    def __init__(self, data):
        self.f = io.StringIO(data)
        self.lineno = 0

    def close(self):
        return self.f.close()

    def readline(self):
        self.lineno += 1
        return self.f.readline()


class DictCol(dict):
    "A dict, where we can add attributes"
    pass


class ApoElt(object):
    """Definition d'un Element Apogee
    sur plusieurs colonnes du fichier CSV
    """

    def __init__(self, cols):
        assert len(cols) > 0
        assert len(set([c["Code"] for c in cols])) == 1  # colonnes de meme code
        assert len(set([c["Type Objet"] for c in cols])) == 1  # colonnes de meme type
        self.cols = cols
        self.code = cols[0]["Code"]
        self.version = cols[0]["Version"]
        self.type_objet = cols[0]["Type Objet"]

    def append(self, col):
        assert col["Code"] == self.code
        if col["Type Objet"] != self.type_objet:
            log(
                "Warning: ApoElt: duplicate id %s (%s and %s)"
                % (self.code, self.type_objet, col["Type Objet"])
            )
            self.type_objet = col["Type Objet"]
        self.cols.append(col)

    def __repr__(self):
        return "ApoElt(code='%s', cols=%s)" % (self.code, pprint.pformat(self.cols))


class EtuCol(object):
    """Valeurs colonnes d'un element pour un etudiant"""

    def __init__(self, nip, apo_elt, init_vals):
        pass  # XXX


ETUD_OK = "ok"
ETUD_ORPHELIN = "orphelin"
ETUD_NON_INSCRIT = "non_inscrit"

VOID_APO_RES = dict(N="", B="", J="", R="", M="")


class ApoEtud(dict):
    """Etudiant Apogee:"""

    def __init__(
        self,
        nip="",
        nom="",
        prenom="",
        naissance="",
        cols={},
        export_res_etape=True,
        export_res_sem=True,
        export_res_ues=True,
        export_res_modules=True,
        export_res_sdj=True,
        export_res_rat=True,
    ):
        self["nip"] = nip
        self["nom"] = nom
        self["prenom"] = prenom
        self["naissance"] = naissance
        self.cols = cols  # { col_id : value }  colid = 'apoL_c0001'
        self.new_cols = {}  # { col_id : value to record in csv }
        self.etud = None  # etud ScoDoc
        self.etat = None  # ETUD_OK, ...
        self.is_NAR = False  # set to True si NARé dans un semestre
        self.log = []
        self.has_logged_no_decision = False
        self.export_res_etape = export_res_etape  # VET, ...
        self.export_res_sem = export_res_sem  # elt_sem_apo
        self.export_res_ues = export_res_ues
        self.export_res_modules = export_res_modules
        self.export_res_sdj = export_res_sdj  # export meme si pas de decision de jury
        self.export_res_rat = export_res_rat

    def __repr__(self):
        return "ApoEtud( nom='%s', nip='%s' )" % (self["nom"], self["nip"])

    def lookup_scodoc(self, etape_formsemestre_ids):
        """Cherche l'étudiant ScoDoc associé à cet étudiant Apogée.
        S'il n'est pas trouvé (état "orphelin", dans Apo mais pas chez nous),
        met .etud à None.
        Sinon, cherche le semestre, et met l'état à ETUD_OK ou ETUD_NON_INSCRIT.
        """
        etuds = sco_etud.get_etud_info(code_nip=self["nip"], filled=True)
        if not etuds:
            # pas dans ScoDoc
            self.etud = None
            self.log.append("non inscrit dans ScoDoc")
            self.etat = ETUD_ORPHELIN
        else:
            self.etud = etuds[0]
            # cherche le semestre ScoDoc correspondant à l'un de ceux de l'etape:
            formsemestre_ids = {s["formsemestre_id"] for s in self.etud["sems"]}
            self.in_formsemestre_ids = formsemestre_ids.intersection(
                etape_formsemestre_ids
            )
            if not self.in_formsemestre_ids:
                self.log.append(
                    "connu dans ScoDoc, mais pas inscrit dans un semestre de cette étape"
                )
                self.etat = ETUD_NON_INSCRIT
            else:
                self.etat = ETUD_OK

    def associate_sco(self, apo_data):
        """Recherche les valeurs des éléments Apogée pour cet étudiant
        Set .new_cols
        """
        self.col_elts = {}  # {'V1RT': {'R': 'ADM', 'J': '', 'B': 20, 'N': '12.14'}}
        if self.etat is None:
            self.lookup_scodoc(apo_data.etape_formsemestre_ids)
        if self.etat != ETUD_OK:
            self.new_cols = (
                self.cols
            )  # etudiant inconnu, recopie les valeurs existantes dans Apo
        else:
            sco_elts = {}  # valeurs trouvées dans ScoDoc   code : { N, B, J, R }
            for col_id in apo_data.col_ids[4:]:
                code = apo_data.cols[col_id]["Code"]  # 'V1RT'
                el = sco_elts.get(
                    code, None
                )  # {'R': ADM, 'J': '', 'B': 20, 'N': '12.14'}
                if el is None:  # pas déjà trouvé
                    cur_sem, autre_sem = self.etud_semestres_de_etape(apo_data)
                    for sem in apo_data.sems_etape:
                        el = self.search_elt_in_sem(code, sem, cur_sem, autre_sem)
                        if el != None:
                            sco_elts[code] = el
                            break
                self.col_elts[code] = el
                if el is None:
                    self.new_cols[col_id] = self.cols[col_id]
                else:
                    try:
                        self.new_cols[col_id] = sco_elts[code][
                            apo_data.cols[col_id]["Type Rés."]
                        ]
                    except KeyError:
                        log(
                            "associate_sco: missing key, etud=%s\ncode='%s'\netape='%s'"
                            % (self, code, apo_data.etape_apogee)
                        )
                        raise ScoValueError(
                            """L'élément %s n'a pas de résultat: peut-être une erreur dans les codes sur le programme pédagogique (vérifier qu'il est bien associé à une UE ou semestre)?"""
                            % code
                        )
            # recopie les 4 premieres colonnes (nom, ..., naissance):
            for col_id in apo_data.col_ids[:4]:
                self.new_cols[col_id] = self.cols[col_id]

    # def unassociated_codes(self, apo_data):
    #     "list of apo elements for this student without a value in ScoDoc"
    #     codes = set([apo_data.cols[col_id].code for col_id in apo_data.col_ids])
    #     return codes - set(sco_elts)

    def search_elt_in_sem(self, code, sem, cur_sem, autre_sem):
        """
        VET code jury etape
        ELP élément pédagogique: UE, module
        Autres éléments: résultats du semestre ou de l'année scolaire:
        => VRTW1: code additionnel au semestre ("code élement semestre", elt_sem_apo)
        => VRT1A: le même que le VET: ("code élement annuel", elt_annee_apo)
        Attention, si le semestre couvre plusieurs étapes, indiquer les codes des éléments,
        séparés par des virgules.

        Args:
           code (str): code apo de l'element cherché
           sem (dict): semestre dans lequel on cherche l'élément
           cur_sem (dict): semestre "courant" pour résultats annuels (VET)
           autre_sem (dict): autre semestre utilisé pour calculé les résultats annuels (VET)

        Returns:
           dict: with N, B, J, R keys, ou None si elt non trouvé
        """
        etudid = self.etud["etudid"]
        nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
        if etudid not in nt.identdict:
            return None  # etudiant non inscrit dans ce semestre

        decision = nt.get_etud_decision_sem(etudid)
        if not self.export_res_sdj and not decision:
            # pas de decision de jury, on n'enregistre rien
            # (meme si démissionnaire)
            if not self.has_logged_no_decision:
                self.log.append("Pas de decision")
                self.has_logged_no_decision = True
            return VOID_APO_RES

        if decision and decision["code"] == NAR:
            self.is_NAR = True

        # Element etape (annuel ou non):
        if sco_formsemestre.sem_has_etape(sem, code) or (
            code in sem["elt_annee_apo"].split(",")
        ):
            export_res_etape = self.export_res_etape
            if (not export_res_etape) and cur_sem:
                # exporte toujours le résultat de l'étape si l'étudiant est diplômé
                Se = sco_parcours_dut.SituationEtudParcours(
                    self.etud, cur_sem["formsemestre_id"]
                )
                export_res_etape = Se.all_other_validated()

            if export_res_etape:
                return self.comp_elt_annuel(etudid, cur_sem, autre_sem)
            else:
                return VOID_APO_RES

        # Element semestre:
        if code in sem["elt_sem_apo"].split(","):
            if self.export_res_sem:
                return self.comp_elt_semestre(nt, decision, etudid)
            else:
                return VOID_APO_RES

        # Elements UE
        decisions_ue = nt.get_etud_decision_ues(etudid)
        for ue in nt.get_ues():
            if code in ue["code_apogee"].split(","):
                if self.export_res_ues:
                    if decisions_ue and ue["ue_id"] in decisions_ue:
                        ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
                        code_decision_ue = decisions_ue[ue["ue_id"]]["code"]
                        return dict(
                            N=_apo_fmt_note(ue_status["moy"]),
                            B=20,
                            J="",
                            R=code_scodoc_to_apo(code_decision_ue),
                            M="",
                        )
                    else:
                        return VOID_APO_RES
                else:
                    return VOID_APO_RES

        # Elements Modules
        modimpls = nt.get_modimpls()
        module_code_found = False
        for modimpl in modimpls:
            if code in modimpl["module"]["code_apogee"].split(","):
                n = nt.get_etud_mod_moy(modimpl["moduleimpl_id"], etudid)
                if n != "NI" and self.export_res_modules:
                    return dict(N=_apo_fmt_note(n), B=20, J="", R="")
                else:
                    module_code_found = True
        if module_code_found:
            return VOID_APO_RES
        #
        return None  # element Apogee non trouvé dans ce semestre

    def comp_elt_semestre(self, nt, decision, etudid):
        """Calcul résultat apo semestre"""
        # resultat du semestre
        decision_apo = code_scodoc_to_apo(decision["code"])
        note = nt.get_etud_moy_gen(etudid)
        if (
            decision_apo == "DEF"
            or decision["code"] == "DEM"
            or decision["code"] == DEF
        ):
            note_str = "0,01"  # note non nulle pour les démissionnaires
        else:
            note_str = _apo_fmt_note(note)
        return dict(N=note_str, B=20, J="", R=decision_apo, M="")

    def comp_elt_annuel(self, etudid, cur_sem, autre_sem):
        """Calcul resultat annuel (VET) à partir du semestre courant
        et de l'autre (le suivant ou le précédent complétant l'année scolaire)
        """
        # Code annuel:
        #  - Note: moyenne des moyennes générales des deux semestres (pas vraiment de sens, mais faute de mieux)
        #    on pourrait aussi bien prendre seulement la note du dernier semestre (S2 ou S4). Paramétrable ?
        #  - Résultat jury:
        #      si l'autre est validé, code du semestre courant (ex: S1 (ADM), S2 (AJ) => année AJ)
        #      si l'autre n'est pas validé ou est DEF ou DEM, code de l'autre
        #
        #    XXX cette règle est discutable, à valider

        # print 'comp_elt_annuel cur_sem=%s autre_sem=%s' % (cur_sem['formsemestre_id'], autre_sem['formsemestre_id'])
        if not cur_sem:
            # l'étudiant n'a pas de semestre courant ?!
            log("comp_elt_annuel: etudid %s has no cur_sem" % etudid)
            return VOID_APO_RES
        cur_nt = sco_cache.NotesTableCache.get(cur_sem["formsemestre_id"])
        cur_decision = cur_nt.get_etud_decision_sem(etudid)
        if not cur_decision:
            # pas de decision => pas de résultat annuel
            return VOID_APO_RES

        if (cur_decision["code"] == RAT) and not self.export_res_rat:
            # ne touche pas aux RATs
            return VOID_APO_RES

        if not autre_sem:
            # formations monosemestre, ou code VET semestriel,
            # ou jury intermediaire et etudiant non redoublant...
            return self.comp_elt_semestre(cur_nt, cur_decision, etudid)

        decision_apo = code_scodoc_to_apo(cur_decision["code"])

        autre_nt = sco_cache.NotesTableCache.get(autre_sem["formsemestre_id"])
        autre_decision = autre_nt.get_etud_decision_sem(etudid)
        if not autre_decision:
            # pas de decision dans l'autre => pas de résultat annuel
            return VOID_APO_RES
        autre_decision_apo = code_scodoc_to_apo(autre_decision["code"])
        if (
            autre_decision_apo == "DEF"
            or autre_decision["code"] == "DEM"
            or autre_decision["code"] == DEF
        ) or (
            decision_apo == "DEF"
            or cur_decision["code"] == "DEM"
            or cur_decision["code"] == DEF
        ):
            note_str = "0,01"  # note non nulle pour les démissionnaires
        else:
            note = cur_nt.get_etud_moy_gen(etudid)
            autre_note = autre_nt.get_etud_moy_gen(etudid)
            # print 'note=%s autre_note=%s' % (note, autre_note)
            try:
                moy_annuelle = (note + autre_note) / 2
            except TypeError:
                moy_annuelle = ""
            note_str = _apo_fmt_note(moy_annuelle)

        if code_semestre_validant(autre_decision["code"]):
            decision_apo_annuelle = decision_apo
        else:
            decision_apo_annuelle = autre_decision_apo

        return dict(N=note_str, B=20, J="", R=decision_apo_annuelle, M="")

    def etud_semestres_de_etape(self, apo_data):
        """
        Lorsqu'on a une formation semestrialisée mais avec un code étape annuel,
        il faut considérer les deux semestres ((S1,S2) ou (S3,S4)) pour calculer
        le code annuel (VET ou VRT1A (voir elt_annee_apo)).

        Pour les jurys intermediaires (janvier, S1 ou S3):  (S2 ou S4) de la même étape lors d'une année précédente ?

        Renvoie le semestre "courant" et l'autre semestre, ou None s'il n'y en a pas.
        """
        # Cherche le semestre "courant":
        cur_sems = [
            sem
            for sem in self.etud["sems"]
            if (
                (sem["semestre_id"] == apo_data.cur_semestre_id)
                and (apo_data.etape in sem["etapes"])
                and (
                    sco_formsemestre.sem_in_annee_scolaire(sem, apo_data.annee_scolaire)
                )
            )
        ]
        if not cur_sems:
            cur_sem = None
        else:
            # prend le plus recent avec decision
            cur_sem = None
            for sem in cur_sems:
                nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
                decision = nt.get_etud_decision_sem(self.etud["etudid"])
                if decision:
                    cur_sem = sem
                    break
            if cur_sem is None:
                cur_sem = cur_sems[0]  # aucun avec decison, prend le plus recent

        if apo_data.cur_semestre_id <= 0:
            return (
                cur_sem,
                None,
            )  # "autre_sem" non pertinent pour sessions sans semestres

        if apo_data.jury_intermediaire:  # jury de janvier
            # Le semestre suivant: exemple 2 si on est en jury de S1
            autre_semestre_id = apo_data.cur_semestre_id + 1
        else:
            # Le précédent (S1 si on est en S2)
            autre_semestre_id = apo_data.cur_semestre_id - 1

        # L'autre semestre DOIT être antérieur au courant indiqué par apo_data
        if apo_data.periode is not None:
            if apo_data.periode == 1:
                courant_annee_debut = apo_data.annee_scolaire
                courant_mois_debut = 9  # periode = 1 (sept-jan)
            elif apo_data.periode == 2:
                courant_annee_debut = apo_data.annee_scolaire + 1
                courant_mois_debut = 1  # ou 2 (fev-jul)
            else:
                raise ValueError("invalid pediode value !")  # bug ?
            courant_date_debut = "%d-%02d-01" % (
                courant_annee_debut,
                courant_mois_debut,
            )
        else:
            courant_date_debut = "9999-99-99"

        # etud['sems'] est la liste des semestres de l'étudiant, triés par date,
        # le plus récemment effectué en tête.
        # Cherche les semestres (antérieurs) de l'indice autre de la même étape apogée
        # s'il y en a plusieurs, choisit le plus récent ayant une décision

        autres_sems = []
        for sem in self.etud["sems"]:
            if (
                sem["semestre_id"] == autre_semestre_id
                and apo_data.etape_apogee in sem["etapes"]
            ):
                if (
                    sem["date_debut_iso"] < courant_date_debut
                ):  # on demande juste qu'il ait démarré avant
                    autres_sems.append(sem)
        if not autres_sems:
            autre_sem = None
        elif len(autres_sems) == 1:
            autre_sem = autres_sems[0]
        else:
            autre_sem = None
            for sem in autres_sems:
                nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
                decision = nt.get_etud_decision_sem(self.etud["etudid"])
                if decision:
                    autre_sem = sem
                    break
            if autre_sem is None:
                autre_sem = autres_sems[0]  # aucun avec decision, prend le plus recent

        return cur_sem, autre_sem


class ApoData(object):
    def __init__(
        self,
        data,
        periode=None,
        export_res_etape=True,
        export_res_sem=True,
        export_res_ues=True,
        export_res_modules=True,
        export_res_sdj=True,
        export_res_rat=True,
        orig_filename=None,
    ):
        """Lecture du fichier CSV Apogée
        Regroupe les élements importants d'un fichier CSV Apogée
        periode = 1 (sept-jan) ou 2 (fev-jul), mais cette info n'est pas
         (toujours) présente dans les CSV Apogée et doit être indiquée par l'utilisateur
        Laisser periode à None si etape en 1 semestre (LP, décalés, ...)
        """
        self.export_res_etape = export_res_etape  # VET, ...
        self.export_res_sem = export_res_sem  # elt_sem_apo
        self.export_res_ues = export_res_ues
        self.export_res_modules = export_res_modules
        self.export_res_sdj = export_res_sdj
        self.export_res_rat = export_res_rat
        self.orig_filename = orig_filename
        self.periode = periode  #
        try:
            self.read_csv(data)
        except FormatError as e:
            # essaie de retrouver le nom du fichier pour enrichir le message d'erreur
            filename = ""
            if self.orig_filename is None:
                if hasattr(self, "titles"):
                    filename = self.titles.get("apoC_Fichier_Exp", filename)
            else:
                filename = self.orig_filename
            raise FormatError(
                "<h3>Erreur lecture du fichier Apogée <tt>%s</tt></h3><p>" % filename
                + e.args[0]
                + "</p>"
            )
        self.etape_apogee = self.get_etape_apogee()  #  'V1RT'
        self.vdi_apogee = self.get_vdi_apogee()  # '111'
        self.etape = ApoEtapeVDI(etape=self.etape_apogee, vdi=self.vdi_apogee)
        self.cod_dip_apogee = self.get_cod_dip_apogee()
        self.annee_scolaire = self.get_annee_scolaire()
        self.jury_intermediaire = (
            False  # True si jury à mi-étape, eg jury de S1 dans l'étape (S1, S2)
        )

        log(
            "ApoData( periode=%s, annee_scolaire=%s )"
            % (self.periode, self.annee_scolaire)
        )

    def set_periode(self, periode):  # currently unused
        self.periode = periode

    def setup(self):
        """Recherche semestres ScoDoc concernés"""
        self.sems_etape = comp_apo_sems(self.etape_apogee, self.annee_scolaire)
        self.etape_formsemestre_ids = {s["formsemestre_id"] for s in self.sems_etape}
        if self.periode != None:
            self.sems_periode = [
                s
                for s in self.sems_etape
                if (s["periode"] == self.periode) or s["semestre_id"] < 0
            ]
            if not self.sems_periode:
                log("** Warning: ApoData.setup: sems_periode is empty")
                log(
                    "**  (periode=%s, sems_etape [periode]=%s)"
                    % (self.periode, [s["periode"] for s in self.sems_etape])
                )
                self.sems_periode = None
                self.cur_semestre_id = -1  # ?
            else:
                self.cur_semestre_id = self.sems_periode[0]["semestre_id"]
                # Les semestres de la période ont le même indice, n'est-ce pas ?
                if not all(
                    self.cur_semestre_id == s["semestre_id"] for s in self.sems_periode
                ):
                    # debugging information
                    import pprint

                    log("*** ApoData.set() error !")
                    log(
                        "ApoData( periode=%s, annee_scolaire=%s, cur_semestre_id=%s )"
                        % (self.periode, self.annee_scolaire, self.cur_semestre_id)
                    )
                    log("%d semestres dans la periode: " % len(self.sems_periode))
                    for s in self.sems_periode:
                        log(pprint.pformat(s))

                    raise ValueError(
                        "incohérence détectée (contacter les développeurs)"
                    )
            # Cette condition sera inadaptée si semestres décalés
            # (mais ils n'ont pas d'étape annuelle, espérons!)
            if self.cur_semestre_id >= 0:  # non pertinent pour sessions sans semestres
                self.jury_intermediaire = (self.cur_semestre_id % 2) != 0
        else:
            self.sems_periode = None

    def read_csv(self, data: str):
        if not data:
            raise FormatError("Fichier Apogée vide !")

        f = StringIOFileLineWrapper(data)  # pour traiter comme un fichier
        # check that we are at the begining of Apogee CSV
        line = f.readline().strip()
        if line != "XX-APO_TITRES-XX":
            raise FormatError("format incorrect: pas de XX-APO_TITRES-XX")

        # 1-- En-tête: du début jusqu'à la balise XX-APO_VALEURS-XX
        idx = data.index("XX-APO_VALEURS-XX")
        self.header = data[:idx]

        # 2-- Titres:
        #   on va y chercher apoC_Fichier_Exp qui donnera le nom du fichier
        #   ainsi que l'année scolaire et le code diplôme.
        self.titles = _apo_read_TITRES(f)

        # 3-- La section XX-APO_TYP_RES-XX est ignorée:
        line = f.readline().strip()
        if line != "XX-APO_TYP_RES-XX":
            raise FormatError("format incorrect: pas de XX-APO_TYP_RES-XX")
        _apo_skip_section(f)

        # 4-- Définition de colonnes: (on y trouve aussi l'étape)
        line = f.readline().strip()
        if line != "XX-APO_COLONNES-XX":
            raise FormatError("format incorrect: pas de XX-APO_COLONNES-XX")
        self.cols = _apo_read_cols(f)
        self.apo_elts = self._group_elt_cols(self.cols)

        # 5-- Section XX-APO_VALEURS-XX
        # Lecture des étudiants et de leurs résultats
        while True:  # skip
            line = f.readline()
            if not line:
                raise FormatError("format incorrect: pas de XX-APO_VALEURS-XX")
            if line.strip() == "XX-APO_VALEURS-XX":
                break
        self.column_titles = f.readline()
        self.col_ids = self.column_titles.strip().split()
        self.etuds = self.apo_read_etuds(f)
        self.etud_by_nip = {e["nip"]: e for e in self.etuds}

    def get_etud_by_nip(self, nip):
        "returns ApoEtud with a given NIP code"
        return self.etud_by_nip[nip]

    def _group_elt_cols(self, cols):
        """Return ordered dict of ApoElt from list of ApoCols.
        Clé: id apogée, eg 'V1RT', 'V1GE2201', ...
        Valeur: ApoElt, avec les attributs code, type_objet

        Si les id Apogée ne sont pas uniques (ce n'est pas garanti), garde le premier
        """
        elts = collections.OrderedDict()
        for col_id in sorted(list(cols.keys()), reverse=True):
            col = cols[col_id]
            if col["Code"] in elts:
                elts[col["Code"]].append(col)
            else:
                elts[col["Code"]] = ApoElt([col])
        return elts  # { code apo : ApoElt }

    def apo_read_etuds(self, f):
        """Lecture des etudiants (et resultats) du fichier CSV Apogée
        -> liste de dicts
        """
        L = []
        while True:
            line = f.readline()
            if not line:
                break
            if not line.strip():
                continue  # silently ignore blank lines
            line = line.strip(APO_NEWLINE)
            fs = line.split(APO_SEP)
            cols = {}  # { col_id : value }
            for i in range(len(fs)):
                cols[self.col_ids[i]] = fs[i]
            L.append(
                ApoEtud(
                    nip=fs[0],  # id etudiant
                    nom=fs[1],
                    prenom=fs[2],
                    naissance=fs[3],
                    cols=cols,
                    export_res_etape=self.export_res_etape,
                    export_res_sem=self.export_res_sem,
                    export_res_ues=self.export_res_ues,
                    export_res_modules=self.export_res_modules,
                    export_res_sdj=self.export_res_sdj,
                    export_res_rat=self.export_res_rat,
                )
            )

        return L

    def get_etape_apogee(self):
        """Le code etape: 'V1RT', donné par le code de l'élément VET"""
        for elt in self.apo_elts.values():
            if elt.type_objet == "VET":
                return elt.code
        raise ScoValueError("Pas de code etape Apogee (manque élément VET)")

    def get_vdi_apogee(self):
        """le VDI (version de diplôme), stocké dans l'élément VET
        (note: on pourrait peut-être aussi bien le récupérer dans l'en-tête XX-APO_TITRES-XX apoC_cod_vdi)
        """
        for elt in self.apo_elts.values():
            if elt.type_objet == "VET":
                return elt.version
        raise ScoValueError("Pas de VDI Apogee (manque élément VET)")

    def get_cod_dip_apogee(self):
        """Le code diplôme, indiqué dans l'en-tête de la maquette
        exemple: VDTRT
        Retourne '' si absent.
        """
        return self.titles.get("apoC_cod_dip", "")

    def get_annee_scolaire(self):
        """Annee scolaire du fichier Apogee: un integer
        = annee du mois de septembre de début
        """
        m = re.match("[12][0-9]{3}", self.titles["apoC_annee"])
        if not m:
            raise FormatError(
                'Annee scolaire (apoC_annee) invalide: "%s"' % self.titles["apoC_annee"]
            )
        return int(m.group(0))

    def write_header(self, f):
        """write apo CSV header on f
        (beginning of CSV until columns titles just after XX-APO_VALEURS-XX line)
        """
        f.write(self.header)
        f.write(APO_NEWLINE)
        f.write("XX-APO_VALEURS-XX" + APO_NEWLINE)
        f.write(self.column_titles)

    def write_etuds(self, f):
        """write apo CSV etuds on f"""
        for e in self.etuds:
            fs = []  #  e['nip'], e['nom'], e['prenom'], e['naissance'] ]
            for col_id in self.col_ids:
                try:
                    fs.append(str(e.new_cols[col_id]))
                except KeyError:
                    log(
                        "Error: %s %s missing column key %s"
                        % (e["nip"], e["nom"], col_id)
                    )
                    log("Details:\ne = %s" % pprint.pformat(e))
                    log("col_ids=%s" % pprint.pformat(self.col_ids))
                    log("etudiant ignore.\n")

            f.write(APO_SEP.join(fs) + APO_NEWLINE)

    def list_unknown_elements(self):
        """Liste des codes des elements Apogee non trouvés dans ScoDoc
        (après traitement de tous les étudiants)
        """
        s = set()
        for e in self.etuds:
            ul = [code for code in e.col_elts if e.col_elts[code] is None]
            s.update(ul)
        L = list(s)
        L.sort()
        return L

    def list_elements(self):
        """Liste les codes des elements Apogée de la maquette
        et ceux des semestres ScoDoc associés
        Retourne deux ensembles
        """
        try:
            maq_elems = {self.cols[col_id]["Code"] for col_id in self.col_ids[4:]}
        except KeyError:
            # une colonne déclarée dans l'en-tête n'est pas présente
            declared = self.col_ids[4:]  # id des colones dans l'en-tête
            present = sorted(self.cols.keys())  # colones presentes
            log("Fichier Apogee invalide:")
            log("Colonnes declarees: %s" % declared)
            log("Colonnes presentes: %s" % present)
            raise FormatError(
                """Fichier Apogee invalide<br/>Colonnes declarees: <tt>%s</tt>
            <br/>Colonnes presentes: <tt>%s</tt>"""
                % (declared, present)
            )
        # l'ensemble de tous les codes des elements apo des semestres:
        sem_elems = reduce(set.union, list(self.get_codes_by_sem().values()), set())

        return maq_elems, sem_elems

    def get_codes_by_sem(self):
        """Pour chaque semestre associé, donne l'ensemble des codes Apogée qui s'y trouvent
        (dans le semestre, les UE et les modules)
        """
        codes_by_sem = {}
        for sem in self.sems_etape:
            s = set()
            codes_by_sem[sem["formsemestre_id"]] = s
            for col_id in self.col_ids[4:]:
                code = self.cols[col_id]["Code"]  # 'V1RT'
                # associé à l'étape, l'année ou les semestre:
                if (
                    sco_formsemestre.sem_has_etape(sem, code)
                    or (code in sem["elt_sem_apo"].split(","))
                    or (code in sem["elt_annee_apo"].split(","))
                ):
                    s.add(code)
                    continue
                # associé à une UE:
                nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
                for ue in nt.get_ues():
                    if code in ue["code_apogee"].split(","):
                        s.add(code)
                        continue
                # associé à un module:
                modimpls = nt.get_modimpls()
                for modimpl in modimpls:
                    if code in modimpl["module"]["code_apogee"].split(","):
                        s.add(code)
                        continue
        # log('codes_by_sem=%s' % pprint.pformat(codes_by_sem))
        return codes_by_sem

    def build_cr_table(self):
        """Table compte rendu des décisions"""
        CR = []  # tableau compte rendu des decisions
        for e in self.etuds:
            cr = {
                "NIP": e["nip"],
                "nom": e["nom"],
                "prenom": e["prenom"],
                "est_NAR": e.is_NAR,
                "commentaire": "; ".join(e.log),
            }
            if e.col_elts and e.col_elts[self.etape_apogee] != None:
                cr["etape"] = e.col_elts[self.etape_apogee].get("R", "")
                cr["etape_note"] = e.col_elts[self.etape_apogee].get("N", "")
            else:
                cr["etape"] = ""
                cr["etape_note"] = ""
            CR.append(cr)

        columns_ids = ["NIP", "nom", "prenom"]
        columns_ids.extend(("etape", "etape_note", "est_NAR", "commentaire"))

        T = GenTable(
            columns_ids=columns_ids,
            titles=dict(zip(columns_ids, columns_ids)),
            rows=CR,
            xls_sheet_name="Decisions ScoDoc",
        )
        return T


def _apo_read_cols(f):
    """Lecture colonnes apo :
    Démarre après la balise XX-APO_COLONNES-XX
    et s'arrête après la balise APO_COL_VAL_FIN

    Colonne Apogee: les champs sont données par la ligne
    apoL_a01_code de la section XX-APO_COLONNES-XX
    col_id est apoL_c0001, apoL_c0002, ...

    :return: { col_id : { title : value } }
    Example: { 'apoL_c0001' : { 'Type Objet' : 'VET', 'Code' : 'V1IN', ... }, ... }
    """
    line = f.readline().strip(" " + APO_NEWLINE)
    fs = line.split(APO_SEP)
    if fs[0] != "apoL_a01_code":
        raise FormatError("invalid line: %s (expecting apoL_a01_code)" % line)
    col_keys = fs

    while True:  # skip premiere partie (apoL_a02_nom, ...)
        line = f.readline().strip(" " + APO_NEWLINE)
        if line == "APO_COL_VAL_DEB":
            break
    # après APO_COL_VAL_DEB
    cols = {}
    i = 0
    while True:
        line = f.readline().strip(" " + APO_NEWLINE)
        if line == "APO_COL_VAL_FIN":
            break
        i += 1
        fs = line.split(APO_SEP)
        # print fs[0], len(fs)
        # sanity check
        col_id = fs[0]  # apoL_c0001, ...
        if col_id in cols:
            raise FormatError("duplicate column definition: %s" % col_id)
        m = re.match(r"^apoL_c([0-9]{4})$", col_id)
        if not m:
            raise FormatError(
                "invalid column id: %s (expecting apoL_c%04d)" % (line, col_id)
            )
        if int(m.group(1)) != i:
            raise FormatError("invalid column id: %s for index %s" % (col_id, i))

        cols[col_id] = DictCol(list(zip(col_keys, fs)))
        cols[col_id].lineno = f.lineno  # for debuging purpose

    return cols


def _apo_read_TITRES(f):
    "Lecture section TITRES du fichier Apogée, renvoie dict"
    d = {}
    while True:
        line = f.readline().strip(
            " " + APO_NEWLINE
        )  # ne retire pas le \t (pour les clés vides)
        if not line.strip():  # stoppe sur ligne  pleines de \t
            break

        fields = line.split(APO_SEP)
        if len(fields) == 2:
            k, v = fields
        else:
            log("Error read CSV: \nline=%s\nfields=%s" % (line, fields))
            log(dir(f))
            raise FormatError(
                "Fichier Apogee incorrect (section titres, %d champs au lieu de 2)"
                % len(fields)
            )
        d[k] = v
    #
    if not d.get("apoC_Fichier_Exp", None):
        raise FormatError("Fichier Apogee incorrect: pas de titre apoC_Fichier_Exp")
    # keep only basename: may be a windows or unix pathname
    s = d["apoC_Fichier_Exp"].split("/")[-1]
    s = s.split("\\")[-1]  # for DOS paths, eg C:\TEMP\VL4RT_V3ASR.TXT
    d["apoC_Fichier_Exp"] = s
    return d


def _apo_skip_section(f):
    "Saute section Apo: s'arrete apres ligne vide"
    while True:
        line = f.readline().strip()
        if not line:
            break


# -------------------------------------


def comp_apo_sems(etape_apogee, annee_scolaire):
    """
    :param etape_apogee: etape (string or ApoEtapeVDI)
    :param annee_scolaire: annee (int)
    :return: list of sems for etape_apogee in annee_scolaire
    """
    return sco_formsemestre.list_formsemestre_by_etape(
        etape_apo=str(etape_apogee), annee_scolaire=annee_scolaire
    )


def nar_etuds_table(apo_data, NAR_Etuds):
    """Liste les NAR -> excel table"""
    code_etape = apo_data.etape_apogee
    today = datetime.datetime.today().strftime("%d/%m/%y")
    L = []
    NAR_Etuds.sort(key=lambda k: k["nom"])
    for e in NAR_Etuds:
        L.append(
            {
                "nom": e["nom"],
                "prenom": e["prenom"],
                "c0": "",
                "c1": "AD",
                "etape": code_etape,
                "c3": "",
                "c4": "",
                "c5": "",
                "c6": "N",
                "c7": "",
                "c8": "",
                "NIP": e["nip"],
                "c10": "",
                "c11": "",
                "c12": "",
                "c13": "NAR - Jury",
                "date": today,
            }
        )

    columns_ids = (
        "NIP",
        "nom",
        "prenom",
        "etape",
        "c0",
        "c1",
        "c3",
        "c4",
        "c5",
        "c6",
        "c7",
        "c8",
        "c10",
        "c11",
        "c12",
        "c13",
        "date",
    )
    T = GenTable(
        columns_ids=columns_ids,
        titles=dict(zip(columns_ids, columns_ids)),
        rows=L,
        xls_sheet_name="NAR ScoDoc",
    )
    return T.excel()


def export_csv_to_apogee(
    apo_csv_data,
    periode=None,
    dest_zip=None,
    export_res_etape=True,
    export_res_sem=True,
    export_res_ues=True,
    export_res_modules=True,
    export_res_sdj=True,
    export_res_rat=True,
):
    """Genere un fichier CSV Apogée
    à partir d'un fichier CSV Apogée vide (ou partiellement rempli)
    et des résultats ScoDoc.
    Si dest_zip, ajoute les fichiers générés à ce zip
    sinon crée un zip et le publie
    """
    apo_data = ApoData(
        apo_csv_data,
        periode=periode,
        export_res_etape=export_res_etape,
        export_res_sem=export_res_sem,
        export_res_ues=export_res_ues,
        export_res_modules=export_res_modules,
        export_res_sdj=export_res_sdj,
        export_res_rat=export_res_rat,
    )
    apo_data.setup()  # -> .sems_etape

    for e in apo_data.etuds:
        e.lookup_scodoc(apo_data.etape_formsemestre_ids)
        e.associate_sco(apo_data)

    # Ré-écrit le fichier Apogée
    f = io.StringIO()
    apo_data.write_header(f)
    apo_data.write_etuds(f)

    # Table des NAR:
    NAR_Etuds = [e for e in apo_data.etuds if e.is_NAR]
    if NAR_Etuds:
        nar_xls = nar_etuds_table(apo_data, NAR_Etuds)
    else:
        nar_xls = None

    # Journaux & Comptes-rendus
    # Orphelins: etudiants dans fichier Apogée mais pas dans ScoDoc
    Apo_Non_ScoDoc = [e for e in apo_data.etuds if e.etat == ETUD_ORPHELIN]
    # Non inscrits: connus de ScoDoc mais pas inscrit dans l'étape cette année
    Apo_Non_ScoDoc_Inscrits = [e for e in apo_data.etuds if e.etat == ETUD_NON_INSCRIT]
    # CR table
    cr_table = apo_data.build_cr_table()
    cr_xls = cr_table.excel()

    # Create ZIP
    if not dest_zip:
        data = io.BytesIO()
        dest_zip = ZipFile(data, "w")
        my_zip = True
    else:
        my_zip = False
    # Ensure unique filenames
    filename = apo_data.titles["apoC_Fichier_Exp"]
    basename, ext = os.path.splitext(filename)
    csv_filename = filename

    if csv_filename in dest_zip.namelist():
        basename = filename + "-" + apo_data.vdi_apogee
        csv_filename = basename + ext
    nf = 1
    tmplname = basename
    while csv_filename in dest_zip.namelist():
        basename = tmplname + "-%d" % nf
        csv_filename = basename + ext
        nf += 1

    log_filename = "scodoc-" + basename + ".log.txt"
    nar_filename = basename + "-nar" + scu.XLSX_SUFFIX
    cr_filename = basename + "-decisions" + scu.XLSX_SUFFIX

    logf = io.StringIO()
    logf.write("export_to_apogee du %s\n\n" % time.ctime())
    logf.write("Semestres ScoDoc sources:\n")
    for sem in apo_data.sems_etape:
        logf.write("\t%(titremois)s\n" % sem)
    logf.write("Periode: %s\n" % periode)
    logf.write("export_res_etape: %s\n" % int(export_res_etape))
    logf.write("export_res_sem: %s\n" % int(export_res_sem))
    logf.write("export_res_ues: %s\n" % int(export_res_ues))
    logf.write("export_res_modules: %s\n" % int(export_res_modules))
    logf.write("export_res_sdj: %s\n" % int(export_res_sdj))
    logf.write(
        "\nEtudiants Apogee non trouves dans ScoDoc:\n"
        + "\n".join(
            ["%s\t%s\t%s" % (e["nip"], e["nom"], e["prenom"]) for e in Apo_Non_ScoDoc]
        )
    )
    logf.write(
        "\nEtudiants Apogee non inscrits sur ScoDoc dans cette étape:\n"
        + "\n".join(
            [
                "%s\t%s\t%s" % (e["nip"], e["nom"], e["prenom"])
                for e in Apo_Non_ScoDoc_Inscrits
            ]
        )
    )

    logf.write(
        "\n\nElements Apogee inconnus dans ces semestres ScoDoc:\n"
        + "\n".join(apo_data.list_unknown_elements())
    )
    log(logf.getvalue())  # sortie aussi sur le log ScoDoc

    csv_data = f.getvalue().encode(APO_OUTPUT_ENCODING)

    # Write data to ZIP
    dest_zip.writestr(csv_filename, csv_data)
    dest_zip.writestr(log_filename, logf.getvalue())
    if nar_xls:
        dest_zip.writestr(nar_filename, nar_xls)
    dest_zip.writestr(cr_filename, cr_xls)

    if my_zip:
        dest_zip.close()
        data.seek(0)
        return send_file(
            data,
            mimetype="application/zip",
            download_name=scu.sanitize_filename(basename + "-scodoc.zip"),
            as_attachment=True,
        )
    else:
        return None  # zip modified in place
