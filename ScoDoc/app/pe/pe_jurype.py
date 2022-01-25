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

# ----------------------------------------------------------
# Ensemble des fonctions et des classes
# permettant les calculs preliminaires (hors affichage)
# a l'edition d'un jury de poursuites d'etudes
# ----------------------------------------------------------

import io
import os
from zipfile import ZipFile

from app.scodoc.gen_tables import GenTable, SeqGenTable
import app.scodoc.sco_utils as scu
from app.scodoc import sco_cache
from app.scodoc import sco_codes_parcours  # sco_codes_parcours.NEXT -> sem suivant
from app.scodoc import sco_etud
from app.scodoc import sco_formsemestre
from app.pe import pe_tagtable
from app.pe import pe_tools
from app.pe import pe_semestretag
from app.pe import pe_settag

# ----------------------------------------------------------------------------------------
def comp_nom_semestre_dans_parcours(sem):
    """Le nom a afficher pour titrer un semestre
    par exemple: "semestre 2 FI 2015"
    """
    from app.scodoc import sco_formations

    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
    return "%s %s %s  %s" % (
        parcours.SESSION_NAME,  # eg "semestre"
        sem["semestre_id"],  # eg 2
        sem.get("modalite", ""),  # eg FI ou FC
        sem["annee_debut"],  # eg 2015
    )


# ----------------------------------------------------------------------------------------
class JuryPE(object):
    """Classe memorisant toutes les informations necessaires pour etablir un jury de PE. Modele
    base sur NotesTable

    Attributs : - diplome : l'annee d'obtention du diplome DUT et du jury de PE (generalement fevrier XXXX)
                - juryEtudDict : dictionnaire récapitulant les étudiants participant au jury PE (données administratives +
                                celles des semestres valides à prendre en compte permettant le calcul des moyennes  ...
                                {'etudid : { 'nom', 'prenom', 'civilite', 'diplome', '',  }}
                                Rq: il contient à la fois les étudiants qui vont être diplomés à la date prévue
                                et ceux qui sont éliminés (abandon, redoublement, ...) pour affichage alternatif

    """

    # Variables de classe décrivant les aggrégats, leur ordre d'apparition temporelle et
    # leur affichage dans les avis latex
    PARCOURS = {
        "S1": {
            "aggregat": ["S1"],
            "ordre": 1,
            "affichage_court": "S1",
            "affichage_long": "Semestre 1",
        },
        "S2": {
            "aggregat": ["S2"],
            "ordre": 2,
            "affichage_court": "S2",
            "affichage_long": "Semestre 2",
        },
        "S3": {
            "aggregat": ["S3"],
            "ordre": 4,
            "affichage_court": "S3",
            "affichage_long": "Semestre 3",
        },
        "S4": {
            "aggregat": ["S4"],
            "ordre": 5,
            "affichage_court": "S4",
            "affichage_long": "Semestre 4",
        },
        "1A": {
            "aggregat": ["S1", "S2"],
            "ordre": 3,
            "affichage_court": "1A",
            "affichage_long": "1ère année",
        },
        "2A": {
            "aggregat": ["S3", "S4"],
            "ordre": 6,
            "affichage_court": "2A",
            "affichage_long": "2ème année",
        },
        "3S": {
            "aggregat": ["S1", "S2", "S3"],
            "ordre": 7,
            "affichage_court": "S1+S2+S3",
            "affichage_long": "DUT du semestre 1 au semestre 3",
        },
        "4S": {
            "aggregat": ["S1", "S2", "S3", "S4"],
            "ordre": 8,
            "affichage_court": "DUT",
            "affichage_long": "DUT (tout semestre inclus)",
        },
    }

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, semBase):
        """
        Création d'une table PE sur la base d'un semestre selectionné. De ce semestre est déduit :
        1. l'année d'obtention du DUT,
        2. tous les étudiants susceptibles à ce stade (au regard de leur parcours) d'être diplomés.

        Args:
            semBase: le dictionnaire sem donnant la base du jury
            meme_programme: si True, impose un même programme pour tous les étudiants participant au jury,
                            si False, permet des programmes differents
        """
        self.semTagDict = (
            {}
        )  # Les semestres taggués à la base des calculs de moyenne par tag
        self.setTagDict = (
            {}
        )  # dictionnaire récapitulant les semTag impliqués dans le jury de la forme { 'formsemestre_id' : object Semestre_tag
        self.promoTagDict = {}

        # L'année du diplome
        self.diplome = get_annee_diplome_semestre(semBase)

        # Un zip où ranger les fichiers générés:
        self.NOM_EXPORT_ZIP = "Jury_PE_%s" % self.diplome
        self.zipdata = io.BytesIO()
        self.zipfile = ZipFile(self.zipdata, "w")

        #
        self.ETUDINFO_DICT = {}  # Les infos sur les étudiants
        self.PARCOURSINFO_DICT = {}  # Les parcours des étudiants
        self.syntheseJury = {}  # Le jury de synthèse

        # Calcul du jury PE
        self.exe_calculs_juryPE(semBase)
        self.synthetise_juryPE()

        # Export des données => mode 1 seule feuille -> supprimé
        # filename = self.NOM_EXPORT_ZIP + "jurySyntheseDict_" + str(self.diplome) + '.xls'
        # self.xls = self.table_syntheseJury(mode="singlesheet")
        # self.add_file_to_zip(filename, self.xls.excel())

        # Fabrique 1 fichier excel résultat avec 1 seule feuille => trop gros
        filename = self.NOM_EXPORT_ZIP + "_jurySyntheseDict" + scu.XLSX_SUFFIX
        self.xlsV2 = self.table_syntheseJury(mode="multiplesheet")
        if self.xlsV2:
            self.add_file_to_zip(filename, self.xlsV2.excel())

        # Pour debug
        # self.syntheseJury = pe_tools.JURY_SYNTHESE_POUR_DEBUG #Un dictionnaire fictif pour debug

    # ------------------------------------------------------------------------------------------------------------------
    def add_file_to_zip(self, filename, data, path=""):
        """Add a file to our zip
        All files under NOM_EXPORT_ZIP/
        path may specify a subdirectory
        """
        path_in_zip = os.path.join(self.NOM_EXPORT_ZIP, path, filename)
        self.zipfile.writestr(path_in_zip, data)

    # ------------------------------------------------------------------------------------------------------------------
    def get_zipped_data(self):
        """returns file-like data with a zip of all generated (CSV) files.
        Reset file cursor at the beginning !
        """
        if self.zipfile:
            self.zipfile.close()
            self.zipfile = None
        self.zipdata.seek(0)
        return self.zipdata

    # **************************************************************************************************************** #
    # Lancement des différentes actions permettant le calcul du jury PE
    # **************************************************************************************************************** #
    def exe_calculs_juryPE(self, semBase):
        # Liste des étudiants à traiter pour identifier ceux qui seront diplômés
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print(
                "*** Recherche et chargement des étudiants diplômés en %d"
                % (self.diplome)
            )
        self.get_etudiants_in_jury(
            semBase, avec_meme_formation=False
        )  # calcul des coSemestres

        # Les semestres impliqués (ceux valides pour les étudiants à traiter)
        # -------------------------------------------------------------------
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print("*** Création des semestres taggués")
        self.get_semtags_in_jury()
        if pe_tools.PE_DEBUG:
            for semtag in self.semTagDict.values():  # Export
                filename = self.NOM_EXPORT_ZIP + semtag.nom + ".csv"
                self.zipfile.writestr(filename, semtag.str_tagtable())
        # self.export_juryPEDict()

        # Les moyennes sur toute la scolarité
        # -----------------------------------
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print(
                "*** Création des moyennes sur différentes combinaisons de semestres et différents groupes d'étudiant"
            )
        self.get_settags_in_jury()
        if pe_tools.PE_DEBUG:
            for settagdict in self.setTagDict.values():  # Export
                for settag in settagdict.values():
                    filename = self.NOM_EXPORT_ZIP + semtag.nom + ".csv"
                    self.zipfile.writestr(filename, semtag.str_tagtable())
        # self.export_juryPEDict()

        # Les interclassements
        # --------------------
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print(
                "*** Création des interclassements au sein de la promo sur différentes combinaisons de semestres"
            )
        self.get_promotags_in_jury()

    # **************************************************************************************************************** #
    # Fonctions relatives à la liste des étudiants à prendre en compte dans le jury
    # **************************************************************************************************************** #

    # ------------------------------------------------------------------------------------------------------------------
    def get_etudiants_in_jury(self, semBase, avec_meme_formation=False):
        """
        Calcule la liste des étudiants à prendre en compte dans le jury et la renvoie sous la forme
        """
        # Les cosemestres donnant lieu à meme année de diplome
        coSems = get_cosemestres_diplomants(
            semBase, avec_meme_formation=avec_meme_formation
        )  # calcul des coSemestres
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print(
                "1) Recherche des coSemestres -> %d trouvés" % len(coSems)
            )

        # Les étudiants inscrits dans les cosemestres
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print("2) Liste des étudiants dans les différents co-semestres")
        listEtudId = self.get_etudiants_dans_semestres(
            coSems
        )  #  étudiants faisant parti des cosemestres
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print(" => %d étudiants trouvés" % len(listEtudId))

        # L'analyse des parcours étudiants pour déterminer leur année effective de diplome avec prise en compte des redoublements, des abandons, ....
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print("3) Analyse des parcours individuels des étudiants")

        for (no_etud, etudid) in enumerate(listEtudId):
            self.add_etudiants(etudid)
            if pe_tools.PE_DEBUG:
                if (no_etud + 1) % 10 == 0:
                    pe_tools.pe_print((no_etud + 1), " ", end="")
        pe_tools.pe_print()

        if pe_tools.PE_DEBUG:
            pe_tools.pe_print(
                "  => %d étudiants à diplômer en %d"
                % (len(self.get_etudids_du_jury()), self.diplome)
            )
            pe_tools.pe_print(
                "  => %d étudiants éliminer pour abandon"
                % (len(listEtudId) - len(self.get_etudids_du_jury()))
            )

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def get_etudiants_dans_semestres(self, semsListe):
        """Renvoie la liste des etudid des etudiants inscrits à l'un des semestres de la liste fournie en paramètre
        en supprimant les doublons (i.e. un même étudiant qui apparaîtra 2 fois)"""

        etudiants = []
        for sem in semsListe:  # pour chacun des semestres de la liste

            # nt = self.get_notes_d_un_semestre( sem['formsemestre_id'] )
            nt = self.get_cache_notes_d_un_semestre(sem["formsemestre_id"])
            # sco_cache.NotesTableCache.get( sem['formsemestre_id'])
            etudiantsDuSemestre = (
                nt.get_etudids()
            )  # nt.identdict.keys() # identification des etudiants du semestre

            if pe_tools.PE_DEBUG:
                pe_tools.pe_print(
                    "  --> chargement du semestre %s : %d etudiants "
                    % (sem["formsemestre_id"], len(etudiantsDuSemestre))
                )
            etudiants.extend(etudiantsDuSemestre)

        return list(set(etudiants))  # suppression des doublons

    # ------------------------------------------------------------------------------------------------------------------
    def get_etudids_du_jury(self, ordre="aucun"):
        """Renvoie la liste de tous les étudiants (concrètement leur etudid)
        participant au jury c'est à dire, ceux dont la date du 'jury' est self.diplome
        et n'ayant pas abandonné.
        Si l'ordre est précisé, donne une liste etudid dont le nom, prenom trié par ordre alphabétique
        """
        etudids = [
            etudid
            for (etudid, donnees) in self.PARCOURSINFO_DICT.items()
            if donnees["diplome"] == self.diplome and donnees["abandon"] == False
        ]
        if ordre == "alphabetique":  # Tri alphabétique
            etudidsAvecNom = [
                (etudid, etud["nom"] + "/" + etud["prenom"])
                for (etudid, etud) in self.PARCOURSINFO_DICT.items()
                if etudid in etudids
            ]
            etudidsAvecNomTrie = sorted(etudidsAvecNom, key=lambda col: col[1])
            etudids = [etud[0] for etud in etudidsAvecNomTrie]
        return etudids

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def add_etudiants(self, etudid):
        """Ajoute un étudiant (via son etudid) au dictionnaire de synthèse jurydict.
        L'ajout consiste à :
        > insérer une entrée pour l'étudiant en mémorisant ses infos (get_etudInfo),
        avec son nom, prénom, etc...
        > à analyser son parcours, pour vérifier s'il n'a pas abandonné l'IUT en cours de route => clé abandon
        > à chercher ses semestres valides (formsemestre_id) et ses années valides (formannee_id),
        c'est à dire ceux pour lesquels il faudra prendre en compte ses notes dans les calculs de moyenne (type 1A=S1+S2/2)
        """

        if etudid not in self.PARCOURSINFO_DICT:
            etud = self.get_cache_etudInfo_d_un_etudiant(
                etudid
            )  # On charge les données de l'étudiant
            if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
                pe_tools.pe_print(etud["nom"] + " " + etud["prenom"], end="")

            self.PARCOURSINFO_DICT[etudid] = {
                "etudid": etudid,  # les infos sur l'étudiant
                "nom": etud["nom"],  # Ajout à la table jury
            }

            # Analyse du parcours de l'étudiant

            # Sa date prévisionnelle de diplome
            self.PARCOURSINFO_DICT[etudid][
                "diplome"
            ] = self.calcul_anneePromoDUT_d_un_etudiant(etudid)
            if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
                pe_tools.pe_print(
                    "promo=" + str(self.PARCOURSINFO_DICT[etudid]["diplome"]), end=""
                )

            # Est-il réorienté ou démissionnaire ?
            self.PARCOURSINFO_DICT[etudid][
                "abandon"
            ] = self.est_un_etudiant_reoriente_ou_demissionnaire(etudid)

            # A-t-il arrêté de lui-même sa formation avant la fin ?
            etatD = self.est_un_etudiant_disparu(etudid)
            if etatD == True:
                self.PARCOURSINFO_DICT[etudid]["abandon"] = True
            # dans le jury ne seront traités que les étudiants ayant la date attendue de diplome et n'ayant pas abandonné

            # Quels sont ses semestres validant (i.e ceux dont les notes doivent être prises en compte pour le jury)
            # et s'ils existent quelles sont ses notes utiles ?
            sesFormsemestre_idValidants = [
                self.get_Fid_d_un_Si_valide_d_un_etudiant(etudid, nom_sem)
                for nom_sem in JuryPE.PARCOURS["4S"][
                    "aggregat"
                ]  # Recherche du formsemestre_id de son Si valide (ou a défaut en cours)
            ]
            for (i, nom_sem) in enumerate(JuryPE.PARCOURS["4S"]["aggregat"]):
                fid = sesFormsemestre_idValidants[i]
                self.PARCOURSINFO_DICT[etudid][nom_sem] = fid  # ['formsemestre_id']
                if fid != None and pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
                    pe_tools.pe_print(nom_sem + "=" + str(fid), end="")
                    # self.get_moyennesEtClassements_par_semestre_d_un_etudiant( etudid, fid )

            # Quelles sont ses années validantes ('1A', '2A') et ses parcours (3S, 4S) validants ?
            for parcours in ["1A", "2A", "3S", "4S"]:
                lesSemsDuParcours = JuryPE.PARCOURS[parcours][
                    "aggregat"
                ]  # les semestres du parcours : par ex. ['S1', 'S2', 'S3']
                lesFidsValidantDuParcours = [
                    sesFormsemestre_idValidants[
                        JuryPE.PARCOURS["4S"]["aggregat"].index(nom_sem)
                    ]
                    for nom_sem in lesSemsDuParcours  # par ex. ['SEM4532', 'SEM567', ...]
                ]
                parcours_incomplet = (
                    sum([fid == None for fid in lesFidsValidantDuParcours]) > 0
                )

                if not parcours_incomplet:
                    self.PARCOURSINFO_DICT[etudid][
                        parcours
                    ] = lesFidsValidantDuParcours[-1]
                else:
                    self.PARCOURSINFO_DICT[etudid][parcours] = None
                if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
                    pe_tools.pe_print(
                        parcours + "=" + str(self.PARCOURSINFO_DICT[etudid][parcours]),
                        end="",
                    )

            # if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
            #    print

    # ------------------------------------------------------------------------------------------------------------------
    def est_un_etudiant_reoriente_ou_demissionnaire(self, etudid):
        """Renvoie True si l'étudiant est réorienté (NAR) ou démissionnaire (DEM)"""
        from app.scodoc import sco_report

        reponse = False
        etud = self.get_cache_etudInfo_d_un_etudiant(etudid)
        (_, parcours) = sco_report.get_codeparcoursetud(etud)
        if (
            len(set(sco_codes_parcours.CODES_SEM_REO.keys()) & set(parcours.values()))
            > 0
        ):  # Eliminé car NAR apparait dans le parcours
            reponse = True
            if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
                pe_tools.pe_print("  -> à éliminer car réorienté (NAR)")
        if "DEM" in list(parcours.values()):  # Eliminé car DEM
            reponse = True
            if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 2:
                pe_tools.pe_print("  -> à éliminer car DEM")
        return reponse

    # ------------------------------------------------------------------------------------------------------------------
    def est_un_etudiant_disparu(self, etudid):
        """Renvoie True si l'étudiant n'a pas achevé la formation à l'IUT et a disparu des listes, sans
        pour autant avoir été indiqué NAR ou DEM ; recherche son dernier semestre validé et regarde s'il
        n'existe pas parmi les semestres existants dans scodoc un semestre postérieur (en terme de date de
        début) de n° au moins égal à celui de son dernier semestre valide dans lequel il aurait pu
        s'inscrire mais ne l'a pas fait."""
        sessems = self.get_semestresDUT_d_un_etudiant(
            etudid
        )  # les semestres de l'étudiant
        sonDernierSidValide = self.get_dernier_semestre_id_valide_d_un_etudiant(etudid)

        sesdates = [
            pe_tagtable.conversionDate_StrToDate(sem["date_fin"]) for sem in sessems
        ]  # association 1 date -> 1 semestrePE pour les semestres de l'étudiant
        lastdate = max(sesdates)  # date de fin de l'inscription la plus récente

        # if PETable.AFFICHAGE_DEBUG_PE == True : pe_tools.pe_print("     derniere inscription = ", lastDateSem)
        semestresDeScoDoc = sco_formsemestre.do_formsemestre_list()
        if sonDernierSidValide is None:
            # si l'étudiant n'a validé aucun semestre, les prend tous ? (à vérifier)
            semestresSuperieurs = semestresDeScoDoc
        else:
            semestresSuperieurs = [
                sem
                for sem in semestresDeScoDoc
                if sem["semestre_id"] > sonDernierSidValide
            ]  # Semestre de rang plus élevé que son dernier sem valide
        datesDesSemestresSuperieurs = [
            pe_tagtable.conversionDate_StrToDate(sem["date_debut"])
            for sem in semestresSuperieurs
        ]
        datesDesSemestresPossibles = [
            date_deb for date_deb in datesDesSemestresSuperieurs if date_deb >= lastdate
        ]  # date de debut des semestres possibles postérieur au dernier semestre de l'étudiant et de niveau plus élevé que le dernier semestre valide de l'étudiant
        if (
            len(datesDesSemestresPossibles) > 0
        ):  # etudiant ayant disparu de la circulation
            #            if PETable.AFFICHAGE_DEBUG_PE == True :
            #                pe_tools.pe_print("  -> à éliminer car des semestres où il aurait pu s'inscrire existent ")
            #                pe_tools.pe_print(pe_tools.print_semestres_description( datesDesSemestresPossibles.values() ))
            return True
        else:
            return False

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def get_dernier_semestre_id_valide_d_un_etudiant(self, etudid):
        """Renvoie le n° (semestre_id) du dernier semestre validé par un étudiant fourni par son etudid
        et None si aucun semestre n'a été validé
        """
        from app.scodoc import sco_report

        etud = self.get_cache_etudInfo_d_un_etudiant(etudid)
        (code, parcours) = sco_report.get_codeparcoursetud(
            etud
        )  # description = '1234:A', parcours = {1:ADM, 2:NAR, ...}
        sonDernierSemestreValide = max(
            [
                int(cle)
                for (cle, code) in parcours.items()
                if code in sco_codes_parcours.CODES_SEM_VALIDES
            ]
            + [0]
        )  # n° du dernier semestre valide, 0 sinon
        return sonDernierSemestreValide if sonDernierSemestreValide > 0 else None

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def get_Fid_d_un_Si_valide_d_un_etudiant(self, etudid, nom_semestre):
        """Récupère le formsemestre_id valide d'un étudiant fourni son etudid à un semestre DUT de n° semestre_id
        donné. Si le semestre est en cours (pas encore de jury), renvoie le formsemestre_id actuel."""
        semestre_id = JuryPE.PARCOURS["4S"]["aggregat"].index(nom_semestre) + 1
        sesSi = self.get_semestresDUT_d_un_etudiant(
            etudid, semestre_id
        )  # extrait uniquement les Si par ordre temporel décroissant

        if len(sesSi) > 0:  # S'il a obtenu au moins une note
            # mT = sesMoyennes[0]
            leFid = sesSi[0]["formsemestre_id"]
            for (i, sem) in enumerate(
                sesSi
            ):  # Parcours des éventuels semestres précédents
                nt = self.get_cache_notes_d_un_semestre(sem["formsemestre_id"])
                dec = nt.get_etud_decision_sem(
                    etudid
                )  # quelle est la décision du jury ?
                if dec and dec["code"] in list(
                    sco_codes_parcours.CODES_SEM_VALIDES.keys()
                ):  # isinstance( sesMoyennes[i+1], float) and
                    # mT = sesMoyennes[i+1] # substitue la moyenne si le semestre suivant est "valide"
                    leFid = sem["formsemestre_id"]
        else:
            leFid = None
        return leFid

    # **************************************************************************************************************** #
    # Traitements des semestres impliqués dans le jury
    # **************************************************************************************************************** #

    # ------------------------------------------------------------------------------------------------------------------
    def get_semtags_in_jury(self):
        """
        Créé les semestres tagués relatifs aux résultats des étudiants à prendre en compte dans le jury.
        Calcule les moyennes et les classements de chaque semestre par tag et les statistiques de ces semestres.
        """
        lesFids = self.get_formsemestreids_du_jury(
            self.get_etudids_du_jury(), liste_semestres=["S1", "S2", "S3", "S4"]
        )
        for (i, fid) in enumerate(lesFids):
            if pe_tools.PE_DEBUG:
                pe_tools.pe_print(
                    u"%d) Semestre taggué %s (avec classement dans groupe)"
                    % (i + 1, fid)
                )
            self.add_semtags_in_jury(fid)

    # ------------------------------------------------------------------------------------------------------------------
    def add_semtags_in_jury(self, fid):
        """Crée si nécessaire un semtag et le mémorise dans self.semTag ;
        charge également les données des nouveaux étudiants qui en font partis.
        """
        # Semestre taggué avec classement dans le groupe
        if fid not in self.semTagDict:
            nt = self.get_cache_notes_d_un_semestre(fid)

            # Création du semestres
            self.semTagDict[fid] = pe_semestretag.SemestreTag(
                nt, nt.sem
            )  # Création du pesemestre associé
            self.semTagDict[fid].comp_data_semtag()
            lesEtudids = self.semTagDict[fid].get_etudids()

            lesEtudidsManquants = []
            for etudid in lesEtudids:
                if (
                    etudid not in self.PARCOURSINFO_DICT
                ):  # Si l'étudiant n'a pas été pris en compte dans le jury car déjà diplômé ou redoublant
                    lesEtudidsManquants.append(etudid)
                    # self.get_cache_etudInfo_d_un_etudiant(etudid)
                    self.add_etudiants(
                        etudid
                    )  # Ajoute les élements de parcours de l'étudiant

            nbinscrit = self.semTagDict[fid].get_nbinscrits()
            if pe_tools.PE_DEBUG:
                pe_tools.pe_print(
                    u"   - %d étudiants classés " % (nbinscrit)
                    + ": "
                    + ",".join(
                        [etudid for etudid in self.semTagDict[fid].get_etudids()]
                    )
                )
                if lesEtudidsManquants:
                    pe_tools.pe_print(
                        u"   - dont %d étudiants manquants ajoutés aux données du jury"
                        % (len(lesEtudidsManquants))
                        + ": "
                        + ", ".join(lesEtudidsManquants)
                    )
                pe_tools.pe_print(u"    - Export csv")
                filename = self.NOM_EXPORT_ZIP + self.semTagDict[fid].nom + ".csv"
                self.zipfile.writestr(filename, self.semTagDict[fid].str_tagtable())

    # ----------------------------------------------------------------------------------------------------------------
    def get_formsemestreids_du_jury(self, etudids, liste_semestres="4S"):
        """Renvoie la liste des formsemestre_id validants des étudiants en parcourant les semestres valides des étudiants mémorisés dans
        self.PARCOURSINFO_DICT.
        Les étudiants sont identifiés par leur etudic donnés dans la liste etudids (généralement self.get_etudids_in_jury() ).
        La liste_semestres peut être une liste ou une chaine de caractères parmi :
            * None => tous les Fids validant
            * 'Si' => le ième 1 semestre
            * 'iA' => l'année i = ['S1, 'S2'] ou ['S3', 'S4']
            * '3S', '4S' => fusion des semestres
            * [ 'Si', 'iA' , ... ] => une liste combinant les formats précédents
        """
        champs_possibles = list(JuryPE.PARCOURS.keys())
        if (
            not isinstance(liste_semestres, list)
            and not isinstance(liste_semestres, str)
            and liste_semestres not in champs_possibles
        ):
            raise ValueError(
                "Probleme de paramètres d'appel dans pe_jurype.JuryPE.get_formsemestreids_du_jury"
            )

        if isinstance(liste_semestres, list):
            res = []
            for elmt in liste_semestres:
                res.extend(self.get_formsemestreids_du_jury(etudids, elmt))
            return list(set(res))

        # si liste_sem est un nom de parcours
        nom_sem = liste_semestres
        # if nom_sem in ['1A', '2A', '3S', '4S'] :
        #     return self.get_formsemestreids_du_jury(etudids, JuryPE.PARCOURS[nom_sem] )
        # else :
        fids = {
            self.PARCOURSINFO_DICT[etudid][nom_sem]
            for etudid in etudids
            if self.PARCOURSINFO_DICT[etudid][nom_sem] != None
        }

        return list(fids)

    # **************************************************************************************************************** #
    # Traitements des parcours impliquées dans le jury
    # **************************************************************************************************************** #

    # # ----------------------------------------------------------------------------------------------------------------
    # def get_antags_in_jury(self, avec_affichage_debug=True ):
    #     """Construit les settag associés aux années 1A et 2A du jury"""
    #     lesAnnees = {'1A' : ['S1', 'S2'], '2A' : ['S3', 'S4'] }
    #     for nom_annee in lesAnnees:
    #         lesAidDesAnnees = self.get_anneeids_du_jury(annee= nom_annee) # les annee_ids des étudiants du jury
    #         for aid in lesAidDesAnnees:
    #             fidSemTagFinal = JuryPE.convert_aid_en_fid( aid )
    #             lesEtudisDelAnnee = self.semTagDict[ fidSemTagFinal ].get_etudids() # les etudiants sont ceux inscrits dans le semestre final de l'année
    #             parcoursDesEtudiants = { etudid : self.PARCOURSINFO_DICT[etudid] for etudid in lesEtudisDelAnnee } # les parcours des etudid aka quels semestres sont à prendre en compte
    #
    #             lesFidsDesEtudiants = self.get_formsemestreids_du_jury(lesEtudisDelAnnee, nom_annee) # les formsemestres_id à prendre en compte pour les moyennes
    #             # Manque-t-il des semtag associés ; si oui, les créé
    #             pe_tools.pe_print(aid, lesFidsDesEtudiants)
    #             for fid in lesFidsDesEtudiants:
    #                 self.add_semtags_in_jury(fid, avec_affichage_debug=avec_affichage_debug)
    #             lesSemTagDesEtudiants = { fid: self.semTagDict[fid] for fid in lesFidsDesEtudiants }
    #
    #             # Tous les semtag nécessaires pour ses étudiants avec ajout éventuel s'ils n'ont pas été chargés
    #             pe_tools.pe_print(" -> Création de l'année tagguée " + str( aid ))
    #             #settag_id, short_name, listeEtudId, groupe, listeSemAAggreger, ParcoursEtudDict, SemTagDict, with_comp_moy=True)
    #             self.anTagDict[ aid ] = pe_settag.SetTag( aid, "Annee " + self.semTagDict[fidSemTagFinal].short_name, \
    #                                                         lesEtudisDelAnnee, 'groupe', lesAnnees[ nom_annee ], parcoursDesEtudiants, lesSemTagDesEtudiants )
    #             self.anTagDict[ aid ].comp_data_settag() # calcul les moyennes

    # **************************************************************************************************************** #
    # Traitements des moyennes sur différentes combinaisons de parcours 1A, 2A, 3S et 4S,
    # impliquées dans le jury
    # **************************************************************************************************************** #

    def get_settags_in_jury(self):
        """Calcule les moyennes sur la totalité du parcours (S1 jusqu'à S3 ou S4)
        en classant les étudiants au sein du semestre final du parcours (même S3, même S4, ...)"""

        # Par groupe :
        # combinaisons = { 'S1' : ['S1'], 'S2' : ['S2'], 'S3' : ['S3'], 'S4' : ['S4'], \
        #                  '1A' : ['S1', 'S2'], '2A' : ['S3', 'S4'],
        #                  '3S' : ['S1', 'S2', 'S3'], '4S' : ['S1', 'S2', 'S3', 'S4'] }

        # ---> sur 2 parcours DUT (cas S3 fini, cas S4 fini)
        combinaisons = ["1A", "2A", "3S", "4S"]
        for (i, nom) in enumerate(combinaisons):
            parcours = JuryPE.PARCOURS[nom][
                "aggregat"
            ]  # La liste des noms de semestres (S1, S2, ...) impliqués dans l'aggrégat

            # Recherche des parcours possibles par le biais de leur Fid final
            fids_finaux = self.get_formsemestreids_du_jury(
                self.get_etudids_du_jury(), nom
            )  # les formsemestre_ids validant finaux des étudiants du jury

            if len(fids_finaux) > 0:  # S'il existe des parcours validant
                if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 1:
                    pe_tools.pe_print("%d) Fusion %s avec" % (i + 1, nom))

                if nom not in self.setTagDict:
                    self.setTagDict[nom] = {}

                for fid in fids_finaux:
                    if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 1:
                        pe_tools.pe_print(u"   - semestre final %s" % (fid))
                    settag = pe_settag.SetTag(
                        nom, parcours=parcours
                    )  # Le set tag fusionnant les données
                    etudiants = self.semTagDict[
                        fid
                    ].get_etudids()  # Les étudiants du sem final

                    # ajoute les étudiants au semestre
                    settag.set_Etudiants(
                        etudiants,
                        self.PARCOURSINFO_DICT,
                        self.ETUDINFO_DICT,
                        nom_sem_final=self.semTagDict[fid].nom,
                    )

                    # manque-t-il des semestres ? Si oui, les ajoute au jurype puis au settag
                    for ffid in settag.get_Fids_in_settag():
                        if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 1:
                            pe_tools.pe_print(
                                u"      -> ajout du semestre tagué %s" % (ffid)
                            )
                        self.add_semtags_in_jury(ffid)
                    settag.set_SemTagDict(
                        self.semTagDict
                    )  # ajoute les semestres au settag

                    settag.comp_data_settag()  # Calcul les moyennes, les rangs, ..

                    self.setTagDict[nom][fid] = settag  # Mémorise le résultat

            else:
                if pe_tools.PE_DEBUG and pe_tools.PE_DEBUG >= 1:
                    pe_tools.pe_print("%d) Pas de fusion %s possible" % (i + 1, nom))

    def get_promotags_in_jury(self):
        """Calcule les aggrégats en interclassant les étudiants du jury (les moyennes ont déjà été calculées en amont)"""

        lesEtudids = self.get_etudids_du_jury()

        for (i, nom) in enumerate(JuryPE.PARCOURS.keys()):

            settag = pe_settag.SetTagInterClasse(nom, diplome=self.diplome)
            nbreEtudInscrits = settag.set_Etudiants(
                lesEtudids, self.PARCOURSINFO_DICT, self.ETUDINFO_DICT
            )
            if nbreEtudInscrits > 0:
                if pe_tools.PE_DEBUG:
                    pe_tools.pe_print(
                        u"%d) %s avec interclassement sur la promo" % (i + 1, nom)
                    )
                if nom in ["S1", "S2", "S3", "S4"]:
                    settag.set_SetTagDict(self.semTagDict)
                else:  # cas des aggrégats
                    settag.set_SetTagDict(self.setTagDict[nom])
                settag.comp_data_settag()
                self.promoTagDict[nom] = settag
            else:
                if pe_tools.PE_DEBUG:
                    pe_tools.pe_print(
                        u"%d) Pas d'interclassement %s sur la promo faute de notes"
                        % (i + 1, nom)
                    )

    # **************************************************************************************************************** #
    # Méthodes pour la synthèse du juryPE
    # *****************************************************************************************************************
    def synthetise_juryPE(self):
        """Synthétise tous les résultats du jury PE dans un dictionnaire"""
        self.syntheseJury = {}
        for etudid in self.get_etudids_du_jury():
            etudinfo = self.ETUDINFO_DICT[etudid]
            self.syntheseJury[etudid] = {
                "nom": etudinfo["nom"],
                "prenom": etudinfo["prenom"],
                "civilite": etudinfo["civilite"],
                "civilite_str": etudinfo["civilite_str"],
                "age": str(pe_tools.calcul_age(etudinfo["date_naissance"])),
                "lycee": etudinfo["nomlycee"]
                + (
                    " (" + etudinfo["villelycee"] + ")"
                    if etudinfo["villelycee"] != ""
                    else ""
                ),
                "bac": etudinfo["bac"],
                "nip": etudinfo["code_nip"],  # pour la photo
                "entree": self.get_dateEntree(etudid),
                "promo": self.diplome,
            }
            # Le parcours
            self.syntheseJury[etudid]["parcours"] = self.get_parcoursIUT(
                etudid
            )  # liste des semestres
            self.syntheseJury[etudid]["nbSemestres"] = len(
                self.syntheseJury[etudid]["parcours"]
            )  # nombre de semestres

            # Ses résultats
            for nom in JuryPE.PARCOURS:  # S1, puis S2, puis 1A
                # dans le groupe : la table tagguée dans les semtag ou les settag si aggrégat
                self.syntheseJury[etudid][nom] = {"groupe": {}, "promo": {}}
                if (
                    self.PARCOURSINFO_DICT[etudid][nom] != None
                ):  # Un parcours valide existe
                    if nom in ["S1", "S2", "S3", "S4"]:
                        tagtable = self.semTagDict[self.PARCOURSINFO_DICT[etudid][nom]]
                    else:
                        tagtable = self.setTagDict[nom][
                            self.PARCOURSINFO_DICT[etudid][nom]
                        ]
                    for tag in tagtable.get_all_tags():
                        self.syntheseJury[etudid][nom]["groupe"][
                            tag
                        ] = tagtable.get_resultatsEtud(
                            tag, etudid
                        )  # Le tuple des résultats

                    # interclassé dans la promo
                    tagtable = self.promoTagDict[nom]
                    for tag in tagtable.get_all_tags():
                        self.syntheseJury[etudid][nom]["promo"][
                            tag
                        ] = tagtable.get_resultatsEtud(tag, etudid)

    def get_dateEntree(self, etudid):
        """Renvoie l'année d'entrée de l'étudiant à l'IUT"""
        # etudinfo = self.ETUDINFO_DICT[etudid]
        semDeb = self.get_semestresDUT_d_un_etudiant(etudid)[-1]  # le 1er sem à l'IUT
        return semDeb["annee_debut"]

    def get_parcoursIUT(self, etudid):
        """Renvoie une liste d'infos sur les semestres du parcours d'un étudiant"""
        # etudinfo = self.ETUDINFO_DICT[etudid]
        sems = self.get_semestresDUT_d_un_etudiant(etudid)

        infos = []
        for sem in sems:
            nomsem = comp_nom_semestre_dans_parcours(sem)
            infos.append(
                {
                    "nom_semestre_dans_parcours": nomsem,
                    "titreannee": sem["titreannee"],
                    "formsemestre_id": sem["formsemestre_id"],  # utile dans le futur ?
                }
            )
        return infos

    # **************************************************************************************************************** #
    # Méthodes d'affichage pour debug
    # **************************************************************************************************************** #
    def str_etudiants_in_jury(self, delim=";"):

        # En tete:
        entete = ["Id", "Nom", "Abandon", "Diplome"]
        for nom_sem in ["S1", "S2", "S3", "S4", "1A", "2A", "3S", "4S"]:
            entete += [nom_sem, "descr"]
        chaine = delim.join(entete) + "\n"

        for etudid in self.PARCOURSINFO_DICT:

            donnees = self.PARCOURSINFO_DICT[etudid]
            # pe_tools.pe_print(etudid, donnees)
            # les infos générales
            descr = [
                etudid,
                donnees["nom"],
                str(donnees["abandon"]),
                str(donnees["diplome"]),
            ]

            # les semestres
            for nom_sem in ["S1", "S2", "S3", "S4", "1A", "2A", "3S", "4S"]:
                table = (
                    self.semTagDict[donnees[nom_sem]].nom
                    if donnees[nom_sem] in self.semTagDict
                    else "manquant"
                )
                descr += [
                    donnees[nom_sem] if donnees[nom_sem] != None else "manquant",
                    table,
                ]

            chaine += delim.join(descr) + "\n"
        return chaine

    #
    def export_juryPEDict(self):
        """Export csv de self.PARCOURSINFO_DICT"""
        fichier = "juryParcoursDict_" + str(self.diplome)
        pe_tools.pe_print(" -> Export de " + fichier)
        filename = self.NOM_EXPORT_ZIP + fichier + ".csv"
        self.zipfile.writestr(filename, self.str_etudiants_in_jury())

    def get_allTagForAggregat(self, nom_aggregat):
        """Extrait du dictionnaire syntheseJury la liste des tags d'un semestre ou
        d'un aggrégat donné par son nom (S1, S2, S3 ou S4, 1A, ...). Renvoie [] si aucun tag."""
        taglist = set()
        for etudid in self.get_etudids_du_jury():
            taglist = taglist.union(
                set(self.syntheseJury[etudid][nom_aggregat]["groupe"].keys())
            )
            taglist = taglist.union(
                set(self.syntheseJury[etudid][nom_aggregat]["promo"].keys())
            )
        return list(taglist)

    def get_allTagInSyntheseJury(self):
        """Extrait tous les tags du dictionnaire syntheseJury trié par ordre alphabétique. [] si aucun tag"""
        allTags = set()
        for nom in JuryPE.PARCOURS.keys():
            allTags = allTags.union(set(self.get_allTagForAggregat(nom)))
        return sorted(list(allTags)) if len(allTags) > 0 else []

    def table_syntheseJury(self, mode="singlesheet"):  #  was str_syntheseJury
        """Table(s) du jury
        mode: singlesheet ou multiplesheet pour export excel
        """
        sT = SeqGenTable()  # le fichier excel à générer

        # Les etudids des étudiants à afficher, triés par ordre alphabétiques de nom+prénom
        donnees_tries = sorted(
            [
                (
                    etudid,
                    self.syntheseJury[etudid]["nom"]
                    + " "
                    + self.syntheseJury[etudid]["prenom"],
                )
                for etudid in self.syntheseJury.keys()
            ],
            key=lambda c: c[1],
        )
        etudids = [e[0] for e in donnees_tries]
        if not etudids:  # Si pas d'étudiants
            T = GenTable(
                columns_ids=["pas d'étudiants"],
                rows=[],
                titles={"pas d'étudiants": "pas d'étudiants"},
                html_sortable=True,
                xls_sheet_name="dut",
            )
            sT.add_genTable("dut", T)
            return sT

        # Si des étudiants
        maxParcours = max(
            [self.syntheseJury[etudid]["nbSemestres"] for etudid in etudids]
        )

        infos = ["civilite", "nom", "prenom", "age", "nbSemestres"]
        entete = ["etudid"]
        entete.extend(infos)
        entete.extend(["P%d" % i for i in range(1, maxParcours + 1)])
        champs = [
            "note",
            "class groupe",
            "class promo",
            "min/moy/max groupe",
            "min/moy/max promo",
        ]

        # Les aggrégats à afficher par ordre tel que indiqué dans le dictionnaire parcours
        aggregats = list(JuryPE.PARCOURS.keys())  # ['S1', 'S2', ..., '1A', '4S']
        aggregats = sorted(
            aggregats, key=lambda t: JuryPE.PARCOURS[t]["ordre"]
        )  # Tri des aggrégats

        if mode == "multiplesheet":
            allSheets = (
                self.get_allTagInSyntheseJury()
            )  # tous les tags de syntheseJuryDict
            allSheets = sorted(allSheets)  # Tri des tags par ordre alphabétique
            for (
                sem
            ) in aggregats:  # JuryPE.PARCOURS.keys() -> ['S1', 'S2', ..., '1A', '4S']
                entete.extend(["%s %s" % (sem, champ) for champ in champs])
        else:  # "singlesheet"
            allSheets = ["singlesheet"]
            for (
                sem
            ) in aggregats:  # JuryPE.PARCOURS.keys() -> ['S1', 'S2', ..., '1A', '4S']
                tags = self.get_allTagForAggregat(sem)
                entete.extend(
                    ["%s %s %s" % (sem, tag, champ) for tag in tags for champ in champs]
                )

        columns_ids = entete  # les id et les titres de colonnes sont ici identiques
        titles = {i: i for i in columns_ids}

        for (
            sheet
        ) in (
            allSheets
        ):  # Pour tous les sheets à générer (1 si singlesheet, autant que de tags si multiplesheet)
            rows = []
            for etudid in etudids:
                e = self.syntheseJury[etudid]
                # Les info générales:
                row = {
                    "etudid": etudid,
                    "civilite": e["civilite"],
                    "nom": e["nom"],
                    "prenom": e["prenom"],
                    "age": e["age"],
                    "nbSemestres": e["nbSemestres"],
                }
                # Les parcours: P1, P2, ...
                n = 1
                for p in e["parcours"]:
                    row["P%d" % n] = p["titreannee"]
                    n += 1
                # if self.syntheseJury[etudid]['nbSemestres'] < maxParcours:
                #    descr += delim.join( ['']*( maxParcours -self.syntheseJury[etudid]['nbSemestres']) ) + delim
                for sem in aggregats:  # JuryPE.PARCOURS.keys():
                    listeTags = (
                        self.get_allTagForAggregat(sem)
                        if mode == "singlesheet"
                        else [sheet]
                    )
                    for tag in listeTags:
                        if tag in self.syntheseJury[etudid][sem]["groupe"]:
                            resgroupe = self.syntheseJury[etudid][sem]["groupe"][
                                tag
                            ]  # tuple
                        else:
                            resgroupe = (None, None, None, None, None, None, None)
                        if tag in self.syntheseJury[etudid][sem]["promo"]:
                            respromo = self.syntheseJury[etudid][sem]["promo"][tag]
                        else:
                            respromo = (None, None, None, None, None, None, None)

                        # note = "%2.2f" % resgroupe[0] if isinstance(resgroupe[0], float) else str(resgroupe[0])
                        champ = (
                            "%s %s " % (sem, tag)
                            if mode == "singlesheet"
                            else "%s " % (sem)
                        )
                        row[champ + "note"] = scu.fmt_note(resgroupe[0])
                        row[champ + "class groupe"] = "%s / %s" % (
                            resgroupe[2],
                            resgroupe[3],
                        )
                        row[champ + "class promo"] = "%s / %s" % (
                            respromo[2],
                            respromo[3],
                        )
                        row[champ + "min/moy/max groupe"] = "%s / %s / %s" % tuple(
                            scu.fmt_note(x)
                            for x in (resgroupe[6], resgroupe[4], resgroupe[5])
                        )
                        row[champ + "min/moy/max promo"] = "%s / %s / %s" % tuple(
                            scu.fmt_note(x)
                            for x in (respromo[6], respromo[4], respromo[5])
                        )
                rows.append(row)

            T = GenTable(
                columns_ids=columns_ids,
                rows=rows,
                titles=titles,
                html_sortable=True,
                xls_sheet_name=sheet,
            )
            sT.add_genTable(sheet, T)

        if mode == "singlesheet":
            return sT.get_genTable("singlesheet")
        else:
            return sT

    # **************************************************************************************************************** #
    # Méthodes de classe pour gestion d'un cache de données accélérant les calculs / intérêt à débattre
    # **************************************************************************************************************** #

    # ------------------------------------------------------------------------------------------------------------------
    def get_cache_etudInfo_d_un_etudiant(self, etudid):
        """Renvoie les informations sur le parcours d'un étudiant soit en les relisant depuis
        ETUDINFO_DICT si mémorisée soit en les chargeant et en les mémorisant
        """
        if etudid not in self.ETUDINFO_DICT:
            self.ETUDINFO_DICT[etudid] = sco_etud.get_etud_info(
                etudid=etudid, filled=True
            )[0]
        return self.ETUDINFO_DICT[etudid]

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def get_cache_notes_d_un_semestre(self, formsemestre_id):  # inutile en realité !
        """Charge la table des notes d'un formsemestre"""
        return sco_cache.NotesTableCache.get(formsemestre_id)

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def get_semestresDUT_d_un_etudiant(self, etudid, semestre_id=None):
        """Renvoie la liste des semestres DUT d'un étudiant
        pour un semestre_id (parmi 1,2,3,4) donné
        en fonction de ses infos d'etud (cf. sco_etud.get_etud_info( etudid=etudid, filled=True)[0]),
        les semestres étant triés par ordre décroissant.
        Si semestre_id == None renvoie tous les semestres"""
        etud = self.get_cache_etudInfo_d_un_etudiant(etudid)
        if semestre_id == None:
            sesSems = [sem for sem in etud["sems"] if 1 <= sem["semestre_id"] <= 4]
        else:
            sesSems = [sem for sem in etud["sems"] if sem["semestre_id"] == semestre_id]
        return sesSems

    # **********************************************
    def calcul_anneePromoDUT_d_un_etudiant(self, etudid):
        """Calcule et renvoie la date de diplome prévue pour un étudiant fourni avec son etudid
        en fonction de sesSemestres de scolarisation"""
        sesSemestres = self.get_semestresDUT_d_un_etudiant(etudid)
        return max([get_annee_diplome_semestre(sem) for sem in sesSemestres])

    # *********************************************
    # Fonctions d'affichage pour debug
    def get_resultat_d_un_etudiant(self, etudid):
        chaine = ""
        for nom_sem in ["S1", "S2", "S3", "S4"]:
            semtagid = self.PARCOURSINFO_DICT[etudid][
                nom_sem
            ]  # le formsemestre_id du semestre taggué de l'étudiant
            semtag = self.semTagDict[semtagid]
            chaine += "Semestre " + nom_sem + str(semtagid) + "\n"
            # le détail du calcul tag par tag
            # chaine += "Détail du calcul du tag\n"
            # chaine += "-----------------------\n"
            # for tag in semtag.taglist:
            #     chaine += "Tag=" + tag + "\n"
            #     chaine += semtag.str_detail_resultat_d_un_tag(tag, etudid=etudid) + "\n"
            # le bilan des tags
            chaine += "Bilan des tags\n"
            chaine += "--------------\n"
            for tag in semtag.taglist:
                chaine += (
                    tag + ";" + semtag.str_resTag_d_un_etudiant(tag, etudid) + "\n"
                )
            chaine += "\n"
        return chaine

    def get_date_entree_etudiant(self, etudid):
        """Renvoie la date d'entree d'un étudiant"""
        return str(
            min([int(sem["annee_debut"]) for sem in self.ETUDINFO_DICT[etudid]["sems"]])
        )


# ----------------------------------------------------------------------------------------
# Fonctions

# ----------------------------------------------------------------------------------------
def get_annee_diplome_semestre(sem):
    """Pour un semestre donne, décrit par le biais du dictionnaire sem usuel :
    sem = {'formestre_id': ..., 'semestre_id': ..., 'annee_debut': ...},
    à condition qu'il soit un semestre de formation DUT,
    predit l'annee à laquelle sera remis le diplome DUT des etudiants scolarisés dans le semestre
    (en supposant qu'il n'y ait plus de redoublement) et la renvoie sous la forme d'un int.
    Hypothese : les semestres de 1ere partie d'annee universitaire (comme des S1 ou des S3) s'etalent
    sur deux annees civiles - contrairement au semestre de seconde partie d'annee universitaire (comme
    des S2 ou des S4).
    Par exemple :
        > S4 debutant en 2016 finissant en 2016 => diplome en 2016
        > S3 debutant en 2015 et finissant en 2016 => diplome en 2016
        > S3 (decale) debutant en 2015 et finissant en 2015 => diplome en 2016
    La regle de calcul utilise l'annee_fin du semestre sur le principe suivant :
    nbreSemRestant = nombre de semestres restant avant diplome
    nbreAnneeRestant = nombre d'annees restant avant diplome
    1 - delta = 0 si semestre de 1ere partie d'annee / 1 sinon
    decalage = active ou desactive un increment a prendre en compte en cas de semestre decale
    """
    if (
        1 <= sem["semestre_id"] <= 4
    ):  # Si le semestre est un semestre DUT => problème si formation DUT en 1 an ??
        nbreSemRestant = 4 - sem["semestre_id"]
        nbreAnRestant = nbreSemRestant // 2
        delta = int(sem["annee_fin"]) - int(sem["annee_debut"])
        decalage = nbreSemRestant % 2  # 0 si S4, 1 si S3, 0 si S2, 1 si S1
        increment = decalage * (1 - delta)
        return int(sem["annee_fin"]) + nbreAnRestant + increment


# ----------------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------
def get_cosemestres_diplomants(semBase, avec_meme_formation=False):
    """Partant d'un semestre de Base = {'formsemestre_id': ..., 'semestre_id': ..., 'annee_debut': ...},
    renvoie la liste de tous ses co-semestres (lui-meme inclus)
    Par co-semestre, s'entend les semestres :
    > dont l'annee predite pour la remise du diplome DUT est la meme
    > dont la formation est la même (optionnel)
    > ne prenant en compte que les etudiants sans redoublement
    """
    tousLesSems = (
        sco_formsemestre.do_formsemestre_list()
    )  # tous les semestres memorisés dans scodoc
    diplome = get_annee_diplome_semestre(semBase)

    if avec_meme_formation:  # si une formation est imposee
        nom_formation = str(semBase["formation_id"])
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print("   - avec formation imposée : ", nom_formation)
        coSems = [
            sem
            for sem in tousLesSems
            if get_annee_diplome_semestre(sem) == diplome
            and sem["formation_id"] == semBase["formation_id"]
        ]
    else:
        if pe_tools.PE_DEBUG:
            pe_tools.pe_print("   - toutes formations confondues")
        coSems = [
            sem for sem in tousLesSems if get_annee_diplome_semestre(sem) == diplome
        ]

    return coSems
