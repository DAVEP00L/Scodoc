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

"""Tableau de bord module
"""
import time
import urllib

from flask import g, url_for
from flask_login import current_user
from app.auth.models import User

import app.scodoc.sco_utils as scu
from app.scodoc.sco_permissions import Permission

from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_abs
from app.scodoc import sco_compute_moy
from app.scodoc import sco_cache
from app.scodoc import sco_edit_module
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_permissions_check
from app.scodoc import sco_users

# ported from old DTML code in oct 2009

# menu evaluation dans moduleimpl
def moduleimpl_evaluation_menu(evaluation_id, nbnotes=0):
    "Menu avec actions sur une evaluation"
    E = sco_evaluations.do_evaluation_list({"evaluation_id": evaluation_id})[0]
    modimpl = sco_moduleimpl.moduleimpl_list(moduleimpl_id=E["moduleimpl_id"])[0]

    group_id = sco_groups.get_default_group(modimpl["formsemestre_id"])

    if (
        sco_permissions_check.can_edit_notes(
            current_user, E["moduleimpl_id"], allow_ens=False
        )
        and nbnotes != 0
    ):
        sup_label = "Supprimer évaluation impossible (il y a des notes)"
    else:
        sup_label = "Supprimer évaluation"

    menuEval = [
        {
            "title": "Saisir notes",
            "endpoint": "notes.saisie_notes",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": sco_permissions_check.can_edit_notes(
                current_user, E["moduleimpl_id"]
            ),
        },
        {
            "title": "Modifier évaluation",
            "endpoint": "notes.evaluation_edit",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": sco_permissions_check.can_edit_notes(
                current_user, E["moduleimpl_id"], allow_ens=False
            ),
        },
        {
            "title": sup_label,
            "endpoint": "notes.evaluation_delete",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": nbnotes == 0
            and sco_permissions_check.can_edit_notes(
                current_user, E["moduleimpl_id"], allow_ens=False
            ),
        },
        {
            "title": "Supprimer toutes les notes",
            "endpoint": "notes.evaluation_suppress_alln",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": sco_permissions_check.can_edit_notes(
                current_user, E["moduleimpl_id"], allow_ens=False
            ),
        },
        {
            "title": "Afficher les notes",
            "endpoint": "notes.evaluation_listenotes",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": nbnotes > 0,
        },
        {
            "title": "Placement étudiants",
            "endpoint": "notes.placement_eval_selectetuds",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": sco_permissions_check.can_edit_notes(
                current_user, E["moduleimpl_id"]
            ),
        },
        {
            "title": "Absences ce jour",
            "endpoint": "absences.EtatAbsencesDate",
            "args": {
                "date": E["jour"],
                "group_ids": group_id,
            },
            "enabled": E["jour"],
        },
        {
            "title": "Vérifier notes vs absents",
            "endpoint": "notes.evaluation_check_absences_html",
            "args": {
                "evaluation_id": evaluation_id,
            },
            "enabled": nbnotes > 0 and E["jour"],
        },
    ]

    return htmlutils.make_menu("actions", menuEval, alone=True)


def moduleimpl_status(moduleimpl_id=None, partition_id=None):
    """Tableau de bord module (liste des evaluations etc)"""
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    formsemestre_id = M["formsemestre_id"]
    Mod = sco_edit_module.module_list(args={"module_id": M["module_id"]})[0]
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    ModInscrits = sco_moduleimpl.do_moduleimpl_inscription_list(
        moduleimpl_id=M["moduleimpl_id"]
    )

    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    ModEvals = sco_evaluations.do_evaluation_list({"moduleimpl_id": moduleimpl_id})
    ModEvals.sort(
        key=lambda x: (x["numero"], x["jour"], x["heure_debut"]), reverse=True
    )  # la plus RECENTE en tête

    #
    caneditevals = sco_permissions_check.can_edit_notes(
        current_user, moduleimpl_id, allow_ens=sem["ens_can_edit_eval"]
    )
    caneditnotes = sco_permissions_check.can_edit_notes(current_user, moduleimpl_id)
    arrow_up, arrow_down, arrow_none = sco_groups.get_arrow_icons_tags()
    #
    module_resp = User.query.get(M["responsable_id"])
    H = [
        html_sco_header.sco_header(page_title="Module %(titre)s" % Mod),
        """<h2 class="formsemestre">Module <tt>%(code)s</tt> %(titre)s</h2>""" % Mod,
        """<div class="moduleimpl_tableaubord">
    <table>
    <tr>
    <td class="fichetitre2">Responsable: </td><td class="redboldtext">""",
        module_resp.get_nomcomplet(),  # sco_users.user_info(M["responsable_id"])["nomprenom"],
        f"""<span class="blacktt">({module_resp.user_name})</span>""",
    ]
    try:
        sco_moduleimpl.can_change_module_resp(moduleimpl_id)
        H.append(
            """<a class="stdlink" href="edit_moduleimpl_resp?moduleimpl_id=%s">modifier</a>"""
            % moduleimpl_id
        )
    except:
        pass
    H.append("""</td><td>""")
    H.append(
        ", ".join([sco_users.user_info(m["ens_id"])["nomprenom"] for m in M["ens"]])
    )
    H.append("""</td><td>""")
    try:
        sco_moduleimpl.can_change_ens(moduleimpl_id)
        H.append(
            """<a class="stdlink" href="edit_enseignants_form?moduleimpl_id=%s">modifier les enseignants</a>"""
            % moduleimpl_id
        )
    except:
        pass
    H.append("""</td></tr>""")

    # 2ieme ligne: Semestre, Coef
    H.append("""<tr><td class="fichetitre2">""")
    if sem["semestre_id"] >= 0:
        H.append("""Semestre: </td><td>%s""" % sem["semestre_id"])
    else:
        H.append("""</td><td>""")
    if not sem["etat"]:
        H.append(scu.icontag("lock32_img", title="verrouillé"))
    H.append(
        """</td><td class="fichetitre2">Coef dans le semestre: %(coefficient)s</td><td></td></tr>"""
        % Mod
    )
    # 3ieme ligne: Formation
    H.append(
        """<tr><td class="fichetitre2">Formation: </td><td>%(titre)s</td></tr>""" % F
    )
    # Ligne: Inscrits
    H.append(
        """<tr><td class="fichetitre2">Inscrits: </td><td> %d étudiants"""
        % len(ModInscrits)
    )
    if current_user.has_permission(Permission.ScoEtudInscrit):
        H.append(
            """<a class="stdlink" style="margin-left:2em;" href="moduleimpl_inscriptions_edit?moduleimpl_id=%s">modifier</a>"""
            % M["moduleimpl_id"]
        )
    H.append("</td></tr>")
    # Ligne: règle de calcul
    has_expression = sco_compute_moy.moduleimpl_has_expression(M)
    if has_expression:
        H.append(
            '<tr><td class="fichetitre2" colspan="4">Règle de calcul: <span class="formula" title="mode de calcul de la moyenne du module">moyenne=<tt>%s</tt></span>'
            % M["computation_expr"]
        )
        if sco_moduleimpl.can_change_ens(moduleimpl_id, raise_exc=False):
            H.append(
                '<span class="fl"><a class="stdlink"  href="edit_moduleimpl_expr?moduleimpl_id=%s">modifier</a></span>'
                % moduleimpl_id
            )
        H.append("</td></tr>")
    else:
        H.append(
            '<tr><td colspan="4"><em title="mode de calcul de la moyenne du module">règle de calcul standard</em>'
        )
        if sco_moduleimpl.can_change_ens(moduleimpl_id, raise_exc=False):
            H.append(
                ' (<a class="stdlink" href="edit_moduleimpl_expr?moduleimpl_id=%s">changer</a>)'
                % moduleimpl_id
            )
        H.append("</td></tr>")
    H.append(
        '<tr><td colspan="4"><span class="moduleimpl_abs_link"><a class="stdlink" href="view_module_abs?moduleimpl_id=%s">Absences dans ce module</a></span>'
        % moduleimpl_id
    )
    # Adapté à partir d'une suggestion de DS (Le Havre)
    # Liens saisies absences seulement si permission et date courante dans le semestre
    if current_user.has_permission(
        Permission.ScoAbsChange
    ) and sco_formsemestre.sem_est_courant(sem):
        datelundi = sco_abs.ddmmyyyy(time.strftime("%d/%m/%Y")).prev_monday()
        group_id = sco_groups.get_default_group(formsemestre_id)
        H.append(
            f"""
        <span class="moduleimpl_abs_link"><a class="stdlink" 
        href="{url_for("absences.SignaleAbsenceGrHebdo", 
        scodoc_dept=g.scodoc_dept,formsemestre_id=formsemestre_id, 
        moduleimpl_id=moduleimpl_id, datelundi=datelundi, group_ids=group_id)}">
        Saisie Absences hebdo.</a></span>
        """
        )

    H.append("</td></tr></table>")
    #
    if has_expression and nt.expr_diagnostics:
        H.append(sco_formsemestre_status.html_expr_diagnostic(nt.expr_diagnostics))
    #
    if nt.sem_has_decisions():
        H.append(
            """<ul class="tf-msg"><li class="tf-msg warning">Décisions de jury saisies: seul le responsable du semestre peut saisir des notes (il devra modifier les décisions de jury).</li></ul>"""
        )
    #
    H.append(
        """<p><form name="f"><span style="font-size:120%%; font-weight: bold;">%d évaluations :</span>
<span style="padding-left: 30px;">
<input type="hidden" name="moduleimpl_id" value="%s"/>"""
        % (len(ModEvals), moduleimpl_id)
    )
    #
    # Liste les noms de partitions
    partitions = sco_groups.get_partitions_list(sem["formsemestre_id"])
    H.append(
        """Afficher les groupes de&nbsp;<select name="partition_id" onchange="document.f.submit();">"""
    )
    been_selected = False
    for partition in partitions:
        if not partition_id and not been_selected:
            selected = "selected"
            been_selected = True
        if partition["partition_id"] == partition_id:
            selected = "selected"
        else:
            selected = ""
        name = partition["partition_name"]
        if name is None:
            name = "Tous"
        H.append(
            """<option value="%s" %s>%s</option>"""
            % (partition["partition_id"], selected, name)
        )
    H.append(
        """</select>
&nbsp;&nbsp;&nbsp;&nbsp;
<a class="stdlink" href="evaluation_listenotes?moduleimpl_id=%(moduleimpl_id)s">Voir toutes les notes</a>
</span>
</form>
</p>
"""
        % M
    )

    # -------- Tableau des evaluations
    top_table_links = ""
    if sem["etat"]:  # non verrouillé
        top_table_links = (
            """<a class="stdlink" href="evaluation_create?moduleimpl_id=%(moduleimpl_id)s">Créer nouvelle évaluation</a>
        <a class="stdlink" style="margin-left:2em;" href="module_evaluation_renumber?moduleimpl_id=%(moduleimpl_id)s&redirect=1">Trier par date</a>
        """
            % M
        )
    if ModEvals:
        H.append(
            '<div class="moduleimpl_evaluations_top_links">'
            + top_table_links
            + "</div>"
        )
    H.append("""<table class="moduleimpl_evaluations">""")
    eval_index = len(ModEvals) - 1
    first = True
    for eval in ModEvals:
        etat = sco_evaluations.do_evaluation_etat(
            eval["evaluation_id"],
            partition_id=partition_id,
            select_first_partition=True,
        )
        if eval["evaluation_type"] in (
            scu.EVALUATION_RATTRAPAGE,
            scu.EVALUATION_SESSION2,
        ):
            tr_class = "mievr mievr_rattr"
        else:
            tr_class = "mievr"
        tr_class_1 = "mievr"
        if first:
            first = False
        else:
            H.append("""<tr><td colspan="8">&nbsp;</td></tr>""")
            tr_class_1 += " mievr_spaced"
        H.append("""<tr class="%s"><td class="mievr_tit" colspan="8">""" % tr_class_1)
        if eval["jour"]:
            H.append("""Le %(jour)s%(descrheure)s""" % eval)
        else:
            H.append(
                """<a href="evaluation_edit?evaluation_id=%(evaluation_id)s" class="mievr_evalnodate">Evaluation sans date</a>"""
                % eval
            )
        H.append("&nbsp;&nbsp;&nbsp; <em>%(description)s</em>" % eval)
        if eval["evaluation_type"] == scu.EVALUATION_RATTRAPAGE:
            H.append(
                """<span class="mievr_rattr" title="remplace si meilleure note">rattrapage</span>"""
            )
        elif eval["evaluation_type"] == scu.EVALUATION_SESSION2:
            H.append(
                """<span class="mievr_rattr" title="remplace autres notes">session 2</span>"""
            )
        if etat["last_modif"]:
            H.append(
                """<span class="mievr_lastmodif">(dernière modif le %s)</span>"""
                % etat["last_modif"].strftime("%d/%m/%Y à %Hh%M")
            )
        H.append('<span class="evalindex_cont">')
        if has_expression or True:
            H.append(
                """<span class="evalindex" title="Indice dans les vecteurs (formules)">%2d</span>"""
                % eval_index
            )
        # Fleches:
        H.append('<span class="eval_arrows_chld">')
        if eval_index != (len(ModEvals) - 1) and caneditevals:
            H.append(
                '<a href="module_evaluation_move?evaluation_id=%s&after=0" class="aud">%s</a>'
                % (eval["evaluation_id"], arrow_up)
            )
        else:
            H.append(arrow_none)
        if (eval_index > 0) and caneditevals:
            H.append(
                '<a href="module_evaluation_move?evaluation_id=%s&after=1" class="aud">%s</a>'
                % (eval["evaluation_id"], arrow_down)
            )
        else:
            H.append(arrow_none)
        H.append("</span></span>")

        eval_index -= 1
        H.append("""</td></tr>""")
        H.append(
            """<tr class="%s"><th class="moduleimpl_evaluations" colspan="2">&nbsp;</th><th class="moduleimpl_evaluations">Durée</th><th class="moduleimpl_evaluations">Coef.</th><th class="moduleimpl_evaluations">Notes</th><th class="moduleimpl_evaluations">Abs</th><th class="moduleimpl_evaluations">N</th><th class="moduleimpl_evaluations">Moyenne """
            % tr_class
        )

        if etat["evalcomplete"]:
            etat_txt = """(prise en compte)"""
            etat_descr = "notes utilisées dans les moyennes"
        elif eval["publish_incomplete"]:
            etat_txt = """(prise en compte <b>immédiate</b>)"""
            etat_descr = (
                "il manque des notes, mais la prise en compte immédiate a été demandée"
            )
        elif etat["nb_notes"] != 0:
            etat_txt = "(<b>non</b> prise en compte)"
            etat_descr = "il manque des notes"
        else:
            etat_txt = ""
        if caneditevals and etat_txt:
            etat_txt = (
                '<a href="evaluation_edit?evaluation_id=%s" title="%s">%s</a>'
                % (eval["evaluation_id"], etat_descr, etat_txt)
            )
        H.append(etat_txt)
        H.append("""</th></tr>""")

        H.append("""<tr class="%s"><td class="mievr">""" % tr_class)
        if caneditevals:
            H.append(
                """<a class="smallbutton" href="evaluation_edit?evaluation_id=%s">%s</a>"""
                % (
                    eval["evaluation_id"],
                    scu.icontag(
                        "edit_img", alt="modifier", title="Modifier informations"
                    ),
                )
            )
        if caneditnotes:
            H.append(
                """<a class="smallbutton" href="saisie_notes?evaluation_id=%s">%s</a>"""
                % (
                    eval["evaluation_id"],
                    scu.icontag(
                        "notes_img", alt="saisie notes", title="Saisie des notes"
                    ),
                )
            )
        if etat["nb_notes"] == 0:
            if caneditevals:
                H.append(
                    """<a class="smallbutton" href="evaluation_delete?evaluation_id=%(evaluation_id)s">"""
                    % eval
                )
            H.append(scu.icontag("delete_img", alt="supprimer", title="Supprimer"))
            if caneditevals:
                H.append("""</a>""")
        elif etat["evalcomplete"]:
            H.append(
                """<a class="smallbutton" href="evaluation_listenotes?evaluation_id=%s">%s</a>"""
                % (eval["evaluation_id"], scu.icontag("status_green_img", title="ok"))
            )
        else:
            if etat["evalattente"]:
                H.append(
                    """<a class="smallbutton" href="evaluation_listenotes?evaluation_id=%s">%s</a>"""
                    % (
                        eval["evaluation_id"],
                        scu.icontag(
                            "status_greenorange_img",
                            file_format="gif",
                            title="notes en attente",
                        ),
                    )
                )
            else:
                H.append(
                    """<a class="smallbutton" href="evaluation_listenotes?evaluation_id=%s">%s</a>"""
                    % (
                        eval["evaluation_id"],
                        scu.icontag("status_orange_img", title="il manque des notes"),
                    )
                )
        #
        if eval["visibulletin"]:
            H.append(
                scu.icontag(
                    "status_visible_img", title="visible dans bulletins intermédiaires"
                )
            )
        else:
            H.append("&nbsp;")
        H.append('</td><td class="mievr_menu">')
        if caneditnotes:
            H.append(
                moduleimpl_evaluation_menu(
                    eval["evaluation_id"],
                    nbnotes=etat["nb_notes"],
                )
            )
        H.append("</td>")
        #
        H.append(
            """
<td class="mievr_dur">%s</td><td class="rightcell mievr_coef">%s</td>"""
            % (eval["duree"], "%g" % eval["coefficient"])
        )
        H.append(
            """<td class="rightcell mievr_nbnotes">%(nb_notes)s / %(nb_inscrits)s</td>
<td class="rightcell mievr_coef">%(nb_abs)s</td>
<td class="rightcell mievr_coef">%(nb_neutre)s</td>
<td class="rightcell">"""
            % etat
        )
        if etat["moy"]:
            H.append("<b>%s / %g</b>" % (etat["moy"], eval["note_max"]))
            H.append(
                """&nbsp; (<a href="evaluation_listenotes?evaluation_id=%s">afficher</a>)"""
                % (eval["evaluation_id"],)
            )
        else:
            H.append(
                """<a class="redlink" href="saisie_notes?evaluation_id=%s">saisir notes</a>"""
                % (eval["evaluation_id"])
            )
        H.append("""</td></tr>""")
        #
        if etat["nb_notes"] == 0:
            H.append("""<tr class="%s"><td colspan="8">&nbsp;""" % tr_class)
            H.append("""</td></tr>""")
        else:  # il y a deja des notes saisies
            gr_moyennes = etat["gr_moyennes"]
            for gr_moyenne in gr_moyennes:
                H.append("""<tr class="%s">""" % tr_class)
                H.append("""<td colspan="2">&nbsp;</td>""")
                if gr_moyenne["group_name"] is None:
                    name = "Tous"  # tous
                else:
                    name = "Groupe %s" % gr_moyenne["group_name"]
                H.append(
                    """<td colspan="5" class="mievr_grtit">%s &nbsp;</td><td>""" % name
                )
                if gr_moyenne["gr_nb_notes"] > 0:
                    H.append("%(gr_moy)s" % gr_moyenne)
                    H.append(
                        """&nbsp; (<a href="evaluation_listenotes?tf_submitted=1&evaluation_id=%s&group_ids%%3Alist=%s">%s notes</a>"""
                        % (
                            eval["evaluation_id"],
                            gr_moyenne["group_id"],
                            gr_moyenne["gr_nb_notes"],
                        )
                    )
                    if gr_moyenne["gr_nb_att"] > 0:
                        H.append(
                            """, <span class="redboldtext">%s en attente</span>"""
                            % gr_moyenne["gr_nb_att"]
                        )
                    H.append(""")""")
                    if gr_moyenne["group_id"] in etat["gr_incomplets"]:
                        H.append("""[<font color="red">""")
                        if caneditnotes:
                            H.append(
                                """<a class="redlink" href="saisie_notes?evaluation_id=%s&group_ids:list=%s">incomplet</a></font>]"""
                                % (eval["evaluation_id"], gr_moyenne["group_id"])
                            )
                        else:
                            H.append("""incomplet</font>]""")
                else:
                    H.append("""<span class="redboldtext">&nbsp; """)
                    if caneditnotes:
                        H.append(
                            """<a class="redlink" href="saisie_notes?evaluation_id=%s&group_ids:list=%s">"""
                            % (eval["evaluation_id"], gr_moyenne["group_id"])
                        )
                    H.append("pas de notes")
                    if caneditnotes:
                        H.append("""</a>""")
                    H.append("</span>")
                H.append("""</td></tr>""")

    #
    if caneditevals or not sem["etat"]:
        H.append("""<tr><td colspan="8">""")
        if not sem["etat"]:
            H.append("""%s semestre verrouillé""" % scu.icontag("lock32_img"))
        else:
            H.append(top_table_links)

    H.append(
        """</td></tr>
</table>

</div>

<!-- LEGENDE -->
<hr>
<h4>Légende</h4>
<ul>
<li>%s : modifie description de l'évaluation (date, heure, coefficient, ...)</li>
<li>%s : saisie des notes</li>
<li>%s : indique qu'il n'y a aucune note entrée (cliquer pour supprimer cette évaluation)</li>
<li>%s : indique qu'il manque quelques notes dans cette évaluation</li>
<li>%s : toutes les notes sont entrées (cliquer pour les afficher)</li>
<li>%s : indique que cette évaluation sera mentionnée dans les bulletins au format "intermédiaire"
</ul>

<p>Rappel : seules les notes des évaluations complètement saisies (affichées en vert) apparaissent dans les bulletins.
</p>
    """
        % (
            scu.icontag("edit_img"),
            scu.icontag("notes_img"),
            scu.icontag("delete_img"),
            scu.icontag("status_orange_img"),
            scu.icontag("status_green_img"),
            scu.icontag("status_visible_img"),
        )
    )
    H.append(html_sco_header.sco_footer())
    return "".join(H)
