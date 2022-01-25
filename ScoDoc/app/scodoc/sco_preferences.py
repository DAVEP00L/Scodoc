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

"""Global/Semestre Preferences for ScoDoc (version dec 2008)

Preferences (paramètres) communs à tous les utilisateurs.
Peuvent être définis globalement (pour tous les semestres)
ou bien seulement pour un semestre précis.

Chaque parametre est défini dans la base de données SQL par:
 - name : nom du parametre
 - value: valeur du parametre, ou NULL si on doit utiliser une valeur par défaut
 - formsemestre_id: semestre associé, ou NULL si applicable à tous les semestres
                    pour lesquels une valeur spécifique n'est pas définie.

Au niveau du code interface, on défini pour chaque préférence:
 - name (clé)
 - title : titre en français
 - initvalue : valeur initiale
 - explanation: explication en français
 - size: longueur du chap texte
 - input_type: textarea,separator,... type de widget TrivialFormulator a utiliser
 - rows, rols: geometrie des textareas
 - category: misc ou bul ou page_bulletins ou abs ou general ou portal 
             ou pdf ou pvpdf ou ...
 - only_global (default False): si vraie, ne peut pas etre associée a un seul semestre.

Les titres et sous-titres de chaque catégorie sont définis dans PREFS_CATEGORIES

On peut éditer les préférences d'une ou plusieurs catégories au niveau d'un 
semestre ou au niveau global. 
* niveau global: changer les valeurs, liste de catégories.
   
* niveau d'un semestre:
   présenter valeur courante: valeur ou "definie globalement" ou par defaut
    lien "changer valeur globale"
   
------------------------------------------------------------------------------
Doc technique:

* Base de données:
Toutes les préférences sont stockées dans la table sco_prefs, qui contient
des tuples (name, value, formsemestre_id).
Si formsemestre_id est NULL, la valeur concerne tous les semestres,
sinon, elle ne concerne que le semestre indiqué. 

* Utilisation dans ScoDoc8
  - lire une valeur: 
      get_preference(name, formsemestre_id)
      nb: les valeurs sont des chaines, sauf:
         . si le type est spécfié (float ou int)
         . les boolcheckbox qui sont des entiers 0 ou 1
  - avoir un mapping (read only) de toutes les valeurs:
      sco_preferences.SemPreferences(formsemestre_id)
  - editer les preferences globales:
      sco_preferences.get_base_preferences(self).edit()
  - editer les preferences d'un semestre:
      SemPreferences(formsemestre_id).edit()

* Implémentation: sco_preferences.py

PREF_CATEGORIES : définition des catégories de préférences (pour
dialogues édition)
prefs_definition : pour chaque pref, donne infos pour édition (titre, type...) et
valeur par défaut.

class BasePreferences
Une instance unique par site (département, repéré par URL).
- charge les preferences pour tous le semestres depuis la BD.
 .get(formsemestre_id, name)
 .is_global(formsemestre_id, name)
 .save(formsemestre_id=None, name=None)
 .set(formsemestre_id, name, value)
 .deleteformsemestre_id, name)
 .edit() (HTML dialog)

class SemPreferences(formsemestre_id)
Une instance par semestre, et une instance pour prefs globales.
L'attribut .base_prefs point sur BasePreferences.
 .__getitem__   [name]
 .is_global(name)
 .edit(categories=[])


get_base_preferences(formsemestre_id)
 Return base preferences for current scodoc_dept (instance BasePreferences)

"""
import flask
from flask import g, url_for, request
from flask_login import current_user

from app.models import Departement
from app.scodoc import sco_cache
from app import log
from app.scodoc.sco_exceptions import ScoValueError, ScoException
from app.scodoc.TrivialFormulator import TrivialFormulator
import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu

_SCO_BASE_PREFERENCES = {}  # { dept_acronym: BasePreferences instance }


def clear_base_preferences():
    """Clear cached preferences"""
    # usefull only for tests, where the same process may run
    # successively on several databases
    _SCO_BASE_PREFERENCES.clear()


def get_base_preferences():
    """Return global preferences for the current department"""
    dept_acronym = g.scodoc_dept
    if not dept_acronym in _SCO_BASE_PREFERENCES:
        _SCO_BASE_PREFERENCES[dept_acronym] = BasePreferences(dept_acronym)
    return _SCO_BASE_PREFERENCES[dept_acronym]


def get_preference(name, formsemestre_id=None):
    """Returns value of named preference.
    All preferences have a sensible default value, so this
    function always returns a usable value for all defined preferences names.
    """
    return get_base_preferences().get(formsemestre_id, name)


def _convert_pref_type(p, pref_spec):
    """p est une ligne de la bd
    {'id': , 'dept_id': , 'name': '', 'value': '', 'formsemestre_id': }
    converti la valeur chane en le type désiré spécifié par pref_spec
    """
    if "type" in pref_spec:
        typ = pref_spec["type"]
        if typ == "float":
            # special case for float values (where NULL means 0)
            if p["value"]:
                p["value"] = float(p["value"])
            else:
                p["value"] = 0.0
        else:
            func = eval(typ)
            p["value"] = func(p["value"])
    if pref_spec.get("input_type", None) == "boolcheckbox":
        # boolcheckbox: la valeur stockée en base est une chaine "0" ou "1"
        # que l'on ressort en True|False
        if p["value"]:
            try:
                p["value"] = bool(int(p["value"]))
            except ValueError:
                log(
                    f"""Warning: invalid value for boolean pref in db: '{p["value"]}'"""
                )
                p["value"] = False
        else:
            p["value"] = False  # NULL (backward compat)


def _get_pref_default_value_from_config(name, pref_spec):
    """get default value store in application level config.
    If not found, use default value hardcoded in pref_spec.
    """
    # XXX va changer avec la nouvelle base
    # search in scu.CONFIG
    if hasattr(scu.CONFIG, name):
        value = getattr(scu.CONFIG, name)
        log("sco_preferences: found default value in config for %s=%s" % (name, value))
    else:
        # uses hardcoded default
        value = pref_spec["initvalue"]
    return value


PREF_CATEGORIES = (
    # sur page "Paramètres"
    ("general", {}),
    ("misc", {"title": "Divers"}),
    ("abs", {"title": "Suivi des absences", "related": ("bul",)}),
    ("portal", {"title": "Liaison avec portail (Apogée, etc)"}),
    (
        "pdf",
        {
            "title": "Mise en forme des documents PDF",
            "related": ("pvpdf", "bul_margins"),
        },
    ),
    (
        "pvpdf",
        {
            "title": "Procès verbaux de jury (documents PDF)",
            "related": ("pdf", "bul_margins"),
        },
    ),
    # sur page "Réglages des bulletins de notes"
    (
        "bul",
        {
            "title": "Réglages des bulletins de notes",
            "related": ("abs", "bul_margins", "bul_mail"),
        },
    ),
    # sur page "Mise en page des bulletins"
    (
        "bul_margins",
        {
            "title": "Marges additionnelles des bulletins, en millimètres",
            "subtitle": "Le bulletin de notes notes est toujours redimensionné pour occuper l'espace disponible entre les marges.",
            "related": ("bul", "bul_mail", "pdf"),
        },
    ),
    (
        "bul_mail",
        {
            "title": "Envoi des bulletins par e-mail",
            "related": ("bul", "bul_margins", "pdf"),
        },
    ),
    (
        "feuilles",
        {"title": "Mise en forme des feuilles (Absences, Trombinoscopes, Moodle, ...)"},
    ),
    ("pe", {"title": "Avis de poursuites d'études"}),
    ("edt", {"title": "Connexion avec le logiciel d'emplois du temps"}),
)


class BasePreferences(object):
    """Global preferences"""

    _editor = ndb.EditableTable(
        "sco_prefs",
        "pref_id",
        ("pref_id", "dept_id", "name", "value", "formsemestre_id"),
        filter_dept=True,
        sortkey="name",
        convert_null_outputs_to_empty=False,
        # allow_set_id=True, #sco8
        html_quote=False,  # car markup pdf reportlab  (<b> etc)
        filter_nulls=False,
    )

    def __init__(self, dept_acronym: str):
        dept = Departement.query.filter_by(acronym=dept_acronym).first()
        if not dept:
            raise ScoValueError(f"Invalid departement: {dept_acronym}")
        self.dept_id = dept.id
        self.init()
        self.load()

    def init(self):
        from app.scodoc import sco_bulletins_generator

        self.prefs_definition = (
            (
                "DeptName",
                {
                    "initvalue": "Dept",
                    "title": "Nom abrégé du département",
                    "size": 12,
                    "category": "general",
                    "only_global": True,
                },
            ),
            (
                "DeptFullName",
                {
                    "initvalue": "nom du département",
                    "title": "Nom complet du département",
                    "explanation": "inutilisé par défaut",
                    "size": 40,
                    "category": "general",
                    "only_global": True,
                },
            ),
            (
                "UnivName",
                {
                    "initvalue": "",
                    "title": "Nom de l'Université",
                    "explanation": "apparait sur les bulletins et PV de jury",
                    "size": 40,
                    "category": "general",
                    "only_global": True,
                },
            ),
            (
                "InstituteName",
                {
                    "initvalue": "",
                    "title": "Nom de l'Institut",
                    "explanation": 'exemple "IUT de Villetaneuse". Peut être utilisé sur les bulletins.',
                    "size": 40,
                    "category": "general",
                    "only_global": True,
                },
            ),
            (
                "DeptIntranetTitle",
                {
                    "initvalue": "Intranet",
                    "title": "Nom lien intranet",
                    "size": 40,
                    "explanation": 'titre du lien "Intranet" en haut à gauche',
                    "category": "general",
                    "only_global": True,
                },
            ),
            (
                "DeptIntranetURL",
                {
                    "initvalue": "",
                    "title": """URL de l'"intranet" du département""",
                    "size": 40,
                    "explanation": 'lien "Intranet" en haut à gauche',
                    "category": "general",
                    "only_global": True,
                },
            ),
            (
                "emails_notifications",
                {
                    "initvalue": "",
                    "title": "e-mails à qui notifier les opérations",
                    "size": 70,
                    "explanation": "adresses séparées par des virgules; notifie les opérations (saisies de notes, etc). (vous pouvez préférer utiliser le flux rss)",
                    "category": "general",
                    "only_global": False,  # peut être spécifique à un semestre
                },
            ),
            # ------------------ MISC
            (
                "use_ue_coefs",
                {
                    "initvalue": 0,
                    "title": "Utiliser les coefficients d'UE pour calculer la moyenne générale",
                    "explanation": """Calcule les moyennes dans chaque UE, puis pondère ces résultats pour obtenir la moyenne générale. Par défaut, le coefficient d'une UE est simplement la somme des coefficients des modules dans lesquels l'étudiant a des notes. <b>Attention: changer ce réglage va modifier toutes les moyennes du semestre !</b>""",
                    "input_type": "boolcheckbox",
                    "category": "misc",
                    "labels": ["non", "oui"],
                    "only_global": False,
                },
            ),
            (
                "recap_hidebac",
                {
                    "initvalue": 0,
                    "title": "Cacher la colonne Bac",
                    "explanation": "sur la table récapitulative",
                    "input_type": "boolcheckbox",
                    "category": "misc",
                    "labels": ["non", "oui"],
                    "only_global": False,
                },
            ),
            # ------------------ Absences
            (
                "email_chefdpt",
                {
                    "initvalue": "",
                    "title": "e-mail chef du département",
                    "size": 40,
                    "explanation": "utilisé pour envoi mail notification absences",
                    "category": "abs",
                    "only_global": True,
                },
            ),
            (
                "work_saturday",
                {
                    "initvalue": 0,
                    "title": "Considérer le samedi comme travaillé",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                    "only_global": True,  # devrait etre par semestre, mais demanderait modif gestion absences
                },
            ),
            (
                "abs_require_module",  # affecte l'UI mais pas les fonctions de base
                {
                    "initvalue": 0,
                    "title": "Imposer l'indication du module lors de la saisie des absences",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                    "only_global": False,
                },
            ),
            (
                "handle_billets_abs",
                {
                    "initvalue": 0,
                    "title": 'Gestion de "billets" d\'absence',
                    "explanation": 'fonctions pour traiter les "billets" déclarés par les étudiants sur un portail externe',
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                    "only_global": True,
                },
            ),
            (
                "abs_notify_chief",  # renamed from "send_mail_absence_to_chef"
                {
                    "initvalue": 0,
                    "title": "Notifier les absences au chef",
                    "explanation": "Envoyer un mail au chef si un étudiant a beaucoup d'absences",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                    "only_global": True,
                },
            ),
            (
                "abs_notify_respsem",
                {
                    "initvalue": 0,
                    "title": "Notifier les absences au dir. des études",
                    "explanation": "Envoyer un mail au responsable du semestre si un étudiant a beaucoup d'absences",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                },
            ),
            (
                "abs_notify_respeval",
                {
                    "initvalue": 0,
                    "title": "Notifier les absences aux resp. de modules",
                    "explanation": "Envoyer un mail à chaque absence aux responsable des modules avec évaluation à cette date",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                },
            ),
            (
                "abs_notify_etud",
                {
                    "initvalue": 0,
                    "title": "Notifier les absences aux étudiants concernés",
                    "explanation": "Envoyer un mail à l'étudiant s'il a \"beaucoup\" d'absences",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "abs",
                },
            ),
            (
                "abs_notify_email",
                {
                    "initvalue": "",
                    "title": "Notifier à:",
                    "explanation": "e-mail à qui envoyer des notification d'absences (en sus des autres destinataires éventuels, comme le chef etc.)",
                    "size": 40,
                    "category": "abs",
                },
            ),
            (
                "abs_notify_max_freq",
                {
                    "initvalue": 7,
                    "title": "Fréquence maximale de notification",
                    "explanation": "en jours (pas plus de X envois de mail pour chaque étudiant/destinataire)",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "abs",
                },
            ),
            (
                "abs_notify_abs_threshold",
                {
                    "initvalue": 10,
                    "title": "Seuil de première notification",
                    "explanation": "nb minimum d'absences (en 1/2 journées) avant notification",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "abs",
                },
            ),
            (
                "abs_notify_abs_increment",
                {
                    "initvalue": 20,  # les notification suivantes seront donc rares
                    "title": "Seuil notifications suivantes",
                    "explanation": "nb minimum d'absences (en 1/2 journées supplémentaires)",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "abs",
                },
            ),
            (
                "abs_notification_mail_tmpl",
                {
                    "initvalue": """
                        --- Ceci est un message de notification automatique issu de ScoDoc ---

                        L'étudiant %(nomprenom)s  
        L'étudiant %(nomprenom)s  
                        L'étudiant %(nomprenom)s  
                        inscrit en %(inscription)s) 
        inscrit en %(inscription)s) 
                        inscrit en %(inscription)s) 

                        a cumulé %(nbabsjust)s absences justifiées 
        a cumulé %(nbabsjust)s absences justifiées 
                        a cumulé %(nbabsjust)s absences justifiées 
                        et %(nbabsnonjust)s absences NON justifiées.

                        Le compte a pu changer depuis cet envoi, voir la fiche sur %(url_ficheetud)s.


                        Votre dévoué serveur ScoDoc.

                        PS: Au dela de %(abs_notify_abs_threshold)s, un email automatique est adressé toutes les %(abs_notify_abs_increment)s absences. Ces valeurs sont modifiables dans les préférences de ScoDoc.
                    """,
                    "title": """Message notification e-mail""",
                    "explanation": """Balises remplacées, voir la documentation""",
                    "input_type": "textarea",
                    "rows": 15,
                    "cols": 64,
                    "category": "abs",
                },
            ),
            # portal
            (
                "portal_url",
                {
                    "initvalue": "",
                    "title": "URL du portail",
                    "size": 40,
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "portal_timeout",
                {
                    "initvalue": 3,
                    "title": "timeout",
                    "explanation": "secondes",
                    "size": 3,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "portal_dept_name",
                {
                    "initvalue": "Dept",
                    "title": "Code du département sur le portail",
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "etapes_url",
                {
                    "initvalue": "",
                    "title": "URL listant les étapes Apogée",
                    "size": 40,
                    "category": "portal",
                    "only_global": True,
                    "explanation": "par defaut, selon l'api, getEtapes ou scodocEtapes sur l'URL du portail",
                },
            ),
            (
                "maquette_url",
                {
                    "initvalue": "",
                    "title": "URL maquettes Apogee",
                    "size": 40,
                    "category": "portal",
                    "only_global": True,
                    "explanation": "par defaut, scodocMaquette sur l'URL du portail",
                },
            ),
            (
                "portal_api",
                {
                    "initvalue": 1,
                    "title": "Version de l'API",
                    "explanation": "1 ou 2",
                    "size": 3,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "etud_url",
                {
                    "initvalue": "",
                    "title": "URL listant les étudiants Apogée",
                    "size": 40,
                    "category": "portal",
                    "only_global": True,
                    "explanation": "par defaut, selon l'api, getEtud ou scodocEtudiant sur l'URL du portail",
                },
            ),
            (
                "photo_url",
                {
                    "initvalue": "",
                    "title": "URL donnant la photo d'un étudiant avec argument nip=",
                    "size": 40,
                    "category": "portal",
                    "only_global": True,
                    "explanation": "par defaut, selon l'api, getPhoto ou scodocPhoto sur l'URL du portail",
                },
            ),
            (
                "xml_etapes_by_dept",
                {
                    "initvalue": 1,
                    "title": "Etapes séparées par département",
                    "explanation": "XML getEtapes structuré en départements ?",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "notify_etud_changes_to",
                {
                    "initvalue": "",
                    "title": "e-mail à qui notifier les changements d'identité des étudiants",
                    "explanation": "utile pour mettre à jour manuellement d'autres bases de données",
                    "size": 40,
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "always_require_ine",
                {
                    "initvalue": 0,
                    "title": "Impose la présence du code INE",
                    "explanation": "lors de toute création d'étudiant (manuelle ou non)",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "always_require_apo_sem_codes",
                {
                    "initvalue": 0,
                    "title": "Impose la présence des codes Apogée",
                    "explanation": "lors des créations de semestres",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            # exports Apogée
            (
                "export_res_etape",
                {
                    "initvalue": 1,
                    "title": "Exporter résultat de l'étape",
                    "explanation": "remplissage maquettes export Apogée",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "export_res_sem",
                {
                    "initvalue": 1,
                    "title": "Exporter résultat du semestre",
                    "explanation": "remplissage maquettes export Apogée",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "export_res_ues",
                {
                    "initvalue": 1,
                    "title": "Exporter les résultats d'UE",
                    "explanation": "remplissage maquettes export Apogée",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "export_res_modules",
                {
                    "initvalue": 1,
                    "title": "Exporter les résultats de modules",
                    "explanation": "remplissage maquettes export Apogée",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "export_res_sdj",
                {
                    "initvalue": 0,
                    "title": "Exporter les résultats même sans décision de jury",
                    "explanation": "si coché, exporte exporte étudiants même si pas décision de jury saisie (sinon laisse vide)",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            (
                "export_res_rat",
                {
                    "initvalue": 1,
                    "title": "Exporter les RAT comme ATT",
                    "explanation": "si coché, exporte exporte étudiants en attente de ratrapage comme ATT (sinon laisse vide)",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "portal",
                    "only_global": True,
                },
            ),
            # pdf
            (
                "SCOLAR_FONT",
                {
                    "initvalue": "Helvetica",
                    "title": "Police de caractère principale",
                    "explanation": "pour les pdf",
                    "size": 25,
                    "category": "pdf",
                },
            ),
            (
                "SCOLAR_FONT_SIZE",
                {
                    "initvalue": 10,
                    "title": "Taille des caractères",
                    "explanation": "pour les pdf",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "pdf",
                },
            ),
            (
                "SCOLAR_FONT_SIZE_FOOT",
                {
                    "initvalue": 6,
                    "title": "Taille des caractères pied de page",
                    "explanation": "pour les pdf",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "pdf",
                },
            ),
            (
                "pdf_footer_x",
                {
                    "initvalue": 20,
                    "title": "Position horizontale du pied de page pdf (en mm)",
                    "size": 8,
                    "type": "float",
                    "category": "pdf",
                },
            ),
            (
                "pdf_footer_y",
                {
                    "initvalue": 6.35,
                    "title": "Position verticale du pied de page pdf (en mm)",
                    "size": 8,
                    "type": "float",
                    "category": "pdf",
                },
            ),
            # pvpdf
            (
                "DirectorName",
                {
                    "initvalue": "",
                    "title": "Nom du directeur de l'établissement",
                    "size": 32,
                    "explanation": "pour les PV de jury",
                    "category": "pvpdf",
                },
            ),
            (
                "DirectorTitle",
                {
                    "initvalue": """directeur de l'IUT""",
                    "title": 'Titre du "directeur"',
                    "explanation": "titre apparaissant à côté de la signature sur les PV de jury",
                    "size": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "ChiefDeptName",
                {
                    "initvalue": "",
                    "title": "Nom du chef de département",
                    "size": 32,
                    "explanation": "pour les bulletins pdf",
                    "category": "pvpdf",
                },
            ),
            (
                "INSTITUTION_NAME",
                {
                    "initvalue": "<b>Institut Universitaire de Technologie - Université Paris 13</b>",
                    "title": "Nom institution sur pied de pages PV",
                    "explanation": "(pdf, balises &lt;b&gt; interprétées)",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "INSTITUTION_ADDRESS",
                {
                    "initvalue": "Web <b>www.iutv.univ-paris13.fr</b> - 99 avenue Jean-Baptiste Clément - F 93430 Villetaneuse",
                    "title": "Adresse institution sur pied de pages PV",
                    "explanation": "(pdf, balises &lt;b&gt; interprétées)",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "INSTITUTION_CITY",
                {
                    "initvalue": "Villetaneuse",
                    "title": "Ville de l'institution",
                    "explanation": "pour les lettres individuelles",
                    "size": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "PV_INTRO",
                {
                    "initvalue": """<bullet>-</bullet>  
                        Vu l'arrêté du 3 août 2005 relatif au diplôme universitaire de technologie et notamment son article 4 et 6;
                        </para>
                        <para><bullet>-</bullet>  
        <para><bullet>-</bullet>  
                        <para><bullet>-</bullet>  
                        vu l'arrêté n° %(Decnum)s du Président de l'%(UnivName)s;
                        </para>
                        <para><bullet>-</bullet> 
        <para><bullet>-</bullet> 
                        <para><bullet>-</bullet> 
                        vu la délibération de la commission %(Type)s en date du %(Date)s présidée par le Chef du département;
                        """,
                    "title": """Paragraphe d'introduction sur le PV""",
                    "explanation": """Balises remplacées: %(Univname)s = nom de l'université, %(DecNum)s = numéro de l'arrêté, %(Date)s = date de la commission, %(Type)s = type de commission (passage ou délivrance), %(VDICode)s = code diplôme""",
                    "input_type": "textarea",
                    "cols": 80,
                    "rows": 10,
                    "category": "pvpdf",
                },
            ),
            (
                "PV_WITH_BACKGROUND",
                {
                    "initvalue": 0,
                    "title": "Mettre l'image de fond sur les PV de jury (paysage)",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            (
                "PV_WITH_HEADER",
                {
                    "initvalue": 1,  # legacy
                    "title": "Ajouter l'en-tête sur les PV (paysage)",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            (
                "PV_WITH_FOOTER",
                {
                    "initvalue": 1,  # legacy
                    "title": "Ajouter le pied de page sur les PV (paysage)",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            (
                "PV_TITLE_WITH_VDI",
                {
                    "initvalue": 0,  # legacy
                    "title": "Indiquer VDI et code dans le titre du PV",
                    "explanation": "il est souvent préférable de l'inclure dans le paragraphe d'introduction.",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            # marges PV paysages (en millimètres)
            (
                "pv_left_margin",
                {
                    "initvalue": 0,
                    "size": 10,
                    "title": "Marge gauche PV en mm",
                    "type": "float",
                    "category": "pvpdf",
                },
            ),
            (
                "pv_top_margin",
                {
                    "initvalue": 23,
                    "size": 10,
                    "title": "Marge haute PV",
                    "type": "float",
                    "category": "pvpdf",
                },
            ),
            (
                "pv_right_margin",
                {
                    "initvalue": 0,
                    "size": 10,
                    "title": "Marge droite PV",
                    "type": "float",
                    "category": "pvpdf",
                },
            ),
            (
                "pv_bottom_margin",
                {
                    "initvalue": 5,
                    "size": 10,
                    "title": "Marge basse PV",
                    "type": "float",
                    "category": "pvpdf",
                },
            ),
            (
                "PV_LETTER_DIPLOMA_SIGNATURE",
                {
                    "initvalue": """Le %(DirectorTitle)s, <br/>%(DirectorName)s""",
                    "title": """Signature des lettres individuelles de diplôme""",
                    "explanation": """%(DirectorName)s et %(DirectorTitle)s remplacés""",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "PV_LETTER_PASSAGE_SIGNATURE",
                {
                    "initvalue": """Pour le Directeur de l'IUT<br/>
                        et par délégation<br/>
                        Le Chef du département""",
                    "title": """Signature des lettres individuelles de passage d'un semestre à l'autre""",
                    "explanation": """%(DirectorName)s et %(DirectorTitle)s remplacés""",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "pv_sig_image_height",
                {
                    "initvalue": 11,
                    "size": 10,
                    "title": "Hauteur de l'image de la signature",
                    "type": "float",
                    "explanation": "Lorsqu'on donne une image de signature, elle est redimensionnée à cette taille (en millimètres)",
                    "category": "pvpdf",
                },
            ),
            (
                "PV_LETTER_TEMPLATE",
                {
                    "initvalue": """<para spaceBefore="1mm"> </para>
                        <para spaceBefore="20mm" leftindent="%(pv_htab1)s">%(INSTITUTION_CITY)s, le %(date_jury)s
                        </para>

                        <para leftindent="%(pv_htab1)s" spaceBefore="10mm">
                        à <b>%(nomprenom)s</b>
                        </para>
                        <para leftindent="%(pv_htab1)s">%(domicile)s</para>
                        <para leftindent="%(pv_htab1)s">%(codepostaldomicile)s %(villedomicile)s</para>

                        <para spaceBefore="25mm" fontSize="14" alignment="center">
                        <b>Jury de %(type_jury)s  <br/> %(titre_formation)s</b>
                        </para>

                        <para spaceBefore="10mm" fontSize="14" leftindent="0">
                        Le jury de %(type_jury_abbrv)s du département %(DeptName)s
                        s'est réuni le %(date_jury)s. 
        s'est réuni le %(date_jury)s. 
                        s'est réuni le %(date_jury)s. 
                        </para>
                        <para fontSize="14" leftindent="0">Les décisions vous concernant sont :
                        </para>

                        <para leftindent="%(pv_htab2)s" spaceBefore="5mm" fontSize="14">%(prev_decision_sem_txt)s</para>
                        <para leftindent="%(pv_htab2)s" spaceBefore="5mm" fontSize="14">
                            <b>Décision %(decision_orig)s :</b> %(decision_sem_descr)s
                        </para>

                        <para leftindent="%(pv_htab2)s" spaceBefore="0mm" fontSize="14">
                        %(decision_ue_txt)s
                        </para>

                        <para leftindent="%(pv_htab2)s" spaceBefore="0mm" fontSize="14">
                        %(observation_txt)s
                        </para>

                        <para spaceBefore="10mm" fontSize="14">%(autorisations_txt)s</para>

                        <para spaceBefore="10mm" fontSize="14">%(diplome_txt)s</para>
                        """,
                    "title": """Lettre individuelle""",
                    "explanation": """Balises remplacées et balisage XML, voir la documentation""",
                    "input_type": "textarea",
                    "rows": 15,
                    "cols": 64,
                    "category": "pvpdf",
                },
            ),
            (
                "PV_LETTER_WITH_BACKGROUND",
                {
                    "initvalue": 0,
                    "title": "Mettre l'image de fond sur les lettres individuelles de décision",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            (
                "PV_LETTER_WITH_HEADER",
                {
                    "initvalue": 0,
                    "title": "Ajouter l'en-tête sur les lettres individuelles de décision",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            (
                "PV_LETTER_WITH_FOOTER",
                {
                    "initvalue": 0,
                    "title": "Ajouter le pied de page sur les lettres individuelles de décision",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "pvpdf",
                },
            ),
            (
                "pv_htab1",
                {
                    "initvalue": "8cm",
                    "title": "marge colonne droite lettre",
                    "explanation": "pour les courriers pdf",
                    "size": 10,
                    "category": "pvpdf",
                },
            ),
            (
                "pv_htab2",
                {
                    "initvalue": "5mm",
                    "title": "marge colonne gauche lettre",
                    "explanation": "pour les courriers pdf",
                    "size": 10,
                    "category": "pvpdf",
                },
            ),
            (
                "PV_FONTNAME",
                {
                    "initvalue": "Times-Roman",
                    "title": "Police de caractère pour les PV",
                    "explanation": "pour les pdf",
                    "size": 25,
                    "category": "pvpdf",
                },
            ),
            # bul
            (
                "bul_title",
                {
                    "initvalue": "Université Paris 13 - IUT de Villetaneuse - Département %(DeptName)s",
                    "size": 70,
                    "title": "Titre des bulletins",
                    "explanation": "<tt>%(DeptName)s</tt> est remplacé par le nom du département",
                    "category": "bul",
                },
            ),
            (
                "bul_class_name",
                {
                    "initvalue": sco_bulletins_generator.bulletin_default_class_name(),
                    "input_type": "menu",
                    "labels": sco_bulletins_generator.bulletin_class_descriptions(),
                    "allowed_values": sco_bulletins_generator.bulletin_class_names(),
                    "title": "Format des bulletins",
                    "explanation": "format de présentation des bulletins de note (web et pdf)",
                    "category": "bul",
                },
            ),
            (
                "bul_show_abs",  # ex "gestion_absence"
                {
                    "initvalue": 1,
                    "title": "Indiquer les absences sous les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_abs_modules",
                {
                    "initvalue": 0,
                    "title": "Indiquer les absences dans chaque module",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_decision",
                {
                    "initvalue": 0,
                    "title": "Faire figurer les décisions sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_ects",
                {
                    "initvalue": 1,
                    "title": "Faire figurer les ECTS sur les bulletins",
                    "explanation": "crédits associés aux UE ou aux modules, selon réglage",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_codemodules",
                {
                    "initvalue": 0,
                    "title": "Afficher codes des modules sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_matieres",
                {
                    "initvalue": 0,
                    "title": "Afficher les matières sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_all_evals",
                {
                    "initvalue": 0,
                    "title": "Afficher toutes les évaluations sur les bulletins",
                    "explanation": "y compris incomplètes ou futures",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_rangs",
                {
                    "initvalue": 1,
                    "title": "Afficher le classement sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_ue_rangs",
                {
                    "initvalue": 1,
                    "title": "Afficher le classement dans chaque UE sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_mod_rangs",
                {
                    "initvalue": 1,
                    "title": "Afficher le classement dans chaque module sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_moypromo",
                {
                    "initvalue": 0,
                    "title": "Afficher moyennes de la promotion sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_minmax",
                {
                    "initvalue": 0,
                    "title": "Afficher min/max moyennes sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_minmax_mod",
                {
                    "initvalue": 0,
                    "title": "Afficher min/max moyennes des modules sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_minmax_eval",
                {
                    "initvalue": 0,
                    "title": "Afficher min/max moyennes des évaluations sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_coef",
                {
                    "initvalue": 1,
                    "title": "Afficher coefficient des ue/modules sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_ue_cap_details",
                {
                    "initvalue": 0,
                    "title": "Afficher détail des notes des UE capitalisées sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_ue_cap_current",
                {
                    "initvalue": 1,
                    "title": "Afficher les UE en cours mais capitalisées sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_temporary_forced",
                {
                    "initvalue": 0,
                    "title": 'Bannière "provisoire" sur les bulletins',
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_temporary",
                {
                    "initvalue": 1,
                    "title": 'Bannière "provisoire" si pas de décision de jury',
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_temporary_txt",
                {
                    "initvalue": "Provisoire",
                    "title": 'Texte de la bannière "provisoire',
                    "explanation": "",
                    "size": 40,
                    "category": "bul",
                },
            ),
            (
                "bul_show_uevalid",
                {
                    "initvalue": 1,
                    "title": "Faire figurer les UE validées sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_mention",
                {
                    "initvalue": 0,
                    "title": "Faire figurer les mentions sur les bulletins et les PV",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_date_inscr",
                {
                    "initvalue": 1,
                    "title": "Faire figurer la date d'inscription sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_sig_left",
                {
                    "initvalue": 0,
                    "title": "Faire figurer le pied de page de gauche (ex.: nom du directeur) sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_show_sig_right",
                {
                    "initvalue": 0,
                    "title": "Faire figurer le pied de page de droite (ex.: nom du chef de département) sur les bulletins",
                    "input_type": "boolcheckbox",
                    "category": "bul",
                    "labels": ["non", "oui"],
                },
            ),
            (
                "bul_display_publication",
                {
                    "initvalue": 1,
                    "title": "Indique si les bulletins sont publiés",
                    "explanation": "décocher si vous n'avez pas de portail étudiant publiant les bulletins",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "bul",
                    "only_global": False,
                },
            ),
            # champs des bulletins PDF:
            (
                "bul_pdf_title",
                {
                    "initvalue": """<para fontSize="14" align="center">
                        <b>%(UnivName)s</b>
                        </para>
                        <para fontSize="16" align="center" spaceBefore="2mm">
                        <b>%(InstituteName)s</b>
                        </para>
                        <para fontSize="16" align="center" spaceBefore="4mm">
                        <b>RELEVÉ DE NOTES</b>
                        </para>

                        <para fontSize="15" spaceBefore="3mm">
                        %(nomprenom)s <b>%(demission)s</b>
                        </para>

                        <para fontSize="14" spaceBefore="3mm">
                        Formation: %(titre_num)s</para>
                        <para fontSize="14" spaceBefore="2mm">
                        Année scolaire: %(anneescolaire)s
                        </para>""",
                    "title": "Bulletins PDF: paragraphe de titre",
                    "explanation": "(balises interprétées, voir documentation)",
                    "input_type": "textarea",
                    "rows": 10,
                    "cols": 64,
                    "category": "bul",
                },
            ),
            (
                "bul_pdf_caption",
                {
                    "initvalue": """<para spaceBefore="5mm" fontSize="14"><i>%(situation)s</i></para>""",
                    "title": "Bulletins PDF: paragraphe sous table note",
                    "explanation": '(visible seulement si "Faire figurer les décision" est coché)',
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "bul",
                },
            ),
            (
                "bul_pdf_sig_left",
                {
                    "initvalue": """<para>La direction des études
                        <br/>
                        %(responsable)s
                        </para>
                        """,
                    "title": "Bulletins PDF: signature gauche",
                    "explanation": "(balises interprétées, voir documentation)",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "bul",
                },
            ),
            (
                "bul_pdf_sig_right",
                {
                    "initvalue": """<para>Le chef de département
                        <br/>
                        %(ChiefDeptName)s
                        </para>
                        """,
                    "title": "Bulletins PDF: signature droite",
                    "explanation": "(balises interprétées, voir documentation)",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 64,
                    "category": "bul",
                },
            ),
            (
                "bul_pdf_mod_colwidth",
                {
                    "initvalue": None,
                    "title": "Bulletins PDF: largeur col. modules",
                    "explanation": "en cm (vide ou 0 si auto)",
                    "type": "float",
                    "category": "bul",
                },
            ),
            (
                "bul_pdf_with_background",
                {
                    "initvalue": 0,
                    "title": "Mettre l'image de fond sur les bulletins",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "bul",
                },
            ),
            (
                "SCOLAR_FONT_BUL_FIELDS",
                {
                    "initvalue": "Times-Roman",
                    "title": "Police titres bulletins",
                    "explanation": "pour les pdf",
                    "size": 25,
                    "category": "bul",
                },
            ),
            # XXX A COMPLETER, voir sco_formsemestre_edit.py XXX
            # bul_mail
            (
                "email_copy_bulletins",
                {
                    "initvalue": "",
                    "title": "e-mail copie bulletins",
                    "size": 40,
                    "explanation": "adresse recevant une copie des bulletins envoyés aux étudiants",
                    "category": "bul_mail",
                },
            ),
            (
                "email_from_addr",
                {
                    "initvalue": "noreply@scodoc.example.com",
                    "title": "adresse mail origine",
                    "size": 40,
                    "explanation": "adresse expéditeur pour les envois par mails (bulletins)",
                    "category": "bul_mail",
                    "only_global": True,
                },
            ),
            (
                "bul_intro_mail",
                {
                    "initvalue": """%(nomprenom)s,\n\nvous trouverez ci-joint votre relevé de notes au format PDF.\nIl s\'agit d\'un relevé indicatif. Seule la version papier signée par le responsable pédagogique de l\'établissement prend valeur officielle.\n\nPour toute question sur ce document, contactez votre enseignant ou le directeur des études (ne pas répondre à ce message).\n\nCordialement,\nla scolarité du département %(dept)s.\n\nPS: si vous recevez ce message par erreur, merci de contacter %(webmaster)s""",
                    "input_type": "textarea",
                    "title": "Message d'accompagnement",
                    "explanation": "<tt>%(DeptName)s</tt> est remplacé par le nom du département, <tt>%(nomprenom)s</tt> par les noms et prénoms de l'étudiant, <tt>%(dept)s</tt> par le nom du département, et <tt>%(webmaster)s</tt> par l'adresse mail du Webmaster.",
                    "rows": 18,
                    "cols": 85,
                    "category": "bul_mail",
                },
            ),
            (
                "bul_mail_list_abs",
                {
                    "initvalue": 0,
                    "title": "Indiquer la liste des dates d'absences par mail",
                    "explanation": "dans le mail envoyant le bulletin de notes",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "bul_mail",
                },
            ),
            (
                "bul_mail_contact_addr",
                {
                    "initvalue": "l'administrateur",
                    "title": 'Adresse mail contact "webmaster"',
                    "explanation": 'apparait dans le mail accompagnant le bulletin, voir balise "webmaster" ci-dessus.',
                    "category": "bul_mail",
                    "size": 32,
                },
            ),
            (
                "bul_mail_allowed_for_all",
                {
                    "initvalue": 1,
                    "title": "Autoriser tous les utilisateurs à expédier des bulletins par mail",
                    "input_type": "boolcheckbox",
                    "category": "bul_mail",
                    "labels": ["non", "oui"],
                },
            ),
            # bul_margins
            (
                "left_margin",
                {
                    "initvalue": 0,
                    "size": 10,
                    "title": "Marge gauche",
                    "type": "float",
                    "category": "bul_margins",
                },
            ),
            (
                "top_margin",
                {
                    "initvalue": 0,
                    "size": 10,
                    "title": "Marge haute",
                    "type": "float",
                    "category": "bul_margins",
                },
            ),
            (
                "right_margin",
                {
                    "initvalue": 0,
                    "size": 10,
                    "title": "Marge droite",
                    "type": "float",
                    "category": "bul_margins",
                },
            ),
            (
                "bottom_margin",
                {
                    "initvalue": 0,
                    "size": 10,
                    "title": "Marge basse",
                    "type": "float",
                    "category": "bul_margins",
                },
            ),
            # Mise en page feuilles absences/trombinoscopes
            (
                "feuille_releve_abs_taille",
                {
                    "initvalue": "A3",
                    "input_type": "menu",
                    "labels": ["A3", "A4"],
                    "allowed_values": ["A3", "A4"],
                    "title": "Taille feuille relevé absences",
                    "explanation": "Dimensions du papier pour les feuilles de relevés d'absences hebdomadaire",
                    "category": "feuilles",
                },
            ),
            (
                "feuille_releve_abs_format",
                {
                    "initvalue": "Paysage",
                    "input_type": "menu",
                    "labels": ["Paysage", "Portrait"],
                    "allowed_values": ["Paysage", "Portrait"],
                    "title": "Format feuille relevé absences",
                    "explanation": "Format du papier pour les feuilles de relevés d'absences hebdomadaire",
                    "category": "feuilles",
                },
            ),
            (
                "feuille_releve_abs_samedi",
                {
                    "initvalue": 1,
                    "title": "Samedi travaillé",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "category": "feuilles",
                },
            ),
            (
                "feuille_releve_abs_AM",
                {
                    "initvalue": "2",
                    "title": "Créneaux cours matin",
                    "explanation": "Nombre de créneaux de cours le matin",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "feuilles",
                },
            ),
            (
                "feuille_releve_abs_PM",
                {
                    "initvalue": "3",
                    "title": "Créneaux cours après-midi",
                    "explanation": "Nombre de créneaux de cours l'après-midi",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "feuilles",
                },
            ),
            (
                "feuille_placement_emargement",
                {
                    "initvalue": "625",
                    "title": "Feuille d'émargement des contrôles - Signature étudiant",
                    "explanation": "Hauteur de l'espace pour signer",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "feuilles",
                },
            ),
            (
                "feuille_placement_positions",
                {
                    "initvalue": "45",
                    "title": "Feuille des places lors des contrôles",
                    "explanation": "Nombre maximum de lignes par colonne",
                    "size": 4,
                    "type": "int",
                    "convert_numbers": True,
                    "category": "feuilles",
                },
            ),
            # Feuille prepa jury
            (
                "prepa_jury_nip",
                {
                    "initvalue": 0,
                    "title": "Code NIP sur la feuille préparation jury",
                    "input_type": "boolcheckbox",
                    "category": "feuilles",
                    "labels": ["non", "oui"],
                    "only_global": True,
                },
            ),
            (
                "prepa_jury_ine",
                {
                    "initvalue": 0,
                    "title": "Code INE sur la feuille préparation jury",
                    "input_type": "boolcheckbox",
                    "category": "feuilles",
                    "labels": ["non", "oui"],
                    "only_global": True,
                },
            ),
            (
                "anonymous_lst_code",
                {
                    "initvalue": "NIP",
                    "input_type": "menu",
                    "labels": ["NIP", "INE"],
                    "allowed_values": ["NIP", "INE"],
                    "title": "Code pour listes anonymes",
                    "explanation": "à défaut, un code interne sera utilisé",
                    "category": "feuilles",
                    "only_global": True,
                },
            ),
            # Exports pour Moodle:
            (
                "moodle_csv_with_headerline",
                {
                    "initvalue": 0,
                    "title": "Inclure une ligne d'en-têtes dans les fichiers CSV pour Moodle",
                    "input_type": "boolcheckbox",
                    "labels": ["non", "oui"],
                    "only_global": True,
                    "category": "feuilles",
                },
            ),
            (
                "moodle_csv_separator",
                {
                    "initvalue": ",",
                    "title": "séparateur de colonnes dans les fichiers CSV pour Moodle",
                    "size": 2,
                    "only_global": True,
                    "category": "feuilles",
                },
            ),
            # Experimental: avis poursuite d'études
            (
                "NomResponsablePE",
                {
                    "initvalue": "",
                    "title": "Nom du responsable des poursuites d'études",
                    "size": 32,
                    "explanation": "pour les avis pdf de poursuite",
                    "category": "pe",
                },
            ),
            (
                "pe_avis_latex_tmpl",
                {
                    "title": "Template LaTeX des avis",
                    "initvalue": "",
                    "explanation": "préparez-le dans un éditeur de texte puis copier le contenu ici (en utf8). Sinon, le fichier un_avis.tex du serveur sera utilisé.",
                    "input_type": "textarea",
                    "rows": 4,
                    "cols": 80,
                    "category": "pe",
                },
            ),
            (
                "pe_avis_latex_footer",
                {
                    "title": "Code LaTeX en fin d'avis",
                    "initvalue": "",
                    "explanation": "",
                    "input_type": "textarea",
                    "rows": 5,
                    "cols": 80,
                    "category": "pe",
                },
            ),
            (
                "pe_tag_annotation_avis_latex",
                {
                    "title": "Tag désignant l'avis PE",
                    "initvalue": "PE&gt;",
                    "explanation": """ajoutez une annotation aux étudiants précédée du tag désigné ici pour qu'elle soit interprétée comme un avis de poursuites d'études et ajoutée aux avis LaTeX.""",
                    "size": 25,
                    "category": "pe",
                },
            ),
            # Lien avec logiciel emplois du temps
            (
                "edt_sem_ics_url",
                {
                    "title": "Lien EDT",
                    "initvalue": "",
                    "explanation": "URL du calendrier ics emploi du temps du semestre (template)",
                    "size": 80,
                    "category": "edt",
                },
            ),
            (
                "edt_groups2scodoc",
                {
                    "input_type": "textarea",
                    "initvalue": "",
                    "title": "Noms Groupes",
                    "explanation": "Transcodage: nom de groupe EDT ; non de groupe ScoDoc (sur plusieurs lignes)",
                    "rows": 8,
                    "cols": 16,
                    "category": "edt",
                },
            ),
            (
                "ImputationDept",
                {
                    "title": "Département d'imputation",
                    "initvalue": "",
                    "explanation": "préfixe id de session (optionnel, remplace nom département)",
                    "size": 10,
                    "category": "edt",
                },
            ),
        )

        self.prefs_name = set([x[0] for x in self.prefs_definition])
        self.prefs_only_global = set(
            [x[0] for x in self.prefs_definition if x[1].get("only_global", False)]
        )
        self.prefs_dict = dict(self.prefs_definition)

    def load(self):
        """Load all preferences from db"""
        log(f"loading preferences for dept_id={self.dept_id}")

        cnx = ndb.GetDBConnexion()
        preflist = self._editor.list(cnx, {"dept_id": self.dept_id})
        self.prefs = {None: {}}  # { formsemestre_id (or None) : { name : value } }
        self.default = {}  # { name : default_value }
        for p in preflist:
            if not p["formsemestre_id"] in self.prefs:
                self.prefs[p["formsemestre_id"]] = {}
            # Ignore les noms de préférences non utilisés dans le code:
            if p["name"] not in self.prefs_dict:
                continue

            # Convert types:
            if p["name"] in self.prefs_dict:
                _convert_pref_type(p, self.prefs_dict[p["name"]])

            self.prefs[p["formsemestre_id"]][p["name"]] = p["value"]

        # add defaults for missing prefs
        for pref in self.prefs_definition:
            name = pref[0]
            # search preferences in configuration file
            if name and name[0] != "_" and name not in self.prefs[None]:
                value = _get_pref_default_value_from_config(name, pref[1])
                self.default[name] = value
                self.prefs[None][name] = value
                log("creating missing preference for %s=%s" % (name, value))
                # add to db table
                self._editor.create(
                    cnx, {"dept_id": self.dept_id, "name": name, "value": value}
                )

    def get(self, formsemestre_id, name):
        """Returns preference value.
        when no value defined for this semestre, returns global value.
        """
        if formsemestre_id in self.prefs:
            return self.prefs[formsemestre_id].get(name, self.prefs[None][name])
        return self.prefs[None][name]

    def __contains__(self, item):
        return item in self.prefs[None]

    def __len__(self):
        return len(self.prefs[None])

    def is_global(self, formsemestre_id, name):
        "True if name if not defined for semestre"
        params = {
            "dept_id": self.dept_id,
            "name": name,
            "formsemestre_id": formsemestre_id,
        }
        cnx = ndb.GetDBConnexion()
        plist = self._editor.list(cnx, params)
        return len(plist) == 0

    def save(self, formsemestre_id=None, name=None):
        """Write one or all (if name is None) values to db"""
        modif = False
        cnx = ndb.GetDBConnexion()
        if name is None:
            names = list(self.prefs[formsemestre_id].keys())
        else:
            names = [name]
        for name in names:
            value = self.prefs[formsemestre_id][name]
            if self.prefs_dict[name].get("input_type", None) == "boolcheckbox":
                # repasse les booleens en chaines "0":"1"
                value = "1" if value else "0"
            # existe deja ?
            pdb = self._editor.list(
                cnx,
                args={
                    "dept_id": self.dept_id,
                    "formsemestre_id": formsemestre_id,
                    "name": name,
                },
            )
            if len(pdb) > 1:
                # suppress buggy duplicates (may come from corrupted database for ice ages)
                log(
                    f"**oups** detected duplicated preference !\n({self.dept_id}, {formsemestre_id}, {name}, {value})"
                )
                for obj in pdb[1:]:
                    self._editor.delete(cnx, obj["id"])
                pdb = [pdb[0]]

            if not pdb:
                # crée préférence
                log("create pref sem=%s %s=%s" % (formsemestre_id, name, value))
                self._editor.create(
                    cnx,
                    {
                        "dept_id": self.dept_id,
                        "name": name,
                        "value": value,
                        "formsemestre_id": formsemestre_id,
                    },
                )
                modif = True
            else:
                # edit existing value
                existing_value = pdb[0]["value"]  # old stored value
                if (
                    (existing_value != value)
                    and (existing_value != str(value))
                    and (existing_value or str(value))
                ):
                    self._editor.edit(
                        cnx,
                        {
                            "pref_id": pdb[0]["pref_id"],
                            "formsemestre_id": formsemestre_id,
                            "name": name,
                            "value": value,
                        },
                    )
                    modif = True
                    log("save pref sem=%s %s=%s" % (formsemestre_id, name, value))

        # les preferences peuvent affecter les PDF cachés et les notes calculées:
        if modif:
            sco_cache.invalidate_formsemestre()

    def set(self, formsemestre_id, name, value):
        if not name or name[0] == "_" or name not in self.prefs_name:
            raise ValueError("invalid preference name: %s" % name)
        if formsemestre_id and name in self.prefs_only_global:
            raise ValueError("pref %s is always defined globaly")
        if not formsemestre_id in self.prefs:
            self.prefs[formsemestre_id] = {}
        self.prefs[formsemestre_id][name] = value
        self.save(formsemestre_id, name)  # immediately write back to db

    def delete(self, formsemestre_id, name):
        if not formsemestre_id:
            raise ScoException()

        if formsemestre_id in self.prefs and name in self.prefs[formsemestre_id]:
            del self.prefs[formsemestre_id][name]
        cnx = ndb.GetDBConnexion()
        pdb = self._editor.list(
            cnx, args={"formsemestre_id": formsemestre_id, "name": name}
        )
        if pdb:
            log("deleting pref sem=%s %s" % (formsemestre_id, name))
            assert pdb[0]["dept_id"] == self.dept_id
            self._editor.delete(cnx, pdb[0]["pref_id"])
            sco_cache.invalidate_formsemestre()  # > modif preferences

    def edit(self):
        """HTML dialog: edit global preferences"""
        from app.scodoc import html_sco_header

        self.load()
        H = [
            html_sco_header.sco_header(page_title="Préférences"),
            "<h2>Préférences globales pour %s</h2>" % scu.ScoURL(),
            f"""<p><a href="{url_for("scolar.config_logos", scodoc_dept=g.scodoc_dept)
            }">modification des logos du département (pour documents pdf)</a></p>"""
            if current_user.is_administrator()
            else "",
            """<p class="help">Ces paramètres s'appliquent par défaut à tous les semestres, sauf si ceux-ci définissent des valeurs spécifiques.</p>
              <p class="msg">Attention: cliquez sur "Enregistrer les modifications" en bas de page pour appliquer vos changements !</p>
              """,
        ]
        form = self.build_tf_form()
        tf = TrivialFormulator(
            request.base_url,
            scu.get_request_args(),
            form,
            initvalues=self.prefs[None],
            submitlabel="Enregistrer les modifications",
        )
        if tf[0] == 0:
            return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
        elif tf[0] == -1:
            return flask.redirect(scu.ScoURL())  # cancel
        else:
            for pref in self.prefs_definition:
                self.prefs[None][pref[0]] = tf[2][pref[0]]
            self.save()
            return flask.redirect(scu.ScoURL() + "?head_message=Préférences modifiées")

    def build_tf_form(self, categories=[], formsemestre_id=None):
        """Build list of elements for TrivialFormulator.
        If formsemestre_id is not specified, edit global prefs.
        """
        form = []
        for cat, cat_descr in PREF_CATEGORIES:
            if categories and cat not in categories:
                continue  # skip this category
            #
            cat_elems = []
            for pref_name, pref in self.prefs_definition:
                if pref["category"] == cat:
                    if pref.get("only_global", False) and formsemestre_id:
                        continue  # saute les prefs seulement globales
                    descr = pref.copy()
                    descr["comment"] = descr.get("explanation", None)
                    if "explanation" in descr:
                        del descr["explanation"]
                    if formsemestre_id:
                        descr["explanation"] = (
                            """ou <span class="spanlink" onclick="set_global_pref(this, '%s');">utiliser paramètre global</span>"""
                            % pref_name
                        )
                    # if descr.get('only_global',False):
                    #    # pas modifiable, donne juste la valeur courante
                    #    descr['readonly'] = True
                    #    descr['explanation'] = '(valeur globale, non modifiable)'
                    # elif
                    if formsemestre_id and self.is_global(formsemestre_id, pref_name):
                        # valeur actuelle globale (ou vient d'etre supprimee localement):
                        # montre la valeur et menus pour la rendre locale
                        descr["readonly"] = True
                        menu_global = (
                            """<select class="tf-selglobal" onchange="sel_global(this, '%s');">
                            <option value="">Valeur définie globalement</option>
                            <option value="create">Spécifier valeur pour ce semestre seulement</option>
                        </select>
                        """
                            % pref_name
                        )
                        #                         <option value="changeglobal">Changer paramètres globaux</option>
                        descr["explanation"] = menu_global

                    cat_elems.append((pref_name, descr))
            if cat_elems:
                # category titles:
                title = cat_descr.get("title", None)
                if title:
                    form.append(
                        (
                            "sep_%s" % cat,
                            {"input_type": "separator", "title": "<h3>%s</h3>" % title},
                        )
                    )
                subtitle = cat_descr.get("subtitle", None)
                if subtitle:
                    form.append(
                        (
                            "sepsub_%s" % cat,
                            {
                                "input_type": "separator",
                                "title": '<p class="help">%s</p>' % subtitle,
                            },
                        )
                    )
                form.extend(cat_elems)
        return form


class SemPreferences(object):
    """Preferences for a formsemestre"""

    def __init__(self, formsemestre_id=None):
        self.formsemestre_id = formsemestre_id
        self.base_prefs = get_base_preferences()

    def __getitem__(self, name):
        return self.base_prefs.get(self.formsemestre_id, name)

    def __contains__(self, item):
        "check if item is in (global) preferences"
        return item in self.base_prefs

    def get(self, name, defaultvalue=None):
        # utilisé seulement par TF
        try:
            return self[name]  # ignore supplied default value
        except:
            return defaultvalue

    def is_global(self, name):
        "True if preference defined for all semestres"
        return self.base_prefs.is_global(self.formsemestre_id, name)

    # The dialog
    def edit(self, categories=[]):
        """Dialog to edit semestre preferences in given categories"""
        from app.scodoc import html_sco_header
        from app.scodoc import sco_formsemestre

        if not self.formsemestre_id:
            raise ScoValueError(
                "sem_preferences.edit doit etre appele sur un semestre !"
            )  # a bug !
        sem = sco_formsemestre.get_formsemestre(self.formsemestre_id)
        H = [
            html_sco_header.html_sem_header("Préférences du semestre", sem),
            """
<p class="help">Les paramètres définis ici ne s'appliqueront qu'à ce semestre.</p>
<p class="msg">Attention: cliquez sur "Enregistrer les modifications" en bas de page pour appliquer vos changements !</p>
<script type="text/javascript">
function sel_global(el, pref_name) {
     var tf = document.getElementById("tf");
     if (el.value == 'create') {
        tf.create_local.value = pref_name;
        tf.destination.value = 'again';
        tf.submit();
     } else if (el.value == 'changeglobal') {
        tf.destination.value = 'global';
        tf.submit();
     }
}
function set_global_pref(el, pref_name) {
     var tf = document.getElementById("tf");
     tf.suppress.value = pref_name;
     tf.destination.value = 'again';
     var f = tf[pref_name];
     if (f) {
       f.disabled = true;
     } else {
       f =tf[pref_name+':list'];
       if (f) {
         f.disabled = true;
       }
     }
    tf.submit();
}
</script>
""",
        ]
        # build the form:
        form = self.base_prefs.build_tf_form(
            categories=categories, formsemestre_id=self.formsemestre_id
        )
        form.append(("suppress", {"input_type": "hidden"}))
        form.append(("create_local", {"input_type": "hidden"}))
        form.append(("destination", {"input_type": "hidden"}))
        form.append(("formsemestre_id", {"input_type": "hidden"}))
        tf = TrivialFormulator(
            request.base_url,
            scu.get_request_args(),
            form,
            initvalues=self,
            cssclass="sco_pref",
            submitlabel="Enregistrer les modifications",
        )
        dest_url = (
            scu.NotesURL()
            + "/formsemestre_status?formsemestre_id=%s" % self.formsemestre_id
        )
        if tf[0] == 0:
            return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
        elif tf[0] == -1:
            return flask.redirect(dest_url + "&head_message=Annulé")  # cancel
        else:
            # Supprime pref locale du semestre (retour à la valeur globale)
            if tf[2]["suppress"]:
                self.base_prefs.delete(self.formsemestre_id, tf[2]["suppress"])
            # Cree pref local (copie valeur globale)
            if tf[2]["create_local"]:
                cur_value = self[tf[2]["create_local"]]
                self.base_prefs.set(
                    self.formsemestre_id, tf[2]["create_local"], cur_value
                )
            # Modifie valeurs:
            for (pref_name, descr) in self.base_prefs.prefs_definition:
                if (
                    pref_name in tf[2]
                    and not descr.get("only_global", False)
                    and pref_name != tf[2]["suppress"]
                ):
                    form_value = tf[2][pref_name]
                    cur_value = self[pref_name]
                    if cur_value is None:
                        cur_value = ""
                    else:
                        cur_value = str(cur_value)
                    if cur_value != str(form_value):
                        # log('cur_value=%s (type %s), form_value=%s (type %s)' % (cur_value,type(cur_value),form_value, type(form_value)))
                        self.base_prefs.set(self.formsemestre_id, pref_name, form_value)

            # destination:
            # global: change pref and redirect to global params
            # again: change prefs and redisplay this dialog
            # done: change prefs and redirect to semestre status
            destination = tf[2]["destination"]
            if destination == "done" or destination == "":
                return flask.redirect(dest_url + "&head_message=Préférences modifiées")
            elif destination == "again":
                return flask.redirect(
                    request.base_url + "?formsemestre_id=" + str(self.formsemestre_id)
                )
            elif destination == "global":
                return flask.redirect(scu.ScoURL() + "/edit_preferences")


#
def doc_preferences():
    """Liste les preferences en MarkDown, pour la documentation"""
    L = []
    for cat, cat_descr in PREF_CATEGORIES:
        L.append([""])
        L.append(["## " + cat_descr.get("title", "")])
        L.append([""])
        L.append(["Nom", "&nbsp;", "&nbsp;"])
        L.append(["----", "----", "----"])
        for pref_name, pref in get_base_preferences().prefs_definition:
            if pref["category"] == cat:
                L.append(
                    ["`" + pref_name + "`", pref["title"], pref.get("explanation", "")]
                )

    return "\n".join([" | ".join(x) for x in L])
