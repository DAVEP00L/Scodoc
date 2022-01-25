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
Created on Fri Sep  9 09:15:05 2016

@author: barasc
"""

from app.pe.pe_tools import pe_print, PE_DEBUG
from app.pe import pe_tagtable


class SetTag(pe_tagtable.TableTag):
    """Agrège plusieurs semestres (ou settag) taggués (SemestreTag/Settag de 1 à 4) pour extraire des moyennes
    et des classements par tag pour un groupe d'étudiants donnés.
    par. exemple fusion d'un parcours ['S1', 'S2', 'S3'] donnant un nom_combinaison = '3S'
    Le settag est identifié sur la base du dernier semestre (ici le 'S3') ;
    les étudiants considérés sont donc ceux inscrits dans ce S3
    à condition qu'ils disposent d'un parcours sur tous les semestres fusionnés valides (par. ex
    un etudiant non inscrit dans un S1 mais dans un S2 et un S3 n'est pas pris en compte).
    """

    # -------------------------------------------------------------------------------------------------------------------
    def __init__(self, nom_combinaison, parcours):

        pe_tagtable.TableTag.__init__(self, nom=nom_combinaison)
        self.combinaison = nom_combinaison
        self.parcours = parcours  # Le groupe de semestres/parcours à aggréger

    # -------------------------------------------------------------------------------------------
    def set_Etudiants(self, etudiants, juryPEDict, etudInfoDict, nom_sem_final=None):
        """Détermine la liste des étudiants à prendre en compte, en partant de
        la liste en paramètre et en vérifiant qu'ils ont tous un parcours valide."""
        if nom_sem_final:
            self.nom += "_" + nom_sem_final
        for etudid in etudiants:
            parcours_incomplet = (
                sum([juryPEDict[etudid][nom_sem] == None for nom_sem in self.parcours])
                > 0
            )  # manque-t-il des formsemestre_id validant aka l'étudiant n'a pas été inscrit dans tous les semestres de l'aggrégat
            if not parcours_incomplet:
                self.inscrlist.append(etudInfoDict[etudid])
                self.identdict[etudid] = etudInfoDict[etudid]

        delta = len(etudiants) - len(self.inscrlist)
        if delta > 0:
            pe_print(self.nom + " -> " + str(delta) + " étudiants supprimés")

        # Le sous-ensemble des parcours
        self.parcoursDict = {etudid: juryPEDict[etudid] for etudid in self.identdict}

    # -------------------------------------------------------------------------------------------
    def get_Fids_in_settag(self):
        """Renvoie la liste des semestres (leur formsemestre_id) à prendre en compte
        pour le calcul des moyennes, en considérant tous les étudiants inscrits et
        tous les semestres de leur parcours"""
        return list(
            {
                self.parcoursDict[etudid][nom_sem]
                for etudid in self.identdict
                for nom_sem in self.parcours
            }
        )

    # ---------------------------------------------------------------------------------------------
    def set_SemTagDict(self, SemTagDict):
        """Mémorise les semtag nécessaires au jury."""
        self.SemTagDict = {fid: SemTagDict[fid] for fid in self.get_Fids_in_settag()}
        if PE_DEBUG >= 1:
            pe_print(u"    => %d semestres fusionnés" % len(self.SemTagDict))

    # -------------------------------------------------------------------------------------------------------------------
    def comp_data_settag(self):
        """Calcule tous les données numériques relatives au settag"""
        # Attributs relatifs aux tag pour les modules pris en compte
        self.taglist = self.do_taglist()  # la liste des tags
        self.do_tagdict()  # le dico descriptif des tags
        # if PE_DEBUG >= 1: pe_print("   => Tags = " + ", ".join( self.taglist ))

        # Calcul des moyennes de chaque étudiant par tag
        reussiteAjoutTag = {"OK": [], "KO": []}
        for tag in self.taglist:
            moyennes = self.comp_MoyennesSetTag(tag, force=False)
            res = self.add_moyennesTag(tag, moyennes)  # pas de notes => pas de moyenne
            reussiteAjoutTag["OK" if res else "KO"].append(tag)
        if len(reussiteAjoutTag["OK"]) > 0 and PE_DEBUG:
            pe_print(
                "     => Fusion de %d tags : " % (len(reussiteAjoutTag["OK"]))
                + ", ".join(reussiteAjoutTag["OK"])
            )
        if len(reussiteAjoutTag["KO"]) > 0 and PE_DEBUG:
            pe_print(
                "     => %d tags manquants : " % (len(reussiteAjoutTag["KO"]))
                + ", ".join(reussiteAjoutTag["KO"])
            )

    # -------------------------------------------------------------------------------------------------------------------
    def get_etudids(self):
        return list(self.identdict.keys())

    # -------------------------------------------------------------------------------------------------------------------
    def do_taglist(self):
        """Parcourt les tags des semestres taggués et les synthétise sous la forme
        d'une liste en supprimant les doublons
        """
        ensemble = []
        for semtag in self.SemTagDict.values():
            ensemble.extend(semtag.get_all_tags())
        return sorted(list(set(ensemble)))

    # -------------------------------------------------------------------------------------------------------------------
    def do_tagdict(self):
        """Synthétise la liste des modules pris en compte dans le calcul d'un tag (pour analyse des résultats)"""
        self.tagdict = {}
        for semtag in self.SemTagDict.values():
            for tag in semtag.get_all_tags():
                if tag != "dut":
                    if tag not in self.tagdict:
                        self.tagdict[tag] = {}
                    for mod in semtag.tagdict[tag]:
                        self.tagdict[tag][mod] = semtag.tagdict[tag][mod]

    # -------------------------------------------------------------------------------------------------------------------
    def get_NotesEtCoeffsSetTagEtudiant(self, tag, etudid):
        """Récupère tous les notes et les coeffs d'un étudiant relatives à un tag dans ses semestres valides et les renvoie dans un tuple (notes, coeffs)
        avec notes et coeffs deux listes"""
        lesSemsDeLEtudiant = [
            self.parcoursDict[etudid][nom_sem] for nom_sem in self.parcours
        ]  # peuvent être None

        notes = [
            self.SemTagDict[fid].get_moy_from_resultats(tag, etudid)
            for fid in lesSemsDeLEtudiant
            if tag in self.SemTagDict[fid].taglist
        ]  # eventuellement None
        coeffs = [
            self.SemTagDict[fid].get_coeff_from_resultats(tag, etudid)
            for fid in lesSemsDeLEtudiant
            if tag in self.SemTagDict[fid].taglist
        ]
        return (notes, coeffs)

    # -------------------------------------------------------------------------------------------------------------------
    def comp_MoyennesSetTag(self, tag, force=False):
        """Calcule et renvoie les "moyennes" des étudiants à un tag donné, en prenant en compte tous les semestres taggués
         de l'aggrégat, et leur coeff Par moyenne, s'entend une note moyenne, la somme des coefficients de pondération
        appliqué dans cette moyenne.

        Force ou non le calcul de la moyenne lorsque des notes sont manquantes.

        Renvoie les informations sous la forme d'une liste  [etudid: (moy, somme_coeff_normalisée, rang), ...}
        """
        # if tag not in self.get_all_tags() : return None

        # Calcule les moyennes
        lesMoyennes = []
        for (
            etudid
        ) in (
            self.get_etudids()
        ):  # Pour tous les étudiants non défaillants du semestre inscrits dans des modules relatifs au tag
            (notes, coeffs_norm) = self.get_NotesEtCoeffsSetTagEtudiant(
                tag, etudid
            )  # lecture des notes associées au tag
            (moyenne, somme_coeffs) = pe_tagtable.moyenne_ponderee_terme_a_terme(
                notes, coeffs_norm, force=force
            )
            lesMoyennes += [
                (moyenne, somme_coeffs, etudid)
            ]  # Un tuple (pour classement résumant les données)
        return lesMoyennes


class SetTagInterClasse(pe_tagtable.TableTag):
    """Récupère les moyennes de SetTag aggrégant un même parcours (par ex un ['S1', 'S2'] n'ayant pas fini au même S2
    pour fournir un interclassement sur un groupe d'étudiant => seul compte alors la promo
    nom_combinaison = 'S1' ou '1A'
    """

    # -------------------------------------------------------------------------------------------------------------------
    def __init__(self, nom_combinaison, diplome):

        pe_tagtable.TableTag.__init__(self, nom=nom_combinaison + "_%d" % diplome)
        self.combinaison = nom_combinaison
        self.parcoursDict = {}

    # -------------------------------------------------------------------------------------------
    def set_Etudiants(self, etudiants, juryPEDict, etudInfoDict, nom_sem_final=None):
        """Détermine la liste des étudiants à prendre en compte, en partant de
        la liste fournie en paramètre et en vérifiant que l'étudiant dispose bien d'un parcours valide pour la combinaison demandée.
        Renvoie le nombre d'étudiants effectivement inscrits."""
        if nom_sem_final:
            self.nom += "_" + nom_sem_final
        for etudid in etudiants:
            if juryPEDict[etudid][self.combinaison] != None:
                self.inscrlist.append(etudInfoDict[etudid])
                self.identdict[etudid] = etudInfoDict[etudid]
                self.parcoursDict[etudid] = juryPEDict[etudid]
        return len(self.inscrlist)

    # -------------------------------------------------------------------------------------------
    def get_Fids_in_settag(self):
        """Renvoie la liste des semestres (les formsemestre_id finissant la combinaison par ex. '3S' dont les fid des S3) à prendre en compte
        pour les moyennes, en considérant tous les étudiants inscrits"""
        return list(
            {self.parcoursDict[etudid][self.combinaison] for etudid in self.identdict}
        )

    # ---------------------------------------------------------------------------------------------
    def set_SetTagDict(self, SetTagDict):
        """Mémorise les settag nécessaires au jury."""
        self.SetTagDict = {
            fid: SetTagDict[fid] for fid in self.get_Fids_in_settag() if fid != None
        }
        if PE_DEBUG >= 1:
            pe_print(u"    => %d semestres utilisés" % len(self.SetTagDict))

    # -------------------------------------------------------------------------------------------------------------------
    def comp_data_settag(self):
        """Calcule tous les données numériques relatives au settag"""
        # Attributs relatifs aux tag pour les modules pris en compte
        self.taglist = self.do_taglist()

        # if PE_DEBUG >= 1: pe_print("   => Tags = " + ", ".join( self.taglist ))

        # Calcul des moyennes de chaque étudiant par tag
        reussiteAjoutTag = {"OK": [], "KO": []}
        for tag in self.taglist:
            moyennes = self.get_MoyennesSetTag(tag, force=False)
            res = self.add_moyennesTag(tag, moyennes)  # pas de notes => pas de moyenne
            reussiteAjoutTag["OK" if res else "KO"].append(tag)
        if len(reussiteAjoutTag["OK"]) > 0 and PE_DEBUG:
            pe_print(
                "     => Interclassement de %d tags : " % (len(reussiteAjoutTag["OK"]))
                + ", ".join(reussiteAjoutTag["OK"])
            )
        if len(reussiteAjoutTag["KO"]) > 0 and PE_DEBUG:
            pe_print(
                "     => %d tags manquants : " % (len(reussiteAjoutTag["KO"]))
                + ", ".join(reussiteAjoutTag["KO"])
            )

    # -------------------------------------------------------------------------------------------------------------------
    def get_etudids(self):
        return list(self.identdict.keys())

    # -------------------------------------------------------------------------------------------------------------------
    def do_taglist(self):
        """Parcourt les tags des semestres taggués et les synthétise sous la forme
        d'une liste en supprimant les doublons
        """
        ensemble = []
        for settag in self.SetTagDict.values():
            ensemble.extend(settag.get_all_tags())
        return sorted(list(set(ensemble)))

    # -------------------------------------------------------------------------------------------------------------------
    def get_NotesEtCoeffsSetTagEtudiant(self, tag, etudid):
        """Récupère tous les notes et les coeffs d'un étudiant relatives à un tag dans ses semestres valides et les renvoie dans un tuple (notes, coeffs)
        avec notes et coeffs deux listes"""
        leSetTagDeLetudiant = self.parcoursDict[etudid][self.combinaison]

        note = self.SetTagDict[leSetTagDeLetudiant].get_moy_from_resultats(tag, etudid)
        coeff = self.SetTagDict[leSetTagDeLetudiant].get_coeff_from_resultats(
            tag, etudid
        )
        return (note, coeff)

    # -------------------------------------------------------------------------------------------------------------------
    def get_MoyennesSetTag(self, tag, force=False):
        """Renvoie les "moyennes" des étudiants à un tag donné, en prenant en compte tous les settag de l'aggrégat,
        et leur coeff Par moyenne, s'entend une note moyenne, la somme des coefficients de pondération
        appliqué dans cette moyenne.

        Force ou non le calcul de la moyenne lorsque des notes sont manquantes.

        Renvoie les informations sous la forme d'une liste  [etudid: (moy, somme_coeff_normalisée, rang), ...}
        """
        # if tag not in self.get_all_tags() : return None

        # Calcule les moyennes
        lesMoyennes = []
        for (
            etudid
        ) in (
            self.get_etudids()
        ):  # Pour tous les étudiants non défaillants du semestre inscrits dans des modules relatifs au tag
            (moyenne, somme_coeffs) = self.get_NotesEtCoeffsSetTagEtudiant(
                tag, etudid
            )  # lecture des notes associées au tag
            lesMoyennes += [
                (moyenne, somme_coeffs, etudid)
            ]  # Un tuple (pour classement résumant les données)
        return lesMoyennes
