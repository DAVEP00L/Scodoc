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
#   Emmanuel Viennet      emmanuel.viennet@gmail.com
#
##############################################################################

"""Evaluations
"""
import datetime
import operator
import pprint
import time
import urllib

import flask
from flask import url_for
from flask import g
from flask_login import current_user
from flask import request

from app import log
import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
import sco_version
from app.scodoc.gen_tables import GenTable
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc import html_sco_header
from app.scodoc import sco_abs
from app.scodoc import sco_cache
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_news
from app.scodoc import sco_permissions_check
from app.scodoc import sco_preferences
from app.scodoc import sco_users


# --------------------------------------------------------------------
#
#    MISC AUXILIARY FUNCTIONS
#
# --------------------------------------------------------------------
def notes_moyenne_median_mini_maxi(notes):
    "calcule moyenne et mediane d'une liste de valeurs (floats)"
    notes = [
        x
        for x in notes
        if (x != None) and (x != scu.NOTES_NEUTRALISE) and (x != scu.NOTES_ATTENTE)
    ]
    n = len(notes)
    if not n:
        return None, None, None, None
    moy = sum(notes) / n
    median = ListMedian(notes)
    mini = min(notes)
    maxi = max(notes)
    return moy, median, mini, maxi


def ListMedian(L):
    """Median of a list L"""
    n = len(L)
    if not n:
        raise ValueError("empty list")
    L.sort()
    if n % 2:
        return L[n // 2]
    else:
        return (L[n // 2] + L[n // 2 - 1]) / 2


# --------------------------------------------------------------------
_evaluationEditor = ndb.EditableTable(
    "notes_evaluation",
    "evaluation_id",
    (
        "evaluation_id",
        "moduleimpl_id",
        "jour",
        "heure_debut",
        "heure_fin",
        "description",
        "note_max",
        "coefficient",
        "visibulletin",
        "publish_incomplete",
        "evaluation_type",
        "numero",
    ),
    sortkey="numero desc, jour desc, heure_debut desc",  # plus recente d'abord
    output_formators={
        "jour": ndb.DateISOtoDMY,
        "numero": ndb.int_null_is_zero,
    },
    input_formators={
        "jour": ndb.DateDMYtoISO,
        "heure_debut": ndb.TimetoISO8601,  # converti par do_evaluation_list
        "heure_fin": ndb.TimetoISO8601,  # converti par do_evaluation_list
        "visibulletin": bool,
        "publish_incomplete": bool,
        "evaluation_type": int,
    },
)


def do_evaluation_list(args, sortkey=None):
    """List evaluations, sorted by numero (or most recent date first).

    Ajoute les champs:
    'duree' : '2h30'
    'matin' : 1 (commence avant 12:00) ou 0
    'apresmidi' : 1 (termine après 12:00) ou 0
    'descrheure' : ' de 15h00 à 16h30'
    """
    cnx = ndb.GetDBConnexion()
    evals = _evaluationEditor.list(cnx, args, sortkey=sortkey)
    # calcule duree (chaine de car.) de chaque evaluation et ajoute jouriso, matin, apresmidi
    for e in evals:
        heure_debut_dt = e["heure_debut"] or datetime.time(
            8, 00
        )  # au cas ou pas d'heure (note externe?)
        heure_fin_dt = e["heure_fin"] or datetime.time(8, 00)
        e["heure_debut"] = ndb.TimefromISO8601(e["heure_debut"])
        e["heure_fin"] = ndb.TimefromISO8601(e["heure_fin"])
        e["jouriso"] = ndb.DateDMYtoISO(e["jour"])
        heure_debut, heure_fin = e["heure_debut"], e["heure_fin"]
        d = ndb.TimeDuration(heure_debut, heure_fin)
        if d is not None:
            m = d % 60
            e["duree"] = "%dh" % (d / 60)
            if m != 0:
                e["duree"] += "%02d" % m
        else:
            e["duree"] = ""
        if heure_debut and (not heure_fin or heure_fin == heure_debut):
            e["descrheure"] = " à " + heure_debut
        elif heure_debut and heure_fin:
            e["descrheure"] = " de %s à %s" % (heure_debut, heure_fin)
        else:
            e["descrheure"] = ""
        # matin, apresmidi: utile pour se referer aux absences:
        if heure_debut_dt < datetime.time(12, 00):
            e["matin"] = 1
        else:
            e["matin"] = 0
        if heure_fin_dt > datetime.time(12, 00):
            e["apresmidi"] = 1
        else:
            e["apresmidi"] = 0

    return evals


def do_evaluation_list_in_formsemestre(formsemestre_id):
    "list evaluations in this formsemestre"
    mods = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
    evals = []
    for mod in mods:
        evals += do_evaluation_list(args={"moduleimpl_id": mod["moduleimpl_id"]})
    return evals


def _check_evaluation_args(args):
    "Check coefficient, dates and duration, raises exception if invalid"
    moduleimpl_id = args["moduleimpl_id"]
    # check bareme
    note_max = args.get("note_max", None)
    if note_max is None:
        raise ScoValueError("missing note_max")
    try:
        note_max = float(note_max)
    except ValueError:
        raise ScoValueError("Invalid note_max value")
    if note_max < 0:
        raise ScoValueError("Invalid note_max value (must be positive or null)")
    # check coefficient
    coef = args.get("coefficient", None)
    if coef is None:
        raise ScoValueError("missing coefficient")
    try:
        coef = float(coef)
    except ValueError:
        raise ScoValueError("Invalid coefficient value")
    if coef < 0:
        raise ScoValueError("Invalid coefficient value (must be positive or null)")
    # check date
    jour = args.get("jour", None)
    args["jour"] = jour
    if jour:
        M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
        sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
        d, m, y = [int(x) for x in sem["date_debut"].split("/")]
        date_debut = datetime.date(y, m, d)
        d, m, y = [int(x) for x in sem["date_fin"].split("/")]
        date_fin = datetime.date(y, m, d)
        # passe par ndb.DateDMYtoISO pour avoir date pivot
        y, m, d = [int(x) for x in ndb.DateDMYtoISO(jour).split("-")]
        jour = datetime.date(y, m, d)
        if (jour > date_fin) or (jour < date_debut):
            raise ScoValueError(
                "La date de l'évaluation (%s/%s/%s) n'est pas dans le semestre !"
                % (d, m, y)
            )
    heure_debut = args.get("heure_debut", None)
    args["heure_debut"] = heure_debut
    heure_fin = args.get("heure_fin", None)
    args["heure_fin"] = heure_fin
    if jour and ((not heure_debut) or (not heure_fin)):
        raise ScoValueError("Les heures doivent être précisées")
    d = ndb.TimeDuration(heure_debut, heure_fin)
    if d and ((d < 0) or (d > 60 * 12)):
        raise ScoValueError("Heures de l'évaluation incohérentes !")


def do_evaluation_create(
    moduleimpl_id=None,
    jour=None,
    heure_debut=None,
    heure_fin=None,
    description=None,
    note_max=None,
    coefficient=None,
    visibulletin=None,
    publish_incomplete=None,
    evaluation_type=None,
    numero=None,
    **kw,  # ceci pour absorber les arguments excedentaires de tf #sco8
):
    """Create an evaluation"""
    if not sco_permissions_check.can_edit_evaluation(moduleimpl_id=moduleimpl_id):
        raise AccessDenied(
            "Modification évaluation impossible pour %s" % current_user.get_nomplogin()
        )
    args = locals()
    log("do_evaluation_create: args=" + str(args))
    _check_evaluation_args(args)
    # Check numeros
    module_evaluation_renumber(moduleimpl_id, only_if_unumbered=True)
    if not "numero" in args or args["numero"] is None:
        n = None
        # determine le numero avec la date
        # Liste des eval existantes triees par date, la plus ancienne en tete
        ModEvals = do_evaluation_list(
            args={"moduleimpl_id": moduleimpl_id},
            sortkey="jour asc, heure_debut asc",
        )
        if args["jour"]:
            next_eval = None
            t = (
                ndb.DateDMYtoISO(args["jour"], null_is_empty=True),
                ndb.TimetoISO8601(args["heure_debut"], null_is_empty=True),
            )
            for e in ModEvals:
                if (
                    ndb.DateDMYtoISO(e["jour"], null_is_empty=True),
                    ndb.TimetoISO8601(e["heure_debut"], null_is_empty=True),
                ) > t:
                    next_eval = e
                    break
            if next_eval:
                n = module_evaluation_insert_before(ModEvals, next_eval)
            else:
                n = None  # a placer en fin
        if n is None:  # pas de date ou en fin:
            if ModEvals:
                log(pprint.pformat(ModEvals[-1]))
                n = ModEvals[-1]["numero"] + 1
            else:
                n = 0  # the only one
        # log("creating with numero n=%d" % n)
        args["numero"] = n

    #
    cnx = ndb.GetDBConnexion()
    r = _evaluationEditor.create(cnx, args)

    # news
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    mod["moduleimpl_id"] = M["moduleimpl_id"]
    mod["url"] = "Notes/moduleimpl_status?moduleimpl_id=%(moduleimpl_id)s" % mod
    sco_news.add(
        typ=sco_news.NEWS_NOTE,
        object=moduleimpl_id,
        text='Création d\'une évaluation dans <a href="%(url)s">%(titre)s</a>' % mod,
        url=mod["url"],
    )

    return r


def do_evaluation_edit(args):
    "edit an evaluation"
    evaluation_id = args["evaluation_id"]
    the_evals = do_evaluation_list({"evaluation_id": evaluation_id})
    if not the_evals:
        raise ValueError("evaluation inexistante !")
    moduleimpl_id = the_evals[0]["moduleimpl_id"]
    if not sco_permissions_check.can_edit_evaluation(moduleimpl_id=moduleimpl_id):
        raise AccessDenied(
            "Modification évaluation impossible pour %s" % current_user.get_nomplogin()
        )
    args["moduleimpl_id"] = moduleimpl_id
    _check_evaluation_args(args)

    cnx = ndb.GetDBConnexion()
    _evaluationEditor.edit(cnx, args)
    # inval cache pour ce semestre
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    sco_cache.invalidate_formsemestre(formsemestre_id=M["formsemestre_id"])


def do_evaluation_delete(evaluation_id):
    "delete evaluation"
    the_evals = do_evaluation_list({"evaluation_id": evaluation_id})
    if not the_evals:
        raise ValueError("evaluation inexistante !")
    moduleimpl_id = the_evals[0]["moduleimpl_id"]
    if not sco_permissions_check.can_edit_evaluation(moduleimpl_id=moduleimpl_id):
        raise AccessDenied(
            "Modification évaluation impossible pour %s" % current_user.get_nomplogin()
        )
    NotesDB = do_evaluation_get_all_notes(evaluation_id)  # { etudid : value }
    notes = [x["value"] for x in NotesDB.values()]
    if notes:
        raise ScoValueError(
            "Impossible de supprimer cette évaluation: il reste des notes"
        )

    cnx = ndb.GetDBConnexion()

    _evaluationEditor.delete(cnx, evaluation_id)
    # inval cache pour ce semestre
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    sco_cache.invalidate_formsemestre(formsemestre_id=M["formsemestre_id"])
    # news
    mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    mod["moduleimpl_id"] = M["moduleimpl_id"]
    mod["url"] = (
        scu.NotesURL() + "/moduleimpl_status?moduleimpl_id=%(moduleimpl_id)s" % mod
    )
    sco_news.add(
        typ=sco_news.NEWS_NOTE,
        object=moduleimpl_id,
        text='Suppression d\'une évaluation dans <a href="%(url)s">%(titre)s</a>' % mod,
        url=mod["url"],
    )


def do_evaluation_etat(evaluation_id, partition_id=None, select_first_partition=False):
    """donne infos sur l'etat du evaluation
    { nb_inscrits, nb_notes, nb_abs, nb_neutre, nb_att,
    moyenne, mediane, mini, maxi,
    date_last_modif, gr_complets, gr_incomplets, evalcomplete }
    evalcomplete est vrai si l'eval est complete (tous les inscrits
    à ce module ont des notes)
    evalattente est vrai s'il ne manque que des notes en attente
    """
    nb_inscrits = len(
        sco_groups.do_evaluation_listeetuds_groups(evaluation_id, getallstudents=True)
    )
    NotesDB = do_evaluation_get_all_notes(evaluation_id)  # { etudid : value }
    notes = [x["value"] for x in NotesDB.values()]
    nb_abs = len([x for x in notes if x is None])
    nb_neutre = len([x for x in notes if x == scu.NOTES_NEUTRALISE])
    nb_att = len([x for x in notes if x == scu.NOTES_ATTENTE])
    moy_num, median_num, mini_num, maxi_num = notes_moyenne_median_mini_maxi(notes)
    if moy_num is None:
        median, moy = "", ""
        median_num, moy_num = None, None
        mini, maxi = "", ""
        mini_num, maxi_num = None, None
    else:
        median = scu.fmt_note(median_num)
        moy = scu.fmt_note(moy_num)
        mini = scu.fmt_note(mini_num)
        maxi = scu.fmt_note(maxi_num)
    # cherche date derniere modif note
    if len(NotesDB):
        t = [x["date"] for x in NotesDB.values()]
        last_modif = max(t)
    else:
        last_modif = None
    # ---- Liste des groupes complets et incomplets
    E = do_evaluation_list(args={"evaluation_id": evaluation_id})[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    is_malus = Mod["module_type"] == scu.MODULE_MALUS  # True si module de malus
    formsemestre_id = M["formsemestre_id"]
    # Si partition_id is None, prend 'all' ou bien la premiere:
    if partition_id is None:
        if select_first_partition:
            partitions = sco_groups.get_partitions_list(formsemestre_id)
            partition = partitions[0]
        else:
            partition = sco_groups.get_default_partition(formsemestre_id)
        partition_id = partition["partition_id"]

    # Il faut considerer les inscriptions au semestre
    # (pour avoir l'etat et le groupe) et aussi les inscriptions
    # au module (pour gerer les modules optionnels correctement)
    insem = sco_formsemestre_inscriptions.do_formsemestre_inscription_listinscrits(
        formsemestre_id
    )
    insmod = sco_moduleimpl.do_moduleimpl_inscription_list(
        moduleimpl_id=E["moduleimpl_id"]
    )
    insmodset = set([x["etudid"] for x in insmod])
    # retire de insem ceux qui ne sont pas inscrits au module
    ins = [i for i in insem if i["etudid"] in insmodset]

    # Nombre de notes valides d'étudiants inscrits au module
    # (car il peut y avoir des notes d'étudiants désinscrits depuis l'évaluation)
    nb_notes = len(insmodset.intersection(NotesDB))
    nb_notes_total = len(NotesDB)

    # On considere une note "manquante" lorsqu'elle n'existe pas
    # ou qu'elle est en attente (ATT)
    GrNbMissing = scu.DictDefault()  # group_id : nb notes manquantes
    GrNotes = scu.DictDefault(defaultvalue=[])  # group_id: liste notes valides
    TotalNbMissing = 0
    TotalNbAtt = 0
    groups = {}  # group_id : group
    etud_groups = sco_groups.get_etud_groups_in_partition(partition_id)

    for i in ins:
        group = etud_groups.get(i["etudid"], None)
        if group and not group["group_id"] in groups:
            groups[group["group_id"]] = group
        #
        isMissing = False
        if i["etudid"] in NotesDB:
            val = NotesDB[i["etudid"]]["value"]
            if val == scu.NOTES_ATTENTE:
                isMissing = True
                TotalNbAtt += 1
            if group:
                GrNotes[group["group_id"]].append(val)
        else:
            if group:
                _ = GrNotes[group["group_id"]]  # create group
            isMissing = True
        if isMissing:
            TotalNbMissing += 1
            if group:
                GrNbMissing[group["group_id"]] += 1

    gr_incomplets = [x for x in GrNbMissing.keys()]
    gr_incomplets.sort()
    if (
        (TotalNbMissing > 0)
        and (E["evaluation_type"] != scu.EVALUATION_RATTRAPAGE)
        and (E["evaluation_type"] != scu.EVALUATION_SESSION2)
        and not is_malus
    ):
        complete = False
    else:
        complete = True
    if (
        TotalNbMissing > 0
        and ((TotalNbMissing == TotalNbAtt) or E["publish_incomplete"])
        and not is_malus
    ):
        evalattente = True
    else:
        evalattente = False
    # mais ne met pas en attente les evals immediates sans aucune notes:
    if E["publish_incomplete"] and nb_notes == 0:
        evalattente = False

    # Calcul moyenne dans chaque groupe de TD
    gr_moyennes = []  # group : {moy,median, nb_notes}
    for group_id in GrNotes.keys():
        notes = GrNotes[group_id]
        gr_moy, gr_median, gr_mini, gr_maxi = notes_moyenne_median_mini_maxi(notes)
        gr_moyennes.append(
            {
                "group_id": group_id,
                "group_name": groups[group_id]["group_name"],
                "gr_moy_num": gr_moy,
                "gr_moy": scu.fmt_note(gr_moy),
                "gr_median_num": gr_median,
                "gr_median": scu.fmt_note(gr_median),
                "gr_mini": scu.fmt_note(gr_mini),
                "gr_maxi": scu.fmt_note(gr_maxi),
                "gr_mini_num": gr_mini,
                "gr_maxi_num": gr_maxi,
                "gr_nb_notes": len(notes),
                "gr_nb_att": len([x for x in notes if x == scu.NOTES_ATTENTE]),
            }
        )
    gr_moyennes.sort(key=operator.itemgetter("group_name"))

    # retourne mapping
    return {
        "evaluation_id": evaluation_id,
        "nb_inscrits": nb_inscrits,
        "nb_notes": nb_notes,  # nb notes etudiants inscrits
        "nb_notes_total": nb_notes_total,  # nb de notes (incluant desinscrits)
        "nb_abs": nb_abs,
        "nb_neutre": nb_neutre,
        "nb_att": nb_att,
        "moy": moy,
        "moy_num": moy_num,
        "median": median,
        "mini": mini,
        "mini_num": mini_num,
        "maxi": maxi,
        "maxi_num": maxi_num,
        "median_num": median_num,
        "last_modif": last_modif,
        "gr_incomplets": gr_incomplets,
        "gr_moyennes": gr_moyennes,
        "groups": groups,
        "evalcomplete": complete,
        "evalattente": evalattente,
        "is_malus": is_malus,
    }


def do_evaluation_list_in_sem(formsemestre_id, with_etat=True):
    """Liste les evaluations de tous les modules de ce semestre.
       Donne pour chaque eval son état (voir do_evaluation_etat)
       { evaluation_id,nb_inscrits, nb_notes, nb_abs, nb_neutre, moy, median, last_modif ... }

       Exemple:
       [ {
       'coefficient': 1.0,
       'description': 'QCM et cas pratiques',
       'etat': {'evalattente': False,
             'evalcomplete': True,
             'evaluation_id': 'GEAEVAL82883',
             'gr_incomplets': [],
             'gr_moyennes': [{'gr_median': '12.00',
                              'gr_median_num' : 12.,
                              'gr_moy': '11.88',
                              'gr_moy_num' : 11.88,
                              'gr_nb_att': 0,
                              'gr_nb_notes': 166,
                              'group_id': 'GEAG266762',
                              'group_name': None}],
             'groups': {'GEAG266762': {'etudid': 'GEAEID80603',
                                       'group_id': 'GEAG266762',
                                       'group_name': None,
                                       'partition_id': 'GEAP266761'}
              },
             'last_modif': datetime.datetime(2015, 12, 3, 15, 15, 16),
             'median': '12.00',
             'moy': '11.84',
             'nb_abs': 2,
             'nb_att': 0,
             'nb_inscrits': 166,
             'nb_neutre': 0,
             'nb_notes': 168,
             'nb_notes_total': 169
     },
    'evaluation_id': 'GEAEVAL82883',
    'evaluation_type': 0,
    'heure_debut': datetime.time(8, 0),
    'heure_fin': datetime.time(9, 30),
    'jour': datetime.date(2015, 11, 3), // vide => 1/1/1
    'moduleimpl_id': 'GEAMIP80490',
    'note_max': 20.0,
    'numero': 0,
    'publish_incomplete': 0,
    'visibulletin': 1} ]

    """
    req = """SELECT E.id AS evaluation_id, E.* 
    FROM notes_evaluation E, notes_moduleimpl MI 
    WHERE MI.formsemestre_id = %(formsemestre_id)s 
    and MI.id = E.moduleimpl_id 
    ORDER BY MI.id, numero desc, jour desc, heure_debut DESC
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    res = cursor.dictfetchall()
    # etat de chaque evaluation:
    for r in res:
        r["jour"] = r["jour"] or datetime.date(1900, 1, 1)  # pour les comparaisons
        if with_etat:
            r["etat"] = do_evaluation_etat(r["evaluation_id"])

    return res


# ancien _notes_getall
def do_evaluation_get_all_notes(
    evaluation_id, table="notes_notes", filter_suppressed=True, by_uid=None
):
    """Toutes les notes pour une evaluation: { etudid : { 'value' : value, 'date' : date ... }}
    Attention: inclut aussi les notes des étudiants qui ne sont plus inscrits au module.
    """
    do_cache = (
        filter_suppressed and table == "notes_notes" and (by_uid is None)
    )  # pas de cache pour (rares) appels via undo_notes ou specifiant un enseignant
    if do_cache:
        r = sco_cache.EvaluationCache.get(evaluation_id)
        if r != None:
            return r
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cond = " where evaluation_id=%(evaluation_id)s"
    if by_uid:
        cond += " and uid=%(by_uid)s"

    cursor.execute(
        "select * from " + table + cond,
        {"evaluation_id": evaluation_id, "by_uid": by_uid},
    )
    res = cursor.dictfetchall()
    d = {}
    if filter_suppressed:
        for x in res:
            if x["value"] != scu.NOTES_SUPPRESS:
                d[x["etudid"]] = x
    else:
        for x in res:
            d[x["etudid"]] = x
    if do_cache:
        status = sco_cache.EvaluationCache.set(evaluation_id, d)
        if not status:
            log(f"Warning: EvaluationCache.set: {evaluation_id}\t{status}")
    return d


def _eval_etat(evals):
    """evals: list of mappings (etats)
    -> nb_eval_completes, nb_evals_en_cours,
    nb_evals_vides, date derniere modif

    Une eval est "complete" ssi tous les etudiants *inscrits* ont une note.

    """
    nb_evals_completes, nb_evals_en_cours, nb_evals_vides = 0, 0, 0
    dates = []
    for e in evals:
        if e["etat"]["evalcomplete"]:
            nb_evals_completes += 1
        elif e["etat"]["nb_notes"] == 0:
            nb_evals_vides += 1
        else:
            nb_evals_en_cours += 1
        last_modif = e["etat"]["last_modif"]
        if last_modif is not None:
            dates.append(e["etat"]["last_modif"])

    if len(dates):
        dates = scu.sort_dates(dates)
        last_modif = dates[-1]  # date de derniere modif d'une note dans un module
    else:
        last_modif = ""

    return {
        "nb_evals_completes": nb_evals_completes,
        "nb_evals_en_cours": nb_evals_en_cours,
        "nb_evals_vides": nb_evals_vides,
        "last_modif": last_modif,
    }


def do_evaluation_etat_in_sem(formsemestre_id):
    """-> nb_eval_completes, nb_evals_en_cours, nb_evals_vides,
    date derniere modif, attente"""
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > liste evaluations et moduleimpl en attente
    evals = nt.get_sem_evaluation_etat_list()
    etat = _eval_etat(evals)
    # Ajoute information sur notes en attente
    etat["attente"] = len(nt.get_moduleimpls_attente()) > 0
    return etat


def do_evaluation_etat_in_mod(nt, moduleimpl_id):
    """"""
    evals = nt.get_mod_evaluation_etat_list(moduleimpl_id)
    etat = _eval_etat(evals)
    etat["attente"] = moduleimpl_id in [
        m["moduleimpl_id"] for m in nt.get_moduleimpls_attente()
    ]  # > liste moduleimpl en attente
    return etat


def formsemestre_evaluations_cal(formsemestre_id):
    """Page avec calendrier de toutes les evaluations de ce semestre"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > liste evaluations

    evals = nt.get_sem_evaluation_etat_list()
    nb_evals = len(evals)

    color_incomplete = "#FF6060"
    color_complete = "#A0FFA0"
    color_futur = "#70E0FF"

    today = time.strftime("%Y-%m-%d")

    year = int(sem["annee_debut"])
    if sem["mois_debut_ord"] < 8:
        year -= 1  # calendrier septembre a septembre
    events = {}  # (day, halfday) : event
    for e in evals:
        etat = e["etat"]
        if not e["jour"]:
            continue
        day = e["jour"].strftime("%Y-%m-%d")
        mod = sco_moduleimpl.moduleimpl_withmodule_list(
            moduleimpl_id=e["moduleimpl_id"]
        )[0]
        txt = mod["module"]["code"] or mod["module"]["abbrev"] or "eval"
        if e["heure_debut"]:
            debut = e["heure_debut"].strftime("%Hh%M")
        else:
            debut = "?"
        if e["heure_fin"]:
            fin = e["heure_fin"].strftime("%Hh%M")
        else:
            fin = "?"
        description = "%s, de %s à %s" % (mod["module"]["titre"], debut, fin)
        if etat["evalcomplete"]:
            color = color_complete
        else:
            color = color_incomplete
        if day > today:
            color = color_futur
        href = "moduleimpl_status?moduleimpl_id=%s" % e["moduleimpl_id"]
        # if e['heure_debut'].hour < 12:
        #    halfday = True
        # else:
        #    halfday = False
        if not day in events:
            # events[(day,halfday)] = [day, txt, color, href, halfday, description, mod]
            events[day] = [day, txt, color, href, description, mod]
        else:
            e = events[day]
            if e[-1]["moduleimpl_id"] != mod["moduleimpl_id"]:
                # plusieurs evals de modules differents a la meme date
                e[1] += ", " + txt
                e[4] += ", " + description
                if not etat["evalcomplete"]:
                    e[2] = color_incomplete
                if day > today:
                    e[2] = color_futur

    CalHTML = sco_abs.YearTable(
        year, events=list(events.values()), halfday=False, pad_width=None
    )

    H = [
        html_sco_header.html_sem_header(
            "Evaluations du semestre",
            sem,
            cssstyles=["css/calabs.css"],
        ),
        '<div class="cal_evaluations">',
        CalHTML,
        "</div>",
        "<p>soit %s évaluations planifiées;" % nb_evals,
        """<ul><li>en <span style="background-color: %s">rouge</span> les évaluations passées auxquelles il manque des notes</li>
          <li>en <span style="background-color: %s">vert</span> les évaluations déjà notées</li>
          <li>en <span style="background-color: %s">bleu</span> les évaluations futures</li></ul></p>"""
        % (color_incomplete, color_complete, color_futur),
        """<p><a href="formsemestre_evaluations_delai_correction?formsemestre_id=%s" class="stdlink">voir les délais de correction</a></p>
          """
        % (formsemestre_id,),
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def evaluation_date_first_completion(evaluation_id):
    """Première date à laquelle l'évaluation a été complète
    ou None si actuellement incomplète
    """
    etat = do_evaluation_etat(evaluation_id)
    if not etat["evalcomplete"]:
        return None

    # XXX inachevé ou à revoir ?
    # Il faut considerer les inscriptions au semestre
    # (pour avoir l'etat et le groupe) et aussi les inscriptions
    # au module (pour gerer les modules optionnels correctement)
    # E = do_evaluation_list(args={"evaluation_id": evaluation_id})[0]
    # M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    # formsemestre_id = M["formsemestre_id"]
    # insem = sco_formsemestre_inscriptions.do_formsemestre_inscription_listinscrits( formsemestre_id)
    # insmod = sco_moduleimpl.do_moduleimpl_inscription_list(moduleimpl_id=E["moduleimpl_id"])
    # insmodset = set([x["etudid"] for x in insmod])
    # retire de insem ceux qui ne sont pas inscrits au module
    # ins = [i for i in insem if i["etudid"] in insmodset]

    notes = list(
        do_evaluation_get_all_notes(evaluation_id, filter_suppressed=False).values()
    )
    notes_log = list(
        do_evaluation_get_all_notes(
            evaluation_id, filter_suppressed=False, table="notes_notes_log"
        ).values()
    )
    date_premiere_note = {}  # etudid : date
    for note in notes + notes_log:
        etudid = note["etudid"]
        if etudid in date_premiere_note:
            date_premiere_note[etudid] = min(note["date"], date_premiere_note[etudid])
        else:
            date_premiere_note[etudid] = note["date"]

    if not date_premiere_note:
        return None  # complete mais aucun etudiant non démissionnaires
    # complet au moment du max (date la plus tardive) des premieres dates de saisie
    return max(date_premiere_note.values())


def formsemestre_evaluations_delai_correction(formsemestre_id, format="html"):
    """Experimental: un tableau indiquant pour chaque évaluation
    le nombre de jours avant la publication des notes.

    N'indique pas les évaluations de ratrapage ni celles des modules de bonus/malus.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > liste evaluations

    evals = nt.get_sem_evaluation_etat_list()
    T = []
    for e in evals:
        M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=e["moduleimpl_id"])[0]
        Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
        if (e["evaluation_type"] != scu.EVALUATION_NORMALE) or (
            Mod["module_type"] == scu.MODULE_MALUS
        ):
            continue
        e["date_first_complete"] = evaluation_date_first_completion(e["evaluation_id"])
        if e["date_first_complete"]:
            e["delai_correction"] = (e["date_first_complete"].date() - e["jour"]).days
        else:
            e["delai_correction"] = None

        e["module_code"] = Mod["code"]
        e["_module_code_target"] = url_for(
            "notes.moduleimpl_status",
            scodoc_dept=g.scodoc_dept,
            moduleimpl_id=M["moduleimpl_id"],
        )
        e["module_titre"] = Mod["titre"]
        e["responsable_id"] = M["responsable_id"]
        e["responsable_nomplogin"] = sco_users.user_info(M["responsable_id"])[
            "nomplogin"
        ]
        e["_jour_target"] = url_for(
            "notes.evaluation_listenotes",
            scodoc_dept=g.scodoc_dept,
            evaluation_id=e["evaluation_id"],
        )
        T.append(e)

    columns_ids = (
        "module_code",
        "module_titre",
        "responsable_nomplogin",
        "jour",
        "date_first_complete",
        "delai_correction",
        "description",
    )
    titles = {
        "module_code": "Code",
        "module_titre": "Module",
        "responsable_nomplogin": "Responsable",
        "jour": "Date",
        "date_first_complete": "Fin saisie",
        "delai_correction": "Délai",
        "description": "Description",
    }
    tab = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=T,
        html_class="table_leftalign table_coldate",
        html_sortable=True,
        html_title="<h2>Correction des évaluations du semestre</h2>",
        caption="Correction des évaluations du semestre",
        preferences=sco_preferences.SemPreferences(formsemestre_id),
        base_url="%s?formsemestre_id=%s" % (request.base_url, formsemestre_id),
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        filename=scu.make_filename("evaluations_delais_" + sem["titreannee"]),
    )
    return tab.make_page(format=format)


def module_evaluation_insert_before(ModEvals, next_eval):
    """Renumber evals such that an evaluation with can be inserted before next_eval
    Returns numero suitable for the inserted evaluation
    """
    if next_eval:
        n = next_eval["numero"]
        if not n:
            log("renumbering old evals")
            module_evaluation_renumber(next_eval["moduleimpl_id"])
            next_eval = do_evaluation_list(
                args={"evaluation_id": next_eval["evaluation_id"]}
            )[0]
            n = next_eval["numero"]
    else:
        n = 1
    # log('inserting at position numero %s' % n )
    # all numeros >= n are incremented
    for e in ModEvals:
        if e["numero"] >= n:
            e["numero"] += 1
            # log('incrementing %s to %s' % (e['evaluation_id'], e['numero']))
            do_evaluation_edit(e)

    return n


def module_evaluation_move(evaluation_id, after=0, redirect=1):
    """Move before/after previous one (decrement/increment numero)
    (published)
    """
    e = do_evaluation_list(args={"evaluation_id": evaluation_id})[0]
    redirect = int(redirect)
    # access: can change eval ?
    if not sco_permissions_check.can_edit_evaluation(moduleimpl_id=e["moduleimpl_id"]):
        raise AccessDenied(
            "Modification évaluation impossible pour %s" % current_user.get_nomplogin()
        )

    module_evaluation_renumber(e["moduleimpl_id"], only_if_unumbered=True)
    e = do_evaluation_list(args={"evaluation_id": evaluation_id})[0]

    after = int(after)  # 0: deplace avant, 1 deplace apres
    if after not in (0, 1):
        raise ValueError('invalid value for "after"')
    ModEvals = do_evaluation_list({"moduleimpl_id": e["moduleimpl_id"]})
    # log('ModEvals=%s' % [ x['evaluation_id'] for x in ModEvals] )
    if len(ModEvals) > 1:
        idx = [p["evaluation_id"] for p in ModEvals].index(evaluation_id)
        neigh = None  # object to swap with
        if after == 0 and idx > 0:
            neigh = ModEvals[idx - 1]
        elif after == 1 and idx < len(ModEvals) - 1:
            neigh = ModEvals[idx + 1]
        if neigh:  #
            # swap numero with neighbor
            e["numero"], neigh["numero"] = neigh["numero"], e["numero"]
            do_evaluation_edit(e)
            do_evaluation_edit(neigh)
    # redirect to moduleimpl page:
    if redirect:
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=e["moduleimpl_id"],
            )
        )


def module_evaluation_renumber(moduleimpl_id, only_if_unumbered=False, redirect=0):
    """Renumber evaluations in this module, according to their date. (numero=0: oldest one)
    Needed because previous versions of ScoDoc did not have eval numeros
    Note: existing numeros are ignored
    """
    redirect = int(redirect)
    # log('module_evaluation_renumber( moduleimpl_id=%s )' % moduleimpl_id )
    # List sorted according to date/heure, ignoring numeros:
    # (note that we place  evaluations with NULL date at the end)
    ModEvals = do_evaluation_list(
        args={"moduleimpl_id": moduleimpl_id},
        sortkey="jour asc, heure_debut asc",
    )

    all_numbered = False not in [x["numero"] > 0 for x in ModEvals]
    if all_numbered and only_if_unumbered:
        return  # all ok

    # log('module_evaluation_renumber')
    # Reset all numeros:
    i = 1
    for e in ModEvals:
        e["numero"] = i
        do_evaluation_edit(e)
        i += 1

    # If requested, redirect to moduleimpl page:
    if redirect:
        return flask.redirect(
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=moduleimpl_id,
            )
        )


#  -------------- VIEWS
def evaluation_describe(evaluation_id="", edit_in_place=True):
    """HTML description of evaluation, for page headers
    edit_in_place: allow in-place editing when permitted (not implemented)
    """
    from app.scodoc import sco_saisie_notes

    E = do_evaluation_list({"evaluation_id": evaluation_id})[0]
    moduleimpl_id = E["moduleimpl_id"]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    formsemestre_id = M["formsemestre_id"]
    u = sco_users.user_info(M["responsable_id"])
    resp = u["prenomnom"]
    nomcomplet = u["nomcomplet"]
    can_edit = sco_permissions_check.can_edit_notes(
        current_user, moduleimpl_id, allow_ens=False
    )

    link = (
        '<span class="evallink"><a class="stdlink" href="evaluation_listenotes?moduleimpl_id=%s">voir toutes les notes du module</a></span>'
        % moduleimpl_id
    )
    mod_descr = (
        '<a href="moduleimpl_status?moduleimpl_id=%s">%s %s</a> <span class="resp">(resp. <a title="%s">%s</a>)</span> %s'
        % (moduleimpl_id, Mod["code"], Mod["titre"], nomcomplet, resp, link)
    )

    etit = E["description"] or ""
    if etit:
        etit = ' "' + etit + '"'
    if Mod["module_type"] == scu.MODULE_MALUS:
        etit += ' <span class="eval_malus">(points de malus)</span>'
    H = [
        '<span class="eval_title">Evaluation%s</span><p><b>Module : %s</b></p>'
        % (etit, mod_descr)
    ]
    if Mod["module_type"] == scu.MODULE_MALUS:
        # Indique l'UE
        ue = sco_edit_ue.ue_list(args={"ue_id": Mod["ue_id"]})[0]
        H.append("<p><b>UE : %(acronyme)s</b></p>" % ue)
        # store min/max values used by JS client-side checks:
        H.append(
            '<span id="eval_note_min" class="sco-hidden">-20.</span><span id="eval_note_max" class="sco-hidden">20.</span>'
        )
    else:
        # date et absences (pas pour evals de malus)
        jour = E["jour"] or "<em>pas de date</em>"
        H.append(
            "<p>Réalisée le <b>%s</b> de %s à %s "
            % (jour, E["heure_debut"], E["heure_fin"])
        )
        if E["jour"]:
            group_id = sco_groups.get_default_group(formsemestre_id)
            H.append(
                f"""<span class="noprint"><a href="{url_for(
                    'absences.EtatAbsencesDate', 
                    scodoc_dept=g.scodoc_dept, 
                    group_ids=group_id,
                    date=E["jour"]
                    )
                    }">(absences ce jour)</a></span>"""
            )
        H.append(
            '</p><p>Coefficient dans le module: <b>%s</b>, notes sur <span id="eval_note_max">%g</span> '
            % (E["coefficient"], E["note_max"])
        )
        H.append('<span id="eval_note_min" class="sco-hidden">0.</span>')
    if can_edit:
        H.append(
            '<a href="evaluation_edit?evaluation_id=%s">(modifier l\'évaluation)</a>'
            % evaluation_id
        )
    H.append("</p>")

    return '<div class="eval_description">' + "\n".join(H) + "</div>"


def evaluation_create_form(
    moduleimpl_id=None,
    evaluation_id=None,
    edit=False,
    readonly=False,
    page_title="Evaluation",
):
    "formulaire creation/edition des evaluations (pas des notes)"
    if evaluation_id != None:
        the_eval = do_evaluation_list({"evaluation_id": evaluation_id})[0]
        moduleimpl_id = the_eval["moduleimpl_id"]
    #
    M = sco_moduleimpl.moduleimpl_withmodule_list(moduleimpl_id=moduleimpl_id)[0]
    is_malus = M["module"]["module_type"] == scu.MODULE_MALUS  # True si module de malus
    formsemestre_id = M["formsemestre_id"]
    min_note_max = scu.NOTES_PRECISION  # le plus petit bareme possible
    if not readonly:
        if not sco_permissions_check.can_edit_evaluation(moduleimpl_id=moduleimpl_id):
            return (
                html_sco_header.sco_header()
                + "<h2>Opération non autorisée</h2><p>"
                + "Modification évaluation impossible pour %s"
                % current_user.get_nomplogin()
                + "</p>"
                + '<p><a href="moduleimpl_status?moduleimpl_id=%s">Revenir</a></p>'
                % (moduleimpl_id,)
                + html_sco_header.sco_footer()
            )
    if readonly:
        edit = True  # montre les donnees existantes
    if not edit:
        # creation nouvel
        if moduleimpl_id is None:
            raise ValueError("missing moduleimpl_id parameter")
        initvalues = {
            "note_max": 20,
            "jour": time.strftime("%d/%m/%Y", time.localtime()),
            "publish_incomplete": is_malus,
        }
        submitlabel = "Créer cette évaluation"
        action = "Création d'une é"
        link = ""
    else:
        # edition donnees existantes
        # setup form init values
        if evaluation_id is None:
            raise ValueError("missing evaluation_id parameter")
        initvalues = the_eval
        moduleimpl_id = initvalues["moduleimpl_id"]
        submitlabel = "Modifier les données"
        if readonly:
            action = "E"
            link = (
                '<span class="evallink"><a class="stdlink" href="evaluation_listenotes?moduleimpl_id=%s">voir toutes les notes du module</a></span>'
                % M["moduleimpl_id"]
            )
        else:
            action = "Modification d'une é"
            link = ""
        # Note maximale actuelle dans cette eval ?
        etat = do_evaluation_etat(evaluation_id)
        if etat["maxi_num"] is not None:
            min_note_max = max(scu.NOTES_PRECISION, etat["maxi_num"])
        else:
            min_note_max = scu.NOTES_PRECISION
    #
    if min_note_max > scu.NOTES_PRECISION:
        min_note_max_str = scu.fmt_note(min_note_max)
    else:
        min_note_max_str = "0"
    #
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    #
    help = """<div class="help"><p class="help">
    Le coefficient d'une évaluation n'est utilisé que pour pondérer les évaluations au sein d'un module.
    Il est fixé librement par l'enseignant pour refléter l'importance de ses différentes notes
    (examens, projets, travaux pratiques...). Ce coefficient est utilisé pour calculer la note
    moyenne de chaque étudiant dans ce module.
    </p><p class="help">
    Ne pas confondre ce coefficient avec le coefficient du module, qui est lui fixé par le programme
    pédagogique (le PPN pour les DUT) et pondère les moyennes de chaque module pour obtenir
    les moyennes d'UE et la moyenne générale.
    </p><p class="help">
    L'option <em>Visible sur bulletins</em> indique que la note sera reportée sur les bulletins
    en version dite "intermédiaire" (dans cette version, on peut ne faire apparaitre que certaines
    notes, en sus des moyennes de modules. Attention, cette option n'empêche pas la publication sur
    les bulletins en version "longue" (la note est donc visible par les étudiants sur le portail).
    </p><p class="help">
    Les modalités "rattrapage" et "deuxième session" définissent des évaluations prises en compte de 
    façon spéciale: </p>
    <ul>
    <li>les notes d'une évaluation de "rattrapage" remplaceront les moyennes du module
    <em>si elles sont meilleures que celles calculées</em>.</li>
    <li>les notes de "deuxième session" remplacent, lorsqu'elles sont saisies, la moyenne de l'étudiant 
    à ce module, même si la note de deuxième session est plus faible.</li> 
    </ul>
    <p class="help">
    Dans ces deux cas, le coefficient est ignoré, et toutes les notes n'ont
    pas besoin d'être rentrées.
    </p>
    <p class="help">
    Par ailleurs, les évaluations des modules de type "malus" sont toujours spéciales: le coefficient n'est pas utilisé. 
    Les notes de malus sont toujours comprises entre -20 et 20. Les points sont soustraits à la moyenne
    de l'UE à laquelle appartient le module malus (si la note est négative, la moyenne est donc augmentée).
    </p>
    """
    mod_descr = '<a href="moduleimpl_status?moduleimpl_id=%s">%s %s</a> %s' % (
        moduleimpl_id,
        Mod["code"],
        Mod["titre"],
        link,
    )
    if not readonly:
        H = ["<h3>%svaluation en %s</h3>" % (action, mod_descr)]
    else:
        return evaluation_describe(evaluation_id)

    heures = ["%02dh%02d" % (h, m) for h in range(8, 19) for m in (0, 30)]
    #
    initvalues["visibulletin"] = initvalues.get("visibulletin", True)
    if initvalues["visibulletin"]:
        initvalues["visibulletinlist"] = ["X"]
    else:
        initvalues["visibulletinlist"] = []
    vals = scu.get_request_args()
    if vals.get("tf_submitted", False) and "visibulletinlist" not in vals:
        vals["visibulletinlist"] = []
    #
    form = [
        ("evaluation_id", {"default": evaluation_id, "input_type": "hidden"}),
        ("formsemestre_id", {"default": formsemestre_id, "input_type": "hidden"}),
        ("moduleimpl_id", {"default": moduleimpl_id, "input_type": "hidden"}),
        # ('jour', { 'title' : 'Date (j/m/a)', 'size' : 12, 'explanation' : 'date de l\'examen, devoir ou contrôle' }),
        (
            "jour",
            {
                "input_type": "date",
                "title": "Date",
                "size": 12,
                "explanation": "date de l'examen, devoir ou contrôle",
            },
        ),
        (
            "heure_debut",
            {
                "title": "Heure de début",
                "explanation": "heure du début de l'épreuve",
                "input_type": "menu",
                "allowed_values": heures,
                "labels": heures,
            },
        ),
        (
            "heure_fin",
            {
                "title": "Heure de fin",
                "explanation": "heure de fin de l'épreuve",
                "input_type": "menu",
                "allowed_values": heures,
                "labels": heures,
            },
        ),
    ]
    if is_malus:  # pas de coefficient
        form.append(("coefficient", {"input_type": "hidden", "default": "1."}))
    else:
        form.append(
            (
                "coefficient",
                {
                    "size": 10,
                    "type": "float",
                    "explanation": "coef. dans le module (choisi librement par l'enseignant)",
                    "allow_null": False,
                },
            )
        )
    form += [
        (
            "note_max",
            {
                "size": 4,
                "type": "float",
                "title": "Notes de 0 à",
                "explanation": "barème (note max actuelle: %s)" % min_note_max_str,
                "allow_null": False,
                "max_value": scu.NOTES_MAX,
                "min_value": min_note_max,
            },
        ),
        (
            "description",
            {
                "size": 36,
                "type": "text",
                "explanation": 'type d\'évaluation, apparait sur le bulletins longs. Exemples: "contrôle court", "examen de TP", "examen final".',
            },
        ),
        (
            "visibulletinlist",
            {
                "input_type": "checkbox",
                "allowed_values": ["X"],
                "labels": [""],
                "title": "Visible sur bulletins",
                "explanation": "(pour les bulletins en version intermédiaire)",
            },
        ),
        (
            "publish_incomplete",
            {
                "input_type": "boolcheckbox",
                "title": "Prise en compte immédiate",
                "explanation": "notes utilisées même si incomplètes",
            },
        ),
        (
            "evaluation_type",
            {
                "input_type": "menu",
                "title": "Modalité",
                "allowed_values": (
                    scu.EVALUATION_NORMALE,
                    scu.EVALUATION_RATTRAPAGE,
                    scu.EVALUATION_SESSION2,
                ),
                "type": "int",
                "labels": (
                    "Normale",
                    "Rattrapage (remplace si meilleure note)",
                    "Deuxième session (remplace toujours)",
                ),
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        vals,
        form,
        cancelbutton="Annuler",
        submitlabel=submitlabel,
        initvalues=initvalues,
        readonly=readonly,
    )

    dest_url = "moduleimpl_status?moduleimpl_id=%s" % M["moduleimpl_id"]
    if tf[0] == 0:
        head = html_sco_header.sco_header(page_title=page_title)
        return head + "\n".join(H) + "\n" + tf[1] + help + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        # form submission
        if tf[2]["visibulletinlist"]:
            tf[2]["visibulletin"] = True
        else:
            tf[2]["visibulletin"] = False
        if not edit:
            # creation d'une evaluation
            evaluation_id = do_evaluation_create(**tf[2])
            return flask.redirect(dest_url)
        else:
            do_evaluation_edit(tf[2])
            return flask.redirect(dest_url)
