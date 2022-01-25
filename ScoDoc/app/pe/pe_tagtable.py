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

import datetime

from app.scodoc import notes_table


class TableTag(object):
    """
    Classe mémorisant les moyennes des étudiants à différents tag et permettant de calculer les rangs et les statistiques :
    - nom : Nom représentatif des données de la Table
    - inscrlist : Les étudiants inscrits dans le TagTag avec leur information de la forme :
        { etudid : dictionnaire d'info extrait de Scodoc, ...}
    - taglist : Liste triée des noms des tags
    - resultats : Dictionnaire donnant les notes-moyennes de chaque étudiant par tag et la somme commulée
    des coeff utilisées dans le calcul de la moyenne pondérée, sous la forme :
        { tag : { etudid: (note_moy, somme_coeff_norm),
                                        ...}
    - rangs : Dictionnaire donnant les rang par tag de chaque étudiant de la forme :
        { tag : {etudid: rang, ...} }
    - nbinscrits : Nombre d'inscrits dans le semestre (pas de distinction entre les tags)
    - statistiques : Dictionnaire donnant les stastitiques (moyenne, min, max) des résultats par tag de la forme :
        { tag : (moy, min, max), ...}

    """

    def __init__(self, nom=""):
        self.nom = nom
        self.inscrlist = []
        self.identdict = {}
        self.taglist = []

        self.resultats = {}
        self.rangs = {}
        self.statistiques = {}

    # *****************************************************************************************************************
    # Accesseurs
    # *****************************************************************************************************************

    # -----------------------------------------------------------------------------------------------------------
    def get_moy_from_resultats(self, tag, etudid):
        """Renvoie la moyenne obtenue par un étudiant à un tag donné au regard du format de self.resultats"""
        return (
            self.resultats[tag][etudid][0]
            if tag in self.resultats and etudid in self.resultats[tag]
            else None
        )

    # -----------------------------------------------------------------------------------------------------------
    def get_rang_from_resultats(self, tag, etudid):
        """Renvoie le rang à un tag d'un étudiant au regard du format de self.resultats"""
        return (
            self.rangs[tag][etudid]
            if tag in self.resultats and etudid in self.resultats[tag]
            else None
        )

    # -----------------------------------------------------------------------------------------------------------
    def get_coeff_from_resultats(self, tag, etudid):
        """Renvoie la somme des coeffs de pondération normalisée utilisés dans le calcul de la moyenne à un tag d'un étudiant
        au regard du format de self.resultats.
        """
        return (
            self.resultats[tag][etudid][1]
            if tag in self.resultats and etudid in self.resultats[tag]
            else None
        )

    # -----------------------------------------------------------------------------------------------------------
    def get_all_tags(self):
        """Renvoie la liste des tags du semestre triée par ordre alphabétique"""
        # return self.taglist
        return sorted(self.resultats.keys())

    # -----------------------------------------------------------------------------------------------------------
    def get_nbinscrits(self):
        """Renvoie le nombre d'inscrits"""
        return len(self.inscrlist)

    # -----------------------------------------------------------------------------------------------------------
    def get_moy_from_stats(self, tag):
        """ Renvoie la moyenne des notes calculées pour d'un tag donné"""
        return self.statistiques[tag][0] if tag in self.statistiques else None

    def get_min_from_stats(self, tag):
        """ Renvoie la plus basse des notes calculées pour d'un tag donné"""
        return self.statistiques[tag][1] if tag in self.statistiques else None

    def get_max_from_stats(self, tag):
        """ Renvoie la plus haute des notes calculées pour d'un tag donné"""
        return self.statistiques[tag][2] if tag in self.statistiques else None

    # -----------------------------------------------------------------------------------------------------------
    # La structure des données mémorisées pour chaque tag dans le dictionnaire de synthèse
    # d'un jury PE
    FORMAT_DONNEES_ETUDIANTS = (
        "note",
        "coeff",
        "rang",
        "nbinscrits",
        "moy",
        "max",
        "min",
    )

    def get_resultatsEtud(self, tag, etudid):
        """Renvoie un tuple (note, coeff, rang, nb_inscrit, moy, min, max) synthétisant les résultats d'un étudiant
        à un tag donné. None sinon"""
        return (
            self.get_moy_from_resultats(tag, etudid),
            self.get_coeff_from_resultats(tag, etudid),
            self.get_rang_from_resultats(tag, etudid),
            self.get_nbinscrits(),
            self.get_moy_from_stats(tag),
            self.get_min_from_stats(tag),
            self.get_max_from_stats(tag),
        )

    #        return self.tag_stats[tag]
    #    else :
    #        return self.pe_stats

    # *****************************************************************************************************************
    # Ajout des notes
    # *****************************************************************************************************************

    # -----------------------------------------------------------------------------------------------------------
    def add_moyennesTag(self, tag, listMoyEtCoeff) -> bool:
        """
        Mémorise les moyennes, les coeffs de pondération et les etudid dans resultats
        avec calcul du rang
        :param tag: Un tag
        :param listMoyEtCoeff: Une liste donnant [ (moy, coeff, etudid) ]
        """
        # ajout des moyennes au dictionnaire résultat
        if listMoyEtCoeff:
            self.resultats[tag] = {
                etudid: (moyenne, somme_coeffs)
                for (moyenne, somme_coeffs, etudid) in listMoyEtCoeff
            }

            # Calcule les rangs
            lesMoyennesTriees = sorted(
                listMoyEtCoeff,
                reverse=True,
                key=lambda col: col[0]
                if isinstance(col[0], float)
                else 0,  # remplace les None et autres chaines par des zéros
            )  # triées
            self.rangs[tag] = notes_table.comp_ranks(lesMoyennesTriees)  # les rangs

            # calcul des stats
            self.comp_stats_d_un_tag(tag)
            return True
        return False

    # *****************************************************************************************************************
    # Méthodes dévolues aux calculs de statistiques (min, max, moy) sur chaque moyenne taguée
    # *****************************************************************************************************************

    def comp_stats_d_un_tag(self, tag):
        """
        Calcule la moyenne generale, le min, le max pour un tag donné,
        en ne prenant en compte que les moyennes significatives. Mémorise le resultat dans
        self.statistiques
        """
        stats = ("-NA-", "-", "-")
        if tag not in self.resultats:
            return stats

        notes = [
            self.get_moy_from_resultats(tag, etudid) for etudid in self.resultats[tag]
        ]  # les notes du tag
        notes_valides = [
            note for note in notes if isinstance(note, float) and note != None
        ]
        nb_notes_valides = len(notes_valides)
        if nb_notes_valides > 0:
            (moy, _) = moyenne_ponderee_terme_a_terme(notes_valides, force=True)
            self.statistiques[tag] = (moy, max(notes_valides), min(notes_valides))

    # ************************************************************************
    # Méthodes dévolues aux affichages -> a revoir
    # ************************************************************************
    def str_resTag_d_un_etudiant(self, tag, etudid, delim=";"):
        """Renvoie une chaine de caractères (valable pour un csv)
        décrivant la moyenne et le rang d'un étudiant, pour un tag donné ;
        """
        if tag not in self.get_all_tags() or etudid not in self.resultats[tag]:
            return ""

        moystr = TableTag.str_moytag(
            self.get_moy_from_resultats(tag, etudid),
            self.get_rang_from_resultats(tag, etudid),
            self.get_nbinscrits(),
            delim=delim,
        )
        return moystr

    def str_res_d_un_etudiant(self, etudid, delim=";"):
        """Renvoie sur une ligne les résultats d'un étudiant à tous les tags (par ordre alphabétique). """
        return delim.join(
            [self.str_resTag_d_un_etudiant(tag, etudid) for tag in self.get_all_tags()]
        )

    # -----------------------------------------------------------------------
    def str_moytag(cls, moyenne, rang, nbinscrit, delim=";"):
        """Renvoie une chaine de caractères représentant une moyenne (float ou string) et un rang
        pour différents formats d'affichage : HTML, debug ligne de commande, csv"""
        moystr = (
            "%2.2f%s%s%s%d" % (moyenne, delim, rang, delim, nbinscrit)
            if isinstance(moyenne, float)
            else str(moyenne) + delim + str(rang) + delim + str(nbinscrit)
        )
        return moystr

    str_moytag = classmethod(str_moytag)
    # -----------------------------------------------------------------------

    def str_tagtable(self, delim=";", decimal_sep=","):
        """Renvoie une chaine de caractère listant toutes les moyennes, les rangs des étudiants pour tous les tags. """
        entete = ["etudid", "nom", "prenom"]
        for tag in self.get_all_tags():
            entete += [titre + "_" + tag for titre in ["note", "rang", "nb_inscrit"]]
        chaine = delim.join(entete) + "\n"

        for etudid in self.identdict:
            descr = delim.join(
                [
                    etudid,
                    self.identdict[etudid]["nom"],
                    self.identdict[etudid]["prenom"],
                ]
            )
            descr += delim + self.str_res_d_un_etudiant(etudid, delim)
            chaine += descr + "\n"

        # Ajout des stats ... à faire

        if decimal_sep != ".":
            return chaine.replace(".", decimal_sep)
        else:
            return chaine


# ************************************************************************
# Fonctions diverses
# ************************************************************************


# *********************************************
def moyenne_ponderee_terme_a_terme(notes, coeffs=None, force=False):
    """
    Calcule la moyenne pondérée d'une liste de notes avec d'éventuels coeffs de pondération.
    Renvoie le résultat sous forme d'un tuple (moy, somme_coeff)

    La liste de notes contient soit : 1) des valeurs numériques 2) des strings "-NA-" (pas de notes) ou "-NI-" (pas inscrit)
    ou "-c-" ue capitalisée, 3) None.
    Le paramètre force indique si le calcul de la moyenne doit être forcée ou non, c'est à
    dire s'il y a ou non omission des notes non numériques (auquel cas la moyenne est calculée sur les
    notes disponibles) ; sinon renvoie (None, None).
    """
    # Vérification des paramètres d'entrée
    if not isinstance(notes, list) or (
        coeffs != None and not isinstance(coeffs, list) and len(coeffs) != len(notes)
    ):
        raise ValueError("Erreur de paramètres dans moyenne_ponderee_terme_a_terme")

    # Récupération des valeurs des paramètres d'entrée
    coeffs = [1] * len(notes) if coeffs == None else coeffs

    # S'il n'y a pas de notes
    if not notes:  # Si notes = []
        return (None, None)

    notesValides = [
        (1 if isinstance(note, float) or isinstance(note, int) else 0) for note in notes
    ]  # Liste indiquant les notes valides
    if force == True or (
        force == False and sum(notesValides) == len(notes)
    ):  # Si on force le calcul de la moyenne ou qu'on ne le force pas et qu'on a le bon nombre de notes
        (moyenne, ponderation) = (0.0, 0.0)
        for i in range(len(notes)):
            if notesValides[i]:
                moyenne += coeffs[i] * notes[i]
                ponderation += coeffs[i]
        return (
            (moyenne / (ponderation * 1.0), ponderation)
            if ponderation != 0
            else (None, 0)
        )
    else:  # Si on ne force pas le calcul de la moyenne
        return (None, None)


# -------------------------------------------------------------------------------------------
def conversionDate_StrToDate(date_fin):
    """Conversion d'une date fournie sous la forme d'une chaine de caractère de
    type 'jj/mm/aaaa' en un objet date du package datetime.
    Fonction servant au tri des semestres par date
    """
    (d, m, y) = [int(x) for x in date_fin.split("/")]
    date_fin_dst = datetime.date(y, m, d)
    return date_fin_dst
