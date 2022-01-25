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

"""Saisie des notes

   Formulaire revu en juillet 2016
"""
import sys
import time
import datetime
import psycopg2

import flask
from flask import g, url_for, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.sco_exceptions import (
    AccessDenied,
    InvalidNoteValue,
    NoteProcessError,
    ScoGenError,
    ScoValueError,
)
from app.scodoc.sco_permissions import Permission
from app.scodoc.TrivialFormulator import TrivialFormulator, TF
from app.scodoc import html_sco_header, sco_users
from app.scodoc import htmlutils
from app.scodoc import sco_abs
from app.scodoc import sco_cache
from app.scodoc import sco_edit_module
from app.scodoc import sco_evaluations
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_news
from app.scodoc import sco_permissions_check
from app.scodoc import sco_undo_notes
from app.scodoc import sco_etud


def convert_note_from_string(
    note,
    note_max,
    note_min=scu.NOTES_MIN,
    etudid=None,
    absents=None,
    tosuppress=None,
    invalids=None,
):
    """converti une valeur (chaine saisie) vers une note numérique (float)
    Les listes absents, tosuppress et invalids sont modifiées
    """
    absents = absents or []
    tosuppress = tosuppress or []
    invalids = invalids or []
    invalid = False
    note_value = None
    note = note.replace(",", ".")
    if note[:3] == "ABS":
        note_value = None
        absents.append(etudid)
    elif note[:3] == "NEU" or note[:3] == "EXC":
        note_value = scu.NOTES_NEUTRALISE
    elif note[:3] == "ATT":
        note_value = scu.NOTES_ATTENTE
    elif note[:3] == "SUP":
        note_value = scu.NOTES_SUPPRESS
        tosuppress.append(etudid)
    else:
        try:
            note_value = float(note)
            if (note_value < note_min) or (note_value > note_max):
                raise ValueError
        except:
            invalids.append(etudid)
            invalid = True

    return note_value, invalid


def _displayNote(val):
    """Convert note from DB to viewable string.
    Utilisé seulement pour I/O vers formulaires (sans perte de precision)
    (Utiliser fmt_note pour les affichages)
    """
    if val is None:
        val = "ABS"
    elif val == scu.NOTES_NEUTRALISE:
        val = "EXC"  # excuse, note neutralise
    elif val == scu.NOTES_ATTENTE:
        val = "ATT"  # attente, note neutralise
    elif val == scu.NOTES_SUPPRESS:
        val = "SUPR"
    else:
        val = "%g" % val
    return val


def _check_notes(notes, evaluation, mod):
    """notes is a list of tuples (etudid, value)
    mod is the module (used to ckeck type, for malus)
    returns list of valid notes (etudid, float value)
    and 4 lists of etudid: invalids, withoutnotes, absents, tosuppress, existingjury
    """
    note_max = evaluation["note_max"]
    if mod["module_type"] == scu.MODULE_STANDARD:
        note_min = scu.NOTES_MIN
    elif mod["module_type"] == scu.MODULE_MALUS:
        note_min = -20.0
    else:
        raise ValueError("Invalid module type")  # bug
    L = []  # liste (etudid, note) des notes ok (ou absent)
    invalids = []  # etudid avec notes invalides
    withoutnotes = []  # etudid sans notes (champs vides)
    absents = []  # etudid absents
    tosuppress = []  # etudids avec ancienne note à supprimer

    for (etudid, note) in notes:
        note = str(note).strip().upper()
        etudid = int(etudid)  #
        if note[:3] == "DEM":
            continue  # skip !
        if note:
            value, invalid = convert_note_from_string(
                note,
                note_max,
                note_min=note_min,
                etudid=etudid,
                absents=absents,
                tosuppress=tosuppress,
                invalids=invalids,
            )
            if not invalid:
                L.append((etudid, value))
        else:
            withoutnotes.append(etudid)

    return L, invalids, withoutnotes, absents, tosuppress


def do_evaluation_upload_xls():
    """
    Soumission d'un fichier XLS (evaluation_id, notefile)
    """
    authuser = current_user
    vals = scu.get_request_args()
    evaluation_id = int(vals["evaluation_id"])
    comment = vals["comment"]
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    M = sco_moduleimpl.moduleimpl_withmodule_list(moduleimpl_id=E["moduleimpl_id"])[0]
    # Check access
    # (admin, respformation, and responsable_id)
    if not sco_permissions_check.can_edit_notes(authuser, E["moduleimpl_id"]):
        raise AccessDenied("Modification des notes impossible pour %s" % authuser)
    #
    diag, lines = sco_excel.excel_file_to_list(vals["notefile"])
    try:
        if not lines:
            raise InvalidNoteValue()
        # -- search eval code
        n = len(lines)
        i = 0
        while i < n:
            if not lines[i]:
                diag.append("Erreur: format invalide (ligne vide ?)")
                raise InvalidNoteValue()
            f0 = lines[i][0].strip()
            if f0 and f0[0] == "!":
                break
            i = i + 1
        if i == n:
            diag.append("Erreur: format invalide ! (pas de ligne evaluation_id)")
            raise InvalidNoteValue()

        eval_id_str = lines[i][0].strip()[1:]
        try:
            eval_id = int(eval_id_str)
        except ValueError:
            eval_id = None
        if eval_id != evaluation_id:
            diag.append(
                f"Erreur: fichier invalide: le code d'évaluation de correspond pas ! ('{eval_id_str}' != '{evaluation_id}')"
            )
            raise InvalidNoteValue()
        # --- get notes -> list (etudid, value)
        # ignore toutes les lignes ne commençant pas par !
        notes = []
        ni = i + 1
        try:
            for line in lines[i + 1 :]:
                if line:
                    cell0 = line[0].strip()
                    if cell0 and cell0[0] == "!":
                        etudid = cell0[1:]
                        if len(line) > 4:
                            val = line[4].strip()
                        else:
                            val = ""  # ligne courte: cellule vide
                        if etudid:
                            notes.append((etudid, val))
                ni += 1
        except:
            diag.append(
                'Erreur: Ligne invalide ! (erreur ligne %d)<br/>"%s"'
                % (ni, str(lines[ni]))
            )
            raise InvalidNoteValue()
        # -- check values
        L, invalids, withoutnotes, absents, _ = _check_notes(notes, E, M["module"])
        if len(invalids):
            diag.append(
                "Erreur: la feuille contient %d notes invalides</p>" % len(invalids)
            )
            if len(invalids) < 25:
                etudsnames = [
                    sco_etud.get_etud_info(etudid=etudid, filled=True)[0]["nomprenom"]
                    for etudid in invalids
                ]
                diag.append("Notes invalides pour: " + ", ".join(etudsnames))
            raise InvalidNoteValue()
        else:
            nb_changed, nb_suppress, existing_decisions = _notes_add(
                authuser, evaluation_id, L, comment
            )
            # news
            E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
            M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
            mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
            mod["moduleimpl_id"] = M["moduleimpl_id"]
            mod["url"] = url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=mod["moduleimpl_id"],
            )
            sco_news.add(
                typ=sco_news.NEWS_NOTE,
                object=M["moduleimpl_id"],
                text='Chargement notes dans <a href="%(url)s">%(titre)s</a>' % mod,
                url=mod["url"],
            )

            msg = (
                "<p>%d notes changées (%d sans notes, %d absents, %d note supprimées)</p>"
                % (nb_changed, len(withoutnotes), len(absents), nb_suppress)
            )
            if existing_decisions:
                msg += """<p class="warning">Important: il y avait déjà des décisions de jury enregistrées, qui sont potentiellement à revoir suite à cette modification !</p>"""
            # msg += '<p>' + str(notes) # debug
            return 1, msg

    except InvalidNoteValue:
        if diag:
            msg = (
                '<ul class="tf-msg"><li class="tf_msg">'
                + '</li><li class="tf_msg">'.join(diag)
                + "</li></ul>"
            )
        else:
            msg = '<ul class="tf-msg"><li class="tf_msg">Une erreur est survenue</li></ul>'
        return 0, msg + "<p>(pas de notes modifiées)</p>"


def do_evaluation_set_missing(evaluation_id, value, dialog_confirmed=False):
    """Initialisation des notes manquantes"""
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    M = sco_moduleimpl.moduleimpl_withmodule_list(moduleimpl_id=E["moduleimpl_id"])[0]
    # Check access
    # (admin, respformation, and responsable_id)
    if not sco_permissions_check.can_edit_notes(current_user, E["moduleimpl_id"]):
        # XXX imaginer un redirect + msg erreur
        raise AccessDenied("Modification des notes impossible pour %s" % current_user)
    #
    NotesDB = sco_evaluations.do_evaluation_get_all_notes(evaluation_id)
    etudids = sco_groups.do_evaluation_listeetuds_groups(
        evaluation_id, getallstudents=True, include_dems=False
    )
    notes = []
    for etudid in etudids:  # pour tous les inscrits
        if etudid not in NotesDB:  # pas de note
            notes.append((etudid, value))
    # Check value
    L, invalids, _, _, _ = _check_notes(notes, E, M["module"])
    diag = ""
    if len(invalids):
        diag = "Valeur %s invalide" % value
    if diag:
        return (
            html_sco_header.sco_header()
            + '<h2>%s</h2><p><a href="saisie_notes?evaluation_id=%s">Recommencer</a>'
            % (diag, evaluation_id)
            + html_sco_header.sco_footer()
        )
    # Confirm action
    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Mettre toutes les notes manquantes de l'évaluation
            à la valeur %s ?</h2>
            <p>Seuls les étudiants pour lesquels aucune note (ni valeur, ni ABS, ni EXC)
            n'a été rentrée seront affectés.</p>
            <p><b>%d étudiants concernés par ce changement de note.</b></p>
            <p class="warning">Attention, les étudiants sans notes de tous les groupes de ce semestre seront affectés.</p>
            """
            % (value, len(L)),
            dest_url="",
            cancel_url="saisie_notes?evaluation_id=%s" % evaluation_id,
            parameters={"evaluation_id": evaluation_id, "value": value},
        )
    # ok
    comment = "Initialisation notes manquantes"
    nb_changed, _, _ = _notes_add(current_user, evaluation_id, L, comment)
    # news
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    mod["moduleimpl_id"] = M["moduleimpl_id"]
    mod["url"] = url_for(
        "notes.moduleimpl_status",
        scodoc_dept=g.scodoc_dept,
        moduleimpl_id=mod["moduleimpl_id"],
    )
    sco_news.add(
        typ=sco_news.NEWS_NOTE,
        object=M["moduleimpl_id"],
        text='Initialisation notes dans <a href="%(url)s">%(titre)s</a>' % mod,
        url=mod["url"],
    )
    return (
        html_sco_header.sco_header()
        + f"""
        <h2>{nb_changed} notes changées</h2>
        <ul>
        <li><a class="stdlink" href="{url_for("notes.saisie_notes", 
        scodoc_dept=g.scodoc_dept, evaluation_id=evaluation_id)
        }">
        Revenir au formulaire de saisie des notes</a>
        </li>
        <li><a class="stdlink" href="{
            url_for(
                "notes.moduleimpl_status",
                scodoc_dept=g.scodoc_dept,
                moduleimpl_id=M["moduleimpl_id"],
            )}">Tableau de bord du module</a>
        </li>
        </ul>
        """
        + html_sco_header.sco_footer()
    )


def evaluation_suppress_alln(evaluation_id, dialog_confirmed=False):
    "suppress all notes in this eval"
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]

    if sco_permissions_check.can_edit_notes(
        current_user, E["moduleimpl_id"], allow_ens=False
    ):
        # On a le droit de modifier toutes les notes
        # recupere les etuds ayant une note
        NotesDB = sco_evaluations.do_evaluation_get_all_notes(evaluation_id)
    elif sco_permissions_check.can_edit_notes(
        current_user, E["moduleimpl_id"], allow_ens=True
    ):
        # Enseignant associé au module: ne peut supprimer que les notes qu'il a saisi
        NotesDB = sco_evaluations.do_evaluation_get_all_notes(
            evaluation_id, by_uid=current_user.id
        )
    else:
        raise AccessDenied("Modification des notes impossible pour %s" % current_user)

    notes = [(etudid, scu.NOTES_SUPPRESS) for etudid in NotesDB.keys()]

    if not dialog_confirmed:
        nb_changed, nb_suppress, existing_decisions = _notes_add(
            current_user, evaluation_id, notes, do_it=False
        )
        msg = (
            "<p>Confirmer la suppression des %d notes ? <em>(peut affecter plusieurs groupes)</em></p>"
            % nb_suppress
        )
        if existing_decisions:
            msg += """<p class="warning">Important: il y a déjà des décisions de jury enregistrées, qui seront potentiellement à revoir suite à cette modification !</p>"""
        return scu.confirm_dialog(
            msg,
            dest_url="",
            OK="Supprimer les notes",
            cancel_url="moduleimpl_status?moduleimpl_id=%s" % E["moduleimpl_id"],
            parameters={"evaluation_id": evaluation_id},
        )

    # modif
    nb_changed, nb_suppress, existing_decisions = _notes_add(
        current_user, evaluation_id, notes, comment="effacer tout"
    )
    assert nb_changed == nb_suppress
    H = ["<p>%s notes supprimées</p>" % nb_suppress]
    if existing_decisions:
        H.append(
            """<p class="warning">Important: il y avait déjà des décisions de jury enregistrées, qui sont potentiellement à revoir suite à cette modification !</p>"""
        )
    H += [
        '<p><a class="stdlink" href="moduleimpl_status?moduleimpl_id=%s">continuer</a>'
        % E["moduleimpl_id"]
    ]
    # news
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    mod["moduleimpl_id"] = M["moduleimpl_id"]
    mod["url"] = "Notes/moduleimpl_status?moduleimpl_id=%(moduleimpl_id)s" % mod
    sco_news.add(
        typ=sco_news.NEWS_NOTE,
        object=M["moduleimpl_id"],
        text='Suppression des notes d\'une évaluation dans <a href="%(url)s">%(titre)s</a>'
        % mod,
        url=mod["url"],
    )

    return html_sco_header.sco_header() + "\n".join(H) + html_sco_header.sco_footer()


def _notes_add(user, evaluation_id: int, notes: list, comment=None, do_it=True):
    """
    Insert or update notes
    notes is a list of tuples (etudid,value)
    If do_it is False, simulate the process and returns the number of values that
    WOULD be changed or suppressed.
    Nota:
    - si la note existe deja avec valeur distincte, ajoute une entree au log (notes_notes_log)
    Return number of changed notes
    """
    now = psycopg2.Timestamp(
        *time.localtime()[:6]
    )  # datetime.datetime.now().isoformat()
    # Verifie inscription et valeur note
    _ = {}.fromkeys(
        sco_groups.do_evaluation_listeetuds_groups(
            evaluation_id, getallstudents=True, include_dems=True
        )
    )
    for (etudid, value) in notes:
        if not ((value is None) or (type(value) == type(1.0))):
            raise NoteProcessError(
                "etudiant %s: valeur de note invalide (%s)" % (etudid, value)
            )
    # Recherche notes existantes
    NotesDB = sco_evaluations.do_evaluation_get_all_notes(evaluation_id)
    # Met a jour la base
    cnx = ndb.GetDBConnexion(autocommit=False)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    nb_changed = 0
    nb_suppress = 0
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    existing_decisions = (
        []
    )  # etudids pour lesquels il y a une decision de jury et que la note change
    try:
        for (etudid, value) in notes:
            changed = False
            if etudid not in NotesDB:
                # nouvelle note
                if value != scu.NOTES_SUPPRESS:
                    if do_it:
                        aa = {
                            "etudid": etudid,
                            "evaluation_id": evaluation_id,
                            "value": value,
                            "comment": comment,
                            "uid": user.id,
                            "date": now,
                        }
                        ndb.quote_dict(aa)
                        cursor.execute(
                            """INSERT INTO notes_notes
                            (etudid, evaluation_id, value, comment, date, uid)
                            VALUES (%(etudid)s,%(evaluation_id)s,%(value)s,%(comment)s,%(date)s,%(uid)s)
                            """,
                            aa,
                        )
                    changed = True
            else:
                # il y a deja une note
                oldval = NotesDB[etudid]["value"]
                if type(value) != type(oldval):
                    changed = True
                elif type(value) == type(1.0) and (
                    abs(value - oldval) > scu.NOTES_PRECISION
                ):
                    changed = True
                elif value != oldval:
                    changed = True
                if changed:
                    # recopie l'ancienne note dans notes_notes_log, puis update
                    if do_it:
                        cursor.execute(
                            """INSERT INTO notes_notes_log
                                (etudid,evaluation_id,value,comment,date,uid) 
                            SELECT etudid, evaluation_id, value, comment, date, uid
                            FROM notes_notes
                            WHERE etudid=%(etudid)s 
                            and evaluation_id=%(evaluation_id)s
                            """,
                            {"etudid": etudid, "evaluation_id": evaluation_id},
                        )
                        aa = {
                            "etudid": etudid,
                            "evaluation_id": evaluation_id,
                            "value": value,
                            "date": now,
                            "comment": comment,
                            "uid": user.id,
                        }
                        ndb.quote_dict(aa)
                    if value != scu.NOTES_SUPPRESS:
                        if do_it:
                            cursor.execute(
                                """UPDATE notes_notes
                                SET value=%(value)s, comment=%(comment)s, date=%(date)s, uid=%(uid)s
                                WHERE etudid = %(etudid)s 
                                and evaluation_id = %(evaluation_id)s
                                """,
                                aa,
                            )
                    else:  # suppression ancienne note
                        if do_it:
                            log(
                                "_notes_add, suppress, evaluation_id=%s, etudid=%s, oldval=%s"
                                % (evaluation_id, etudid, oldval)
                            )
                            cursor.execute(
                                """DELETE FROM notes_notes
                                WHERE etudid = %(etudid)s 
                                AND evaluation_id = %(evaluation_id)s
                                """,
                                aa,
                            )
                            # garde trace de la suppression dans l'historique:
                            aa["value"] = scu.NOTES_SUPPRESS
                            cursor.execute(
                                """INSERT INTO notes_notes_log (etudid,evaluation_id,value,comment,date,uid) 
                                VALUES (%(etudid)s, %(evaluation_id)s, %(value)s, %(comment)s, %(date)s, %(uid)s)
                                """,
                                aa,
                            )
                        nb_suppress += 1
            if changed:
                nb_changed += 1
                if has_existing_decision(M, E, etudid):
                    existing_decisions.append(etudid)
    except:
        log("*** exception in _notes_add")
        if do_it:
            cnx.rollback()  # abort
            # inval cache
            sco_cache.invalidate_formsemestre(
                formsemestre_id=M["formsemestre_id"]
            )  # > modif notes (exception)
            sco_cache.EvaluationCache.delete(evaluation_id)
        raise ScoGenError("Erreur enregistrement note: merci de ré-essayer")
    if do_it:
        cnx.commit()
        sco_cache.invalidate_formsemestre(
            formsemestre_id=M["formsemestre_id"]
        )  # > modif notes
        sco_cache.EvaluationCache.delete(evaluation_id)
    return nb_changed, nb_suppress, existing_decisions


def saisie_notes_tableur(evaluation_id, group_ids=()):
    """Saisie des notes via un fichier Excel"""
    evals = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})
    if not evals:
        raise ScoValueError("invalid evaluation_id")
    E = evals[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    formsemestre_id = M["formsemestre_id"]
    if not sco_permissions_check.can_edit_notes(current_user, E["moduleimpl_id"]):
        return (
            html_sco_header.sco_header()
            + "<h2>Modification des notes impossible pour %s</h2>"
            % current_user.user_name
            + """<p>(vérifiez que le semestre n'est pas verrouillé et que vous
               avez l'autorisation d'effectuer cette opération)</p>
               <p><a href="moduleimpl_status?moduleimpl_id=%s">Continuer</a></p>
               """
            % E["moduleimpl_id"]
            + html_sco_header.sco_footer()
        )

    if E["description"]:
        page_title = 'Saisie des notes de "%s"' % E["description"]
    else:
        page_title = "Saisie des notes"

    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids=group_ids,
        formsemestre_id=formsemestre_id,
        select_all_when_unspecified=True,
        etat=None,
    )

    H = [
        html_sco_header.sco_header(
            page_title=page_title,
            javascripts=sco_groups_view.JAVASCRIPTS,
            cssstyles=sco_groups_view.CSSSTYLES,
            init_qtip=True,
        ),
        sco_evaluations.evaluation_describe(evaluation_id=evaluation_id),
        """<span class="eval_title">Saisie des notes par fichier</span>""",
    ]

    # Menu choix groupe:
    H.append("""<div id="group-tabs"><table><tr><td>""")
    H.append(sco_groups_view.form_groups_choice(groups_infos))
    H.append("</td></tr></table></div>")

    H.append(
        """<div class="saisienote_etape1">
        <span class="titredivsaisienote">Etape 1 : </span>
        <ul>
        <li><a href="feuille_saisie_notes?evaluation_id=%s&%s" class="stdlink" id="lnk_feuille_saisie">obtenir le fichier tableur à remplir</a></li>
        <li>ou <a class="stdlink" href="saisie_notes?evaluation_id=%s">aller au formulaire de saisie</a></li>
        </ul>
        </div>
        <form><input type="hidden" name="evaluation_id" id="formnotes_evaluation_id" value="%s"/></form>
        """
        % (evaluation_id, groups_infos.groups_query_args, evaluation_id, evaluation_id)
    )

    H.append(
        """<div class="saisienote_etape2">
    <span class="titredivsaisienote">Etape 2 : chargement d'un fichier de notes</span>"""  # '
    )

    nf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("evaluation_id", {"default": evaluation_id, "input_type": "hidden"}),
            (
                "notefile",
                {"input_type": "file", "title": "Fichier de note (.xls)", "size": 44},
            ),
            (
                "comment",
                {
                    "size": 44,
                    "title": "Commentaire",
                    "explanation": "(la colonne remarque du fichier excel est ignorée)",
                },
            ),
        ),
        formid="notesfile",
        submitlabel="Télécharger",
    )
    if nf[0] == 0:
        H.append(
            """<p>Le fichier doit être un fichier tableur obtenu via
        l'étape 1 ci-dessus, puis complété et enregistré au format Excel.
        </p>"""
        )
        H.append(nf[1])
    elif nf[0] == -1:
        H.append("<p>Annulation</p>")
    elif nf[0] == 1:
        updiag = do_evaluation_upload_xls()
        if updiag[0]:
            H.append(updiag[1])
            H.append(
                """<p>Notes chargées.&nbsp;&nbsp;&nbsp;
            <a class="stdlink" href="moduleimpl_status?moduleimpl_id=%(moduleimpl_id)s">
            Revenir au tableau de bord du module</a>
            &nbsp;&nbsp;&nbsp;
            <a class="stdlink" href="saisie_notes?evaluation_id=%(evaluation_id)s">Charger d'autres notes dans cette évaluation</a>
            </p>"""
                % E
            )
        else:
            H.append("""<p class="redboldtext">Notes non chargées !</p>""" + updiag[1])
            H.append(
                """
            <p><a class="stdlink" href="saisie_notes_tableur?evaluation_id=%(evaluation_id)s">
            Reprendre</a>
            </p>"""
                % E
            )
    #
    H.append("""</div><h3>Autres opérations</h3><ul>""")
    if sco_permissions_check.can_edit_notes(
        current_user, E["moduleimpl_id"], allow_ens=False
    ):
        H.append(
            """
        <li>
        <form action="do_evaluation_set_missing" method="GET">
        Mettre toutes les notes manquantes à <input type="text" size="5" name="value"/>
        <input type="submit" value="OK"/> 
        <input type="hidden" name="evaluation_id" value="%s"/> 
        <em>ABS indique "absent" (zéro), EXC "excusé" (neutralisées), ATT "attente"</em>
        </form>
        </li>        
        <li><a class="stdlink" href="evaluation_suppress_alln?evaluation_id=%s">Effacer toutes les notes de cette évaluation</a> (ceci permet ensuite de supprimer l'évaluation si besoin)
        </li>"""
            % (evaluation_id, evaluation_id)
        )  # '
    H.append(
        """<li><a class="stdlink" href="moduleimpl_status?moduleimpl_id=%(moduleimpl_id)s">Revenir au module</a></li>
    <li><a class="stdlink" href="saisie_notes?evaluation_id=%(evaluation_id)s">Revenir au formulaire de saisie</a></li>
    </ul>"""
        % E
    )

    H.append(
        """<h3>Explications</h3>
<ol>
<li>Etape 1: 
<ol><li>choisir le ou les groupes d'étudiants;</li>
    <li>télécharger le fichier Excel à remplir.</li>
</ol>
</li>
<li>Etape 2 (cadre vert): Indiquer le fichier Excel <em>téléchargé à l'étape 1</em> et dans lequel on a saisi des notes. Remarques:
<ul>
<li>le fichier Excel peut être incomplet: on peut ne saisir que quelques notes et répéter l'opération (en téléchargeant un nouveau fichier) plus tard;</li>
<li>seules les valeurs des notes modifiées sont prises en compte;</li>
<li>seules les notes sont extraites du fichier Excel;</li>
<li>on peut optionnellement ajouter un commentaire (type "copies corrigées par Dupont", ou "Modif. suite à contestation") dans la case "Commentaire".
</li>
<li>le fichier Excel <em>doit impérativement être celui chargé à l'étape 1 pour cette évaluation</em>. Il n'est pas possible d'utiliser une liste d'appel ou autre document Excel téléchargé d'une autre page.</li>
</ul>
</li>
</ol>
"""
    )
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def feuille_saisie_notes(evaluation_id, group_ids=[]):
    """Document Excel pour saisie notes dans l'évaluation et les groupes indiqués"""
    evals = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})
    if not evals:
        raise ScoValueError("invalid evaluation_id")
    E = evals[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    formsemestre_id = M["formsemestre_id"]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
    mod_responsable = sco_users.user_info(M["responsable_id"])
    if E["jour"]:
        indication_date = ndb.DateDMYtoISO(E["jour"])
    else:
        indication_date = scu.sanitize_filename(E["description"])[:12]
    evalname = "%s-%s" % (Mod["code"], indication_date)

    if E["description"]:
        evaltitre = "%s du %s" % (E["description"], E["jour"])
    else:
        evaltitre = "évaluation du %s" % E["jour"]
    description = "%s en %s (%s) resp. %s" % (
        evaltitre,
        Mod["abbrev"],
        Mod["code"],
        mod_responsable["prenomnom"],
    )

    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids=group_ids,
        formsemestre_id=formsemestre_id,
        select_all_when_unspecified=True,
        etat=None,
    )
    groups = sco_groups.listgroups(groups_infos.group_ids)
    gr_title_filename = sco_groups.listgroups_filename(groups)
    # gr_title = sco_groups.listgroups_abbrev(groups)
    if None in [g["group_name"] for g in groups]:  # tous les etudiants
        getallstudents = True
        # gr_title = "tous"
        gr_title_filename = "tous"
    else:
        getallstudents = False
    etudids = sco_groups.do_evaluation_listeetuds_groups(
        evaluation_id, groups, getallstudents=getallstudents, include_dems=True
    )

    # une liste de liste de chaines: lignes de la feuille de calcul
    L = []

    etuds = _get_sorted_etuds(E, etudids, formsemestre_id)
    for e in etuds:
        etudid = e["etudid"]
        groups = sco_groups.get_etud_groups(etudid, sem)
        grc = sco_groups.listgroups_abbrev(groups)

        L.append(
            [
                "%s" % etudid,
                e["nom"].upper(),
                e["prenom"].lower().capitalize(),
                e["inscr"]["etat"],
                grc,
                e["val"],
                e["explanation"],
            ]
        )

    filename = "notes_%s_%s" % (evalname, gr_title_filename)
    xls = sco_excel.excel_feuille_saisie(E, sem["titreannee"], description, lines=L)
    return scu.send_file(xls, filename, scu.XLSX_SUFFIX, mime=scu.XLSX_MIMETYPE)
    # return sco_excel.send_excel_file(xls, filename)


def has_existing_decision(M, E, etudid):
    """Verifie s'il y a une validation pour cet etudiant dans ce semestre ou UE
    Si oui, return True
    """
    formsemestre_id = M["formsemestre_id"]
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etud_decision_sem, get_etud_decision_ues
    if nt.get_etud_decision_sem(etudid):
        return True
    dec_ues = nt.get_etud_decision_ues(etudid)
    if dec_ues:
        mod = sco_edit_module.module_list({"module_id": M["module_id"]})[0]
        ue_id = mod["ue_id"]
        if ue_id in dec_ues:
            return True  # decision pour l'UE a laquelle appartient cette evaluation

    return False  # pas de decision de jury affectee par cette note


# -----------------------------
# Nouveau formulaire saisie notes (2016)


def saisie_notes(evaluation_id, group_ids=[]):
    """Formulaire saisie notes d'une évaluation pour un groupe"""
    group_ids = [int(group_id) for group_id in group_ids]
    evals = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})
    if not evals:
        raise ScoValueError("invalid evaluation_id")
    E = evals[0]
    M = sco_moduleimpl.moduleimpl_withmodule_list(moduleimpl_id=E["moduleimpl_id"])[0]
    formsemestre_id = M["formsemestre_id"]
    # Check access
    # (admin, respformation, and responsable_id)
    if not sco_permissions_check.can_edit_notes(current_user, E["moduleimpl_id"]):
        return (
            html_sco_header.sco_header()
            + "<h2>Modification des notes impossible pour %s</h2>"
            % current_user.user_name
            + """<p>(vérifiez que le semestre n'est pas verrouillé et que vous
               avez l'autorisation d'effectuer cette opération)</p>
               <p><a href="moduleimpl_status?moduleimpl_id=%s">Continuer</a></p>
               """
            % E["moduleimpl_id"]
            + html_sco_header.sco_footer()
        )

    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids=group_ids,
        formsemestre_id=formsemestre_id,
        select_all_when_unspecified=True,
        etat=None,
    )

    if E["description"]:
        page_title = 'Saisie "%s"' % E["description"]
    else:
        page_title = "Saisie des notes"

    # HTML page:
    H = [
        html_sco_header.sco_header(
            page_title=page_title,
            javascripts=sco_groups_view.JAVASCRIPTS + ["js/saisie_notes.js"],
            cssstyles=sco_groups_view.CSSSTYLES,
            init_qtip=True,
        ),
        sco_evaluations.evaluation_describe(evaluation_id=evaluation_id),
        '<div id="saisie_notes"><span class="eval_title">Saisie des notes</span>',
    ]
    H.append("""<div id="group-tabs"><table><tr><td>""")
    H.append(sco_groups_view.form_groups_choice(groups_infos))
    H.append('</td><td style="padding-left: 35px;">')
    H.append(
        htmlutils.make_menu(
            "Autres opérations",
            [
                {
                    "title": "Saisie par fichier tableur",
                    "id": "menu_saisie_tableur",
                    "endpoint": "notes.saisie_notes_tableur",
                    "args": {
                        "evaluation_id": E["evaluation_id"],
                        "group_ids": groups_infos.group_ids,
                    },
                },
                {
                    "title": "Voir toutes les notes du module",
                    "endpoint": "notes.evaluation_listenotes",
                    "args": {"moduleimpl_id": E["moduleimpl_id"]},
                },
                {
                    "title": "Effacer toutes les notes de cette évaluation",
                    "endpoint": "notes.evaluation_suppress_alln",
                    "args": {"evaluation_id": E["evaluation_id"]},
                },
            ],
            alone=True,
        )
    )
    H.append("""</td></tr></table></div>""")

    # Le formulaire de saisie des notes:
    destination = url_for(
        "notes.moduleimpl_status",
        scodoc_dept=g.scodoc_dept,
        moduleimpl_id=E["moduleimpl_id"],
    )

    form = _form_saisie_notes(E, M, groups_infos.group_ids, destination=destination)
    if form is None:
        log(f"redirecting to {destination}")
        return flask.redirect(destination)
    H.append(form)
    #
    H.append("</div>")  # /saisie_notes

    H.append(
        """<div class="sco_help">
    <p>Les modifications sont enregistrées au fur et à mesure.</p>
    <h4>Codes spéciaux:</h4>
    <ul>
    <li>ABS: absent (compte comme un zéro)</li>
    <li>EXC: excusé (note neutralisée)</li>
    <li>SUPR: pour supprimer une note existante</li>
    <li>ATT: note en attente (permet de publier une évaluation avec des notes manquantes)</li>
    </ul>
    </div>"""
    )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def _get_sorted_etuds(E, etudids, formsemestre_id):
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    NotesDB = sco_evaluations.do_evaluation_get_all_notes(
        E["evaluation_id"]
    )  # Notes existantes
    cnx = ndb.GetDBConnexion()
    etuds = []
    for etudid in etudids:
        # infos identite etudiant
        e = sco_etud.etudident_list(cnx, {"etudid": etudid})[0]
        sco_etud.format_etud_ident(e)
        etuds.append(e)
        # infos inscription dans ce semestre
        e["inscr"] = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            {"etudid": etudid, "formsemestre_id": formsemestre_id}
        )[0]
        # Groupes auxquels appartient cet étudiant:
        e["groups"] = sco_groups.get_etud_groups(etudid, sem)

        # Information sur absence (tenant compte de la demi-journée)
        jour_iso = ndb.DateDMYtoISO(E["jour"])
        warn_abs_lst = []
        if E["matin"]:
            nbabs = sco_abs.count_abs(etudid, jour_iso, jour_iso, matin=1)
            nbabsjust = sco_abs.count_abs_just(etudid, jour_iso, jour_iso, matin=1)
            if nbabs:
                if nbabsjust:
                    warn_abs_lst.append("absent justifié le matin !")
                else:
                    warn_abs_lst.append("absent le matin !")
        if E["apresmidi"]:
            nbabs = sco_abs.count_abs(etudid, jour_iso, jour_iso, matin=0)
            nbabsjust = sco_abs.count_abs_just(etudid, jour_iso, jour_iso, matin=0)
            if nbabs:
                if nbabsjust:
                    warn_abs_lst.append("absent justifié l'après-midi !")
                else:
                    warn_abs_lst.append("absent l'après-midi !")

        e["absinfo"] = '<span class="sn_abs">' + " ".join(warn_abs_lst) + "</span>  "

        # Note actuelle de l'étudiant:
        if etudid in NotesDB:
            e["val"] = _displayNote(NotesDB[etudid]["value"])
            comment = NotesDB[etudid]["comment"]
            if comment is None:
                comment = ""
            e["explanation"] = "%s (%s) %s" % (
                NotesDB[etudid]["date"].strftime("%d/%m/%y %Hh%M"),
                NotesDB[etudid]["uid"],
                comment,
            )
        else:
            e["val"] = ""
            e["explanation"] = ""
        # Démission ?
        if e["inscr"]["etat"] == "D":
            # if not e['val']:
            e["val"] = "DEM"
            e["explanation"] = "Démission"

    etuds.sort(key=lambda x: (x["nom"], x["prenom"]))

    return etuds


def _form_saisie_notes(E, M, group_ids, destination=""):
    """Formulaire HTML saisie des notes  dans l'évaluation E du moduleimpl M
    pour les groupes indiqués.

    On charge tous les étudiants, ne seront montrés que ceux
    des groupes sélectionnés grace a un filtre en javascript.
    """
    evaluation_id = E["evaluation_id"]
    formsemestre_id = M["formsemestre_id"]

    etudids = sco_groups.do_evaluation_listeetuds_groups(
        evaluation_id, getallstudents=True, include_dems=True
    )
    if not etudids:
        return '<div class="ue_warning"><span>Aucun étudiant sélectionné !</span></div>'

    # Decisions de jury existantes ?
    decisions_jury = {etudid: has_existing_decision(M, E, etudid) for etudid in etudids}
    # Nb de decisions de jury (pour les inscrits à l'évaluation):
    nb_decisions = sum(decisions_jury.values())

    etuds = _get_sorted_etuds(E, etudids, formsemestre_id)

    # Build form:
    descr = [
        ("evaluation_id", {"default": evaluation_id, "input_type": "hidden"}),
        ("formsemestre_id", {"default": formsemestre_id, "input_type": "hidden"}),
        ("group_ids", {"default": group_ids, "input_type": "hidden", "type": "list"}),
        # ('note_method', { 'default' : note_method, 'input_type' : 'hidden'}),
        ("comment", {"size": 44, "title": "Commentaire", "return_focus_next": True}),
        ("changed", {"default": "0", "input_type": "hidden"}),  # changed in JS
    ]
    if M["module"]["module_type"] == scu.MODULE_STANDARD:
        descr.append(
            (
                "s3",
                {
                    "input_type": "text",  # affiche le barème
                    "title": "Notes ",
                    "cssclass": "formnote_bareme",
                    "readonly": True,
                    "default": "&nbsp;/ %g" % E["note_max"],
                },
            )
        )
    elif M["module"]["module_type"] == scu.MODULE_MALUS:
        descr.append(
            (
                "s3",
                {
                    "input_type": "text",  # affiche le barème
                    "title": "",
                    "cssclass": "formnote_bareme",
                    "readonly": True,
                    "default": "Points de malus (soustraits à la moyenne de l'UE, entre -20 et 20)",
                },
            )
        )
    else:
        raise ValueError("invalid module type (%s)" % M["module"]["module_type"])  # bug

    initvalues = {}
    for e in etuds:
        etudid = e["etudid"]
        disabled = e["val"] == "DEM"
        etud_classes = []
        if disabled:
            classdem = " etud_dem"
            etud_classes.append("etud_dem")
            disabled_attr = 'disabled="%d"' % disabled
        else:
            classdem = ""
            disabled_attr = ""
        # attribue a chaque element une classe css par groupe:
        for group_info in e["groups"]:
            etud_classes.append("group-" + str(group_info["group_id"]))

        label = (
            '<span class="%s">' % classdem
            + e["civilite_str"]
            + " "
            + sco_etud.format_nomprenom(e, reverse=True)
            + "</span>"
        )

        # Historique des saisies de notes:
        if not disabled:
            explanation = (
                '<span id="hist_%s">' % etudid
                + get_note_history_menu(evaluation_id, etudid)
                + "</span>"
            )
        else:
            explanation = ""
        explanation = e["absinfo"] + explanation

        # Lien modif decision de jury:
        explanation += '<span id="jurylink_%s" class="jurylink"></span>' % etudid

        # Valeur actuelle du champ:
        initvalues["note_" + str(etudid)] = e["val"]
        label_link = '<a class="etudinfo" id="%s">%s</a>' % (etudid, label)

        # Element de formulaire:
        descr.append(
            (
                "note_" + str(etudid),
                {
                    "size": 5,
                    "title": label_link,
                    "explanation": explanation,
                    "return_focus_next": True,
                    "attributes": [
                        'class="note%s"' % classdem,
                        disabled_attr,
                        'data-last-saved-value="%s"' % e["val"],
                        'data-orig-value="%s"' % e["val"],
                        'data-etudid="%s"' % etudid,
                    ],
                    "template": """<tr%(item_dom_attr)s class="etud_elem """
                    + " ".join(etud_classes)
                    + """"><td class="tf-fieldlabel">%(label)s</td>
                    <td class="tf-field">%(elem)s</td></tr>
                    """,
                },
            )
        )
    #
    H = []
    if nb_decisions > 0:
        H.append(
            """<div class="saisie_warn">
        <ul class="tf-msg">
        <li class="tf-msg">Attention: il y a déjà des <b>décisions de jury</b> enregistrées pour %d étudiants. Après changement des notes, vérifiez la situation !</li>
        </ul>
        </div>"""
            % nb_decisions
        )
    # H.append('''<div id="sco_msg" class="head_message"></div>''')

    tf = TF(
        destination,
        scu.get_request_args(),
        descr,
        initvalues=initvalues,
        submitbutton=False,
        formid="formnotes",
        method="GET",
    )
    H.append(tf.getform())  # check and init
    H.append(
        f"""<a href="{url_for("notes.moduleimpl_status", scodoc_dept=g.scodoc_dept, 
        moduleimpl_id=M["moduleimpl_id"])
        }" class="btn btn-primary">Terminer</a>
        """
    )
    if tf.canceled():
        return None
    elif (not tf.submitted()) or not tf.result:
        # ajout formulaire saisie notes manquantes
        H.append(
            """
        <div>
        <form action="do_evaluation_set_missing" method="GET">
        Mettre <em>toutes</em> les notes manquantes à <input type="text" size="5" name="value"/>
        <input type="submit" value="OK"/> 
        <input type="hidden" name="evaluation_id" value="%s"/> 
        <em>affecte tous les groupes. ABS indique "absent" (zéro), EXC "excusé" (neutralisées), ATT "attente"</em>
        </form>
        </div>
        """
            % evaluation_id
        )
        # affiche formulaire
        return "\n".join(H)
    else:
        # form submission
        # rien à faire
        return None


def save_note(etudid=None, evaluation_id=None, value=None, comment=""):
    """Enregistre une note (ajax)"""
    authuser = current_user
    log(
        "save_note: evaluation_id=%s etudid=%s uid=%s value=%s"
        % (evaluation_id, etudid, authuser, value)
    )
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    Mod["url"] = url_for(
        "notes.moduleimpl_status",
        scodoc_dept=g.scodoc_dept,
        moduleimpl_id=M["moduleimpl_id"],
    )
    result = {"nbchanged": 0}  # JSON
    # Check access: admin, respformation, or responsable_id
    if not sco_permissions_check.can_edit_notes(authuser, E["moduleimpl_id"]):
        result["status"] = "unauthorized"
    else:
        L, _, _, _, _ = _check_notes([(etudid, value)], E, Mod)
        if L:
            nbchanged, _, existing_decisions = _notes_add(
                authuser, evaluation_id, L, comment=comment, do_it=True
            )
            sco_news.add(
                typ=sco_news.NEWS_NOTE,
                object=M["moduleimpl_id"],
                text='Chargement notes dans <a href="%(url)s">%(titre)s</a>' % Mod,
                url=Mod["url"],
                max_frequency=30 * 60,  # 30 minutes
            )
            result["nbchanged"] = nbchanged
            result["existing_decisions"] = existing_decisions
            if nbchanged > 0:
                result["history_menu"] = get_note_history_menu(evaluation_id, etudid)
            else:
                result["history_menu"] = ""  # no update needed
        result["status"] = "ok"
    return scu.sendJSON(result)


def get_note_history_menu(evaluation_id, etudid):
    """Menu HTML historique de la note"""
    history = sco_undo_notes.get_note_history(evaluation_id, etudid)
    if not history:
        return ""

    H = []
    if len(history) > 1:
        H.append(
            '<select data-etudid="%s" class="note_history" onchange="change_history(this);">'
            % etudid
        )
        envir = "select"
        item = "option"
    else:
        # pas de menu
        H.append('<span class="history">')
        envir = "span"
        item = "span"

    first = True
    for i in history:
        jt = i["date"].strftime("le %d/%m/%Y à %H:%M") + " (%s)" % i["user_name"]
        dispnote = _displayNote(i["value"])
        if first:
            nv = ""  # ne repete pas la valeur de la note courante
        else:
            # ancienne valeur
            nv = ": %s" % dispnote
        first = False
        if i["comment"]:
            comment = ' <span class="histcomment">%s</span>' % i["comment"]
        else:
            comment = ""
        H.append(
            '<%s data-note="%s">%s %s%s</%s>' % (item, dispnote, jt, nv, comment, item)
        )

    H.append("</%s>" % envir)
    return "\n".join(H)
