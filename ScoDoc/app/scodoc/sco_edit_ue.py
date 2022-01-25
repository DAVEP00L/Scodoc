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

"""Ajout/Modification/Suppression UE

"""
import flask
from flask import g, url_for, request
from flask_login import current_user

from app.models.formations import NotesUE
import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator, TF
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import ScoValueError, ScoLockedFormError

from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_edit_formation
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_news
from app.scodoc import sco_permissions
from app.scodoc import sco_preferences
from app.scodoc import sco_tag_module

_ueEditor = ndb.EditableTable(
    "notes_ue",
    "ue_id",
    (
        "ue_id",
        "formation_id",
        "acronyme",
        "numero",
        "titre",
        "type",
        "ue_code",
        "ects",
        "is_external",
        "code_apogee",
        "coefficient",
    ),
    sortkey="numero",
    input_formators={
        "type": ndb.int_null_is_zero,
        "is_external": ndb.bool_or_str,
    },
    output_formators={
        "numero": ndb.int_null_is_zero,
        "ects": ndb.float_null_is_null,
        "coefficient": ndb.float_null_is_zero,
    },
)


def ue_list(*args, **kw):
    "list UEs"
    cnx = ndb.GetDBConnexion()
    return _ueEditor.list(cnx, *args, **kw)


def do_ue_create(args):
    "create an ue"
    from app.scodoc import sco_formations

    cnx = ndb.GetDBConnexion()
    # check duplicates
    ues = ue_list({"formation_id": args["formation_id"], "acronyme": args["acronyme"]})
    if ues:
        raise ScoValueError('Acronyme d\'UE "%s" déjà utilisé !' % args["acronyme"])
    # create
    r = _ueEditor.create(cnx, args)

    # news
    F = sco_formations.formation_list(args={"formation_id": args["formation_id"]})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=args["formation_id"],
        text="Modification de la formation %(acronyme)s" % F,
        max_frequency=3,
    )
    return r


def do_ue_delete(ue_id, delete_validations=False, force=False):
    "delete UE and attached matieres (but not modules)"
    from app.scodoc import sco_formations
    from app.scodoc import sco_parcours_dut

    cnx = ndb.GetDBConnexion()
    log("do_ue_delete: ue_id=%s, delete_validations=%s" % (ue_id, delete_validations))
    # check
    ue = ue_list({"ue_id": ue_id})
    if not ue:
        raise ScoValueError("UE inexistante !")
    ue = ue[0]
    if ue_is_locked(ue["ue_id"]):
        raise ScoLockedFormError()
    # Il y a-t-il des etudiants ayant validé cette UE ?
    # si oui, propose de supprimer les validations
    validations = sco_parcours_dut.scolar_formsemestre_validation_list(
        cnx, args={"ue_id": ue_id}
    )
    if validations and not delete_validations and not force:
        return scu.confirm_dialog(
            "<p>%d étudiants ont validé l'UE %s (%s)</p><p>Si vous supprimez cette UE, ces validations vont être supprimées !</p>"
            % (len(validations), ue["acronyme"], ue["titre"]),
            dest_url="",
            target_variable="delete_validations",
            cancel_url=url_for(
                "notes.ue_table",
                scodoc_dept=g.scodoc_dept,
                formation_id=str(ue["formation_id"]),
            ),
            parameters={"ue_id": ue_id, "dialog_confirmed": 1},
        )
    if delete_validations:
        log("deleting all validations of UE %s" % ue_id)
        ndb.SimpleQuery(
            "DELETE FROM scolar_formsemestre_validation WHERE ue_id=%(ue_id)s",
            {"ue_id": ue_id},
        )

    # delete all matiere in this UE
    mats = sco_edit_matiere.matiere_list({"ue_id": ue_id})
    for mat in mats:
        sco_edit_matiere.do_matiere_delete(mat["matiere_id"])
    # delete uecoef and events
    ndb.SimpleQuery(
        "DELETE FROM notes_formsemestre_uecoef WHERE ue_id=%(ue_id)s",
        {"ue_id": ue_id},
    )
    ndb.SimpleQuery("DELETE FROM scolar_events WHERE ue_id=%(ue_id)s", {"ue_id": ue_id})
    cnx = ndb.GetDBConnexion()
    _ueEditor.delete(cnx, ue_id)
    # > UE delete + supr. validations associées etudiants (cas compliqué, mais rarement utilisé: acceptable de tout invalider ?):
    sco_cache.invalidate_formsemestre()
    # news
    F = sco_formations.formation_list(args={"formation_id": ue["formation_id"]})[0]
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=ue["formation_id"],
        text="Modification de la formation %(acronyme)s" % F,
        max_frequency=3,
    )
    #
    if not force:
        return flask.redirect(
            url_for(
                "notes.ue_table",
                scodoc_dept=g.scodoc_dept,
                formation_id=ue["formation_id"],
            )
        )
    else:
        return None


def ue_create(formation_id=None):
    """Creation d'une UE"""
    return ue_edit(create=True, formation_id=formation_id)


def ue_edit(ue_id=None, create=False, formation_id=None):
    """Modification ou creation d'une UE"""
    from app.scodoc import sco_formations

    create = int(create)
    if not create:
        U = ue_list(args={"ue_id": ue_id})
        if not U:
            raise ScoValueError("UE inexistante !")
        U = U[0]
        formation_id = U["formation_id"]
        title = "Modification de l'UE %(titre)s" % U
        initvalues = U
        submitlabel = "Modifier les valeurs"
    else:
        title = "Création d'une UE"
        initvalues = {}
        submitlabel = "Créer cette UE"
    Fol = sco_formations.formation_list(args={"formation_id": formation_id})
    if not Fol:
        raise ScoValueError(
            "Formation %s inexistante ! (si vous avez suivi un lien valide, merci de signaler le problème)"
            % formation_id
        )
    Fo = Fol[0]
    parcours = sco_codes_parcours.get_parcours_from_code(Fo["type_parcours"])

    H = [
        html_sco_header.sco_header(page_title=title, javascripts=["js/edit_ue.js"]),
        "<h2>" + title,
        " (formation %(acronyme)s, version %(version)s)</h2>" % Fo,
        """
<p class="help">Les UE sont des groupes de modules dans une formation donnée, utilisés pour l'évaluation (on calcule des moyennes par UE et applique des seuils ("barres")). 
</p>

<p class="help">Note: L'UE n'a pas de coefficient associé. Seuls les <em>modules</em> ont des coefficients.
</p>""",
    ]

    ue_types = parcours.ALLOWED_UE_TYPES
    ue_types.sort()
    ue_types_names = [sco_codes_parcours.UE_TYPE_NAME[k] for k in ue_types]
    ue_types = [str(x) for x in ue_types]

    fw = [
        ("ue_id", {"input_type": "hidden"}),
        ("create", {"input_type": "hidden", "default": create}),
        ("formation_id", {"input_type": "hidden", "default": formation_id}),
        ("titre", {"size": 30, "explanation": "nom de l'UE"}),
        ("acronyme", {"size": 8, "explanation": "abbréviation", "allow_null": False}),
        (
            "numero",
            {
                "size": 2,
                "explanation": "numéro (1,2,3,4) de l'UE pour l'ordre d'affichage",
                "type": "int",
            },
        ),
        (
            "type",
            {
                "explanation": "type d'UE",
                "input_type": "menu",
                "allowed_values": ue_types,
                "labels": ue_types_names,
            },
        ),
        (
            "ects",
            {
                "size": 4,
                "type": "float",
                "title": "ECTS",
                "explanation": "nombre de crédits ECTS",
            },
        ),
        (
            "coefficient",
            {
                "size": 4,
                "type": "float",
                "title": "Coefficient",
                "explanation": """les coefficients d'UE ne sont utilisés que lorsque 
                l'option <em>Utiliser les coefficients d'UE pour calculer la moyenne générale</em>
                est activée. Par défaut, le coefficient d'une UE est simplement la somme des 
                coefficients des modules dans lesquels l'étudiant a des notes.
                """,
            },
        ),
        (
            "ue_code",
            {
                "size": 12,
                "title": "Code UE",
                "explanation": "code interne (optionnel). Toutes les UE partageant le même code (et le même code de formation) sont compatibles (compensation de semestres, capitalisation d'UE). Voir liste ci-dessous.",
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
            "is_external",
            {
                "input_type": "boolcheckbox",
                "title": "UE externe",
                "explanation": "réservé pour les capitalisations d'UE effectuées à l'extérieur de l'établissement",
            },
        ),
    ]
    if parcours.UE_IS_MODULE:
        # demande le semestre pour creer le module immediatement:
        semestres_indices = list(range(1, parcours.NB_SEM + 1))
        fw.append(
            (
                "semestre_id",
                {
                    "input_type": "menu",
                    "type": "int",
                    "title": parcours.SESSION_NAME.capitalize(),
                    "explanation": "%s de début du module dans la formation"
                    % parcours.SESSION_NAME,
                    "labels": [str(x) for x in semestres_indices],
                    "allowed_values": semestres_indices,
                },
            )
        )
    if create and not parcours.UE_IS_MODULE:
        fw.append(
            (
                "create_matiere",
                {
                    "input_type": "boolcheckbox",
                    "default": False,
                    "title": "Créer matière identique",
                    "explanation": "créer immédiatement une matière dans cette UE (utile si on n'utilise pas de matières)",
                },
            )
        )
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        fw,
        initvalues=initvalues,
        submitlabel=submitlabel,
    )
    if tf[0] == 0:
        X = """<div id="ue_list_code"></div>
        """
        return "\n".join(H) + tf[1] + X + html_sco_header.sco_footer()
    else:
        if create:
            if not tf[2]["ue_code"]:
                del tf[2]["ue_code"]
            if not tf[2]["numero"]:
                if not "semestre_id" in tf[2]:
                    tf[2]["semestre_id"] = 0
                # numero regroupant par semestre ou année:
                tf[2]["numero"] = next_ue_numero(
                    formation_id, int(tf[2]["semestre_id"] or 0)
                )

            ue_id = do_ue_create(tf[2])
            if parcours.UE_IS_MODULE or tf[2]["create_matiere"]:
                matiere_id = sco_edit_matiere.do_matiere_create(
                    {"ue_id": ue_id, "titre": tf[2]["titre"], "numero": 1},
                )
            if parcours.UE_IS_MODULE:
                # dans ce mode, crée un (unique) module dans l'UE:
                _ = sco_edit_module.do_module_create(
                    {
                        "titre": tf[2]["titre"],
                        "code": tf[2]["acronyme"],
                        "coefficient": 1.0,  # tous les modules auront coef 1, et on utilisera les ECTS
                        "ue_id": ue_id,
                        "matiere_id": matiere_id,
                        "formation_id": formation_id,
                        "semestre_id": tf[2]["semestre_id"],
                    },
                )
        else:
            do_ue_edit(tf[2])
        return flask.redirect(
            url_for(
                "notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=formation_id
            )
        )


def _add_ue_semestre_id(ues):
    """ajoute semestre_id dans les ue, en regardant le premier module de chacune.
    Les UE sans modules se voient attribuer le numero UE_SEM_DEFAULT (1000000),
    qui les place à la fin de la liste.
    """
    for ue in ues:
        Modlist = sco_edit_module.module_list(args={"ue_id": ue["ue_id"]})
        if Modlist:
            ue["semestre_id"] = Modlist[0]["semestre_id"]
        else:
            ue["semestre_id"] = 1000000


def next_ue_numero(formation_id, semestre_id=None):
    """Numero d'une nouvelle UE dans cette formation.
    Si le semestre est specifie, cherche les UE ayant des modules de ce semestre
    """
    ues = ue_list(args={"formation_id": formation_id})
    if not ues:
        return 0
    if semestre_id is None:
        return ues[-1]["numero"] + 1000
    else:
        # Avec semestre: (prend le semestre du 1er module de l'UE)
        _add_ue_semestre_id(ues)
        ue_list_semestre = [ue for ue in ues if ue["semestre_id"] == semestre_id]
        if ue_list_semestre:
            return ue_list_semestre[-1]["numero"] + 10
        else:
            return ues[-1]["numero"] + 1000


def ue_delete(ue_id=None, delete_validations=False, dialog_confirmed=False):
    """Delete an UE"""
    ues = ue_list(args={"ue_id": ue_id})
    if not ues:
        raise ScoValueError("UE inexistante !")
    ue = ues[0]

    if not dialog_confirmed:
        return scu.confirm_dialog(
            "<h2>Suppression de l'UE %(titre)s (%(acronyme)s))</h2>" % ue,
            dest_url="",
            parameters={"ue_id": ue_id},
            cancel_url=url_for(
                "notes.ue_table",
                scodoc_dept=g.scodoc_dept,
                formation_id=str(ue["formation_id"]),
            ),
        )

    return do_ue_delete(ue_id, delete_validations=delete_validations)


def ue_table(formation_id=None, msg=""):  # was ue_list
    """Liste des matières et modules d'une formation, avec liens pour
    éditer (si non verrouillée).
    """
    from app.scodoc import sco_formations
    from app.scodoc import sco_formsemestre_validation

    F = sco_formations.formation_list(args={"formation_id": formation_id})
    if not F:
        raise ScoValueError("invalid formation_id")
    F = F[0]
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
    locked = sco_formations.formation_has_locked_sems(formation_id)

    ues = ue_list(args={"formation_id": formation_id, "is_external": False})
    ues_externes = ue_list(args={"formation_id": formation_id, "is_external": True})
    # tri par semestre et numero:
    _add_ue_semestre_id(ues)
    _add_ue_semestre_id(ues_externes)
    ues.sort(key=lambda u: (u["semestre_id"], u["numero"]))
    ues_externes.sort(key=lambda u: (u["semestre_id"], u["numero"]))
    has_duplicate_ue_codes = len(set([ue["ue_code"] for ue in ues])) != len(ues)

    has_perm_change = current_user.has_permission(Permission.ScoChangeFormation)
    # editable = (not locked) and has_perm_change
    # On autorise maintanant la modification des formations qui ont des semestres verrouillés,
    # sauf si cela affect les notes passées (verrouillées):
    #   - pas de modif des modules utilisés dans des semestres verrouillés
    #   - pas de changement des codes d'UE utilisés dans des semestres verrouillés
    editable = has_perm_change
    tag_editable = (
        current_user.has_permission(Permission.ScoEditFormationTags) or has_perm_change
    )
    if locked:
        lockicon = scu.icontag("lock32_img", title="verrouillé")
    else:
        lockicon = ""

    arrow_up, arrow_down, arrow_none = sco_groups.get_arrow_icons_tags()
    delete_icon = scu.icontag(
        "delete_small_img", title="Supprimer (module inutilisé)", alt="supprimer"
    )
    delete_disabled_icon = scu.icontag(
        "delete_small_dis_img", title="Suppression impossible (module utilisé)"
    )
    H = [
        html_sco_header.sco_header(
            cssstyles=["libjs/jQuery-tagEditor/jquery.tag-editor.css"],
            javascripts=[
                "libjs/jinplace-1.2.1.min.js",
                "js/ue_list.js",
                "libjs/jQuery-tagEditor/jquery.tag-editor.min.js",
                "libjs/jQuery-tagEditor/jquery.caret.min.js",
                "js/module_tag_editor.js",
            ],
            page_title="Programme %s" % F["acronyme"],
        ),
        """<h2>Formation %(titre)s (%(acronyme)s) [version %(version)s] code %(formation_code)s"""
        % F,
        lockicon,
        "</h2>",
    ]
    if locked:
        H.append(
            f"""<p class="help">Cette formation est verrouillée car
{len(locked)} semestres verrouillés s'y réferent.
Si vous souhaitez modifier cette formation (par exemple pour y ajouter un module), 
vous devez:
</p>
<ul class="help">
<li>soit créer une nouvelle version de cette formation pour pouvoir l'éditer
librement (vous pouvez passer par la fonction "Associer à une nouvelle version
du programme" (menu "Semestre") si vous avez un semestre en cours);
</li>
<li>soit déverrouiller le ou les semestres qui s'y réfèrent (attention, en
 principe ces semestres sont archivés et ne devraient pas être modifiés).
</li>
</ul>"""
        )
    if msg:
        H.append('<p class="msg">' + msg + "</p>")

    if has_duplicate_ue_codes:
        H.append(
            """<div class="ue_warning"><span>Attention: plusieurs UE de cette
            formation ont le même code. Il faut corriger cela ci-dessous,
            sinon les calculs d'ECTS seront erronés !</span></div>"""
        )

    # Description de la formation
    H.append('<div class="formation_descr">')
    H.append(
        '<div class="fd_d"><span class="fd_t">Titre:</span><span class="fd_v">%(titre)s</span></div>'
        % F
    )
    H.append(
        '<div class="fd_d"><span class="fd_t">Titre officiel:</span><span class="fd_v">%(titre_officiel)s</span></div>'
        % F
    )
    H.append(
        '<div class="fd_d"><span class="fd_t">Acronyme:</span><span class="fd_v">%(acronyme)s</span></div>'
        % F
    )
    H.append(
        '<div class="fd_d"><span class="fd_t">Code:</span><span class="fd_v">%(formation_code)s</span></div>'
        % F
    )
    H.append(
        '<div class="fd_d"><span class="fd_t">Version:</span><span class="fd_v">%(version)s</span></div>'
        % F
    )
    H.append(
        '<div class="fd_d"><span class="fd_t">Type parcours:</span><span class="fd_v">%s</span></div>'
        % parcours.__doc__
    )
    if parcours.UE_IS_MODULE:
        H.append(
            '<div class="fd_d"><span class="fd_t"> </span><span class="fd_n">(Chaque module est une UE)</span></div>'
        )

    if editable:
        H.append(
            '<div><a href="formation_edit?formation_id=%(formation_id)s" class="stdlink">modifier ces informations</a></div>'
            % F
        )

    H.append("</div>")

    # Description des UE/matières/modules
    H.append('<div class="formation_ue_list">')
    H.append('<div class="ue_list_tit">Programme pédagogique:</div>')

    H.append(
        '<form><input type="checkbox" class="sco_tag_checkbox">montrer les tags</input></form>'
    )
    H.append(
        _ue_table_ues(
            parcours,
            ues,
            editable,
            tag_editable,
            has_perm_change,
            arrow_up,
            arrow_down,
            arrow_none,
            delete_icon,
            delete_disabled_icon,
        )
    )
    if editable:
        H.append(
            '<ul><li><a class="stdlink" href="ue_create?formation_id=%s">Ajouter une UE</a></li>'
            % formation_id
        )
        H.append(
            '<li><a href="formation_add_malus_modules?formation_id=%(formation_id)s" class="stdlink">Ajouter des modules de malus dans chaque UE</a></li></ul>'
            % F
        )
    H.append("</div>")  # formation_ue_list

    if ues_externes:
        H.append('<div class="formation_ue_list formation_ue_list_externes">')
        H.append(
            '<div class="ue_list_tit">UE externes déclarées (pour information):</div>'
        )
        H.append(
            _ue_table_ues(
                parcours,
                ues_externes,
                editable,
                tag_editable,
                has_perm_change,
                arrow_up,
                arrow_down,
                arrow_none,
                delete_icon,
                delete_disabled_icon,
            )
        )
        H.append("</div>")  # formation_ue_list

    H.append("<p><ul>")
    if editable:
        H.append(
            """
<li><a class="stdlink" href="formation_create_new_version?formation_id=%(formation_id)s">Créer une nouvelle version (non verrouillée)</a></li>
"""
            % F
        )
    H.append(
        """
<li><a class="stdlink" href="formation_table_recap?formation_id=%(formation_id)s">Table récapitulative de la formation</a></li>
    
<li><a class="stdlink" href="formation_export?formation_id=%(formation_id)s&format=xml">Export XML de la formation</a> (permet de la sauvegarder pour l'échanger avec un autre site)</li>

<li><a class="stdlink" href="formation_export?formation_id=%(formation_id)s&format=json">Export JSON de la formation</a></li>

<li><a class="stdlink" href="module_list?formation_id=%(formation_id)s">Liste détaillée des modules de la formation</a> (debug) </li>
</ul>
</p>"""
        % F
    )
    if has_perm_change:
        H.append(
            """
        <h3> <a name="sems">Semestres ou sessions de cette formation</a></h3>
        <p><ul>"""
        )
        for sem in sco_formsemestre.do_formsemestre_list(
            args={"formation_id": formation_id}
        ):
            H.append(
                '<li><a class="stdlink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titremois)s</a>'
                % sem
            )
            if not sem["etat"]:
                H.append(" [verrouillé]")
            else:
                H.append(
                    ' <a class="stdlink" href="formsemestre_editwithmodules?formation_id=%(formation_id)s&formsemestre_id=%(formsemestre_id)s">Modifier</a>'
                    % sem
                )
            H.append("</li>")
        H.append("</ul>")

    if current_user.has_permission(Permission.ScoImplement):
        H.append(
            """<ul>
        <li><a class="stdlink" href="formsemestre_createwithmodules?formation_id=%(formation_id)s&semestre_id=1">Mettre en place un nouveau semestre de formation %(acronyme)s</a>
 </li>

</ul>"""
            % F
        )
    #   <li>(debug) <a class="stdlink" href="check_form_integrity?formation_id=%(formation_id)s">Vérifier cohérence</a></li>

    warn, _ = sco_formsemestre_validation.check_formation_ues(formation_id)
    H.append(warn)

    H.append(html_sco_header.sco_footer())
    return "".join(H)


def _ue_table_ues(
    parcours,
    ues,
    editable,
    tag_editable,
    has_perm_change,
    arrow_up,
    arrow_down,
    arrow_none,
    delete_icon,
    delete_disabled_icon,
):
    """Édition de programme: liste des UEs (avec leurs matières et modules)."""
    H = []
    cur_ue_semestre_id = None
    iue = 0
    for ue in ues:
        if ue["ects"]:
            ue["ects_str"] = ", %g ECTS" % ue["ects"]
        else:
            ue["ects_str"] = ""
        if editable:
            klass = "span_apo_edit"
        else:
            klass = ""
        ue["code_apogee_str"] = (
            """, Apo: <span class="%s" data-url="edit_ue_set_code_apogee" id="%s" data-placeholder="%s">"""
            % (klass, ue["ue_id"], scu.APO_MISSING_CODE_STR)
            + (ue["code_apogee"] or "")
            + "</span>"
        )

        if cur_ue_semestre_id != ue["semestre_id"]:
            cur_ue_semestre_id = ue["semestre_id"]
            if iue > 0:
                H.append("</ul>")
            if ue["semestre_id"] == sco_codes_parcours.UE_SEM_DEFAULT:
                lab = "Pas d'indication de semestre:"
            else:
                lab = "Semestre %s:" % ue["semestre_id"]
            H.append('<div class="ue_list_tit_sem">%s</div>' % lab)
            H.append('<ul class="notes_ue_list">')
        H.append('<li class="notes_ue_list">')
        if iue != 0 and editable:
            H.append(
                '<a href="ue_move?ue_id=%s&after=0" class="aud">%s</a>'
                % (ue["ue_id"], arrow_up)
            )
        else:
            H.append(arrow_none)
        if iue < len(ues) - 1 and editable:
            H.append(
                '<a href="ue_move?ue_id=%s&after=1" class="aud">%s</a>'
                % (ue["ue_id"], arrow_down)
            )
        else:
            H.append(arrow_none)
        iue += 1
        ue["acro_titre"] = str(ue["acronyme"])
        if ue["titre"] != ue["acronyme"]:
            ue["acro_titre"] += " " + str(ue["titre"])
        H.append(
            """%(acro_titre)s <span class="ue_code">(code %(ue_code)s%(ects_str)s, coef. %(coefficient)3.2f%(code_apogee_str)s)</span>
            <span class="ue_coef"></span>
            """
            % ue
        )
        if ue["type"] != sco_codes_parcours.UE_STANDARD:
            H.append(
                '<span class="ue_type">%s</span>'
                % sco_codes_parcours.UE_TYPE_NAME[ue["type"]]
            )
        if ue["is_external"]:
            # Cas spécial: si l'UE externe a plus d'un module, c'est peut être une UE
            # qui a été déclarée externe par erreur (ou suite à un bug d'import/export xml)
            # Dans ce cas, propose de changer le type (même si verrouillée)
            if len(sco_moduleimpl.moduleimpls_in_external_ue(ue["ue_id"])) > 1:
                H.append('<span class="ue_is_external">')
                if has_perm_change:
                    H.append(
                        f"""<a class="stdlink" href="{
                            url_for("notes.ue_set_internal", scodoc_dept=g.scodoc_dept, ue_id=ue["ue_id"])
                            }">transformer en UE ordinaire</a>&nbsp;"""
                    )
                H.append("</span>")
        ue_editable = editable and not ue_is_locked(ue["ue_id"])
        if ue_editable:
            H.append(
                '<a class="stdlink" href="ue_edit?ue_id=%(ue_id)s">modifier</a>' % ue
            )
        else:
            H.append('<span class="locked">[verrouillé]</span>')
        H.append(
            _ue_table_matieres(
                parcours,
                ue,
                editable,
                tag_editable,
                arrow_up,
                arrow_down,
                arrow_none,
                delete_icon,
                delete_disabled_icon,
            )
        )
    return "\n".join(H)


def _ue_table_matieres(
    parcours,
    ue,
    editable,
    tag_editable,
    arrow_up,
    arrow_down,
    arrow_none,
    delete_icon,
    delete_disabled_icon,
):
    """Édition de programme: liste des matières (et leurs modules) d'une UE."""
    H = []
    if not parcours.UE_IS_MODULE:
        H.append('<ul class="notes_matiere_list">')
    matieres = sco_edit_matiere.matiere_list(args={"ue_id": ue["ue_id"]})
    for mat in matieres:
        if not parcours.UE_IS_MODULE:
            H.append('<li class="notes_matiere_list">')
            if editable and not sco_edit_matiere.matiere_is_locked(mat["matiere_id"]):
                H.append(
                    f"""<a class="stdlink" href="{
                        url_for("notes.matiere_edit", 
                        scodoc_dept=g.scodoc_dept, matiere_id=mat["matiere_id"])
                        }">
                    """
                )
            H.append("%(titre)s" % mat)
            if editable and not sco_edit_matiere.matiere_is_locked(mat["matiere_id"]):
                H.append("</a>")

        modules = sco_edit_module.module_list(args={"matiere_id": mat["matiere_id"]})
        H.append(
            _ue_table_modules(
                parcours,
                mat,
                modules,
                editable,
                tag_editable,
                arrow_up,
                arrow_down,
                arrow_none,
                delete_icon,
                delete_disabled_icon,
            )
        )
    if not matieres:
        H.append("<li>Aucune matière dans cette UE ! ")
        if editable:
            H.append(
                """<a class="stdlink" href="ue_delete?ue_id=%(ue_id)s">supprimer l'UE</a>"""
                % ue
            )
        H.append("</li>")
    if editable and not parcours.UE_IS_MODULE:
        H.append(
            '<li><a class="stdlink" href="matiere_create?ue_id=%(ue_id)s">créer une matière</a> </li>'
            % ue
        )
    if not parcours.UE_IS_MODULE:
        H.append("</ul>")
    return "\n".join(H)


def _ue_table_modules(
    parcours,
    mat,
    modules,
    editable,
    tag_editable,
    arrow_up,
    arrow_down,
    arrow_none,
    delete_icon,
    delete_disabled_icon,
):
    """Édition de programme: liste des modules d'une matière d'une UE"""
    H = ['<ul class="notes_module_list">']
    im = 0
    for mod in modules:
        mod["nb_moduleimpls"] = sco_edit_module.module_count_moduleimpls(
            mod["module_id"]
        )
        klass = "notes_module_list"
        if mod["module_type"] == scu.MODULE_MALUS:
            klass += " module_malus"
        H.append('<li class="%s">' % klass)

        H.append('<span class="notes_module_list_buts">')
        if im != 0 and editable:
            H.append(
                '<a href="module_move?module_id=%s&after=0" class="aud">%s</a>'
                % (mod["module_id"], arrow_up)
            )
        else:
            H.append(arrow_none)
        if im < len(modules) - 1 and editable:
            H.append(
                '<a href="module_move?module_id=%s&after=1" class="aud">%s</a>'
                % (mod["module_id"], arrow_down)
            )
        else:
            H.append(arrow_none)
        im += 1
        if mod["nb_moduleimpls"] == 0 and editable:
            H.append(
                '<a class="smallbutton" href="module_delete?module_id=%s">%s</a>'
                % (mod["module_id"], delete_icon)
            )
        else:
            H.append(delete_disabled_icon)
        H.append("</span>")

        mod_editable = (
            editable  # and not sco_edit_module.module_is_locked( Mod['module_id'])
        )
        if mod_editable:
            H.append(
                '<a class="discretelink" title="Modifier le module numéro %(numero)s, utilisé par %(nb_moduleimpls)d sessions" href="module_edit?module_id=%(module_id)s">'
                % mod
            )
        H.append(
            '<span class="formation_module_tit">%s</span>'
            % scu.join_words(mod["code"], mod["titre"])
        )
        if mod_editable:
            H.append("</a>")
        heurescoef = (
            "%(heures_cours)s/%(heures_td)s/%(heures_tp)s, coef. %(coefficient)s" % mod
        )
        if mod_editable:
            klass = "span_apo_edit"
        else:
            klass = ""
        heurescoef += (
            ', Apo: <span class="%s" data-url="edit_module_set_code_apogee" id="%s" data-placeholder="%s">'
            % (klass, mod["module_id"], scu.APO_MISSING_CODE_STR)
            + (mod["code_apogee"] or "")
            + "</span>"
        )
        if tag_editable:
            tag_cls = "module_tag_editor"
        else:
            tag_cls = "module_tag_editor_ro"
        tag_mk = """<span class="sco_tag_edit"><form><textarea data-module_id="{}" class="{}">{}</textarea></form></span>"""
        tag_edit = tag_mk.format(
            mod["module_id"],
            tag_cls,
            ",".join(sco_tag_module.module_tag_list(mod["module_id"])),
        )
        H.append(
            " %s %s" % (parcours.SESSION_NAME, mod["semestre_id"])
            + " (%s)" % heurescoef
            + tag_edit
        )
        H.append("</li>")
    if not modules:
        H.append("<li>Aucun module dans cette matière ! ")
        if editable:
            H.append(
                f"""<a class="stdlink" href="{
                    url_for("notes.matiere_delete", 
                    scodoc_dept=g.scodoc_dept, matiere_id=mat["matiere_id"])}"
                >la supprimer</a>
                """
            )
        H.append("</li>")
    if editable:  # and ((not parcours.UE_IS_MODULE) or len(Modlist) == 0):
        H.append(
            f"""<li> <a class="stdlink" href="{
                    url_for("notes.module_create", 
                    scodoc_dept=g.scodoc_dept, matiere_id=mat["matiere_id"])}"
            >créer un module</a></li>
            """
        )
    H.append("</ul>")
    H.append("</li>")
    return "\n".join(H)


def ue_sharing_code(ue_code=None, ue_id=None, hide_ue_id=None):
    """HTML list of UE sharing this code
    Either ue_code or ue_id may be specified.
    hide_ue_id spécifie un id à retirer de la liste.
    """
    from app.scodoc import sco_formations

    ue_code = str(ue_code)
    if ue_id:
        ue = ue_list(args={"ue_id": ue_id})[0]
        if not ue_code:
            ue_code = ue["ue_code"]
        F = sco_formations.formation_list(args={"formation_id": ue["formation_id"]})[0]
        formation_code = F["formation_code"]
        # UE du même code, code formation et departement:
        q_ues = (
            NotesUE.query.filter_by(ue_code=ue_code)
            .join(NotesUE.formation, aliased=True)
            .filter_by(dept_id=g.scodoc_dept_id, formation_code=formation_code)
        )
    else:
        # Toutes les UE du departement avec ce code:
        q_ues = (
            NotesUE.query.filter_by(ue_code=ue_code)
            .join(NotesUE.formation, aliased=True)
            .filter_by(dept_id=g.scodoc_dept_id)
        )

    if hide_ue_id:  # enlève l'ue de depart
        q_ues = q_ues.filter(NotesUE.id != hide_ue_id)

    ues = q_ues.all()
    if not ues:
        if ue_id:
            return """<span class="ue_share">Seule UE avec code %s</span>""" % ue_code
        else:
            return """<span class="ue_share">Aucune UE avec code %s</span>""" % ue_code
    H = []
    if ue_id:
        H.append('<span class="ue_share">Autres UE avec le code %s:</span>' % ue_code)
    else:
        H.append('<span class="ue_share">UE avec le code %s:</span>' % ue_code)
    H.append("<ul>")
    for ue in ues:
        H.append(
            f"""<li>{ue.acronyme} ({ue.titre}) dans <a class="stdlink" 
            href="{url_for("notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=ue.formation.id)}"
            >{ue.formation.acronyme} ({ue.formation.titre})</a>, version {ue.formation.version}
            </li>
            """
        )
    H.append("</ul>")
    return "\n".join(H)


def do_ue_edit(args, bypass_lock=False, dont_invalidate_cache=False):
    "edit an UE"
    # check
    ue_id = args["ue_id"]
    ue = ue_list({"ue_id": ue_id})[0]
    if (not bypass_lock) and ue_is_locked(ue["ue_id"]):
        raise ScoLockedFormError()
    # check: acronyme unique dans cette formation
    if "acronyme" in args:
        new_acro = args["acronyme"]
        ues = ue_list({"formation_id": ue["formation_id"], "acronyme": new_acro})
        if ues and ues[0]["ue_id"] != ue_id:
            raise ScoValueError('Acronyme d\'UE "%s" déjà utilisé !' % args["acronyme"])

    # On ne peut pas supprimer le code UE:
    if "ue_code" in args and not args["ue_code"]:
        del args["ue_code"]

    cnx = ndb.GetDBConnexion()
    _ueEditor.edit(cnx, args)

    if not dont_invalidate_cache:
        # Invalide les semestres utilisant cette formation:
        sco_edit_formation.invalidate_sems_in_formation(ue["formation_id"])


# essai edition en ligne:
def edit_ue_set_code_apogee(id=None, value=None):
    "set UE code apogee"
    ue_id = id
    value = value.strip("-_ \t")
    log("edit_ue_set_code_apogee: ue_id=%s code_apogee=%s" % (ue_id, value))

    ues = ue_list(args={"ue_id": ue_id})
    if not ues:
        return "ue invalide"

    do_ue_edit(
        {"ue_id": ue_id, "code_apogee": value},
        bypass_lock=True,
        dont_invalidate_cache=False,
    )
    if not value:
        value = scu.APO_MISSING_CODE_STR
    return value


def ue_is_locked(ue_id):
    """True if UE should not be modified
    (contains modules used in a locked formsemestre)
    """
    r = ndb.SimpleDictFetch(
        """SELECT ue.id
        FROM notes_ue ue, notes_modules mod, notes_formsemestre sem, notes_moduleimpl mi
        WHERE ue.id = mod.ue_id
        AND mi.module_id = mod.id AND mi.formsemestre_id = sem.id
        AND ue.id = %(ue_id)s AND sem.etat = false
        """,
        {"ue_id": ue_id},
    )
    return len(r) > 0


# ---- Table recap formation
def formation_table_recap(formation_id, format="html"):
    """Table recapitulant formation."""
    from app.scodoc import sco_formations

    F = sco_formations.formation_list(args={"formation_id": formation_id})
    if not F:
        raise ScoValueError("invalid formation_id")
    F = F[0]
    T = []
    ues = ue_list(args={"formation_id": formation_id})
    for ue in ues:
        Matlist = sco_edit_matiere.matiere_list(args={"ue_id": ue["ue_id"]})
        for Mat in Matlist:
            Modlist = sco_edit_module.module_list(
                args={"matiere_id": Mat["matiere_id"]}
            )
            for Mod in Modlist:
                Mod["nb_moduleimpls"] = sco_edit_module.module_count_moduleimpls(
                    Mod["module_id"]
                )
                #
                T.append(
                    {
                        "UE_acro": ue["acronyme"],
                        "Mat_tit": Mat["titre"],
                        "Mod_tit": Mod["abbrev"] or Mod["titre"],
                        "Mod_code": Mod["code"],
                        "Mod_coef": Mod["coefficient"],
                        "Mod_sem": Mod["semestre_id"],
                        "nb_moduleimpls": Mod["nb_moduleimpls"],
                        "heures_cours": Mod["heures_cours"],
                        "heures_td": Mod["heures_td"],
                        "heures_tp": Mod["heures_tp"],
                        "ects": Mod["ects"],
                    }
                )
    columns_ids = [
        "UE_acro",
        "Mat_tit",
        "Mod_tit",
        "Mod_code",
        "Mod_coef",
        "Mod_sem",
        "nb_moduleimpls",
        "heures_cours",
        "heures_td",
        "heures_tp",
        "ects",
    ]
    titles = {
        "UE_acro": "UE",
        "Mat_tit": "Matière",
        "Mod_tit": "Module",
        "Mod_code": "Code",
        "Mod_coef": "Coef.",
        "Mod_sem": "Sem.",
        "nb_moduleimpls": "Nb utilisé",
        "heures_cours": "Cours (h)",
        "heures_td": "TD (h)",
        "heures_tp": "TP (h)",
        "ects": "ECTS",
    }

    title = (
        """Formation %(titre)s (%(acronyme)s) [version %(version)s] code %(formation_code)s"""
        % F
    )
    tab = GenTable(
        columns_ids=columns_ids,
        rows=T,
        titles=titles,
        origin="Généré par %s le " % scu.sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption=title,
        html_caption=title,
        html_class="table_leftalign",
        base_url="%s?formation_id=%s" % (request.base_url, formation_id),
        page_title=title,
        html_title="<h2>" + title + "</h2>",
        pdf_title=title,
        preferences=sco_preferences.SemPreferences(),
    )
    return tab.make_page(format=format)


def ue_list_semestre_ids(ue):
    """Liste triée des numeros de semestres des modules dans cette UE
    Il est recommandable que tous les modules d'une UE aient le même indice de semestre.
    Mais cela n'a pas toujours été le cas dans les programmes pédagogiques officiels,
    aussi ScoDoc laisse le choix.
    """
    Modlist = sco_edit_module.module_list(args={"ue_id": ue["ue_id"]})
    return sorted(list(set([mod["semestre_id"] for mod in Modlist])))
