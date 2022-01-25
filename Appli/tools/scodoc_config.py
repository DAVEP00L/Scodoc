# -*- mode: python -*-
# -*- coding: utf-8 -*-

#
# Configuration globale de ScoDoc (version juin 2009)
#

# La plupart des réglages sont stoqués en base de donnée et accessibles via le web
# (pages de paramètres ou préférences).
# Les valeurs indiquées ici sont les valeurs initiales que prendront
# les paramètres lors de la création d'un nouveau département,
# elles ne sont plus utilisées ensuite.

# Nota: il y a aussi des réglages dans sco_utils.py, mais ils nécessitent
# souvent de comprendre le code qui les utilise pour ne pas faire d'erreur: attention.


class CFG(object):
    pass


CONFIG = CFG()

CONFIG.always_require_ine = 0  # set to 1 if you want to require INE

#
#   ------------- Documents PDF -------------
#
CONFIG.SCOLAR_FONT = "Helvetica"
CONFIG.SCOLAR_FONT_SIZE = 10
CONFIG.SCOLAR_FONT_SIZE_FOOT = 6

# Pour pieds de pages Procès verbaux:
#  (markup leger reportlab supporté, par ex. <b>blah blah</b>)
CONFIG.INSTITUTION_NAME = (
    "<b>Institut Universitaire de Technologie - Université Georges Perec</b>"
)
CONFIG.INSTITUTION_ADDRESS = (
    "Web <b>www.sor.bonne.top</b> - 11, rue Simon Crubelier  - 75017 Paris"
)

CONFIG.INSTITUTION_CITY = "Paris"


# Taille du l'image logo: largeur/hauteur  (ne pas oublier le . !!!)
CONFIG.LOGO_FOOTER_ASPECT = (
    326 / 96.0
)  # W/H    XXX provisoire: utilisera PIL pour connaitre la taille de l'image
CONFIG.LOGO_FOOTER_HEIGHT = 10  # taille dans le document en millimetres

CONFIG.LOGO_HEADER_ASPECT = 549 / 346.0  # XXX logo IUTV
CONFIG.LOGO_HEADER_HEIGHT = 28  # taille verticale dans le document en millimetres

# Pied de page PDF : un format Python, %(xxx)s est remplacé par la variable xxx.
# Les variables définies sont:
#   day   : Day of the month as a decimal number [01,31]
#   month : Month as a decimal number [01,12].
#   year  : Year without century as a decimal number [00,99].
#   Year  : Year with century as a decimal number.
#   hour  : Hour (24-hour clock) as a decimal number [00,23].
#   minute: Minute as a decimal number [00,59].
#
#   server_url: URL du serveur ScoDoc
#   scodoc_name: le nom du logiciel (ScoDoc actuellement, voir sco_version.py)

CONFIG.DEFAULT_PDF_FOOTER_TEMPLATE = "Edité par %(scodoc_name)s le %(day)s/%(month)s/%(year)s à %(hour)sh%(minute)s sur %(server_url)s"


#
#   ------------- Capitalisation des UEs -------------
# Deux écoles:
#   - règle "DUT": capitalisation des UE obtenues avec moyenne UE >= 10 ET de toutes les UE
#                   des semestres validés (ADM, ADC, AJ). (conforme à l'arrêté d'août 2005)
#
#   - règle "LMD": capitalisation uniquement des UE avec moy. > 10

# XXX à revoir pour le BUT: variable à intégrer aux parcours
CONFIG.CAPITALIZE_ALL_UES = (
    True  # si vrai, capitalise toutes les UE des semestres validés (règle "LMD").
)


#
# -----------------------------------------------------
#
# -------------- Personnalisation des pages (DEPRECATED)
#
# -----------------------------------------------------
# Nom (chemin complet) d'un fichier .html à inclure juste après le <body>
#  le <body> des pages ScoDoc
CONFIG.CUSTOM_HTML_HEADER = ""

# Fichier html a inclure en fin des pages (juste avant le </body>)
CONFIG.CUSTOM_HTML_FOOTER = ""

# Fichier .html à inclure dans la pages connexion/déconnexion (accueil)
# si on veut que ce soit différent (par défaut la même chose)
CONFIG.CUSTOM_HTML_HEADER_CNX = CONFIG.CUSTOM_HTML_HEADER
CONFIG.CUSTOM_HTML_FOOTER_CNX = CONFIG.CUSTOM_HTML_FOOTER


# -----------------------------------------------------
#
# -------------- Noms de Lycées
#
# -----------------------------------------------------

# Fichier de correspondance codelycee -> noms
# (dans tools/)
CONFIG.ETABL_FILENAME = "etablissements.csv"


# ----------------------------------------------------
CONFIG.ALLOW_NULL_PRENOM = False  # True for UCAC (étudiants camerounais sans prénoms)

CONFIG.ETUD_MAX_FILE_SIZE = (
    10 * 1024 * 1024
)  # taille max des fichiers archive etudiants (en octets)

CONFIG.PUBLISH_PORTAL_PHOTO_URL = (
    False  # si pas de photo et portail, publie l'url (était vrai jusqu'en oct 2016)
)

CONFIG.MIN_PASSWORD_LENGTH = 0  # si > 0: longueur minimale requise des nouveaux mots de passe (le test cracklib.FascistCheck s'appliquera dans tous les cas)

# ----------------------------------------------------
# Ce dictionnaire est fusionné à celui de sco_codes_parcours
# pour définir les codes jury et explications associées
CONFIG.CODES_EXPL = {
    # AJ  : 'Ajourné (échec)',
}
