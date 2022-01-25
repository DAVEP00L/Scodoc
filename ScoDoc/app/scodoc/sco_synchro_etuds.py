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

"""Synchronisation des listes d'étudiants avec liste portail (Apogée)
"""

import time
import pprint
from operator import itemgetter

from flask import g, url_for
from flask_login import current_user

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_inscriptions
from app.scodoc import sco_groups
from app.scodoc import sco_inscr_passage
from app.scodoc import sco_news
from app.scodoc import sco_excel
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_etud
from app import log
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_permissions import Permission

# Clés utilisées pour la synchro
EKEY_APO = "nip"
EKEY_SCO = "code_nip"
EKEY_NAME = "code NIP"

# view:
def formsemestre_synchro_etuds(
    formsemestre_id,
    etuds=[],  # liste des codes NIP des etudiants a inscrire (ou deja inscrits)
    inscrits_without_key=[],  # codes etudid des etudiants sans code NIP a laisser inscrits
    anneeapogee=None,
    submitted=False,
    dialog_confirmed=False,
    export_cat_xls=None,
    read_only=False,  # Affiche sans permettre modifications
):
    """Synchronise les étudiants de ce semestre avec ceux d'Apogée.
    On a plusieurs cas de figure: L'étudiant peut être
    1- présent dans Apogée et inscrit dans le semestre ScoDoc (etuds_ok)
    2- dans Apogée, dans ScoDoc, mais pas inscrit dans le semestre (etuds_noninscrits)
    3- dans Apogée et pas dans ScoDoc (a_importer)
    4- inscrit dans le semestre ScoDoc, mais pas trouvé dans Apogée (sur la base du code NIP)

    Que faire ?
    Cas 1: rien à faire
    Cas 2: inscrire dans le semestre
    Cas 3: importer l'étudiant (le créer)
            puis l'inscrire à ce semestre.
    Cas 4: lister les etudiants absents d'Apogée (indiquer leur code NIP...)

    - présenter les différents cas
    - l'utilisateur valide (cocher les étudiants à importer/inscrire)
    - go

    etuds: apres sélection par l'utilisateur, la liste des étudiants selectionnés
    que l'on va importer/inscrire
    """
    log("formsemestre_synchro_etuds: formsemestre_id=%s" % formsemestre_id)
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    sem["etape_apo_str"] = sco_formsemestre.formsemestre_etape_apo_str(sem)
    # Write access ?
    if not current_user.has_permission(Permission.ScoEtudInscrit):
        read_only = True
    if read_only:
        submitted = False
        dialog_confirmed = False
    # -- check lock
    if not sem["etat"]:
        raise ScoValueError("opération impossible: semestre verrouille")
    if not sem["etapes"]:
        raise ScoValueError(
            """opération impossible: ce semestre n'a pas de code étape
        (voir "<a href="formsemestre_editwithmodules?formation_id=%(formation_id)s&formsemestre_id=%(formsemestre_id)s">Modifier ce semestre</a>")
        """
            % sem
        )
    header = html_sco_header.sco_header(page_title="Synchronisation étudiants")
    footer = html_sco_header.sco_footer()
    base_url = url_for(
        "notes.formsemestre_synchro_etuds",
        scodoc_dept=g.scodoc_dept,
        formsemestre_id=formsemestre_id,
        anneeapogee=anneeapogee or None,  # si None, le param n'est pas dans l'URL
    )

    if anneeapogee is None:  # année d'inscription par défaut
        anneeapogee = scu.annee_scolaire_debut(
            sem["annee_debut"], sem["mois_debut_ord"]
        )
    anneeapogee = str(anneeapogee)

    if isinstance(etuds, str):
        etuds = etuds.split(",")  # vient du form de confirmation
    elif isinstance(etuds, int):
        etuds = [etuds]
    if isinstance(inscrits_without_key, int):
        inscrits_without_key = [inscrits_without_key]
    elif isinstance(inscrits_without_key, str):
        inscrits_without_key = inscrits_without_key.split(",")
    elif not isinstance(inscrits_without_key, list):
        raise ValueError("invalid type for inscrits_without_key")
    inscrits_without_key = [int(x) for x in inscrits_without_key if x]
    (
        etuds_by_cat,
        a_importer,
        a_inscrire,
        inscrits_set,
        inscrits_without_key_all,
        etudsapo_ident,
    ) = list_synch(sem, anneeapogee=anneeapogee)
    if export_cat_xls:
        filename = export_cat_xls
        xls = build_page(
            sem,
            etuds_by_cat,
            anneeapogee,
            export_cat_xls=export_cat_xls,
            base_url=base_url,
            read_only=read_only,
        )
        return scu.send_file(
            xls,
            mime=scu.XLS_MIMETYPE,
            filename=filename,
            suffix=scu.XLSX_SUFFIX,
        )

    H = [header]
    if not submitted:
        H += build_page(
            sem,
            etuds_by_cat,
            anneeapogee,
            base_url=base_url,
            read_only=read_only,
        )
    else:
        etuds_set = set(etuds)
        a_importer = a_importer.intersection(etuds_set)
        a_desinscrire = inscrits_set - etuds_set
        log("inscrits_without_key_all=%s" % set(inscrits_without_key_all))
        log("inscrits_without_key=%s" % inscrits_without_key)
        a_desinscrire_without_key = set(inscrits_without_key_all) - set(
            inscrits_without_key
        )
        log("a_desinscrire_without_key=%s" % a_desinscrire_without_key)
        inscrits_ailleurs = set(sco_inscr_passage.list_inscrits_date(sem))
        a_inscrire = a_inscrire.intersection(etuds_set)

        if not dialog_confirmed:
            # Confirmation
            if a_importer:
                H.append("<h3>Etudiants à importer et inscrire :</h3><ol>")
                for key in a_importer:
                    H.append("<li>%(fullname)s</li>" % etudsapo_ident[key])
                H.append("</ol>")

            if a_inscrire:
                H.append("<h3>Etudiants à inscrire :</h3><ol>")
                for key in a_inscrire:
                    H.append("<li>%(fullname)s</li>" % etudsapo_ident[key])
                H.append("</ol>")

            a_inscrire_en_double = inscrits_ailleurs.intersection(a_inscrire)
            if a_inscrire_en_double:
                H.append("<h3>dont étudiants déjà inscrits:</h3><ol>")
                for key in a_inscrire_en_double:
                    H.append(
                        '<li class="inscrailleurs">%(fullname)s</li>'
                        % etudsapo_ident[key]
                    )
                H.append("</ol>")

            if a_desinscrire:
                H.append("<h3>Etudiants à désinscrire :</h3><ol>")
                for key in a_desinscrire:
                    etud = sco_etud.get_etud_info(filled=True, code_nip=key)[0]
                    H.append('<li class="desinscription">%(nomprenom)s</li>' % etud)
                H.append("</ol>")
            if a_desinscrire_without_key:
                H.append("<h3>Etudiants à désinscrire (sans code):</h3><ol>")
                for etudid in a_desinscrire_without_key:
                    etud = inscrits_without_key_all[etudid]
                    sco_etud.format_etud_ident(etud)
                    H.append('<li class="desinscription">%(nomprenom)s</li>' % etud)
                H.append("</ol>")

            todo = (
                a_importer or a_inscrire or a_desinscrire or a_desinscrire_without_key
            )
            if not todo:
                H.append("""<h3>Il n'y a rien à modifier !</h3>""")
            H.append(
                scu.confirm_dialog(
                    dest_url="formsemestre_synchro_etuds",
                    add_headers=False,
                    cancel_url="formsemestre_synchro_etuds?formsemestre_id="
                    + str(formsemestre_id),
                    OK="Effectuer l'opération" if todo else "OK",
                    parameters={
                        "formsemestre_id": formsemestre_id,
                        "etuds": ",".join(etuds),
                        "inscrits_without_key": ",".join(
                            [str(x) for x in inscrits_without_key]
                        ),
                        "submitted": 1,
                        "anneeapogee": anneeapogee,
                    },
                )
            )
        else:
            # OK, do it

            # Conversions des listes de codes NIP en listes de codes etudid
            def nip2etudid(code_nip):
                etud = sco_etud.get_etud_info(code_nip=code_nip)[0]
                return etud["etudid"]

            etudids_a_inscrire = [nip2etudid(x) for x in a_inscrire]
            etudids_a_desinscrire = [nip2etudid(x) for x in a_desinscrire]
            etudids_a_desinscrire += a_desinscrire_without_key
            #
            with sco_cache.DefferedSemCacheManager():
                do_import_etuds_from_portal(sem, a_importer, etudsapo_ident)
                sco_inscr_passage.do_inscrit(sem, etudids_a_inscrire)
                sco_inscr_passage.do_desinscrit(sem, etudids_a_desinscrire)

            H.append(
                """<h3>Opération effectuée</h3>
            <ul>
                <li><a class="stdlink" href="formsemestre_synchro_etuds?formsemestre_id=%s">Continuer la synchronisation</a></li>"""
                % formsemestre_id
            )
            #
            partitions = sco_groups.get_partitions_list(
                formsemestre_id, with_default=False
            )
            if partitions:  # il y a au moins une vraie partition
                H.append(
                    f"""<li><a class="stdlink" href="{
                        url_for("scolar.affect_groups",
                scodoc_dept=g.scodoc_dept,
                partition_id=partitions[0]["partition_id"]
                )}">Répartir les groupes de {partitions[0]["partition_name"]}</a></li>
                """
                )

    H.append(footer)
    return "\n".join(H)


def build_page(
    sem,
    etuds_by_cat,
    anneeapogee,
    export_cat_xls=None,
    base_url="",
    read_only=False,
):
    if export_cat_xls:
        return sco_inscr_passage.etuds_select_boxes(
            etuds_by_cat, export_cat_xls=export_cat_xls, base_url=base_url
        )
    year = time.localtime()[0]
    if anneeapogee and abs(year - int(anneeapogee)) < 50:
        years = list(
            range(min(year - 1, int(anneeapogee) - 1), max(year, int(anneeapogee)) + 1)
        )
    else:
        years = list(range(year - 1, year + 1))
        anneeapogee = ""
    options = []
    for y in years:
        if str(y) == anneeapogee:
            sel = "selected"
        else:
            sel = ""
        options.append('<option value="%s" %s>%s</option>' % (str(y), sel, str(y)))
    if anneeapogee:
        sel = ""
    else:
        sel = "selected"
    options.append('<option value="" %s>toutes</option>' % sel)
    # sem['etape_apo_str'] = sem['etape_apo'] or '-'

    H = [
        """<h2 class="formsemestre">Synchronisation des étudiants du semestre avec Apogée</h2>""",
        """<p>Actuellement <b>%d</b> inscrits dans ce semestre.</p>"""
        % (
            len(etuds_by_cat["etuds_ok"]["etuds"])
            + len(etuds_by_cat["etuds_nonapogee"]["etuds"])
            + len(etuds_by_cat["inscrits_without_key"]["etuds"])
        ),
        """<p>Code étape Apogée: %(etape_apo_str)s</p>
        <form method="post" action="formsemestre_synchro_etuds">
        """
        % sem,
        """
        Année Apogée: <select id="anneeapogee" name="anneeapogee" 
        onchange="document.location='formsemestre_synchro_etuds?formsemestre_id=%s&anneeapogee='+document.getElementById('anneeapogee').value">"""
        % (sem["formsemestre_id"]),
        "\n".join(options),
        """
        </select>
        """,
        ""
        if read_only
        else """
        <input type="hidden" name="formsemestre_id" value="%(formsemestre_id)s"/>
        <input type="submit" name="submitted" value="Appliquer les modifications"/>
        &nbsp;<a href="#help">aide</a>
        """
        % sem,  # "
        sco_inscr_passage.etuds_select_boxes(
            etuds_by_cat,
            sel_inscrits=False,
            show_empty_boxes=True,
            base_url=base_url,
            read_only=read_only,
        ),
        ""
        if read_only
        else """<p/><input type="submit" name="submitted" value="Appliquer les modifications"/>""",
        formsemestre_synchro_etuds_help(sem),
        """</form>""",
    ]
    return H


def list_synch(sem, anneeapogee=None):
    """"""
    inscrits = sco_inscr_passage.list_inscrits(sem["formsemestre_id"], with_dems=True)
    # Tous les ensembles d'etudiants sont ici des ensembles de codes NIP (voir EKEY_SCO)
    # (sauf inscrits_without_key)
    inscrits_set = set()
    inscrits_without_key = {}  # etudid : etud sans code NIP
    for e in inscrits.values():
        if not e[EKEY_SCO]:
            inscrits_without_key[e["etudid"]] = e
            e["inscrit"] = True  # checkbox state
        else:
            inscrits_set.add(e[EKEY_SCO])
    #     allinscrits_set = set() # tous les inscrits scodoc avec code_nip, y compris les demissionnaires
    #     for e in inscrits.values():
    #         if e[EKEY_SCO]:
    #             allinscrits_set.add(e[EKEY_SCO])

    datefinalisationinscription_by_NIP = {}  # nip : datefinalisationinscription_str

    etapes = sem["etapes"]
    etudsapo_set = set()
    etudsapo_ident = {}
    for etape in etapes:
        if etape:
            etudsapo = sco_portal_apogee.get_inscrits_etape(
                etape, anneeapogee=anneeapogee
            )
            etudsapo_set = etudsapo_set.union(set([x[EKEY_APO] for x in etudsapo]))
            for e in etudsapo:
                if e[EKEY_APO] not in etudsapo_ident:
                    etudsapo_ident[e[EKEY_APO]] = e
                datefinalisationinscription_by_NIP[e[EKEY_APO]] = e[
                    "datefinalisationinscription"
                ]

    # categories:
    etuds_ok = etudsapo_set.intersection(inscrits_set)
    etuds_aposco, a_importer, key2etudid = list_all(etudsapo_set)
    etuds_noninscrits = etuds_aposco - inscrits_set
    etuds_nonapogee = inscrits_set - etudsapo_set
    # Etudiants ayant payé (avec balise <paiementinscription> true)
    # note: si le portail ne renseigne pas cette balise, suppose que paiement ok
    etuds_payes = set(
        [x[EKEY_APO] for x in etudsapo if x.get("paiementinscription", True)]
    )
    #
    cnx = ndb.GetDBConnexion()
    # Tri listes
    def set_to_sorted_list(etudset, etud_apo=False, is_inscrit=False):
        def key2etud(key, etud_apo=False):
            if not etud_apo:
                etudid = key2etudid[key]
                etuds = sco_etud.identite_list(cnx, {"etudid": etudid})
                if not etuds:  # ? cela ne devrait pas arriver XXX
                    log(f"XXX key2etud etudid={{etudid}}, type {{type(etudid)}}")
                etud = etuds[0]
                etud["inscrit"] = is_inscrit  # checkbox state
                etud[
                    "datefinalisationinscription"
                ] = datefinalisationinscription_by_NIP.get(key, None)
                if key in etudsapo_ident:
                    etud["etape"] = etudsapo_ident[key].get("etape", "")
            else:
                # etudiant Apogee
                etud = etudsapo_ident[key]

                etud["etudid"] = ""
                etud["civilite"] = etud.get(
                    "sexe", etud.get("gender", "")
                )  # la cle 'sexe' est prioritaire sur 'gender'
                etud["inscrit"] = is_inscrit  # checkbox state
            if key in etuds_payes:
                etud["paiementinscription"] = True
            else:
                etud["paiementinscription"] = False
            return etud

        etuds = [key2etud(x, etud_apo) for x in etudset]
        etuds.sort(key=itemgetter("nom"))
        return etuds

    #
    boites = {
        "etuds_a_importer": {
            "etuds": set_to_sorted_list(a_importer, is_inscrit=True, etud_apo=True),
            "infos": {
                "id": "etuds_a_importer",
                "title": "Etudiants dans Apogée à importer",
                "help": """Ces étudiants sont inscrits dans cette étape Apogée mais ne sont pas connus par ScoDoc: 
                cocher les noms à importer et inscrire puis appuyer sur le bouton "Appliquer".""",
                "title_target": "",
                "with_checkbox": True,
                "etud_key": EKEY_APO,  # clé à stocker dans le formulaire html
                "filename": "etuds_a_importer",
            },
            "nomprenoms": etudsapo_ident,
        },
        "etuds_noninscrits": {
            "etuds": set_to_sorted_list(etuds_noninscrits, is_inscrit=True),
            "infos": {
                "id": "etuds_noninscrits",
                "title": "Etudiants non inscrits dans ce semestre",
                "help": """Ces étudiants sont déjà connus par ScoDoc, sont inscrits dans cette étape Apogée mais ne sont pas inscrits à ce semestre ScoDoc. Cochez les étudiants à inscrire.""",
                "comment": """ dans ScoDoc et Apogée, <br/>mais pas inscrits
                      dans ce semestre""",
                "title_target": "",
                "with_checkbox": True,
                "etud_key": EKEY_SCO,
                "filename": "etuds_non_inscrits",
            },
        },
        "etuds_nonapogee": {
            "etuds": set_to_sorted_list(etuds_nonapogee, is_inscrit=True),
            "infos": {
                "id": "etuds_nonapogee",
                "title": "Etudiants ScoDoc inconnus dans cette étape Apogée",
                "help": """Ces étudiants sont inscrits dans ce semestre ScoDoc, ont un code NIP, mais ne sont pas inscrits dans cette étape Apogée. Soit ils sont en retard pour leur inscription, soit il s'agit d'une erreur: vérifiez avec le service Scolarité de votre établissement. Autre possibilité: votre code étape semestre (%s) est incorrect ou vous n'avez pas choisi la bonne année d'inscription."""
                % sem["etape_apo_str"],
                "comment": " à vérifier avec la Scolarité",
                "title_target": "",
                "with_checkbox": True,
                "etud_key": EKEY_SCO,
                "filename": "etuds_non_apogee",
            },
        },
        "inscrits_without_key": {
            "etuds": list(inscrits_without_key.values()),
            "infos": {
                "id": "inscrits_without_key",
                "title": "Etudiants ScoDoc sans clé Apogée (NIP)",
                "help": """Ces étudiants sont inscrits dans ce semestre ScoDoc, mais n'ont pas de code NIP: on ne peut pas les mettre en correspondance avec Apogée. Utiliser le lien 'Changer les données identité' dans le menu 'Etudiant' sur leur fiche pour ajouter cette information.""",
                "title_target": "",
                "with_checkbox": True,
                "checkbox_name": "inscrits_without_key",
                "filename": "inscrits_without_key",
            },
        },
        "etuds_ok": {
            "etuds": set_to_sorted_list(etuds_ok, is_inscrit=True),
            "infos": {
                "id": "etuds_ok",
                "title": "Etudiants dans Apogée et déjà inscrits",
                "help": """Ces etudiants sont inscrits dans le semestre ScoDoc et sont présents dans Apogée: 
                tout est donc correct. Décocher les étudiants que vous souhaitez désinscrire.""",
                "title_target": "",
                "with_checkbox": True,
                "etud_key": EKEY_SCO,
                "filename": "etuds_inscrits_ok_apo",
            },
        },
    }
    return (
        boites,
        a_importer,
        etuds_noninscrits,
        inscrits_set,
        inscrits_without_key,
        etudsapo_ident,
    )


def list_all(etudsapo_set):
    """Cherche le sous-ensemble des etudiants Apogee de ce semestre
    qui existent dans ScoDoc.
    """
    # on charge TOUS les etudiants (au pire qq 100000 ?)
    # si tres grosse base, il serait mieux de faire une requete
    # d'interrogation par etudiant.
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        "SELECT "
        + EKEY_SCO
        + """, id AS etudid
        FROM identite WHERE dept_id=%(dept_id)s
        """,
        {"dept_id": g.scodoc_dept_id},
    )
    key2etudid = dict([(x[0], x[1]) for x in cursor.fetchall()])
    all_set = set(key2etudid.keys())

    # ne retient que ceux dans Apo
    etuds_aposco = etudsapo_set.intersection(
        all_set
    )  # a la fois dans Apogee et dans ScoDoc
    a_importer = etudsapo_set - all_set  # dans Apogee, mais inconnus dans ScoDoc
    return etuds_aposco, a_importer, key2etudid


def formsemestre_synchro_etuds_help(sem):
    sem["default_group_id"] = sco_groups.get_default_group(sem["formsemestre_id"])
    return (
        """<div class="pas_help pas_help_left"><h3><a name="help">Explications</a></h3>
    <p>Cette page permet d'importer dans le semestre destination
    <a class="stdlink"
    href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titreannee)s</a>
    les étudiants inscrits dans l'étape Apogée correspondante (<b><tt>%(etape_apo_str)s</tt></b>) 
    </p>
    <p>Au départ, tous les étudiants d'Apogée sont sélectionnés; vous pouvez
    en déselectionner certains. Tous les étudiants cochés seront inscrits au semestre ScoDoc,
    les autres seront si besoin désinscrits. Aucune modification n'est effectuée avant
    d'appuyer sur le bouton "Appliquer les modifications".</p>

    <h4>Autres fonctions utiles</h4>
    <ul>
    <li><a href="check_group_apogee?group_id=%(default_group_id)s">vérification
    des codes Apogée</a> (des étudiants déjà inscrits)</li>
    <li>le <a href="formsemestre_inscr_passage?formsemestre_id=%(formsemestre_id)s">
    formulaire de passage</a> qui permet aussi de désinscrire des étudiants
    en cas d'erreur, etc.</li>
    </ul>
    </div>"""
        % sem
    )


def gender2civilite(gender):
    """Le portail code en 'M', 'F', et ScoDoc en 'M', 'F', 'X'"""
    if gender == "M" or gender == "F" or gender == "X":
        return gender
    elif not gender:
        return "X"
    log('gender2civilite: invalid value "%s", defaulting to "X"' % gender)
    return "X"  # "X" en général n'est pas affiché, donc bon choix si invalide


def get_opt_str(etud, k):
    v = etud.get(k, None)
    if not v:
        return v
    return v.strip()


def get_annee_naissance(ddmmyyyyy: str) -> int:
    """Extrait l'année de la date stockée en dd/mm/yyyy dans le XML portail"""
    if not ddmmyyyyy:
        return None
    try:
        return int(ddmmyyyyy.split("/")[2])
    except (ValueError, IndexError):
        return None


def do_import_etuds_from_portal(sem, a_importer, etudsapo_ident):
    """Inscrit les etudiants Apogee dans ce semestre."""
    log("do_import_etuds_from_portal: a_importer=%s" % a_importer)
    if not a_importer:
        return
    cnx = ndb.GetDBConnexion()
    created_etudids = []

    try:  # --- begin DB transaction
        for key in a_importer:
            etud = etudsapo_ident[
                key
            ]  # on a ici toutes les infos renvoyées par le portail

            # Traduit les infos portail en infos pour ScoDoc:
            address = etud.get("address", "").strip()
            if address[-2:] == "\\n":  # certains champs se terminent par \n
                address = address[:-2]

            args = {
                "code_nip": etud["nip"],
                "nom": etud["nom"].strip(),
                "prenom": etud["prenom"].strip(),
                # Les champs suivants sont facultatifs (pas toujours renvoyés par le portail)
                "code_ine": etud.get("ine", "").strip(),
                "civilite": gender2civilite(etud["gender"].strip()),
                "etape": etud.get("etape", None),
                "email": etud.get("mail", "").strip(),
                "emailperso": etud.get("mailperso", "").strip(),
                "date_naissance": etud.get("naissance", "").strip(),
                "lieu_naissance": etud.get("ville_naissance", "").strip(),
                "dept_naissance": etud.get("code_dep_naissance", "").strip(),
                "domicile": address,
                "codepostaldomicile": etud.get("postalcode", "").strip(),
                "villedomicile": etud.get("city", "").strip(),
                "paysdomicile": etud.get("country", "").strip(),
                "telephone": etud.get("phone", "").strip(),
                "typeadresse": "domicile",
                "boursier": etud.get("bourse", None),
                "description": "infos portail",
            }

            # Identite
            args["etudid"] = sco_etud.identite_create(cnx, args)
            created_etudids.append(args["etudid"])
            # Admissions
            do_import_etud_admission(cnx, args["etudid"], etud)

            # Adresse
            sco_etud.adresse_create(cnx, args)

            # Inscription au semestre
            sco_formsemestre_inscriptions.do_formsemestre_inscription_with_modules(
                sem["formsemestre_id"],
                args["etudid"],
                etat="I",
                etape=args["etape"],
                method="synchro_apogee",
            )
    except:
        cnx.rollback()
        log("do_import_etuds_from_portal: aborting transaction !")
        # Nota: db transaction is sometimes partly commited...
        # here we try to remove all created students
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        for etudid in created_etudids:
            log("do_import_etuds_from_portal: deleting etudid=%s" % etudid)
            cursor.execute(
                "delete from notes_moduleimpl_inscription where etudid=%(etudid)s",
                {"etudid": etudid},
            )
            cursor.execute(
                "delete from notes_formsemestre_inscription where etudid=%(etudid)s",
                {"etudid": etudid},
            )
            cursor.execute(
                "delete from scolar_events where etudid=%(etudid)s", {"etudid": etudid}
            )
            cursor.execute(
                "delete from adresse where etudid=%(etudid)s", {"etudid": etudid}
            )
            cursor.execute(
                "delete from admissions where etudid=%(etudid)s", {"etudid": etudid}
            )
            cursor.execute(
                "delete from group_membership where etudid=%(etudid)s",
                {"etudid": etudid},
            )
            cursor.execute(
                "delete from identite where id=%(etudid)s", {"etudid": etudid}
            )
        cnx.commit()
        log("do_import_etuds_from_portal: re-raising exception")
        # > import: modif identite, adresses, inscriptions
        sco_cache.invalidate_formsemestre()
        raise

    sco_news.add(
        typ=sco_news.NEWS_INSCR,
        text="Import Apogée de %d étudiants en " % len(created_etudids),
        object=sem["formsemestre_id"],
    )


def do_import_etud_admission(
    cnx, etudid, etud, import_naissance=False, import_identite=False
):
    """Importe les donnees admission pour cet etud.
    etud est un dictionnaire traduit du XML portail
    """
    annee_courante = time.localtime()[0]
    serie_bac, spe_bac = get_bac(etud)
    args = {
        "etudid": etudid,
        "annee": get_opt_str(etud, "inscription") or annee_courante,
        "bac": serie_bac,
        "specialite": spe_bac,
        "annee_bac": get_opt_str(etud, "anneebac"),
        "codelycee": get_opt_str(etud, "lycee"),
        "boursier": get_opt_str(etud, "bourse"),
    }
    # log("do_import_etud_admission: etud=%s" % pprint.pformat(etud))
    al = sco_etud.admission_list(cnx, args={"etudid": etudid})
    if not al:
        sco_etud.admission_create(cnx, args)  # -> adm_id
    else:
        # existing data: merge
        e = al[0]
        if get_opt_str(etud, "inscription"):
            e["annee"] = args["annee"]
        keys = list(args.keys())
        for k in keys:
            if not args[k]:
                del args[k]
        e.update(args)
        sco_etud.admission_edit(cnx, e)
    # Traite cas particulier de la date de naissance pour anciens
    # etudiants IUTV
    if import_naissance:
        date_naissance = etud["naissance"].strip()
        if date_naissance:
            sco_etud.identite_edit_nocheck(
                cnx, {"etudid": etudid, "date_naissance": date_naissance}
            )
    # Reimport des identités
    if import_identite:
        args = {"etudid": etudid}
        # Les champs n'ont pas les mêmes noms dans Apogee et dans ScoDoc:
        fields_apo_sco = [
            ("naissance", "date_naissance"),
            ("ville_naissance", "lieu_naissance"),
            ("code_dep_naissance", "dept_naissance"),
            ("nom", "nom"),
            ("prenom", "prenom"),
            ("ine", "code_ine"),
            ("bourse", "boursier"),
        ]
        for apo_field, sco_field in fields_apo_sco:
            x = etud.get(apo_field, "").strip()
            if x:
                args[sco_field] = x
        # Champs spécifiques:
        civilite = gender2civilite(etud["gender"].strip())
        if civilite:
            args["civilite"] = civilite

        sco_etud.identite_edit_nocheck(cnx, args)


def get_bac(etud):
    bac = get_opt_str(etud, "bac")
    if not bac:
        return None, None
    serie_bac = bac.split("-")[0]
    if len(serie_bac) < 8:
        spe_bac = bac[len(serie_bac) + 1 :]
    else:
        serie_bac = bac
        spe_bac = None
    return serie_bac, spe_bac


def update_etape_formsemestre_inscription(ins, etud):
    """Met à jour l'étape de l'inscription.

    Args:
        ins (dict): formsemestre_inscription
        etud (dict): etudiant portail Apo
    """
    if etud["etape"] != ins["etape"]:
        ins["etape"] = etud["etape"]
        sco_formsemestre_inscriptions.do_formsemestre_inscription_edit(args=ins)


def formsemestre_import_etud_admission(
    formsemestre_id, import_identite=True, import_email=False
):
    """Tente d'importer les données admission depuis le portail
    pour tous les étudiants du semestre.
    Si  import_identite==True, recopie l'identité (nom/prenom/sexe/date_naissance)
    de chaque étudiant depuis le portail.
    N'affecte pas les etudiants inconnus sur le portail.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        {"formsemestre_id": formsemestre_id}
    )
    log(
        "formsemestre_import_etud_admission: %s (%d etuds)"
        % (formsemestre_id, len(ins))
    )
    no_nip = []  # liste d'etudids sans code NIP
    unknowns = []  # etudiants avec NIP mais inconnus du portail
    changed_mails = []  # modification d'adresse mails
    cnx = ndb.GetDBConnexion()

    # Essaie de recuperer les etudiants des étapes, car
    # la requete get_inscrits_etape est en général beaucoup plus
    # rapide que les requetes individuelles get_etud_apogee
    anneeapogee = str(
        scu.annee_scolaire_debut(sem["annee_debut"], sem["mois_debut_ord"])
    )
    apo_etuds = {}  # nip : etud apo
    for etape in sem["etapes"]:
        etudsapo = sco_portal_apogee.get_inscrits_etape(etape, anneeapogee=anneeapogee)
        apo_etuds.update({e["nip"]: e for e in etudsapo})

    for i in ins:
        etudid = i["etudid"]
        info = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        code_nip = info["code_nip"]
        if not code_nip:
            no_nip.append(etudid)
        else:
            etud = apo_etuds.get(code_nip)
            if not etud:
                # pas vu dans les etudiants de l'étape, tente en individuel
                etud = sco_portal_apogee.get_etud_apogee(code_nip)
            if etud:
                update_etape_formsemestre_inscription(i, etud)
                do_import_etud_admission(
                    cnx,
                    etudid,
                    etud,
                    import_naissance=True,
                    import_identite=import_identite,
                )
                apo_emailperso = etud.get("mailperso", "")
                if info["emailperso"] and not apo_emailperso:
                    apo_emailperso = info["emailperso"]
                if (
                    import_email
                    and info["email"] != etud["mail"]
                    or info["emailperso"] != apo_emailperso
                ):
                    sco_etud.adresse_edit(
                        cnx,
                        args={
                            "etudid": etudid,
                            "adresse_id": info["adresse_id"],
                            "email": etud["mail"],
                            "emailperso": apo_emailperso,
                        },
                    )
                    # notifie seulement les changements d'adresse mail institutionnelle
                    if info["email"] != etud["mail"]:
                        changed_mails.append((info, etud["mail"]))
            else:
                unknowns.append(code_nip)
    sco_cache.invalidate_formsemestre(formsemestre_id=sem["formsemestre_id"])
    return no_nip, unknowns, changed_mails
