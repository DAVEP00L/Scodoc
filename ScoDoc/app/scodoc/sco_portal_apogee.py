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

"""Liaison avec le portail ENT (qui donne accès aux infos Apogée)
"""
import datetime
import os
import time
import urllib
import xml
import xml.sax.saxutils
import xml.dom.minidom

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc import sco_preferences

SCO_CACHE_ETAPE_FILENAME = os.path.join(scu.SCO_TMP_DIR, "last_etapes.xml")


def has_portal():
    "True if we are connected to a portal"
    return get_portal_url()


class PortalInterface(object):
    def __init__(self):
        self.first_time = True

    def get_portal_url(self):
        "URL of portal"
        portal_url = sco_preferences.get_preference("portal_url")
        if portal_url and not portal_url.endswith("/"):
            portal_url += "/"
        if self.first_time:
            if portal_url:
                log("Portal URL=%s" % portal_url)
            else:
                log("Portal not configured")
            self.first_time = False
        return portal_url

    def get_etapes_url(self):
        "Full URL of service giving list of etapes (in XML)"
        etapes_url = sco_preferences.get_preference("etapes_url")
        if not etapes_url:
            # Default:
            portal_url = self.get_portal_url()
            if not portal_url:
                return None
            api_ver = self.get_portal_api_version()
            if api_ver > 1:
                etapes_url = portal_url + "scodocEtapes.php"
            else:
                etapes_url = portal_url + "getEtapes.php"
        return etapes_url

    def get_etud_url(self):
        "Full URL of service giving list of students (in XML)"
        etud_url = sco_preferences.get_preference("etud_url")
        if not etud_url:
            # Default:
            portal_url = self.get_portal_url()
            if not portal_url:
                return None
            api_ver = self.get_portal_api_version()
            if api_ver > 1:
                etud_url = portal_url + "scodocEtudiant.php"
            else:
                etud_url = portal_url + "getEtud.php"
        return etud_url

    def get_photo_url(self):
        "Full URL of service giving photo of student"
        photo_url = sco_preferences.get_preference("photo_url")
        if not photo_url:
            # Default:
            portal_url = self.get_portal_url()
            if not portal_url:
                return None
            api_ver = self.get_portal_api_version()
            if api_ver > 1:
                photo_url = portal_url + "scodocPhoto.php"
            else:
                photo_url = portal_url + "getPhoto.php"
        return photo_url

    def get_maquette_url(self):
        """Full URL of service giving Apogee maquette pour une étape (fichier "CSV")"""
        maquette_url = sco_preferences.get_preference("maquette_url")
        if not maquette_url:
            # Default:
            portal_url = self.get_portal_url()
            if not portal_url:
                return None
            maquette_url = portal_url + "scodocMaquette.php"
        return maquette_url

    def get_portal_api_version(self):
        "API version of the portal software"
        api_ver = sco_preferences.get_preference("portal_api")
        if not api_ver:
            # Default:
            api_ver = 1
        return api_ver


_PI = PortalInterface()
get_portal_url = _PI.get_portal_url
get_etapes_url = _PI.get_etapes_url
get_etud_url = _PI.get_etud_url
get_photo_url = _PI.get_photo_url
get_maquette_url = _PI.get_maquette_url
get_portal_api_version = _PI.get_portal_api_version


def get_inscrits_etape(code_etape, anneeapogee=None, ntrials=2):
    """Liste des inscrits à une étape Apogée
    Result = list of dicts
    ntrials: try several time the same request, useful for some bad web services
    """
    log("get_inscrits_etape: code=%s anneeapogee=%s" % (code_etape, anneeapogee))
    if anneeapogee is None:
        anneeapogee = str(time.localtime()[0])

    etud_url = get_etud_url()
    api_ver = get_portal_api_version()
    if not etud_url:
        return []
    portal_timeout = sco_preferences.get_preference("portal_timeout")
    if api_ver > 1:
        req = (
            etud_url
            + "?"
            + urllib.parse.urlencode((("etape", code_etape), ("annee", anneeapogee)))
        )
    else:
        req = etud_url + "?" + urllib.parse.urlencode((("etape", code_etape),))
    actual_timeout = float(portal_timeout) / ntrials
    if portal_timeout > 0:
        actual_timeout = max(1, actual_timeout)
    for _ntrial in range(ntrials):
        doc = scu.query_portal(req, timeout=actual_timeout)
        if doc:
            break
    if not doc:
        raise ScoValueError("pas de réponse du portail ! (timeout=%s)" % portal_timeout)
    etuds = _normalize_apo_fields(xml_to_list_of_dicts(doc, req=req))

    # Filtre sur annee inscription Apogee:
    def check_inscription(e):
        if "inscription" in e:
            if e["inscription"] == anneeapogee:
                return True
            else:
                return False
        else:
            log(
                "get_inscrits_etape: pas inscription dans code_etape=%s e=%s"
                % (code_etape, e)
            )
            return False  # ??? pas d'annee d'inscription dans la réponse

    etuds = [e for e in etuds if check_inscription(e)]
    return etuds


def query_apogee_portal(**args):
    """Recupere les infos sur les etudiants nommés
    args: nom, prenom, code_nip
    (nom et prenom matchent des parties de noms)
    """
    etud_url = get_etud_url()
    api_ver = get_portal_api_version()
    if not etud_url:
        return []
    if api_ver > 1:
        if args["nom"] or args["prenom"]:
            # Ne fonctionne pas avec l'API 2 sur nom et prenom
            # XXX TODO : va poser problème pour la page modif données étudiants : A VOIR
            return []
    portal_timeout = sco_preferences.get_preference("portal_timeout")
    req = etud_url + "?" + urllib.parse.urlencode(list(args.items()))
    doc = scu.query_portal(req, timeout=portal_timeout)  # sco_utils
    return xml_to_list_of_dicts(doc, req=req)


def xml_to_list_of_dicts(doc, req=None):
    """Convert an XML 1.0 str to a list of dicts."""
    if not doc:
        return []
    # Fix for buggy XML returned by some APIs (eg USPN)
    invalid_entities = {
        "&CCEDIL;": "Ç",
        "& ": "&amp; ",  # only when followed by a space (avoid affecting entities)
        # to be completed...
    }
    for k in invalid_entities:
        doc = doc.replace(k, invalid_entities[k])
    #
    try:
        dom = xml.dom.minidom.parseString(doc)
    except xml.parsers.expat.ExpatError as e:
        # Find faulty part
        err_zone = doc.splitlines()[e.lineno - 1][e.offset : e.offset + 20]
        # catch bug: log and re-raise exception
        log(
            "xml_to_list_of_dicts: exception in XML parseString\ndoc:\n%s\n(end xml doc)\n"
            % doc
        )
        raise ScoValueError(
            'erreur dans la réponse reçue du portail ! (peut être : "%s")' % err_zone
        )
    infos = []
    try:
        if dom.childNodes[0].nodeName != "etudiants":
            raise ValueError
        etudiants = dom.getElementsByTagName("etudiant")
        for etudiant in etudiants:
            d = {}
            # recupere toutes les valeurs <valeur>XXX</valeur>
            for e in etudiant.childNodes:
                if e.nodeType == e.ELEMENT_NODE:
                    childs = e.childNodes
                    if len(childs):
                        d[str(e.nodeName)] = childs[0].nodeValue
            infos.append(d)
    except:
        log("*** invalid XML response from Etudiant Web Service")
        log("req=%s" % req)
        log("doc=%s" % doc)
        raise ValueError("invalid XML response from Etudiant Web Service\n%s" % doc)
    return infos


def get_infos_apogee_allaccents(nom, prenom):
    "essai recup infos avec differents codages des accents"
    if nom:
        nom_noaccents = scu.suppress_accents(nom)
    else:
        nom_noaccents = nom

    if prenom:
        prenom_noaccents = scu.suppress_accents(prenom)
    else:
        prenom_noaccents = prenom

    # avec accents
    infos = query_apogee_portal(nom=nom, prenom=prenom)
    # sans accents
    if nom != nom_noaccents or prenom != prenom_noaccents:
        infos += query_apogee_portal(nom=nom_noaccents, prenom=prenom_noaccents)
    return infos


def get_infos_apogee(nom, prenom):
    """recupere les codes Apogee en utilisant le web service CRIT"""
    if (not nom) and (not prenom):
        return []
    # essaie plusieurs codages: tirets, accents
    infos = get_infos_apogee_allaccents(nom, prenom)
    nom_st = nom.replace("-", " ")
    prenom_st = prenom.replace("-", " ")
    if nom_st != nom or prenom_st != prenom:
        infos += get_infos_apogee_allaccents(nom_st, prenom_st)
    # si pas de match et nom ou prenom composé, essaie en coupant
    if not infos:
        if nom:
            nom1 = nom.split()[0]
        else:
            nom1 = nom
        if prenom:
            prenom1 = prenom.split()[0]
        else:
            prenom1 = prenom
        if nom != nom1 or prenom != prenom1:
            infos += get_infos_apogee_allaccents(nom1, prenom1)
    return infos


def get_etud_apogee(code_nip):
    """Informations à partir du code NIP.
    None si pas d'infos sur cet etudiant.
    Exception si reponse invalide.
    """
    if not code_nip:
        return {}
    etud_url = get_etud_url()
    if not etud_url:
        return {}
    portal_timeout = sco_preferences.get_preference("portal_timeout")
    req = etud_url + "?" + urllib.parse.urlencode((("nip", code_nip),))
    doc = scu.query_portal(req, timeout=portal_timeout)
    d = _normalize_apo_fields(xml_to_list_of_dicts(doc, req=req))
    if not d:
        return None
    if len(d) > 1:
        raise ValueError("invalid XML response from Etudiant Web Service\n%s" % doc)
    return d[0]


def get_default_etapes():
    """Liste par défaut, lue du fichier de config"""
    filename = scu.SCO_TOOLS_DIR + "/default-etapes.txt"
    log("get_default_etapes: reading %s" % filename)
    f = open(filename)
    etapes = {}
    for line in f.readlines():
        line = line.strip()
        if line and line[0] != "#":
            dept, code, intitule = [x.strip() for x in line.split(":")]
            if dept and code:
                if dept in etapes:
                    etapes[dept][code] = intitule
                else:
                    etapes[dept] = {code: intitule}
    return etapes


def _parse_etapes_from_xml(doc):
    """
    may raise exception if invalid xml doc
    """
    xml_etapes_by_dept = sco_preferences.get_preference("xml_etapes_by_dept")
    # parser XML
    dom = xml.dom.minidom.parseString(doc)
    infos = {}
    if dom.childNodes[0].nodeName != "etapes":
        raise ValueError
    if xml_etapes_by_dept:
        # Ancien format XML avec des sections par departement:
        for d in dom.childNodes[0].childNodes:
            if d.nodeType == d.ELEMENT_NODE:
                dept = d.nodeName
                _xml_list_codes(infos, dept, d.childNodes)
    else:
        # Toutes les étapes:
        dept = ""
        _xml_list_codes(infos, "", dom.childNodes[0].childNodes)
    return infos


def get_etapes_apogee():
    """Liste des etapes apogee
    { departement : { code_etape : intitule } }
    Demande la liste au portail, ou si échec utilise liste
    par défaut
    """
    etapes_url = get_etapes_url()
    infos = {}
    if etapes_url:
        portal_timeout = sco_preferences.get_preference("portal_timeout")
        log(
            "get_etapes_apogee: requesting '%s' with timeout=%s"
            % (etapes_url, portal_timeout)
        )
        doc = scu.query_portal(etapes_url, timeout=portal_timeout)
        try:
            infos = _parse_etapes_from_xml(doc)
            # cache le resultat (utile si le portail repond de façon intermitente)
            if infos:
                log("get_etapes_apogee: caching result")
                with open(SCO_CACHE_ETAPE_FILENAME, "w") as f:
                    f.write(doc)
        except:
            log("invalid XML response from getEtapes Web Service\n%s" % etapes_url)
            # Avons nous la copie d'une réponse récente ?
            try:
                doc = open(SCO_CACHE_ETAPE_FILENAME).read()
                infos = _parse_etapes_from_xml(doc)
                log("using last saved version from " + SCO_CACHE_ETAPE_FILENAME)
            except:
                infos = {}
    else:
        # Pas de portail: utilise étapes par défaut livrées avec ScoDoc
        log("get_etapes_apogee: no configured URL (using default file)")
        infos = get_default_etapes()
    return infos


def _xml_list_codes(target_dict, dept, nodes):
    for e in nodes:
        if e.nodeType == e.ELEMENT_NODE:
            intitule = e.childNodes[0].nodeValue
            code = e.attributes["code"].value
            if dept in target_dict:
                target_dict[dept][code] = intitule
            else:
                target_dict[dept] = {code: intitule}


def get_etapes_apogee_dept():
    """Liste des etapes apogee pour ce departement.
    Utilise la propriete 'portal_dept_name' pour identifier le departement.

    Si xml_etapes_by_dept est faux (nouveau format XML depuis sept 2014),
    le departement n'est pas utilisé: toutes les étapes sont présentées.

    Returns [ ( code, intitule) ], ordonnée
    """
    xml_etapes_by_dept = sco_preferences.get_preference("xml_etapes_by_dept")
    if xml_etapes_by_dept:
        portal_dept_name = sco_preferences.get_preference("portal_dept_name")
        log('get_etapes_apogee_dept: portal_dept_name="%s"' % portal_dept_name)
    else:
        portal_dept_name = ""
        log("get_etapes_apogee_dept: pas de sections par departement")

    infos = get_etapes_apogee()
    if portal_dept_name and portal_dept_name not in infos:
        log(
            "get_etapes_apogee_dept: pas de section '%s' dans la reponse portail"
            % portal_dept_name
        )
        return []
    if portal_dept_name:
        etapes = list(infos[portal_dept_name].items())
    else:
        # prend toutes les etapes
        etapes = []
        for k in infos.keys():
            etapes += list(infos[k].items())

    etapes.sort()  # tri sur le code etape
    return etapes


def _portal_date_dmy2date(s):
    """date inscription renvoyée sous la forme dd/mm/yy
    renvoie un objet date, ou None
    """
    s = s.strip()
    if not s:
        return None
    else:
        d, m, y = [int(x) for x in s.split("/")]  # raises ValueError if bad format
        if y < 100:
            y += 2000  # 21ème siècle
        return datetime.date(y, m, d)


def _normalize_apo_fields(infolist):
    """
    infolist: liste de dict renvoyés par le portail Apogee

    recode les champs: paiementinscription (-> booleen), datefinalisationinscription (date)
    ajoute le champs 'paiementinscription_str' : 'ok', 'Non' ou '?'
    ajoute les champs 'etape' (= None) et 'prenom' ('') s'ils ne sont pas présents.
    """
    for infos in infolist:
        if "paiementinscription" in infos:
            infos["paiementinscription"] = (
                infos["paiementinscription"].lower() == "true"
            )
            if infos["paiementinscription"]:
                infos["paiementinscription_str"] = "ok"
            else:
                infos["paiementinscription_str"] = "Non"
        else:
            infos["paiementinscription"] = None
            infos["paiementinscription_str"] = "?"

        if "datefinalisationinscription" in infos:
            infos["datefinalisationinscription"] = _portal_date_dmy2date(
                infos["datefinalisationinscription"]
            )
            infos["datefinalisationinscription_str"] = infos[
                "datefinalisationinscription"
            ].strftime("%d/%m/%Y")
        else:
            infos["datefinalisationinscription"] = None
            infos["datefinalisationinscription_str"] = ""

        if "etape" not in infos:
            infos["etape"] = None

        if "prenom" not in infos:
            infos["prenom"] = ""

    return infolist


def check_paiement_etuds(etuds):
    """Interroge le portail pour vérifier l'état de "paiement" et l'étape d'inscription.

    Seuls les etudiants avec code NIP sont renseignés.

    Renseigne l'attribut booleen 'paiementinscription' dans chaque etud.

    En sortie: modif les champs de chaque etud
    'paiementinscription' : True, False ou None
    'paiementinscription_str' : 'ok', 'Non' ou '?' ou '(pas de code)'
    'etape' : etape Apogee ou None
    """
    # interrogation séquentielle longue...
    for etud in etuds:
        if "code_nip" not in etud:
            etud["paiementinscription"] = None
            etud["paiementinscription_str"] = "(pas de code)"
            etud["datefinalisationinscription"] = None
            etud["datefinalisationinscription_str"] = "NA"
            etud["etape"] = None
        else:
            # Modifie certains champs de l'étudiant:
            infos = get_etud_apogee(etud["code_nip"])
            if infos:
                for k in (
                    "paiementinscription",
                    "paiementinscription_str",
                    "datefinalisationinscription",
                    "datefinalisationinscription_str",
                    "etape",
                ):
                    etud[k] = infos[k]
            else:
                etud["datefinalisationinscription"] = None
                etud["datefinalisationinscription_str"] = "Erreur"
                etud["datefinalisationinscription"] = None
                etud["paiementinscription_str"] = "(pb cnx Apogée)"


def get_maquette_apogee(etape="", annee_scolaire=""):
    """Maquette CSV Apogee pour une étape et une annee scolaire"""
    maquette_url = get_maquette_url()
    if not maquette_url:
        return None
    portal_timeout = sco_preferences.get_preference("portal_timeout")
    req = (
        maquette_url
        + "?"
        + urllib.parse.urlencode((("etape", etape), ("annee", annee_scolaire)))
    )
    doc = scu.query_portal(req, timeout=portal_timeout)
    return doc
