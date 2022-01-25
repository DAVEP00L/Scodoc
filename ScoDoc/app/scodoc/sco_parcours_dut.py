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

"""Semestres: gestion parcours DUT (Arreté du 13 août 2005)
"""

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.scolog import logdb
from app.scodoc import sco_cache
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formations
from app.scodoc.sco_codes_parcours import (
    CMP,
    ADC,
    ADJ,
    ADM,
    AJ,
    ATT,
    NO_SEMESTRE_ID,
    BUG,
    NEXT,
    NEXT2,
    NEXT_OR_NEXT2,
    REO,
    REDOANNEE,
    REDOSEM,
    RA_OR_NEXT,
    RA_OR_RS,
    RS_OR_NEXT,
    CODES_SEM_VALIDES,
    NOTES_BARRE_GEN_COMPENSATION,
    code_semestre_attente,
    code_semestre_validant,
)
from app.scodoc.dutrules import DUTRules  # regles generees a partir du CSV
from app.scodoc.sco_exceptions import ScoValueError


class DecisionSem(object):
    "Decision prenable pour un semestre"

    def __init__(
        self,
        code_etat=None,
        code_etat_ues={},  # { ue_id : code }
        new_code_prev="",
        explication="",  # aide pour le jury
        formsemestre_id_utilise_pour_compenser=None,  # None si code != ADC
        devenir=None,  # code devenir
        assiduite=True,
        rule_id=None,  # id regle correspondante
    ):
        self.code_etat = code_etat
        self.code_etat_ues = code_etat_ues
        self.new_code_prev = new_code_prev
        self.explication = explication
        self.formsemestre_id_utilise_pour_compenser = (
            formsemestre_id_utilise_pour_compenser
        )
        self.devenir = devenir
        self.assiduite = assiduite
        self.rule_id = rule_id
        # code unique (string) utilise pour la gestion du formulaire
        self.codechoice = (
            "C"  # prefix pour éviter que Flask le considère comme int
            + str(
                hash(
                    (
                        code_etat,
                        new_code_prev,
                        formsemestre_id_utilise_pour_compenser,
                        devenir,
                        assiduite,
                    )
                )
            )
        )
        # xxx debug
        # log('%s: %s %s %s %s %s' % (self.codechoice,code_etat,new_code_prev,formsemestre_id_utilise_pour_compenser,devenir,assiduite) )


def SituationEtudParcours(etud, formsemestre_id):
    """renvoie une instance de SituationEtudParcours (ou sous-classe spécialisée)"""
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etud_decision_sem, get_etud_moy_gen, get_ues, get_etud_ue_status, etud_check_conditions_ues
    parcours = nt.parcours
    #
    if parcours.ECTS_ONLY:
        return SituationEtudParcoursECTS(etud, formsemestre_id, nt)
    else:
        return SituationEtudParcoursGeneric(etud, formsemestre_id, nt)


class SituationEtudParcoursGeneric(object):
    "Semestre dans un parcours"

    def __init__(self, etud, formsemestre_id, nt):
        """
        etud: dict filled by fill_etuds_info()
        """
        self.etud = etud
        self.etudid = etud["etudid"]
        self.formsemestre_id = formsemestre_id
        self.sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        self.nt = nt
        self.formation = self.nt.formation
        self.parcours = self.nt.parcours
        # Ce semestre est-il le dernier de la formation ? (e.g. semestre 4 du DUT)
        # pour le DUT, le dernier est toujours S4.
        # Ici: terminal si semestre == NB_SEM ou bien semestre_id==-1
        #        (licences et autres formations en 1 seule session))
        self.semestre_non_terminal = (
            self.sem["semestre_id"] != self.parcours.NB_SEM
        )  # True | False
        if self.sem["semestre_id"] == NO_SEMESTRE_ID:
            self.semestre_non_terminal = False
        # Liste des semestres du parcours de cet étudiant:
        self._comp_semestres()
        # Determine le semestre "precedent"
        self.prev_formsemestre_id = self._search_prev()
        # Verifie barres
        self._comp_barres()
        # Verifie compensation
        if self.prev and self.sem["gestion_compensation"]:
            self.can_compensate_with_prev = self.prev["can_compensate"]
        else:
            self.can_compensate_with_prev = False

    def get_possible_choices(self, assiduite=True):
        """Donne la liste des décisions possibles en jury (hors décisions manuelles)
        (liste d'instances de DecisionSem)
        assiduite = True si pas de probleme d'assiduité
        """
        choices = []
        if self.prev_decision:
            prev_code_etat = self.prev_decision["code"]
        else:
            prev_code_etat = None

        state = (
            prev_code_etat,
            assiduite,
            self.barre_moy_ok,
            self.barres_ue_ok,
            self.can_compensate_with_prev,
            self.semestre_non_terminal,
        )
        # log('get_possible_choices: state=%s' % str(state) )
        for rule in DUTRules:
            # Saute codes non autorisés dans ce parcours (eg ATT en LP)
            if rule.conclusion[0] in self.parcours.UNUSED_CODES:
                continue
            # Saute regles REDOSEM si pas de semestres decales:
            if (not self.sem["gestion_semestrielle"]) and rule.conclusion[
                3
            ] == "REDOSEM":
                continue
            if rule.match(state):
                if rule.conclusion[0] == ADC:
                    # dans les regles on ne peut compenser qu'avec le PRECEDENT:
                    fiduc = self.prev_formsemestre_id
                    assert fiduc
                else:
                    fiduc = None
                # Detection d'incoherences (regles BUG)
                if rule.conclusion[5] == BUG:
                    log("get_possible_choices: inconsistency: state=%s" % str(state))
                #
                # valid_semestre = code_semestre_validant(rule.conclusion[0])
                choices.append(
                    DecisionSem(
                        code_etat=rule.conclusion[0],
                        new_code_prev=rule.conclusion[2],
                        devenir=rule.conclusion[3],
                        formsemestre_id_utilise_pour_compenser=fiduc,
                        explication=rule.conclusion[5],
                        assiduite=assiduite,
                        rule_id=rule.rule_id,
                    )
                )
        return choices

    def explique_devenir(self, devenir):
        "Phrase d'explication pour le code devenir"
        if not devenir:
            return ""
        s = self.sem["semestre_id"]  # numero semestre courant
        if s < 0:  # formation sans semestres (eg licence)
            next_s = 1
        else:
            next_s = self._get_next_semestre_id()
        # log('s=%s  next=%s' % (s, next_s))
        SA = self.parcours.SESSION_ABBRV  # 'S' ou 'A'
        if self.semestre_non_terminal and not self.all_other_validated():
            passage = "Passe en %s%s" % (SA, next_s)
        else:
            passage = "Formation terminée"
        if devenir == NEXT:
            return passage
        elif devenir == REO:
            return "Réorienté"
        elif devenir == REDOANNEE:
            return "Redouble année (recommence %s%s)" % (SA, (s - 1))
        elif devenir == REDOSEM:
            return "Redouble semestre (recommence en %s%s)" % (SA, s)
        elif devenir == RA_OR_NEXT:
            return passage + ", ou redouble année (en %s%s)" % (SA, (s - 1))
        elif devenir == RA_OR_RS:
            return "Redouble semestre %s%s, ou redouble année (en %s%s)" % (
                SA,
                s,
                SA,
                s - 1,
            )
        elif devenir == RS_OR_NEXT:
            return passage + ", ou semestre %s%s" % (SA, s)
        elif devenir == NEXT_OR_NEXT2:
            return passage + ", ou en semestre %s%s" % (
                SA,
                s + 2,
            )  # coherent avec  get_next_semestre_ids
        elif devenir == NEXT2:
            return "Passe en %s%s" % (SA, s + 2)
        else:
            log("explique_devenir: code devenir inconnu: %s" % devenir)
            return "Code devenir inconnu !"

    def all_other_validated(self):
        "True si tous les autres semestres de cette formation sont validés"
        return self._sems_validated(exclude_current=True)

    def sem_idx_is_validated(self, semestre_id):
        "True si le semestre d'indice indiqué est validé dans ce parcours"
        return self._sem_list_validated(set([semestre_id]))

    def parcours_validated(self):
        "True si parcours validé (diplôme obtenu, donc)."
        return self._sems_validated()

    def _sems_validated(self, exclude_current=False):
        "True si semestres du parcours validés"
        if self.sem["semestre_id"] == NO_SEMESTRE_ID:
            # mono-semestre: juste celui ci
            decision = self.nt.get_etud_decision_sem(self.etudid)
            return decision and code_semestre_validant(decision["code"])
        else:
            to_validate = set(
                range(1, self.parcours.NB_SEM + 1)
            )  # ensemble des indices à valider
            if exclude_current and self.sem["semestre_id"] in to_validate:
                to_validate.remove(self.sem["semestre_id"])
            return self._sem_list_validated(to_validate)

    def can_jump_to_next2(self):
        """True si l'étudiant peut passer directement en Sn+2 (eg de S2 en S4).
        Il faut donc que tous les semestres 1...n-1 soient validés et que n+1 soit en attente.
        (et que le sem courant n soit validé, ce qui n'est pas testé ici)
        """
        n = self.sem["semestre_id"]
        if not self.sem["gestion_semestrielle"]:
            return False  # pas de semestre décalés
        if n == NO_SEMESTRE_ID or n > self.parcours.NB_SEM - 2:
            return False  # n+2 en dehors du parcours
        if self._sem_list_validated(set(range(1, n))):
            # antérieurs validé, teste suivant
            n1 = n + 1
            for sem in self.get_semestres():
                if (
                    sem["semestre_id"] == n1
                    and sem["formation_code"] == self.formation["formation_code"]
                ):
                    nt = sco_cache.NotesTableCache.get(
                        sem["formsemestre_id"]
                    )  # > get_etud_decision_sem
                    decision = nt.get_etud_decision_sem(self.etudid)
                    if decision and (
                        code_semestre_validant(decision["code"])
                        or code_semestre_attente(decision["code"])
                    ):
                        return True
        return False

    def _sem_list_validated(self, sem_idx_set):
        """True si les semestres dont les indices sont donnés en argument (modifié)
        sont validés. En sortie, sem_idx_set contient ceux qui n'ont pas été validés."""
        for sem in self.get_semestres():
            if sem["formation_code"] == self.formation["formation_code"]:
                nt = sco_cache.NotesTableCache.get(
                    sem["formsemestre_id"]
                )  # > get_etud_decision_sem
                decision = nt.get_etud_decision_sem(self.etudid)
                if decision and code_semestre_validant(decision["code"]):
                    # validé
                    sem_idx_set.discard(sem["semestre_id"])

        return not sem_idx_set

    def _comp_semestres(self):
        # etud['sems'] est trie par date decroissante (voir fill_etuds_info)
        sems = self.etud["sems"][:]  # copy
        sems.reverse()
        # Nb max d'UE et acronymes
        ue_acros = {}  # acronyme ue : 1
        nb_max_ue = 0
        for sem in sems:
            nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])  # > get_ues
            ues = nt.get_ues(filter_sport=True)
            for ue in ues:
                ue_acros[ue["acronyme"]] = 1
            nb_ue = len(ues)
            if nb_ue > nb_max_ue:
                nb_max_ue = nb_ue
            # add formation_code to each sem:
            sem["formation_code"] = sco_formations.formation_list(
                args={"formation_id": sem["formation_id"]}
            )[0]["formation_code"]
            # si sem peut servir à compenser le semestre courant, positionne
            #  can_compensate
            sem["can_compensate"] = check_compensation(
                self.etudid, self.sem, self.nt, sem, nt
            )

        self.ue_acros = list(ue_acros.keys())
        self.ue_acros.sort()
        self.nb_max_ue = nb_max_ue
        self.sems = sems

    def get_semestres(self):
        """Liste des semestres dans lesquels a été inscrit
        l'étudiant (quelle que soit la formation), le plus ancien en tête"""
        return self.sems

    def get_parcours_descr(self, filter_futur=False):
        """Description brève du parcours: "S1, S2, ..."
        Si filter_futur, ne mentionne pas les semestres qui sont après le semestre courant.
        """
        cur_begin_date = self.sem["dateord"]
        p = []
        for s in self.sems:
            if s["ins"]["etat"] == "D":
                dem = " (dem.)"
            else:
                dem = ""
            if filter_futur and s["dateord"] > cur_begin_date:
                continue  # skip semestres demarrant apres le courant
            SA = self.parcours.SESSION_ABBRV  # 'S' ou 'A'
            if s["semestre_id"] < 0:
                SA = "A"  # force, cas des DUT annuels par exemple
                p.append("%s%d%s" % (SA, -s["semestre_id"], dem))
            else:
                p.append("%s%d%s" % (SA, s["semestre_id"], dem))
        return ", ".join(p)

    def get_parcours_decisions(self):
        """Decisions de jury de chacun des semestres du parcours,
        du S1 au NB_SEM+1, ou mono-semestre.
        Returns: { semestre_id : code }
        """
        r = {}
        if self.sem["semestre_id"] == NO_SEMESTRE_ID:
            indices = [NO_SEMESTRE_ID]
        else:
            indices = list(range(1, self.parcours.NB_SEM + 1))
        for i in indices:
            # cherche dans les semestres de l'étudiant, en partant du plus récent
            sem = None
            for asem in reversed(self.get_semestres()):
                if asem["semestre_id"] == i:
                    sem = asem
                    break
            if not sem:
                code = ""  # non inscrit à ce semestre
            else:
                nt = sco_cache.NotesTableCache.get(
                    sem["formsemestre_id"]
                )  # > get_etud_decision_sem
                decision = nt.get_etud_decision_sem(self.etudid)
                if decision:
                    code = decision["code"]
                else:
                    code = "-"
            r[i] = code
        return r

    def _comp_barres(self):
        "calcule barres_ue_ok et barre_moy_ok:  barre moy. gen. et barres UE"
        self.barres_ue_ok, self.barres_ue_diag = self.nt.etud_check_conditions_ues(
            self.etudid
        )
        self.moy_gen = self.nt.get_etud_moy_gen(self.etudid)
        self.barre_moy_ok = (isinstance(self.moy_gen, float)) and (
            self.moy_gen >= (self.parcours.BARRE_MOY - scu.NOTES_TOLERANCE)
        )
        # conserve etat UEs
        ue_ids = [
            x["ue_id"] for x in self.nt.get_ues(etudid=self.etudid, filter_sport=True)
        ]
        self.ues_status = {}  # ue_id : status
        for ue_id in ue_ids:
            self.ues_status[ue_id] = self.nt.get_etud_ue_status(self.etudid, ue_id)

    def could_be_compensated(self):
        "true si ce semestre pourrait etre compensé par un autre (e.g. barres UE > 8)"
        return self.barres_ue_ok

    def _search_prev(self):
        """Recherche semestre 'precedent'.
        return prev_formsemestre_id
        """
        self.prev = None
        self.prev_decision = None
        if len(self.sems) < 2:
            return None
        # Cherche sem courant dans la liste triee par date_debut
        cur = None
        icur = -1
        for cur in self.sems:
            icur += 1
            if cur["formsemestre_id"] == self.formsemestre_id:
                break
        if not cur or cur["formsemestre_id"] != self.formsemestre_id:
            log(
                "*** SituationEtudParcours: search_prev: cur not found (formsemestre_id=%s, etudid=%s)"
                % (self.formsemestre_id, self.etudid)
            )
            return None  # pas de semestre courant !!!
        # Cherche semestre antérieur de même formation (code) et semestre_id precedent
        #
        # i = icur - 1 # part du courant, remonte vers le passé
        i = len(self.sems) - 1  # par du dernier, remonte vers le passé
        prev = None
        while i >= 0:
            if (
                self.sems[i]["formation_code"] == self.formation["formation_code"]
                and self.sems[i]["semestre_id"] == cur["semestre_id"] - 1
            ):
                prev = self.sems[i]
                break
            i -= 1
        if not prev:
            return None  # pas de precedent trouvé
        self.prev = prev
        # Verifications basiques:
        # ?
        # Code etat du semestre precedent:
        nt = sco_cache.NotesTableCache.get(prev["formsemestre_id"])
        # > get_etud_decision_sem, get_etud_moy_gen, etud_check_conditions_ues
        self.prev_decision = nt.get_etud_decision_sem(self.etudid)
        self.prev_moy_gen = nt.get_etud_moy_gen(self.etudid)
        self.prev_barres_ue_ok = nt.etud_check_conditions_ues(self.etudid)[0]
        return self.prev["formsemestre_id"]

    def get_next_semestre_ids(self, devenir):
        """Liste des numeros de semestres autorises avec ce devenir
        Ne vérifie pas que le devenir est possible (doit être fait avant),
        juste que le rang du semestre est dans le parcours [1..NB_SEM]
        """
        s = self.sem["semestre_id"]
        if devenir == NEXT:
            ids = [self._get_next_semestre_id()]
        elif devenir == REDOANNEE:
            ids = [s - 1]
        elif devenir == REDOSEM:
            ids = [s]
        elif devenir == RA_OR_NEXT:
            ids = [s - 1, self._get_next_semestre_id()]
        elif devenir == RA_OR_RS:
            ids = [s - 1, s]
        elif devenir == RS_OR_NEXT:
            ids = [s, self._get_next_semestre_id()]
        elif devenir == NEXT_OR_NEXT2:
            ids = [
                self._get_next_semestre_id(),
                s + 2,
            ]  # cohérent avec explique_devenir()
        elif devenir == NEXT2:
            ids = [s + 2]
        else:
            ids = []  # reoriente ou autre: pas de next !
        # clip [1..NB_SEM]
        r = []
        for idx in ids:
            if idx > 0 and idx <= self.parcours.NB_SEM:
                r.append(idx)
        return r

    def _get_next_semestre_id(self):
        """Indice du semestre suivant non validé.
        S'il n'y en a pas, ramène NB_SEM+1
        """
        s = self.sem["semestre_id"]
        if s >= self.parcours.NB_SEM:
            return self.parcours.NB_SEM + 1
        validated = True
        while validated and (s < self.parcours.NB_SEM):
            s = s + 1
            # semestre s validé ?
            validated = False
            for sem in self.sems:
                if (
                    sem["formation_code"] == self.formation["formation_code"]
                    and sem["semestre_id"] == s
                ):
                    nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
                    # > get_etud_decision_sem
                    decision = nt.get_etud_decision_sem(self.etudid)
                    if decision and code_semestre_validant(decision["code"]):
                        validated = True
        return s

    def valide_decision(self, decision):
        """Enregistre la decision (instance de DecisionSem)
        Enregistre codes semestre et UE, et autorisations inscription.
        """
        cnx = ndb.GetDBConnexion(autocommit=False)
        # -- check
        if decision.code_etat in self.parcours.UNUSED_CODES:
            raise ScoValueError("code decision invalide dans ce parcours")
        #
        if decision.code_etat == ADC:
            fsid = decision.formsemestre_id_utilise_pour_compenser
            if fsid:
                ok = False
                for sem in self.sems:
                    if sem["formsemestre_id"] == fsid and sem["can_compensate"]:
                        ok = True
                        break
                if not ok:
                    raise ScoValueError("valide_decision: compensation impossible")
        # -- supprime decision precedente et enregistre decision
        to_invalidate = []
        if self.nt.get_etud_decision_sem(self.etudid):
            to_invalidate = formsemestre_update_validation_sem(
                cnx,
                self.formsemestre_id,
                self.etudid,
                decision.code_etat,
                decision.assiduite,
                decision.formsemestre_id_utilise_pour_compenser,
            )
        else:
            formsemestre_validate_sem(
                cnx,
                self.formsemestre_id,
                self.etudid,
                decision.code_etat,
                decision.assiduite,
                decision.formsemestre_id_utilise_pour_compenser,
            )
        logdb(
            cnx,
            method="validate_sem",
            etudid=self.etudid,
            commit=False,
            msg="formsemestre_id=%s code=%s"
            % (self.formsemestre_id, decision.code_etat),
        )
        # -- decisions UEs
        formsemestre_validate_ues(
            self.formsemestre_id,
            self.etudid,
            decision.code_etat,
            decision.assiduite,
        )
        # -- modification du code du semestre precedent
        if self.prev and decision.new_code_prev:
            if decision.new_code_prev == ADC:
                # ne compense le prec. qu'avec le sem. courant
                fsid = self.formsemestre_id
            else:
                fsid = None
            to_invalidate += formsemestre_update_validation_sem(
                cnx,
                self.prev["formsemestre_id"],
                self.etudid,
                decision.new_code_prev,
                assidu=True,
                formsemestre_id_utilise_pour_compenser=fsid,
            )
            logdb(
                cnx,
                method="validate_sem",
                etudid=self.etudid,
                commit=False,
                msg="formsemestre_id=%s code=%s"
                % (self.prev["formsemestre_id"], decision.new_code_prev),
            )
            # modifs des codes d'UE (pourraient passer de ADM a CMP, meme sans modif des notes)
            formsemestre_validate_ues(
                self.prev["formsemestre_id"],
                self.etudid,
                decision.new_code_prev,
                decision.assiduite,  # attention: en toute rigueur il faudrait utiliser une indication de l'assiduite au sem. precedent, que nous n'avons pas...
            )

            sco_cache.invalidate_formsemestre(
                formsemestre_id=self.prev["formsemestre_id"]
            )  # > modif decisions jury (sem, UE)

        # -- supprime autorisations venant de ce formsemestre
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        try:
            cursor.execute(
                """delete from scolar_autorisation_inscription
            where etudid = %(etudid)s and origin_formsemestre_id=%(origin_formsemestre_id)s
            """,
                {"etudid": self.etudid, "origin_formsemestre_id": self.formsemestre_id},
            )

            # -- enregistre autorisations inscription
            next_semestre_ids = self.get_next_semestre_ids(decision.devenir)
            for next_semestre_id in next_semestre_ids:
                _scolar_autorisation_inscription_editor.create(
                    cnx,
                    {
                        "etudid": self.etudid,
                        "formation_code": self.formation["formation_code"],
                        "semestre_id": next_semestre_id,
                        "origin_formsemestre_id": self.formsemestre_id,
                    },
                )
            cnx.commit()
        except:
            cnx.rollback()
            raise
        sco_cache.invalidate_formsemestre(
            formsemestre_id=self.formsemestre_id
        )  # > modif decisions jury et autorisations inscription
        if decision.formsemestre_id_utilise_pour_compenser:
            # inval aussi le semestre utilisé pour compenser:
            sco_cache.invalidate_formsemestre(
                formsemestre_id=decision.formsemestre_id_utilise_pour_compenser,
            )  # > modif decision jury
        for formsemestre_id in to_invalidate:
            sco_cache.invalidate_formsemestre(
                formsemestre_id=formsemestre_id
            )  # > modif decision jury


class SituationEtudParcoursECTS(SituationEtudParcoursGeneric):
    """Gestion parcours basés sur ECTS"""

    def __init__(self, etud, formsemestre_id, nt):
        SituationEtudParcoursGeneric.__init__(self, etud, formsemestre_id, nt)

    def could_be_compensated(self):
        return False  # jamais de compensations dans ce parcours

    def get_possible_choices(self, assiduite=True):
        """Listes de décisions "recommandées" (hors décisions manuelles)

        Dans ce type de parcours, on n'utilise que ADM, AJ, et ADJ (?).
        """
        etud_moy_infos = self.nt.get_etud_moy_infos(self.etudid)
        if (
            etud_moy_infos["ects_pot"] >= self.parcours.ECTS_BARRE_VALID_YEAR
            and etud_moy_infos["ects_pot"] >= self.parcours.ECTS_FONDAMENTAUX_PER_YEAR
        ):
            choices = [
                DecisionSem(
                    code_etat=ADM,
                    new_code_prev=None,
                    devenir=NEXT,
                    formsemestre_id_utilise_pour_compenser=None,
                    explication="Semestre validé",
                    assiduite=assiduite,
                    rule_id="1000",
                )
            ]
        else:
            choices = [
                DecisionSem(
                    code_etat=AJ,
                    new_code_prev=None,
                    devenir=NEXT,
                    formsemestre_id_utilise_pour_compenser=None,
                    explication="Semestre non validé",
                    assiduite=assiduite,
                    rule_id="1001",
                )
            ]
        return choices


#
def check_compensation(etudid, sem, nt, semc, ntc):
    """Verifie si le semestre sem peut se compenser en utilisant semc
    - semc non utilisé par un autre semestre
    - decision du jury prise  ADM ou ADJ ou ATT ou ADC
    - barres UE (moy ue > 8) dans sem et semc
    - moyenne des moy_gen > 10
    Return boolean
    """
    # -- deja utilise ?
    decc = ntc.get_etud_decision_sem(etudid)
    if (
        decc
        and decc["compense_formsemestre_id"]
        and decc["compense_formsemestre_id"] != sem["formsemestre_id"]
    ):
        return False
    # -- semestres consecutifs ?
    if abs(sem["semestre_id"] - semc["semestre_id"]) != 1:
        return False
    # -- decision jury:
    if decc and not decc["code"] in (ADM, ADJ, ATT, ADC):
        return False
    # -- barres UE et moyenne des moyennes:
    moy_gen = nt.get_etud_moy_gen(etudid)
    moy_genc = ntc.get_etud_moy_gen(etudid)
    try:
        moy_moy = (moy_gen + moy_genc) / 2
    except:  # un des semestres sans aucune note !
        return False

    if (
        nt.etud_check_conditions_ues(etudid)[0]
        and ntc.etud_check_conditions_ues(etudid)[0]
        and moy_moy >= NOTES_BARRE_GEN_COMPENSATION
    ):
        return True
    else:
        return False


# -------------------------------------------------------------------------------------------


def int_or_null(s):
    if s == "":
        return None
    else:
        return int(s)


_scolar_formsemestre_validation_editor = ndb.EditableTable(
    "scolar_formsemestre_validation",
    "formsemestre_validation_id",
    (
        "formsemestre_validation_id",
        "etudid",
        "formsemestre_id",
        "ue_id",
        "code",
        "assidu",
        "event_date",
        "compense_formsemestre_id",
        "moy_ue",
        "semestre_id",
        "is_external",
    ),
    output_formators={
        "event_date": ndb.DateISOtoDMY,
    },
    input_formators={
        "event_date": ndb.DateDMYtoISO,
        "assidu": bool,
        "is_external": bool,
    },
)

scolar_formsemestre_validation_create = _scolar_formsemestre_validation_editor.create
scolar_formsemestre_validation_list = _scolar_formsemestre_validation_editor.list
scolar_formsemestre_validation_delete = _scolar_formsemestre_validation_editor.delete
scolar_formsemestre_validation_edit = _scolar_formsemestre_validation_editor.edit


def formsemestre_validate_sem(
    cnx,
    formsemestre_id,
    etudid,
    code,
    assidu=True,
    formsemestre_id_utilise_pour_compenser=None,
):
    "Ajoute ou change validation semestre"
    args = {"formsemestre_id": formsemestre_id, "etudid": etudid}
    # delete existing
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    try:
        cursor.execute(
            """delete from scolar_formsemestre_validation
        where etudid = %(etudid)s and formsemestre_id=%(formsemestre_id)s and ue_id is null""",
            args,
        )
        # insert
        args["code"] = code
        args["assidu"] = assidu
        log("formsemestre_validate_sem: %s" % args)
        scolar_formsemestre_validation_create(cnx, args)
        # marque sem. utilise pour compenser:
        if formsemestre_id_utilise_pour_compenser:
            assert code == ADC
            args2 = {
                "formsemestre_id": formsemestre_id_utilise_pour_compenser,
                "compense_formsemestre_id": formsemestre_id,
                "etudid": etudid,
            }
            cursor.execute(
                """update scolar_formsemestre_validation
            set compense_formsemestre_id=%(compense_formsemestre_id)s
            where etudid = %(etudid)s and formsemestre_id=%(formsemestre_id)s
            and ue_id is null""",
                args2,
            )
    except:
        cnx.rollback()
        raise


def formsemestre_update_validation_sem(
    cnx,
    formsemestre_id,
    etudid,
    code,
    assidu=True,
    formsemestre_id_utilise_pour_compenser=None,
):
    "Update validation semestre"
    args = {
        "formsemestre_id": formsemestre_id,
        "etudid": etudid,
        "code": code,
        "assidu": assidu,
    }
    log("formsemestre_update_validation_sem: %s" % args)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    to_invalidate = []

    # enleve compensations si necessaire
    # recupere les semestres auparavant utilisés pour invalider les caches
    # correspondants:
    cursor.execute(
        """select formsemestre_id from scolar_formsemestre_validation
    where compense_formsemestre_id=%(formsemestre_id)s and etudid = %(etudid)s""",
        args,
    )
    to_invalidate = [x[0] for x in cursor.fetchall()]
    # suppress:
    cursor.execute(
        """update scolar_formsemestre_validation set compense_formsemestre_id=NULL
    where compense_formsemestre_id=%(formsemestre_id)s and etudid = %(etudid)s""",
        args,
    )
    if formsemestre_id_utilise_pour_compenser:
        assert code == ADC
        # marque sem. utilise pour compenser:
        args2 = {
            "formsemestre_id": formsemestre_id_utilise_pour_compenser,
            "compense_formsemestre_id": formsemestre_id,
            "etudid": etudid,
        }
        cursor.execute(
            """update scolar_formsemestre_validation
        set compense_formsemestre_id=%(compense_formsemestre_id)s
        where etudid = %(etudid)s and formsemestre_id=%(formsemestre_id)s
        and ue_id is null""",
            args2,
        )

    cursor.execute(
        """update scolar_formsemestre_validation
    set code = %(code)s, event_date=DEFAULT, assidu=%(assidu)s
    where etudid = %(etudid)s and formsemestre_id=%(formsemestre_id)s
    and ue_id is null""",
        args,
    )
    return to_invalidate


def formsemestre_validate_ues(formsemestre_id, etudid, code_etat_sem, assiduite):
    """Enregistre codes UE, selon état semestre.
    Les codes UE sont toujours calculés ici, et non passés en paramètres
    car ils ne dépendent que de la note d'UE et de la validation ou non du semestre.
    Les UE des semestres NON ASSIDUS ne sont jamais validées (code AJ).
    """
    valid_semestre = CODES_SEM_VALIDES.get(code_etat_sem, False)
    cnx = ndb.GetDBConnexion(autocommit=False)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_ues, get_etud_ue_status
    ue_ids = [x["ue_id"] for x in nt.get_ues(etudid=etudid, filter_sport=True)]
    for ue_id in ue_ids:
        ue_status = nt.get_etud_ue_status(etudid, ue_id)
        if not assiduite:
            code_ue = AJ
        else:
            # log('%s: %s: ue_status=%s' % (formsemestre_id,ue_id,ue_status))
            if (
                isinstance(ue_status["moy"], float)
                and ue_status["moy"] >= nt.parcours.NOTES_BARRE_VALID_UE
            ):
                code_ue = ADM
            elif not isinstance(ue_status["moy"], float):
                # aucune note (pas de moyenne) dans l'UE: ne la valide pas
                code_ue = None
            elif valid_semestre:
                code_ue = CMP
            else:
                code_ue = AJ
        # log('code_ue=%s' % code_ue)
        if etud_est_inscrit_ue(cnx, etudid, formsemestre_id, ue_id) and code_ue:
            do_formsemestre_validate_ue(
                cnx, nt, formsemestre_id, etudid, ue_id, code_ue
            )

        logdb(
            cnx,
            method="validate_ue",
            etudid=etudid,
            msg="ue_id=%s code=%s" % (ue_id, code_ue),
            commit=False,
        )
    cnx.commit()


def do_formsemestre_validate_ue(
    cnx,
    nt,
    formsemestre_id,
    etudid,
    ue_id,
    code,
    moy_ue=None,
    date=None,
    semestre_id=None,
    is_external=False,
):
    """Ajoute ou change validation UE"""
    args = {
        "formsemestre_id": formsemestre_id,
        "etudid": etudid,
        "ue_id": ue_id,
        "semestre_id": semestre_id,
        "is_external": is_external,
    }
    if date:
        args["event_date"] = date

    # delete existing
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    try:
        cond = "etudid = %(etudid)s and ue_id=%(ue_id)s"
        if formsemestre_id:
            cond += " and formsemestre_id=%(formsemestre_id)s"
        if semestre_id:
            cond += " and semestre_id=%(semestre_id)s"
        cursor.execute("delete from scolar_formsemestre_validation where " + cond, args)
        # insert
        args["code"] = code
        if code == ADM:
            if moy_ue is None:
                # stocke la moyenne d'UE capitalisée:
                moy_ue = nt.get_etud_ue_status(etudid, ue_id)["moy"]
            args["moy_ue"] = moy_ue
        log("formsemestre_validate_ue: %s" % args)
        if code != None:
            scolar_formsemestre_validation_create(cnx, args)
        else:
            log("formsemestre_validate_ue: code is None, not recording validation")
    except:
        cnx.rollback()
        raise


def formsemestre_has_decisions(formsemestre_id):
    """True s'il y a au moins une validation (decision de jury) dans ce semestre
    equivalent to notes_table.sem_has_decisions() but much faster when nt not cached
    """
    cnx = ndb.GetDBConnexion()
    validations = scolar_formsemestre_validation_list(
        cnx, args={"formsemestre_id": formsemestre_id}
    )
    return len(validations) > 0


def etud_est_inscrit_ue(cnx, etudid, formsemestre_id, ue_id):
    """Vrai si l'étudiant est inscrit a au moins un module de cette UE dans ce semestre"""
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT mi.* 
    FROM notes_moduleimpl mi, notes_modules mo, notes_ue ue, notes_moduleimpl_inscription i
    WHERE i.etudid = %(etudid)s 
    and i.moduleimpl_id=mi.id
    and mi.formsemestre_id = %(formsemestre_id)s
    and mi.module_id = mo.id
    and mo.ue_id = %(ue_id)s
    """,
        {"etudid": etudid, "formsemestre_id": formsemestre_id, "ue_id": ue_id},
    )

    return len(cursor.fetchall())


_scolar_autorisation_inscription_editor = ndb.EditableTable(
    "scolar_autorisation_inscription",
    "autorisation_inscription_id",
    ("etudid", "formation_code", "semestre_id", "date", "origin_formsemestre_id"),
    output_formators={"date": ndb.DateISOtoDMY},
    input_formators={"date": ndb.DateDMYtoISO},
)
scolar_autorisation_inscription_list = _scolar_autorisation_inscription_editor.list


def formsemestre_get_autorisation_inscription(etudid, origin_formsemestre_id):
    """Liste des autorisations d'inscription pour cet étudiant
    émanant du semestre indiqué.
    """
    cnx = ndb.GetDBConnexion()
    return scolar_autorisation_inscription_list(
        cnx, {"origin_formsemestre_id": origin_formsemestre_id, "etudid": etudid}
    )


def formsemestre_get_etud_capitalisation(sem, etudid):
    """Liste des UE capitalisées (ADM) correspondant au semestre sem et à l'étudiant.

    Recherche dans les semestres de la même formation (code) avec le même
    semestre_id et une date de début antérieure à celle du semestre mentionné.
    Et aussi les UE externes validées.

    Resultat: [ { 'formsemestre_id' :
                  'ue_id' : ue_id dans le semestre origine
                  'ue_code' :
                  'moy_ue' :
                  'event_date' :
                  'is_external'
                  } ]
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """select distinct SFV.*, ue.ue_code from notes_ue ue, notes_formations nf, 
        notes_formations nf2, scolar_formsemestre_validation SFV, notes_formsemestre sem

    WHERE ue.formation_id = nf.id   
    and nf.formation_code = nf2.formation_code
    and nf2.id=%(formation_id)s

    and SFV.ue_id = ue.id
    and SFV.code = 'ADM'
    and SFV.etudid = %(etudid)s
    
    and (  (sem.id = SFV.formsemestre_id
           and sem.date_debut < %(date_debut)s
           and sem.semestre_id = %(semestre_id)s )
         or (
             ((SFV.formsemestre_id is NULL) OR (SFV.is_external)) -- les UE externes ou "anterieures"
             AND (SFV.semestre_id is NULL OR SFV.semestre_id=%(semestre_id)s)
           ) )
    """,
        {
            "etudid": etudid,
            "formation_id": sem["formation_id"],
            "semestre_id": sem["semestre_id"],
            "date_debut": ndb.DateDMYtoISO(sem["date_debut"]),
        },
    )

    return cursor.dictfetchall()


def list_formsemestre_utilisateurs_uecap(formsemestre_id):
    """Liste des formsemestres pouvant utiliser une UE capitalisee de ce semestre
    (et qui doivent donc etre sortis du cache si l'on modifie ce
    semestre): meme code formation, meme semestre_id, date posterieure"""
    cnx = ndb.GetDBConnexion()
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT sem.id
    FROM notes_formsemestre sem, notes_formations F
    WHERE sem.formation_id = F.id
    and F.formation_code = %(formation_code)s
    and sem.semestre_id = %(semestre_id)s
    and sem.date_debut >= %(date_debut)s
    and sem.id != %(formsemestre_id)s;
    """,
        {
            "formation_code": F["formation_code"],
            "semestre_id": sem["semestre_id"],
            "formsemestre_id": formsemestre_id,
            "date_debut": ndb.DateDMYtoISO(sem["date_debut"]),
        },
    )
    return [x[0] for x in cursor.fetchall()]
