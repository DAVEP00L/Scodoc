# -*- mode: python -*-
# -*- coding: utf-8 -*-

#
# Configuration globale de ScoDoc (version juin 2009)
#   Ce fichier est copié dans /opt/scodoc-data/config
#   par les scripts d'installation/mise à jour.

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

# set to 1 if you want to require INE:
# CONFIG.always_require_ine = 0

# The base URL, use only if you are behind a proxy
#  eg "https://scodoc.example.net/ScoDoc"
# CONFIG.ABSOLUTE_URL = ""

# -----------------------------------------------------
# -------------- Documents PDF
# -----------------------------------------------------

# Taille du l'image logo: largeur/hauteur  (ne pas oublier le . !!!)
# W/H    XXX provisoire: utilisera PIL pour connaitre la taille de l'image
# CONFIG.LOGO_FOOTER_ASPECT = 326 / 96.0
# Taille dans le document en millimetres
# CONFIG.LOGO_FOOTER_HEIGHT = 10
# Proportions logo (donné ici pour IUTV)
# CONFIG.LOGO_HEADER_ASPECT = 549 / 346.0
# Taille verticale dans le document en millimetres
# CONFIG.LOGO_HEADER_HEIGHT = 28

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

# CONFIG.DEFAULT_PDF_FOOTER_TEMPLATE = "Edité par %(scodoc_name)s le %(day)s/%(month)s/%(year)s à %(hour)sh%(minute)s sur %(server_url)s"


#
#   ------------- Capitalisation des UEs -------------
# Deux écoles:
#   - règle "DUT": capitalisation des UE obtenues avec moyenne UE >= 10 ET de toutes les UE
#                   des semestres validés (ADM, ADC, AJ). (conforme à l'arrêté d'août 2005)
#
#   - règle "LMD": capitalisation uniquement des UE avec moy. > 10

# Si vrai, capitalise toutes les UE des semestres validés (règle "DUT").
# CONFIG.CAPITALIZE_ALL_UES = True


#
# -----------------------------------------------------
#
# -------------- Personnalisation des pages
#
# -----------------------------------------------------
# Nom (chemin complet) d'un fichier .html à inclure juste après le <body>
#  le <body> des pages ScoDoc
# CONFIG.CUSTOM_HTML_HEADER = ""

# Fichier html a inclure en fin des pages (juste avant le </body>)
# CONFIG.CUSTOM_HTML_FOOTER = ""

# Fichier .html à inclure dans la pages connexion/déconnexion (accueil)
# si on veut que ce soit différent (par défaut la même chose)
# CONFIG.CUSTOM_HTML_HEADER_CNX = CONFIG.CUSTOM_HTML_HEADER
# CONFIG.CUSTOM_HTML_FOOTER_CNX = CONFIG.CUSTOM_HTML_FOOTER


# -----------------------------------------------------
# -------------- Noms de Lycées
# -----------------------------------------------------
# Fichier de correspondance codelycee -> noms
# CONFIG.ETABL_FILENAME = "etablissements.csv"


# ----------------------------------------------------
# -------------- Divers:
# ----------------------------------------------------
# True for UCAC (étudiants camerounais sans prénoms)
# CONFIG.ALLOW_NULL_PRENOM = False

# Taille max des fichiers archive etudiants (en octets)
# CONFIG.ETUD_MAX_FILE_SIZE = 10 * 1024 * 1024

# Si pas de photo et portail, publie l'url (était vrai jusqu'en oct 2016)
# CONFIG.PUBLISH_PORTAL_PHOTO_URL = False

# Si > 0: longueur minimale requise des nouveaux mots de passe
# (le test cracklib.FascistCheck s'appliquera dans tous les cas)
# CONFIG.MIN_PASSWORD_LENGTH = 0


# Ce dictionnaire est fusionné à celui de sco_codes_parcours
# pour définir les codes jury et explications associées
# CONFIG.CODES_EXPL = {
#    # AJ  : 'Ajourné (échec)',
# }
