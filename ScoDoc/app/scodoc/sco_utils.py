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


""" Common definitions
"""
import base64
import bisect
import copy
import datetime
import json
from hashlib import md5
import numbers
import os
import pydot
import re
import requests
import _thread
import time
import unicodedata
import urllib
from urllib.parse import urlparse, parse_qsl, urlunparse, urlencode

from PIL import Image as PILImage

from flask import g, request
from flask import url_for, make_response

from config import Config
from app import log
from app.scodoc.sco_vdi import ApoEtapeVDI
from app.scodoc.sco_xml import quote_xml_attr
from app.scodoc.sco_codes_parcours import NOTES_TOLERANCE, CODES_EXPL
from app.scodoc import sco_exceptions
from app.scodoc import sco_xml
import sco_version


# ----- CALCUL ET PRESENTATION DES NOTES
NOTES_PRECISION = 1e-4  # evite eventuelles erreurs d'arrondis
NOTES_MIN = 0.0  # valeur minimale admise pour une note (sauf malus, dans [-20, 20])
NOTES_MAX = 1000.0
NOTES_NEUTRALISE = -1000.0  # notes non prises en comptes dans moyennes
NOTES_SUPPRESS = -1001.0  # note a supprimer
NOTES_ATTENTE = -1002.0  # note "en attente" (se calcule comme une note neutralisee)


# Types de modules
MODULE_STANDARD = 0
MODULE_MALUS = 1

MALUS_MAX = 20.0
MALUS_MIN = -20.0

APO_MISSING_CODE_STR = "----"  # shown in HTML pages in place of missing code Apogée
EDIT_NB_ETAPES = 6  # Nombre max de codes étapes / semestre presentés dans l'UI

IT_SITUATION_MISSING_STR = (
    "____"  # shown on ficheEtud (devenir) in place of empty situation
)

RANG_ATTENTE_STR = "(attente)"  #  rang affiché sur bulletins quand notes en attente

# borne supérieure de chaque mention
NOTES_MENTIONS_TH = (
    NOTES_TOLERANCE,
    7.0,
    10.0,
    12.0,
    14.0,
    16.0,
    18.0,
    20.0 + NOTES_TOLERANCE,
)
NOTES_MENTIONS_LABS = (
    "Nul",
    "Faible",
    "Insuffisant",
    "Passable",
    "Assez bien",
    "Bien",
    "Très bien",
    "Excellent",
)

EVALUATION_NORMALE = 0
EVALUATION_RATTRAPAGE = 1
EVALUATION_SESSION2 = 2


def fmt_note(val, note_max=None, keep_numeric=False):
    """conversion note en str pour affichage dans tables HTML ou PDF.
    Si keep_numeric, laisse les valeur numeriques telles quelles (pour export Excel)
    """
    if val is None:
        return "ABS"
    if val == NOTES_NEUTRALISE:
        return "EXC"  # excuse, note neutralise
    if val == NOTES_ATTENTE:
        return "ATT"  # attente, note neutralisee
    if isinstance(val, float) or isinstance(val, int):
        if note_max != None and note_max > 0:
            val = val * 20.0 / note_max
        if keep_numeric:
            return val
        else:
            s = "%2.2f" % round(float(val), 2)  # 2 chiffres apres la virgule
            s = "0" * (5 - len(s)) + s  # padding: 0 à gauche pour longueur 5: "12.34"
            return s
    else:
        return val.replace("NA", "-")


def fmt_coef(val):
    """Conversion valeur coefficient (float) en chaine"""
    if val < 0.01:
        return "%g" % val  # unusually small value
    return "%g" % round(val, 2)


def fmt_abs(val):
    """Conversion absences en chaine. val est une list [nb_abs_total, nb_abs_justifiees
    => NbAbs / Nb_justifiees
    """
    return "%s / %s" % (val[0], val[1])


def isnumber(x):
    "True if x is a number (int, float, etc.)"
    return isinstance(x, numbers.Number)


def join_words(*words):
    words = [str(w).strip() for w in words if w is not None]
    return " ".join([w for w in words if w])


def get_mention(moy):
    """Texte "mention" en fonction de la moyenne générale"""
    try:
        moy = float(moy)
    except:
        return ""
    return NOTES_MENTIONS_LABS[bisect.bisect_right(NOTES_MENTIONS_TH, moy)]


class DictDefault(dict):  # obsolete, use collections.defaultdict
    """A dictionnary with default value for all keys
    Each time a non existent key is requested, it is added to the dict.
    (used in python 2.4, can't use new __missing__ method)
    """

    defaultvalue = 0

    def __init__(self, defaultvalue=0, kv_dict={}):
        dict.__init__(self)
        self.defaultvalue = defaultvalue
        self.update(kv_dict)

    def __getitem__(self, k):
        if k in self:
            return self.get(k)
        value = copy.copy(self.defaultvalue)
        self[k] = value
        return value


class WrapDict(object):
    """Wrap a dict so that getitem returns '' when values are None"""

    def __init__(self, adict, NoneValue=""):
        self.dict = adict
        self.NoneValue = NoneValue

    def __getitem__(self, key):
        value = self.dict[key]
        if value is None:
            return self.NoneValue
        else:
            return value


def group_by_key(d, key):
    gr = DictDefault(defaultvalue=[])
    for e in d:
        gr[e[key]].append(e)
    return gr


# ----- Global lock for critical sections (except notes_tables caches)
GSL = _thread.allocate_lock()  # Global ScoDoc Lock

SCODOC_DIR = Config.SCODOC_DIR

# ----- Repertoire "config" modifiable
#        /opt/scodoc-data/config
SCODOC_CFG_DIR = os.path.join(Config.SCODOC_VAR_DIR, "config")
# ----- Version information
SCODOC_VERSION_DIR = os.path.join(SCODOC_CFG_DIR, "version")
# ----- Repertoire tmp : /opt/scodoc-data/tmp
SCO_TMP_DIR = os.path.join(Config.SCODOC_VAR_DIR, "tmp")
if not os.path.exists(SCO_TMP_DIR) and os.path.exists(Config.SCODOC_VAR_DIR):
    os.mkdir(SCO_TMP_DIR, 0o755)
# ----- Les logos: /opt/scodoc-data/config/logos
SCODOC_LOGOS_DIR = os.path.join(SCODOC_CFG_DIR, "logos")
LOGOS_IMAGES_ALLOWED_TYPES = ("jpg", "jpeg", "png")  # remind that PIL does not read pdf


# ----- Les outils distribués
SCO_TOOLS_DIR = os.path.join(Config.SCODOC_DIR, "tools")


# ----- Lecture du fichier de configuration
from app.scodoc import sco_config
from app.scodoc import sco_config_load

sco_config_load.load_local_configuration(SCODOC_CFG_DIR)
CONFIG = sco_config.CONFIG
if hasattr(CONFIG, "CODES_EXPL"):
    CODES_EXPL.update(
        CONFIG.CODES_EXPL
    )  # permet de customiser les explications de codes

if CONFIG.CUSTOM_HTML_HEADER:
    CUSTOM_HTML_HEADER = open(CONFIG.CUSTOM_HTML_HEADER).read()
else:
    CUSTOM_HTML_HEADER = ""

if CONFIG.CUSTOM_HTML_HEADER_CNX:
    CUSTOM_HTML_HEADER_CNX = open(CONFIG.CUSTOM_HTML_HEADER_CNX).read()
else:
    CUSTOM_HTML_HEADER_CNX = ""

if CONFIG.CUSTOM_HTML_FOOTER:
    CUSTOM_HTML_FOOTER = open(CONFIG.CUSTOM_HTML_FOOTER).read()
else:
    CUSTOM_HTML_FOOTER = ""

if CONFIG.CUSTOM_HTML_FOOTER_CNX:
    CUSTOM_HTML_FOOTER_CNX = open(CONFIG.CUSTOM_HTML_FOOTER_CNX).read()
else:
    CUSTOM_HTML_FOOTER_CNX = ""

SCO_ENCODING = "utf-8"  # used by Excel, XML, PDF, ...


SCO_DEFAULT_SQL_USER = "scodoc"  # should match Zope process UID
SCO_DEFAULT_SQL_PORT = "5432"
SCO_DEFAULT_SQL_USERS_CNX = "dbname=SCOUSERS port=%s" % SCO_DEFAULT_SQL_PORT

# Valeurs utilisées pour affichage seulement, pas de requetes ni de mails envoyés:
SCO_WEBSITE = "https://scodoc.org"
SCO_USER_MANUAL = "https://scodoc.org/GuideUtilisateur"
SCO_ANNONCES_WEBSITE = "https://listes.univ-paris13.fr/mailman/listinfo/scodoc-annonces"
SCO_DEVEL_LIST = "scodoc-devel@listes.univ-paris13.fr"
SCO_USERS_LIST = "notes@listes.univ-paris13.fr"

# Mails avec exceptions (erreurs) anormales envoyés à cette adresse:
# mettre '' pour désactiver completement l'envois de mails d'erreurs.
# (ces mails sont précieux pour corriger les erreurs, ne les désactiver que si
#  vous avez de bonnes raisons de le faire: vous pouvez me contacter avant)
SCO_EXC_MAIL = "scodoc-exception@viennet.net"

# L'adresse du mainteneur (non utilisée automatiquement par ScoDoc: ne pas changer)
SCO_DEV_MAIL = "emmanuel.viennet@gmail.com"  # SVP ne pas changer

# Adresse pour l'envoi des dumps (pour assistance technnique):
#   ne pas changer (ou vous perdez le support)
SCO_DUMP_UP_URL = "https://scodoc.org/scodoc-installmgr/upload-dump"

CSV_FIELDSEP = ";"
CSV_LINESEP = "\n"
CSV_MIMETYPE = "text/comma-separated-values"
CSV_SUFFIX = ".csv"
JSON_MIMETYPE = "application/json"
JSON_SUFFIX = ".json"
PDF_MIMETYPE = "application/pdf"
PDF_SUFFIX = ".pdf"
XLS_MIMETYPE = "application/vnd.ms-excel"
XLS_SUFFIX = ".xls"
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_SUFFIX = ".xlsx"
XML_MIMETYPE = "text/xml"
XML_SUFFIX = ".xml"


def get_mime_suffix(format_code: str) -> tuple[str, str]:
    """Returns (MIME, SUFFIX) from format_code == "xls", "xml", ...
    SUFFIX includes the dot: ".xlsx", ".xml", ...
    "xls" and "xlsx" format codes give XLSX
    """
    d = {
        "csv": (CSV_MIMETYPE, CSV_SUFFIX),
        "xls": (XLSX_MIMETYPE, XLSX_SUFFIX),
        "xlsx": (XLSX_MIMETYPE, XLSX_SUFFIX),
        "pdf": (PDF_MIMETYPE, PDF_SUFFIX),
        "xml": (XML_MIMETYPE, XML_SUFFIX),
        "json": (JSON_MIMETYPE, JSON_SUFFIX),
    }
    return d[format_code]


# Admissions des étudiants
# Différents types de voies d'admission:
# (stocké en texte libre dans la base, mais saisie par menus pour harmoniser)
TYPE_ADMISSION_DEFAULT = "Inconnue"
TYPES_ADMISSION = (TYPE_ADMISSION_DEFAULT, "APB", "APB-PC", "CEF", "Direct")

BULLETINS_VERSIONS = ("short", "selectedevals", "long")

# Support for ScoDoc7 compatibility


def ScoURL():
    """base URL for this sco instance.
    e.g. https://scodoc.xxx.fr/ScoDoc/DEPT/Scolarite
    = page accueil département
    """
    return url_for("scolar.index_html", scodoc_dept=g.scodoc_dept)[
        : -len("/index_html")
    ]


def NotesURL():
    """URL of Notes
    e.g. https://scodoc.xxx.fr/ScoDoc/DEPT/Scolarite/Notes
    = url de base des méthodes de notes
    (page accueil programmes).
    """
    return url_for("notes.index_html", scodoc_dept=g.scodoc_dept)[: -len("/index_html")]


def EntreprisesURL():
    """URL of Enterprises
    e.g. https://scodoc.xxx.fr/ScoDoc/DEPT/Scolarite/Entreprises
    = url de base des requêtes de ZEntreprises
    et page accueil Entreprises
    """
    return "NotImplemented"
    # url_for("entreprises.index_html", scodoc_dept=g.scodoc_dept)[
    #    : -len("/index_html")
    # ]


def AbsencesURL():
    """URL of Absences"""
    return url_for("absences.index_html", scodoc_dept=g.scodoc_dept)[
        : -len("/index_html")
    ]


def UsersURL():
    """URL of Users
    e.g. https://scodoc.xxx.fr/ScoDoc/DEPT/Scolarite/Users
    = url de base des requêtes ZScoUsers
    et page accueil users
    """
    return url_for("users.index_html", scodoc_dept=g.scodoc_dept)[: -len("/index_html")]


# ---- Simple python utilities


def simplesqlquote(s, maxlen=50):
    """simple SQL quoting to avoid most SQL injection attacks.
    Note: we use this function in the (rare) cases where we have to
    construct SQL code manually"""
    s = s[:maxlen]
    s.replace("'", r"\'")
    s.replace(";", r"\;")
    for bad in ("select", "drop", ";", "--", "insert", "delete", "xp_"):
        s = s.replace(bad, "")
    return s


def unescape_html(s):
    """un-escape html entities"""
    s = s.strip().replace("&amp;", "&")
    s = s.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    return s


def build_url_query(url: str, **params) -> str:
    """Add parameters to existing url, as a query string"""
    url_parse = urlparse(url)
    query = url_parse.query
    url_dict = dict(parse_qsl(query))
    url_dict.update(params)
    url_new_query = urlencode(url_dict)
    url_parse = url_parse._replace(query=url_new_query)
    new_url = urlunparse(url_parse)
    return new_url


# test if obj is iterable (but not a string)
isiterable = lambda obj: getattr(obj, "__iter__", False)


def unescape_html_dict(d):
    """un-escape all dict values, recursively"""
    try:
        indices = list(d.keys())
    except:
        indices = list(range(len(d)))
    for k in indices:
        v = d[k]
        if isinstance(v, bytes):
            d[k] = unescape_html(v)
        elif isiterable(v):
            unescape_html_dict(v)


# Expressions used to check noms/prenoms
FORBIDDEN_CHARS_EXP = re.compile(r"[*\|~\(\)\\]")
ALPHANUM_EXP = re.compile(r"^[\w-]+$", re.UNICODE)


def is_valid_code_nip(s):
    """True si s peut être un code NIP: au moins 6 chiffres décimaux"""
    if not s:
        return False
    return re.match(r"^[0-9]{6,32}$", s)


def strnone(s):
    "convert s to string, '' if s is false"
    if s:
        return str(s)
    else:
        return ""


def stripquotes(s):
    "strip s from spaces and quotes"
    s = s.strip()
    if s and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1]
    return s


def suppress_accents(s):
    "remove accents and suppress non ascii characters from string s"
    if isinstance(s, str):
        return (
            unicodedata.normalize("NFD", s)
            .encode("ascii", "ignore")
            .decode(SCO_ENCODING)
        )
    return s  # may be int


class PurgeChars:
    """delete all chars except those belonging to the specified string"""

    def __init__(self, allowed_chars=""):
        self.allowed_chars_set = {ord(c) for c in allowed_chars}

    def __getitem__(self, x):
        if x not in self.allowed_chars_set:
            return None
        raise LookupError()


def purge_chars(s, allowed_chars=""):
    return s.translate(PurgeChars(allowed_chars=allowed_chars))


def sanitize_string(s):
    """s is an ordinary string, encoding given by SCO_ENCODING"
    suppress accents and chars interpreted in XML
    Irreversible (not a quote)

    For ids and some filenames
    """
    # Table suppressing some chars:
    trans = str.maketrans("", "", "'`\"<>!&\\ ")
    return suppress_accents(s.translate(trans)).replace(" ", "_").replace("\t", "_")


_BAD_FILENAME_CHARS = str.maketrans("", "", ":/\\&[]*?'")


def make_filename(name):
    """Try to convert name to a reasonable filename
    without spaces, (back)slashes, : and without accents
    """
    return (
        suppress_accents(name.translate(_BAD_FILENAME_CHARS)).replace(" ", "_")
        or "scodoc"
    )


VALID_CARS = (
    "-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.!"  # no / !
)
VALID_CARS_SET = set(VALID_CARS)
VALID_EXP = re.compile("^[" + VALID_CARS + "]+$")


def sanitize_filename(filename):
    """Keep only valid chars
    used for archives filenames
    """
    filename = suppress_accents(filename.replace(" ", "_"))
    sane = "".join([c for c in filename if c in VALID_CARS_SET])
    if len(sane) < 2:
        sane = time.strftime("%Y-%m-%d-%H%M%S") + "-" + sane
    return sane


def is_valid_filename(filename):
    """True if filename is safe"""
    return VALID_EXP.match(filename)


def bul_filename(sem, etud, format):
    """Build a filename for this bulletin"""
    dt = time.strftime("%Y-%m-%d")
    filename = f"bul-{sem['titre_num']}-{dt}-{etud['nom']}.{format}"
    filename = make_filename(filename)
    return filename


def sendCSVFile(data, filename):  # DEPRECATED  utiliser send_file
    """publication fichier CSV."""
    return send_file(data, filename=filename, mime=CSV_MIMETYPE, attached=True)


def sendPDFFile(data, filename):  # DEPRECATED  utiliser send_file
    return send_file(data, filename=filename, mime=PDF_MIMETYPE, attached=True)


class ScoDocJSONEncoder(json.JSONEncoder):
    def default(self, o):  # pylint: disable=E0202
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        elif isinstance(o, ApoEtapeVDI):
            return str(o)
        else:
            return json.JSONEncoder.default(self, o)


def sendJSON(data, attached=False):
    js = json.dumps(data, indent=1, cls=ScoDocJSONEncoder)
    return send_file(
        js, filename="sco_data.json", mime=JSON_MIMETYPE, attached=attached
    )


def sendXML(data, tagname=None, force_outer_xml_tag=True, attached=False, quote=True):
    if type(data) != list:
        data = [data]  # always list-of-dicts
    if force_outer_xml_tag:
        data = [{tagname: data}]
        tagname += "_list"
    doc = sco_xml.simple_dictlist2xml(data, tagname=tagname, quote=quote)
    return send_file(doc, filename="sco_data.xml", mime=XML_MIMETYPE, attached=attached)


def sendResult(
    data,
    name=None,
    format=None,
    force_outer_xml_tag=True,
    attached=False,
    quote_xml=True,
):
    if (format is None) or (format == "html"):
        return data
    elif format == "xml":  # name is outer tagname
        return sendXML(
            data,
            tagname=name,
            force_outer_xml_tag=force_outer_xml_tag,
            attached=attached,
            quote=quote_xml,
        )
    elif format == "json":
        return sendJSON(data, attached=attached)
    else:
        raise ValueError("invalid format: %s" % format)


def send_file(data, filename="", suffix="", mime=None, attached=None):
    """Build Flask Response for file download of given type
    By default (attached is None), json and xml are inlined and otrher types are attached.
    """
    if attached is None:
        if mime == XML_MIMETYPE or mime == JSON_MIMETYPE:
            attached = False
        else:
            attached = True
    # if attached and not filename:
    #    raise ValueError("send_file: missing attachement filename")
    if filename:
        if suffix:
            filename += suffix
        filename = make_filename(filename)
    response = make_response(data)
    response.headers["Content-Type"] = mime
    if attached and filename:
        response.headers["Content-Disposition"] = 'attachment; filename="%s"' % filename
    return response


def get_request_args():
    """returns a dict with request (POST or GET) arguments
    converted to suit legacy Zope style (scodoc7) functions.
    """
    # copy to get a mutable object (necessary for TrivialFormulator and several methods)
    if request.method == "POST":
        # request.form is a werkzeug.datastructures.ImmutableMultiDict
        # must copy to get a mutable version (needed by TrivialFormulator)
        vals = request.form.copy()
        if request.files:
            # Add files in form:
            vals.update(request.files)
        for k in request.form:
            if k.endswith(":list"):
                vals[k[:-5]] = request.form.getlist(k)
    elif request.method == "GET":
        vals = {}
        for k in request.args:
            # current_app.logger.debug("%s\t%s" % (k, request.args.getlist(k)))
            if k.endswith(":list"):
                vals[k[:-5]] = request.args.getlist(k)
            else:
                values = request.args.getlist(k)
                vals[k] = values[0] if len(values) == 1 else values
    return vals


def get_scodoc_version():
    "return a string identifying ScoDoc version"
    return sco_version.SCOVERSION


def check_scodoc7_password(scodoc7_hash, password):
    """Check a password vs scodoc7 hash
    used only during old databases migrations"""
    m = md5()
    m.update(password.encode("utf-8"))
    h = base64.encodebytes(m.digest()).decode("utf-8").strip()
    return h == scodoc7_hash


# Simple string manipulations


def abbrev_prenom(prenom):
    "Donne l'abreviation d'un prenom"
    # un peu lent, mais espère traiter tous les cas
    # Jean -> J.
    # Charles -> Ch.
    # Jean-Christophe -> J.-C.
    # Marie Odile -> M. O.
    prenom = prenom.replace(".", " ").strip()
    if not prenom:
        return ""
    d = prenom[:3].upper()
    if d == "CHA":
        abrv = "Ch."  # 'Charles' donne 'Ch.'
        i = 3
    else:
        abrv = prenom[0].upper() + "."
        i = 1
    n = len(prenom)
    while i < n:
        c = prenom[i]
        if c == " " or c == "-" and i < n - 1:
            sep = c
            i += 1
            # gobbe tous les separateurs
            while i < n and (prenom[i] == " " or prenom[i] == "-"):
                if prenom[i] == "-":
                    sep = "-"
                i += 1
            if i < n:
                abrv += sep + prenom[i].upper() + "."
        i += 1
    return abrv


#
def timedate_human_repr():
    "representation du temps courant pour utilisateur: a localiser"
    return time.strftime("%d/%m/%Y à %Hh%M")


def annee_scolaire_repr(year, month):
    """representation de l'annee scolaire : '2009 - 2010'
    à partir d'une date.
    """
    if month > 7:  # apres le 1er aout
        return "%s - %s" % (year, year + 1)
    else:
        return "%s - %s" % (year - 1, year)


def annee_scolaire_debut(year, month):
    """Annee scolaire de debut (septembre): heuristique pour l'hémisphère nord..."""
    if int(month) > 7:
        return int(year)
    else:
        return int(year) - 1


def sem_decale_str(sem):
    """'D' si semestre decalé, ou ''"""
    # considère "décalé" les semestre impairs commençant entre janvier et juin
    # et les pairs entre juillet et decembre
    if sem["semestre_id"] <= 0:
        return ""
    if (sem["semestre_id"] % 2 and sem["mois_debut_ord"] <= 6) or (
        not sem["semestre_id"] % 2 and sem["mois_debut_ord"] > 6
    ):
        return "D"
    else:
        return ""


def is_valid_mail(email):
    """True if well-formed email address"""
    return re.match(r"^.+@.+\..{2,3}$", email)


def graph_from_edges(edges, graph_name="mygraph"):
    """Crée un graph pydot
    à partir d'une liste d'arêtes [ (n1, n2), (n2, n3), ... ]
    où n1, n2, ... sont des chaînes donnant l'id des nœuds.

    Fonction remplaçant celle de pydot qui est buggée.
    """
    nodes = set([it for tup in edges for it in tup])
    graph = pydot.Dot(graph_name)
    for n in nodes:
        graph.add_node(pydot.Node(n))
    for e in edges:
        graph.add_edge(pydot.Edge(src=e[0], dst=e[1]))
    return graph


ICONSIZES = {}  # name : (width, height) cache image sizes


def icontag(name, file_format="png", no_size=False, **attrs):
    """tag HTML pour un icone.
    (dans les versions anterieures on utilisait Zope)
    Les icones sont des fichiers PNG dans .../static/icons
    Si la taille (width et height) n'est pas spécifiée, lit l'image
    pour la mesurer (et cache le résultat).
    """
    if (not no_size) and (("width" not in attrs) or ("height" not in attrs)):
        if name not in ICONSIZES:
            img_file = os.path.join(
                Config.SCODOC_DIR,
                "app/static/icons/%s.%s"
                % (
                    name,
                    file_format,
                ),
            )
            im = PILImage.open(img_file)
            width, height = im.size[0], im.size[1]
            ICONSIZES[name] = (width, height)  # cache
        else:
            width, height = ICONSIZES[name]
        attrs["width"] = width
        attrs["height"] = height
    if "border" not in attrs:
        attrs["border"] = 0
    if "alt" not in attrs:
        attrs["alt"] = "logo %s" % name
    s = " ".join(['%s="%s"' % (k, attrs[k]) for k in attrs])
    return '<img class="%s" %s src="/ScoDoc/static/icons/%s.%s" />' % (
        name,
        s,
        name,
        file_format,
    )


ICON_PDF = icontag("pdficon16x20_img", title="Version PDF")
ICON_XLS = icontag("xlsicon_img", title="Version tableur")


def sort_dates(L, reverse=False):
    """Return sorted list of dates, allowing None items (they are put at the beginning)"""
    mindate = datetime.datetime(datetime.MINYEAR, 1, 1)
    try:
        return sorted(L, key=lambda x: x or mindate, reverse=reverse)
    except:
        # Helps debugging
        log("sort_dates( %s )" % L)
        raise


def query_portal(req, msg="Portail Apogee", timeout=3):
    """Retreives external data using HTTP request
    (used to connect to Apogee portal, or ScoDoc server)
    returns a string,  "" on error
    """
    log("query_portal: %s" % req)

    try:
        r = requests.get(req, timeout=timeout)  # seconds / request
    except:
        log("query_portal: can't connect to %s" % msg)
        return ""
    if r.status_code != 200:
        log(f"query_portal: http error {r.status_code}")
        return ""  # XXX ou raise exception ?

    return r.text


def AnneeScolaire(sco_year=None):
    "annee de debut de l'annee scolaire courante"
    if sco_year:
        year = sco_year
        try:
            year = int(year)
            if year > 1900 and year < 2999:
                return year
        except:
            raise sco_exceptions.ScoValueError("invalid sco_year")
    t = time.localtime()
    year, month = t[0], t[1]
    if month < 8:  # le "pivot" est le 1er aout
        year = year - 1
    return year


def confirm_dialog(
    message="<p>Confirmer ?</p>",
    OK="OK",
    Cancel="Annuler",
    dest_url="",
    cancel_url="",
    target_variable="dialog_confirmed",
    parameters={},
    add_headers=True,  # complete page
    helpmsg=None,
):
    from app.scodoc import html_sco_header

    # dialog de confirmation simple
    parameters[target_variable] = 1
    # Attention: la page a pu etre servie en GET avec des parametres
    # si on laisse l'url "action" vide, les parametres restent alors que l'on passe en POST...
    if not dest_url:
        action = ""
    else:
        # strip remaining parameters from destination url:
        dest_url = urllib.parse.splitquery(dest_url)[0]
        action = f'action="{dest_url}"'

    H = [
        f"""<form {action} method="POST">
        {message}
        """,
    ]
    if OK or not cancel_url:
        H.append(f'<input type="submit" value="{OK}"/>')
    if cancel_url:
        H.append(
            """<input type ="button" value="%s"
            onClick="document.location='%s';"/>"""
            % (Cancel, cancel_url)
        )
    for param in parameters.keys():
        if parameters[param] is None:
            parameters[param] = ""
        if type(parameters[param]) == type([]):
            for e in parameters[param]:
                H.append('<input type="hidden" name="%s" value="%s"/>' % (param, e))
        else:
            H.append(
                '<input type="hidden" name="%s" value="%s"/>'
                % (param, parameters[param])
            )
    H.append("</form>")
    if helpmsg:
        H.append('<p class="help">' + helpmsg + "</p>")
    if add_headers:
        return (
            html_sco_header.sco_header() + "\n".join(H) + html_sco_header.sco_footer()
        )
    else:
        return "\n".join(H)
