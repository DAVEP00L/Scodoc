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

"""
# Outil de comparaison Apogée/ScoDoc (J.-M. Place, Jan 2020)

## fonctionalités

Le menu 'synchronisation avec Apogée' ne permet pas de traiter facilement les cas
où un même code étape est implementé dans des semestres (au sens ScoDoc) différents.

La proposition est d'ajouter à la page de description des ensembles de semestres 
une section permettant de faire le point sur les cas particuliers.

Cette section est composée de deux parties:
* Une partie effectif où figurent le nombre d'étudiants selon un répartition par  
 semestre (en ligne) et par code étape (en colonne). On ajoute également des 
 colonnes/lignes correspondant à des anomalies (étudiant sans code étape, sans
 semestre, avec deux semestres, sans NIP, etc.).
 
 * La seconde partie présente la liste des étudiants. Il est possible qu'un 
  même nom figure deux fois dans la liste (si on a pas pu faire la correspondance
  entre une inscription apogée et un étudiant d'un semestre, par exemple).
 
 L'activation d'un des nombres du tableau 'effectifs' restreint l'affichage de 
 la liste aux étudiants qui contribuent à ce nombre.

## Réalisation

Les modifications logicielles portent sur:

### La création d'une classe sco_etape_bilan.py

Cette classe compile la totalité des données:

** Liste des semestres

** Listes des étapes

** Liste des étudiants

** constitution des listes d'anomalies

Cette classe explore la suite semestres du semset.
Pour chaque semestre, elle recense les étudiants du semestre et 
les codes étapes concernés.

puis tous les codes étapes (toujours en important les étudiants de l'étape
via le portail)

enfin on dispatch chaque étudiant dans une case - soit ordinaire, soit 
correspondant à une anomalie.

### Modification de sco_etape_apogee_view.py

Pour insertion de l'affichage ajouté

### Modification de sco_semset.py

Affichage proprement dit

### Modification de scp_formsemestre.py

Modification/ajout de la méthode sem_in_semestre_scolaire pour permettre 
l'inscrition de semestres décalés (S1 en septembre, ...).
Le filtrage s'effctue sur la date et non plus sur la parité du semestre (1-3/2-4).
"""

import json

from flask import url_for, g

from app.scodoc.sco_portal_apogee import get_inscrits_etape
from app import log
from app.scodoc.sco_utils import annee_scolaire_debut
from app.scodoc.gen_tables import GenTable

COL_PREFIX = "COL_"

# Les indicatifs sont des marqueurs de classe CSS insérés dans la table étudiant
# et utilisés par le javascript pour permettre un filtrage de la liste étudiants
#  sur un 'cas' considéré

# indicatifs
COL_CUMUL = "C9"
ROW_CUMUL = "R9"

# Constante d'anomalie
PAS_DE_NIP = "C1"
PAS_D_ETAPE = "C2"
PLUSIEURS_ETAPES = "C3"
PAS_DE_SEMESTRE = "R4"
PLUSIEURS_SEMESTRES = "R5"
NIP_NON_UNIQUE = "U"

FLAG = {
    PAS_DE_NIP: "A",
    PAS_D_ETAPE: "B",
    PLUSIEURS_ETAPES: "C",
    PAS_DE_SEMESTRE: "D",
    PLUSIEURS_SEMESTRES: "E",
    NIP_NON_UNIQUE: "U",
}


class DataEtudiant(object):
    """
    Structure de donnée des informations pour un étudiant
    """

    def __init__(self, nip="", etudid=""):
        self.nip = nip
        self.etudid = etudid
        self.data_apogee = None
        self.data_scodoc = None
        self.etapes = set()  # l'ensemble des étapes où il est inscrit
        self.semestres = set()  # l'ensemble des semestres où il est inscrit
        self.tags = set()  # les anomalies relevées
        self.ind_row = "-"  # là où il compte dans les effectifs (ligne et colonne)
        self.ind_col = "-"

    def add_etape(self, etape):
        self.etapes.add(etape)

    def add_semestre(self, semestre):
        self.semestres.add(semestre)

    def set_apogee(self, data_apogee):
        self.data_apogee = data_apogee

    def set_scodoc(self, data_scodoc):
        self.data_scodoc = data_scodoc

    def add_tag(self, tag):
        self.tags.add(tag)

    def set_ind_row(self, indicatif):
        self.ind_row = indicatif

    def set_ind_col(self, indicatif):
        self.ind_col = indicatif

    def get_identity(self):
        """
        Calcul le nom/prénom de l'étudiant (données ScoDoc en priorité, sinon données Apogée)
        :return: L'identité calculée
        """
        if self.data_scodoc is not None:
            return self.data_scodoc["nom"] + self.data_scodoc["prenom"]
        else:
            return self.data_apogee["nom"] + self.data_apogee["prenom"]


def help():
    return """
    <div id="export_help" class="pas_help"> <span>Explications sur les tableaux des effectifs et liste des 
    étudiants</span> 
        <div> <p>Le tableau des effectifs présente le nombre d'étudiants selon deux critères:</p> 
        <ul> 
        <li>En colonne le statut de l'étudiant par rapport à Apogée: 
            <ul> 
                <li><span class="libelle">Hors Apogée</span> 
                    <span class="anomalie">(anomalie A</span>): Le NIP de l'étudiant n'est pas connu d'apogée ou 
                l'étudiant n'a pas de NIP</li> 
                <li><span class="libelle">Pas d'étape</span> <span class="anomalie">(anomalie B</span>): Le NIP de 
                    l'étudiant ne correspond à aucune des étapes connues pour cet ensemble de semestre. Il est 
                    possible qu'il soit inscrit ailleurs (dans une autre ensemble de semestres, un autre département, 
                    une autre composante de l'université) ou en mobilité internationale.</li> 
                <li><span class="libelle">Plusieurs étapes</span> <span class="anomalie">(anomalie C)</span>: 
                    Les étudiants inscrits dans plusieurs étapes apogée de l'ensemble de semestres</li> 
                <li>Un des codes étapes connus (la liste des codes étapes connus est l'union des codes étapes 
                    déclarés pour chaque semestre particpant</li> 
                <li><span class="libelle">Total semestre</span>: cumul des effectifs de la ligne</li> 
            </ul> 
            </li> 
        <li>En ligne le statut de l'étudiant par rapport à ScoDoc: 
            <ul> 
                <li>Inscription dans un des semestres de l'ensemble</li> 
                <li><span class="libelle">Hors semestre</span> <span class="anomalie">(anomalie D)</span>: 
                    L'étudiant, bien qu'enregistré par apogée dans un des codes étapes connus, ne figure dans aucun 
                    des semestres de l'ensemble. On y trouve par exemple les étudiants régulièrement inscrits 
                    mais non présents à la rentrée (donc non enregistrés dans ScoDoc) <p>Note: On ne considère 
                    ici que les semestres de l'ensemble (l'inscription de l'étudiant dans un semestre étranger à 
                    l'ensemble actuel n'est pas vérifiée).</p> </li> 
                <li><span class="libelle">Plusieurs semestres</span> <span class="anomalie">(anomalie E)</span>: 
                    L'étudiant est enregistré dans plusieurs semestres de l'ensemble.</li> 
                <li><span class="libelle">Total</span>: cumul des effectifs de la colonne</li> 
            </ul> 
            </li> 
        <li>(<span class="anomalie">anomalie U</span>) On présente également les cas où un même NIP est affecté 
            à deux dossiers différents (Un dossier d'apogée et un dossier de ScoDoc). Un tel cas compte pour 
            deux unités dans le tableau des effcetifs et engendre 2 lignes distinctes dans la liste des étudiants</li> 
        </ul> 
        </div> 
    </div> """


def entete_liste_etudiant():
    return """
            <h4 id='effectifs'>Liste des étudiants <span id='compte'></span>
                <ul>
                <li id='sans_filtre'>Pas de filtrage: Cliquez sur un des nombres du tableau ci-dessus pour 
                    n'afficher que les étudiants correspondants</li>
                <li id='filtre_row' style='display:none'></li>
                <li id='filtre_col' style='display:none'></li>
                </ul>
            </h4>
    """


class EtapeBilan(object):
    """
    Structure de donnée représentation l'état global de la comparaison ScoDoc/Apogée
    """

    def __init__(self):
        self.semestres = (
            {}
        )  # Dictionnaire des formsemestres du semset (formsemestre_id -> semestre)
        self.etapes = []  # Liste des étapes apogées du semset (clé_apogée)
        # pour les descriptions qui suivents:
        #   cle_etu = nip si non vide, sinon etudid
        #   data_etu = { nip, etudid, data_apogee, data_scodoc }
        self.etudiants = {}  # cle_etu -> data_etu
        self.keys_etu = {}  # nip -> [ etudid* ]
        self.etu_semestre = {}  # semestre -> { key_etu }
        self.etu_etapes = {}  # etape -> { key_etu }
        self.repartition = {}  # (ind_row, ind_col) -> nombre d étudiants
        self.tag_count = {}  # nombre d'animalies détectées (par type d'anomalie)

        # on collectionne les indicatifs trouvés pour n'afficher que les indicatifs 'utiles'
        self.indicatifs = {}
        self.top_row = 0
        self.top_col = 0
        self.all_rows_ind = [PAS_DE_SEMESTRE, PLUSIEURS_SEMESTRES]
        self.all_cols_ind = [PAS_DE_NIP, PAS_D_ETAPE, PLUSIEURS_ETAPES]
        self.all_rows_str = None
        self.all_cols_str = None
        self.titres = {
            PAS_DE_NIP: "PAS_DE_NIP",
            PAS_D_ETAPE: "PAS_D_ETAPE",
            PLUSIEURS_ETAPES: "PLUSIEURS_ETAPES",
            PAS_DE_SEMESTRE: "PAS_DE_SEMESTRE",
            PLUSIEURS_SEMESTRES: "PLUSIEURS_SEMESTRES",
            NIP_NON_UNIQUE: "NIP_NON_UNIQUE",
        }

    def inc_tag_count(self, tag):
        if tag not in self.tag_count:
            self.tag_count[tag] = 0
        self.tag_count[tag] += 1

    def set_indicatif(self, item, as_row):  # item = semestre ou key_etape
        if as_row:
            indicatif = "R" + chr(self.top_row + 97)
            self.all_rows_ind.append(indicatif)
            self.top_row += 1
        else:
            indicatif = "C" + chr(self.top_col + 97)
            self.all_cols_ind.append(indicatif)
            self.top_col += 1
        self.indicatifs[item] = indicatif
        if self.top_row > 26:
            log("Dépassement (plus de 26 semestres dans la table diagnostic")
        if self.top_col > 26:
            log("Dépassement (plus de 26 étapes dans la table diagnostic")

    def add_sem(self, semestre):
        """
        Prise en compte d'un semestre dans le bilan.
        * ajoute le semestre et les étudiants du semestre
        * ajoute les étapes du semestre et (via portail) les étudiants pour ces codes étapes
        :param semestre: Le semestre à prendre en compte
        :return: None
        """
        self.semestres[semestre["formsemestre_id"]] = semestre
        # if anneeapogee == None:  # année d'inscription par défaut
        anneeapogee = str(
            annee_scolaire_debut(semestre["annee_debut"], semestre["mois_debut_ord"])
        )
        self.set_indicatif(semestre["formsemestre_id"], True)
        for etape in semestre["etapes"]:
            self.add_etape(etape.etape_vdi, anneeapogee)

    def add_etape(self, etape_str, anneeapogee):
        """
        Prise en compte d'une étape apogée
        :param etape_str: La clé de l'étape à prendre en compte
        :param anneeapogee:  l'année de l'étape à prendre en compte
        :return: None
        """
        if etape_str != "":
            key_etape = etape_to_key(anneeapogee, etape_str)
            if key_etape not in self.etapes:
                self.etapes.append(key_etape)
                self.set_indicatif(
                    key_etape, False
                )  # ajout de la colonne/indicatif supplémentaire

    def compute_key_etu(self, nip, etudid):
        """
        Calcul de la clé étudiant:
        * Le nip si il existe
        * sinon l'identifiant ScoDoc
        Tient à jour le dictionnaire key_etu (référentiel des étudiants)
        La problèmatique est de gérer toutes les anomalies possibles:
        - étudiant sans nip,
        - plusieurs étudiants avec le même nip,
        - etc.
        :param nip: le nip de l'étudiant
        :param etudid: l'identifiant ScoDoc
        :return: L'identifiant unique de l'étudiant
        """
        if nip not in self.keys_etu:
            self.keys_etu[nip] = []
        if etudid not in self.keys_etu[nip]:
            if etudid is None:
                if len(self.keys_etu[nip]) == 1:
                    etudid = self.keys_etu[nip][0]
                else:  # nip non trouvé ou utilisé par plusieurs étudiants
                    self.keys_etu[nip].append(None)
            else:
                self.keys_etu[nip].append(etudid)
        return nip, etudid

    def register_etud_apogee(self, etud, etape):
        """
        Enregistrement des données de l'étudiant par rapport à apogée.
        L'étudiant peut avoir été déjà enregistré auparavant (par exemple connu par son semestre)
        Dans ce cas, on ne met à jour que son association à l'étape apogée
        :param etud: les données étudiant
        :param etape:  l'étape apogée
        :return:
        """
        nip = etud["nip"]
        key_etu = self.compute_key_etu(nip, None)
        if key_etu not in self.etudiants:
            data = DataEtudiant(nip)
            data.set_apogee(etud)
            data.add_etape(etape)
            self.etudiants[key_etu] = data
        else:
            self.etudiants[key_etu].set_apogee(etud)
            self.etudiants[key_etu].add_etape(etape)
        return key_etu

    def register_etud_scodoc(self, etud, semestre):
        """
        Enregistrement de l'étudiant par rapport à son semestre
        :param etud: Les données de l'étudiant
        :param semestre:  Le semestre où il est à enregistrer
        :return: la clé unique pour cet étudiant
        """
        nip = etud["code_nip"]
        etudid = etud["etudid"]
        key_etu = self.compute_key_etu(nip, etudid)
        if key_etu not in self.etudiants:
            data = DataEtudiant(nip, etudid)
            data.set_scodoc(etud)
            data.add_semestre(semestre)
            self.etudiants[key_etu] = data
        else:
            self.etudiants[key_etu].add_semestre(semestre)
        return key_etu

    def load_listes(self):
        """
        Inventaire complet des étudiants:
        * Pour tous les semestres d'abord
        * Puis pour toutes les étapes
        :return:  None
        """
        for semestre in self.semestres:
            etuds = self.semestres[semestre]["etuds"]
            self.etu_semestre[semestre] = set()
            for etud in etuds:
                key_etu = self.register_etud_scodoc(etud, semestre)
                self.etu_semestre[semestre].add(key_etu)

        for key_etape in self.etapes:
            anneeapogee, etapestr = key_to_values(key_etape)
            self.etu_etapes[key_etape] = set()
            for etud in get_inscrits_etape(etapestr, anneeapogee):
                key_etu = self.register_etud_apogee(etud, key_etape)
                self.etu_etapes[key_etape].add(key_etu)

    def dispatch(self):
        """
        Réparti l'ensemble des étudiants selon les lignes (semestres) et les colonnes (étapes).

        :return:  None
        """
        # Initialisation des cumuls
        self.repartition[ROW_CUMUL, COL_CUMUL] = 0
        self.repartition[PAS_DE_SEMESTRE, COL_CUMUL] = 0
        self.repartition[PLUSIEURS_SEMESTRES, COL_CUMUL] = 0
        self.repartition[ROW_CUMUL, PAS_DE_NIP] = 0
        self.repartition[ROW_CUMUL, PAS_D_ETAPE] = 0
        self.repartition[ROW_CUMUL, PLUSIEURS_ETAPES] = 0
        for semestre in self.semestres:
            self.repartition[self.indicatifs[semestre], COL_CUMUL] = 0
        for key_etape in self.etapes:
            self.repartition[ROW_CUMUL, self.indicatifs[key_etape]] = 0

        # recherche des nip identiques
        for nip in self.keys_etu:
            if nip != "":
                nbnips = len(self.keys_etu[nip])
                if nbnips > 1:
                    for i, etudid in enumerate(self.keys_etu[nip]):
                        data_etu = self.etudiants[nip, etudid]
                        data_etu.add_tag(NIP_NON_UNIQUE)
                        data_etu.nip = data_etu.nip + "&nbsp;(%d/%d)" % (i + 1, nbnips)
                        self.inc_tag_count(NIP_NON_UNIQUE)
        for nip in self.keys_etu:
            for etudid in self.keys_etu[nip]:
                key_etu = (nip, etudid)
                data_etu = self.etudiants[key_etu]
                ind_col = "-"
                ind_row = "-"

                # calcul de la colonne
                if len(data_etu.etapes) == 1:
                    ind_col = self.indicatifs[list(data_etu.etapes)[0]]
                elif nip == "":
                    data_etu.add_tag(FLAG[PAS_DE_NIP])
                    ind_col = PAS_DE_NIP
                elif len(data_etu.etapes) == 0:
                    self.etudiants[key_etu].add_tag(FLAG[PAS_D_ETAPE])
                    ind_col = PAS_D_ETAPE
                if len(data_etu.etapes) > 1:
                    data_etu.add_tag(FLAG[PLUSIEURS_ETAPES])
                    ind_col = PLUSIEURS_ETAPES

                if len(data_etu.semestres) == 1:
                    ind_row = self.indicatifs[list(data_etu.semestres)[0]]
                elif len(data_etu.semestres) > 1:
                    data_etu.add_tag(FLAG[PLUSIEURS_SEMESTRES])
                    ind_row = PLUSIEURS_SEMESTRES
                elif len(data_etu.semestres) < 1:
                    self.etudiants[key_etu].add_tag(FLAG[PAS_DE_SEMESTRE])
                    ind_row = PAS_DE_SEMESTRE

                data_etu.set_ind_col(ind_col)
                data_etu.set_ind_row(ind_row)
                self._inc_count(ind_row, ind_col)
                self.inc_tag_count(ind_row)
                self.inc_tag_count(ind_col)

    def html_diagnostic(self):
        """
        affichage de l'html
        :return: Le code html à afficher
        """
        self.load_listes()  # chargement des données
        self.dispatch()  # analyse et répartition
        # calcul de la liste des colonnes et des lignes de la table des effectifs
        self.all_rows_str = "'" + ",".join(["." + r for r in self.all_rows_ind]) + "'"
        self.all_cols_str = "'" + ",".join(["." + c for c in self.all_cols_ind]) + "'"

        H = [
            '<div id="synthese" class=u"semset_description"><h4>Tableau des effectifs</h4>',
            self._diagtable(),
            self.display_tags(),
            entete_liste_etudiant(),
            self.table_effectifs(),
            help(),
        ]

        return "\n".join(H)

    def _inc_count(self, ind_row, ind_col):
        if (ind_row, ind_col) not in self.repartition:
            self.repartition[ind_row, ind_col] = 0
        self.repartition[ind_row, ind_col] += 1
        self.repartition[ROW_CUMUL, ind_col] += 1
        self.repartition[ind_row, COL_CUMUL] += 1
        self.repartition[ROW_CUMUL, COL_CUMUL] += 1

    def _get_count(self, ind_row, ind_col):
        if (ind_row, ind_col) in self.repartition:
            count = self.repartition[ind_row, ind_col]
            if count > 1:
                comptage = "(%d étudiants)" % count
            else:
                comptage = "(1 étudiant)"
        else:
            count = 0
            return ""

        # Ajoute l'appel à la routine javascript de filtrage (apo_semset_maq_status.js
        # signature:
        #   function show_css(elt, all_rows, all_cols, row, col, precision)
        #      elt: le lien cliqué
        #      all_rows: la liste de toutes les lignes existantes dans le tableau répartition
        #           (exemple: ".Rb,.R1,.R2,.R3")
        #      all_cols: la liste de toutes les colonnes existantes dans le tableau répartition
        #           (exemple: ".Ca,.C1,.C2,.C3")
        #      row: la ligne sélectionnée (sélecteur css) (expl: ".R1")
        #            ; '*' si pas de sélection sur la ligne
        #      col: la (les) colonnes sélectionnées (sélecteur css) (exple: ".C2")
        #            ; '*' si pas de sélection sur colonne
        #      precision: ajout sur le titre (en général, le nombre d'étudiant)
        #      filtre_row: explicitation du filtre ligne éventuelle
        #      filtre_col: explicitation du filtre colonne évnetuelle
        if ind_row == ROW_CUMUL and ind_col == COL_CUMUL:
            javascript = "doFiltrage(%s, %s, '*', '*', '%s', '%s', '%s');" % (
                self.all_rows_str,
                self.all_cols_str,
                comptage,
                "",
                "",
            )
        elif ind_row == ROW_CUMUL:
            javascript = "doFiltrage(%s, %s, '*', '.%s', '%s', '%s', '%s');" % (
                self.all_rows_str,
                self.all_cols_str,
                ind_col,
                comptage,
                "",
                json.dumps(self.titres[ind_col].replace("<br/>", " / "))[1:-1],
            )
        elif ind_col == COL_CUMUL:
            javascript = "doFiltrage(%s, %s, '.%s', '*', '%s', '%s', '%s');" % (
                self.all_rows_str,
                self.all_cols_str,
                ind_row,
                " (%d étudiants)" % count,
                json.dumps(self.titres[ind_row])[1:-1],
                "",
            )
        else:
            javascript = "doFiltrage(%s, %s, '.%s', '.%s', '%s', '%s', '%s');" % (
                self.all_rows_str,
                self.all_cols_str,
                ind_row,
                ind_col,
                comptage,
                json.dumps(self.titres[ind_row])[1:-1],
                json.dumps(self.titres[ind_col].replace("<br/>", " / "))[1:-1],
            )
        return '<a href="#synthese" onclick="%s">%d</a>' % (javascript, count)

    def _diagtable(self):
        H = []

        liste_semestres = sorted(self.semestres.keys())
        liste_etapes = []
        for key_etape in self.etapes:
            liste_etapes.append(key_etape)
        liste_etapes.sort(key=lambda key: etape_to_col(key_etape))

        col_ids = []
        if PAS_DE_NIP in self.tag_count:
            col_ids.append(PAS_DE_NIP)
        if PAS_D_ETAPE in self.tag_count:
            col_ids.append(PAS_D_ETAPE)
        if PLUSIEURS_ETAPES in self.tag_count:
            col_ids.append(PLUSIEURS_ETAPES)
        self.titres["row_title"] = "Semestre"
        self.titres[PAS_DE_NIP] = "Hors Apogée (" + FLAG[PAS_DE_NIP] + ")"
        self.titres[PAS_D_ETAPE] = "Pas d'étape (" + FLAG[PAS_D_ETAPE] + ")"
        self.titres[PLUSIEURS_ETAPES] = (
            "Plusieurs etapes (" + FLAG[PLUSIEURS_ETAPES] + ")"
        )
        for key_etape in liste_etapes:
            col_id = self.indicatifs[key_etape]
            col_ids.append(col_id)
            self.titres[col_id] = "%s<br/>%s" % key_to_values(key_etape)
        col_ids.append(COL_CUMUL)
        self.titres[COL_CUMUL] = "Total<br/>semestre"

        rows = []
        for semestre in liste_semestres:
            ind_row = self.indicatifs[semestre]
            self.titres[ind_row] = (
                "%(titre_num)s (%(formsemestre_id)s)" % self.semestres[semestre]
            )
            row = {
                "row_title": self.link_semestre(semestre),
                PAS_DE_NIP: self._get_count(ind_row, PAS_DE_NIP),
                PAS_D_ETAPE: self._get_count(ind_row, PAS_D_ETAPE),
                PLUSIEURS_ETAPES: self._get_count(ind_row, PLUSIEURS_ETAPES),
                COL_CUMUL: self._get_count(ind_row, COL_CUMUL),
                "_css_row_class": ind_row,
            }
            for key_etape in liste_etapes:
                ind_col = self.indicatifs[key_etape]
                row[ind_col] = self._get_count(ind_row, ind_col)
            rows.append(row)

        if PAS_DE_SEMESTRE in self.tag_count:
            row = {
                "row_title": "Hors semestres (" + FLAG[PAS_DE_SEMESTRE] + ")",
                PAS_DE_NIP: "",
                PAS_D_ETAPE: "",
                PLUSIEURS_ETAPES: "",
                COL_CUMUL: self._get_count(PAS_DE_SEMESTRE, COL_CUMUL),
                "_css_row_class": PAS_DE_SEMESTRE,
            }
            for key_etape in liste_etapes:
                ind_col = self.indicatifs[key_etape]
                row[ind_col] = self._get_count(PAS_DE_SEMESTRE, ind_col)
            rows.append(row)

        if PLUSIEURS_SEMESTRES in self.tag_count:
            row = {
                "row_title": "Plusieurs semestres (" + FLAG[PLUSIEURS_SEMESTRES] + ")",
                PAS_DE_NIP: "",
                PAS_D_ETAPE: "",
                PLUSIEURS_ETAPES: "",
                COL_CUMUL: self._get_count(PLUSIEURS_SEMESTRES, COL_CUMUL),
                "_css_row_class": PLUSIEURS_SEMESTRES,
            }
            for key_etape in liste_etapes:
                ind_col = self.indicatifs[key_etape]
                row[ind_col] = self._get_count(PLUSIEURS_SEMESTRES, ind_col)
            rows.append(row)

        row = {
            "row_title": "Total",
            PAS_DE_NIP: self._get_count(ROW_CUMUL, PAS_DE_NIP),
            PAS_D_ETAPE: self._get_count(ROW_CUMUL, PAS_D_ETAPE),
            PLUSIEURS_ETAPES: self._get_count(ROW_CUMUL, PLUSIEURS_ETAPES),
            COL_CUMUL: self._get_count(ROW_CUMUL, COL_CUMUL),
            "_css_row_class": COL_CUMUL,
        }
        for key_etape in liste_etapes:
            ind_col = self.indicatifs[key_etape]
            row[ind_col] = self._get_count(ROW_CUMUL, ind_col)
        rows.append(row)

        H.append(
            GenTable(
                rows,
                col_ids,
                self.titres,
                html_class="repartition",
                html_with_td_classes=True,
            ).gen(format="html")
        )
        return "\n".join(H)

    def display_tags(self):
        H = []
        if NIP_NON_UNIQUE in self.tag_count:
            H.append("<h4>Anomalies</h4>")
            javascript = "show_tag(%s, %s, '%s');" % (
                self.all_rows_str,
                self.all_cols_str,
                NIP_NON_UNIQUE,
            )
            H.append(
                'Code(s) nip) partagé(s) par <a href="#synthèse" onclick="%s">%d</a> étudiants<br/>'
                % (javascript, self.tag_count[NIP_NON_UNIQUE])
            )
        return "\n".join(H)

    @staticmethod
    def link_etu(etudid, nom):
        return '<a class="stdlink" href="%s">%s</a>' % (
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            nom,
        )

    def link_semestre(self, semestre, short=False):
        if short:
            return (
                '<a class="stdlink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%('
                "formsemestre_id)s</a> " % self.semestres[semestre]
            )
        else:
            return (
                '<a class="stdlink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titre_num)s'
                " %(mois_debut)s - %(mois_fin)s)</a>" % self.semestres[semestre]
            )

    def table_effectifs(self):
        H = []

        col_ids = ["tag", "etudiant", "prenom", "nip", "semestre", "apogee", "annee"]
        titles = {
            "tag": "Etat",
            "etudiant": "Nom",
            "prenom": "Prenom",
            "nip": "code nip",
            "semestre": "semestre",
            "annee": "année",
            "apogee": "etape",
        }
        rows = []

        for data_etu in sorted(
            list(self.etudiants.values()), key=lambda etu: etu.get_identity()
        ):
            nip = data_etu.nip
            etudid = data_etu.etudid
            if data_etu.data_scodoc is None:
                nom = data_etu.data_apogee["nom"]
                prenom = data_etu.data_apogee["prenom"]
                link = nom
            else:
                nom = data_etu.data_scodoc["nom"]
                prenom = data_etu.data_scodoc["prenom"]
                link = self.link_etu(etudid, nom)
            tag = ", ".join([tag for tag in sorted(data_etu.tags)])
            semestre = "<br/>".join(
                [self.link_semestre(sem, True) for sem in data_etu.semestres]
            )
            annees = "<br/>".join([etape[0] for etape in data_etu.etapes])
            etapes = "<br/>".join([etape[1] for etape in data_etu.etapes])
            classe = data_etu.ind_row + data_etu.ind_col
            if NIP_NON_UNIQUE in data_etu.tags:
                classe += " " + NIP_NON_UNIQUE
            row = {
                "tag": tag,
                "etudiant": link,
                "prenom": prenom.capitalize(),
                "nip": nip,
                "semestre": semestre,
                "annee": annees,
                "apogee": etapes,
                "_css_row_class": classe,
            }
            rows.append(row)

        H.append(
            GenTable(
                rows,
                col_ids,
                titles,
                table_id="detail",
                html_class="table_leftalign",
                html_sortable=True,
            ).gen(format="html")
        )
        return "\n".join(H)


def etape_to_key(anneeapogee, etapestr):
    return anneeapogee, etapestr


def key_to_values(key_etape):
    return key_etape


def etape_to_col(key_etape):
    return "%s@%s" % key_etape
