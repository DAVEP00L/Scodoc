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

"""Liste des notes d'une évaluation
"""
from operator import itemgetter
import urllib

import flask
from flask import url_for, g, request

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc import htmlutils
from app.scodoc import html_sco_header
from app.scodoc import sco_abs
from app.scodoc import sco_cache
from app.scodoc import sco_edit_module
from app.scodoc import sco_evaluations
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_preferences
from app.scodoc import sco_etud
from app.scodoc import sco_users
import sco_version
from app.scodoc.gen_tables import GenTable
from app.scodoc.htmlutils import histogram_notes


def do_evaluation_listenotes():
    """
    Affichage des notes d'une évaluation

    args: evaluation_id ou moduleimpl_id
    (si moduleimpl_id, affiche toutes les évaluations du module)
    """
    mode = None
    vals = scu.get_request_args()
    if "evaluation_id" in vals:
        evaluation_id = int(vals["evaluation_id"])
        mode = "eval"
        evals = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})
    if "moduleimpl_id" in vals and vals["moduleimpl_id"]:
        moduleimpl_id = int(vals["moduleimpl_id"])
        mode = "module"
        evals = sco_evaluations.do_evaluation_list({"moduleimpl_id": moduleimpl_id})
    if not mode:
        raise ValueError("missing argument: evaluation or module")
    if not evals:
        return "<p>Aucune évaluation !</p>"

    format = vals.get("format", "html")
    E = evals[0]  # il y a au moins une evaluation
    # description de l'evaluation
    if mode == "eval":
        H = [sco_evaluations.evaluation_describe(evaluation_id=evaluation_id)]
    else:
        H = []
    # groupes
    groups = sco_groups.do_evaluation_listegroupes(
        E["evaluation_id"], include_default=True
    )
    grlabs = [g["group_name"] or "tous" for g in groups]  # legendes des boutons
    grnams = [str(g["group_id"]) for g in groups]  # noms des checkbox

    if len(evals) > 1:
        descr = [
            ("moduleimpl_id", {"default": E["moduleimpl_id"], "input_type": "hidden"})
        ]
    else:
        descr = [
            ("evaluation_id", {"default": E["evaluation_id"], "input_type": "hidden"})
        ]
    if len(grnams) > 1:
        descr += [
            (
                "s",
                {
                    "input_type": "separator",
                    "title": "<b>Choix du ou des groupes d'étudiants:</b>",
                },
            ),
            (
                "group_ids",
                {
                    "input_type": "checkbox",
                    "title": "",
                    "allowed_values": grnams,
                    "labels": grlabs,
                    "attributes": ('onclick="document.tf.submit();"',),
                },
            ),
        ]
    else:
        if grnams:
            def_nam = grnams[0]
        else:
            def_nam = ""
        descr += [
            (
                "group_ids",
                {"input_type": "hidden", "type": "list", "default": [def_nam]},
            )
        ]
    descr += [
        (
            "anonymous_listing",
            {
                "input_type": "checkbox",
                "title": "",
                "allowed_values": ("yes",),
                "labels": ('listing "anonyme"',),
                "attributes": ('onclick="document.tf.submit();"',),
                "template": '<tr><td class="tf-fieldlabel">%(label)s</td><td class="tf-field">%(elem)s &nbsp;&nbsp;',
            },
        ),
        (
            "note_sur_20",
            {
                "input_type": "checkbox",
                "title": "",
                "allowed_values": ("yes",),
                "labels": ("notes sur 20",),
                "attributes": ('onclick="document.tf.submit();"',),
                "template": "%(elem)s &nbsp;&nbsp;",
            },
        ),
        (
            "hide_groups",
            {
                "input_type": "checkbox",
                "title": "",
                "allowed_values": ("yes",),
                "labels": ("masquer les groupes",),
                "attributes": ('onclick="document.tf.submit();"',),
                "template": "%(elem)s &nbsp;&nbsp;",
            },
        ),
        (
            "with_emails",
            {
                "input_type": "checkbox",
                "title": "",
                "allowed_values": ("yes",),
                "labels": ("montrer les e-mails",),
                "attributes": ('onclick="document.tf.submit();"',),
                "template": "%(elem)s</td></tr>",
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        cancelbutton=None,
        submitbutton=None,
        bottom_buttons=False,
        method="GET",
        cssclass="noprint",
        name="tf",
        is_submitted=True,  # toujours "soumis" (démarre avec liste complète)
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1]
    elif tf[0] == -1:
        return flask.redirect(
            "%s/Notes/moduleimpl_status?moduleimpl_id=%s"
            % (scu.ScoURL(), E["moduleimpl_id"])
        )
    else:
        anonymous_listing = tf[2]["anonymous_listing"]
        note_sur_20 = tf[2]["note_sur_20"]
        hide_groups = tf[2]["hide_groups"]
        with_emails = tf[2]["with_emails"]
        return _make_table_notes(
            tf[1],
            evals,
            format=format,
            note_sur_20=note_sur_20,
            anonymous_listing=anonymous_listing,
            group_ids=tf[2]["group_ids"],
            hide_groups=hide_groups,
            with_emails=with_emails,
        )


def _make_table_notes(
    html_form,
    evals,
    format="",
    note_sur_20=False,
    anonymous_listing=False,
    hide_groups=False,
    with_emails=False,
    group_ids=[],
):
    """Generate table for evaluations marks"""
    if not evals:
        return "<p>Aucune évaluation !</p>"
    E = evals[0]
    moduleimpl_id = E["moduleimpl_id"]
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
    # (debug) check that all evals are in same module:
    for e in evals:
        if e["moduleimpl_id"] != moduleimpl_id:
            raise ValueError("invalid evaluations list")

    if format == "xls":
        keep_numeric = True  # pas de conversion des notes en strings
    else:
        keep_numeric = False
    # Si pas de groupe, affiche tout
    if not group_ids:
        group_ids = [sco_groups.get_default_group(M["formsemestre_id"])]
    groups = sco_groups.listgroups(group_ids)

    gr_title = sco_groups.listgroups_abbrev(groups)
    gr_title_filename = sco_groups.listgroups_filename(groups)

    etudids = sco_groups.do_evaluation_listeetuds_groups(
        E["evaluation_id"], groups, include_dems=True
    )

    if anonymous_listing:
        columns_ids = ["code"]  # cols in table
    else:
        if format == "xls" or format == "xml":
            columns_ids = ["nom", "prenom"]
        else:
            columns_ids = ["nomprenom"]
    if not hide_groups:
        columns_ids.append("group")

    titles = {
        "code": "Code",
        "group": "Groupe",
        "nom": "Nom",
        "prenom": "Prénom",
        "nomprenom": "Nom",
        "expl_key": "Rem.",
        "email": "e-mail",
        "emailperso": "e-mail perso",
    }

    rows = []

    class keymgr(dict):  # comment : key (pour regrouper les comments a la fin)
        def __init__(self):
            self.lastkey = 1

        def nextkey(self):
            r = self.lastkey
            self.lastkey += 1
            # self.lastkey = chr(ord(self.lastkey)+1)
            return str(r)

    K = keymgr()
    for etudid in etudids:
        css_row_class = None
        # infos identite etudiant
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        # infos inscription
        inscr = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            {"etudid": etudid, "formsemestre_id": M["formsemestre_id"]}
        )[0]

        if inscr["etat"] == "I":  # si inscrit, indique groupe
            groups = sco_groups.get_etud_groups(etudid, sem)
            grc = sco_groups.listgroups_abbrev(groups)
        else:
            if inscr["etat"] == "D":
                grc = "DEM"  # attention: ce code est re-ecrit plus bas, ne pas le changer (?)
                css_row_class = "etuddem"
            else:
                grc = inscr["etat"]

        code = ""  # code pour listings anonyme, à la place du nom
        if sco_preferences.get_preference("anonymous_lst_code") == "INE":
            code = etud["code_ine"]
        elif sco_preferences.get_preference("anonymous_lst_code") == "NIP":
            code = etud["code_nip"]
        if not code:  # laisser le code vide n'aurait aucun sens, prenons l'etudid
            code = etudid

        rows.append(
            {
                "code": str(code),  # INE, NIP ou etudid
                "_code_td_attrs": 'style="padding-left: 1em; padding-right: 2em;"',
                "etudid": etudid,
                "nom": etud["nom"].upper(),
                "_nomprenom_target": "formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s"
                % (M["formsemestre_id"], etudid),
                "_nomprenom_td_attrs": 'id="%s" class="etudinfo"' % (etud["etudid"]),
                "prenom": etud["prenom"].lower().capitalize(),
                "nomprenom": etud["nomprenom"],
                "group": grc,
                "email": etud["email"],
                "emailperso": etud["emailperso"],
                "_css_row_class": css_row_class or "",
            }
        )

    # Lignes en tête:
    coefs = {
        "nom": "",
        "prenom": "",
        "nomprenom": "",
        "group": "",
        "code": "",
        "_css_row_class": "sorttop fontitalic",
        "_table_part": "head",
    }
    note_max = {
        "nom": "",
        "prenom": "",
        "nomprenom": "",
        "group": "",
        "code": "",
        "_css_row_class": "sorttop fontitalic",
        "_table_part": "head",
    }
    moys = {
        "_css_row_class": "moyenne sortbottom",
        "_table_part": "foot",
        #'_nomprenom_td_attrs' : 'colspan="2" ',
        "nomprenom": "Moyenne (sans les absents) :",
        "comment": "",
    }
    # Ajoute les notes de chaque évaluation:
    for e in evals:
        e["eval_state"] = sco_evaluations.do_evaluation_etat(e["evaluation_id"])
        notes, nb_abs, nb_att = _add_eval_columns(
            e,
            rows,
            titles,
            coefs,
            note_max,
            moys,
            K,
            note_sur_20,
            keep_numeric,
        )
        columns_ids.append(e["evaluation_id"])
    #
    if anonymous_listing:
        rows.sort(key=lambda x: x["code"] or "")
    else:
        rows.sort(
            key=lambda x: (x["nom"] or "", x["prenom"] or "")
        )  # sort by nom, prenom

    # Si module, ajoute moyenne du module:
    if len(evals) > 1:
        _add_moymod_column(
            sem["formsemestre_id"],
            e,
            rows,
            titles,
            coefs,
            note_max,
            moys,
            note_sur_20,
            keep_numeric,
        )
        columns_ids.append("moymod")

    # Ajoute colonnes emails tout à droite:
    if with_emails:
        columns_ids += ["email", "emailperso"]
    # Ajoute lignes en tête et moyennes
    if len(evals) > 0:
        rows = [coefs, note_max] + rows
    rows.append(moys)
    # ajout liens HTMl vers affichage une evaluation:
    if format == "html" and len(evals) > 1:
        rlinks = {"_table_part": "head"}
        for e in evals:
            rlinks[e["evaluation_id"]] = "afficher"
            rlinks[
                "_" + str(e["evaluation_id"]) + "_help"
            ] = "afficher seulement les notes de cette évaluation"
            rlinks["_" + str(e["evaluation_id"]) + "_target"] = url_for(
                "notes.evaluation_listenotes",
                scodoc_dept=g.scodoc_dept,
                evaluation_id=e["evaluation_id"],
            )
            rlinks["_" + str(e["evaluation_id"]) + "_td_attrs"] = ' class="tdlink" '
        rows.append(rlinks)

    if len(evals) == 1:  # colonne "Rem." seulement si une eval
        if format == "html":  # pas d'indication d'origine en pdf (pour affichage)
            columns_ids.append("expl_key")
        elif format == "xls" or format == "xml":
            columns_ids.append("comment")

    # titres divers:
    gl = "".join(["&group_ids%3Alist=" + str(g) for g in group_ids])
    if note_sur_20:
        gl = "&note_sur_20%3Alist=yes" + gl
    if anonymous_listing:
        gl = "&anonymous_listing%3Alist=yes" + gl
    if hide_groups:
        gl = "&hide_groups%3Alist=yes" + gl
    if with_emails:
        gl = "&with_emails%3Alist=yes" + gl
    if len(evals) == 1:
        evalname = "%s-%s" % (Mod["code"], ndb.DateDMYtoISO(E["jour"]))
        hh = "%s, %s (%d étudiants)" % (E["description"], gr_title, len(etudids))
        filename = scu.make_filename("notes_%s_%s" % (evalname, gr_title_filename))
        caption = hh
        pdf_title = "%(description)s (%(jour)s)" % e
        html_title = ""
        base_url = "evaluation_listenotes?evaluation_id=%s" % E["evaluation_id"] + gl
        html_next_section = (
            '<div class="notes_evaluation_stats">%d absents, %d en attente.</div>'
            % (nb_abs, nb_att)
        )
    else:
        filename = scu.make_filename("notes_%s_%s" % (Mod["code"], gr_title_filename))
        title = "Notes du module %(code)s %(titre)s" % Mod
        title += " semestre %(titremois)s" % sem
        if gr_title and gr_title != "tous":
            title += " %s" % gr_title
        caption = title
        html_next_section = ""
        if format == "pdf":
            caption = ""  # same as pdf_title
        pdf_title = title
        html_title = (
            """<h2 class="formsemestre">Notes du module <a href="moduleimpl_status?moduleimpl_id=%s">%s %s</a></h2>"""
            % (moduleimpl_id, Mod["code"], Mod["titre"])
        )
        base_url = "evaluation_listenotes?moduleimpl_id=%s" % moduleimpl_id + gl
    # display
    tab = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=rows,
        html_sortable=True,
        base_url=base_url,
        filename=filename,
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption=caption,
        html_next_section=html_next_section,
        page_title="Notes de " + sem["titremois"],
        html_title=html_title,
        pdf_title=pdf_title,
        html_class="table_leftalign notes_evaluation",
        preferences=sco_preferences.SemPreferences(M["formsemestre_id"]),
        # html_generate_cells=False # la derniere ligne (moyennes) est incomplete
    )

    t = tab.make_page(format=format, with_html_headers=False)
    if format != "html":
        return t

    if len(evals) > 1:
        all_complete = True
        for e in evals:
            if not e["eval_state"]["evalcomplete"]:
                all_complete = False
        if all_complete:
            eval_info = '<span class="eval_info eval_complete">Evaluations prises en compte dans les moyennes</span>'
        else:
            eval_info = '<span class="eval_info help">Les évaluations en vert et orange sont prises en compte dans les moyennes. Celles en rouge n\'ont pas toutes leurs notes.</span>'
        return html_form + eval_info + t + "<p></p>"
    else:
        # Une seule evaluation: ajoute histogramme
        histo = histogram_notes(notes)
        # 2 colonnes: histo, comments
        C = [
            "<table><tr><td><div><h4>Répartition des notes:</h4>"
            + histo
            + "</div></td>\n",
            '<td style="padding-left: 50px; vertical-align: top;"><p>',
        ]
        commentkeys = list(K.items())  # [ (comment, key), ... ]
        commentkeys.sort(key=lambda x: int(x[1]))
        for (comment, key) in commentkeys:
            C.append(
                '<span class="colcomment">(%s)</span> <em>%s</em><br/>' % (key, comment)
            )
        if commentkeys:
            C.append(
                '<span><a class=stdlink" href="evaluation_list_operations?evaluation_id=%s">Gérer les opérations</a></span><br/>'
                % E["evaluation_id"]
            )
        eval_info = "xxx"
        if E["eval_state"]["evalcomplete"]:
            eval_info = '<span class="eval_info eval_complete">Evaluation prise en compte dans les moyennes</span>'
        elif E["eval_state"]["evalattente"]:
            eval_info = '<span class="eval_info eval_attente">Il y a des notes en attente (les autres sont prises en compte)</span>'
        else:
            eval_info = '<span class="eval_info eval_incomplete">Notes incomplètes, évaluation non prise en compte dans les moyennes</span>'

        return (
            sco_evaluations.evaluation_describe(evaluation_id=E["evaluation_id"])
            + eval_info
            + html_form
            + t
            + "\n".join(C)
        )


def _add_eval_columns(
    e, rows, titles, coefs, note_max, moys, K, note_sur_20, keep_numeric
):
    """Add eval e"""
    nb_notes = 0
    nb_abs = 0
    nb_att = 0
    sum_notes = 0
    notes = []  # liste des notes numeriques, pour calcul histogramme uniquement
    evaluation_id = e["evaluation_id"]
    NotesDB = sco_evaluations.do_evaluation_get_all_notes(evaluation_id)
    for row in rows:
        etudid = row["etudid"]
        if etudid in NotesDB:
            val = NotesDB[etudid]["value"]
            if val is None:
                nb_abs += 1
            if val == scu.NOTES_ATTENTE:
                nb_att += 1
            # calcul moyenne SANS LES ABSENTS
            if val != None and val != scu.NOTES_NEUTRALISE and val != scu.NOTES_ATTENTE:
                if e["note_max"] > 0:
                    valsur20 = val * 20.0 / e["note_max"]  # remet sur 20
                else:
                    valsur20 = 0
                notes.append(valsur20)  # toujours sur 20 pour l'histogramme
                if note_sur_20:
                    val = valsur20  # affichage notes / 20 demandé
                nb_notes = nb_notes + 1
                sum_notes += val
            val_fmt = scu.fmt_note(val, keep_numeric=keep_numeric)
            comment = NotesDB[etudid]["comment"]
            if comment is None:
                comment = ""
            explanation = "%s (%s) %s" % (
                NotesDB[etudid]["date"].strftime("%d/%m/%y %Hh%M"),
                sco_users.user_info(NotesDB[etudid]["uid"])["nomcomplet"],
                comment,
            )
        else:
            explanation = ""
            val_fmt = ""
            val = None

        if val is None:
            row["_" + str(evaluation_id) + "_td_attrs"] = 'class="etudabs" '
            if not row.get("_css_row_class", ""):
                row["_css_row_class"] = "etudabs"
        # regroupe les commentaires
        if explanation:
            if explanation in K:
                expl_key = "(%s)" % K[explanation]
            else:
                K[explanation] = K.nextkey()
                expl_key = "(%s)" % K[explanation]
        else:
            expl_key = ""

        row.update(
            {
                evaluation_id: val_fmt,
                "_" + str(evaluation_id) + "_help": explanation,
                # si plusieurs evals seront ecrasés et non affichés:
                "comment": explanation,
                "expl_key": expl_key,
                "_expl_key_help": explanation,
            }
        )

        coefs[evaluation_id] = "coef. %s" % e["coefficient"]
        if note_sur_20:
            nmax = 20.0
        else:
            nmax = e["note_max"]
        if keep_numeric:
            note_max[evaluation_id] = nmax
        else:
            note_max[evaluation_id] = "/ %s" % nmax

        if nb_notes > 0:
            moys[evaluation_id] = "%.3g" % (sum_notes / nb_notes)
            moys[
                "_" + str(evaluation_id) + "_help"
            ] = "moyenne sur %d notes (%s le %s)" % (
                nb_notes,
                e["description"],
                e["jour"],
            )
        else:
            moys[evaluation_id] = ""

        titles[evaluation_id] = "%(description)s (%(jour)s)" % e

        if e["eval_state"]["evalcomplete"]:
            titles["_" + str(evaluation_id) + "_td_attrs"] = 'class="eval_complete"'
        elif e["eval_state"]["evalattente"]:
            titles["_" + str(evaluation_id) + "_td_attrs"] = 'class="eval_attente"'
        else:
            titles["_" + str(evaluation_id) + "_td_attrs"] = 'class="eval_incomplete"'

    return notes, nb_abs, nb_att  # pour histogramme


def _add_moymod_column(
    formsemestre_id,
    e,
    rows,
    titles,
    coefs,
    note_max,
    moys,
    note_sur_20,
    keep_numeric,
):
    """Ajoute la colonne moymod à rows"""
    col_id = "moymod"
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_etud_mod_moy
    nb_notes = 0
    sum_notes = 0
    notes = []  # liste des notes numeriques, pour calcul histogramme uniquement
    for row in rows:
        etudid = row["etudid"]
        val = nt.get_etud_mod_moy(
            e["moduleimpl_id"], etudid
        )  # note sur 20, ou 'NA','NI'
        row[col_id] = scu.fmt_note(val, keep_numeric=keep_numeric)
        row["_" + col_id + "_td_attrs"] = ' class="moyenne" '
        if not isinstance(val, str):
            notes.append(val)
            nb_notes = nb_notes + 1
            sum_notes += val
    coefs[col_id] = "(avec abs)"
    if keep_numeric:
        note_max[col_id] = 20.0
    else:
        note_max[col_id] = "/ 20"
    titles[col_id] = "Moyenne module"
    if nb_notes > 0:
        moys[col_id] = "%.3g" % (sum_notes / nb_notes)
        moys["_" + col_id + "_help"] = "moyenne des moyennes"
    else:
        moys[col_id] = ""


# ---------------------------------------------------------------------------------


# matin et/ou après-midi ?
def _eval_demijournee(E):
    "1 si matin, 0 si apres midi, 2 si toute la journee"
    am, pm = False, False
    if E["heure_debut"] < "13:00":
        am = True
    if E["heure_fin"] > "13:00":
        pm = True
    if am and pm:
        demijournee = 2
    elif am:
        demijournee = 1
    else:
        demijournee = 0
        pm = True
    return am, pm, demijournee


def evaluation_check_absences(evaluation_id):
    """Vérifie les absences au moment de cette évaluation.
    Cas incohérents que l'on peut rencontrer pour chaque étudiant:
      note et absent
      ABS et pas noté absent
      ABS et absent justifié
      EXC et pas noté absent
      EXC et pas justifie
    Ramene 3 listes d'etudid
    """
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    if not E["jour"]:
        return [], [], [], [], []  # evaluation sans date

    etudids = sco_groups.do_evaluation_listeetuds_groups(
        evaluation_id, getallstudents=True
    )

    am, pm, demijournee = _eval_demijournee(E)

    # Liste les absences à ce moment:
    A = sco_abs.list_abs_jour(ndb.DateDMYtoISO(E["jour"]), am=am, pm=pm)
    As = set([x["etudid"] for x in A])  # ensemble des etudiants absents
    NJ = sco_abs.list_abs_non_just_jour(ndb.DateDMYtoISO(E["jour"]), am=am, pm=pm)
    NJs = set([x["etudid"] for x in NJ])  # ensemble des etudiants absents non justifies
    Just = sco_abs.list_abs_jour(
        ndb.DateDMYtoISO(E["jour"]), am=am, pm=pm, is_abs=None, is_just=True
    )
    Justs = set([x["etudid"] for x in Just])  # ensemble des etudiants avec justif

    # Les notes:
    NotesDB = sco_evaluations.do_evaluation_get_all_notes(evaluation_id)
    ValButAbs = []  # une note mais noté absent
    AbsNonSignalee = []  # note ABS mais pas noté absent
    ExcNonSignalee = []  # note EXC mais pas noté absent
    ExcNonJust = []  #  note EXC mais absent non justifie
    AbsButExc = []  # note ABS mais justifié
    for etudid in etudids:
        if etudid in NotesDB:
            val = NotesDB[etudid]["value"]
            if (
                val != None and val != scu.NOTES_NEUTRALISE and val != scu.NOTES_ATTENTE
            ) and etudid in As:
                # note valide et absent
                ValButAbs.append(etudid)
            if val is None and not etudid in As:
                # absent mais pas signale comme tel
                AbsNonSignalee.append(etudid)
            if val == scu.NOTES_NEUTRALISE and not etudid in As:
                # Neutralisé mais pas signale absent
                ExcNonSignalee.append(etudid)
            if val == scu.NOTES_NEUTRALISE and etudid in NJs:
                # EXC mais pas justifié
                ExcNonJust.append(etudid)
            if val is None and etudid in Justs:
                # ABS mais justificatif
                AbsButExc.append(etudid)

    return ValButAbs, AbsNonSignalee, ExcNonSignalee, ExcNonJust, AbsButExc


def evaluation_check_absences_html(evaluation_id, with_header=True, show_ok=True):
    """Affiche etat verification absences d'une evaluation"""

    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    am, pm, demijournee = _eval_demijournee(E)

    (
        ValButAbs,
        AbsNonSignalee,
        ExcNonSignalee,
        ExcNonJust,
        AbsButExc,
    ) = evaluation_check_absences(evaluation_id)

    if with_header:
        H = [
            html_sco_header.html_sem_header("Vérification absences à l'évaluation"),
            sco_evaluations.evaluation_describe(evaluation_id=evaluation_id),
            """<p class="help">Vérification de la cohérence entre les notes saisies et les absences signalées.</p>""",
        ]
    else:
        # pas de header, mais un titre
        H = [
            """<h2 class="eval_check_absences">%s du %s """
            % (E["description"], E["jour"])
        ]
        if (
            not ValButAbs
            and not AbsNonSignalee
            and not ExcNonSignalee
            and not ExcNonJust
        ):
            H.append(': <span class="eval_check_absences_ok">ok</span>')
        H.append("</h2>")

    def etudlist(etudids, linkabs=False):
        H.append("<ul>")
        if not etudids and show_ok:
            H.append("<li>aucun</li>")
        for etudid in etudids:
            etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
            H.append(
                '<li><a class="discretelink" href="%s">'
                % url_for(
                    "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
                )
                + "%(nomprenom)s</a>" % etud
            )
            if linkabs:
                H.append(
                    f"""<a class="stdlink" href="{url_for(
                    'absences.doSignaleAbsence', 
                    scodoc_dept=g.scodoc_dept, 
                    etudid=etud["etudid"],
                    datedebut=E["jour"],
                    datefin=E["jour"],
                    demijournee=demijournee,
                    moduleimpl_id=E["moduleimpl_id"],
                    )
                    }">signaler cette absence</a>"""
                )
            H.append("</li>")
        H.append("</ul>")

    if ValButAbs or show_ok:
        H.append(
            "<h3>Etudiants ayant une note alors qu'ils sont signalés absents:</h3>"
        )
        etudlist(ValButAbs)

    if AbsNonSignalee or show_ok:
        H.append(
            """<h3>Etudiants avec note "ABS" alors qu'ils ne sont <em>pas</em> signalés absents:</h3>"""
        )
        etudlist(AbsNonSignalee, linkabs=True)

    if ExcNonSignalee or show_ok:
        H.append(
            """<h3>Etudiants avec note "EXC" alors qu'ils ne sont <em>pas</em> signalés absents:</h3>"""
        )
        etudlist(ExcNonSignalee)

    if ExcNonJust or show_ok:
        H.append(
            """<h3>Etudiants avec note "EXC" alors qu'ils sont absents <em>non justifiés</em>:</h3>"""
        )
        etudlist(ExcNonJust)

    if AbsButExc or show_ok:
        H.append(
            """<h3>Etudiants avec note "ABS" alors qu'ils ont une <em>justification</em>:</h3>"""
        )
        etudlist(AbsButExc)

    if with_header:
        H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def formsemestre_check_absences_html(formsemestre_id):
    """Affiche etat verification absences pour toutes les evaluations du semestre !"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    H = [
        html_sco_header.html_sem_header(
            "Vérification absences aux évaluations de ce semestre",
            sem,
        ),
        """<p class="help">Vérification de la cohérence entre les notes saisies et les absences signalées.
          Sont listés tous les modules avec des évaluations.<br/>Aucune action n'est effectuée:
          il vous appartient de corriger les erreurs détectées si vous le jugez nécessaire.
          </p>""",
    ]
    # Modules, dans l'ordre
    Mlist = sco_moduleimpl.moduleimpl_withmodule_list(formsemestre_id=formsemestre_id)
    for M in Mlist:
        evals = sco_evaluations.do_evaluation_list(
            {"moduleimpl_id": M["moduleimpl_id"]}
        )
        if evals:
            H.append(
                '<div class="module_check_absences"><h2><a href="moduleimpl_status?moduleimpl_id=%s">%s: %s</a></h2>'
                % (M["moduleimpl_id"], M["module"]["code"], M["module"]["abbrev"])
            )
        for E in evals:
            H.append(
                evaluation_check_absences_html(
                    E["evaluation_id"],
                    with_header=False,
                    show_ok=False,
                )
            )
        if evals:
            H.append("</div>")
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)
