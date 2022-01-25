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

"""ScoDoc : formulaires gestion maquettes Apogee / export resultats
"""

import io
from zipfile import ZipFile

import flask
from flask import url_for, g, send_file, request

# from werkzeug.utils import send_file

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_apogee_csv
from app.scodoc import sco_etape_apogee
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app.scodoc import sco_semset
from app.scodoc import sco_etud
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_apogee_csv import APO_PORTAL_ENCODING, APO_INPUT_ENCODING
from app.scodoc.sco_exceptions import ScoValueError


def apo_semset_maq_status(
    semset_id="",
    allow_missing_apo=False,
    allow_missing_decisions=False,
    allow_missing_csv=False,
    block_export_res_etape=False,
    block_export_res_sem=False,
    block_export_res_ues=False,
    block_export_res_modules=False,
    block_export_res_sdj=True,
):
    """Page statut / tableau de bord"""
    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)
    semset.fill_formsemestres()
    # autorise export meme si etudiants Apo manquants:
    allow_missing_apo = int(allow_missing_apo)
    # autorise export meme s'il manque des décisions de jury:
    allow_missing_decisions = int(allow_missing_decisions)
    # autorise export même si maquette csv manquantes:
    allow_missing_csv = int(allow_missing_csv)
    block_export_res_etape = int(block_export_res_etape)
    block_export_res_sem = int(block_export_res_sem)
    block_export_res_ues = int(block_export_res_ues)
    block_export_res_modules = int(block_export_res_modules)
    block_export_res_sdj = int(block_export_res_sdj)

    prefs = sco_preferences.SemPreferences()

    tab_archives = table_apo_csv_list(semset)

    (
        ok_for_export,
        etapes_missing_csv,
        etuds_without_nip,
        nips_ok,
        nips_no_apo,
        nips_no_sco,
        apo_dups,
        maq_elems,
        sem_elems,
    ) = sco_etape_apogee.apo_csv_semset_check(
        semset, allow_missing_apo, allow_missing_csv
    )

    if not allow_missing_decisions:
        ok_for_export &= semset["jury_ok"]

    H = [
        html_sco_header.sco_header(
            page_title="Export Apogée",
            javascripts=["js/apo_semset_maq_status.js"],
        ),
        """<h2>Export des résultats vers Apogée</h2>"""
        """<div class="semset_descr">""",
        semset.html_descr(),
        semset.html_form_sems(),
        """</div>""",
    ]
    # Bilans code apogée
    H.append(semset.html_diagnostic())

    # Maquettes enregistrées
    H.append(
        """<div class="apo_csv_list">
    <span class="box_title">Maquettes Apogée</span>
    """
    )
    if not tab_archives.is_empty():
        H.append(tab_archives.html())
    else:
        H.append("""<p><em>Aucune maquette chargée</em></p>""")
    # Upload fichier:
    H.append(
        """<form id="apo_csv_add" action="view_apo_csv_store" method="post" enctype="multipart/form-data">
        Charger votre fichier maquette Apogée: 
        <input type="file" size="30" name="csvfile"/>
        <input type="hidden" name="semset_id" value="%s"/>
        <input type="submit" value="Ajouter ce fichier"/>
        <input type="checkbox" name="autodetect" checked/>autodétecter encodage</input>
        </form>"""
        % (semset_id,)
    )
    # Récupération sur portail:
    maquette_url = sco_portal_apogee.get_maquette_url()
    if maquette_url:  # portail configuré
        menu_etapes = """<option value=""></option>"""
        menu_etapes += "".join(
            ['<option value="%s">%s</option>' % (et, et) for et in semset.list_etapes()]
        )
        H.append(
            """<form id="apo_csv_download" action="view_apo_csv_download_and_store" method="post" enctype="multipart/form-data">
        Ou récupérer maquette Apogée pour une étape:
        <script type="text/javascript">
        function change_etape(e) {
           $('#apo_csv_download_submit_btn').attr('disabled', (e.value == ""));           
        }
        </script>
        <select name="etape_apo" onchange="change_etape(this);">
        %s
        </select>
        <input type="hidden" name="semset_id" value="%s"/>
        <input id="apo_csv_download_submit_btn" type="submit" value="Télécharger" disabled="disabled"/>
        </form>"""
            % (menu_etapes, semset_id)
        )
    #
    H.append("</div>")

    # Tableau de bord
    if ok_for_export:
        class_ok = "apo_csv_status_ok"
    else:
        class_ok = "apo_csv_status_nok"

    H.append('<div class="apo_csv_status %s">' % class_ok)
    if ok_for_export:
        H.append("""<span class="box_title">Exportation</span>""")
    else:
        H.append(
            """<span class="box_title">Problèmes à résoudre avant export des résultats:</span>"""
        )
    H.append('<div class="apo_csv_problems"><ul>')
    if len(semset.annees_scolaires()) > 1:
        H.append("""<li>Il y a plusieurs années scolaires !</li>""")

    if etapes_missing_csv:
        H.append(
            "<li>Etapes sans maquette: <tt>%s</tt></li>"
            % sco_formsemestre.etapes_apo_str(sorted(etapes_missing_csv))
        )

    if etuds_without_nip:
        H.append("<li>%d étudiants ScoDoc sans code NIP</li>" % len(etuds_without_nip))

    if nips_no_apo:
        url_list = url_for(
            "notes.view_scodoc_etuds",
            scodoc_dept=g.scodoc_dept,
            semset_id=semset_id,
            title="Etudiants ScoDoc non listés dans les maquettes Apogée chargées",
            nip_list=",".join(nips_no_apo),
        )
        H.append(
            '<li><a href="%s">%d étudiants</a> dans ce semestre non présents dans les maquettes Apogée chargées</li>'
            % (url_list, len(nips_no_apo))
        )

    if nips_no_sco:  # seulement un warning
        url_list = url_for(
            "notes.view_apo_etuds",
            scodoc_dept=g.scodoc_dept,
            semset_id=semset_id,
            title="Etudiants présents dans maquettes Apogée mais pas dans les semestres ScoDoc",
            nip_list=",".join(nips_no_sco),
        )
        H.append(
            '<li class="apo_csv_warning">Attention: il reste <a href="%s">%d étudiants</a> dans les maquettes Apogée chargées mais pas inscrits dans ce semestre ScoDoc</li>'
            % (url_list, len(nips_no_sco))
        )

    if apo_dups:
        url_list = url_for(
            "notes.view_apo_etuds",
            scodoc_dept=g.scodoc_dept,
            semset_id=semset_id,
            title="Doublons%%20Apogée",
            nip_list=",".join(apo_dups),
        )
        H.append(
            '<li><a href="%s">%d étudiants</a> présents dans les <em>plusieurs</em> maquettes Apogée chargées</li>'
            % (url_list, len(apo_dups))
        )

    H.append("</ul></div>")

    # Decisions de jury
    if semset["jury_ok"]:
        class_ok = "apo_csv_jury_ok"
    else:
        class_ok = "apo_csv_jury_nok"

    H.append('<div class="apo_csv_jury %s"><ul>' % class_ok)
    if semset["jury_ok"]:
        H.append("""<li>Décisions de jury saisies</li>""")
    else:
        H.append("""<li>Il manque des décisions de jury !</li>""")

    if ok_for_export:
        H.append("""<li>%d étudiants, prêt pour l'export.</li>""" % len(nips_ok))
    H.append("</ul></div>")

    H.append(
        """<form name="f" method="get" action="%s">
    <input type="hidden" name="semset_id" value="%s"></input>
    <div><input type="checkbox" name="allow_missing_apo" value="1" onchange="document.f.submit()" """
        % (request.base_url, semset_id)
    )
    if allow_missing_apo:
        H.append("checked")
    H.append(
        """ >autoriser export même si étudiants manquants dans Apogée</input></div>"""
    )
    H.append(
        """<div><input type="checkbox" name="allow_missing_decisions" value="1" onchange="document.f.submit()" """
    )
    if allow_missing_decisions:
        H.append("checked")
    H.append(
        """ >autoriser export même si des décisions de jury n'ont pas été saisies</input></div>"""
    )
    H.append(
        """<div><input type="checkbox" name="allow_missing_csv" value="1" onchange="document.f.submit()" """
    )
    if allow_missing_csv:
        H.append("checked")
    H.append(""" >autoriser export même si étapes sans maquettes</input></div>""")
    H.append("""</form>""")

    if semset and ok_for_export:
        H.append(
            """<form class="form_apo_export" action="apo_csv_export_results" method="get">        
        <input type="submit" value="Export vers Apogée">
        <input type="hidden" name="semset_id" value="%s"/>
        """
            % (semset_id,)
        )
        H.append('<div id="param_export_res">')

        def checked(block, pname, msg):
            if not prefs[pname]:
                return (
                    "disabled",
                    "checked",
                    "<em>export de " + msg + " désactivé dans les paramètres</em>",
                )
            if block:
                return "", "checked", "ne pas exporter " + msg
            else:
                return "", "", "ne pas exporter " + msg

        H.append(
            """<div><label><input type="checkbox" name="block_export_res_etape" value="1" %s %s>%s</input></label></div>"""
            % checked(
                block_export_res_etape,
                "export_res_etape",
                "résultat de l'étape (VET), sauf si diplôme",
            )
        )
        H.append(
            """<div><label><input type="checkbox" name="block_export_res_sem" value="1" %s %s/>%s</label></div>"""
            % checked(block_export_res_sem, "export_res_sem", "résultat du semestre")
        )
        H.append(
            """<div><label><input type="checkbox" name="block_export_res_ues" value="1" %s %s/>%s</label></div>"""
            % checked(block_export_res_ues, "export_res_ues", "résultats d'UE")
        )
        H.append(
            """<div><label><input type="checkbox" name="block_export_res_modules" value="1" %s %s/>%s</label></div>"""
            % checked(
                block_export_res_modules, "export_res_modules", "résultats de module"
            )
        )
        H.append(
            """<div><label><input type="checkbox" name="block_export_res_sdj" value="1" %s %s/>%s</label></div>"""
            % checked(
                block_export_res_sdj,
                "export_res_sdj",
                "résultats sans décision de jury",
            )
        )
        H.append("</div>")
        H.append("</form>")

    # Elements:
    missing = maq_elems - sem_elems
    H.append('<div id="apo_elements">')
    H.append(
        '<p>Elements Apogée: <span class="apo_elems">%s</span></p>'
        % ", ".join(
            [
                e if not e in missing else '<span class="missing">' + e + "</span>"
                for e in sorted(maq_elems)
            ]
        )
    )

    if missing:
        formation_ids = {sem["formation_id"] for sem in semset.sems}
        formations = [
            sco_formations.formation_list(formation_id=i)[0] for i in formation_ids
        ]
        # log('formations=%s' % formations)
        H.append(
            '<div class="apo_csv_status_missing_elems"><span class="fontred">Elements Apogée absents dans ScoDoc: </span><span class="apo_elems fontred">%s</span>'
            % ", ".join(sorted(missing))
        )
        H.append(
            '<div class="help">Ces éléments de la maquette Apogée ne sont pas déclarés dans ScoDoc et ne seront donc pas remplis.</div><div> Vous pouvez les déclarer dans les programmes pédagogiques: '
        )
        H.append(
            ", ".join(
                [
                    '<a class="stdlink"  href="ue_table?formation_id=%(formation_id)s">%(acronyme)s v%(version)s</a>'
                    % f
                    for f in formations
                ]
            )
        )
        H.append("</div></div>")

    H.append("</div>")
    H.append("</div>")
    # Aide:
    H.append(
        """
    <p><a class="stdlink" href="semset_page">Retour aux ensembles de semestres</a></p>
    
    <div class="pas_help">
    <h3>Explications</h3>
    <p>Cette page permet de stocker les fichiers Apogée nécessaires pour 
    l'export des résultats après les jurys, puis de remplir et exporter ces fichiers.
    </p>
    <p>
    Les fichiers ("maquettes") Apogée sont de type CSV, du texte codé en %s.
    </p>
    <p>On a un fichier par étape Apogée. Pour les obtenir, soit on peut les télécharger directement (si votre ScoDoc est interfacé avec Apogée), soit se débrouiller pour exporter le fichier 
    texte depuis Apogée. Son contenu ressemble à cela:</p>
    <pre class="small_pre_acc">
 XX-APO_TITRES-XX
 apoC_annee	2007/2008
 apoC_cod_dip	VDTCJ
 apoC_Cod_Exp	1
 apoC_cod_vdi	111
 apoC_Fichier_Exp	VDTCJ_V1CJ.txt
 apoC_lib_dip	DUT CJ
 apoC_Titre1	Export Apogée du 13/06/2008 à 14:29
 apoC_Titre2

 XX-APO_COLONNES-XX
 apoL_a01_code	Type Objet	Code	Version	Année	Session	Admission/Admissibilité	Type Rés.			Etudiant	Numéro
 apoL_a02_nom										1	Nom
 apoL_a03_prenom										1	Prénom
 apoL_a04_naissance									Session	Admissibilité	Naissance
 APO_COL_VAL_DEB
 apoL_c0001	VET	V1CJ	111	2007	0	1	N	V1CJ - DUT CJ an1	0	1	Note
 apoL_c0002	VET	V1CJ	111	2007	0	1	B		0	1	Barème
 apoL_c0003	VET	V1CJ	111	2007	0	1	R		0	1	Résultat
 APO_COL_VAL_FIN
 apoL_c0030	APO_COL_VAL_FIN

 XX-APO_VALEURS-XX
 apoL_a01_code	apoL_a02_nom	apoL_a03_prenom	apoL_a04_naissance	apoL_c0001	apoL_c0002	apoL_c0003	apoL_c0004	apoL_c0005	apoL_c0006 (...)
 11681234	DUPONT	TOTO	 23/09/1986	18	20	ADM	18	20	ADM	(...)
    </pre>
    <p>Après avoir obtenu les fichier, stockez-les dans ScoDoc 
    (bouton "Ajouter fichier" en haut de cette page. Après vérification, il va 
    apparaitre dans une table. Vous pouvez supprimer ce fichier, ou en ajouter 
    d'autres si votre semestre correspond à plusieurs étapes Apogée.
    </p>
    <p>ScoDoc vérifie que tous les étudiants du semestre sont mentionnés dans 
    un fichier Apogée et que les étapes correspondent.</p>
    <p>Lorsque c'est le cas, et que les décisions de jury sont saisies, 
    un bouton "Export vers Apogée" apparait et vous pouvez exporter les résultats.
    <p>
    <p>Vous obtiendrez alors un fichier ZIP comprenant tous les fichiers nécessaires.
    Certains de ces fichiers devront être importés dans Apogée.
    </p>
    </div>
    """
        % (APO_INPUT_ENCODING,)
    )
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def table_apo_csv_list(semset):
    """Table des archives (triée par date d'archivage)"""
    annee_scolaire = semset["annee_scolaire"]
    sem_id = semset["sem_id"]

    T = sco_etape_apogee.apo_csv_list_stored_archives(
        annee_scolaire, sem_id, etapes=semset.list_etapes()
    )

    for t in T:
        # Ajoute qq infos pour affichage:
        csv_data = sco_etape_apogee.apo_csv_get(t["etape_apo"], annee_scolaire, sem_id)
        apo_data = sco_apogee_csv.ApoData(csv_data, periode=semset["sem_id"])
        t["filename"] = apo_data.titles["apoC_Fichier_Exp"]
        t["nb_etuds"] = len(apo_data.etuds)
        t["date_str"] = t["date"].strftime("%d/%m/%Y à %H:%M")
        view_link = "view_apo_csv?etape_apo=%s&semset_id=%s" % (
            t["etape_apo"],
            semset["semset_id"],
        )
        t["_filename_target"] = view_link
        t["_etape_apo_target"] = view_link
        t["suppress"] = scu.icontag(
            "delete_small_img", border="0", alt="supprimer", title="Supprimer"
        )
        t["_suppress_target"] = "view_apo_csv_delete?etape_apo=%s&semset_id=%s" % (
            t["etape_apo"],
            semset["semset_id"],
        )

    columns_ids = ["filename", "etape_apo", "date_str", "nb_etuds"]
    # if can_edit:
    columns_ids = ["suppress"] + columns_ids

    tab = GenTable(
        titles={
            "archive_id": "",
            "filename": "Fichier",
            "etape_apo": "Etape",
            "nb_etuds": "Nb étudiants",
            "date_str": "Enregistré le",
        },
        columns_ids=columns_ids,
        rows=T,
        html_class="table_leftalign apo_maq_list",
        html_sortable=True,
        # base_url = '%s?formsemestre_id=%s' % (request.base_url, formsemestre_id),
        # caption='Maquettes enregistrées',
        preferences=sco_preferences.SemPreferences(),
    )

    return tab


def view_apo_etuds(semset_id, title="", nip_list="", format="html"):
    """Table des étudiants Apogée par nips
    nip_list est une chaine, codes nip séparés par des ,
    """
    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)
    # annee_scolaire = semset["annee_scolaire"]
    # sem_id = semset["sem_id"]
    if not isinstance(nip_list, str):
        nip_list = str(nip_list)
    nips = nip_list.split(",")
    etuds = sco_etape_apogee.apo_csv_retreive_etuds_by_nip(semset, nips)
    # Ils sont parfois dans ScoDoc même si pas dans le semestre: essaie de les retrouver
    for etud in etuds.values():
        etud_sco = sco_etud.get_etud_info(code_nip=etud["nip"], filled=True)
        if etud_sco:
            e = etud_sco[0]
            etud["inscriptions_scodoc"] = ", ".join(
                [
                    '<a href="formsemestre_bulletinetud?formsemestre_id={s[formsemestre_id]}&etudid={e[etudid]}">{s[etapes_apo_str]} (S{s[semestre_id]})</a>'.format(
                        s=sem, e=e
                    )
                    for sem in e["sems"]
                ]
            )

    return _view_etuds_page(
        semset_id,
        title=title,
        etuds=list(etuds.values()),
        keys=("nip", "etape_apo", "nom", "prenom", "inscriptions_scodoc"),
        format=format,
    )


def view_scodoc_etuds(semset_id, title="", nip_list="", format="html"):
    """Table des étudiants ScoDoc par nips ou etudids"""
    if not isinstance(nip_list, str):
        nip_list = str(nip_list)
    nips = nip_list.split(",")
    etuds = [sco_etud.get_etud_info(code_nip=nip, filled=True)[0] for nip in nips]

    for e in etuds:
        tgt = url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=e["etudid"])
        e["_nom_target"] = tgt
        e["_prenom_target"] = tgt
        e["_nom_td_attrs"] = 'id="%s" class="etudinfo"' % (e["etudid"],)
        e["_prenom_td_attrs"] = 'id="pre-%s" class="etudinfo"' % (e["etudid"],)

    return _view_etuds_page(
        semset_id,
        title=title,
        etuds=etuds,
        keys=("code_nip", "nom", "prenom"),
        format=format,
    )


def _view_etuds_page(semset_id, title="", etuds=[], keys=(), format="html"):
    # Tri les étudiants par nom:
    if etuds:
        etuds.sort(key=lambda x: (x["nom"], x["prenom"]))

    H = [
        html_sco_header.sco_header(
            page_title=title,
            init_qtip=True,
            javascripts=["js/etud_info.js"],
        ),
        "<h2>%s</h2>" % title,
    ]

    tab = GenTable(
        titles={
            "nip": "Code NIP",
            "code_nip": "Code NIP",
            "etape_apo": "Etape",
            "nom": "Nom",
            "prenom": "Prénom",
            "inscriptions_scodoc": "Inscriptions ScoDoc",
        },
        columns_ids=keys,
        rows=etuds,
        html_sortable=True,
        html_class="table_leftalign",
        filename="students_apo",
        preferences=sco_preferences.SemPreferences(),
    )
    if format != "html":
        return tab.make_page(format=format)

    H.append(tab.html())

    H.append(
        """<p><a href="apo_semset_maq_status?semset_id=%s">Retour à la page d'export Apogée</a>"""
        % semset_id
    )

    return "\n".join(H) + html_sco_header.sco_footer()


def view_apo_csv_store(semset_id="", csvfile=None, data="", autodetect=False):
    """Store CSV data
    Le semset identifie l'annee scolaire et le semestre
    Si csvfile, lit depuis FILE, sinon utilise data
    """
    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)

    if csvfile:
        data = csvfile.read()
        if autodetect:
            # check encoding (although documentation states that users SHOULD upload LATIN1)
            data, message = sco_apogee_csv.fix_data_encoding(data)
            if message:
                log("view_apo_csv_store: %s" % message)
        else:
            log("view_apo_csv_store: autodetection of encoding disabled by user")
    if not data:
        raise ScoValueError("view_apo_csv_store: no data")

    # check si etape maquette appartient bien au semset
    apo_data = sco_apogee_csv.ApoData(
        data, periode=semset["sem_id"]
    )  # parse le fichier -> exceptions
    if apo_data.etape not in semset["etapes"]:
        raise ScoValueError(
            "Le code étape de ce fichier ne correspond pas à ceux de cet ensemble"
        )

    sco_etape_apogee.apo_csv_store(data, semset["annee_scolaire"], semset["sem_id"])

    return flask.redirect("apo_semset_maq_status?semset_id=" + semset_id)


def view_apo_csv_download_and_store(etape_apo="", semset_id=""):
    """Download maquette and store it"""
    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)

    data = sco_portal_apogee.get_maquette_apogee(
        etape=etape_apo, annee_scolaire=semset["annee_scolaire"]
    )
    # here, data is utf8
    # but we store and generate latin1 files, to ease further import in Apogée
    data = data.decode(APO_PORTAL_ENCODING).encode(APO_INPUT_ENCODING)  # XXX #py3
    return view_apo_csv_store(semset_id, data=data, autodetect=False)


def view_apo_csv_delete(etape_apo="", semset_id="", dialog_confirmed=False):
    """Delete CSV file"""
    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)
    dest_url = f"apo_semset_maq_status?semset_id={semset_id}"
    if not dialog_confirmed:
        return scu.confirm_dialog(
            """<h2>Confirmer la suppression du fichier étape <tt>%s</tt>?</h2>
               <p>La suppression sera définitive.</p>"""
            % (etape_apo,),
            dest_url="",
            cancel_url=dest_url,
            parameters={"semset_id": semset_id, "etape_apo": etape_apo},
        )

    info = sco_etape_apogee.apo_csv_get_archive(
        etape_apo, semset["annee_scolaire"], semset["sem_id"]
    )
    sco_etape_apogee.apo_csv_delete(info["archive_id"])
    return flask.redirect(dest_url + "&head_message=Archive%20supprimée")


def view_apo_csv(etape_apo="", semset_id="", format="html"):
    """Visualise une maquette stockée
    Si format="raw", renvoie le fichier maquette tel quel
    """
    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)
    annee_scolaire = semset["annee_scolaire"]
    sem_id = semset["sem_id"]
    csv_data = sco_etape_apogee.apo_csv_get(etape_apo, annee_scolaire, sem_id)
    if format == "raw":
        scu.send_file(csv_data, etape_apo, suffix=".txt", mime=scu.CSV_MIMETYPE)

    apo_data = sco_apogee_csv.ApoData(csv_data, periode=semset["sem_id"])

    (
        ok_for_export,
        etapes_missing_csv,
        etuds_without_nip,
        nips_ok,
        nips_no_apo,
        nips_no_sco,
        apo_dups,
        maq_elems,
        sem_elems,
    ) = sco_etape_apogee.apo_csv_semset_check(semset)

    H = [
        html_sco_header.sco_header(
            page_title="Maquette Apogée enregistrée pour %s" % etape_apo,
            init_qtip=True,
            javascripts=["js/etud_info.js"],
        ),
        """<h2>Etudiants dans la maquette Apogée %s</h2>""" % etape_apo,
        """<p>Pour l'ensemble <a class="stdlink" href="apo_semset_maq_status?semset_id=%(semset_id)s">%(title)s</a> (indice semestre: %(sem_id)s)</p>"""
        % semset,
    ]
    # Infos générales
    H.append(
        """
    <div class="apo_csv_infos">
    <div class="apo_csv_etape"><span>Code étape:</span><span>{0.etape_apogee} VDI {0.vdi_apogee} (année {0.annee_scolaire})</span></div>
    </div>
    """.format(
            apo_data
        )
    )

    # Liste des étudiants (sans les résultats pour le moment): TODO
    etuds = apo_data.etuds
    if not etuds:
        return "\n".join(H) + "<p>Aucun étudiant</p>" + html_sco_header.sco_footer()

    # Ajout infos sur ScoDoc vs Apogee
    for e in etuds:
        e["in_scodoc"] = e["nip"] not in nips_no_sco
        e["in_scodoc_str"] = {True: "oui", False: "non"}[e["in_scodoc"]]
        if e["in_scodoc"]:
            e["_in_scodoc_str_target"] = url_for(
                "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, code_nip=e["nip"]
            )
            e.update(sco_etud.get_etud_info(code_nip=e["nip"], filled=True)[0])
            e["_nom_td_attrs"] = 'id="%s" class="etudinfo"' % (e["etudid"],)
            e["_prenom_td_attrs"] = 'id="pre-%s" class="etudinfo"' % (e["etudid"],)
        else:
            e["_css_row_class"] = "apo_not_scodoc"

    # Construit la table:
    tab = GenTable(
        titles={
            "nip": "Code NIP",
            "nom": "Nom",
            "prenom": "Prénom",
            "naissance": "Naissance",
            "in_scodoc_str": "Inscrit dans ces semestres ScoDoc",
        },
        columns_ids=("nip", "nom", "prenom", "naissance", "in_scodoc_str"),
        rows=etuds,
        html_sortable=True,
        html_class="table_leftalign apo_maq_table",
        base_url="%s?etape_apo=%s&semset_id=%s"
        % (request.base_url, etape_apo, semset_id),
        filename="students_" + etape_apo,
        caption="Etudiants Apogée en " + etape_apo,
        preferences=sco_preferences.SemPreferences(),
    )

    if format != "html":
        return tab.make_page(format=format)

    H += [
        tab.html(),
        """<p><a class="stdlink" href="view_apo_csv?etape_apo=%s&semset_id=%s&format=raw">fichier maquette CSV brut (non rempli par ScoDoc)</a></p>"""
        % (etape_apo, semset_id),
        """<div><a class="stdlink" href="apo_semset_maq_status?semset_id=%s">Retour</a>    
        </div>"""
        % semset_id,
        html_sco_header.sco_footer(),
    ]

    return "\n".join(H)


# called from Web (GET)
def apo_csv_export_results(
    semset_id,
    block_export_res_etape=False,
    block_export_res_sem=False,
    block_export_res_ues=False,
    block_export_res_modules=False,
    block_export_res_sdj=False,
):
    """Remplit les fichiers CSV archivés
    et donne un ZIP avec tous les résultats.
    """
    # nota: on peut éventuellement exporter même si tout n'est pas ok
    # mais le lien via le tableau de bord n'est pas actif
    # Les fichiers résultats ne sont pas stockés: pas besoin de permission particulière
    prefs = sco_preferences.SemPreferences()
    export_res_etape = prefs["export_res_etape"] and not int(block_export_res_etape)
    export_res_sem = prefs["export_res_sem"] and not int(block_export_res_sem)
    export_res_ues = prefs["export_res_ues"] and not int(block_export_res_ues)
    export_res_modules = prefs["export_res_modules"] and not int(
        block_export_res_modules
    )
    export_res_sdj = prefs["export_res_sdj"] and not int(block_export_res_sdj)
    export_res_rat = prefs["export_res_rat"]

    if not semset_id:
        raise ValueError("invalid null semset_id")
    semset = sco_semset.SemSet(semset_id=semset_id)
    annee_scolaire = semset["annee_scolaire"]
    periode = semset["sem_id"]

    data = io.BytesIO()
    dest_zip = ZipFile(data, "w")

    etapes_apo = sco_etape_apogee.apo_csv_list_stored_etapes(
        annee_scolaire, periode, etapes=semset.list_etapes()
    )
    for etape_apo in etapes_apo:
        apo_csv = sco_etape_apogee.apo_csv_get(etape_apo, annee_scolaire, periode)
        sco_apogee_csv.export_csv_to_apogee(
            apo_csv,
            periode=periode,
            export_res_etape=export_res_etape,
            export_res_sem=export_res_sem,
            export_res_ues=export_res_ues,
            export_res_modules=export_res_modules,
            export_res_sdj=export_res_sdj,
            export_res_rat=export_res_rat,
            dest_zip=dest_zip,
        )

    dest_zip.close()
    data.seek(0)
    basename = (
        sco_preferences.get_preference("DeptName")
        + str(annee_scolaire)
        + "-%s-" % periode
        + "-".join(etapes_apo)
    )
    basename = scu.unescape_html(basename)

    return send_file(
        data,
        mimetype="application/zip",
        download_name=scu.sanitize_filename(basename + ".zip"),
        as_attachment=True,
    )
