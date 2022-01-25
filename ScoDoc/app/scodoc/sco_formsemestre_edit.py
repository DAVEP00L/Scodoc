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

"""Form choix modules / responsables et creation formsemestre
"""
import flask
from flask import url_for, g, request
from flask_login import current_user
from app.auth.models import User

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app.scodoc import sco_cache
from app.scodoc import sco_groups
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator, TF
from app.scodoc.sco_exceptions import AccessDenied, ScoValueError
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_vdi import ApoEtapeVDI
from app.scodoc import html_sco_header
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_compute_moy
from app.scodoc import sco_edit_matiere
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_etud
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups_copy
from app.scodoc import sco_modalites
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_permissions_check
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app.scodoc import sco_users


def _default_sem_title(F):
    """Default title for a semestre in formation F"""
    return F["titre"]


def formsemestre_createwithmodules():
    """Page création d'un semestre"""
    H = [
        html_sco_header.sco_header(
            page_title="Création d'un semestre",
            javascripts=["libjs/AutoSuggest.js"],
            cssstyles=["css/autosuggest_inquisitor.css"],
            bodyOnLoad="init_tf_form('')",
        ),
        """<h2>Mise en place d'un semestre de formation</h2>""",
    ]
    r = do_formsemestre_createwithmodules()
    if isinstance(r, str):
        H.append(r)
    else:
        return r  # response redirect
    return "\n".join(H) + html_sco_header.sco_footer()


def formsemestre_editwithmodules(formsemestre_id):
    """Page modification semestre"""
    # portage from dtml
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    H = [
        html_sco_header.html_sem_header(
            "Modification du semestre",
            sem,
            javascripts=["libjs/AutoSuggest.js"],
            cssstyles=["css/autosuggest_inquisitor.css"],
            bodyOnLoad="init_tf_form('')",
        )
    ]
    if not sem["etat"]:
        H.append(
            """<p>%s<b>Ce semestre est verrouillé.</b></p>"""
            % scu.icontag("lock_img", border="0", title="Semestre verrouillé")
        )
    else:
        r = do_formsemestre_createwithmodules(edit=1)
        if isinstance(r, str):
            H.append(r)
        else:
            return r  # response redirect
        vals = scu.get_request_args()
        if not vals.get("tf_submitted", False):
            H.append(
                """<p class="help">Seuls les modules cochés font partie de ce semestre. Pour les retirer, les décocher et appuyer sur le bouton "modifier".
</p>
<p class="help">Attention : s'il y a déjà des évaluations dans un module, il ne peut pas être supprimé !</p>
<p class="help">Les modules ont toujours un responsable. Par défaut, c'est le directeur des études.</p>"""
            )

    return "\n".join(H) + html_sco_header.sco_footer()


def can_edit_sem(formsemestre_id="", sem=None):
    """Return sem if user can edit it, False otherwise"""
    sem = sem or sco_formsemestre.get_formsemestre(formsemestre_id)
    if not current_user.has_permission(Permission.ScoImplement):  # pas chef
        if not sem["resp_can_edit"] or current_user.id not in sem["responsables"]:
            return False
    return sem


def do_formsemestre_createwithmodules(edit=False):
    "Form choix modules / responsables et creation formsemestre"
    # Fonction accessible à tous, controle acces à la main:
    vals = scu.get_request_args()
    if edit:
        formsemestre_id = int(vals["formsemestre_id"])
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not current_user.has_permission(Permission.ScoImplement):
        if not edit:
            # il faut ScoImplement pour creer un semestre
            raise AccessDenied("vous n'avez pas le droit d'effectuer cette opération")
        else:
            if not sem["resp_can_edit"] or current_user.id not in sem["responsables"]:
                raise AccessDenied(
                    "vous n'avez pas le droit d'effectuer cette opération"
                )

    # Liste des enseignants avec forme pour affichage / saisie avec suggestion
    # attention: il faut prendre ici tous les utilisateurs, même inactifs, car
    # les responsables de modules d'anciens semestres peuvent ne plus être actifs.
    # Mais la suggestion utilise get_user_list_xml() qui ne suggérera que les actifs.
    user_list = sco_users.get_user_list(with_inactives=True)
    uid2display = {}  # user_name : forme pour affichage = "NOM Prenom (login)"
    for u in user_list:
        uid2display[u.id] = u.get_nomplogin()
    allowed_user_names = list(uid2display.values()) + [""]
    #
    formation_id = int(vals["formation_id"])
    F = sco_formations.formation_list(args={"formation_id": formation_id})
    if not F:
        raise ScoValueError("Formation inexistante !")
    F = F[0]
    if not edit:
        initvalues = {"titre": _default_sem_title(F)}
        semestre_id = int(vals["semestre_id"])
        sem_module_ids = set()
    else:
        # setup form init values
        initvalues = sem
        semestre_id = initvalues["semestre_id"]
        # add associated modules to tf-checked:
        ams = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
        sem_module_ids = set([x["module_id"] for x in ams])
        initvalues["tf-checked"] = ["MI" + str(x["module_id"]) for x in ams]
        for x in ams:
            initvalues["MI" + str(x["module_id"])] = uid2display.get(
                x["responsable_id"],
                f"inconnu numéro {x['responsable_id']} resp. de {x['moduleimpl_id']} !",
            )

        initvalues["responsable_id"] = uid2display.get(
            sem["responsables"][0], sem["responsables"][0]
        )
        if len(sem["responsables"]) > 1:
            initvalues["responsable_id2"] = uid2display.get(
                sem["responsables"][1], sem["responsables"][1]
            )

    # Liste des ID de semestres
    if F["type_parcours"] is not None:
        parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
        NB_SEM = parcours.NB_SEM
    else:
        NB_SEM = 10  # fallback, max 10 semestres
    semestre_id_list = [-1] + list(range(1, NB_SEM + 1))
    semestre_id_labels = []
    for sid in semestre_id_list:
        if sid == "-1":
            semestre_id_labels.append("pas de semestres")
        else:
            semestre_id_labels.append(f"S{sid}")
    # Liste des modules  dans ce semestre de cette formation
    # on pourrait faire un simple module_list( )
    # mais si on veut l'ordre du PPN (groupe par UE et matieres) il faut:
    mods = []  # liste de dicts
    uelist = sco_edit_ue.ue_list({"formation_id": formation_id})
    for ue in uelist:
        matlist = sco_edit_matiere.matiere_list({"ue_id": ue["ue_id"]})
        for mat in matlist:
            modsmat = sco_edit_module.module_list({"matiere_id": mat["matiere_id"]})
            # XXX debug checks
            for m in modsmat:
                if m["ue_id"] != ue["ue_id"]:
                    log(
                        "XXX createwithmodules: m.ue_id=%s != u.ue_id=%s !"
                        % (m["ue_id"], ue["ue_id"])
                    )
                if m["formation_id"] != formation_id:
                    log(
                        "XXX createwithmodules: formation_id=%s\n\tm=%s"
                        % (formation_id, str(m))
                    )
                if m["formation_id"] != ue["formation_id"]:
                    log(
                        "XXX createwithmodules: formation_id=%s\n\tue=%s\tm=%s"
                        % (formation_id, str(ue), str(m))
                    )
            # /debug
            mods = mods + modsmat
    # Pour regroupement des modules par semestres:
    semestre_ids = {}
    for mod in mods:
        semestre_ids[mod["semestre_id"]] = 1
    semestre_ids = list(semestre_ids.keys())
    semestre_ids.sort()

    modalites = sco_modalites.do_modalite_list()
    modalites_abbrv = [m["modalite"] for m in modalites]
    modalites_titles = [m["titre"] for m in modalites]
    #
    modform = [
        ("formsemestre_id", {"input_type": "hidden"}),
        ("formation_id", {"input_type": "hidden", "default": formation_id}),
        (
            "date_debut",
            {
                "title": "Date de début",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a",
                "size": 9,
                "allow_null": False,
            },
        ),
        (
            "date_fin",
            {
                "title": "Date de fin",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a",
                "size": 9,
                "allow_null": False,
            },
        ),
        (
            "responsable_id",
            {
                "input_type": "text_suggest",
                "size": 50,
                "title": "Directeur des études",
                "explanation": "taper le début du nom et choisir dans le menu",
                "allowed_values": allowed_user_names,
                "allow_null": False,  # il faut au moins un responsable de semestre
                "text_suggest_options": {
                    "script": url_for(
                        "users.get_user_list_xml", scodoc_dept=g.scodoc_dept
                    )
                    + "?",  # "Users/get_user_list_xml?",
                    "varname": "start",
                    "json": False,
                    "noresults": "Valeur invalide !",
                    "timeout": 60000,
                },
            },
        ),
        (
            "responsable_id2",
            {
                "input_type": "text_suggest",
                "size": 50,
                "title": "Co-directeur des études",
                "explanation": "",
                "allowed_values": allowed_user_names,
                "allow_null": True,  # optionnel
                "text_suggest_options": {
                    "script": url_for(
                        "users.get_user_list_xml", scodoc_dept=g.scodoc_dept
                    )
                    + "?",
                    "varname": "start",
                    "json": False,
                    "noresults": "Valeur invalide !",
                    "timeout": 60000,
                },
            },
        ),
        (
            "titre",
            {
                "size": 40,
                "title": "Nom de ce semestre",
                "explanation": """n'indiquez pas les dates, ni le semestre, ni la modalité dans
                le titre: ils seront automatiquement ajoutés <input type="button" 
                value="remettre titre par défaut" onClick="document.tf.titre.value='%s';"/>"""
                % _default_sem_title(F),
            },
        ),
        (
            "modalite",
            {
                "input_type": "menu",
                "title": "Modalité",
                "allowed_values": modalites_abbrv,
                "labels": modalites_titles,
            },
        ),
        (
            "semestre_id",
            {
                "input_type": "menu",
                "title": "Semestre dans la formation",
                "allowed_values": semestre_id_list,
                "labels": semestre_id_labels,
            },
        ),
    ]
    etapes = sco_portal_apogee.get_etapes_apogee_dept()
    # Propose les etapes renvoyées par le portail
    # et ajoute les étapes du semestre qui ne sont pas dans la liste (soit la liste a changé, soit l'étape a été ajoutée manuellement)
    etapes_set = {et[0] for et in etapes}
    if edit:
        for etape_vdi in sem["etapes"]:
            if etape_vdi.etape not in etapes_set:
                etapes.append((etape_vdi.etape, "inconnue"))
    modform.append(
        (
            "elt_help_apo",
            {
                "title": "Codes Apogée nécessaires pour inscrire les étudiants et exporter les notes en fin de semestre:",
                "input_type": "separator",
            },
        )
    )

    mf_manual = {
        "size": 12,
        "template": '<tr%(item_dom_attr)s><td class="tf-fieldlabel">%(label)s</td><td class="tf-field">%(elem)s',
    }
    if etapes:
        mf = {
            "input_type": "menu",
            "allowed_values": [""] + [e[0] for e in etapes],
            "labels": ["(aucune)"] + ["%s (%s)" % (e[1], e[0]) for e in etapes],
            "template": '<tr%(item_dom_attr)s><td class="tf-fieldlabel">%(label)s</td><td class="tf-field">%(elem)s',
        }
    else:
        # fallback: code etape libre
        mf = mf_manual

    for n in range(1, scu.EDIT_NB_ETAPES + 1):
        mf["title"] = "Etape Apogée (%d)" % n
        modform.append(("etape_apo" + str(n), mf.copy()))
        modform.append(
            (
                "vdi_apo" + str(n),
                {
                    "size": 7,
                    "title": "Version (VDI): ",
                    "template": '<span class="vdi_label">%(label)s</span><span class="tf-field">%(elem)s</span></td></tr>',
                },
            )
        )
    # Saisie manuelle de l'étape: (seulement si menus)
    if etapes:
        n = 0
        mf = mf_manual
        mf["title"] = "Etape Apogée (+)"
        modform.append(("etape_apo" + str(n), mf.copy()))
        modform.append(
            (
                "vdi_apo" + str(n),
                {
                    "size": 7,
                    "title": "Version (VDI): ",
                    "template": '<span class="vdi_label">%(label)s</span><span class="tf-field">%(elem)s</span></td></tr>',
                    "explanation": "saisie manuelle si votre étape n'est pas dans le menu",
                },
            )
        )

    modform.append(
        (
            "elt_sem_apo",
            {
                "size": 32,
                "title": "Element(s) Apogée:",
                "explanation": "du semestre (ex: VRTW1). Séparés par des virgules.",
                "allow_null": not sco_preferences.get_preference(
                    "always_require_apo_sem_codes"
                ),
            },
        )
    )
    modform.append(
        (
            "elt_annee_apo",
            {
                "size": 32,
                "title": "Element(s) Apogée:",
                "explanation": "de l'année (ex: VRT1A). Séparés par des virgules.",
                "allow_null": not sco_preferences.get_preference(
                    "always_require_apo_sem_codes"
                ),
            },
        )
    )
    if edit:
        formtit = (
            """
        <p><a href="formsemestre_edit_uecoefs?formsemestre_id=%s">Modifier les coefficients des UE capitalisées</a></p>
        <h3>Sélectionner les modules, leurs responsables et les étudiants à inscrire:</h3>
        """
            % formsemestre_id
        )
    else:
        formtit = """<h3>Sélectionner les modules et leurs responsables</h3><p class="help">Si vous avez des parcours (options), ne sélectionnez que les modules du tronc commun.</p>"""

    modform += [
        (
            "gestion_compensation_lst",
            {
                "input_type": "checkbox",
                "title": "Jurys",
                "allowed_values": ["X"],
                "explanation": "proposer compensations de semestres (parcours DUT)",
                "labels": [""],
            },
        ),
        (
            "gestion_semestrielle_lst",
            {
                "input_type": "checkbox",
                "title": "",
                "allowed_values": ["X"],
                "explanation": "formation semestrialisée (jurys avec semestres décalés)",
                "labels": [""],
            },
        ),
    ]
    if current_user.has_permission(Permission.ScoImplement):
        modform += [
            (
                "resp_can_edit",
                {
                    "input_type": "boolcheckbox",
                    "title": "Autorisations",
                    "explanation": "Autoriser le directeur des études à modifier ce semestre",
                },
            )
        ]
    modform += [
        (
            "resp_can_change_ens",
            {
                "input_type": "boolcheckbox",
                "title": "",
                "explanation": "Autoriser le directeur des études à modifier les enseignants",
            },
        ),
        (
            "ens_can_edit_eval",
            {
                "input_type": "boolcheckbox",
                "title": "",
                "explanation": "Autoriser tous les enseignants associés à un module à y créer des évaluations",
            },
        ),
        (
            "bul_bgcolor",
            {
                "size": 8,
                "title": "Couleur fond des bulletins",
                "explanation": "version web seulement (ex: #ffeeee)",
            },
        ),
        (
            "bul_publish_xml_lst",
            {
                "input_type": "checkbox",
                "title": "Publication",
                "allowed_values": ["X"],
                "explanation": "publier le bulletin sur le portail étudiants",
                "labels": [""],
            },
        ),
        (
            "block_moyennes",
            {
                "input_type": "boolcheckbox",
                "title": "Bloquer moyennes",
                "explanation": "empêcher le calcul des moyennes d'UE et générale.",
            },
        ),
        (
            "sep",
            {
                "input_type": "separator",
                "title": "",
                "template": "</table>%s<table>" % formtit,
            },
        ),
    ]

    nbmod = 0
    if edit:
        templ_sep = "<tr><td>%(label)s</td><td><b>Responsable</b></td><td><b>Inscrire</b></td></tr>"
    else:
        templ_sep = "<tr><td>%(label)s</td><td><b>Responsable</b></td></tr>"
    for semestre_id in semestre_ids:
        modform.append(
            (
                "sep",
                {
                    "input_type": "separator",
                    "title": "<b>Semestre %s</b>" % semestre_id,
                    "template": templ_sep,
                },
            )
        )
        for mod in mods:
            if mod["semestre_id"] == semestre_id:
                nbmod += 1
                if edit:
                    select_name = "%s!group_id" % mod["module_id"]

                    def opt_selected(gid):
                        if gid == vals.get(select_name):
                            return "selected"
                        else:
                            return ""

                    if mod["module_id"] in sem_module_ids:
                        disabled = "disabled"
                    else:
                        disabled = ""
                    fcg = '<select name="%s" %s>' % (select_name, disabled)
                    default_group_id = sco_groups.get_default_group(formsemestre_id)
                    fcg += '<option value="%s" %s>Tous</option>' % (
                        default_group_id,
                        opt_selected(default_group_id),
                    )
                    fcg += '<option value="" %s>Aucun</option>' % opt_selected("")
                    for p in sco_groups.get_partitions_list(formsemestre_id):
                        if p["partition_name"] != None:
                            for group in sco_groups.get_partition_groups(p):
                                fcg += '<option value="%s" %s>%s %s</option>' % (
                                    group["group_id"],
                                    opt_selected(group["group_id"]),
                                    p["partition_name"],
                                    group["group_name"],
                                )
                    fcg += "</select>"
                    itemtemplate = (
                        """<tr><td class="tf-fieldlabel">%(label)s</td><td class="tf-field">%(elem)s</td><td>"""
                        + fcg
                        + "</td></tr>"
                    )
                else:
                    itemtemplate = """<tr><td class="tf-fieldlabel">%(label)s</td><td class="tf-field">%(elem)s</td></tr>"""
                modform.append(
                    (
                        "MI" + str(mod["module_id"]),
                        {
                            "input_type": "text_suggest",
                            "size": 50,
                            "withcheckbox": True,
                            "title": "%s %s" % (mod["code"], mod["titre"]),
                            "allowed_values": allowed_user_names,
                            "template": itemtemplate,
                            "text_suggest_options": {
                                "script": url_for(
                                    "users.get_user_list_xml", scodoc_dept=g.scodoc_dept
                                )
                                + "?",
                                "varname": "start",
                                "json": False,
                                "noresults": "Valeur invalide !",
                                "timeout": 60000,
                            },
                        },
                    )
                )
    if nbmod == 0:
        modform.append(
            (
                "sep",
                {
                    "input_type": "separator",
                    "title": "aucun module dans cette formation !!!",
                },
            )
        )
    if edit:
        #         modform.append( ('inscrire_etudslist',
        #                          { 'input_type' : 'checkbox',
        #                            'allowed_values' : ['X'], 'labels' : [ '' ],
        #                            'title' : '' ,
        #                            'explanation' : 'inscrire tous les étudiants du semestre aux modules ajoutés'}) )
        submitlabel = "Modifier ce semestre de formation"
    else:
        submitlabel = "Créer ce semestre de formation"
    #
    # Etapes:
    if edit:
        n = 1
        for etape_vdi in sem["etapes"]:
            initvalues["etape_apo" + str(n)] = etape_vdi.etape
            initvalues["vdi_apo" + str(n)] = etape_vdi.vdi
            n += 1
    #
    initvalues["gestion_compensation"] = initvalues.get("gestion_compensation", False)
    if initvalues["gestion_compensation"]:
        initvalues["gestion_compensation_lst"] = ["X"]
    else:
        initvalues["gestion_compensation_lst"] = []
    if vals.get("tf_submitted", False) and "gestion_compensation_lst" not in vals:
        vals["gestion_compensation_lst"] = []

    initvalues["gestion_semestrielle"] = initvalues.get("gestion_semestrielle", False)
    if initvalues["gestion_semestrielle"]:
        initvalues["gestion_semestrielle_lst"] = ["X"]
    else:
        initvalues["gestion_semestrielle_lst"] = []
    if vals.get("tf_submitted", False) and "gestion_semestrielle_lst" not in vals:
        vals["gestion_semestrielle_lst"] = []

    initvalues["bul_hide_xml"] = initvalues.get("bul_hide_xml", False)
    if not initvalues["bul_hide_xml"]:
        initvalues["bul_publish_xml_lst"] = ["X"]
    else:
        initvalues["bul_publish_xml_lst"] = []
    if vals.get("tf_submitted", False) and "bul_publish_xml_lst" not in vals:
        vals["bul_publish_xml_lst"] = []

    #
    tf = TrivialFormulator(
        request.base_url,
        vals,
        modform,
        submitlabel=submitlabel,
        cancelbutton="Annuler",
        top_buttons=True,
        initvalues=initvalues,
    )
    msg = ""
    if tf[0] == 1:
        # check dates
        if ndb.DateDMYtoISO(tf[2]["date_debut"]) > ndb.DateDMYtoISO(tf[2]["date_fin"]):
            msg = '<ul class="tf-msg"><li class="tf-msg">Dates de début et fin incompatibles !</li></ul>'
        if sco_preferences.get_preference("always_require_apo_sem_codes") and not any(
            [tf[2]["etape_apo" + str(n)] for n in range(0, scu.EDIT_NB_ETAPES + 1)]
        ):
            msg = '<ul class="tf-msg"><li class="tf-msg">Code étape Apogée manquant</li></ul>'

    if tf[0] == 0 or msg:
        return (
            '<p>Formation <a class="discretelink" href="ue_table?formation_id=%(formation_id)s"><em>%(titre)s</em> (%(acronyme)s), version %(version)s, code %(formation_code)s</a></p>'
            % F
            + msg
            + str(tf[1])
        )
    elif tf[0] == -1:
        return "<h4>annulation</h4>"
    else:
        if tf[2]["gestion_compensation_lst"]:
            tf[2]["gestion_compensation"] = True
        else:
            tf[2]["gestion_compensation"] = False
        if tf[2]["gestion_semestrielle_lst"]:
            tf[2]["gestion_semestrielle"] = True
        else:
            tf[2]["gestion_semestrielle"] = False
        if tf[2]["bul_publish_xml_lst"]:
            tf[2]["bul_hide_xml"] = False
        else:
            tf[2]["bul_hide_xml"] = True
        # remap les identifiants de responsables:
        tf[2]["responsable_id"] = User.get_user_id_from_nomplogin(
            tf[2]["responsable_id"]
        )
        tf[2]["responsable_id2"] = User.get_user_id_from_nomplogin(
            tf[2]["responsable_id2"]
        )
        tf[2]["responsables"] = [tf[2]["responsable_id"]]
        if tf[2]["responsable_id2"]:
            tf[2]["responsables"].append(tf[2]["responsable_id2"])

        for module_id in tf[2]["tf-checked"]:
            mod_resp_id = User.get_user_id_from_nomplogin(tf[2][module_id])
            if mod_resp_id is None:
                # Si un module n'a pas de responsable (ou inconnu), l'affecte au 1er directeur des etudes:
                mod_resp_id = tf[2]["responsable_id"]
            tf[2][module_id] = mod_resp_id

        # etapes:
        tf[2]["etapes"] = []
        if etapes:  # menus => case supplementaire pour saisie manuelle, indicée 0
            start_i = 0
        else:
            start_i = 1
        for n in range(start_i, scu.EDIT_NB_ETAPES + 1):
            tf[2]["etapes"].append(
                ApoEtapeVDI(
                    etape=tf[2]["etape_apo" + str(n)], vdi=tf[2]["vdi_apo" + str(n)]
                )
            )
        if not edit:
            # creation du semestre
            formsemestre_id = sco_formsemestre.do_formsemestre_create(tf[2])
            # creation des modules
            for module_id in tf[2]["tf-checked"]:
                assert module_id[:2] == "MI"
                modargs = {
                    "module_id": int(module_id[2:]),
                    "formsemestre_id": formsemestre_id,
                    "responsable_id": tf[2][module_id],
                }
                _ = sco_moduleimpl.do_moduleimpl_create(modargs)
            return flask.redirect(
                "formsemestre_status?formsemestre_id=%s&head_message=Nouveau%%20semestre%%20créé"
                % formsemestre_id
            )
        else:
            # modification du semestre:
            # on doit creer les modules nouvellement selectionnés
            # modifier ceux a modifier, et DETRUIRE ceux qui ne sont plus selectionnés.
            # Note: la destruction echouera s'il y a des objets dependants
            #       (eg des evaluations définies)
            # nouveaux modules
            # (retire le "MI" du début du nom de champs)
            checkedmods = [int(x[2:]) for x in tf[2]["tf-checked"]]
            sco_formsemestre.do_formsemestre_edit(tf[2])
            ams = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
            existingmods = [x["module_id"] for x in ams]
            mods_tocreate = [x for x in checkedmods if not x in existingmods]
            # modules a existants a modifier
            mods_toedit = [x for x in checkedmods if x in existingmods]
            # modules a detruire
            mods_todelete = [x for x in existingmods if not x in checkedmods]
            #
            msg = []
            for module_id in mods_tocreate:
                modargs = {
                    "module_id": module_id,
                    "formsemestre_id": formsemestre_id,
                    "responsable_id": tf[2]["MI" + str(module_id)],
                }
                moduleimpl_id = sco_moduleimpl.do_moduleimpl_create(modargs)
                mod = sco_edit_module.module_list({"module_id": module_id})[0]
                msg += ["création de %s (%s)" % (mod["code"], mod["titre"])]
                # INSCRIPTIONS DES ETUDIANTS
                log(
                    'inscription module: %s = "%s"'
                    % ("%s!group_id" % module_id, tf[2]["%s!group_id" % module_id])
                )
                group_id = tf[2]["%s!group_id" % module_id]
                if group_id:
                    etudids = [
                        x["etudid"] for x in sco_groups.get_group_members(group_id)
                    ]
                    log(
                        "inscription module:module_id=%s,moduleimpl_id=%s: %s"
                        % (module_id, moduleimpl_id, etudids)
                    )
                    sco_moduleimpl.do_moduleimpl_inscrit_etuds(
                        moduleimpl_id,
                        formsemestre_id,
                        etudids,
                    )
                    msg += [
                        "inscription de %d étudiants au module %s"
                        % (len(etudids), mod["code"])
                    ]
                else:
                    log(
                        "inscription module:module_id=%s,moduleimpl_id=%s: aucun etudiant inscrit"
                        % (module_id, moduleimpl_id)
                    )
            #
            ok, diag = formsemestre_delete_moduleimpls(formsemestre_id, mods_todelete)
            msg += diag
            for module_id in mods_toedit:
                moduleimpl_id = sco_moduleimpl.moduleimpl_list(
                    formsemestre_id=formsemestre_id, module_id=module_id
                )[0]["moduleimpl_id"]
                modargs = {
                    "moduleimpl_id": moduleimpl_id,
                    "module_id": module_id,
                    "formsemestre_id": formsemestre_id,
                    "responsable_id": tf[2]["MI" + str(module_id)],
                }
                sco_moduleimpl.do_moduleimpl_edit(
                    modargs, formsemestre_id=formsemestre_id
                )
                mod = sco_edit_module.module_list({"module_id": module_id})[0]

            if msg:
                msg_html = (
                    '<div class="ue_warning"><span>Attention !<ul><li>'
                    + "</li><li>".join(msg)
                    + "</li></ul></span></div>"
                )
                if ok:
                    msg_html += "<p>Modification effectuée</p>"
                else:
                    msg_html += "<p>Modification effectuée (<b>mais modules cités non supprimés</b>)</p>"
                msg_html += (
                    '<a href="formsemestre_status?formsemestre_id=%s">retour au tableau de bord</a>'
                    % formsemestre_id
                )
                return msg_html
            else:
                return flask.redirect(
                    "formsemestre_status?formsemestre_id=%s&head_message=Semestre modifié"
                    % formsemestre_id
                )


def formsemestre_delete_moduleimpls(formsemestre_id, module_ids_to_del):
    """Delete moduleimpls
    module_ids_to_del: list of module_id (warning: not moduleimpl)
    Moduleimpls must have no associated evaluations.
    """
    ok = True
    msg = []
    for module_id in module_ids_to_del:
        # get id
        moduleimpl_id = sco_moduleimpl.moduleimpl_list(
            formsemestre_id=formsemestre_id, module_id=module_id
        )[0]["moduleimpl_id"]
        mod = sco_edit_module.module_list({"module_id": module_id})[0]
        # Evaluations dans ce module ?
        evals = sco_evaluations.do_evaluation_list({"moduleimpl_id": moduleimpl_id})
        if evals:
            msg += [
                '<b>impossible de supprimer %s (%s) car il y a %d évaluations définies (<a href="moduleimpl_status?moduleimpl_id=%s" class="stdlink">supprimer les d\'abord</a>)</b>'
                % (mod["code"], mod["titre"], len(evals), moduleimpl_id)
            ]
            ok = False
        else:
            msg += ["suppression de %s (%s)" % (mod["code"], mod["titre"])]
            sco_moduleimpl.do_moduleimpl_delete(
                moduleimpl_id, formsemestre_id=formsemestre_id
            )

    return ok, msg


def formsemestre_clone(formsemestre_id):
    """
    Formulaire clonage d'un semestre
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # Liste des enseignants avec forme pour affichage / saisie avec suggestion
    user_list = sco_users.get_user_list()
    uid2display = {}  # user_name : forme pour affichage = "NOM Prenom (login)"
    for u in user_list:
        uid2display[u.id] = u.get_nomplogin()
    allowed_user_names = list(uid2display.values()) + [""]

    initvalues = {
        "formsemestre_id": sem["formsemestre_id"],
        "responsable_id": uid2display.get(
            sem["responsables"][0], sem["responsables"][0]
        ),
    }

    H = [
        html_sco_header.html_sem_header(
            "Copie du semestre",
            sem,
            javascripts=["libjs/AutoSuggest.js"],
            cssstyles=["css/autosuggest_inquisitor.css"],
            bodyOnLoad="init_tf_form('')",
        ),
        """<p class="help">Cette opération duplique un semestre: on reprend les mêmes modules et responsables. Aucun étudiant n'est inscrit.</p>""",
    ]

    descr = [
        ("formsemestre_id", {"input_type": "hidden"}),
        (
            "date_debut",
            {
                "title": "Date de début",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a",
                "size": 9,
                "allow_null": False,
            },
        ),
        (
            "date_fin",
            {
                "title": "Date de fin",  # j/m/a
                "input_type": "date",
                "explanation": "j/m/a",
                "size": 9,
                "allow_null": False,
            },
        ),
        (
            "responsable_id",
            {
                "input_type": "text_suggest",
                "size": 50,
                "title": "Directeur des études",
                "explanation": "taper le début du nom et choisir dans le menu",
                "allowed_values": allowed_user_names,
                "allow_null": False,
                "text_suggest_options": {
                    "script": url_for(
                        "users.get_user_list_xml", scodoc_dept=g.scodoc_dept
                    )
                    + "?",
                    "varname": "start",
                    "json": False,
                    "noresults": "Valeur invalide !",
                    "timeout": 60000,
                },
            },
        ),
        (
            "clone_evaluations",
            {
                "title": "Copier aussi les évaluations",
                "input_type": "boolcheckbox",
                "explanation": "copie toutes les évaluations, sans les dates (ni les notes!)",
            },
        ),
        (
            "clone_partitions",
            {
                "title": "Copier aussi les partitions",
                "input_type": "boolcheckbox",
                "explanation": "copie toutes les partitions (sans les étudiants!)",
            },
        ),
    ]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        submitlabel="Dupliquer ce semestre",
        cancelbutton="Annuler",
        initvalues=initvalues,
    )
    msg = ""
    if tf[0] == 1:
        # check dates
        if ndb.DateDMYtoISO(tf[2]["date_debut"]) > ndb.DateDMYtoISO(tf[2]["date_fin"]):
            msg = '<ul class="tf-msg"><li class="tf-msg">Dates de début et fin incompatibles !</li></ul>'
    if tf[0] == 0 or msg:
        return "".join(H) + msg + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:  # cancel
        return flask.redirect(
            "formsemestre_status?formsemestre_id=%s" % formsemestre_id
        )
    else:
        new_formsemestre_id = do_formsemestre_clone(
            formsemestre_id,
            User.get_user_id_from_nomplogin(tf[2]["responsable_id"]),
            tf[2]["date_debut"],
            tf[2]["date_fin"],
            clone_evaluations=tf[2]["clone_evaluations"],
            clone_partitions=tf[2]["clone_partitions"],
        )
        return flask.redirect(
            "formsemestre_status?formsemestre_id=%s&head_message=Nouveau%%20semestre%%20créé"
            % new_formsemestre_id
        )


def do_formsemestre_clone(
    orig_formsemestre_id,
    responsable_id,  # new resp.
    date_debut,
    date_fin,  # 'dd/mm/yyyy'
    clone_evaluations=False,
    clone_partitions=False,
):
    """Clone a semestre: make copy, same modules, same options, same resps, same partitions.
    New dates, responsable_id
    """
    log("cloning %s" % orig_formsemestre_id)
    orig_sem = sco_formsemestre.get_formsemestre(orig_formsemestre_id)
    cnx = ndb.GetDBConnexion()
    # 1- create sem
    args = orig_sem.copy()
    del args["formsemestre_id"]
    args["responsables"] = [responsable_id]
    args["date_debut"] = date_debut
    args["date_fin"] = date_fin
    args["etat"] = 1  # non verrouillé
    formsemestre_id = sco_formsemestre.do_formsemestre_create(args)
    log("created formsemestre %s" % formsemestre_id)
    # 2- create moduleimpls
    mods_orig = sco_moduleimpl.moduleimpl_list(formsemestre_id=orig_formsemestre_id)
    for mod_orig in mods_orig:
        args = mod_orig.copy()
        args["formsemestre_id"] = formsemestre_id
        mid = sco_moduleimpl.do_moduleimpl_create(args)
        # copy notes_modules_enseignants
        ens = sco_moduleimpl.do_ens_list(
            args={"moduleimpl_id": mod_orig["moduleimpl_id"]}
        )
        for e in ens:
            args = e.copy()
            args["moduleimpl_id"] = mid
            sco_moduleimpl.do_ens_create(args)
        # optionally, copy evaluations
        if clone_evaluations:
            evals = sco_evaluations.do_evaluation_list(
                args={"moduleimpl_id": mod_orig["moduleimpl_id"]}
            )
            for e in evals:
                args = e.copy()
                del args["jour"]  # erase date
                args["moduleimpl_id"] = mid
                _ = sco_evaluations.do_evaluation_create(**args)

    # 3- copy uecoefs
    objs = sco_formsemestre.formsemestre_uecoef_list(
        cnx, args={"formsemestre_id": orig_formsemestre_id}
    )
    for obj in objs:
        args = obj.copy()
        args["formsemestre_id"] = formsemestre_id
        _ = sco_formsemestre.formsemestre_uecoef_create(cnx, args)

    # NB: don't copy notes_formsemestre_custommenu (usually specific)

    # 4- Copy new style preferences
    prefs = sco_preferences.SemPreferences(orig_formsemestre_id)

    if orig_formsemestre_id in prefs.base_prefs.prefs:
        for pname in prefs.base_prefs.prefs[orig_formsemestre_id]:
            if not prefs.is_global(pname):
                pvalue = prefs[pname]
                try:
                    prefs.base_prefs.set(formsemestre_id, pname, pvalue)
                except ValueError:
                    log(
                        "do_formsemestre_clone: ignoring old preference %s=%s for %s"
                        % (pname, pvalue, formsemestre_id)
                    )

    # 5- Copy formules utilisateur
    objs = sco_compute_moy.formsemestre_ue_computation_expr_list(
        cnx, args={"formsemestre_id": orig_formsemestre_id}
    )
    for obj in objs:
        args = obj.copy()
        args["formsemestre_id"] = formsemestre_id
        _ = sco_compute_moy.formsemestre_ue_computation_expr_create(cnx, args)

    # 5- Copy partitions and groups
    if clone_partitions:
        sco_groups_copy.clone_partitions_and_groups(
            orig_formsemestre_id, formsemestre_id
        )

    return formsemestre_id


# ---------------------------------------------------------------------------------------


def formsemestre_associate_new_version(
    formsemestre_id,
    other_formsemestre_ids=[],
    dialog_confirmed=False,
):
    """Formulaire changement formation d'un semestre"""
    formsemestre_id = int(formsemestre_id)
    other_formsemestre_ids = [int(x) for x in other_formsemestre_ids]
    if not dialog_confirmed:
        # dresse le liste des semestres de la meme formation et version
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
        othersems = sco_formsemestre.do_formsemestre_list(
            args={
                "formation_id": F["formation_id"],
                "version": F["version"],
                "etat": "1",
            },
        )
        of = []
        for s in othersems:
            if (
                s["formsemestre_id"] == formsemestre_id
                or s["formsemestre_id"] in other_formsemestre_ids
            ):
                checked = 'checked="checked"'
            else:
                checked = ""
            if s["formsemestre_id"] == formsemestre_id:
                disabled = 'disabled="1"'
            else:
                disabled = ""
            of.append(
                '<div><input type="checkbox" name="other_formsemestre_ids:list" value="%s" %s %s>%s</input></div>'
                % (s["formsemestre_id"], checked, disabled, s["titremois"])
            )

        return scu.confirm_dialog(
            """<h2>Associer à une nouvelle version de formation non verrouillée ?</h2>
                <p>Le programme pédagogique ("formation") va être dupliqué pour que vous puissiez le modifier sans affecter les autres semestres. Les autres paramètres (étudiants, notes...) du semestre seront inchangés.</p>
                <p>Veillez à ne pas abuser de cette possibilité, car créer trop de versions de formations va vous compliquer la gestion (à vous de garder trace des différences et à ne pas vous tromper par la suite...).
                </p>
                <div class="othersemlist"><p>Si vous voulez associer aussi d'autres semestres à la nouvelle version, cochez-les:</p>"""
            + "".join(of)
            + "</div>",
            OK="Associer ces semestres à une nouvelle version",
            dest_url="",
            cancel_url="formsemestre_status?formsemestre_id=%s" % formsemestre_id,
            parameters={"formsemestre_id": formsemestre_id},
        )
    else:
        do_formsemestres_associate_new_version(
            [formsemestre_id] + other_formsemestre_ids
        )
        return flask.redirect(
            url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
                head_message="Formation dupliquée",
            )
        )


def do_formsemestres_associate_new_version(formsemestre_ids):
    """Cree une nouvelle version de la formation du semestre, et y rattache les semestres.
    Tous les moduleimpl sont ré-associés à la nouvelle formation, ainsi que les decisions de jury
    si elles existent (codes d'UE validées).
    Les semestre doivent tous appartenir à la meme version de la formation
    """
    log("do_formsemestres_associate_new_version %s" % formsemestre_ids)
    if not formsemestre_ids:
        return
    # Check: tous de la même formation
    assert isinstance(formsemestre_ids[0], int)
    sem = sco_formsemestre.get_formsemestre(formsemestre_ids[0])
    formation_id = sem["formation_id"]
    for formsemestre_id in formsemestre_ids[1:]:
        assert isinstance(formsemestre_id, int)
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        if formation_id != sem["formation_id"]:
            raise ScoValueError("les semestres ne sont pas tous de la même formation !")

    cnx = ndb.GetDBConnexion()
    # New formation:
    (
        formation_id,
        modules_old2new,
        ues_old2new,
    ) = sco_formations.formation_create_new_version(formation_id, redirect=False)

    for formsemestre_id in formsemestre_ids:
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        sem["formation_id"] = formation_id
        sco_formsemestre.do_formsemestre_edit(sem, cnx=cnx, html_quote=False)
        _reassociate_moduleimpls(cnx, formsemestre_id, ues_old2new, modules_old2new)

    cnx.commit()


def _reassociate_moduleimpls(cnx, formsemestre_id, ues_old2new, modules_old2new):
    """Associe les moduleimpls d'un semestre existant à un autre programme
    et met à jour les décisions de jury (validations d'UE).
    """
    # re-associate moduleimpls to new modules:
    modimpls = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
    for mod in modimpls:
        mod["module_id"] = modules_old2new[mod["module_id"]]
        sco_moduleimpl.do_moduleimpl_edit(mod, formsemestre_id=formsemestre_id)
    # update decisions:
    events = sco_etud.scolar_events_list(cnx, args={"formsemestre_id": formsemestre_id})
    for e in events:
        if e["ue_id"]:
            e["ue_id"] = ues_old2new[e["ue_id"]]
        sco_etud.scolar_events_edit(cnx, e)
    validations = sco_parcours_dut.scolar_formsemestre_validation_list(
        cnx, args={"formsemestre_id": formsemestre_id}
    )
    for e in validations:
        if e["ue_id"]:
            e["ue_id"] = ues_old2new[e["ue_id"]]
        # log('e=%s' % e )
        sco_parcours_dut.scolar_formsemestre_validation_edit(cnx, e)


def formsemestre_delete(formsemestre_id):
    """Delete a formsemestre (affiche avertissements)"""
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    H = [
        html_sco_header.html_sem_header("Suppression du semestre", sem),
        """<div class="ue_warning"><span>Attention !</span>
<p class="help">A n'utiliser qu'en cas d'erreur lors de la saisie d'une formation. Normalement,
<b>un semestre ne doit jamais être supprimé</b> (on perd la mémoire des notes et de tous les événements liés à ce semestre !).</p>

 <p class="help">Tous les modules de ce semestre seront supprimés. Ceci n'est possible que
 si :</p>
 <ol>
  <li>aucune décision de jury n'a été entrée dans ce semestre;</li>
  <li>et aucun étudiant de ce semestre ne le compense avec un autre semestre.</li>
  </ol></div>""",
    ]

    evals = sco_evaluations.do_evaluation_list_in_formsemestre(formsemestre_id)
    if evals:
        H.append(
            """<p class="warning">Attention: il y a %d évaluations dans ce semestre (sa suppression entrainera l'effacement définif des notes) !</p>"""
            % len(evals)
        )
        submit_label = (
            "Confirmer la suppression (du semestre et des %d évaluations !)"
            % len(evals)
        )
    else:
        submit_label = "Confirmer la suppression du semestre"
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (("formsemestre_id", {"input_type": "hidden"}),),
        initvalues=F,
        submitlabel=submit_label,
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        if formsemestre_has_decisions_or_compensations(formsemestre_id):
            H.append(
                """<p><b>Ce semestre ne peut pas être supprimé ! (il y a des décisions de jury ou des compensations par d'autres semestres)</b></p>"""
            )
        else:
            H.append(tf[1])
        return "\n".join(H) + html_sco_header.sco_footer()
    elif tf[0] == -1:  # cancel
        return flask.redirect(
            scu.NotesURL()
            + "/formsemestre_status?formsemestre_id="
            + str(formsemestre_id)
        )
    else:
        return flask.redirect(
            "formsemestre_delete2?formsemestre_id=" + str(formsemestre_id)
        )


def formsemestre_delete2(formsemestre_id, dialog_confirmed=False):
    """Delete a formsemestre (confirmation)"""
    # Confirmation dialog
    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Vous voulez vraiment supprimer ce semestre ???</h2><p>(opération irréversible)</p>""",
            dest_url="",
            cancel_url="formsemestre_status?formsemestre_id=%s" % formsemestre_id,
            parameters={"formsemestre_id": formsemestre_id},
        )
    # Bon, s'il le faut...
    do_formsemestre_delete(formsemestre_id)
    return flask.redirect(scu.ScoURL() + "?head_message=Semestre%20supprimé")


def formsemestre_has_decisions_or_compensations(formsemestre_id):
    """True if decision de jury dans ce semestre
    ou bien compensation de ce semestre par d'autre ssemestres.
    """
    r = ndb.SimpleDictFetch(
        """SELECT v.id AS formsemestre_validation_id, v.* 
        FROM scolar_formsemestre_validation v 
        WHERE v.formsemestre_id = %(formsemestre_id)s 
        OR v.compense_formsemestre_id = %(formsemestre_id)s""",
        {"formsemestre_id": formsemestre_id},
    )
    return r


def do_formsemestre_delete(formsemestre_id):
    """delete formsemestre, and all its moduleimpls.
    No checks, no warnings: erase all !
    """
    cnx = ndb.GetDBConnexion()
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)

    sco_cache.EvaluationCache.invalidate_sem(formsemestre_id)

    # --- Destruction des modules de ce semestre
    mods = sco_moduleimpl.moduleimpl_list(formsemestre_id=formsemestre_id)
    for mod in mods:
        # evaluations
        evals = sco_evaluations.do_evaluation_list(
            args={"moduleimpl_id": mod["moduleimpl_id"]}
        )
        for e in evals:
            ndb.SimpleQuery(
                "DELETE FROM notes_notes WHERE evaluation_id=%(evaluation_id)s",
                e,
            )
            ndb.SimpleQuery(
                "DELETE FROM notes_notes_log WHERE evaluation_id=%(evaluation_id)s",
                e,
            )
            ndb.SimpleQuery(
                "DELETE FROM notes_evaluation WHERE id=%(evaluation_id)s",
                e,
            )

        sco_moduleimpl.do_moduleimpl_delete(
            mod["moduleimpl_id"], formsemestre_id=formsemestre_id
        )
    # --- Desinscription des etudiants
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = "DELETE FROM notes_formsemestre_inscription WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des evenements
    req = "DELETE FROM scolar_events WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des appreciations
    req = "DELETE FROM notes_appreciations WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Supression des validations (!!!)
    req = "DELETE FROM scolar_formsemestre_validation WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Supression des references a ce semestre dans les compensations:
    req = "UPDATE  scolar_formsemestre_validation SET compense_formsemestre_id=NULL WHERE compense_formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des autorisations
    req = "DELETE FROM scolar_autorisation_inscription WHERE origin_formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des coefs d'UE capitalisées
    req = "DELETE FROM notes_formsemestre_uecoef WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des item du menu custom
    req = "DELETE FROM notes_formsemestre_custommenu WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des formules
    req = "DELETE FROM notes_formsemestre_ue_computation_expr WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des preferences
    req = "DELETE FROM sco_prefs WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Suppression des groupes et partitions
    req = """DELETE FROM group_membership  
    WHERE group_id IN 
    (SELECT gm.group_id FROM group_membership gm, partition p, group_descr gd
        WHERE gm.group_id = gd.id AND gd.partition_id = p.id 
        AND p.formsemestre_id=%(formsemestre_id)s)
    """
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    req = """DELETE FROM group_descr 
    WHERE id IN 
    (SELECT gd.id FROM group_descr gd, partition p 
        WHERE gd.partition_id = p.id 
        AND p.formsemestre_id=%(formsemestre_id)s)
    """
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    req = "DELETE FROM partition WHERE formsemestre_id=%(formsemestre_id)s"
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Responsables
    req = """DELETE FROM notes_formsemestre_responsables 
    WHERE formsemestre_id=%(formsemestre_id)s"""
    cursor.execute(req, {"formsemestre_id": formsemestre_id})
    # --- Etapes
    req = """DELETE FROM notes_formsemestre_etapes
    WHERE formsemestre_id=%(formsemestre_id)s"""
    cursor.execute(req, {"formsemestre_id": formsemestre_id})

    # --- Destruction du semestre
    sco_formsemestre._formsemestreEditor.delete(cnx, formsemestre_id)

    # news
    from app.scodoc import sco_news

    sco_news.add(
        typ=sco_news.NEWS_SEM,
        object=formsemestre_id,
        text="Suppression du semestre %(titre)s" % sem,
    )


# ---------------------------------------------------------------------------------------
def formsemestre_edit_options(formsemestre_id):
    """dialog to change formsemestre options
    (accessible par ScoImplement ou dir. etudes)
    """
    log("formsemestre_edit_options")
    ok, err = sco_permissions_check.check_access_diretud(formsemestre_id)
    if not ok:
        return err
    return sco_preferences.SemPreferences(formsemestre_id).edit(categories=["bul"])


def formsemestre_change_lock(formsemestre_id) -> None:
    """Change etat (verrouille si ouvert, déverrouille si fermé)
    nota: etat (1 ouvert, 0 fermé)
    """
    ok, err = sco_permissions_check.check_access_diretud(formsemestre_id)
    if not ok:
        return err
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etat = not sem["etat"]

    args = {"formsemestre_id": formsemestre_id, "etat": etat}
    sco_formsemestre.do_formsemestre_edit(args)


def formsemestre_change_publication_bul(
    formsemestre_id, dialog_confirmed=False, redirect=True
):
    """Change etat publication bulletins sur portail"""
    ok, err = sco_permissions_check.check_access_diretud(formsemestre_id)
    if not ok:
        return err
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etat = not sem["bul_hide_xml"]

    if not dialog_confirmed:
        if etat:
            msg = "non"
        else:
            msg = ""
        return scu.confirm_dialog(
            "<h2>Confirmer la %s publication des bulletins ?</h2>" % msg,
            helpmsg="""Il est parfois utile de désactiver la diffusion des bulletins,
            par exemple pendant la tenue d'un jury ou avant harmonisation des notes.
            <br/>
            Ce réglage n'a d'effet que si votre établissement a interfacé ScoDoc et un portail étudiant.
            """,
            dest_url="",
            cancel_url="formsemestre_status?formsemestre_id=%s" % formsemestre_id,
            parameters={"bul_hide_xml": etat, "formsemestre_id": formsemestre_id},
        )

    args = {"formsemestre_id": formsemestre_id, "bul_hide_xml": etat}
    sco_formsemestre.do_formsemestre_edit(args)
    if redirect:
        return flask.redirect(
            "formsemestre_status?formsemestre_id=%s" % formsemestre_id
        )
    return None


def formsemestre_edit_uecoefs(formsemestre_id, err_ue_id=None):
    """Changement manuel des coefficients des UE capitalisées."""
    from app.scodoc import notes_table

    ok, err = sco_permissions_check.check_access_diretud(formsemestre_id)
    if not ok:
        return err
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)

    footer = html_sco_header.sco_footer()
    help = """<p class="help">
    Seuls les modules ont un coefficient. Cependant, il est nécessaire d'affecter un coefficient aux UE capitalisée pour pouvoir les prendre en compte dans la moyenne générale.
    </p>
    <p class="help">ScoDoc calcule normalement le coefficient d'une UE comme la somme des
    coefficients des modules qui la composent.
    </p>
    <p class="help">Dans certains cas, on n'a pas les mêmes modules dans le semestre antérieur
    (capitalisé) et dans le semestre courant, et le coefficient d'UE est alors variable.
    Il est alors possible de forcer la valeur du coefficient d'UE.
    </p>
    <p class="help">
    Indiquez "auto" (ou laisser vide) pour que ScoDoc calcule automatiquement le coefficient,
    ou bien entrez une valeur (nombre réel).
    </p>
    <p class="help">Dans le doute, si le mode auto n'est pas applicable et que tous les étudiants sont inscrits aux mêmes modules de ce semestre, prenez comme coefficient la somme indiquée. 
    Sinon, référez vous au programme pédagogique. Les lignes en <font color="red">rouge</font>
    sont à changer.
    </p>
    <p class="warning">Les coefficients indiqués ici ne s'appliquent que pour le traitement des UE capitalisées.
    </p>
    """
    H = [
        html_sco_header.html_sem_header("Coefficients des UE du semestre", sem),
        help,
    ]
    #
    ues, modimpls = notes_table.get_sem_ues_modimpls(formsemestre_id)
    for ue in ues:
        ue["sum_coefs"] = sum(
            [
                mod["module"]["coefficient"]
                for mod in modimpls
                if mod["module"]["ue_id"] == ue["ue_id"]
            ]
        )

    cnx = ndb.GetDBConnexion()

    initvalues = {"formsemestre_id": formsemestre_id}
    form = [("formsemestre_id", {"input_type": "hidden"})]
    for ue in ues:
        coefs = sco_formsemestre.formsemestre_uecoef_list(
            cnx, args={"formsemestre_id": formsemestre_id, "ue_id": ue["ue_id"]}
        )
        if coefs:
            initvalues["ue_" + str(ue["ue_id"])] = coefs[0]["coefficient"]
        else:
            initvalues["ue_" + str(ue["ue_id"])] = "auto"
        descr = {
            "size": 10,
            "title": ue["acronyme"],
            "explanation": "somme coefs modules = %s" % ue["sum_coefs"],
        }
        if ue["ue_id"] == err_ue_id:
            descr["dom_id"] = "erroneous_ue"
        form.append(("ue_" + str(ue["ue_id"]), descr))

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        form,
        submitlabel="Changer les coefficients",
        cancelbutton="Annuler",
        initvalues=initvalues,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + footer
    elif tf[0] == -1:
        return "<h4>annulation</h4>"  # XXX
    else:
        # change values
        # 1- supprime les coef qui ne sont plus forcés
        # 2- modifie ou cree les coefs
        ue_deleted = []
        ue_modified = []
        msg = []
        for ue in ues:
            val = tf[2]["ue_" + str(ue["ue_id"])]
            coefs = sco_formsemestre.formsemestre_uecoef_list(
                cnx, args={"formsemestre_id": formsemestre_id, "ue_id": ue["ue_id"]}
            )
            if val == "" or val == "auto":
                # supprime ce coef (il sera donc calculé automatiquement)
                if coefs:
                    ue_deleted.append(ue)
            else:
                try:
                    val = float(val)
                    if (not coefs) or (coefs[0]["coefficient"] != val):
                        ue["coef"] = val
                        ue_modified.append(ue)
                except:
                    ok = False
                    msg.append(
                        "valeur invalide (%s) pour le coefficient de l'UE %s"
                        % (val, ue["acronyme"])
                    )

        if not ok:
            return (
                "\n".join(H)
                + "<p><ul><li>%s</li></ul></p>" % "</li><li>".join(msg)
                + tf[1]
                + footer
            )

        # apply modifications
        for ue in ue_modified:
            sco_formsemestre.do_formsemestre_uecoef_edit_or_create(
                cnx, formsemestre_id, ue["ue_id"], ue["coef"]
            )
        for ue in ue_deleted:
            sco_formsemestre.do_formsemestre_uecoef_delete(
                cnx, formsemestre_id, ue["ue_id"]
            )

        if ue_modified or ue_deleted:
            z = ["""<h3>Modification effectuées</h3>"""]
            if ue_modified:
                z.append("""<h4>Coefs modifiés dans les UE:<h4><ul>""")
                for ue in ue_modified:
                    z.append("<li>%(acronyme)s : %(coef)s</li>" % ue)
                z.append("</ul>")
            if ue_deleted:
                z.append("""<h4>Coefs supprimés dans les UE:<h4><ul>""")
                for ue in ue_deleted:
                    z.append("<li>%(acronyme)s</li>" % ue)
                z.append("</ul>")
        else:
            z = ["""<h3>Aucune modification</h3>"""]
        sco_cache.invalidate_formsemestre(
            formsemestre_id=formsemestre_id
        )  # > modif coef UE cap (modifs notes de _certains_ etudiants)

        header = html_sco_header.html_sem_header("Coefficients des UE du semestre", sem)
        return (
            header
            + "\n".join(z)
            + """<p><a href="formsemestre_status?formsemestre_id=%s">Revenir au tableau de bord</a></p>"""
            % formsemestre_id
            + footer
        )


# ----- identification externe des sessions (pour SOJA et autres logiciels)
def get_formsemestre_session_id(sem, F, parcours):
    """Identifiant de session pour ce semestre
    Exemple:  RT-DUT-FI-S1-ANNEE

    DEPT-TYPE-MODALITE+-S?|SPECIALITE

    TYPE=DUT|LP*|M*
    MODALITE=FC|FI|FA (si plusieurs, en inverse alpha)

    SPECIALITE=[A-Z]+   EON,ASSUR, ... (si pas Sn ou SnD)

    ANNEE=annee universitaire de debut (exemple: un S2 de 2013-2014 sera S2-2013)

    """
    # sem = sco_formsemestre.get_formsemestre( formsemestre_id)
    # F = sco_formations.formation_list(  args={ 'formation_id' : sem['formation_id'] } )[0]
    # parcours = sco_codes_parcours.get_parcours_from_code(F['type_parcours'])

    ImputationDept = sco_preferences.get_preference(
        "ImputationDept", sem["formsemestre_id"]
    )
    if not ImputationDept:
        ImputationDept = sco_preferences.get_preference("DeptName")
    ImputationDept = ImputationDept.upper()
    parcours_type = parcours.NAME
    modalite = sem["modalite"]
    modalite = (
        (modalite or "").replace("FAP", "FA").replace("APP", "FA")
    )  # exception pour code Apprentissage
    if sem["semestre_id"] > 0:
        decale = scu.sem_decale_str(sem)
        semestre_id = "S%d" % sem["semestre_id"] + decale
    else:
        semestre_id = F["code_specialite"]
    annee_sco = str(scu.annee_scolaire_debut(sem["annee_debut"], sem["mois_debut_ord"]))

    return scu.sanitize_string(
        "-".join((ImputationDept, parcours_type, modalite, semestre_id, annee_sco))
    )
