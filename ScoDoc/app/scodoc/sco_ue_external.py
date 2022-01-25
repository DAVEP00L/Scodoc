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

"""Fonction de gestion des UE "externes" (effectuees dans un cursus exterieur)

On rapatrie (saisit) les notes (et crédits ECTS).

Cas d'usage: les étudiants d'une formation gérée par ScoDoc peuvent
suivre un certain nombre d'UE à l'extérieur. L'établissement a reconnu
au préalable une forme d'équivalence entre ces UE et celles du
programme. Les UE effectuées à l'extérieur sont par nature variable
d'un étudiant à l'autre et d'une année à l'autre, et ne peuvent pas
être introduites dans le programme pédagogique ScoDoc sans alourdir
considérablement les opérations (saisie, affichage du programme,
gestion des inscriptions).
En outre, un  suivi détaillé de ces UE n'est pas nécessaire: il suffit
de pouvoir y associer une note et une quantité de crédits ECTS.

Solution proposée (nov 2014):
 - un nouveau type d'UE qui

    -  s'affichera à part dans le programme pédagogique
    et les bulletins
    - pas présentées lors de la mise en place de semestres
    - affichage sur bulletin des étudiants qui y sont inscrit
    - création en même temps que la saisie de la note
       (chaine creation: UE/matière/module, inscription étudiant, entrée valeur note)
       avec auto-suggestion du nom pour limiter la création de doublons
    - seront aussi présentées (à part) sur la page "Voir les inscriptions aux modules"

"""
import flask
from flask import request
from flask_login import current_user

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_saisie_notes
from app.scodoc import sco_etud
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
from app.scodoc.sco_permissions import Permission
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message


def external_ue_create(
    formsemestre_id,
    titre="",
    acronyme="",
    ue_type=sco_codes_parcours.UE_STANDARD,
    ects=0.0,
):
    """Crée UE/matiere/module/evaluation puis saisie les notes"""
    log("external_ue_create( formsemestre_id=%s, titre=%s )" % (formsemestre_id, titre))
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # Contrôle d'accès:
    if not current_user.has_permission(Permission.ScoImplement):
        if not sem["resp_can_edit"] or (current_user.id not in sem["responsables"]):
            raise AccessDenied("vous n'avez pas le droit d'effectuer cette opération")
    #
    formation_id = sem["formation_id"]
    log("creating external UE in %s: %s" % (formsemestre_id, acronyme))

    numero = sco_edit_ue.next_ue_numero(formation_id, semestre_id=sem["semestre_id"])
    ue_id = sco_edit_ue.do_ue_create(
        {
            "formation_id": formation_id,
            "titre": titre,
            "acronyme": acronyme,
            "numero": numero,
            "type": ue_type,
            "ects": ects,
            "is_external": True,
        },
    )

    matiere_id = sco_edit_matiere.do_matiere_create(
        {"ue_id": ue_id, "titre": titre or acronyme, "numero": 1}
    )

    module_id = sco_edit_module.do_module_create(
        {
            "titre": "UE extérieure",
            "code": acronyme,
            "coefficient": ects,  # tous le coef. module est egal à la quantite d'ECTS
            "ue_id": ue_id,
            "matiere_id": matiere_id,
            "formation_id": formation_id,
            "semestre_id": sem["semestre_id"],
        },
    )

    moduleimpl_id = sco_moduleimpl.do_moduleimpl_create(
        {
            "module_id": module_id,
            "formsemestre_id": formsemestre_id,
            # affecte le 1er responsable du semestre comme resp. du module
            "responsable_id": sem["responsables"][0],
        },
    )

    return moduleimpl_id


def external_ue_inscrit_et_note(moduleimpl_id, formsemestre_id, notes_etuds):
    log(
        "external_ue_inscrit_et_note(moduleimpl_id=%s, notes_etuds=%s)"
        % (moduleimpl_id, notes_etuds)
    )
    # Inscription des étudiants
    sco_moduleimpl.do_moduleimpl_inscrit_etuds(
        moduleimpl_id,
        formsemestre_id,
        list(notes_etuds.keys()),
    )

    # Création d'une évaluation si il n'y en a pas déjà:
    ModEvals = sco_evaluations.do_evaluation_list(args={"moduleimpl_id": moduleimpl_id})
    if len(ModEvals):
        # met la note dans le première évaluation existante:
        evaluation_id = ModEvals[0]["evaluation_id"]
    else:
        # crée une évaluation:
        evaluation_id = sco_evaluations.do_evaluation_create(
            moduleimpl_id=moduleimpl_id,
            note_max=20.0,
            coefficient=1.0,
            publish_incomplete=True,
            evaluation_type=scu.EVALUATION_NORMALE,
            visibulletin=False,
            description="note externe",
        )
    # Saisie des notes
    _, _, _ = sco_saisie_notes._notes_add(
        current_user,
        evaluation_id,
        list(notes_etuds.items()),
        do_it=True,
    )


def get_existing_external_ue(formation_id):
    "la liste de toutes les UE externes définies dans cette formation"
    return sco_edit_ue.ue_list(args={"formation_id": formation_id, "is_external": True})


def get_external_moduleimpl_id(formsemestre_id, ue_id):
    "moduleimpl correspondant à l'UE externe indiquée de ce formsemestre"
    r = ndb.SimpleDictFetch(
        """
    SELECT mi.id AS moduleimpl_id FROM notes_moduleimpl mi, notes_modules mo
    WHERE mi.id = %(formsemestre_id)s
    AND mi.module_id = mo.id
    AND mo.ue_id = %(ue_id)s
    """,
        {"ue_id": ue_id, "formsemestre_id": formsemestre_id},
    )
    if r:
        return r[0]["moduleimpl_id"]
    else:
        raise ScoValueError("aucun module externe ne correspond")


# Web function
def external_ue_create_form(formsemestre_id, etudid):
    """Formulaire création UE externe + inscription étudiant et saisie note
    - Demande UE: peut-être existante (liste les UE externes de cette formation),
       ou sinon spécifier titre, acronyme, type, ECTS
    - Demande note à enregistrer.

    Note: pour l'édition éventuelle de ces informations, on utilisera les
    fonctions standards sur les UE/modules/notes
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # Contrôle d'accès:
    if not current_user.has_permission(Permission.ScoImplement):
        if not sem["resp_can_edit"] or (current_user.id not in sem["responsables"]):
            raise AccessDenied("vous n'avez pas le droit d'effectuer cette opération")

    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    formation_id = sem["formation_id"]
    existing_external_ue = get_existing_external_ue(formation_id)

    H = [
        html_sco_header.html_sem_header(
            "Ajout d'une UE externe pour %(nomprenom)s" % etud,
            sem,
            javascripts=["js/sco_ue_external.js"],
        ),
        """<p class="help">Cette page permet d'indiquer que l'étudiant a suivi une UE 
    dans un autre établissement et qu'elle doit être intégrée dans le semestre courant.<br/>
    La note (/20) obtenue par l'étudiant doit toujours être spécifiée.</br>
    On peut choisir une UE externe existante (dans le menu), ou bien en créer une, qui sera 
    alors ajoutée à la formation.
    </p>
    """,
    ]
    html_footer = html_sco_header.sco_footer()
    Fo = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(Fo["type_parcours"])
    ue_types = parcours.ALLOWED_UE_TYPES
    ue_types.sort()
    ue_types_names = [sco_codes_parcours.UE_TYPE_NAME[k] for k in ue_types]
    ue_types = [str(x) for x in ue_types]

    if existing_external_ue:
        default_label = "Nouvelle UE"
    else:
        default_label = "Aucune UE externe existante"

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("formsemestre_id", {"input_type": "hidden"}),
            ("etudid", {"input_type": "hidden"}),
            (
                "existing_ue",
                {
                    "input_type": "menu",
                    "title": "UE externe existante:",
                    "allowed_values": [""]
                    + [ue["ue_id"] for ue in existing_external_ue],
                    "labels": [default_label]
                    + [
                        "%s (%s)" % (ue["titre"], ue["acronyme"])
                        for ue in existing_external_ue
                    ],
                    "attributes": ['onchange="update_external_ue_form();"'],
                    "explanation": "inscrire cet étudiant dans cette UE",
                },
            ),
            (
                "sep",
                {
                    "input_type": "separator",
                    "title": "Ou bien déclarer une nouvelle UE externe:",
                    "dom_id": "tf_extue_decl",
                },
            ),
            # champs a desactiver si une UE existante est choisie
            (
                "titre",
                {"size": 30, "explanation": "nom de l'UE", "dom_id": "tf_extue_titre"},
            ),
            (
                "acronyme",
                {
                    "size": 8,
                    "explanation": "abbréviation",
                    "allow_null": True,  # attention: verifier
                    "dom_id": "tf_extue_acronyme",
                },
            ),
            (
                "type",
                {
                    "explanation": "type d'UE",
                    "input_type": "menu",
                    "allowed_values": ue_types,
                    "labels": ue_types_names,
                    "dom_id": "tf_extue_type",
                },
            ),
            (
                "ects",
                {
                    "size": 4,
                    "type": "float",
                    "title": "ECTS",
                    "explanation": "nombre de crédits ECTS",
                    "dom_id": "tf_extue_ects",
                },
            ),
            #
            (
                "note",
                {"size": 4, "explanation": "note sur 20", "dom_id": "tf_extue_note"},
            ),
        ),
        submitlabel="Enregistrer",
        cancelbutton="Annuler",
    )

    bull_url = "formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s" % (
        formsemestre_id,
        etudid,
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + html_footer
    elif tf[0] == -1:
        return flask.redirect(bull_url)
    else:
        note = tf[2]["note"].strip().upper()
        note_value, invalid = sco_saisie_notes.convert_note_from_string(note, 20.0)
        if invalid:
            return (
                "\n".join(H)
                + "\n"
                + tf_error_message("valeur note invalide")
                + tf[1]
                + html_footer
            )
        if tf[2]["existing_ue"]:
            ue_id = tf[2]["existing_ue"]
            moduleimpl_id = get_external_moduleimpl_id(formsemestre_id, ue_id)
        else:
            acronyme = tf[2]["acronyme"].strip()
            if not acronyme:
                return (
                    "\n".join(H)
                    + "\n"
                    + tf_error_message("spécifier acronyme d'UE")
                    + tf[1]
                    + html_footer
                )
            moduleimpl_id = external_ue_create(
                formsemestre_id,
                titre=tf[2]["titre"],
                acronyme=acronyme,
                ue_type=tf[2]["type"],  # type de l'UE
                ects=tf[2]["ects"],
            )

        external_ue_inscrit_et_note(
            moduleimpl_id,
            formsemestre_id,
            {etudid: note_value},
        )
        return flask.redirect(bull_url + "&head_message=Ajout%20effectué")
