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

"""Calcul des moyennes de module
"""
import pprint
import traceback

from flask import url_for, g
import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.sco_utils import (
    NOTES_ATTENTE,
    NOTES_NEUTRALISE,
    EVALUATION_NORMALE,
    EVALUATION_RATTRAPAGE,
    EVALUATION_SESSION2,
)
from app.scodoc.sco_exceptions import ScoValueError
from app import log
from app.scodoc import sco_abs
from app.scodoc import sco_edit_module
from app.scodoc import sco_evaluations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_formulas
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_etud


def moduleimpl_has_expression(mod):
    "True if we should use a user-defined expression"
    expr = mod["computation_expr"]
    if not expr:
        return False
    expr = expr.strip()
    if not expr or expr[0] == "#":
        return False
    return True


def formsemestre_expressions_use_abscounts(formsemestre_id):
    """True si les notes de ce semestre dépendent des compteurs d'absences.
    Cela n'est normalement pas le cas, sauf si des formules utilisateur
    utilisent ces compteurs.
    """
    # check presence of 'nbabs' in expressions
    ab = "nb_abs"  # chaine recherchée
    cnx = ndb.GetDBConnexion()
    # 1- moyennes d'UE:
    elist = formsemestre_ue_computation_expr_list(
        cnx, {"formsemestre_id": formsemestre_id}
    )
    for e in elist:
        expr = e["computation_expr"].strip()
        if expr and expr[0] != "#" and ab in expr:
            return True
    # 2- moyennes de modules
    for mod in sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id):
        if moduleimpl_has_expression(mod) and ab in mod["computation_expr"]:
            return True
    return False


_formsemestre_ue_computation_exprEditor = ndb.EditableTable(
    "notes_formsemestre_ue_computation_expr",
    "notes_formsemestre_ue_computation_expr_id",
    (
        "notes_formsemestre_ue_computation_expr_id",
        "formsemestre_id",
        "ue_id",
        "computation_expr",
    ),
    html_quote=False,  # does nt automatically quote
)
formsemestre_ue_computation_expr_create = _formsemestre_ue_computation_exprEditor.create
formsemestre_ue_computation_expr_delete = _formsemestre_ue_computation_exprEditor.delete
formsemestre_ue_computation_expr_list = _formsemestre_ue_computation_exprEditor.list
formsemestre_ue_computation_expr_edit = _formsemestre_ue_computation_exprEditor.edit


def get_ue_expression(formsemestre_id, ue_id, cnx, html_quote=False):
    """Returns UE expression (formula), or None if no expression has been defined"""
    el = formsemestre_ue_computation_expr_list(
        cnx, {"formsemestre_id": formsemestre_id, "ue_id": ue_id}
    )
    if not el:
        return None
    else:
        expr = el[0]["computation_expr"].strip()
        if expr and expr[0] != "#":
            if html_quote:
                expr = ndb.quote_html(expr)
            return expr
        else:
            return None


def compute_user_formula(
    sem,
    etudid,
    moy,
    moy_valid,
    notes,
    coefs,
    coefs_mask,
    formula,
    diag_info=None,  # infos supplementaires a placer ds messages d'erreur
    use_abs=True,
):
    """Calcul moyenne a partir des notes et coefs, en utilisant la formule utilisateur (une chaine).
    Retourne moy, et en cas d'erreur met à jour diag_info (msg)
    """
    if use_abs:
        nbabs, nbabs_just = sco_abs.get_abs_count(etudid, sem)
    else:
        nbabs, nbabs_just = 0, 0
    try:
        moy_val = float(moy)
    except ValueError:
        moy_val = 0.0  # 0. when no valid value
    variables = {
        "cmask": coefs_mask,  # NoteVector(v=coefs_mask),
        "notes": notes,  # NoteVector(v=notes),
        "coefs": coefs,  # NoteVector(v=coefs),
        "moy": moy,
        "moy_valid": moy_valid,  # deprecated, use moy_is_valid
        "moy_is_valid": moy_valid,  # True si moyenne numerique
        "moy_val": moy_val,
        "nb_abs": float(nbabs),
        "nb_abs_just": float(nbabs_just),
        "nb_abs_nojust": float(nbabs - nbabs_just),
    }
    try:
        formula = formula.replace("\n", "").replace("\r", "")
        # log('expression : %s\nvariables=%s\n' % (formula, variables)) #  debug
        user_moy = sco_formulas.eval_user_expression(formula, variables)
        # log('user_moy=%s' % user_moy)
        if user_moy != "NA":
            user_moy = float(user_moy)
            if (user_moy > 20) or (user_moy < 0):
                etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]

                raise ScoValueError(
                    f"""
                    Valeur moyenne {user_moy} hors limite pour
                    <a href="{url_for('notes.formsemestre_bulletinetud',
                    scodoc_dept=g.scodoc_dept,
                    formsemestre_id=sem["formsemestre_id"],
                    etudid=etudid
                    )}">{etud["nomprenom"]}</a>"""
                )
    except:
        log(
            "invalid expression : %s\nvariables=%s\n"
            % (formula, pprint.pformat(variables))
        )
        tb = traceback.format_exc()
        log("Exception during evaluation:\n%s\n" % tb)
        diag_info.update({"msg": tb.splitlines()[-1]})
        user_moy = "ERR"

    # log('formula=%s\nvariables=%s\nmoy=%s\nuser_moy=%s' % (formula, variables, moy, user_moy))

    return user_moy


def compute_moduleimpl_moyennes(nt, modimpl):
    """Retourne dict { etudid : note_moyenne } pour tous les etuds inscrits
    au moduleimpl mod, la liste des evaluations "valides" (toutes notes entrées
    ou en attente), et att (vrai s'il y a des notes en attente dans ce module).
    La moyenne est calculée en utilisant les coefs des évaluations.
    Les notes NEUTRES (abs. excuses) ne sont pas prises en compte.
    Les notes ABS sont remplacées par des zéros.
    S'il manque des notes et que le coef n'est pas nul,
    la moyenne n'est pas calculée: NA
    Ne prend en compte que les evaluations où toutes les notes sont entrées.
    Le résultat note_moyenne est une note sur 20.
    """
    diag_info = {}  # message d'erreur formule
    moduleimpl_id = modimpl["moduleimpl_id"]
    is_malus = modimpl["module"]["module_type"] == scu.MODULE_MALUS
    sem = sco_formsemestre.get_formsemestre(modimpl["formsemestre_id"])
    etudids = sco_moduleimpl.moduleimpl_listeetuds(
        moduleimpl_id
    )  # tous, y compris demissions
    # Inscrits au semestre (pour traiter les demissions):
    inssem_set = set(
        [
            x["etudid"]
            for x in sco_formsemestre_inscriptions.do_formsemestre_inscription_listinscrits(
                modimpl["formsemestre_id"]
            )
        ]
    )
    insmod_set = inssem_set.intersection(etudids)  # inscrits au semestre et au module

    evals = nt.get_mod_evaluation_etat_list(moduleimpl_id)
    evals.sort(
        key=lambda x: (x["numero"], x["jour"], x["heure_debut"])
    )  # la plus ancienne en tête

    user_expr = moduleimpl_has_expression(modimpl)
    attente = False
    # recupere les notes de toutes les evaluations
    eval_rattr = None
    for e in evals:
        e["nb_inscrits"] = e["etat"]["nb_inscrits"]
        NotesDB = sco_evaluations.do_evaluation_get_all_notes(
            e["evaluation_id"]
        )  # toutes, y compris demissions
        # restreint aux étudiants encore inscrits à ce module
        notes = [
            NotesDB[etudid]["value"] for etudid in NotesDB if (etudid in insmod_set)
        ]
        e["nb_notes"] = len(notes)
        e["nb_abs"] = len([x for x in notes if x is None])
        e["nb_neutre"] = len([x for x in notes if x == NOTES_NEUTRALISE])
        e["nb_att"] = len([x for x in notes if x == NOTES_ATTENTE])
        e["notes"] = NotesDB

        if e["etat"]["evalattente"]:
            attente = True
        if (
            e["evaluation_type"] == EVALUATION_RATTRAPAGE
            or e["evaluation_type"] == EVALUATION_SESSION2
        ):
            if eval_rattr:
                # !!! plusieurs rattrapages !
                diag_info.update(
                    {
                        "msg": "plusieurs évaluations de rattrapage !",
                        "moduleimpl_id": moduleimpl_id,
                    }
                )
            eval_rattr = e

    # Les modules MALUS ne sont jamais considérés en attente
    if is_malus:
        attente = False

    # filtre les evals valides (toutes les notes entrées)
    valid_evals = [
        e
        for e in evals
        if (
            (e["etat"]["evalcomplete"] or e["etat"]["evalattente"])
            and (e["note_max"] > 0)
        )
    ]
    #
    R = {}
    formula = scu.unescape_html(modimpl["computation_expr"])
    formula_use_abs = "abs" in formula

    for etudid in insmod_set:  # inscrits au semestre et au module
        sum_notes = 0.0
        sum_coefs = 0.0
        nb_missing = 0
        for e in valid_evals:
            if e["evaluation_type"] != EVALUATION_NORMALE:
                continue
            if etudid in e["notes"]:
                note = e["notes"][etudid]["value"]
                if note is None:  # ABSENT
                    note = 0
                if note != NOTES_NEUTRALISE and note != NOTES_ATTENTE:
                    sum_notes += (note * 20.0 / e["note_max"]) * e["coefficient"]
                    sum_coefs += e["coefficient"]
            else:
                # il manque une note ! (si publish_incomplete, cela peut arriver, on ignore)
                if e["coefficient"] > 0 and not e["publish_incomplete"]:
                    nb_missing += 1
                    # ne devrait pas arriver ?
                    log("\nXXX SCM298\n")
        if nb_missing == 0 and sum_coefs > 0:
            if sum_coefs > 0:
                R[etudid] = sum_notes / sum_coefs
                moy_valid = True
            else:
                R[etudid] = "NA"
                moy_valid = False
        else:
            R[etudid] = "NA"
            moy_valid = False

        if user_expr:
            # recalcule la moyenne en utilisant la formule utilisateur
            notes = []
            coefs = []
            coefs_mask = []  # 0/1, 0 si coef a ete annulé
            nb_notes = 0  # nombre de notes valides
            for e in evals:
                if (
                    (e["etat"]["evalcomplete"] or e["etat"]["evalattente"])
                    and etudid in e["notes"]
                ) and (e["note_max"] > 0):
                    note = e["notes"][etudid]["value"]
                    if note is None:
                        note = 0
                    if note != NOTES_NEUTRALISE and note != NOTES_ATTENTE:
                        notes.append(note * 20.0 / e["note_max"])
                        coefs.append(e["coefficient"])
                        coefs_mask.append(1)
                        nb_notes += 1
                    else:
                        notes.append(0.0)
                        coefs.append(0.0)
                        coefs_mask.append(0)
                else:
                    notes.append(0.0)
                    coefs.append(0.0)
                    coefs_mask.append(0)
            if nb_notes > 0 or formula_use_abs:
                user_moy = compute_user_formula(
                    sem,
                    etudid,
                    R[etudid],
                    moy_valid,
                    notes,
                    coefs,
                    coefs_mask,
                    formula,
                    diag_info=diag_info,
                    use_abs=formula_use_abs,
                )
                if diag_info:
                    diag_info["moduleimpl_id"] = moduleimpl_id
                R[etudid] = user_moy
        # Note de rattrapage ou deuxième session ?
        if eval_rattr:
            if etudid in eval_rattr["notes"]:
                note = eval_rattr["notes"][etudid]["value"]
                if note != None and note != NOTES_NEUTRALISE and note != NOTES_ATTENTE:
                    if not isinstance(R[etudid], float):
                        R[etudid] = note
                    else:
                        note_sur_20 = note * 20.0 / eval_rattr["note_max"]
                        if eval_rattr["evaluation_type"] == EVALUATION_RATTRAPAGE:
                            # rattrapage classique: prend la meilleure note entre moyenne
                            # module et note eval rattrapage
                            if (R[etudid] == "NA") or (note_sur_20 > R[etudid]):
                                # log('note_sur_20=%s' % note_sur_20)
                                R[etudid] = note_sur_20
                        elif eval_rattr["evaluation_type"] == EVALUATION_SESSION2:
                            # rattrapage type "deuxième session": remplace la note moyenne
                            R[etudid] = note_sur_20

    return R, valid_evals, attente, diag_info


def formsemestre_compute_modimpls_moyennes(nt, formsemestre_id):
    """retourne dict { moduleimpl_id : { etudid, note_moyenne_dans_ce_module } },
    la liste des moduleimpls, la liste des evaluations valides,
    liste des moduleimpls  avec notes en attente.
    """
    # sem = sco_formsemestre.get_formsemestre( formsemestre_id)
    # inscr = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
    #    args={"formsemestre_id": formsemestre_id}
    # )
    # etudids = [x["etudid"] for x in inscr]
    modimpls = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
    # recupere les moyennes des etudiants de tous les modules
    D = {}
    valid_evals = []
    valid_evals_per_mod = {}  # { moduleimpl_id : eval }
    mods_att = []
    expr_diags = []
    for modimpl in modimpls:
        mod = sco_edit_module.module_list(args={"module_id": modimpl["module_id"]})[0]
        modimpl["module"] = mod  # add module dict to moduleimpl (used by nt)
        moduleimpl_id = modimpl["moduleimpl_id"]
        assert moduleimpl_id not in D
        (
            D[moduleimpl_id],
            valid_evals_mod,
            attente,
            expr_diag,
        ) = compute_moduleimpl_moyennes(nt, modimpl)
        valid_evals_per_mod[moduleimpl_id] = valid_evals_mod
        valid_evals += valid_evals_mod
        if attente:
            mods_att.append(modimpl)
        if expr_diag:
            expr_diags.append(expr_diag)
    #
    return D, modimpls, valid_evals_per_mod, valid_evals, mods_att, expr_diags
