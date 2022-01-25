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

"""Calculs sur les notes et cache des resultats
"""

from operator import itemgetter

from flask import g, url_for

from app.models import ScoDocSiteConfig
import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.sco_formulas import NoteVector
from app.scodoc.sco_exceptions import ScoValueError

from app.scodoc.sco_formsemestre import (
    formsemestre_uecoef_list,
    formsemestre_uecoef_create,
)
from app.scodoc.sco_codes_parcours import (
    DEF,
    UE_SPORT,
    UE_is_fondamentale,
    UE_is_professionnelle,
)
from app.scodoc.sco_parcours_dut import formsemestre_get_etud_capitalisation
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_compute_moy
from app.scodoc import sco_cache
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_preferences
from app.scodoc import sco_etud


def comp_ranks(T):
    """Calcul rangs à partir d'une liste ordonnée de tuples [ (valeur, ..., etudid) ]
    (valeur est une note numérique), en tenant compte des ex-aequos
    Le resultat est: { etudid : rang } où rang est une chaine decrivant le rang
    """
    rangs = {}  # { etudid : rang } (rang est une chaine)
    nb_ex = 0  # nb d'ex-aequo consécutifs en cours
    for i in range(len(T)):
        # test ex-aequo
        if i < len(T) - 1:
            next = T[i + 1][0]
        else:
            next = None
        moy = T[i][0]
        if nb_ex:
            srang = "%d ex" % (i + 1 - nb_ex)
            if moy == next:
                nb_ex += 1
            else:
                nb_ex = 0
        else:
            if moy == next:
                srang = "%d ex" % (i + 1 - nb_ex)
                nb_ex = 1
            else:
                srang = "%d" % (i + 1)
        rangs[T[i][-1]] = srang  # str(i+1)
    return rangs


def get_sem_ues_modimpls(formsemestre_id, modimpls=None):
    """Get liste des UE du semestre (à partir des moduleimpls)
    (utilisé quand on ne peut pas construire nt et faire nt.get_ues())
    """
    if modimpls is None:
        modimpls = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
    uedict = {}
    for modimpl in modimpls:
        mod = sco_edit_module.module_list(args={"module_id": modimpl["module_id"]})[0]
        modimpl["module"] = mod
        if not mod["ue_id"] in uedict:
            ue = sco_edit_ue.ue_list(args={"ue_id": mod["ue_id"]})[0]
            uedict[ue["ue_id"]] = ue
    ues = list(uedict.values())
    ues.sort(key=lambda u: u["numero"])
    return ues, modimpls


def comp_etud_sum_coef_modules_ue(formsemestre_id, etudid, ue_id):
    """Somme des coefficients des modules de l'UE dans lesquels cet étudiant est inscrit
    ou None s'il n'y a aucun module.

    (nécessaire pour éviter appels récursifs de nt, qui peuvent boucler)
    """
    infos = ndb.SimpleDictFetch(
        """SELECT mod.coefficient
    FROM notes_modules mod, notes_moduleimpl mi, notes_moduleimpl_inscription ins
    WHERE mod.id = mi.module_id
    and ins.etudid = %(etudid)s
    and ins.moduleimpl_id = mi.id
    and mi.formsemestre_id = %(formsemestre_id)s
    and mod.ue_id = %(ue_id)s
    """,
        {"etudid": etudid, "formsemestre_id": formsemestre_id, "ue_id": ue_id},
    )

    if not infos:
        return None
    else:
        s = sum(x["coefficient"] for x in infos)
        return s


class NotesTable(object):
    """Une NotesTable représente un tableau de notes pour un semestre de formation.
    Les colonnes sont des modules.
    Les lignes des étudiants.
    On peut calculer les moyennes par étudiant (pondérées par les coefs)
    ou les moyennes par module.

    Attributs publics (en lecture):
    - inscrlist: étudiants inscrits à ce semestre, par ordre alphabétique (avec demissions)
    - identdict: { etudid : ident }
    - sem : le formsemestre
    get_table_moyennes_triees: [ (moy_gen, moy_ue1, moy_ue2, ... moy_ues, moy_mod1, ..., moy_modn, etudid) ]
    (où toutes les valeurs sont soit des nombres soit des chaines spéciales comme 'NA', 'NI'),
    incluant les UE de sport

    - bonus[etudid] : valeur du bonus "sport".

    Attributs privés:
    - _modmoys : { moduleimpl_id : { etudid: note_moyenne_dans_ce_module } }
    - _ues : liste des UE de ce semestre (hors capitalisees)
    - _matmoys : { matiere_id : { etudid: note moyenne dans cette matiere } }

    """

    def __init__(self, formsemestre_id):
        log(f"NotesTable( formsemestre_id={formsemestre_id} )")
        if not formsemestre_id:
            raise ValueError("invalid formsemestre_id (%s)" % formsemestre_id)
        self.formsemestre_id = formsemestre_id
        cnx = ndb.GetDBConnexion()
        self.sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        self.moduleimpl_stats = {}  # { moduleimpl_id : {stats} }
        self._uecoef = {}  # { ue_id : coef } cache coef manuels ue cap
        self._evaluations_etats = None  # liste des evaluations avec état
        self.use_ue_coefs = sco_preferences.get_preference(
            "use_ue_coefs", formsemestre_id
        )
        # si vrai, bloque calcul des moy gen. et d'UE.:
        self.block_moyennes = self.sem["block_moyennes"]
        # Infos sur les etudiants
        self.inscrlist = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            args={"formsemestre_id": formsemestre_id}
        )
        # infos identite etudiant
        # xxx sous-optimal: 1/select par etudiant -> 0.17" pour identdict sur GTR1 !
        self.identdict = {}  # { etudid : ident }
        self.inscrdict = {}  # { etudid : inscription }
        for x in self.inscrlist:
            i = sco_etud.etudident_list(cnx, {"etudid": x["etudid"]})[0]
            self.identdict[x["etudid"]] = i
            self.inscrdict[x["etudid"]] = x
            x["nomp"] = (i["nom_usuel"] or i["nom"]) + i["prenom"]  # pour tri

        # Tri les etudids par NOM
        self.inscrlist.sort(key=itemgetter("nomp"))

        # { etudid : rang dans l'ordre alphabetique }
        rangalpha = {}
        for i in range(len(self.inscrlist)):
            rangalpha[self.inscrlist[i]["etudid"]] = i

        self.bonus = scu.DictDefault(defaultvalue=0)
        # Notes dans les modules  { moduleimpl_id : { etudid: note_moyenne_dans_ce_module } }
        (
            self._modmoys,
            self._modimpls,
            self._valid_evals_per_mod,
            valid_evals,
            mods_att,
            self.expr_diagnostics,
        ) = sco_compute_moy.formsemestre_compute_modimpls_moyennes(
            self, formsemestre_id
        )
        self._mods_att = mods_att  # liste des modules avec des notes en attente
        self._matmoys = {}  # moyennes par matieres
        self._valid_evals = {}  # { evaluation_id : eval }
        for e in valid_evals:
            self._valid_evals[e["evaluation_id"]] = e  # Liste des modules et UE
        uedict = {}  # public member: { ue_id : ue }
        self.uedict = uedict  # les ues qui ont un modimpl dans ce semestre
        for modimpl in self._modimpls:
            # module has been added by formsemestre_compute_modimpls_moyennes
            mod = modimpl["module"]
            if not mod["ue_id"] in uedict:
                ue = sco_edit_ue.ue_list(args={"ue_id": mod["ue_id"]})[0]
                uedict[ue["ue_id"]] = ue
            else:
                ue = uedict[mod["ue_id"]]
            modimpl["ue"] = ue  # add ue dict to moduleimpl
            self._matmoys[mod["matiere_id"]] = {}
            mat = sco_edit_matiere.matiere_list(args={"matiere_id": mod["matiere_id"]})[
                0
            ]
            modimpl["mat"] = mat  # add matiere dict to moduleimpl
            # calcul moyennes du module et stocke dans le module
            # nb_inscrits, nb_notes, nb_abs, nb_neutre, moy, median, last_modif=

        self.formation = sco_formations.formation_list(
            args={"formation_id": self.sem["formation_id"]}
        )[0]
        self.parcours = sco_codes_parcours.get_parcours_from_code(
            self.formation["type_parcours"]
        )

        # Decisions jury et UE capitalisées
        self.comp_decisions_jury()
        self.comp_ue_capitalisees()

        # Liste des moyennes de tous, en chaines de car., triées
        self._ues = list(uedict.values())
        self._ues.sort(key=lambda u: u["numero"])

        T = []
        # XXX self.comp_ue_coefs(cnx)
        self.moy_gen = {}  # etudid : moy gen (avec UE capitalisées)
        self.moy_ue = {}  # ue_id : { etudid : moy ue } (valeur numerique)
        self.etud_moy_infos = {}  # etudid : resultats de comp_etud_moy_gen()
        valid_moy = []  # liste des valeurs valides de moyenne generale (pour min/max)
        for ue in self._ues:
            self.moy_ue[ue["ue_id"]] = {}
        self._etud_moy_ues = {}  # { etudid : { ue_id : {'moy', 'sum_coefs', ... } }

        for etudid in self.get_etudids():
            etud_moy_gen = self.comp_etud_moy_gen(etudid, cnx)
            self.etud_moy_infos[etudid] = etud_moy_gen
            ue_status = etud_moy_gen["moy_ues"]
            self._etud_moy_ues[etudid] = ue_status

            moy_gen = etud_moy_gen["moy"]
            self.moy_gen[etudid] = moy_gen
            if etud_moy_gen["sum_coefs"] > 0:
                valid_moy.append(moy_gen)

            moy_ues = []
            for ue in self._ues:
                moy_ue = ue_status[ue["ue_id"]]["moy"]
                moy_ues.append(moy_ue)
                self.moy_ue[ue["ue_id"]][etudid] = moy_ue

            t = [moy_gen] + moy_ues
            #
            is_cap = {}  # ue_id : is_capitalized
            for ue in self._ues:
                is_cap[ue["ue_id"]] = ue_status[ue["ue_id"]]["is_capitalized"]

            for modimpl in self.get_modimpls():
                val = self.get_etud_mod_moy(modimpl["moduleimpl_id"], etudid)
                if is_cap[modimpl["module"]["ue_id"]]:
                    t.append("-c-")
                else:
                    t.append(val)
            #
            t.append(etudid)
            T.append(tuple(t))
        # tri par moyennes décroissantes,
        # en laissant les demissionnaires a la fin, par ordre alphabetique
        def row_key(x):
            """clé de tri par moyennes décroissantes,
            en laissant les demissionnaires a la fin, par ordre alphabetique.
            (moy_gen, rang_alpha)
            """
            try:
                moy = -float(x[0])
            except (ValueError, TypeError):
                moy = 1000.0
            return (moy, rangalpha[x[-1]])

        T.sort(key=row_key)
        self.T = T

        if len(valid_moy):
            self.moy_min = min(valid_moy)
            self.moy_max = max(valid_moy)
        else:
            self.moy_min = self.moy_max = "NA"

        # calcul rangs (/ moyenne generale)
        self.rangs = comp_ranks(T)

        self.rangs_groupes = (
            {}
        )  # { group_id : { etudid : rang } }  (lazy, see get_etud_rang_group)
        self.group_etuds = (
            {}
        )  # { group_id : set of etudids } (lazy, see get_etud_rang_group)

        # calcul rangs dans chaque UE
        ue_rangs = (
            {}
        )  # ue_rangs[ue_id] = ({ etudid : rang }, nb_inscrits) (rang est une chaine)
        for ue in self._ues:
            ue_id = ue["ue_id"]
            val_ids = [
                (self.moy_ue[ue_id][etudid], etudid) for etudid in self.moy_ue[ue_id]
            ]
            ue_eff = len(
                [x for x in val_ids if isinstance(x[0], float)]
            )  # nombre d'étudiants avec une note dans l'UE
            val_ids.sort(key=row_key)
            ue_rangs[ue_id] = (
                comp_ranks(val_ids),
                ue_eff,
            )  # et non: len(self.moy_ue[ue_id]) qui est l'effectif de la promo
        self.ue_rangs = ue_rangs
        # ---- calcul rangs dans les modules
        self.mod_rangs = {}
        for modimpl in self._modimpls:
            vals = self._modmoys[modimpl["moduleimpl_id"]]
            val_ids = [(vals[etudid], etudid) for etudid in vals.keys()]
            val_ids.sort(key=row_key)
            self.mod_rangs[modimpl["moduleimpl_id"]] = (comp_ranks(val_ids), len(vals))
        #
        self.compute_moy_moy()
        #
        log(f"NotesTable( formsemestre_id={formsemestre_id} ) done.")

    def get_etudids(self, sorted=False):
        if sorted:
            # Tri par moy. generale décroissante
            return [x[-1] for x in self.T]
        else:
            # Tri par ordre alphabetique de NOM
            return [x["etudid"] for x in self.inscrlist]

    def get_sexnom(self, etudid):
        "M. DUPONT"
        etud = self.identdict[etudid]
        return etud["civilite_str"] + " " + (etud["nom_usuel"] or etud["nom"]).upper()

    def get_nom_short(self, etudid):
        "formatte nom d'un etud (pour table recap)"
        etud = self.identdict[etudid]
        # Attention aux caracteres multibytes pour decouper les 2 premiers:
        return (
            (etud["nom_usuel"] or etud["nom"]).upper()
            + " "
            + etud["prenom"].capitalize()[:2]
            + "."
        )

    def get_nom_long(self, etudid):
        "formatte nom d'un etud:  M. Pierre DUPONT"
        etud = self.identdict[etudid]
        return sco_etud.format_nomprenom(etud)

    def get_displayed_etud_code(self, etudid):
        'code à afficher sur les listings "anonymes"'
        return self.identdict[etudid]["code_nip"] or self.identdict[etudid]["etudid"]

    def get_etud_etat(self, etudid):
        "Etat de l'etudiant: 'I', 'D', DEF ou '' (si pas connu dans ce semestre)"
        if etudid in self.inscrdict:
            return self.inscrdict[etudid]["etat"]
        else:
            return ""

    def get_etud_etat_html(self, etudid):
        etat = self.inscrdict[etudid]["etat"]
        if etat == "I":
            return ""
        elif etat == "D":
            return ' <font color="red">(DEMISSIONNAIRE)</font> '
        elif etat == DEF:
            return ' <font color="red">(DEFAILLANT)</font> '
        else:
            return ' <font color="red">(%s)</font> ' % etat

    def get_ues(self, filter_sport=False, filter_non_inscrit=False, etudid=None):
        """liste des ue, ordonnée par numero.
        Si filter_non_inscrit, retire les UE dans lesquelles l'etudiant n'est
        inscrit à aucun module.
        Si filter_sport, retire les UE de type SPORT
        """
        if not filter_sport and not filter_non_inscrit:
            return self._ues

        if filter_sport:
            ues_src = [ue for ue in self._ues if ue["type"] != UE_SPORT]
        else:
            ues_src = self._ues
        if not filter_non_inscrit:
            return ues_src
        ues = []
        for ue in ues_src:
            if self.get_etud_ue_status(etudid, ue["ue_id"])["is_capitalized"]:
                # garde toujours les UE capitalisees
                has_note = True
            else:
                has_note = False
                # verifie que l'etud. est inscrit a au moins un module de l'UE
                # (en fait verifie qu'il a une note)
                modimpls = self.get_modimpls(ue["ue_id"])

                for modi in modimpls:
                    moy = self.get_etud_mod_moy(modi["moduleimpl_id"], etudid)
                    try:
                        float(moy)
                        has_note = True
                        break
                    except:
                        pass
            if has_note:
                ues.append(ue)
        return ues

    def get_modimpls(self, ue_id=None):
        "liste des modules pour une UE (ou toutes si ue_id==None), triés par matières."
        if ue_id is None:
            r = self._modimpls
        else:
            r = [m for m in self._modimpls if m["ue"]["ue_id"] == ue_id]
        # trie la liste par ue.numero puis mat.numero puis mod.numero
        r.sort(
            key=lambda x: (x["ue"]["numero"], x["mat"]["numero"], x["module"]["numero"])
        )
        return r

    def get_etud_eval_note(self, etudid, evaluation_id):
        "note d'un etudiant a une evaluation"
        return self._valid_evals[evaluation_id]["notes"][etudid]

    def get_evals_in_mod(self, moduleimpl_id):
        "liste des evaluations valides dans un module"
        return [
            e for e in self._valid_evals.values() if e["moduleimpl_id"] == moduleimpl_id
        ]

    def get_mod_stats(self, moduleimpl_id):
        """moyenne generale, min, max pour un module
        Ne prend en compte que les evaluations où toutes les notes sont entrées
        Cache le resultat.
        """
        if moduleimpl_id in self.moduleimpl_stats:
            return self.moduleimpl_stats[moduleimpl_id]
        nb_notes = 0
        sum_notes = 0.0
        nb_missing = 0
        moys = self._modmoys[moduleimpl_id]
        vals = []
        for etudid in self.get_etudids():
            # saute les demissionnaires et les défaillants:
            if self.inscrdict[etudid]["etat"] != "I":
                continue
            val = moys.get(etudid, None)  # None si non inscrit
            try:
                vals.append(float(val))
            except:
                nb_missing = nb_missing + 1
        sum_notes = sum(vals)
        nb_notes = len(vals)
        if nb_notes > 0:
            moy = sum_notes / nb_notes
            max_note, min_note = max(vals), min(vals)
        else:
            moy, min_note, max_note = "NA", "-", "-"
        s = {
            "moy": moy,
            "max": max_note,
            "min": min_note,
            "nb_notes": nb_notes,
            "nb_missing": nb_missing,
            "nb_valid_evals": len(self._valid_evals_per_mod[moduleimpl_id]),
        }
        self.moduleimpl_stats[moduleimpl_id] = s
        return s

    def compute_moy_moy(self):
        """precalcule les moyennes d'UE et generale (moyennes sur tous
        les etudiants), et les stocke dans self.moy_moy, self.ue['moy']

        Les moyennes d'UE ne tiennent pas compte des capitalisations.
        """
        ues = self.get_ues()
        sum_moy = 0  # la somme des moyennes générales valides
        nb_moy = 0  # le nombre de moyennes générales valides
        for ue in ues:
            ue["_notes"] = []  # liste tmp des valeurs de notes valides dans l'ue
        nb_dem = 0  # nb d'étudiants démissionnaires dans le semestre
        nb_def = 0  # nb d'étudiants défaillants dans le semestre
        T = self.get_table_moyennes_triees()
        for t in T:
            etudid = t[-1]
            # saute les demissionnaires et les défaillants:
            if self.inscrdict[etudid]["etat"] != "I":
                if self.inscrdict[etudid]["etat"] == "D":
                    nb_dem += 1
                if self.inscrdict[etudid]["etat"] == DEF:
                    nb_def += 1
                continue
            try:
                sum_moy += float(t[0])
                nb_moy += 1
            except:
                pass
            i = 0
            for ue in ues:
                i += 1
                try:
                    ue["_notes"].append(float(t[i]))
                except:
                    pass
        self.nb_demissions = nb_dem
        self.nb_defaillants = nb_def
        if nb_moy > 0:
            self.moy_moy = sum_moy / nb_moy
        else:
            self.moy_moy = "-"

        i = 0
        for ue in ues:
            i += 1
            ue["nb_moy"] = len(ue["_notes"])
            if ue["nb_moy"] > 0:
                ue["moy"] = sum(ue["_notes"]) / ue["nb_moy"]
                ue["max"] = max(ue["_notes"])
                ue["min"] = min(ue["_notes"])
            else:
                ue["moy"], ue["max"], ue["min"] = "", "", ""
            del ue["_notes"]

    def get_etud_mod_moy(self, moduleimpl_id, etudid):
        """moyenne d'un etudiant dans un module (ou NI si non inscrit)"""
        return self._modmoys[moduleimpl_id].get(etudid, "NI")

    def get_etud_mat_moy(self, matiere_id, etudid):
        """moyenne d'un étudiant dans une matière (ou NA si pas de notes)"""
        matmoy = self._matmoys.get(matiere_id, None)
        if not matmoy:
            return "NM"  # non inscrit
            # log('*** oups: get_etud_mat_moy(%s, %s)' % (matiere_id, etudid))
            # raise ValueError('matiere invalide !') # should not occur
        return matmoy.get(etudid, "NA")

    def comp_etud_moy_ue(self, etudid, ue_id=None, cnx=None):
        """Calcule moyenne gen. pour un etudiant dans une UE
        Ne prend en compte que les evaluations où toutes les notes sont entrées
        Return a dict(moy, nb_notes, nb_missing, sum_coefs)
        Si pas de notes, moy == 'NA' et sum_coefs==0
        Si non inscrit, moy == 'NI' et sum_coefs==0
        """
        assert ue_id
        modimpls = self.get_modimpls(ue_id)
        nb_notes = 0  # dans cette UE
        sum_notes = 0.0
        sum_coefs = 0.0
        nb_missing = 0  # nb de modules sans note dans cette UE

        notes_bonus_gen = []  # liste des notes de sport et culture
        coefs_bonus_gen = []

        ue_malus = 0.0  # malus à appliquer à cette moyenne d'UE

        notes = NoteVector()
        coefs = NoteVector()
        coefs_mask = NoteVector()  # 0/1, 0 si coef a ete annulé

        matiere_id_last = None
        matiere_sum_notes = matiere_sum_coefs = 0.0

        est_inscrit = False  # inscrit à l'un des modules de cette UE ?

        for modimpl in modimpls:
            # module ne faisant pas partie d'une UE capitalisee
            val = self._modmoys[modimpl["moduleimpl_id"]].get(etudid, "NI")
            # si 'NI', etudiant non inscrit a ce module
            if val != "NI":
                est_inscrit = True
            if modimpl["module"]["module_type"] == scu.MODULE_STANDARD:
                coef = modimpl["module"]["coefficient"]
                if modimpl["ue"]["type"] != UE_SPORT:
                    notes.append(val, name=modimpl["module"]["code"])
                    try:
                        sum_notes += val * coef
                        sum_coefs += coef
                        nb_notes = nb_notes + 1
                        coefs.append(coef)
                        coefs_mask.append(1)
                        matiere_id = modimpl["module"]["matiere_id"]
                        if (
                            matiere_id_last
                            and matiere_id != matiere_id_last
                            and matiere_sum_coefs
                        ):
                            self._matmoys[matiere_id_last][etudid] = (
                                matiere_sum_notes / matiere_sum_coefs
                            )
                            matiere_sum_notes = matiere_sum_coefs = 0.0
                        matiere_sum_notes += val * coef
                        matiere_sum_coefs += coef
                        matiere_id_last = matiere_id
                    except TypeError:  # val == "NI" "NA"
                        assert val == "NI" or val == "NA" or val == "ERR"
                        nb_missing = nb_missing + 1
                        coefs.append(0)
                        coefs_mask.append(0)

                else:  # UE_SPORT:
                    # la note du module de sport agit directement sur la moyenne gen.
                    try:
                        notes_bonus_gen.append(float(val))
                        coefs_bonus_gen.append(coef)
                    except:
                        # log('comp_etud_moy_ue: exception: val=%s coef=%s' % (val,coef))
                        pass
            elif modimpl["module"]["module_type"] == scu.MODULE_MALUS:
                try:
                    ue_malus += val
                except:
                    pass  # si non inscrit ou manquant, ignore
            else:
                raise ValueError(
                    "invalid module type (%s)" % modimpl["module"]["module_type"]
                )

        if matiere_id_last and matiere_sum_coefs:
            self._matmoys[matiere_id_last][etudid] = (
                matiere_sum_notes / matiere_sum_coefs
            )

        # Calcul moyenne:
        if sum_coefs > 0:
            moy = sum_notes / sum_coefs
            if ue_malus:
                moy -= ue_malus
                moy = max(scu.NOTES_MIN, min(moy, 20.0))
            moy_valid = True
        else:
            moy = "NA"
            moy_valid = False

        # Recalcule la moyenne en utilisant une formule utilisateur
        expr_diag = {}
        formula = sco_compute_moy.get_ue_expression(self.formsemestre_id, ue_id, cnx)
        if formula:
            moy = sco_compute_moy.compute_user_formula(
                self.sem,
                etudid,
                moy,
                moy_valid,
                notes,
                coefs,
                coefs_mask,
                formula,
                diag_info=expr_diag,
            )
            if expr_diag:
                expr_diag["ue_id"] = ue_id
                self.expr_diagnostics.append(expr_diag)

        return dict(
            moy=moy,
            nb_notes=nb_notes,
            nb_missing=nb_missing,
            sum_coefs=sum_coefs,
            notes_bonus_gen=notes_bonus_gen,
            coefs_bonus_gen=coefs_bonus_gen,
            expr_diag=expr_diag,
            ue_malus=ue_malus,
            est_inscrit=est_inscrit,
        )

    def comp_etud_moy_gen(self, etudid, cnx):
        """Calcule moyenne gen. pour un etudiant
        Return a dict:
         moy  : moyenne générale
         nb_notes, nb_missing, sum_coefs
         ects_pot : (float) nb de crédits ECTS qui seraient validés (sous réserve de validation par le jury),
         ects_pot_fond: (float) nb d'ECTS issus d'UE fondamentales (non électives)
         ects_pot_pro: (float) nb d'ECTS issus d'UE pro
         moy_ues : { ue_id : ue_status }
        où ue_status = {
             'est_inscrit' : True si étudiant inscrit à au moins un module de cette UE
             'moy' :  moyenne, avec capitalisation eventuelle
             'coef_ue' : coef de l'UE utilisé pour le calcul de la moyenne générale
                         (la somme des coefs des modules, ou le coef d'UE capitalisée,
                         ou encore le coef d'UE si l'option use_ue_coefs est active)
             'cur_moy_ue' : moyenne de l'UE en cours (sans considérer de capitalisation)
             'cur_coef_ue': coefficient de l'UE courante
             'is_capitalized' : True|False,
             'ects_pot' : (float) nb de crédits ECTS qui seraient validés (sous réserve de validation par le jury),
             'ects_pot_fond': 0. si UE non fondamentale, = ects_pot sinon,
             'ects_pot_pro' : 0 si UE non pro, = ects_pot sinon,
             'formsemestre_id' : (si capitalisee),
             'event_date' : (si capitalisee)
             }
        Si pas de notes, moy == 'NA' et sum_coefs==0

        Prend toujours en compte les UE capitalisées.
        """
        # Si l'étudiant a Démissionné ou est DEFaillant, on n'enregistre pas ses moyennes
        block_computation = (
            self.inscrdict[etudid]["etat"] == "D"
            or self.inscrdict[etudid]["etat"] == DEF
            or self.block_moyennes
        )

        moy_ues = {}
        notes_bonus_gen = (
            []
        )  # liste des notes de sport et culture (s'appliquant à la MG)
        coefs_bonus_gen = []
        nb_notes = 0  # nb de notes d'UE (non capitalisees)
        sum_notes = 0.0  # somme des notes d'UE
        # somme des coefs d'UE (eux-même somme des coefs de modules avec notes):
        sum_coefs = 0.0

        nb_missing = 0  # nombre d'UE sans notes
        sem_ects_pot = 0.0
        sem_ects_pot_fond = 0.0
        sem_ects_pot_pro = 0.0

        for ue in self.get_ues():
            # - On calcule la moyenne d'UE courante:
            if not block_computation:
                mu = self.comp_etud_moy_ue(etudid, ue_id=ue["ue_id"], cnx=cnx)
            else:
                mu = dict(
                    moy="NA",
                    nb_notes=0,
                    nb_missing=0,
                    sum_coefs=0,
                    notes_bonus_gen=0,
                    coefs_bonus_gen=0,
                    expr_diag="",
                    est_inscrit=False,
                )
            # infos supplementaires pouvant servir au calcul du bonus sport
            mu["ue"] = ue
            moy_ues[ue["ue_id"]] = mu

            # - Faut-il prendre une UE capitalisée ?
            if mu["moy"] != "NA" and mu["est_inscrit"]:
                max_moy_ue = mu["moy"]
            else:
                # pas de notes dans l'UE courante, ou pas inscrit
                max_moy_ue = 0.0
            if not mu["est_inscrit"]:
                coef_ue = 0.0
            else:
                if self.use_ue_coefs:
                    coef_ue = mu["ue"]["coefficient"]
                else:
                    # coef UE = sum des coefs modules
                    coef_ue = mu["sum_coefs"]

            # is_capitalized si l'UE prise en compte est une UE capitalisée
            mu["is_capitalized"] = False
            # was_capitalized s'il y a precedemment une UE capitalisée (pas forcement meilleure)
            mu["was_capitalized"] = False

            is_external = False
            event_date = None
            if not block_computation:
                for ue_cap in self.ue_capitalisees[etudid]:
                    if ue_cap["ue_code"] == ue["ue_code"]:
                        moy_ue_cap = ue_cap["moy"]
                        mu["was_capitalized"] = True
                        event_date = event_date or ue_cap["event_date"]
                        if (moy_ue_cap != "NA") and (moy_ue_cap > max_moy_ue):
                            # meilleure UE capitalisée
                            event_date = ue_cap["event_date"]
                            max_moy_ue = moy_ue_cap
                            mu["is_capitalized"] = True
                            capitalized_ue_id = ue_cap["ue_id"]
                            formsemestre_id = ue_cap["formsemestre_id"]
                            coef_ue = self.get_etud_ue_cap_coef(
                                etudid, ue, ue_cap, cnx=cnx
                            )
                            is_external = ue_cap["is_external"]

            mu["cur_moy_ue"] = mu["moy"]  # la moyenne dans le sem. courant
            if mu["est_inscrit"]:
                mu["cur_coef_ue"] = mu["sum_coefs"]
            else:
                mu["cur_coef_ue"] = 0.0
            mu["moy"] = max_moy_ue  # la moyenne d'UE a prendre en compte
            mu["is_external"] = is_external  # validation externe (dite "antérieure")
            mu["coef_ue"] = coef_ue  # coef reel ou coef de l'ue si capitalisee

            if mu["is_capitalized"]:
                mu["formsemestre_id"] = formsemestre_id
                mu["capitalized_ue_id"] = capitalized_ue_id
            if mu["was_capitalized"]:
                mu["event_date"] = event_date
            # - ECTS ? ("pot" pour "potentiels" car les ECTS ne seront acquises qu'apres validation du jury
            if (
                isinstance(mu["moy"], float)
                and mu["moy"] >= self.parcours.NOTES_BARRE_VALID_UE
            ):
                mu["ects_pot"] = ue["ects"] or 0.0
                if UE_is_fondamentale(ue["type"]):
                    mu["ects_pot_fond"] = mu["ects_pot"]
                else:
                    mu["ects_pot_fond"] = 0.0
                if UE_is_professionnelle(ue["type"]):
                    mu["ects_pot_pro"] = mu["ects_pot"]
                else:
                    mu["ects_pot_pro"] = 0.0
            else:
                mu["ects_pot"] = 0.0
                mu["ects_pot_fond"] = 0.0
                mu["ects_pot_pro"] = 0.0
            sem_ects_pot += mu["ects_pot"]
            sem_ects_pot_fond += mu["ects_pot_fond"]
            sem_ects_pot_pro += mu["ects_pot_pro"]

            # - Calcul moyenne générale dans le semestre:
            if mu["is_capitalized"]:
                try:
                    sum_notes += mu["moy"] * mu["coef_ue"]
                    sum_coefs += mu["coef_ue"]
                except:  # pas de note dans cette UE
                    pass
            else:
                if mu["coefs_bonus_gen"]:
                    notes_bonus_gen.extend(mu["notes_bonus_gen"])
                    coefs_bonus_gen.extend(mu["coefs_bonus_gen"])
                #
                try:
                    sum_notes += mu["moy"] * mu["sum_coefs"]
                    sum_coefs += mu["sum_coefs"]
                    nb_notes = nb_notes + 1
                except TypeError:
                    nb_missing = nb_missing + 1
        # Le resultat:
        infos = dict(
            nb_notes=nb_notes,
            nb_missing=nb_missing,
            sum_coefs=sum_coefs,
            moy_ues=moy_ues,
            ects_pot=sem_ects_pot,
            ects_pot_fond=sem_ects_pot_fond,
            ects_pot_pro=sem_ects_pot_pro,
            sem=self.sem,
        )
        # ---- Calcul moyenne (avec bonus sport&culture)
        if sum_coefs <= 0 or block_computation:
            infos["moy"] = "NA"
        else:
            if self.use_ue_coefs:
                # Calcul optionnel (mai 2020)
                # moyenne pondére par leurs coefficients des moyennes d'UE
                sum_moy_ue = 0
                sum_coefs_ue = 0
                for mu in moy_ues.values():
                    # mu["moy"] can be a number, or "NA", or "ERR" (user-defined UE formulas)
                    if (
                        (mu["ue"]["type"] != UE_SPORT)
                        and scu.isnumber(mu["moy"])
                        and (mu["est_inscrit"] or mu["is_capitalized"])
                    ):
                        coef_ue = mu["ue"]["coefficient"]
                        sum_moy_ue += mu["moy"] * coef_ue
                        sum_coefs_ue += coef_ue
                if sum_coefs_ue != 0:
                    infos["moy"] = sum_moy_ue / sum_coefs_ue
                else:
                    infos["moy"] = "NA"
            else:
                # Calcul standard ScoDoc: moyenne pondérée des notes de modules
                infos["moy"] = sum_notes / sum_coefs

            if notes_bonus_gen and infos["moy"] != "NA":
                # regle de calcul maison (configurable, voir bonus_sport.py)
                if sum(coefs_bonus_gen) <= 0 and len(coefs_bonus_gen) != 1:
                    log(
                        "comp_etud_moy_gen: invalid or null coefficient (%s) for notes_bonus_gen=%s (etudid=%s, formsemestre_id=%s)"
                        % (
                            coefs_bonus_gen,
                            notes_bonus_gen,
                            etudid,
                            self.formsemestre_id,
                        )
                    )
                    bonus = 0
                else:
                    if len(coefs_bonus_gen) == 1:
                        coefs_bonus_gen = [1.0]  # irrelevant, may be zero

                    bonus_func = ScoDocSiteConfig.get_bonus_sport_func()
                    if bonus_func:
                        bonus = bonus_func(
                            notes_bonus_gen, coefs_bonus_gen, infos=infos
                        )
                    else:
                        bonus = 0.0
                self.bonus[etudid] = bonus
                infos["moy"] += bonus
                infos["moy"] = min(infos["moy"], 20.0)  # clip bogus bonus

        return infos

    def get_etud_moy_gen(self, etudid):
        """Moyenne generale de cet etudiant dans ce semestre.
        Prend en compte les UE capitalisées.
        Si pas de notes: 'NA'
        """
        return self.moy_gen[etudid]

    def get_etud_moy_infos(self, etudid):
        """Infos sur moyennes"""
        return self.etud_moy_infos[etudid]

    # was etud_has_all_ue_over_threshold:
    def etud_check_conditions_ues(self, etudid):
        """Vrai si les conditions sur les UE sont remplies.
        Ne considère que les UE ayant des notes (moyenne calculée).
        (les UE sans notes ne sont pas comptées comme sous la barre)
        Prend en compte les éventuelles UE capitalisées.

        Pour les parcours habituels, cela revient à vérifier que
        les moyennes d'UE sont toutes > à leur barre (sauf celles sans notes)

        Pour les parcours non standards (LP2014), cela peut être plus compliqué.

        Return: True|False, message explicatif
        """
        return self.parcours.check_barre_ues(
            [self.get_etud_ue_status(etudid, ue["ue_id"]) for ue in self._ues]
        )

    def get_table_moyennes_triees(self):
        return self.T

    def get_etud_rang(self, etudid):
        return self.rangs[etudid]

    def get_etud_rang_group(self, etudid, group_id):
        """Returns rank of etud in this group and number of etuds in group.
        If etud not in group, returns None.
        """
        if not group_id in self.rangs_groupes:
            # lazy: fill rangs_groupes on demand
            # { groupe : { etudid : rang } }
            if not group_id in self.group_etuds:
                # lazy fill: list of etud in group_id
                etuds = sco_groups.get_group_members(group_id)
                self.group_etuds[group_id] = set([x["etudid"] for x in etuds])
            # 1- build T restricted to group
            Tr = []
            for t in self.get_table_moyennes_triees():
                t_etudid = t[-1]
                if t_etudid in self.group_etuds[group_id]:
                    Tr.append(t)
            #
            self.rangs_groupes[group_id] = comp_ranks(Tr)

        return (
            self.rangs_groupes[group_id].get(etudid, None),
            len(self.rangs_groupes[group_id]),
        )

    def get_table_moyennes_dict(self):
        """{ etudid : (liste des moyennes) } comme get_table_moyennes_triees"""
        D = {}
        for t in self.T:
            D[t[-1]] = t
        return D

    def get_moduleimpls_attente(self):
        "Liste des moduleimpls avec des notes en attente"
        return self._mods_att

    # Decisions existantes du jury
    def comp_decisions_jury(self):
        """Cherche les decisions du jury pour le semestre (pas les UE).
        Calcule l'attribut:
        decisions_jury = { etudid : { 'code' : None|ATT|..., 'assidu' : 0|1 }}
        decision_jury_ues={ etudid : { ue_id : { 'code' : Note|ADM|CMP, 'event_date' }}}
        Si la decision n'a pas été prise, la clé etudid n'est pas présente.
        Si l'étudiant est défaillant, met un code DEF sur toutes les UE
        """
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        cursor.execute(
            "select etudid, code, assidu, compense_formsemestre_id, event_date from scolar_formsemestre_validation where formsemestre_id=%(formsemestre_id)s and ue_id is NULL;",
            {"formsemestre_id": self.formsemestre_id},
        )
        decisions_jury = {}
        for (
            etudid,
            code,
            assidu,
            compense_formsemestre_id,
            event_date,
        ) in cursor.fetchall():
            decisions_jury[etudid] = {
                "code": code,
                "assidu": assidu,
                "compense_formsemestre_id": compense_formsemestre_id,
                "event_date": ndb.DateISOtoDMY(event_date),
            }

        self.decisions_jury = decisions_jury
        # UEs:
        cursor.execute(
            "select etudid, ue_id, code, event_date from scolar_formsemestre_validation where formsemestre_id=%(formsemestre_id)s and ue_id is not NULL;",
            {"formsemestre_id": self.formsemestre_id},
        )
        decisions_jury_ues = {}
        for (etudid, ue_id, code, event_date) in cursor.fetchall():
            if etudid not in decisions_jury_ues:
                decisions_jury_ues[etudid] = {}
            # Calcul des ECTS associes a cette UE:
            ects = 0.0
            if sco_codes_parcours.code_ue_validant(code):
                ue = self.uedict.get(ue_id, None)
                if ue is None:  # not in list for this sem ??? (probably an error)
                    log(
                        "Warning: %s capitalized an UE %s which is not part of current sem %s"
                        % (etudid, ue_id, self.formsemestre_id)
                    )
                    ue = sco_edit_ue.ue_list(args={"ue_id": ue_id})[0]
                    self.uedict[ue_id] = ue  # record this UE
                    if ue_id not in self._uecoef:
                        cl = formsemestre_uecoef_list(
                            cnx,
                            args={
                                "formsemestre_id": self.formsemestre_id,
                                "ue_id": ue_id,
                            },
                        )
                        if not cl:
                            # cas anormal: UE capitalisee, pas dans ce semestre, et sans coef
                            log("Warning: setting UE coef to zero")
                            formsemestre_uecoef_create(
                                cnx,
                                args={
                                    "formsemestre_id": self.formsemestre_id,
                                    "ue_id": ue_id,
                                    "coefficient": 0,
                                },
                            )

                ects = ue["ects"] or 0.0  # 0 if None

            decisions_jury_ues[etudid][ue_id] = {
                "code": code,
                "ects": ects,  # 0. si non UE validée ou si mode de calcul different (?)
                "event_date": ndb.DateISOtoDMY(event_date),
            }

        self.decisions_jury_ues = decisions_jury_ues

    def get_etud_decision_sem(self, etudid):
        """Decision du jury prise pour cet etudiant, ou None s'il n'y en pas eu.
        { 'code' : None|ATT|..., 'assidu' : 0|1, 'event_date' : , compense_formsemestre_id }
        Si état défaillant, force le code a DEF
        """
        if self.get_etud_etat(etudid) == DEF:
            return {
                "code": DEF,
                "assidu": False,
                "event_date": "",
                "compense_formsemestre_id": None,
            }
        else:
            return self.decisions_jury.get(etudid, None)

    def get_etud_decision_ues(self, etudid):
        """Decisions du jury pour les UE de cet etudiant, ou None s'il n'y en pas eu.
        Ne tient pas compte des UE capitalisées.
        { ue_id : { 'code' : ADM|CMP|AJ, 'event_date' : }
        Ne renvoie aucune decision d'UE pour les défaillants
        """
        if self.get_etud_etat(etudid) == DEF:
            return {}
        else:
            return self.decisions_jury_ues.get(etudid, None)

    def sem_has_decisions(self):
        """True si au moins une decision de jury dans ce semestre"""
        if [x for x in self.decisions_jury_ues.values() if x]:
            return True

        return len([x for x in self.decisions_jury_ues.values() if x]) > 0

    def etud_has_decision(self, etudid):
        """True s'il y a une décision de jury pour cet étudiant"""
        return self.get_etud_decision_ues(etudid) or self.get_etud_decision_sem(etudid)

    def all_etuds_have_sem_decisions(self):
        """True si tous les étudiants du semestre ont une décision de jury.
        ne regarde pas les décisions d'UE (todo: à voir ?)
        """
        for etudid in self.get_etudids():
            if self.inscrdict[etudid]["etat"] == "D":
                continue  # skip demissionnaires
            if self.get_etud_decision_sem(etudid) is None:
                return False
        return True

    # Capitalisation des UEs
    def comp_ue_capitalisees(self):
        """Cherche pour chaque etudiant ses UE capitalisées dans ce semestre.
        Calcule l'attribut:
        ue_capitalisees = { etudid :
                             [{ 'moy':, 'event_date' : ,'formsemestre_id' : }, ...] }
        """
        self.ue_capitalisees = scu.DictDefault(defaultvalue=[])
        cnx = None
        for etudid in self.get_etudids():
            capital = formsemestre_get_etud_capitalisation(self.sem, etudid)
            for ue_cap in capital:
                # Si la moyenne d'UE n'avait pas été stockée (anciennes versions de ScoDoc)
                # il faut la calculer ici et l'enregistrer
                if ue_cap["moy_ue"] is None:
                    log(
                        "comp_ue_capitalisees: recomputing UE moy (etudid=%s, ue_id=%s formsemestre_id=%s)"
                        % (etudid, ue_cap["ue_id"], ue_cap["formsemestre_id"])
                    )
                    nt_cap = sco_cache.NotesTableCache.get(
                        ue_cap["formsemestre_id"]
                    )  # > UE capitalisees par un etud
                    moy_ue_cap = nt_cap.get_etud_ue_status(etudid, ue_cap["ue_id"])[
                        "moy"
                    ]
                    ue_cap["moy_ue"] = moy_ue_cap
                    if (
                        isinstance(moy_ue_cap, float)
                        and moy_ue_cap >= self.parcours.NOTES_BARRE_VALID_UE
                    ):
                        if not cnx:
                            cnx = ndb.GetDBConnexion(autocommit=False)
                        sco_parcours_dut.do_formsemestre_validate_ue(
                            cnx,
                            nt_cap,
                            ue_cap["formsemestre_id"],
                            etudid,
                            ue_cap["ue_id"],
                            ue_cap["code"],
                        )
                    else:
                        log(
                            "*** valid inconsistency: moy_ue_cap=%s (etudid=%s, ue_id=%s formsemestre_id=%s)"
                            % (
                                moy_ue_cap,
                                etudid,
                                ue_cap["ue_id"],
                                ue_cap["formsemestre_id"],
                            )
                        )
                ue_cap["moy"] = ue_cap["moy_ue"]  # backward compat (needs refactoring)
                self.ue_capitalisees[etudid].append(ue_cap)
        if cnx:
            cnx.commit()
        # log('comp_ue_capitalisees=\n%s' % pprint.pformat(self.ue_capitalisees) )

    # def comp_etud_sum_coef_modules_ue( etudid, ue_id):
    #     """Somme des coefficients des modules de l'UE dans lesquels cet étudiant est inscrit
    #     ou None s'il n'y a aucun module
    #     """
    #     c_list = [ mod['module']['coefficient']
    #                for mod in self._modimpls
    #                if (( mod['module']['ue_id'] == ue_id)
    #                    and self._modmoys[mod['moduleimpl_id']].get(etudid, False) is not False)
    #     ]
    #     if not c_list:
    #         return None
    #     return sum(c_list)

    def get_etud_ue_cap_coef(self, etudid, ue, ue_cap, cnx=None):
        """Calcule le coefficient d'une UE capitalisée, pour cet étudiant,
        injectée dans le semestre courant.

        ue : ue du semestre courant

        ue_cap = resultat de formsemestre_get_etud_capitalisation
        { 'ue_id' (dans le semestre source),
          'ue_code', 'moy', 'event_date','formsemestre_id' }
        """
        # log("get_etud_ue_cap_coef\nformsemestre_id='%s'\netudid='%s'\nue=%s\nue_cap=%s\n" % (self.formsemestre_id, etudid, ue, ue_cap))
        # 1- Coefficient explicitement déclaré dans le semestre courant pour cette UE ?
        if ue["ue_id"] not in self._uecoef:
            self._uecoef[ue["ue_id"]] = formsemestre_uecoef_list(
                cnx,
                args={"formsemestre_id": self.formsemestre_id, "ue_id": ue["ue_id"]},
            )

        if len(self._uecoef[ue["ue_id"]]):
            # utilisation du coef manuel
            return self._uecoef[ue["ue_id"]][0]["coefficient"]

        # 2- Mode automatique: calcul du coefficient
        # Capitalisation depuis un autre semestre ScoDoc ?
        coef = None
        if ue_cap["formsemestre_id"]:
            # Somme des coefs dans l'UE du semestre d'origine (nouveau: 23/01/2016)
            coef = comp_etud_sum_coef_modules_ue(
                ue_cap["formsemestre_id"], etudid, ue_cap["ue_id"]
            )
        if coef != None:
            return coef
        else:
            # Capitalisation UE externe: quel coef appliquer ?
            # Si l'étudiant est inscrit dans le semestre courant,
            # somme des coefs des modules de l'UE auxquels il est inscrit
            c = comp_etud_sum_coef_modules_ue(self.formsemestre_id, etudid, ue["ue_id"])
            if c is not None:  # inscrit à au moins un module de cette UE
                return c
            # arfff: aucun moyen de déterminer le coefficient de façon sûre
            log(
                "* oups: calcul coef UE impossible\nformsemestre_id='%s'\netudid='%s'\nue=%s\nue_cap=%s"
                % (self.formsemestre_id, etudid, ue, ue_cap)
            )
            raise ScoValueError(
                """<div class="scovalueerror"><p>Coefficient de l'UE capitalisée %s impossible à déterminer
                pour l'étudiant <a href="%s" class="discretelink">%s</a></p>
                <p>Il faut <a href="%s">saisir le coefficient de cette UE avant de continuer</a></p>
                </div>
                """
                % (
                    ue["acronyme"],
                    url_for(
                        "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid
                    ),
                    self.get_nom_long(etudid),
                    url_for(
                        "notes.formsemestre_edit_uecoefs",
                        scodoc_dept=g.scodoc_dept,
                        formsemestre_id=self.formsemestre_id,
                        err_ue_id=ue["ue_id"],
                    ),
                )
            )

        return 0.0  # ?

    def get_etud_ue_status(self, etudid, ue_id):
        "Etat de cette UE (note, coef, capitalisation, ...)"
        return self._etud_moy_ues[etudid][ue_id]

    def etud_has_notes_attente(self, etudid):
        """Vrai si cet etudiant a au moins une note en attente dans ce semestre.
        (ne compte que les notes en attente dans des évaluation avec coef. non nul).
        """
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        cursor.execute(
            """SELECT n.*
            FROM notes_notes n, notes_evaluation e, notes_moduleimpl m,
            notes_moduleimpl_inscription i
            WHERE n.etudid = %(etudid)s
            and n.value = %(code_attente)s
            and n.evaluation_id = e.id
            and e.moduleimpl_id = m.id
            and m.formsemestre_id = %(formsemestre_id)s
            and e.coefficient != 0
            and m.id = i.moduleimpl_id
            and i.etudid=%(etudid)s
            """,
            {
                "formsemestre_id": self.formsemestre_id,
                "etudid": etudid,
                "code_attente": scu.NOTES_ATTENTE,
            },
        )
        return len(cursor.fetchall()) > 0

    def get_evaluations_etats(self):  # evaluation_list_in_sem
        """[ {...evaluation et son etat...} ]"""
        if self._evaluations_etats is None:
            self._evaluations_etats = sco_evaluations.do_evaluation_list_in_sem(
                self.formsemestre_id
            )

        return self._evaluations_etats

    def get_sem_evaluation_etat_list(self):
        """Liste des evaluations de ce semestre, avec leur etat"""
        return self.get_evaluations_etats()

    def get_mod_evaluation_etat_list(self, moduleimpl_id):
        """Liste des évaluations de ce module"""
        return [
            e
            for e in self.get_evaluations_etats()
            if e["moduleimpl_id"] == moduleimpl_id
        ]
