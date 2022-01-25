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

"""Ajout/Modification/Supression matieres
(portage from DTML)
"""
import flask
from flask import g, url_for, request

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message
from app.scodoc.sco_exceptions import ScoValueError, ScoLockedFormError
from app.scodoc import html_sco_header

_matiereEditor = ndb.EditableTable(
    "notes_matieres",
    "matiere_id",
    ("matiere_id", "ue_id", "numero", "titre"),
    sortkey="numero",
    output_formators={"numero": ndb.int_null_is_zero},
)


def matiere_list(*args, **kw):
    "list matieres"
    cnx = ndb.GetDBConnexion()
    return _matiereEditor.list(cnx, *args, **kw)


def do_matiere_edit(*args, **kw):
    "edit a matiere"
    from app.scodoc import sco_edit_ue
    from app.scodoc import sco_edit_formation

    cnx = ndb.GetDBConnexion()
    # check
    mat = matiere_list({"matiere_id": args[0]["matiere_id"]})[0]
    if matiere_is_locked(mat["matiere_id"]):
        raise ScoLockedFormError()
    # edit
    _matiereEditor.edit(cnx, *args, **kw)
    formation_id = sco_edit_ue.ue_list({"ue_id": mat["ue_id"]})[0]["formation_id"]
    sco_edit_formation.invalidate_sems_in_formation(formation_id)


def do_matiere_create(args):
    "create a matiere"
    from app.scodoc import sco_edit_ue
    from app.scodoc import sco_formations
    from app.scodoc import sco_news

    cnx = ndb.GetDBConnexion()
    # check
    ue = sco_edit_ue.ue_list({"ue_id": args["ue_id"]})[0]
    # create matiere
    r = _matiereEditor.create(cnx, args)

    # news
    F = sco_formations.formation_list(args={"formation_id": ue["formation_id"]})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=ue["formation_id"],
        text="Modification de la formation %(acronyme)s" % F,
        max_frequency=3,
    )
    return r


def matiere_create(ue_id=None):
    """Creation d'une matiere"""
    from app.scodoc import sco_edit_ue

    UE = sco_edit_ue.ue_list(args={"ue_id": ue_id})[0]
    H = [
        html_sco_header.sco_header(page_title="Création d'une matière"),
        """<h2>Création d'une matière dans l'UE %(titre)s (%(acronyme)s)</h2>""" % UE,
        """<p class="help">Les matières sont des groupes de modules dans une UE
d'une formation donnée. Les matières servent surtout pour la
présentation (bulletins, etc) mais <em>n'ont pas de rôle dans le calcul
des notes.</em>
</p> 

<p class="help">Si votre formation n'utilise pas la notion de
"matières", créez une matière par UE, et donnez lui le même nom que l'UE
(en effet, tout module doit appartenir à une matière).
</p>

<p class="help">Comme les UE, les matières n'ont pas de coefficient
associé.
</p>""",
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("ue_id", {"input_type": "hidden", "default": ue_id}),
            ("titre", {"size": 30, "explanation": "nom de la matière."}),
            (
                "numero",
                {
                    "size": 2,
                    "explanation": "numéro (1,2,3,4...) pour affichage",
                    "type": "int",
                },
            ),
        ),
        submitlabel="Créer cette matière",
    )

    dest_url = url_for(
        "notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=UE["formation_id"]
    )

    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        # check unicity
        mats = matiere_list(args={"ue_id": ue_id, "titre": tf[2]["titre"]})
        if mats:
            return (
                "\n".join(H)
                + tf_error_message("Titre de matière déjà existant dans cette UE")
                + tf[1]
                + html_sco_header.sco_footer()
            )
        _ = do_matiere_create(tf[2])
        return flask.redirect(dest_url)


def do_matiere_delete(oid):
    "delete matiere and attached modules"
    from app.scodoc import sco_formations
    from app.scodoc import sco_edit_ue
    from app.scodoc import sco_edit_module
    from app.scodoc import sco_news

    cnx = ndb.GetDBConnexion()
    # check
    mat = matiere_list({"matiere_id": oid})[0]
    ue = sco_edit_ue.ue_list({"ue_id": mat["ue_id"]})[0]
    locked = matiere_is_locked(mat["matiere_id"])
    if locked:
        log("do_matiere_delete: mat=%s" % mat)
        log("do_matiere_delete: ue=%s" % ue)
        log("do_matiere_delete: locked sems: %s" % locked)
        raise ScoLockedFormError()
    log("do_matiere_delete: matiere_id=%s" % oid)
    # delete all modules in this matiere
    mods = sco_edit_module.module_list({"matiere_id": oid})
    for mod in mods:
        sco_edit_module.do_module_delete(mod["module_id"])
    _matiereEditor.delete(cnx, oid)

    # news
    F = sco_formations.formation_list(args={"formation_id": ue["formation_id"]})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=ue["formation_id"],
        text="Modification de la formation %(acronyme)s" % F,
        max_frequency=3,
    )


def matiere_delete(matiere_id=None):
    """Delete matière"""
    from app.scodoc import sco_edit_ue

    M = matiere_list(args={"matiere_id": matiere_id})[0]
    UE = sco_edit_ue.ue_list(args={"ue_id": M["ue_id"]})[0]
    H = [
        html_sco_header.sco_header(page_title="Suppression d'une matière"),
        "<h2>Suppression de la matière %(titre)s" % M,
        " dans l'UE (%(acronyme)s))</h2>" % UE,
    ]
    dest_url = url_for(
        "notes.ue_table",
        scodoc_dept=g.scodoc_dept,
        formation_id=str(UE["formation_id"]),
    )
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("matiere_id", {"input_type": "hidden"}),),
        initvalues=M,
        submitlabel="Confirmer la suppression",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        do_matiere_delete(matiere_id)
        return flask.redirect(dest_url)


def matiere_edit(matiere_id=None):
    """Edit matiere"""
    from app.scodoc import sco_formations
    from app.scodoc import sco_edit_ue

    F = matiere_list(args={"matiere_id": matiere_id})
    if not F:
        raise ScoValueError("Matière inexistante !")
    F = F[0]
    ues = sco_edit_ue.ue_list(args={"ue_id": F["ue_id"]})
    if not ues:
        raise ScoValueError("UE inexistante !")
    ue = ues[0]
    Fo = sco_formations.formation_list(args={"formation_id": ue["formation_id"]})[0]

    ues = sco_edit_ue.ue_list(args={"formation_id": ue["formation_id"]})
    ue_names = ["%(acronyme)s (%(titre)s)" % u for u in ues]
    ue_ids = [u["ue_id"] for u in ues]
    H = [
        html_sco_header.sco_header(page_title="Modification d'une matière"),
        """<h2>Modification de la matière %(titre)s""" % F,
        """(formation %(acronyme)s, version %(version)s)</h2>""" % Fo,
    ]
    help = """<p class="help">Les matières sont des groupes de modules dans une UE
d'une formation donnée. Les matières servent surtout pour la
présentation (bulletins, etc) mais <em>n'ont pas de rôle dans le calcul
des notes.</em>
</p> 

<p class="help">Si votre formation n'utilise pas la notion de
"matières", créez une matière par UE, et donnez lui le même nom que l'UE
(en effet, tout module doit appartenir à une matière).
</p>

<p class="help">Comme les UE, les matières n'ont pas de coefficient
associé.
</p>"""
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("matiere_id", {"input_type": "hidden"}),
            (
                "ue_id",
                {"input_type": "menu", "allowed_values": ue_ids, "labels": ue_names},
            ),
            ("titre", {"size": 30, "explanation": "nom de cette matière"}),
            (
                "numero",
                {
                    "size": 2,
                    "explanation": "numéro (1,2,3,4...) pour affichage",
                    "type": "int",
                },
            ),
        ),
        initvalues=F,
        submitlabel="Modifier les valeurs",
    )

    dest_url = url_for(
        "notes.ue_table",
        scodoc_dept=g.scodoc_dept,
        formation_id=str(ue["formation_id"]),
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + help + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        # check unicity
        mats = matiere_list(args={"ue_id": tf[2]["ue_id"], "titre": tf[2]["titre"]})
        if len(mats) > 1 or (len(mats) == 1 and mats[0]["matiere_id"] != matiere_id):
            return (
                "\n".join(H)
                + tf_error_message("Titre de matière déjà existant dans cette UE")
                + tf[1]
                + html_sco_header.sco_footer()
            )

        # changement d'UE ?
        if tf[2]["ue_id"] != F["ue_id"]:
            log("attaching mat %s to new UE %s" % (matiere_id, tf[2]["ue_id"]))
            ndb.SimpleQuery(
                "UPDATE notes_modules SET ue_id = %(ue_id)s WHERE matiere_id=%(matiere_id)s",
                {"ue_id": tf[2]["ue_id"], "matiere_id": matiere_id},
            )

        do_matiere_edit(tf[2])

        return flask.redirect(dest_url)


def matiere_is_locked(matiere_id):
    """True if matiere should not be modified
    (contains modules used in a locked formsemestre)
    """
    r = ndb.SimpleDictFetch(
        """SELECT ma.id
        FROM notes_matieres ma, notes_modules mod, notes_formsemestre sem, notes_moduleimpl mi
        WHERE ma.id = mod.matiere_id
        AND mi.module_id = mod.id
        AND mi.formsemestre_id = sem.id
        AND ma.id = %(matiere_id)s
        AND sem.etat = false
        """,
        {"matiere_id": matiere_id},
    )
    return len(r) > 0
