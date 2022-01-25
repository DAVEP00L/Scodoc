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

"""Affichage étudiants d'un ou plusieurs groupes
   sous forme: de liste html (table exportable), de trombinoscope (exportable en pdf)
"""

# Re-ecriture en 2014 (re-organisation de l'interface, modernisation du code)

import collections
import datetime
import operator
import urllib
from urllib.parse import parse_qs
import time


from flask import url_for, g, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
from app.scodoc import html_sco_header
from app.scodoc import sco_abs
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app.scodoc import sco_etud
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_permissions import Permission

JAVASCRIPTS = html_sco_header.BOOTSTRAP_MULTISELECT_JS + [
    "js/etud_info.js",
    "js/groups_view.js",
]

CSSSTYLES = html_sco_header.BOOTSTRAP_MULTISELECT_CSS

# view:
def groups_view(
    group_ids=(),
    format="html",
    # Options pour listes:
    with_codes=0,
    etat=None,
    with_paiement=0,  # si vrai, ajoute colonnes infos paiement droits et finalisation inscription (lent car interrogation portail)
    with_archives=0,  # ajoute colonne avec noms fichiers archivés
    with_annotations=0,
    formsemestre_id=None,  # utilise si aucun groupe selectionné
):
    """Affichage des étudiants des groupes indiqués
    group_ids: liste de group_id
    format: csv, json, xml, xls, allxls, xlsappel, moodlecsv, pdf
    """
    # Informations sur les groupes à afficher:
    groups_infos = DisplayedGroupsInfos(
        group_ids,
        formsemestre_id=formsemestre_id,
        etat=etat,
        select_all_when_unspecified=True,
    )
    # Formats spéciaux: download direct
    if format != "html":
        return groups_table(
            groups_infos=groups_infos,
            format=format,
            with_codes=with_codes,
            etat=etat,
            with_paiement=with_paiement,
            with_archives=with_archives,
            with_annotations=with_annotations,
        )

    H = [
        html_sco_header.sco_header(
            javascripts=JAVASCRIPTS,
            cssstyles=CSSSTYLES,
            init_qtip=True,
        )
    ]
    # Menu choix groupe
    H.append("""<div id="group-tabs">""")
    H.append(form_groups_choice(groups_infos, submit_on_change=True))
    # Note: le formulaire est soumis a chaque modif des groupes
    # on pourrait faire comme pour le form de saisie des notes. Il faudrait pour cela:
    #  - charger tous les etudiants au debut, quels que soient les groupes selectionnés
    #  - ajouter du JS pour modifier les liens (arguments group_ids) quand le menu change

    # Tabs
    # H.extend( ("""<span>toto</span><ul id="toto"><li>item 1</li><li>item 2</li></ul>""",) )
    H.extend(
        (
            """<ul class="nav nav-tabs">
    <li class="active"><a href="#tab-listes" data-toggle="tab">Listes</a></li>
    <li><a href="#tab-photos" data-toggle="tab">Photos</a></li>
    <li><a href="#tab-abs" data-toggle="tab">Absences et feuilles...</a></li>
    </ul>
    </div>
    <!-- Tab panes -->
    <div class="tab-content">
    <div class="tab-pane active" id="tab-listes">
    """,
            groups_table(
                groups_infos=groups_infos,
                format=format,
                with_codes=with_codes,
                etat=etat,
                with_paiement=with_paiement,
                with_archives=with_archives,
                with_annotations=with_annotations,
            ),
            "</div>",
            """<div class="tab-pane" id="tab-photos">""",
            tab_photos_html(groups_infos, etat=etat),
            #'<p>hello</p>',
            "</div>",
            '<div class="tab-pane" id="tab-abs">',
            tab_absences_html(groups_infos, etat=etat),
            "</div>",
        )
    )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def form_groups_choice(groups_infos, with_selectall_butt=False, submit_on_change=False):
    """form pour selection groupes
    group_ids est la liste des groupes actuellement sélectionnés
    et doit comporter au moins un élément, sauf si formsemestre_id est spécifié.
    (utilisé pour retrouver le semestre et proposer la liste des autres groupes)

    Si submit_on_change, ajoute une classe "submit_on_change" qui est utilisee en JS
    """
    default_group_id = sco_groups.get_default_group(groups_infos.formsemestre_id)

    H = [
        """<form id="group_selector" method="get">
    <input type="hidden" name="formsemestre_id" id="formsemestre_id" value="%s"/>
    <input type="hidden" name="default_group_id" id="default_group_id" value="%s"/>
    Groupes: 
    """
        % (groups_infos.formsemestre_id, default_group_id)
    ]

    H.append(menu_groups_choice(groups_infos, submit_on_change=submit_on_change))

    if with_selectall_butt:
        H.append(
            """<input type="button" value="sélectionner tous" onmousedown="select_tous();"/>"""
        )
    H.append("</form>")

    return "\n".join(H)


def menu_groups_choice(groups_infos, submit_on_change=False):
    """menu pour selection groupes
    group_ids est la liste des groupes actuellement sélectionnés
    et doit comporter au moins un élément, sauf si formsemestre_id est spécifié.
    (utilisé pour retrouver le semestre et proposer la liste des autres groupes)
    """
    default_group_id = sco_groups.get_default_group(groups_infos.formsemestre_id)

    if submit_on_change:
        klass = "submit_on_change"
    else:
        klass = ""
    H = [
        """<select name="group_ids" id="group_ids_sel" class="multiselect %s" multiple="multiple">
    """
        % (klass,)
    ]

    n_members = len(sco_groups.get_group_members(default_group_id))
    if default_group_id in groups_infos.group_ids:
        selected = "selected"
    else:
        selected = ""
    H.append(
        '<option class="default_group" value="%s" %s>%s (%s)</option>'
        % (default_group_id, selected, "Tous", n_members)
    )

    for partition in groups_infos.partitions:
        H.append('<optgroup label="%s">' % partition["partition_name"])
        # Les groupes dans cette partition:
        for g in sco_groups.get_partition_groups(partition):
            if g["group_id"] in groups_infos.group_ids:
                selected = "selected"
            else:
                selected = ""
            if g["group_name"]:
                n_members = len(sco_groups.get_group_members(g["group_id"]))
                H.append(
                    '<option value="%s" %s>%s (%s)</option>'
                    % (g["group_id"], selected, g["group_name"], n_members)
                )
        H.append("</optgroup>")
    H.append("</select> ")
    return "\n".join(H)


def menu_group_choice(group_id=None, formsemestre_id=None):
    """Un bête menu pour choisir un seul groupe
    group_id est le groupe actuellement sélectionné.
    Si aucun groupe selectionné, utilise formsemestre_id pour lister les groupes.
    """
    if group_id:
        group = sco_groups.get_group(group_id)
        formsemestre_id = group["formsemestre_id"]
    elif not formsemestre_id:
        raise ValueError("missing formsemestre_id")
    H = [
        """
    <select id="group_selector_u" name="group_id" onchange="reload_selected_group();">
    """
    ]
    if not group_id:
        H.append('<option value="">choisir...</option>')
    for partition in sco_groups.get_partitions_list(formsemestre_id):
        if partition["partition_name"]:
            H.append('<optgroup label="%s">' % partition["partition_name"])
        groups = sco_groups.get_partition_groups(partition)
        for group in groups:
            if group["group_id"] == group_id:
                selected = "selected"
            else:
                selected = ""
            name = group["group_name"] or "Tous"
            n_members = len(sco_groups.get_group_members(group["group_id"]))
            H.append(
                '<option value="%s" %s>%s (%s)</option>'
                % (group["group_id"], selected, name, n_members)
            )
        if partition["partition_name"]:
            H.append("</optgroup>")
    H.append(
        """</select>
    <script>
function reload_selected_group() {
var url = $.url();
var group_id = $("#group_selector_u").val();
if (group_id) {
  url.param()['group_id'] = group_id;
  var query_string = $.param(url.param(), traditional=true );
  window.location = url.attr('base') + url.attr('path') + '?' + query_string;
}
}
    </script>
    """
    )
    return "\n".join(H)


class DisplayedGroupsInfos(object):
    """Container with attributes describing groups to display in the page
    .groups_query_args : 'group_ids=xxx&group_ids=yyy'
    .base_url : url de la requete, avec les groupes, sans les autres paramètres
    .formsemestre_id : semestre "principal" (en fait celui du 1er groupe de la liste)
    .members
    .groups_titles
    """

    def __init__(
        self,
        group_ids=(),  # groupes specifies dans l'URL, ou un seul int
        formsemestre_id=None,
        etat=None,
        select_all_when_unspecified=False,
        moduleimpl_id=None,  # used to find formsemestre when unspecified
    ):
        if isinstance(group_ids, int):
            if group_ids:
                group_ids = [group_ids]  # cas ou un seul parametre, pas de liste
        else:
            group_ids = [int(g) for g in group_ids]
        if not formsemestre_id and moduleimpl_id:
            mods = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)
            if len(mods) != 1:
                raise ValueError("invalid moduleimpl_id")
            formsemestre_id = mods[0]["formsemestre_id"]

        if not group_ids:  # appel sans groupe (eg page accueil)
            if not formsemestre_id:
                raise Exception("missing parameter formsemestre_id or group_ids")
            if select_all_when_unspecified:
                group_ids = [sco_groups.get_default_group(formsemestre_id)]
            else:
                # selectionne le premier groupe trouvé, s'il y en a un
                partition = sco_groups.get_partitions_list(
                    formsemestre_id, with_default=True
                )[0]
                groups = sco_groups.get_partition_groups(partition)
                if groups:
                    group_ids = [groups[0]["group_id"]]
                else:
                    group_ids = [sco_groups.get_default_group(formsemestre_id)]

        gq = []
        for group_id in group_ids:
            gq.append("group_ids=" + str(group_id))
        self.groups_query_args = "&".join(gq)
        self.base_url = request.base_url + "?" + self.groups_query_args
        self.group_ids = group_ids
        self.groups = []
        groups_titles = []
        self.members = []
        self.tous_les_etuds_du_sem = (
            False  # affiche tous les etuds du semestre ? (si un seul semestre)
        )
        self.sems = collections.OrderedDict()  # formsemestre_id : sem
        self.formsemestre = None
        self.formsemestre_id = formsemestre_id
        self.nbdem = 0  # nombre d'étudiants démissionnaires en tout
        sem = None
        selected_partitions = set()
        for group_id in group_ids:
            group_members, group, group_tit, sem, nbdem = sco_groups.get_group_infos(
                group_id, etat=etat
            )
            self.groups.append(group)
            self.nbdem += nbdem
            self.sems[sem["formsemestre_id"]] = sem
            if not self.formsemestre_id:
                self.formsemestre_id = sem["formsemestre_id"]
                self.formsemestre = sem
            self.members.extend(group_members)
            groups_titles.append(group_tit)
            if group["group_name"] == None:
                self.tous_les_etuds_du_sem = True
            else:
                # liste les partitions explicitement sélectionnés (= des groupes de group_ids)
                selected_partitions.add((group["numero"], group["partition_id"]))

        self.selected_partitions = [
            x[1] for x in sorted(list(selected_partitions))
        ]  # -> [ partition_id ]

        if not self.formsemestre:  # aucun groupe selectionne
            self.formsemestre = sco_formsemestre.get_formsemestre(formsemestre_id)

        self.sortuniq()

        if len(self.sems) > 1:
            self.tous_les_etuds_du_sem = False  # plusieurs semestres
        if self.tous_les_etuds_du_sem:
            if sem and sem["semestre_id"] >= 0:
                self.groups_titles = "S%d" % sem["semestre_id"]
            else:
                self.groups_titles = "tous"
            self.groups_filename = self.groups_titles
        else:
            self.groups_titles = ", ".join(groups_titles)
            self.groups_filename = "_".join(groups_titles).replace(" ", "_")
            # Sanitize filename:
            self.groups_filename = scu.make_filename(self.groups_filename)

        # colonnes pour affichages nom des groupes:
        # gère le cas où les étudiants appartiennent à des semestres différents
        self.partitions = []  # les partitions, sans celle par defaut
        for formsemestre_id in self.sems:
            for partition in sco_groups.get_partitions_list(formsemestre_id):
                if partition["partition_name"]:
                    self.partitions.append(partition)

    def sortuniq(self):
        "Trie les étudiants (de plusieurs groupes) et elimine les doublons"
        if (len(self.group_ids) <= 1) or len(self.members) <= 1:
            return  # on suppose que les etudiants d'un groupe sont deja triés
        self.members.sort(
            key=operator.itemgetter("nom_disp", "prenom")
        )  # tri selon nom_usuel ou nom
        to_remove = []
        T = self.members
        for i in range(len(T) - 1, 0, -1):
            if T[i - 1]["etudid"] == T[i]["etudid"]:
                to_remove.append(i)
        for i in to_remove:
            del T[i]

    def get_form_elem(self):
        """html hidden input with groups"""
        H = []
        for group_id in self.group_ids:
            H.append('<input type="hidden" name="group_ids" value="%s"/>' % group_id)
        return "\n".join(H)


# Ancien ZScolar.group_list renommé ici en group_table
def groups_table(
    groups_infos=None,  # instance of DisplayedGroupsInfos
    with_codes=0,
    etat=None,
    format="html",
    with_paiement=0,  # si vrai, ajoute colonnes infos paiement droits et finalisation inscription (lent car interrogation portail)
    with_archives=0,  # ajoute colonne avec noms fichiers archivés
    with_annotations=0,
):
    """liste etudiants inscrits dans ce semestre
    format: csv, json, xml, xls, allxls, xlsappel, moodlecsv, pdf
    Si with_codes, ajoute 4 colonnes avec les codes etudid, NIP, INE et etape
    """
    from app.scodoc import sco_report

    # log(
    #     "enter groups_table %s: %s"
    #     % (groups_infos.members[0]["nom"], groups_infos.members[0].get("etape", "-"))
    # )
    with_codes = int(with_codes)
    with_paiement = int(with_paiement)
    with_archives = int(with_archives)
    with_annotations = int(with_annotations)

    base_url_np = groups_infos.base_url + "&with_codes=%s" % with_codes
    base_url = (
        base_url_np
        + "&with_paiement=%s&with_archives=%s&with_annotations=%s"
        % (with_paiement, with_archives, with_annotations)
    )
    #
    columns_ids = ["civilite_str", "nom_disp", "prenom"]  # colonnes a inclure
    titles = {
        "civilite_str": "Civ.",
        "nom_disp": "Nom",
        "prenom": "Prénom",
        "email": "Mail",
        "emailperso": "Personnel",
        "etat": "Etat",
        "etudid": "etudid",
        "code_nip": "code_nip",
        "code_ine": "code_ine",
        "datefinalisationinscription_str": "Finalisation inscr.",
        "paiementinscription_str": "Paiement",
        "etudarchive": "Fichiers",
        "annotations_str": "Annotations",
        "etape": "Etape",
        "semestre_groupe": "Semestre-Groupe",  # pour Moodle
    }

    # ajoute colonnes pour groupes
    columns_ids.extend([p["partition_id"] for p in groups_infos.partitions])
    titles.update(
        dict(
            [(p["partition_id"], p["partition_name"]) for p in groups_infos.partitions]
        )
    )
    partitions_name = {
        p["partition_id"]: p["partition_name"] for p in groups_infos.partitions
    }

    if format != "html":  # ne mentionne l'état que en Excel (style en html)
        columns_ids.append("etat")
    columns_ids.append("email")
    columns_ids.append("emailperso")

    if format == "moodlecsv":
        columns_ids = ["email", "semestre_groupe"]

    if with_codes:
        columns_ids += ["etape", "etudid", "code_nip", "code_ine"]
    if with_paiement:
        columns_ids += ["datefinalisationinscription_str", "paiementinscription_str"]
    if with_paiement:  #  or with_codes:
        sco_portal_apogee.check_paiement_etuds(groups_infos.members)
    if with_archives:
        from app.scodoc import sco_archives_etud

        sco_archives_etud.add_archives_info_to_etud_list(groups_infos.members)
        columns_ids += ["etudarchive"]
    if with_annotations:
        sco_etud.add_annotations_to_etud_list(groups_infos.members)
        columns_ids += ["annotations_str"]
    moodle_sem_name = groups_infos.formsemestre["session_id"]
    moodle_groupenames = set()
    # ajoute liens
    for etud in groups_infos.members:
        if etud["email"]:
            etud["_email_target"] = "mailto:" + etud["email"]
        else:
            etud["_email_target"] = ""
        if etud["emailperso"]:
            etud["_emailperso_target"] = "mailto:" + etud["emailperso"]
        else:
            etud["_emailperso_target"] = ""
        fiche_url = url_for(
            "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
        )
        etud["_nom_disp_target"] = fiche_url
        etud["_prenom_target"] = fiche_url

        etud["_nom_disp_td_attrs"] = 'id="%s" class="etudinfo"' % (etud["etudid"])

        if etud["etat"] == "D":
            etud["_css_row_class"] = "etuddem"
        # et groupes:
        for partition_id in etud["partitions"]:
            etud[partition_id] = etud["partitions"][partition_id]["group_name"]
        # Ajoute colonne pour moodle: semestre_groupe, de la forme
        #     RT-DUT-FI-S3-2021-PARTITION-GROUPE
        moodle_groupename = []
        if groups_infos.selected_partitions:
            # il y a des groupes selectionnes, utilise leurs partitions
            for partition_id in groups_infos.selected_partitions:
                if partition_id in etud["partitions"]:
                    moodle_groupename.append(
                        partitions_name[partition_id]
                        + "-"
                        + etud["partitions"][partition_id]["group_name"]
                    )
        else:
            # pas de groupes sélectionnés: prend le premier s'il y en a un
            moodle_groupename = ["tous"]
            if etud["partitions"]:
                for p in etud["partitions"].items():  # partitions is an OrderedDict
                    moodle_groupename = [
                        partitions_name[p[0]] + "-" + p[1]["group_name"]
                    ]
                    break

        moodle_groupenames |= set(moodle_groupename)
        etud["semestre_groupe"] = moodle_sem_name + "-" + "+".join(moodle_groupename)

    if groups_infos.nbdem > 1:
        s = "s"
    else:
        s = ""

    if format == "moodlecsv":
        # de la forme S1-[FI][FA]-groupe.csv
        if not moodle_groupenames:
            moodle_groupenames = {"tous"}
        filename = (
            moodle_sem_name
            + "-"
            + groups_infos.formsemestre["modalite"]
            + "-"
            + "+".join(sorted(moodle_groupenames))
        )
    else:
        filename = "etudiants_%s" % groups_infos.groups_filename

    prefs = sco_preferences.SemPreferences(groups_infos.formsemestre_id)
    tab = GenTable(
        rows=groups_infos.members,
        columns_ids=columns_ids,
        titles=titles,
        caption="soit %d étudiants inscrits et %d démissionaire%s."
        % (len(groups_infos.members) - groups_infos.nbdem, groups_infos.nbdem, s),
        base_url=base_url,
        filename=filename,
        pdf_link=False,  # pas d'export pdf
        html_sortable=True,
        html_class="table_leftalign table_listegroupe",
        xml_outer_tag="group_list",
        xml_row_tag="etud",
        text_fields_separator=prefs["moodle_csv_separator"],
        text_with_titles=prefs["moodle_csv_with_headerline"],
        preferences=prefs,
    )
    #
    if format == "html":
        amail_inst = [
            x["email"] for x in groups_infos.members if x["email"] and x["etat"] != "D"
        ]
        amail_perso = [
            x["emailperso"]
            for x in groups_infos.members
            if x["emailperso"] and x["etat"] != "D"
        ]

        if len(groups_infos.members):
            if groups_infos.tous_les_etuds_du_sem:
                htitle = "Les %d étudiants inscrits" % len(groups_infos.members)
            else:
                htitle = "Groupe %s (%d étudiants)" % (
                    groups_infos.groups_titles,
                    len(groups_infos.members),
                )
        else:
            htitle = "Aucun étudiant !"
        H = [
            '<div class="tab-content"><form>' '<h3 class="formsemestre"><span>',
            htitle,
            "</span>",
        ]
        if groups_infos.members:
            Of = []
            options = {
                "with_paiement": "Paiement inscription",
                "with_archives": "Fichiers archivés",
                "with_annotations": "Annotations",
                "with_codes": "Codes",
            }
            for option in options:
                if locals().get(option, False):
                    selected = "selected"
                else:
                    selected = ""
                Of.append(
                    """<option value="%s" %s>%s</option>"""
                    % (option, selected, options[option])
                )

            H.extend(
                [
                    """<span style="margin-left: 2em;"><select name="group_list_options" id="group_list_options" class="multiselect" multiple="multiple">""",
                    "\n".join(Of),
                    """</select></span>
                    <script type="text/javascript">
                    $(document).ready(function() {
                    $('#group_list_options').multiselect(
                    {
                    includeSelectAllOption: false,
                    nonSelectedText:'Options...',
                    onChange: function(element, checked){
                        change_list_options();
                    }
                    }
                    );
                    });
                    </script>
                    """,
                ]
            )
        H.append("</h3></form>")
        if groups_infos.members:
            H.extend(
                [
                    tab.html(),
                    "<ul>",
                    '<li><a class="stdlink" href="%s&format=xlsappel">Feuille d\'appel Excel</a></li>'
                    % (tab.base_url,),
                    '<li><a class="stdlink" href="%s&format=xls">Table Excel</a></li>'
                    % (tab.base_url,),
                    '<li><a class="stdlink" href="%s&format=moodlecsv">Fichier CSV pour Moodle (groupe sélectionné)</a></li>'
                    % (tab.base_url,),
                    """<li>
                    <a class="stdlink" href="export_groups_as_moodle_csv?formsemestre_id=%s">Fichier CSV pour Moodle (tous les groupes)</a>
                    <em>(voir le paramétrage pour modifier le format des fichiers Moodle exportés)</em> 
                    </li>"""
                    % groups_infos.formsemestre_id,
                ]
            )
            if amail_inst:
                H.append(
                    '<li><a class="stdlink" href="mailto:?bcc=%s">Envoyer un mail collectif au groupe de %s (via %d adresses institutionnelles)</a></li>'
                    % (
                        ",".join(amail_inst),
                        groups_infos.groups_titles,
                        len(amail_inst),
                    )
                )

            if amail_perso:
                H.append(
                    '<li><a class="stdlink" href="mailto:?bcc=%s">Envoyer un mail collectif au groupe de %s (via %d adresses personnelles)</a></li>'
                    % (
                        ",".join(amail_perso),
                        groups_infos.groups_titles,
                        len(amail_perso),
                    )
                )
            else:
                H.append("<li><em>Adresses personnelles non renseignées</em></li>")

            H.append("</ul>")

        return "".join(H) + "</div>"

    elif (
        format == "pdf"
        or format == "xml"
        or format == "json"
        or format == "xls"
        or format == "moodlecsv"
    ):
        if format == "moodlecsv":
            format = "csv"
        return tab.make_page(format=format)

    elif format == "xlsappel":
        xls = sco_excel.excel_feuille_listeappel(
            groups_infos.formsemestre,
            groups_infos.groups_titles,
            groups_infos.members,
            partitions=groups_infos.partitions,
            with_codes=with_codes,
            with_paiement=with_paiement,
            server_name=request.url_root,
        )
        filename = "liste_%s" % groups_infos.groups_filename
        return scu.send_file(xls, filename, scu.XLSX_SUFFIX, scu.XLSX_MIMETYPE)
    elif format == "allxls":
        # feuille Excel avec toutes les infos etudiants
        if not groups_infos.members:
            return ""
        keys = [
            "etudid",
            "code_nip",
            "etat",
            "civilite_str",
            "nom",
            "nom_usuel",
            "prenom",
            "inscriptionstr",
        ]
        if with_paiement:
            keys.append("paiementinscription")
        keys += [
            "email",
            "emailperso",
            "domicile",
            "villedomicile",
            "codepostaldomicile",
            "paysdomicile",
            "telephone",
            "telephonemobile",
            "fax",
            "date_naissance",
            "lieu_naissance",
            "bac",
            "specialite",
            "annee_bac",
            "nomlycee",
            "villelycee",
            "codepostallycee",
            "codelycee",
            "type_admission",
            "boursier_prec",
            "debouche",
            "parcours",
            "codeparcours",
        ]
        titles = keys[:]
        other_partitions = sco_groups.get_group_other_partitions(groups_infos.groups[0])
        keys += [p["partition_id"] for p in other_partitions]
        titles += [p["partition_name"] for p in other_partitions]
        # remplis infos lycee si on a que le code lycée
        # et ajoute infos inscription
        for m in groups_infos.members:
            etud = sco_etud.get_etud_info(m["etudid"], filled=True)[0]
            m.update(etud)
            sco_etud.etud_add_lycee_infos(etud)
            # et ajoute le parcours
            Se = sco_parcours_dut.SituationEtudParcours(
                etud, groups_infos.formsemestre_id
            )
            m["parcours"] = Se.get_parcours_descr()
            m["codeparcours"], _ = sco_report.get_codeparcoursetud(etud)

        L = [[m.get(k, "") for k in keys] for m in groups_infos.members]
        title = "etudiants_%s" % groups_infos.groups_filename
        xls = sco_excel.excel_simple_table(titles=titles, lines=L, sheet_name=title)
        filename = title
        return scu.send_file(xls, filename, scu.XLSX_SUFFIX, scu.XLSX_MIMETYPE)
    else:
        raise ValueError("unsupported format")


def tab_absences_html(groups_infos, etat=None):
    """contenu du tab "absences et feuilles diverses" """
    authuser = current_user
    H = ['<div class="tab-content">']
    if not groups_infos.members:
        return "".join(H) + "<h3>Aucun étudiant !</h3></div>"
    H.extend(
        [
            "<h3>Absences</h3>",
            '<ul class="ul_abs">',
            "<li>",
            form_choix_saisie_semaine(groups_infos),  # Ajout Le Havre
            "</li>",
            "<li>",
            form_choix_jour_saisie_hebdo(groups_infos),
            "</li>",
            """<li><a class="stdlink" href="Absences/EtatAbsencesGr?%s&debut=%s&fin=%s">État des absences du groupe</a></li>"""
            % (
                groups_infos.groups_query_args,
                groups_infos.formsemestre["date_debut"],
                groups_infos.formsemestre["date_fin"],
            ),
            "</ul>",
            "<h3>Feuilles</h3>",
            '<ul class="ul_feuilles">',
            """<li><a class="stdlink" href="%s&format=xlsappel">Feuille d'émargement %s (Excel)</a></li>"""
            % (groups_infos.base_url, groups_infos.groups_titles),
            """<li><a class="stdlink" href="trombino?%s&format=pdf">Trombinoscope en PDF</a></li>"""
            % groups_infos.groups_query_args,
            """<li><a class="stdlink" href="pdf_trombino_tours?%s&format=pdf">Trombinoscope en PDF (format "IUT de Tours", beta)</a></li>"""
            % groups_infos.groups_query_args,
            """<li><a class="stdlink" href="pdf_feuille_releve_absences?%s&format=pdf">Feuille relevé absences hebdomadaire (beta)</a></li>"""
            % groups_infos.groups_query_args,
            """<li><a class="stdlink" href="trombino?%s&format=pdflist">Liste d'appel avec photos</a></li>"""
            % groups_infos.groups_query_args,
            "</ul>",
        ]
    )

    H.append('<h3>Opérations diverses</h3><ul class="ul_misc">')
    # Lien pour verif codes INE/NIP
    # (pour tous les etudiants du semestre)
    group_id = sco_groups.get_default_group(groups_infos.formsemestre_id)
    if authuser.has_permission(Permission.ScoEtudInscrit):
        H.append(
            '<li><a class="stdlink" href="check_group_apogee?group_id=%s&etat=%s">Vérifier codes Apogée</a> (de tous les groupes)</li>'
            % (group_id, etat or "")
        )
    # Lien pour ajout fichiers étudiants
    if authuser.has_permission(Permission.ScoEtudAddAnnotations):
        H.append(
            """<li><a class="stdlink" href="etudarchive_import_files_form?group_id=%s">Télécharger des fichiers associés aux étudiants (e.g. dossiers d'admission)</a></li>"""
            % (group_id)
        )

    H.append("</ul></div>")
    return "".join(H)


def tab_photos_html(groups_infos, etat=None):
    """contenu du tab "photos" """
    from app.scodoc import sco_trombino

    if not groups_infos.members:
        return '<div class="tab-content"><h3>Aucun étudiant !</h3></div>'

    return sco_trombino.trombino_html(groups_infos)


def form_choix_jour_saisie_hebdo(groups_infos, moduleimpl_id=None):
    """Formulaire choix jour semaine pour saisie."""
    authuser = current_user
    if not authuser.has_permission(Permission.ScoAbsChange):
        return ""
    sem = groups_infos.formsemestre
    first_monday = sco_abs.ddmmyyyy(sem["date_debut"]).prev_monday()
    today_idx = datetime.date.today().weekday()

    FA = []  # formulaire avec menu saisi absences
    FA.append(
        '<form id="form_choix_jour_saisie_hebdo" action="Absences/SignaleAbsenceGrSemestre" method="get">'
    )
    FA.append('<input type="hidden" name="datefin" value="%(date_fin)s"/>' % sem)
    FA.append(groups_infos.get_form_elem())
    if moduleimpl_id:
        FA.append(
            '<input type="hidden" name="moduleimpl_id" value="%s"/>' % moduleimpl_id
        )
    FA.append('<input type="hidden" name="destination" value=""/>')

    FA.append(
        """<input type="button" onclick="$('#form_choix_jour_saisie_hebdo')[0].destination.value=get_current_url(); $('#form_choix_jour_saisie_hebdo').submit();" value="Saisir absences du "/>"""
    )
    FA.append("""<select name="datedebut">""")
    date = first_monday
    i = 0
    for jour in sco_abs.day_names():
        if i == today_idx:
            sel = "selected"
        else:
            sel = ""
        i += 1
        FA.append('<option value="%s" %s>%s</option>' % (date, sel, jour))
        date = date.next_day()
    FA.append("</select>")
    FA.append("</form>")
    return "\n".join(FA)


# Ajout Le Havre
# Formulaire saisie absences semaine
def form_choix_saisie_semaine(groups_infos):
    authuser = current_user
    if not authuser.has_permission(Permission.ScoAbsChange):
        return ""
    # construit l'URL "destination"
    # (a laquelle on revient apres saisie absences)
    query_args = parse_qs(request.query_string)
    moduleimpl_id = query_args.get("moduleimpl_id", [""])[0]
    if "head_message" in query_args:
        del query_args["head_message"]
    destination = "%s?%s" % (
        request.base_url,
        urllib.parse.urlencode(query_args, True),
    )
    destination = destination.replace(
        "%", "%%"
    )  # car ici utilisee dans un format string !

    DateJour = time.strftime("%d/%m/%Y")
    datelundi = sco_abs.ddmmyyyy(DateJour).prev_monday()
    FA = []  # formulaire avec menu saisie hebdo des absences
    FA.append('<form action="Absences/SignaleAbsenceGrHebdo" method="get">')
    FA.append('<input type="hidden" name="datelundi" value="%s"/>' % datelundi)
    FA.append('<input type="hidden" name="moduleimpl_id" value="%s"/>' % moduleimpl_id)
    FA.append('<input type="hidden" name="destination" value="%s"/>' % destination)
    FA.append(groups_infos.get_form_elem())
    FA.append('<input type="submit" class="button" value="Saisie à la semaine" />')
    FA.append("</form>")
    return "\n".join(FA)


def export_groups_as_moodle_csv(formsemestre_id=None):
    """Export all students/groups, in a CSV format suitable for Moodle
    Each (student,group) will be listed on a separate line
    jo@univ.fr,S3-A
    jo@univ.fr,S3-B1
    if jo belongs to group A in a partition, and B1 in another one.
    Caution: if groups in different partitions share the same name, there will be
    duplicates... should we prefix the group names with the partition's name ?
    """
    if not formsemestre_id:
        raise ScoValueError("missing parameter: formsemestre_id")
    _, partitions_etud_groups = sco_groups.get_formsemestre_groups(
        formsemestre_id, with_default=True
    )
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    moodle_sem_name = sem["session_id"]

    columns_ids = ("email", "semestre_groupe")
    T = []
    for partition_id in partitions_etud_groups:
        partition = sco_groups.get_partition(partition_id)
        members = partitions_etud_groups[partition_id]
        for etudid in members:
            etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
            group_name = members[etudid]["group_name"]
            elts = [moodle_sem_name]
            if partition["partition_name"]:
                elts.append(partition["partition_name"])
            if group_name:
                elts.append(group_name)
            T.append({"email": etud["email"], "semestre_groupe": "-".join(elts)})
    # Make table
    prefs = sco_preferences.SemPreferences(formsemestre_id)
    tab = GenTable(
        rows=T,
        columns_ids=("email", "semestre_groupe"),
        filename=moodle_sem_name + "-moodle",
        titles={x: x for x in columns_ids},
        text_fields_separator=prefs["moodle_csv_separator"],
        text_with_titles=prefs["moodle_csv_with_headerline"],
        preferences=prefs,
    )
    return tab.make_page(format="csv")
