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

from app import log
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_tag_module
from app.pe import pe_tagtable


class SemestreTag(pe_tagtable.TableTag):
    """Un SemestreTag représente un tableau de notes (basé sur notesTable)
    modélisant les résultats des étudiants sous forme de moyennes par tag.

    Attributs récupérés via des NotesTables :
    - nt: le tableau de notes du semestre considéré
    - nt.inscrlist: étudiants inscrits à ce semestre, par ordre alphabétique (avec demissions)
    - nt.identdict: { etudid : ident }
    - nt._modimpls : liste des moduleimpl { ... 'module_id', ...}

    Attributs supplémentaires :
    - inscrlist/identdict: étudiants inscrits hors démissionnaires ou défaillants
    - _tagdict : Dictionnaire résumant les tags et les modules du semestre auxquels ils sont liés


    Attributs hérités de TableTag :
    - nom :
    - resultats: {tag: { etudid: (note_moy, somme_coff), ...} , ...}
    - rang
    - statistiques

    Redéfinition :
    - get_etudids() : les etudids des étudiants non défaillants ni démissionnaires
    """

    DEBUG = True

    # -----------------------------------------------------------------------------
    # Fonctions d'initialisation
    # -----------------------------------------------------------------------------
    def __init__(self, notetable, sem):  # Initialisation sur la base d'une notetable
        """Instantiation d'un objet SemestreTag à partir d'un tableau de note
        et des informations sur le semestre pour le dater
        """
        pe_tagtable.TableTag.__init__(
            self,
            nom="S%d %s %s-%s"
            % (
                sem["semestre_id"],
                "ENEPS"
                if "ENEPS" in sem["titre"]
                else "UFA"
                if "UFA" in sem["titre"]
                else "FI",
                sem["annee_debut"],
                sem["annee_fin"],
            ),
        )

        # Les attributs spécifiques
        self.nt = notetable

        # Les attributs hérités : la liste des étudiants
        self.inscrlist = [etud for etud in self.nt.inscrlist if etud["etat"] == "I"]
        self.identdict = {
            etudid: ident
            for (etudid, ident) in self.nt.identdict.items()
            if etudid in self.get_etudids()
        }  # Liste des étudiants non démissionnaires et non défaillants

        # Les modules pris en compte dans le calcul des moyennes par tag => ceux des UE standards
        self.modimpls = [
            modimpl
            for modimpl in self.nt._modimpls
            if modimpl["ue"]["type"] == sco_codes_parcours.UE_STANDARD
        ]  # la liste des modules (objet modimpl)
        # self._modimpl_ids = [modimpl['moduleimpl_id'] for modimpl in self._modimpls] # la liste de id des modules (modimpl_id)
        self.somme_coeffs = sum(
            [modimpl["module"]["coefficient"] for modimpl in self.modimpls]
        )

    # -----------------------------------------------------------------------------
    def comp_data_semtag(self):
        """Calcule tous les données numériques associées au semtag"""
        # Attributs relatifs aux tag pour les modules pris en compte
        self.tagdict = (
            self.do_tagdict()
        )  # Dictionnaire résumant les tags et les données (normalisées) des modules du semestre auxquels ils sont liés

        # Calcul des moyennes de chaque étudiant puis ajoute la moyenne au sens "DUT"
        for tag in self.tagdict:
            self.add_moyennesTag(tag, self.comp_MoyennesTag(tag, force=True))
        self.add_moyennesTag("dut", self.get_moyennes_DUT())
        self.taglist = sorted(
            list(self.tagdict.keys()) + ["dut"]
        )  # actualise la liste des tags

    # -----------------------------------------------------------------------------
    def get_etudids(self):
        """Renvoie la liste des etud_id des étudiants inscrits au semestre"""
        return [etud["etudid"] for etud in self.inscrlist]

    # -----------------------------------------------------------------------------
    def do_tagdict(self):
        """Parcourt les modimpl du semestre (instance des modules d'un programme) et synthétise leurs données sous la
        forme d'un dictionnaire reliant les tags saisis dans le programme aux
        données des modules qui les concernent, à savoir les modimpl_id, les module_id, le code du module, le coeff,
        la pondération fournie avec le tag (par défaut 1 si non indiquée).
        { tagname1 : { modimpl_id1 : { 'module_id' : ..., 'coeff' : ..., 'coeff_norm' : ..., 'ponderation' : ..., 'module_code' : ..., 'ue_xxx' : ...},
                       modimpl_id2 : ....
                     },
          tagname2 : ...
        }
        Renvoie le dictionnaire ainsi construit.

        Rq: choix fait de repérer les modules par rapport à leur modimpl_id (valable uniquement pour un semestre), car
        correspond à la majorité des calculs de moyennes pour les étudiants
        (seuls ceux qui ont capitalisé des ue auront un régime de calcul différent).
        """
        tagdict = {}

        for modimpl in self.modimpls:
            modimpl_id = modimpl["moduleimpl_id"]
            # liste des tags pour le modimpl concerné:
            tags = sco_tag_module.module_tag_list(modimpl["module_id"])

            for (
                tag
            ) in tags:  # tag de la forme "mathématiques", "théorie", "pe:0", "maths:2"
                [tagname, ponderation] = sco_tag_module.split_tagname_coeff(
                    tag
                )  # extrait un tagname et un éventuel coefficient de pondération (par defaut: 1)
                # tagname = tagname
                if tagname not in tagdict:  # Ajout d'une clé pour le tag
                    tagdict[tagname] = {}

                # Ajout du modimpl au tagname considéré
                tagdict[tagname][modimpl_id] = {
                    "module_id": modimpl["module_id"],  # les données sur le module
                    "coeff": modimpl["module"][
                        "coefficient"
                    ],  # le coeff du module dans le semestre
                    "ponderation": ponderation,  # la pondération demandée pour le tag sur le module
                    "module_code": modimpl["module"][
                        "code"
                    ],  # le code qui doit se retrouver à l'identique dans des ue capitalisee
                    "ue_id": modimpl["ue"]["ue_id"],  # les données sur l'ue
                    "ue_code": modimpl["ue"]["ue_code"],
                    "ue_acronyme": modimpl["ue"]["acronyme"],
                }
        return tagdict

    # -----------------------------------------------------------------------------
    def comp_MoyennesTag(self, tag, force=False):
        """Calcule et renvoie les "moyennes" de tous les étudiants du SemTag (non défaillants)
        à un tag donné, en prenant en compte
        tous les modimpl_id concerné par le tag, leur coeff et leur pondération.
        Force ou non le calcul de la moyenne lorsque des notes sont manquantes.
        Renvoie les informations sous la forme d'une liste  [ (moy, somme_coeff_normalise, etudid), ...]
        """
        lesMoyennes = []
        for etudid in self.get_etudids():
            (
                notes,
                coeffs_norm,
                ponderations,
            ) = self.get_listesNotesEtCoeffsTagEtudiant(
                tag, etudid
            )  # les notes associées au tag
            coeffs = comp_coeff_pond(
                coeffs_norm, ponderations
            )  # les coeff pondérés par les tags
            (moyenne, somme_coeffs) = pe_tagtable.moyenne_ponderee_terme_a_terme(
                notes, coeffs, force=force
            )
            lesMoyennes += [
                (moyenne, somme_coeffs, etudid)
            ]  # Un tuple (pour classement résumant les données)
        return lesMoyennes

    # -----------------------------------------------------------------------------
    def get_moyennes_DUT(self):
        """Lit les moyennes DUT du semestre pour tous les étudiants
        et les renvoie au même format que comp_MoyennesTag"""
        return [(self.nt.moy_gen[etudid], 1.0, etudid) for etudid in self.get_etudids()]

    # -----------------------------------------------------------------------------
    def get_noteEtCoeff_modimpl(self, modimpl_id, etudid, profondeur=2):
        """Renvoie un couple donnant la note et le coeff normalisé d'un étudiant à un module d'id modimpl_id.
        La note et le coeff sont extraits :
        1) soit des données du semestre en normalisant le coefficient par rapport à la somme des coefficients des modules du semestre,
        2) soit des données des UE précédemment capitalisées, en recherchant un module de même CODE que le modimpl_id proposé,
        le coefficient normalisé l'étant alors par rapport au total des coefficients du semestre auquel appartient l'ue capitalisée
        """
        (note, coeff_norm) = (None, None)

        modimpl = get_moduleimpl(self.nt, modimpl_id)  # Le module considéré
        if modimpl == None or profondeur < 0:
            return (None, None)

        # Y-a-t-il eu capitalisation d'UE ?
        ue_capitalisees = self.get_ue_capitalisees(
            etudid
        )  # les ue capitalisées des étudiants
        ue_capitalisees_id = [
            ue["ue_id"] for ue in ue_capitalisees
        ]  # les id des ue capitalisées

        # Si le module ne fait pas partie des UE capitalisées
        if modimpl["module"]["ue_id"] not in ue_capitalisees_id:
            note = self.nt.get_etud_mod_moy(modimpl_id, etudid)  # lecture de la note
            coeff = modimpl["module"]["coefficient"]  # le coeff
            coeff_norm = (
                coeff / self.somme_coeffs if self.somme_coeffs != 0 else 0
            )  # le coeff normalisé

        # Si le module fait partie d'une UE capitalisée
        elif len(ue_capitalisees) > 0:
            moy_ue_actuelle = get_moy_ue_from_nt(
                self.nt, etudid, modimpl_id
            )  # la moyenne actuelle
            # A quel semestre correspond l'ue capitalisée et quelles sont ses notes ?
            # fid_prec = [ ue['formsemestre_id'] for ue in ue_capitalisees if ue['ue_id'] == modimpl['module']['ue_id'] ][0]
            # semestre_id = modimpl['module']['semestre_id']
            fids_prec = [
                ue["formsemestre_id"]
                for ue in ue_capitalisees
                if ue["ue_code"] == modimpl["ue"]["ue_code"]
            ]  # and ue['semestre_id'] == semestre_id]
            if len(fids_prec) > 0:
                # => le formsemestre_id du semestre dont vient la capitalisation
                fid_prec = fids_prec[0]
                # Lecture des notes de ce semestre
                nt_prec = sco_cache.NotesTableCache.get(
                    fid_prec
                )  # le tableau de note du semestre considéré

                # Y-a-t-il un module équivalent c'est à dire correspondant au même code (le module_id n'étant pas significatif en cas de changement de PPN)
                modimpl_prec = [
                    module
                    for module in nt_prec._modimpls
                    if module["module"]["code"] == modimpl["module"]["code"]
                ]
                if len(modimpl_prec) > 0:  # si une correspondance est trouvée
                    modprec_id = modimpl_prec[0]["moduleimpl_id"]
                    moy_ue_capitalisee = get_moy_ue_from_nt(nt_prec, etudid, modprec_id)
                    if (
                        moy_ue_capitalisee is None
                    ) or moy_ue_actuelle >= moy_ue_capitalisee:  # on prend la meilleure ue
                        note = self.nt.get_etud_mod_moy(
                            modimpl_id, etudid
                        )  # lecture de la note
                        coeff = modimpl["module"]["coefficient"]  # le coeff
                        coeff_norm = (
                            coeff / self.somme_coeffs if self.somme_coeffs != 0 else 0
                        )  # le coeff normalisé
                    else:
                        semtag_prec = SemestreTag(nt_prec, nt_prec.sem)
                        (note, coeff_norm) = semtag_prec.get_noteEtCoeff_modimpl(
                            modprec_id, etudid, profondeur=profondeur - 1
                        )  # lecture de la note via le semtag associé au modimpl capitalisé

                # Sinon - pas de notes à prendre en compte
        return (note, coeff_norm)

    # -----------------------------------------------------------------------------
    def get_ue_capitalisees(self, etudid):
        """Renvoie la liste des ue_id effectivement capitalisées par un étudiant"""
        # return [ ue for ue in self.nt.ue_capitalisees[etudid] if self.nt.get_etud_ue_status(etudid,ue['ue_id'])['is_capitalized'] ]
        return self.nt.ue_capitalisees[etudid]

    # -----------------------------------------------------------------------------
    def get_listesNotesEtCoeffsTagEtudiant(self, tag, etudid):
        """Renvoie un triplet (notes, coeffs_norm, ponderations) où notes, coeff_norm et ponderation désignent trois listes
        donnant -pour un tag donné- les note, coeff et ponderation de chaque modimpl à prendre en compte dans
        le calcul de la moyenne du tag.
        Les notes et coeff_norm sont extraits grâce à SemestreTag.get_noteEtCoeff_modimpl (donc dans semestre courant ou UE capitalisée).
        Les pondérations sont celles déclarées avec le tag (cf. _tagdict)."""

        notes = []
        coeffs_norm = []
        ponderations = []
        for (moduleimpl_id, modimpl) in self.tagdict[
            tag
        ].items():  # pour chaque module du semestre relatif au tag
            (note, coeff_norm) = self.get_noteEtCoeff_modimpl(moduleimpl_id, etudid)
            if note != None:
                notes.append(note)
                coeffs_norm.append(coeff_norm)
                ponderations.append(modimpl["ponderation"])
        return (notes, coeffs_norm, ponderations)

    # -----------------------------------------------------------------------------
    # Fonctions d'affichage (et d'export csv) des données du semestre en mode debug
    # -----------------------------------------------------------------------------
    def str_detail_resultat_d_un_tag(self, tag, etudid=None, delim=";"):
        """Renvoie une chaine de caractère décrivant les résultats d'étudiants à un tag :
        rappelle les notes obtenues dans les modules à prendre en compte, les moyennes et les rangs calculés.
        Si etudid=None, tous les étudiants inscrits dans le semestre sont pris en compte. Sinon seuls les étudiants indiqués sont affichés."""
        # Entete
        chaine = delim.join(["%15s" % "nom", "etudid"]) + delim
        taglist = self.get_all_tags()
        if tag in taglist:
            for mod in self.tagdict[tag].values():
                chaine += mod["module_code"] + delim
                chaine += ("%1.1f" % mod["ponderation"]) + delim
                chaine += "coeff" + delim
            chaine += delim.join(
                ["moyenne", "rang", "nbinscrit", "somme_coeff", "somme_coeff"]
            )  # ligne 1
        chaine += "\n"

        # Différents cas de boucles sur les étudiants (de 1 à plusieurs)
        if etudid == None:
            lesEtuds = self.get_etudids()
        elif isinstance(etudid, str) and etudid in self.get_etudids():
            lesEtuds = [etudid]
        elif isinstance(etudid, list):
            lesEtuds = [eid for eid in self.get_etudids() if eid in etudid]
        else:
            lesEtuds = []

        for etudid in lesEtuds:
            descr = (
                "%15s" % self.nt.get_nom_short(etudid)[:15]
                + delim
                + str(etudid)
                + delim
            )
            if tag in taglist:
                for modimpl_id in self.tagdict[tag]:
                    (note, coeff) = self.get_noteEtCoeff_modimpl(modimpl_id, etudid)
                    descr += (
                        (
                            "%2.2f" % note
                            if note != None and isinstance(note, float)
                            else str(note)
                        )
                        + delim
                        + (
                            "%1.5f" % coeff
                            if coeff != None and isinstance(coeff, float)
                            else str(coeff)
                        )
                        + delim
                        + (
                            "%1.5f" % (coeff * self.somme_coeffs)
                            if coeff != None and isinstance(coeff, float)
                            else "???"  # str(coeff * self._sum_coeff_semestre) # voir avec Cléo
                        )
                        + delim
                    )
                moy = self.get_moy_from_resultats(tag, etudid)
                rang = self.get_rang_from_resultats(tag, etudid)
                coeff = self.get_coeff_from_resultats(tag, etudid)
                tot = (
                    coeff * self.somme_coeffs
                    if coeff != None
                    and self.somme_coeffs != None
                    and isinstance(coeff, float)
                    else None
                )
                descr += (
                    pe_tagtable.TableTag.str_moytag(
                        moy, rang, len(self.get_etudids()), delim=delim
                    )
                    + delim
                )
                descr += (
                    (
                        "%1.5f" % coeff
                        if coeff != None and isinstance(coeff, float)
                        else str(coeff)
                    )
                    + delim
                    + (
                        "%.2f" % (tot)
                        if tot != None
                        else str(coeff) + "*" + str(self.somme_coeffs)
                    )
                )
            chaine += descr
            chaine += "\n"
        return chaine

    def str_tagsModulesEtCoeffs(self):
        """Renvoie une chaine affichant la liste des tags associés au semestre, les modules qui les concernent et les coeffs de pondération.
        Plus concrêtement permet d'afficher le contenu de self._tagdict"""
        chaine = "Semestre %s d'id %d" % (self.nom, id(self)) + "\n"
        chaine += " -> somme de coeffs: " + str(self.somme_coeffs) + "\n"
        taglist = self.get_all_tags()
        for tag in taglist:
            chaine += " > " + tag + ": "
            for (modid, mod) in self.tagdict[tag].items():
                chaine += (
                    mod["module_code"]
                    + " ("
                    + str(mod["coeff"])
                    + "*"
                    + str(mod["ponderation"])
                    + ") "
                    + str(modid)
                    + ", "
                )
            chaine += "\n"
        return chaine


# ************************************************************************
# Fonctions diverses
# ************************************************************************

# *********************************************
def comp_coeff_pond(coeffs, ponderations):
    """
    Applique une ponderation (indiquée dans la liste ponderations) à une liste de coefficients :
    ex: coeff = [2, 3, 1, None], ponderation = [1, 2, 0, 1] => [2*1, 3*2, 1*0, None]
    Les coeff peuvent éventuellement être None auquel cas None est conservé ;
    Les pondérations sont des floattants
    """
    if (
        coeffs == None
        or ponderations == None
        or not isinstance(coeffs, list)
        or not isinstance(ponderations, list)
        or len(coeffs) != len(ponderations)
    ):
        raise ValueError("Erreur de paramètres dans comp_coeff_pond")
    return [
        (None if coeffs[i] == None else coeffs[i] * ponderations[i])
        for i in range(len(coeffs))
    ]


# -----------------------------------------------------------------------------
def get_moduleimpl(nt, modimpl_id):
    """Renvoie l'objet modimpl dont l'id est modimpl_id fourni dans la note table nt,
    en utilisant l'attribut nt._modimpls"""
    modimplids = [
        modimpl["moduleimpl_id"] for modimpl in nt._modimpls
    ]  # la liste de id des modules (modimpl_id)
    if modimpl_id not in modimplids:
        if SemestreTag.DEBUG:
            log(
                "SemestreTag.get_moduleimpl( %s ) : le modimpl recherche n'existe pas"
                % (modimpl_id)
            )
        return None
    return nt._modimpls[modimplids.index(modimpl_id)]


# **********************************************
def get_moy_ue_from_nt(nt, etudid, modimpl_id):
    """Renvoie la moyenne de l'UE d'un etudid dans laquelle se trouve le module de modimpl_id
    en partant du note table nt"""
    mod = get_moduleimpl(nt, modimpl_id)  # le module
    indice = 0
    while indice < len(nt._ues):
        if (
            nt._ues[indice]["ue_id"] == mod["module"]["ue_id"]
        ):  # si les ue_id correspond
            data = [
                ligne for ligne in nt.T if ligne[-1] == etudid
            ]  # les notes de l'étudiant
            if data:
                return data[0][indice + 1]  # la moyenne à l'ue
            else:
                indice += 1
        return None  # si non trouvé
