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

""" Accès donnees etudiants
"""

# Ancien module "scolars"
import os
import time
from operator import itemgetter

from flask import url_for, g, request
from flask_mail import Message

from app import email
from app import log

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.sco_exceptions import ScoGenError, ScoValueError
from app.scodoc import safehtml
from app.scodoc import sco_preferences
from app.scodoc.scolog import logdb
from app.scodoc.TrivialFormulator import TrivialFormulator

MONTH_NAMES_ABBREV = [
    "Jan ",
    "Fév ",
    "Mars",
    "Avr ",
    "Mai ",
    "Juin",
    "Jul ",
    "Août",
    "Sept",
    "Oct ",
    "Nov ",
    "Déc ",
]

MONTH_NAMES = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def format_etud_ident(etud):
    """Format identite de l'étudiant (modifié en place)
    nom, prénom et formes associees
    """
    etud["nom"] = format_nom(etud["nom"])
    if "nom_usuel" in etud:
        etud["nom_usuel"] = format_nom(etud["nom_usuel"])
    else:
        etud["nom_usuel"] = ""
    etud["prenom"] = format_prenom(etud["prenom"])
    etud["civilite_str"] = format_civilite(etud["civilite"])
    # Nom à afficher:
    if etud["nom_usuel"]:
        etud["nom_disp"] = etud["nom_usuel"]
        if etud["nom"]:
            etud["nom_disp"] += " (" + etud["nom"] + ")"
    else:
        etud["nom_disp"] = etud["nom"]

    etud["nomprenom"] = format_nomprenom(etud)  # M. Pierre DUPONT
    if etud["civilite"] == "M":
        etud["ne"] = ""
    elif etud["civilite"] == "F":
        etud["ne"] = "e"
    else:  # 'X'
        etud["ne"] = "(e)"
    # Mail à utiliser pour les envois vers l'étudiant:
    # choix qui pourrait être controé par une preference
    # ici priorité au mail institutionnel:
    etud["email_default"] = etud.get("email", "") or etud.get("emailperso", "")


def force_uppercase(s):
    return s.upper() if s else s


def format_nomprenom(etud, reverse=False):
    """Formatte civilité/nom/prenom pour affichages: "M. Pierre Dupont"
    Si reverse, "Dupont Pierre", sans civilité.
    """
    nom = etud.get("nom_disp", "") or etud.get("nom_usuel", "") or etud["nom"]
    prenom = format_prenom(etud["prenom"])
    civilite = format_civilite(etud["civilite"])
    if reverse:
        fs = [nom, prenom]
    else:
        fs = [civilite, prenom, nom]
    return " ".join([x for x in fs if x])


def format_prenom(s):
    "Formatte prenom etudiant pour affichage"
    if not s:
        return ""
    frags = s.split()
    r = []
    for frag in frags:
        fs = frag.split("-")
        r.append("-".join([x.lower().capitalize() for x in fs]))
    return " ".join(r)


def format_nom(s, uppercase=True):
    if not s:
        return ""
    if uppercase:
        return s.upper()
    else:
        return format_prenom(s)


def input_civilite(s):
    """Converts external representation of civilite to internal:
    'M', 'F', or 'X' (and nothing else).
    Raises ScoValueError if conversion fails.
    """
    s = s.upper().strip()
    if s in ("M", "M.", "MR", "H"):
        return "M"
    elif s in ("F", "MLLE", "MLLE.", "MELLE", "MME"):
        return "F"
    elif s == "X" or not s:
        return "X"
    raise ScoValueError("valeur invalide pour la civilité: %s" % s)


def format_civilite(civilite):
    """returns 'M.' ou 'Mme' ou '' (pour le genre neutre,
    personne ne souhaitant pas d'affichage).
    Raises ScoValueError if conversion fails.
    """
    try:
        return {
            "M": "M.",
            "F": "Mme",
            "X": "",
        }[civilite]
    except KeyError:
        raise ScoValueError("valeur invalide pour la civilité: %s" % civilite)


def format_lycee(nomlycee):
    nomlycee = nomlycee.strip()
    s = nomlycee.lower()
    if s[:5] == "lycee" or s[:5] == "lycée":
        return nomlycee[5:]
    else:
        return nomlycee


def format_telephone(n):
    if n is None:
        return ""
    if len(n) < 7:
        return n
    else:
        n = n.replace(" ", "").replace(".", "")
        i = 0
        r = ""
        j = len(n) - 1
        while j >= 0:
            r = n[j] + r
            if i % 2 == 1 and j != 0:
                r = " " + r
            i += 1
            j -= 1
        if len(r) == 13 and r[0] != "0":
            r = "0" + r
        return r


def format_pays(s):
    "laisse le pays seulement si != FRANCE"
    if s.upper() != "FRANCE":
        return s
    else:
        return ""


PIVOT_YEAR = 70


def pivot_year(y):
    if y == "" or y is None:
        return None
    y = int(round(float(y)))
    if y >= 0 and y < 100:
        if y < PIVOT_YEAR:
            y = y + 2000
        else:
            y = y + 1900
    return y


_identiteEditor = ndb.EditableTable(
    "identite",
    "etudid",
    (
        "etudid",
        "nom",
        "nom_usuel",
        "prenom",
        "civilite",  # 'M", "F", or "X"
        "date_naissance",
        "lieu_naissance",
        "dept_naissance",
        "nationalite",
        "statut",
        "boursier",
        "foto",
        "photo_filename",
        "code_ine",
        "code_nip",
    ),
    filter_dept=True,
    sortkey="nom",
    input_formators={
        "nom": force_uppercase,
        "prenom": force_uppercase,
        "civilite": input_civilite,
        "date_naissance": ndb.DateDMYtoISO,
        "boursier": bool,
    },
    output_formators={"date_naissance": ndb.DateISOtoDMY},
    convert_null_outputs_to_empty=True,
    # allow_set_id=True,  # car on specifie le code Apogee a la creation #sco8
)

identite_delete = _identiteEditor.delete


def identite_list(cnx, *a, **kw):
    """List, adding on the fly 'annee_naissance' and 'civilite_str' (M., Mme, "")."""
    objs = _identiteEditor.list(cnx, *a, **kw)
    for o in objs:
        if o["date_naissance"]:
            o["annee_naissance"] = int(o["date_naissance"].split("/")[2])
        else:
            o["annee_naissance"] = o["date_naissance"]
        o["civilite_str"] = format_civilite(o["civilite"])
    return objs


def identite_edit_nocheck(cnx, args):
    """Modifie les champs mentionnes dans args, sans verification ni notification."""
    _identiteEditor.edit(cnx, args)


def check_nom_prenom(cnx, nom="", prenom="", etudid=None):
    """Check if nom and prenom are valid.
    Also check for duplicates (homonyms), excluding etudid :
    in general, homonyms are allowed, but it may be useful to generate a warning.
    Returns:
    True | False, NbHomonyms
    """
    if not nom or (not prenom and not scu.CONFIG.ALLOW_NULL_PRENOM):
        return False, 0
    nom = nom.lower().strip()
    if prenom:
        prenom = prenom.lower().strip()
    # Don't allow some special cars (eg used in sql regexps)
    if scu.FORBIDDEN_CHARS_EXP.search(nom) or scu.FORBIDDEN_CHARS_EXP.search(prenom):
        return False, 0
    # Now count homonyms (dans tous les départements):
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = """SELECT id 
    FROM identite 
    WHERE lower(nom) ~ %(nom)s 
    and lower(prenom) ~ %(prenom)s
    """
    if etudid:
        req += "  and id <> %(etudid)s"
    cursor.execute(req, {"nom": nom, "prenom": prenom, "etudid": etudid})
    res = cursor.dictfetchall()
    return True, len(res)


def _check_duplicate_code(cnx, args, code_name, disable_notify=False, edit=True):
    etudid = args.get("etudid", None)
    if args.get(code_name, None):
        etuds = identite_list(cnx, {code_name: str(args[code_name])})
        # log('etuds=%s'%etuds)
        nb_max = 0
        if edit:
            nb_max = 1
        if len(etuds) > nb_max:
            listh = []  # liste des doubles
            for e in etuds:
                listh.append(
                    """Autre étudiant: <a href="%s">"""
                    % url_for(
                        "scolar.ficheEtud",
                        scodoc_dept=g.scodoc_dept,
                        etudid=e["etudid"],
                    )
                    + """%(nom)s %(prenom)s</a>""" % e
                )
            if etudid:
                OK = "retour à la fiche étudiant"
                dest_endpoint = "scolar.ficheEtud"
                parameters = {"etudid": etudid}
            else:
                if "tf_submitted" in args:
                    del args["tf_submitted"]
                    OK = "Continuer"
                    dest_endpoint = "scolar.etudident_create_form"
                    parameters = args
                else:
                    OK = "Annuler"
                    dest_endpoint = "notes.index_html"
                    parameters = {}
            if not disable_notify:
                err_page = f"""<h3><h3>Code étudiant ({code_name}) dupliqué !</h3>
                <p class="help">Le {code_name} {args[code_name]} est déjà utilisé: un seul étudiant peut avoir 
                ce code. Vérifier votre valeur ou supprimer l'autre étudiant avec cette valeur.
                </p>
                <ul><li>
                { '</li><li>'.join(listh) }
                </li></ul>
                <p>
                <a href="{ url_for(dest_endpoint, scodoc_dept=g.scodoc_dept, **parameters) }
                ">{OK}</a>
                </p>
                """
            else:
                err_page = f"""<h3>Code étudiant ({code_name}) dupliqué !</h3>"""
            log("*** error: code %s duplique: %s" % (code_name, args[code_name]))
            raise ScoGenError(err_page)


def _check_civilite(args):
    civilite = args.get("civilite", "X") or "X"
    args["civilite"] = input_civilite(civilite)  # TODO: A faire valider


def identite_edit(cnx, args, disable_notify=False):
    """Modifie l'identite d'un étudiant.
    Si pref notification et difference, envoie message notification, sauf si disable_notify
    """
    _check_duplicate_code(
        cnx, args, "code_nip", disable_notify=disable_notify, edit=True
    )
    _check_duplicate_code(
        cnx, args, "code_ine", disable_notify=disable_notify, edit=True
    )
    notify_to = None
    if not disable_notify:
        try:
            notify_to = sco_preferences.get_preference("notify_etud_changes_to")
        except:
            pass

    if notify_to:
        # etat AVANT edition pour envoyer diffs
        before = identite_list(cnx, {"etudid": args["etudid"]})[0]

    identite_edit_nocheck(cnx, args)

    # Notification du changement par e-mail:
    if notify_to:
        etud = get_etud_info(etudid=args["etudid"], filled=True)[0]
        after = identite_list(cnx, {"etudid": args["etudid"]})[0]
        notify_etud_change(
            notify_to,
            etud,
            before,
            after,
            "Modification identite %(nomprenom)s" % etud,
        )


def identite_create(cnx, args):
    "check unique etudid, then create"
    _check_duplicate_code(cnx, args, "code_nip", edit=False)
    _check_duplicate_code(cnx, args, "code_ine", edit=False)
    _check_civilite(args)

    if "etudid" in args:
        etudid = args["etudid"]
        r = identite_list(cnx, {"etudid": etudid})
        if r:
            raise ScoValueError(
                "Code identifiant (etudid) déjà utilisé ! (%s)" % etudid
            )
    return _identiteEditor.create(cnx, args)


def notify_etud_change(email_addr, etud, before, after, subject):
    """Send email notifying changes to etud
    before and after are two dicts, with values before and after the change.
    """
    txt = [
        "Code NIP:" + etud["code_nip"],
        "Civilité: " + etud["civilite_str"],
        "Nom: " + etud["nom"],
        "Prénom: " + etud["prenom"],
        "Etudid: " + str(etud["etudid"]),
        "\n",
        "Changements effectués:",
    ]
    n = 0
    for key in after.keys():
        if before[key] != after[key]:
            txt.append('%s: %s (auparavant: "%s")' % (key, after[key], before[key]))
            n += 1
    if not n:
        return  # pas de changements
    txt = "\n".join(txt)
    # build mail
    log("notify_etud_change: sending notification to %s" % email_addr)
    log("notify_etud_change: subject: %s" % subject)
    log(txt)
    email.send_email(
        subject, sco_preferences.get_preference("email_from_addr"), [email_addr], txt
    )
    return txt


# --------
# Note: la table adresse n'est pas dans dans la table "identite"
#       car on prevoit plusieurs adresses par etudiant (ie domicile, entreprise)

_adresseEditor = ndb.EditableTable(
    "adresse",
    "adresse_id",
    (
        "adresse_id",
        "etudid",
        "email",
        "emailperso",
        "domicile",
        "codepostaldomicile",
        "villedomicile",
        "paysdomicile",
        "telephone",
        "telephonemobile",
        "fax",
        "typeadresse",
        "entreprise_id",
        "description",
    ),
    convert_null_outputs_to_empty=True,
)

adresse_create = _adresseEditor.create
adresse_delete = _adresseEditor.delete
adresse_list = _adresseEditor.list


def adresse_edit(cnx, args, disable_notify=False):
    """Modifie l'adresse d'un étudiant.
    Si pref notification et difference, envoie message notification, sauf si disable_notify
    """
    notify_to = None
    if not disable_notify:
        try:
            notify_to = sco_preferences.get_preference("notify_etud_changes_to")
        except:
            pass
    if notify_to:
        # etat AVANT edition pour envoyer diffs
        before = adresse_list(cnx, {"etudid": args["etudid"]})[0]

    _adresseEditor.edit(cnx, args)

    # Notification du changement par e-mail:
    if notify_to:
        etud = get_etud_info(etudid=args["etudid"], filled=True)[0]
        after = adresse_list(cnx, {"etudid": args["etudid"]})[0]
        notify_etud_change(
            notify_to,
            etud,
            before,
            after,
            "Modification adresse %(nomprenom)s" % etud,
        )


def getEmail(cnx, etudid):
    "get email institutionnel etudiant (si plusieurs adresses, prend le premier non null"
    adrs = adresse_list(cnx, {"etudid": etudid})
    for adr in adrs:
        if adr["email"]:
            return adr["email"]
    return ""


# ---------
_admissionEditor = ndb.EditableTable(
    "admissions",
    "adm_id",
    (
        "adm_id",
        "etudid",
        "annee",
        "bac",
        "specialite",
        "annee_bac",
        "math",
        "physique",
        "anglais",
        "francais",
        "rang",
        "qualite",
        "rapporteur",
        "decision",
        "score",
        "classement",
        "apb_groupe",
        "apb_classement_gr",
        "commentaire",
        "nomlycee",
        "villelycee",
        "codepostallycee",
        "codelycee",
        "type_admission",
        "boursier_prec",
    ),
    input_formators={
        "annee": pivot_year,
        "bac": force_uppercase,
        "specialite": force_uppercase,
        "annee_bac": pivot_year,
        "classement": ndb.int_null_is_null,
        "apb_classement_gr": ndb.int_null_is_null,
        "boursier_prec": bool,
    },
    output_formators={"type_admission": lambda x: x or scu.TYPE_ADMISSION_DEFAULT},
    convert_null_outputs_to_empty=True,
)

admission_create = _admissionEditor.create
admission_delete = _admissionEditor.delete
admission_list = _admissionEditor.list
admission_edit = _admissionEditor.edit

# Edition simultanee de identite et admission
class EtudIdentEditor(object):
    def create(self, cnx, args):
        etudid = identite_create(cnx, args)
        args["etudid"] = etudid
        admission_create(cnx, args)
        return etudid

    def list(self, *args, **kw):
        R = identite_list(*args, **kw)
        Ra = admission_list(*args, **kw)
        # print len(R), len(Ra)
        # merge: add admission fields to identite
        A = {}
        for r in Ra:
            A[r["etudid"]] = r
        res = []
        for i in R:
            res.append(i)
            if i["etudid"] in A:
                # merge
                res[-1].update(A[i["etudid"]])
            else:  # pas d'etudiant trouve
                # print "*** pas d'info admission pour %s" % str(i)
                void_adm = {
                    k: None
                    for k in _admissionEditor.dbfields
                    if k != "etudid" and k != "adm_id"
                }
                res[-1].update(void_adm)
        # tri par nom
        res.sort(key=itemgetter("nom", "prenom"))
        return res

    def edit(self, cnx, args, disable_notify=False):
        identite_edit(cnx, args, disable_notify=disable_notify)
        if "adm_id" in args:  # safety net
            admission_edit(cnx, args)


_etudidentEditor = EtudIdentEditor()
etudident_list = _etudidentEditor.list
etudident_edit = _etudidentEditor.edit
etudident_create = _etudidentEditor.create


def make_etud_args(etudid=None, code_nip=None, use_request=True, raise_exc=True):
    """forme args dict pour requete recherche etudiant
    On peut specifier etudid
    ou bien (si use_request) cherche dans la requete http: etudid, code_nip, code_ine
    (dans cet ordre).
    """
    args = None
    if etudid:
        args = {"etudid": etudid}
    elif code_nip:
        args = {"code_nip": code_nip}
    elif use_request:  # use form from current request (Flask global)
        if request.method == "POST":
            vals = request.form
        elif request.method == "GET":
            vals = request.args
        else:
            vals = {}
        if "etudid" in vals:
            args = {"etudid": int(vals["etudid"])}
        elif "code_nip" in vals:
            args = {"code_nip": str(vals["code_nip"])}
        elif "code_ine" in vals:
            args = {"code_ine": str(vals["code_ine"])}
    if not args and raise_exc:
        raise ValueError("getEtudInfo: no parameter !")
    return args


def log_unknown_etud():
    """Log request: cas ou getEtudInfo n'a pas ramene de resultat"""
    etud_args = make_etud_args(raise_exc=False)
    log(f"unknown student: args={etud_args}")


def get_etud_info(etudid=False, code_nip=False, filled=False) -> list:
    """infos sur un etudiant (API). If not found, returns empty list.
    On peut specifier etudid ou code_nip
    ou bien cherche dans les argumenst de la requête courante:
     etudid, code_nip, code_ine (dans cet ordre).
    """
    if etudid is None:
        return []
    cnx = ndb.GetDBConnexion()
    args = make_etud_args(etudid=etudid, code_nip=code_nip)
    etud = etudident_list(cnx, args=args)

    if filled:
        fill_etuds_info(etud)
    return etud


# Optim par cache local, utilité non prouvée mais
# on s'oriente vers un cahce persistent dans Redis ou bien l'utilisation de NT
# def get_etud_info_filled_by_etudid(etudid, cnx=None) -> dict:
#     """Infos sur un étudiant, avec cache local à la requête"""
#     if etudid in g.stored_etud_info:
#         return g.stored_etud_info[etudid]
#     cnx = cnx or ndb.GetDBConnexion()
#     etud = etudident_list(cnx, args={"etudid": etudid})
#     fill_etuds_info(etud)
#     g.stored_etud_info[etudid] = etud[0]
#     return etud[0]


def create_etud(cnx, args={}):
    """Creation d'un étudiant. génère aussi évenement et "news".

    Args:
        args: dict avec les attributs de l'étudiant

    Returns:
        etud, l'étudiant créé.
    """
    from app.scodoc import sco_news

    # creation d'un etudiant
    etudid = etudident_create(cnx, args)
    # crée une adresse vide (chaque etudiant doit etre dans la table "adresse" !)
    _ = adresse_create(
        cnx,
        {
            "etudid": etudid,
            "typeadresse": "domicile",
            "description": "(creation individuelle)",
        },
    )

    # event
    scolar_events_create(
        cnx,
        args={
            "etudid": etudid,
            "event_date": time.strftime("%d/%m/%Y"),
            "formsemestre_id": None,
            "event_type": "CREATION",
        },
    )
    # log
    logdb(
        cnx,
        method="etudident_edit_form",
        etudid=etudid,
        msg="creation initiale",
    )
    etud = etudident_list(cnx, {"etudid": etudid})[0]
    fill_etuds_info([etud])
    etud["url"] = url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid)
    sco_news.add(
        typ=sco_news.NEWS_INSCR,
        object=None,  # pas d'object pour ne montrer qu'un etudiant
        text='Nouvel étudiant <a href="%(url)s">%(nomprenom)s</a>' % etud,
        url=etud["url"],
    )
    return etud


# ---------- "EVENTS"
_scolar_eventsEditor = ndb.EditableTable(
    "scolar_events",
    "event_id",
    (
        "event_id",
        "etudid",
        "event_date",
        "formsemestre_id",
        "ue_id",
        "event_type",
        "comp_formsemestre_id",
    ),
    sortkey="event_date",
    convert_null_outputs_to_empty=True,
    output_formators={"event_date": ndb.DateISOtoDMY},
    input_formators={"event_date": ndb.DateDMYtoISO},
)

# scolar_events_create = _scolar_eventsEditor.create
scolar_events_delete = _scolar_eventsEditor.delete
scolar_events_list = _scolar_eventsEditor.list
scolar_events_edit = _scolar_eventsEditor.edit


def scolar_events_create(cnx, args):
    # several "events" may share the same values
    _scolar_eventsEditor.create(cnx, args)


# --------
_etud_annotationsEditor = ndb.EditableTable(
    "etud_annotations",
    "id",
    (
        "id",
        "date",
        "etudid",
        "author",
        "comment",
        "author",
    ),
    sortkey="date desc",
    convert_null_outputs_to_empty=True,
    output_formators={"comment": safehtml.html_to_safe_html, "date": ndb.DateISOtoDMY},
)

etud_annotations_create = _etud_annotationsEditor.create
etud_annotations_delete = _etud_annotationsEditor.delete
etud_annotations_list = _etud_annotationsEditor.list
etud_annotations_edit = _etud_annotationsEditor.edit


def add_annotations_to_etud_list(etuds):
    """Add key 'annotations' describing annotations of etuds
    (used to list all annotations of a group)
    """
    cnx = ndb.GetDBConnexion()
    for etud in etuds:
        l = []
        for a in etud_annotations_list(cnx, args={"etudid": etud["etudid"]}):
            l.append("%(comment)s (%(date)s)" % a)
        etud["annotations_str"] = ", ".join(l)


# -------- APPRECIATIONS (sur bulletins) -------------------
# Les appreciations sont dans la table postgres notes_appreciations
_appreciationsEditor = ndb.EditableTable(
    "notes_appreciations",
    "id",
    (
        "id",
        "date",
        "etudid",
        "formsemestre_id",
        "author",
        "comment",
        "author",
    ),
    sortkey="date desc",
    convert_null_outputs_to_empty=True,
    output_formators={"comment": safehtml.html_to_safe_html, "date": ndb.DateISOtoDMY},
)

appreciations_create = _appreciationsEditor.create
appreciations_delete = _appreciationsEditor.delete
appreciations_list = _appreciationsEditor.list
appreciations_edit = _appreciationsEditor.edit


# -------- Noms des Lycées à partir du code
def read_etablissements():
    filename = os.path.join(scu.SCO_TOOLS_DIR, scu.CONFIG.ETABL_FILENAME)
    log("reading %s" % filename)
    with open(filename) as f:
        L = [x[:-1].split(";") for x in f]
    E = {}
    for l in L[1:]:
        E[l[0]] = {
            "name": l[1],
            "address": l[2],
            "codepostal": l[3],
            "commune": l[4],
            "position": l[5] + "," + l[6],
        }
    return E


ETABLISSEMENTS = None


def get_etablissements():
    global ETABLISSEMENTS
    if ETABLISSEMENTS is None:
        ETABLISSEMENTS = read_etablissements()
    return ETABLISSEMENTS


def get_lycee_infos(codelycee):
    E = get_etablissements()
    return E.get(codelycee, None)


def format_lycee_from_code(codelycee):
    "Description lycee à partir du code"
    E = get_etablissements()
    if codelycee in E:
        e = E[codelycee]
        nomlycee = e["name"]
        return "%s (%s)" % (nomlycee, e["commune"])
    else:
        return "%s (établissement inconnu)" % codelycee


def etud_add_lycee_infos(etud):
    """Si codelycee est renseigné, ajout les champs au dict"""
    if etud["codelycee"]:
        il = get_lycee_infos(etud["codelycee"])
        if il:
            if not etud["codepostallycee"]:
                etud["codepostallycee"] = il["codepostal"]
            if not etud["nomlycee"]:
                etud["nomlycee"] = il["name"]
            if not etud["villelycee"]:
                etud["villelycee"] = il["commune"]
            if not etud.get("positionlycee", None):
                if il["position"] != "0.0,0.0":
                    etud["positionlycee"] = il["position"]
    return etud


""" Conversion fichier original:
f = open('etablissements.csv')
o = open('etablissements2.csv', 'w')
o.write( f.readline() )
for l in f:
    fs = l.split(';')
    nom = ' '.join( [ x.capitalize() for x in fs[1].split() ] )
    adr = ' '.join( [ x.capitalize() for x in fs[2].split() ] )
    ville=' '.join( [ x.capitalize() for x in fs[4].split() ] )
    o.write( '%s;%s;%s;%s;%s\n' % (fs[0], nom, adr, fs[3], ville))

o.close()
"""


def list_scolog(etudid):
    "liste des operations effectuees sur cet etudiant"
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        "SELECT * FROM scolog WHERE etudid=%(etudid)s ORDER BY DATE DESC",
        {"etudid": etudid},
    )
    return cursor.dictfetchall()


def fill_etuds_info(etuds):
    """etuds est une liste d'etudiants (mappings)
    Pour chaque etudiant, ajoute ou formatte les champs
    -> informations pour fiche etudiant ou listes diverses
    """
    from app.scodoc import sco_formsemestre
    from app.scodoc import sco_formsemestre_inscriptions

    cnx = ndb.GetDBConnexion()
    # open('/tmp/t','w').write( str(etuds) )
    for etud in etuds:
        etudid = etud["etudid"]
        etud["dept"] = g.scodoc_dept
        adrs = adresse_list(cnx, {"etudid": etudid})
        if not adrs:
            # certains "vieux" etudiants n'ont pas d'adresse
            adr = {}.fromkeys(_adresseEditor.dbfields, "")
            adr["etudid"] = etudid
        else:
            adr = adrs[0]
            if len(adrs) > 1:
                log("fill_etuds_info: etudid=%s a %d adresses" % (etudid, len(adrs)))
        etud.update(adr)
        format_etud_ident(etud)

        # Semestres dans lesquel il est inscrit
        ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            {"etudid": etudid}
        )
        etud["ins"] = ins
        sems = []
        cursem = None  # semestre "courant" ou il est inscrit
        for i in ins:
            sem = sco_formsemestre.get_formsemestre(i["formsemestre_id"])
            if sco_formsemestre.sem_est_courant(sem):
                cursem = sem
                curi = i
            sem["ins"] = i
            sems.append(sem)
        # trie les semestres par date de debut, le plus recent d'abord
        # (important, ne pas changer (suivi cohortes))
        sems.sort(key=itemgetter("dateord"), reverse=True)
        etud["sems"] = sems
        etud["cursem"] = cursem
        if cursem:
            etud["inscription"] = cursem["titremois"]
            etud["inscriptionstr"] = "Inscrit en " + cursem["titremois"]
            etud["inscription_formsemestre_id"] = cursem["formsemestre_id"]
            etud["etatincursem"] = curi["etat"]
            etud["situation"] = descr_situation_etud(etudid, etud["ne"])
            # XXX est-ce utile ? sco_groups.etud_add_group_infos( etud, cursem)
        else:
            if etud["sems"]:
                if etud["sems"][0]["dateord"] > time.strftime(
                    "%Y-%m-%d", time.localtime()
                ):
                    etud["inscription"] = "futur"
                    etud["situation"] = "futur élève"
                else:
                    etud["inscription"] = "ancien"
                    etud["situation"] = "ancien élève"
            else:
                etud["inscription"] = "non inscrit"
                etud["situation"] = etud["inscription"]
            etud["inscriptionstr"] = etud["inscription"]
            etud["inscription_formsemestre_id"] = None
            # XXXetud['partitions'] = {} # ne va pas chercher les groupes des anciens semestres
            etud["etatincursem"] = "?"

        # nettoyage champs souvents vides
        if etud["nomlycee"]:
            etud["ilycee"] = "Lycée " + format_lycee(etud["nomlycee"])
            if etud["villelycee"]:
                etud["ilycee"] += " (%s)" % etud["villelycee"]
            etud["ilycee"] += "<br/>"
        else:
            if etud["codelycee"]:
                etud["ilycee"] = format_lycee_from_code(etud["codelycee"])
            else:
                etud["ilycee"] = ""
        rap = ""
        if etud["rapporteur"] or etud["commentaire"]:
            rap = "Note du rapporteur"
            if etud["rapporteur"]:
                rap += " (%s)" % etud["rapporteur"]
            rap += ": "
            if etud["commentaire"]:
                rap += "<em>%s</em>" % etud["commentaire"]
        etud["rap"] = rap

        # if etud['boursier_prec']:
        #    pass

        if etud["telephone"]:
            etud["telephonestr"] = "<b>Tél.:</b> " + format_telephone(etud["telephone"])
        else:
            etud["telephonestr"] = ""
        if etud["telephonemobile"]:
            etud["telephonemobilestr"] = "<b>Mobile:</b> " + format_telephone(
                etud["telephonemobile"]
            )
        else:
            etud["telephonemobilestr"] = ""


def descr_situation_etud(etudid, ne=""):
    """chaine decrivant la situation actuelle de l'etudiant"""
    from app.scodoc import sco_formsemestre

    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT I.formsemestre_id, I.etat 
        FROM notes_formsemestre_inscription I,  notes_formsemestre S 
        WHERE etudid=%(etudid)s 
        and S.id = I.formsemestre_id 
        and date_debut < now() 
        and date_fin > now() 
        ORDER BY S.date_debut DESC;""",
        {"etudid": etudid},
    )
    r = cursor.dictfetchone()
    if not r:
        situation = "non inscrit"
    else:
        sem = sco_formsemestre.get_formsemestre(r["formsemestre_id"])
        if r["etat"] == "I":
            situation = "inscrit%s en %s" % (ne, sem["titremois"])
            # Cherche la date d'inscription dans scolar_events:
            events = scolar_events_list(
                cnx,
                args={
                    "etudid": etudid,
                    "formsemestre_id": sem["formsemestre_id"],
                    "event_type": "INSCRIPTION",
                },
            )
            if not events:
                log(
                    "*** situation inconsistante pour %s (inscrit mais pas d'event)"
                    % etudid
                )
                date_ins = "???"  # ???
            else:
                date_ins = events[0]["event_date"]
            situation += " le " + str(date_ins)
        else:
            situation = "démission de %s" % sem["titremois"]
            # Cherche la date de demission dans scolar_events:
            events = scolar_events_list(
                cnx,
                args={
                    "etudid": etudid,
                    "formsemestre_id": sem["formsemestre_id"],
                    "event_type": "DEMISSION",
                },
            )
            if not events:
                log(
                    "*** situation inconsistante pour %s (demission mais pas d'event)"
                    % etudid
                )
                date_dem = "???"  # ???
            else:
                date_dem = events[0]["event_date"]
            situation += " le " + str(date_dem)
    return situation
