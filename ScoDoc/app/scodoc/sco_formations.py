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

"""Import / Export de formations
"""
from operator import itemgetter
import xml.dom.minidom

import flask
from flask import g, url_for, request
from flask_login import current_user

import app.scodoc.sco_utils as scu

import app.scodoc.notesdb as ndb
from app import log
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formsemestre
from app.scodoc import sco_news
from app.scodoc import sco_preferences
from app.scodoc import sco_tag_module
from app.scodoc import sco_xml
import sco_version
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_permissions import Permission

_formationEditor = ndb.EditableTable(
    "notes_formations",
    "formation_id",
    (
        "formation_id",
        "acronyme",
        "titre",
        "titre_officiel",
        "version",
        "formation_code",
        "type_parcours",
        "code_specialite",
    ),
    filter_dept=True,
    sortkey="acronyme",
)


def formation_list(formation_id=None, args={}):
    """List formation(s) with given id, or matching args
    (when args is given, formation_id is ignored).
    """
    if not args:
        if formation_id is None:
            args = {}
        else:
            args = {"formation_id": formation_id}
    cnx = ndb.GetDBConnexion()
    r = _formationEditor.list(cnx, args=args)
    # log('%d formations found' % len(r))
    return r


def formation_has_locked_sems(formation_id):
    "True if there is a locked formsemestre in this formation"
    sems = sco_formsemestre.do_formsemestre_list(
        args={"formation_id": formation_id, "etat": False}
    )
    return sems


def formation_export(
    formation_id,
    export_ids=False,
    export_tags=True,
    export_external_ues=False,
    format=None,
):
    """Get a formation, with UE, matieres, modules
    in desired format
    """
    F = formation_list(args={"formation_id": formation_id})[0]
    selector = {"formation_id": formation_id}
    if not export_external_ues:
        selector["is_external"] = False
    ues = sco_edit_ue.ue_list(selector)
    F["ue"] = ues
    for ue in ues:
        ue_id = ue["ue_id"]
        if not export_ids:
            del ue["ue_id"]
            del ue["formation_id"]
        if ue["ects"] is None:
            del ue["ects"]
        mats = sco_edit_matiere.matiere_list({"ue_id": ue_id})
        ue["matiere"] = mats
        for mat in mats:
            matiere_id = mat["matiere_id"]
            if not export_ids:
                del mat["matiere_id"]
                del mat["ue_id"]
            mods = sco_edit_module.module_list({"matiere_id": matiere_id})
            mat["module"] = mods
            for mod in mods:
                if export_tags:
                    # mod['tags'] = sco_tag_module.module_tag_list( module_id=mod['module_id'])
                    tags = sco_tag_module.module_tag_list(module_id=mod["module_id"])
                    if tags:
                        mod["tags"] = [{"name": x} for x in tags]
                if not export_ids:
                    del mod["ue_id"]
                    del mod["matiere_id"]
                    del mod["module_id"]
                    del mod["formation_id"]
                if mod["ects"] is None:
                    del mod["ects"]

    return scu.sendResult(
        F, name="formation", format=format, force_outer_xml_tag=False, attached=True
    )


def formation_import_xml(doc: str, import_tags=True):
    """Create a formation from XML representation
    (format dumped by formation_export( format='xml' ))
    XML may contain object (UE, modules) ids: this function returns two
    dicts mapping these ids to the created ids.

    Args:
        doc:    str, xml data
        import_tags: if false, does not import tags on modules.

    Returns:
        formation_id, modules_old2new, ues_old2new
    """
    from app.scodoc import sco_edit_formation

    # log("formation_import_xml: doc=%s" % doc)
    try:
        dom = xml.dom.minidom.parseString(doc)
    except:
        log("formation_import_xml: invalid XML data")
        raise ScoValueError("Fichier XML invalide")

    f = dom.getElementsByTagName("formation")[0]  # or dom.documentElement
    D = sco_xml.xml_to_dicts(f)
    assert D[0] == "formation"
    F = D[1]
    # F_quoted = F.copy()
    # ndb.quote_dict(F_quoted)
    F["dept_id"] = g.scodoc_dept_id
    # find new version number
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT max(version)
        FROM notes_formations
        WHERE acronyme=%(acronyme)s and titre=%(titre)s and dept_id=%(dept_id)s
        """,
        F,
    )
    res = cursor.fetchall()
    try:
        version = int(res[0][0]) + 1
    except:
        version = 1
    F["version"] = version
    # create formation
    # F_unquoted = F.copy()
    # unescape_html_dict(F_unquoted)
    formation_id = sco_edit_formation.do_formation_create(F)
    log("formation %s created" % formation_id)
    ues_old2new = {}  # xml ue_id : new ue_id
    modules_old2new = {}  # xml module_id : new module_id
    # (nb: mecanisme utilise pour cloner semestres seulement, pas pour I/O XML)
    # -- create UEs
    for ue_info in D[2]:
        assert ue_info[0] == "ue"
        ue_info[1]["formation_id"] = formation_id
        if "ue_id" in ue_info[1]:
            xml_ue_id = int(ue_info[1]["ue_id"])
            del ue_info[1]["ue_id"]
        else:
            xml_ue_id = None
        ue_id = sco_edit_ue.do_ue_create(ue_info[1])
        if xml_ue_id:
            ues_old2new[xml_ue_id] = ue_id
        # -- create matieres
        for mat_info in ue_info[2]:
            assert mat_info[0] == "matiere"
            mat_info[1]["ue_id"] = ue_id
            mat_id = sco_edit_matiere.do_matiere_create(mat_info[1])
            # -- create modules
            for mod_info in mat_info[2]:
                assert mod_info[0] == "module"
                if "module_id" in mod_info[1]:
                    xml_module_id = int(mod_info[1]["module_id"])
                    del mod_info[1]["module_id"]
                else:
                    xml_module_id = None
                mod_info[1]["formation_id"] = formation_id
                mod_info[1]["matiere_id"] = mat_id
                mod_info[1]["ue_id"] = ue_id
                mod_id = sco_edit_module.do_module_create(mod_info[1])
                if xml_module_id:
                    modules_old2new[int(xml_module_id)] = mod_id
                if import_tags:
                    if len(mod_info) > 2:
                        tag_names = [t[1]["name"] for t in mod_info[2]]
                        sco_tag_module.module_tag_set(mod_id, tag_names)

    return formation_id, modules_old2new, ues_old2new


def formation_list_table(formation_id=None, args={}):
    """List formation, grouped by titre and sorted by versions
    and listing associated semestres
    returns a table
    """
    formations = formation_list(formation_id=formation_id, args=args)
    title = "Programmes pédagogiques"
    lockicon = scu.icontag(
        "lock32_img", title="Comporte des semestres verrouillés", border="0"
    )
    suppricon = scu.icontag(
        "delete_small_img", border="0", alt="supprimer", title="Supprimer"
    )
    editicon = scu.icontag(
        "edit_img", border="0", alt="modifier", title="Modifier titres et code"
    )

    editable = current_user.has_permission(Permission.ScoChangeFormation)

    # Traduit/ajoute des champs à afficher:
    for f in formations:
        try:
            f["parcours_name"] = sco_codes_parcours.get_parcours_from_code(
                f["type_parcours"]
            ).NAME
        except:
            f["parcours_name"] = ""
        f["_titre_target"] = url_for(
            "notes.ue_table",
            scodoc_dept=g.scodoc_dept,
            formation_id=str(f["formation_id"]),
        )
        f["_titre_link_class"] = "stdlink"
        f["_titre_id"] = "titre-%s" % f["acronyme"].lower().replace(" ", "-")
        # Ajoute les semestres associés à chaque formation:
        f["sems"] = sco_formsemestre.do_formsemestre_list(
            args={"formation_id": f["formation_id"]}
        )
        f["sems_list_txt"] = ", ".join([s["session_id"] for s in f["sems"]])
        f["_sems_list_txt_html"] = ", ".join(
            [
                '<a class="discretelink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%('
                "session_id)s<a> " % s
                for s in f["sems"]
            ]
            + [
                '<a class="stdlink" id="add-semestre-%s" '
                'href="formsemestre_createwithmodules?formation_id=%s&semestre_id=1">ajouter</a> '
                % (f["acronyme"].lower().replace(" ", "-"), f["formation_id"])
            ]
        )
        if f["sems"]:
            f["date_fin_dernier_sem"] = max([s["date_fin_iso"] for s in f["sems"]])
            f["annee_dernier_sem"] = f["date_fin_dernier_sem"].split("-")[0]
        else:
            f["date_fin_dernier_sem"] = ""
            f["annee_dernier_sem"] = ""
        locked = formation_has_locked_sems(f["formation_id"])
        #
        if locked:
            but_locked = lockicon
        else:
            but_locked = '<span class="but_placeholder"></span>'
        if editable and not locked:
            but_suppr = '<a class="stdlink" href="formation_delete?formation_id=%s" id="delete-formation-%s">%s</a>' % (
                f["formation_id"],
                f["acronyme"].lower().replace(" ", "-"),
                suppricon,
            )
        else:
            but_suppr = '<span class="but_placeholder"></span>'
        if editable:
            but_edit = (
                '<a class="stdlink" href="formation_edit?formation_id=%s" id="edit-formation-%s">%s</a>'
                % (f["formation_id"], f["acronyme"].lower().replace(" ", "-"), editicon)
            )
        else:
            but_edit = '<span class="but_placeholder"></span>'
        f["buttons"] = ""
        f["_buttons_html"] = but_locked + but_suppr + but_edit
    # Tri par annee_denier_sem, type, acronyme, titre, version décroissante
    formations.sort(key=itemgetter("version"), reverse=True)
    formations.sort(key=itemgetter("titre"))
    formations.sort(key=itemgetter("acronyme"))
    formations.sort(key=itemgetter("parcours_name"))
    formations.sort(
        key=itemgetter("annee_dernier_sem"), reverse=True
    )  # plus recemments utilises en tete

    #
    columns_ids = (
        "buttons",
        "acronyme",
        "parcours_name",
        "formation_code",
        "version",
        "titre",
        "sems_list_txt",
    )
    titles = {
        "buttons": "",
        "acronyme": "Acro.",
        "parcours_name": "Type",
        "titre": "Titre",
        "version": "Version",
        "formation_code": "Code",
        "sems_list_txt": "Semestres",
    }
    return GenTable(
        columns_ids=columns_ids,
        rows=formations,
        titles=titles,
        origin="Généré par %s le " % sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption=title,
        html_caption=title,
        table_id="formation_list_table",
        html_class="formation_list_table table_leftalign",
        html_with_td_classes=True,
        html_sortable=True,
        base_url="%s?formation_id=%s" % (request.base_url, formation_id),
        page_title=title,
        pdf_title=title,
        preferences=sco_preferences.SemPreferences(),
    )


def formation_create_new_version(formation_id, redirect=True):
    "duplicate formation, with new version number"
    resp = formation_export(formation_id, export_ids=True, format="xml")
    xml_data = resp.get_data(as_text=True)
    new_id, modules_old2new, ues_old2new = formation_import_xml(xml_data)
    # news
    F = formation_list(args={"formation_id": new_id})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=new_id,
        text="Nouvelle version de la formation %(acronyme)s" % F,
    )
    if redirect:
        return flask.redirect(
            url_for(
                "notes.ue_table",
                scodoc_dept=g.scodoc_dept,
                formation_id=new_id,
                msg="Nouvelle version !",
            )
        )
    else:
        return new_id, modules_old2new, ues_old2new
