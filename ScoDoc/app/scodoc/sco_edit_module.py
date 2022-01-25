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

"""Ajout/Modification/Suppression modules
(portage from DTML)
"""
import flask
from flask import url_for, g, request
from flask_login import current_user

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import ScoValueError, ScoLockedFormError, ScoGenError
from app.scodoc import html_sco_header
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_news

_MODULE_HELP = """<p class="help">
Les modules sont décrits dans le programme pédagogique. Un module est pour ce 
logiciel l'unité pédagogique élémentaire. On va lui associer une note 
à travers des <em>évaluations</em>. <br/>
Cette note (moyenne de module) sera utilisée pour calculer la moyenne
générale (et la moyenne de l'UE à laquelle appartient le module). Pour
cela, on utilisera le <em>coefficient</em> associé au module.
</p>

<p class="help">Un module possède un enseignant responsable
(typiquement celui qui dispense le cours magistral). On peut associer
au module une liste d'enseignants (typiquement les chargés de TD).
Tous ces enseignants, plus le responsable du semestre, pourront
saisir et modifier les notes de ce module.
</p> """

_moduleEditor = ndb.EditableTable(
    "notes_modules",
    "module_id",
    (
        "module_id",
        "titre",
        "code",
        "abbrev",
        "heures_cours",
        "heures_td",
        "heures_tp",
        "coefficient",
        "ue_id",
        "matiere_id",
        "formation_id",
        "semestre_id",
        "numero",
        "code_apogee",
        "module_type"
        #'ects'
    ),
    sortkey="numero, code, titre",
    output_formators={
        "heures_cours": ndb.float_null_is_zero,
        "heures_td": ndb.float_null_is_zero,
        "heures_tp": ndb.float_null_is_zero,
        "numero": ndb.int_null_is_zero,
        "coefficient": ndb.float_null_is_zero,
        "module_type": ndb.int_null_is_zero
        #'ects' : ndb.float_null_is_null
    },
)


def module_list(*args, **kw):
    "list modules"
    cnx = ndb.GetDBConnexion()
    return _moduleEditor.list(cnx, *args, **kw)


def do_module_create(args) -> int:
    "create a module"
    # create
    from app.scodoc import sco_formations

    cnx = ndb.GetDBConnexion()
    r = _moduleEditor.create(cnx, args)

    # news
    F = sco_formations.formation_list(args={"formation_id": args["formation_id"]})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=args["formation_id"],
        text="Modification de la formation %(acronyme)s" % F,
        max_frequency=3,
    )
    return r


def module_create(matiere_id=None):
    """Creation d'un module"""
    from app.scodoc import sco_formations
    from app.scodoc import sco_edit_ue

    if matiere_id is None:
        raise ScoValueError("invalid matiere !")
    M = sco_edit_matiere.matiere_list(args={"matiere_id": matiere_id})[0]
    UE = sco_edit_ue.ue_list(args={"ue_id": M["ue_id"]})[0]
    Fo = sco_formations.formation_list(args={"formation_id": UE["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(Fo["type_parcours"])
    semestres_indices = list(range(1, parcours.NB_SEM + 1))
    H = [
        html_sco_header.sco_header(page_title="Création d'un module"),
        """<h2>Création d'un module dans la matière %(titre)s""" % M,
        """ (UE %(acronyme)s)</h2>""" % UE,
        _MODULE_HELP,
    ]
    # cherche le numero adequat (pour placer le module en fin de liste)
    Mods = module_list(args={"matiere_id": matiere_id})
    if Mods:
        default_num = max([m["numero"] for m in Mods]) + 10
    else:
        default_num = 10
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "code",
                {
                    "size": 10,
                    "explanation": "code du module (doit être unique dans la formation)",
                    "allow_null": False,
                    "validator": lambda val, field, formation_id=Fo[
                        "formation_id"
                    ]: check_module_code_unicity(val, field, formation_id),
                },
            ),
            ("titre", {"size": 30, "explanation": "nom du module"}),
            ("abbrev", {"size": 20, "explanation": "nom abrégé (pour bulletins)"}),
            (
                "module_type",
                {
                    "input_type": "menu",
                    "title": "Type",
                    "explanation": "",
                    "labels": ("Standard", "Malus"),
                    "allowed_values": (str(scu.MODULE_STANDARD), str(scu.MODULE_MALUS)),
                },
            ),
            (
                "heures_cours",
                {"size": 4, "type": "float", "explanation": "nombre d'heures de cours"},
            ),
            (
                "heures_td",
                {
                    "size": 4,
                    "type": "float",
                    "explanation": "nombre d'heures de Travaux Dirigés",
                },
            ),
            (
                "heures_tp",
                {
                    "size": 4,
                    "type": "float",
                    "explanation": "nombre d'heures de Travaux Pratiques",
                },
            ),
            (
                "coefficient",
                {
                    "size": 4,
                    "type": "float",
                    "explanation": "coefficient dans la formation (PPN)",
                    "allow_null": False,
                },
            ),
            # ('ects', { 'size' : 4, 'type' : 'float', 'title' : 'ECTS', 'explanation' : 'nombre de crédits ECTS (inutilisés: les crédits sont associés aux UE)' }),
            ("formation_id", {"default": UE["formation_id"], "input_type": "hidden"}),
            ("ue_id", {"default": M["ue_id"], "input_type": "hidden"}),
            ("matiere_id", {"default": M["matiere_id"], "input_type": "hidden"}),
            (
                "semestre_id",
                {
                    "input_type": "menu",
                    "type": "int",
                    "title": parcours.SESSION_NAME.capitalize(),
                    "explanation": "%s de début du module dans la formation standard"
                    % parcours.SESSION_NAME,
                    "labels": [str(x) for x in semestres_indices],
                    "allowed_values": semestres_indices,
                },
            ),
            (
                "code_apogee",
                {
                    "title": "Code Apogée",
                    "size": 25,
                    "explanation": "(optionnel) code élément pédagogique Apogée ou liste de codes ELP séparés par des virgules",
                },
            ),
            (
                "numero",
                {
                    "size": 2,
                    "explanation": "numéro (1,2,3,4...) pour ordre d'affichage",
                    "type": "int",
                    "default": default_num,
                },
            ),
        ),
        submitlabel="Créer ce module",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    else:
        do_module_create(tf[2])
        return flask.redirect(
            url_for(
                "notes.ue_table",
                scodoc_dept=g.scodoc_dept,
                formation_id=UE["formation_id"],
            )
        )


def do_module_delete(oid):
    "delete module"
    from app.scodoc import sco_formations

    mod = module_list({"module_id": oid})[0]
    if module_is_locked(mod["module_id"]):
        raise ScoLockedFormError()

    # S'il y a des moduleimpls, on ne peut pas detruire le module !
    mods = sco_moduleimpl.moduleimpl_list(module_id=oid)
    if mods:
        err_page = f"""<h3>Destruction du module impossible car il est utilisé dans des semestres existants !</h3>
        <p class="help">Il faut d'abord supprimer le semestre. Mais il est peut être préférable de 
        laisser ce programme intact et d'en créer une nouvelle version pour la modifier.
        </p>
        <a href="{url_for('notes.ue_table', scodoc_dept=g.scodoc_dept, 
            formation_id=mod["formation_id"])}">reprendre</a>
        """
        raise ScoGenError(err_page)
    # delete
    cnx = ndb.GetDBConnexion()
    _moduleEditor.delete(cnx, oid)

    # news
    F = sco_formations.formation_list(args={"formation_id": mod["formation_id"]})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=mod["formation_id"],
        text="Modification de la formation %(acronyme)s" % F,
        max_frequency=3,
    )


def module_delete(module_id=None):
    """Delete a module"""
    if not module_id:
        raise ScoValueError("invalid module !")
    modules = module_list(args={"module_id": module_id})
    if not modules:
        raise ScoValueError("Module inexistant !")
    mod = modules[0]
    H = [
        html_sco_header.sco_header(page_title="Suppression d'un module"),
        """<h2>Suppression du module %(titre)s (%(code)s)</h2>""" % mod,
    ]

    dest_url = url_for(
        "notes.ue_table",
        scodoc_dept=g.scodoc_dept,
        formation_id=str(mod["formation_id"]),
    )
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("module_id", {"input_type": "hidden"}),),
        initvalues=mod,
        submitlabel="Confirmer la suppression",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        do_module_delete(module_id)
        return flask.redirect(dest_url)


def do_module_edit(val):
    "edit a module"
    from app.scodoc import sco_edit_formation

    # check
    mod = module_list({"module_id": val["module_id"]})[0]
    if module_is_locked(mod["module_id"]):
        # formation verrouillée: empeche de modifier certains champs:
        protected_fields = ("coefficient", "ue_id", "matiere_id", "semestre_id")
        for f in protected_fields:
            if f in val:
                del val[f]
    # edit
    cnx = ndb.GetDBConnexion()
    _moduleEditor.edit(cnx, val)
    sco_edit_formation.invalidate_sems_in_formation(mod["formation_id"])


def check_module_code_unicity(code, field, formation_id, module_id=None):
    "true si code module unique dans la formation"
    Mods = module_list(args={"code": code, "formation_id": formation_id})
    if module_id:  # edition: supprime le module en cours
        Mods = [m for m in Mods if m["module_id"] != module_id]

    return len(Mods) == 0


def module_edit(module_id=None):
    """Edit a module"""
    from app.scodoc import sco_formations
    from app.scodoc import sco_tag_module

    if not module_id:
        raise ScoValueError("invalid module !")
    Mod = module_list(args={"module_id": module_id})
    if not Mod:
        raise ScoValueError("invalid module !")
    Mod = Mod[0]
    unlocked = not module_is_locked(module_id)
    Fo = sco_formations.formation_list(args={"formation_id": Mod["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(Fo["type_parcours"])
    M = ndb.SimpleDictFetch(
        """SELECT ue.acronyme, mat.*, mat.id AS matiere_id
        FROM notes_matieres mat, notes_ue ue
        WHERE mat.ue_id = ue.id
        AND ue.formation_id = %(formation_id)s
        ORDER BY ue.numero, mat.numero
        """,
        {"formation_id": Mod["formation_id"]},
    )
    Mnames = ["%s / %s" % (x["acronyme"], x["titre"]) for x in M]
    Mids = ["%s!%s" % (x["ue_id"], x["matiere_id"]) for x in M]
    Mod["ue_matiere_id"] = "%s!%s" % (Mod["ue_id"], Mod["matiere_id"])

    semestres_indices = list(range(1, parcours.NB_SEM + 1))
    dest_url = url_for(
        "notes.ue_table",
        scodoc_dept=g.scodoc_dept,
        formation_id=str(Mod["formation_id"]),
    )
    H = [
        html_sco_header.sco_header(
            page_title="Modification du module %(titre)s" % Mod,
            cssstyles=["libjs/jQuery-tagEditor/jquery.tag-editor.css"],
            javascripts=[
                "libjs/jQuery-tagEditor/jquery.tag-editor.min.js",
                "libjs/jQuery-tagEditor/jquery.caret.min.js",
                "js/module_tag_editor.js",
            ],
        ),
        """<h2>Modification du module %(titre)s""" % Mod,
        """ (formation %(acronyme)s, version %(version)s)</h2>""" % Fo,
        _MODULE_HELP,
    ]
    if not unlocked:
        H.append(
            """<div class="ue_warning"><span>Formation verrouillée, seuls certains éléments peuvent être modifiés</span></div>"""
        )

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            (
                "code",
                {
                    "size": 10,
                    "explanation": "code du module (doit être unique dans la formation)",
                    "allow_null": False,
                    "validator": lambda val, field, formation_id=Mod[
                        "formation_id"
                    ]: check_module_code_unicity(
                        val, field, formation_id, module_id=module_id
                    ),
                },
            ),
            ("titre", {"size": 30, "explanation": "nom du module"}),
            ("abbrev", {"size": 20, "explanation": "nom abrégé (pour bulletins)"}),
            (
                "module_type",
                {
                    "input_type": "menu",
                    "title": "Type",
                    "explanation": "",
                    "labels": ("Standard", "Malus"),
                    "allowed_values": (str(scu.MODULE_STANDARD), str(scu.MODULE_MALUS)),
                    "enabled": unlocked,
                },
            ),
            (
                "heures_cours",
                {"size": 4, "type": "float", "explanation": "nombre d'heures de cours"},
            ),
            (
                "heures_td",
                {
                    "size": 4,
                    "type": "float",
                    "explanation": "nombre d'heures de Travaux Dirigés",
                },
            ),
            (
                "heures_tp",
                {
                    "size": 4,
                    "type": "float",
                    "explanation": "nombre d'heures de Travaux Pratiques",
                },
            ),
            (
                "coefficient",
                {
                    "size": 4,
                    "type": "float",
                    "explanation": "coefficient dans la formation (PPN)",
                    "allow_null": False,
                    "enabled": unlocked,
                },
            ),
            # ('ects', { 'size' : 4, 'type' : 'float', 'title' : 'ECTS', 'explanation' : 'nombre de crédits ECTS',  'enabled' : unlocked }),
            ("formation_id", {"input_type": "hidden"}),
            ("ue_id", {"input_type": "hidden"}),
            ("module_id", {"input_type": "hidden"}),
            (
                "ue_matiere_id",
                {
                    "input_type": "menu",
                    "title": "Matière",
                    "explanation": "un module appartient à une seule matière.",
                    "labels": Mnames,
                    "allowed_values": Mids,
                    "enabled": unlocked,
                },
            ),
            (
                "semestre_id",
                {
                    "input_type": "menu",
                    "type": "int",
                    "title": parcours.SESSION_NAME.capitalize(),
                    "explanation": "%s de début du module dans la formation standard"
                    % parcours.SESSION_NAME,
                    "labels": [str(x) for x in semestres_indices],
                    "allowed_values": semestres_indices,
                    "enabled": unlocked,
                },
            ),
            (
                "code_apogee",
                {
                    "title": "Code Apogée",
                    "size": 25,
                    "explanation": "(optionnel) code élément pédagogique Apogée ou liste de codes ELP séparés par des virgules",
                },
            ),
            (
                "numero",
                {
                    "size": 2,
                    "explanation": "numéro (1,2,3,4...) pour ordre d'affichage",
                    "type": "int",
                },
            ),
        ),
        html_foot_markup="""<div style="width: 90%;"><span class="sco_tag_edit"><textarea data-module_id="{}" class="module_tag_editor">{}</textarea></span></div>""".format(
            module_id, ",".join(sco_tag_module.module_tag_list(module_id))
        ),
        initvalues=Mod,
        submitlabel="Modifier ce module",
    )

    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        # l'UE peut changer
        tf[2]["ue_id"], tf[2]["matiere_id"] = tf[2]["ue_matiere_id"].split("!")
        # Check unicité code module dans la formation

        do_module_edit(tf[2])
        return flask.redirect(dest_url)


# Edition en ligne du code Apogee
def edit_module_set_code_apogee(id=None, value=None):
    "Set UE code apogee"
    module_id = id
    value = value.strip("-_ \t")
    log("edit_module_set_code_apogee: module_id=%s code_apogee=%s" % (module_id, value))

    modules = module_list(args={"module_id": module_id})
    if not modules:
        return "module invalide"  # should not occur

    do_module_edit({"module_id": module_id, "code_apogee": value})
    if not value:
        value = scu.APO_MISSING_CODE_STR
    return value


def module_table(formation_id):
    """Liste des modules de la formation
    (XXX inutile ou a revoir)
    """
    from app.scodoc import sco_formations

    if not formation_id:
        raise ScoValueError("invalid formation !")
    F = sco_formations.formation_list(args={"formation_id": formation_id})[0]
    H = [
        html_sco_header.sco_header(page_title="Liste des modules de %(titre)s" % F),
        """<h2>Listes des modules dans la formation %(titre)s (%(acronyme)s)</h2>"""
        % F,
        '<ul class="notes_module_list">',
    ]
    editable = current_user.has_permission(Permission.ScoChangeFormation)

    for Mod in module_list(args={"formation_id": formation_id}):
        H.append('<li class="notes_module_list">%s' % Mod)
        if editable:
            H.append('<a href="module_edit?module_id=%(module_id)s">modifier</a>' % Mod)
            H.append(
                '<a href="module_delete?module_id=%(module_id)s">supprimer</a>' % Mod
            )
        H.append("</li>")
    H.append("</ul>")
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def module_is_locked(module_id):
    """True if module should not be modified
    (used in a locked formsemestre)
    """
    r = ndb.SimpleDictFetch(
        """SELECT mi.id
        FROM notes_modules mod, notes_formsemestre sem, notes_moduleimpl mi
        WHERE mi.module_id = mod.id
        AND mi.formsemestre_id = sem.id
        AND mi.module_id = %(module_id)s
        AND sem.etat = false
        """,
        {"module_id": module_id},
    )
    return len(r) > 0


def module_count_moduleimpls(module_id):
    "Number of moduleimpls using this module"
    mods = sco_moduleimpl.moduleimpl_list(module_id=module_id)
    return len(mods)


def formation_add_malus_modules(formation_id, titre=None, redirect=True):
    """Création d'un module de "malus" dans chaque UE d'une formation"""
    from app.scodoc import sco_edit_ue

    ues = sco_edit_ue.ue_list(args={"formation_id": formation_id})

    for ue in ues:
        # Un seul module de malus par UE:
        nb_mod_malus = len(
            [
                mod
                for mod in module_list(args={"ue_id": ue["ue_id"]})
                if mod["module_type"] == scu.MODULE_MALUS
            ]
        )
        if nb_mod_malus == 0:
            ue_add_malus_module(ue["ue_id"], titre=titre)

    if redirect:
        return flask.redirect(
            url_for(
                "notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=formation_id
            )
        )


def ue_add_malus_module(ue_id, titre=None, code=None):
    """Add a malus module in this ue"""
    from app.scodoc import sco_edit_ue

    ue = sco_edit_ue.ue_list(args={"ue_id": ue_id})[0]

    if titre is None:
        titre = ""
    if code is None:
        code = "MALUS%d" % ue["numero"]

    # Tout module doit avoir un semestre_id (indice 1, 2, ...)
    semestre_ids = sco_edit_ue.ue_list_semestre_ids(ue)
    if semestre_ids:
        semestre_id = semestre_ids[0]
    else:
        # c'est ennuyeux: dans ce cas, on pourrait demander à indiquer explicitement
        # le semestre ? ou affecter le malus au semestre 1 ???
        raise ScoValueError(
            "Impossible d'ajouter un malus s'il n'y a pas d'autres modules"
        )

    # Matiere pour placer le module malus
    Matlist = sco_edit_matiere.matiere_list(args={"ue_id": ue_id})
    numero = max([mat["numero"] for mat in Matlist]) + 10
    matiere_id = sco_edit_matiere.do_matiere_create(
        {"ue_id": ue_id, "titre": "Malus", "numero": numero}
    )

    module_id = do_module_create(
        {
            "titre": titre,
            "code": code,
            "coefficient": 0.0,  # unused
            "ue_id": ue_id,
            "matiere_id": matiere_id,
            "formation_id": ue["formation_id"],
            "semestre_id": semestre_id,
            "module_type": scu.MODULE_MALUS,
        },
    )

    return module_id
