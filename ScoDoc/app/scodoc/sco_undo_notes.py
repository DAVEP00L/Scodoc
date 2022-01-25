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

"""ScoDoc : annulation des saisies de notes


note = {evaluation_id, etudid, value, date, uid, comment}

Pour une évaluation:
 - notes actuelles: table notes_notes
 - historique: table notes_notes_log 

saisie de notes == saisir ou supprimer une ou plusieurs notes (mêmes date et uid)
! tolérance sur les dates (200ms ?)
Chaque saisie affecte ou remplace une ou plusieurs notes.

Opérations:
 - lister les saisies de notes
 - annuler une saisie complète
 - lister les modifs d'une seule note
 - annuler une modif d'une note
"""

import datetime
from flask import request

from app.scodoc.intervals import intervalmap

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc import sco_evaluations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_preferences
from app.scodoc import sco_users
import sco_version
from app.scodoc.gen_tables import GenTable

# deux notes (de même uid) sont considérées comme de la même opération si
# elles sont séparées de moins de 2*tolerance:
OPERATION_DATE_TOLERANCE = datetime.timedelta(seconds=0.1)


class NotesOperation(dict):
    """Represents an operation on an evaluation
    Keys: evaluation_id, date, uid, notes
    """

    def get_comment(self):
        if self["notes"]:
            return self["notes"][0]["comment"]
        else:
            return ""

    def comp_values(self):
        "compute keys: comment, nb_notes"
        self["comment"] = self.get_comment()
        self["nb_notes"] = len(self["notes"])
        self["datestr"] = self["date"].strftime("%a %d/%m/%y %Hh%M")

    def undo(self):
        "undo operation"
        pass
        # replace notes by last found in notes_log
        # and suppress log entry
        # select * from notes_notes_log where evaluation_id= and etudid= and date <
        #
        # verrouille tables notes, notes_log
        # pour chaque note qui n'est pas plus recente que l'operation:
        #   recupere valeurs precedentes dans log
        #   affecte valeurs notes
        #   suppr log
        # deverrouille tablesj
        # for note in self['notes']:
        #    # il y a-t-il une modif plus recente ?
        #    if self['current_notes_by_etud']['date'] <= self['date'] + OPERATION_DATE_TOLERANCE:
        #
        # + invalider cache   sco_cache.EvaluationCache.delete(evaluation_id)


def list_operations(evaluation_id):
    """returns list of NotesOperation for this evaluation"""
    notes = list(
        sco_evaluations.do_evaluation_get_all_notes(
            evaluation_id, filter_suppressed=False
        ).values()
    )
    notes_log = list(
        sco_evaluations.do_evaluation_get_all_notes(
            evaluation_id, filter_suppressed=False, table="notes_notes_log"
        ).values()
    )
    dt = OPERATION_DATE_TOLERANCE
    NotesDates = {}  # { uid : intervalmap }

    for note in notes + notes_log:
        if note["uid"] not in NotesDates:
            NotesDates[note["uid"]] = intervalmap()
        nd = NotesDates[note["uid"]]
        if nd[note["date"]] is None:
            nd[note["date"] - dt : note["date"] + dt] = [note]
        else:
            nd[note["date"]].append(note)

    current_notes_by_etud = {}  # { etudid : note }
    for note in notes:
        current_notes_by_etud[note["etudid"]] = note

    Ops = []
    for uid in NotesDates.keys():
        for (t0, _), notes in NotesDates[uid].items():
            Op = NotesOperation(
                evaluation_id=evaluation_id,
                date=t0,
                uid=uid,
                notes=NotesDates[uid][t0],
                current_notes_by_etud=current_notes_by_etud,
            )
            Op.comp_values()
            Ops.append(Op)

    return Ops


def evaluation_list_operations(evaluation_id):
    """Page listing operations on evaluation"""
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]

    Ops = list_operations(evaluation_id)

    columns_ids = ("datestr", "uid", "nb_notes", "comment")
    titles = {
        "datestr": "Date",
        "uid": "Enseignant",
        "nb_notes": "Nb de notes",
        "comment": "Commentaire",
    }
    tab = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=Ops,
        html_sortable=False,
        html_title="<h2>Opérations sur l'évaluation %s du %s</h2>"
        % (E["description"], E["jour"]),
        preferences=sco_preferences.SemPreferences(M["formsemestre_id"]),
    )
    return tab.make_page()


def formsemestre_list_saisies_notes(formsemestre_id, format="html"):
    """Table listant toutes les opérations de saisies de notes, dans toutes
    les évaluations du semestre.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id, raise_soft_exc=True)
    r = ndb.SimpleDictFetch(
        """SELECT i.nom, code_nip, n.*, mod.titre, e.description, e.jour
        FROM notes_notes n, notes_evaluation e, notes_moduleimpl mi,
        notes_modules mod, identite i
        WHERE mi.id = e.moduleimpl_id
        and mi.module_id = mod.id
        and e.id = n.evaluation_id
        and i.id = n.etudid
        and mi.formsemestre_id = %(formsemestre_id)s
        ORDER BY date desc
        """,
        {"formsemestre_id": formsemestre_id},
    )
    columns_ids = (
        "date",
        "code_nip",
        "nom",
        "value",
        "uid",
        "titre",
        "description",
        "jour",
        "comment",
    )
    titles = {
        "code_nip": "NIP",
        "nom": "Etudiant",
        "date": "Date",
        "value": "Note",
        "comment": "Remarque",
        "uid": "Enseignant",
        "titre": "Module",
        "description": "Evaluation",
        "jour": "Date éval.",
    }
    tab = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=r,
        html_title="<h2>Saisies de notes dans %s</h2>" % sem["titreannee"],
        html_class="table_leftalign table_coldate",
        html_sortable=True,
        caption="Saisies de notes dans %s" % sem["titreannee"],
        preferences=sco_preferences.SemPreferences(formsemestre_id),
        base_url="%s?formsemestre_id=%s" % (request.base_url, formsemestre_id),
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
    )
    return tab.make_page(format=format)


def get_note_history(evaluation_id, etudid, fmt=""):
    """Historique d'une note
    = liste chronologique d'opérations, la plus récente d'abord
    [ { 'value', 'date', 'comment', 'uid' } ]
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)

    # Valeur courante
    cursor.execute(
        """
    SELECT * FROM notes_notes
    WHERE evaluation_id=%(evaluation_id)s AND etudid=%(etudid)s 
    """,
        {"evaluation_id": evaluation_id, "etudid": etudid},
    )
    history = cursor.dictfetchall()

    # Historique
    cursor.execute(
        """
    SELECT * FROM notes_notes_log
    WHERE evaluation_id=%(evaluation_id)s AND etudid=%(etudid)s 
    ORDER BY date DESC""",
        {"evaluation_id": evaluation_id, "etudid": etudid},
    )

    history += cursor.dictfetchall()

    # Replace None comments by ''
    # et cherche nom complet de l'enseignant:
    for x in history:
        x["comment"] = x["comment"] or ""
        x["user_name"] = sco_users.user_info(x["uid"])["nomcomplet"]

    if fmt == "json":
        return scu.sendJSON(history)
    else:
        return history


"""
from debug import *
from app.scodoc.sco_undo_notes import *
_ = go_dept(app, 'RT').Notes
get_note_history( 'EVAL29740', 'EID28403')
"""
