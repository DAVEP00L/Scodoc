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

"""Saisie et gestion des semestres extérieurs à ScoDoc dans un parcours.

On va créer/gérer des semestres de la même formation que le semestre ScoDoc 
où est inscrit l'étudiant, leur attribuer la modalité 'EXT'.
Ces semestres n'auront qu'un seul inscrit !
"""
import time

import flask
from flask import url_for, g, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message
from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_formsemestre_validation
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_etud


def formsemestre_ext_create(etudid, sem_params):
    """Crée un formsemestre exterieur et y inscrit l'étudiant.
    sem_params: dict nécessaire à la création du formsemestre
    """
    # Check args
    _formation = sco_formations.formation_list(
        args={"formation_id": sem_params["formation_id"]}
    )[0]
    if etudid:
        _etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]

    # Create formsemestre
    sem_params["modalite"] = "EXT"
    sem_params["etapes"] = None
    sem_params["responsables"] = [current_user.id]
    formsemestre_id = sco_formsemestre.do_formsemestre_create(sem_params, silent=True)
    # nota: le semestre est créé vide: pas de modules

    # Inscription au semestre
    sco_formsemestre_inscriptions.do_formsemestre_inscription_with_modules(
        formsemestre_id,
        etudid,
        method="formsemestre_ext_create",
    )
    return formsemestre_id


def formsemestre_ext_create_form(etudid, formsemestre_id):
    """Formulaire creation/inscription à un semestre extérieur"""
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    H = [
        html_sco_header.sco_header(),
        """<h2>Enregistrement d'une inscription antérieure dans un autre établissement</h2>
        <p class="help">
        Cette opération créé un semestre extérieur ("ancien") et y inscrit juste cet étudiant. 
        La décision de jury peut ensuite y être saisie. 
        </p>
        <p class="help">
        Notez que si un semestre extérieur similaire a déjà été créé pour un autre étudiant,
        il est préférable d'utiliser la fonction 
        "<a href="formsemestre_inscription_with_modules_form?etudid=%s&only_ext=1">
        inscrire à un autre semestre</a>"
        </p>
        """
        % (etudid,),
        """<h3><a href="%s" class="stdlink">Etudiant %s</a></h3>"""
        % (
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            etud["nomprenom"],
        ),
    ]
    F = html_sco_header.sco_footer()
    orig_sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # Ne propose que des semestres de semestre_id strictement inférieur au semestre courant
    # et seulement si pas inscrit au même semestre_id d'un semestre ordinaire ScoDoc.
    # Les autres situations (eg redoublements en changeant d'établissement)
    # doivent être gérées par les validations de semestres "antérieurs"
    insem = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"etudid": etudid, "etat": "I"}
    )
    semlist = [sco_formsemestre.get_formsemestre(i["formsemestre_id"]) for i in insem]
    existing_semestre_ids = set([s["semestre_id"] for s in semlist])
    min_semestre_id = 1
    max_semestre_id = orig_sem["semestre_id"]
    semestre_ids = set(range(min_semestre_id, max_semestre_id)) - existing_semestre_ids
    H.append(
        """<p>L'étudiant est déjà inscrit dans des semestres ScoDoc de rangs:
            %s
            </p>"""
        % sorted(list(existing_semestre_ids))
    )
    if not semestre_ids:
        H.append("""<p class="warning">pas de semestres extérieurs possibles</p>""")
        return "\n".join(H) + F
    # Formulaire
    semestre_ids_list = sorted(semestre_ids)
    semestre_ids_labels = [f"S{x}" for x in semestre_ids_list]
    descr = [
        ("formsemestre_id", {"input_type": "hidden"}),
        ("etudid", {"input_type": "hidden"}),
        (
            "semestre_id",
            {
                "input_type": "menu",
                "title": "Indice du semestre dans le cursus",
                "allowed_values": semestre_ids_list,
                "labels": semestre_ids_labels,
            },
        ),
        (
            "titre",
            {
                "size": 40,
                "title": "Nom de ce semestre extérieur",
                "explanation": """par exemple: établissement. N'indiquez pas les dates, ni le semestre, ni la modalité dans
                 le titre: ils seront automatiquement ajoutés""",
            },
        ),
        (
            "date_debut",
            {
                "title": "Date de début",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a (peut être approximatif)",
                "size": 9,
                "allow_null": False,
            },
        ),
        (
            "date_fin",
            {
                "title": "Date de fin",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a (peut être approximatif)",
                "size": 9,
                "allow_null": False,
            },
        ),
        (
            "elt_help_ue",
            {
                "title": """Les notes et coefficients des UE 
                capitalisées seront saisis ensuite""",
                "input_type": "separator",
            },
        ),
    ]

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        cancelbutton="Annuler",
        method="post",
        submitlabel="Créer semestre extérieur et y inscrire l'étudiant",
        cssclass="inscription",
        name="tf",
    )
    if tf[0] == 0:
        H.append(
            """<p>Ce formulaire sert à enregistrer un semestre antérieur dans la formation 
            effectué dans un autre établissement.
            </p>"""
        )
        return "\n".join(H) + "\n" + tf[1] + F
    elif tf[0] == -1:
        return flask.redirect(
            "%s/formsemestre_bulletinetud?formsemestre_id==%s&etudid=%s"
            % (scu.ScoURL(), formsemestre_id, etudid)
        )
    else:
        tf[2]["formation_id"] = orig_sem["formation_id"]
        formsemestre_ext_create(etudid, tf[2])
        return flask.redirect(
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
        )


def formsemestre_ext_edit_ue_validations(formsemestre_id, etudid):
    """Edition des validations d'UE et de semestre (jury)
    pour un semestre extérieur.
    On peut saisir pour chaque UE du programme de formation
    sa validation, son code jury, sa note, son coefficient.

    La moyenne générale du semestre est calculée et affichée,
    mais pas enregistrée.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    ues = _list_ue_with_coef_and_validations(sem, etudid)
    descr = _ue_form_description(ues, scu.get_request_args())
    if request.method == "GET":
        initvalues = {
            "note_" + str(ue["ue_id"]): ue["validation"].get("moy_ue", "") for ue in ues
        }
    else:
        initvalues = {}
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        cssclass="tf_ext_edit_ue_validations",
        submitlabel="Enregistrer ces validations",
        cancelbutton="Annuler",
        initvalues=initvalues,
    )
    if tf[0] == -1:
        return "<h4>annulation</h4>"
    else:
        H = _make_page(etud, sem, tf)
        if tf[0] == 0:  # premier affichage
            return "\n".join(H)
        else:  # soumission
            # simule erreur
            ok, message = _check_values(ues, tf[2])
            if not ok:
                H = _make_page(etud, sem, tf, message=message)
                return "\n".join(H)
            else:
                # Submit
                _record_ue_validations_and_coefs(formsemestre_id, etudid, ues, tf[2])
                return flask.redirect(
                    "formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s"
                    % (formsemestre_id, etudid)
                )


def _make_page(etud, sem, tf, message=""):
    nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
    moy_gen = nt.get_etud_moy_gen(etud["etudid"])
    H = [
        html_sco_header.sco_header(
            page_title="Validation des UE d'un semestre extérieur",
            javascripts=["js/formsemestre_ext_edit_ue_validations.js"],
        ),
        tf_error_message(message),
        """<p><b>%(nomprenom)s</b> est inscrit%(ne)s à ce semestre extérieur.</p>
        <p>Voici les UE entregistrées avec leur notes et coefficients.
        </p>
        """
        % etud,
        """<p>La moyenne de ce semestre serait: 
        <span class="ext_sem_moy"><span class="ext_sem_moy_val">%s</span> / 20</span>
        </p>
        """
        % moy_gen,
        '<div id="formsemestre_ext_edit_ue_validations">',
        tf[1],
        "</div>",
        """<div>
        <a class="stdlink" 
        href="formsemestre_bulletinetud?formsemestre_id=%s&etudid=%s">
        retour au bulletin de notes
        </a></div>
        """
        % (sem["formsemestre_id"], etud["etudid"]),
        html_sco_header.sco_footer(),
    ]
    return H


_UE_VALID_CODES = {
    None: "Non inscrit",
    "ADM": "Capitalisée (ADM)",
    # "CMP": "Acquise (car semestre validé)",
}


def _ue_form_description(ues, values):
    """Description du formulaire de saisie des UE / validations
    Pour chaque UE, on peut saisir: son code jury, sa note, son coefficient.
    """
    descr = [
        (
            "head_sep",
            {
                "input_type": "separator",
                "template": """<tr %(item_dom_attr)s><th>UE</th>
            <th>Code jury</th><th>Note/20</th><th>Coefficient UE</th></tr>
            """,
            },
        ),
        ("formsemestre_id", {"input_type": "hidden"}),
        ("etudid", {"input_type": "hidden"}),
    ]
    for ue in ues:
        # Menu pour code validation UE:
        # Ne propose que ADM, CMP et "Non inscrit"
        select_name = "valid_" + str(ue["ue_id"])
        menu_code_UE = """<select class="ueext_valid_select" name="%s">""" % (
            select_name,
        )
        cur_value = values.get("valid_" + str(ue["ue_id"]), False)
        for code in _UE_VALID_CODES:
            if cur_value is False:  # pas dans le form, cherche en base
                cur_value = ue["validation"].get("code", None)
            if str(cur_value) == str(code):
                selected = "selected"
            else:
                selected = ""
            menu_code_UE += '<option value="%s" %s>%s</option>' % (
                code,
                selected,
                _UE_VALID_CODES[code],
            )
            if cur_value is None:
                disabled = 'disabled="1"'
            else:
                disabled = ""
        menu_code_UE += "</select>"
        cur_value = values.get("coef_" + str(ue["ue_id"]), False)
        if cur_value is False:  # pas dans le form, cherche en base
            cur_value = ue["uecoef"].get("coefficient", "")
        itemtemplate = (
            """<tr><td class="tf-fieldlabel">%(label)s</td>"""
            + "<td>"
            + menu_code_UE
            + "</td>"  # code jury
            + '<td class="tf-field tf_field_note">%(elem)s</td>'  # note
            + """<td class="tf-field tf_field_coef">
            <input type="text" size="4" name="coef_%s" value="%s" %s></input></td>
            """
            % (ue["ue_id"], cur_value, disabled)
            + "</td></tr>"
        )
        descr.append(
            (
                "note_" + str(ue["ue_id"]),
                {
                    "input_type": "text",
                    "size": 4,
                    "template": itemtemplate,
                    "title": "<tt><b>%(acronyme)s</b></tt> %(titre)s" % ue,
                    "attributes": [disabled],
                },
            )
        )
    return descr


def _check_values(ue_list, values):
    """Check that form values are ok
    for each UE:
        code != None => note and coef
        note or coef => code != None
        note float in [0, 20]
        note => coef
        coef float >= 0
    """
    for ue in ue_list:
        pu = " pour UE %s" % ue["acronyme"]
        code = values.get("valid_" + str(ue["ue_id"]), False)
        if code == "None":
            code = None
        note = values.get("note_" + str(ue["ue_id"]), False)
        try:
            note = _convert_field_to_float(note)
        except ValueError:
            return False, "note invalide" + pu
        coef = values.get("coef_" + str(ue["ue_id"]), False)
        try:
            coef = _convert_field_to_float(coef)
        except ValueError:
            return False, "coefficient invalide" + pu
        if code != False:
            if code not in _UE_VALID_CODES:
                return False, "code invalide" + pu
            if code != None:
                if note is False or note == "":
                    return False, "note manquante" + pu
        if note != False and note != "":
            if code == None:
                return (
                    False,
                    "code jury incohérent (code %s, note %s)" % (code, note)
                    + pu
                    + " (supprimer note et coef)",
                )
            if note < 0 or note > 20:
                return False, "valeur note invalide" + pu
            if not isinstance(coef, float):
                return False, "coefficient manquant pour note %s" % note + pu
        if coef != False and coef != "":
            if coef < 0:
                return False, "valeur coefficient invalide" + pu
    return True, "ok"


def _convert_field_to_float(val):
    """value may be empty, False, or a float. Raise exception"""
    if val != False:
        val = val.strip()
    if val:
        val = float(val)
    return val


def _list_ue_with_coef_and_validations(sem, etudid):
    """Liste des UE de la même formation que sem,
    avec leurs coefs d'UE capitalisée (si déjà saisi)
    et leur validation pour cet étudiant.
    """
    cnx = ndb.GetDBConnexion()
    formsemestre_id = sem["formsemestre_id"]
    ues = sco_edit_ue.ue_list({"formation_id": sem["formation_id"]})
    for ue in ues:
        # add coefficient
        uecoef = sco_formsemestre.formsemestre_uecoef_list(
            cnx, args={"formsemestre_id": formsemestre_id, "ue_id": ue["ue_id"]}
        )
        if uecoef:
            ue["uecoef"] = uecoef[0]
        else:
            ue["uecoef"] = {}
        # add validation
        validation = sco_parcours_dut.scolar_formsemestre_validation_list(
            cnx,
            args={
                "formsemestre_id": formsemestre_id,
                "etudid": etudid,
                "ue_id": ue["ue_id"],
            },
        )
        if validation:
            ue["validation"] = validation[0]
        else:
            ue["validation"] = {}
    return ues


def _record_ue_validations_and_coefs(formsemestre_id, etudid, ues, values):
    for ue in ues:
        code = values.get("valid_" + str(ue["ue_id"]), False)
        if code == "None":
            code = None
        note = values.get("note_" + str(ue["ue_id"]), False)
        note = _convert_field_to_float(note)
        coef = values.get("coef_" + str(ue["ue_id"]), False)
        coef = _convert_field_to_float(coef)
        if coef == "" or coef == False:
            coef = None
        now_dmy = time.strftime("%d/%m/%Y")
        log(
            "_record_ue_validations_and_coefs: %s etudid=%s ue_id=%s moy_ue=%s ue_coef=%s"
            % (formsemestre_id, etudid, ue["ue_id"], note, repr(coef))
        )
        assert code == None or (note)  # si code validant, il faut une note
        sco_formsemestre_validation.do_formsemestre_validate_previous_ue(
            formsemestre_id,
            etudid,
            ue["ue_id"],
            note,
            now_dmy,
            code=code,
            ue_coefficient=coef,
        )
