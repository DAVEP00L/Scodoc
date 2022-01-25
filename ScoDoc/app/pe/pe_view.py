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

##############################################################################
#  Module "Avis de poursuite d'étude"
#  conçu et développé par Cléo Baras (IUT de Grenoble)
##############################################################################


"""ScoDoc : interface des fonctions de gestion des avis de poursuites d'étude

"""

from flask import send_file, request

import app.scodoc.sco_utils as scu
from app.scodoc import sco_formsemestre
from app.scodoc import html_sco_header
from app.scodoc import sco_preferences

from app.pe import pe_tools
from app.pe import pe_jurype
from app.pe import pe_avislatex


def _pe_view_sem_recap_form(formsemestre_id):
    H = [
        html_sco_header.sco_header(page_title="Avis de poursuite d'études"),
        """<h2 class="formsemestre">Génération des avis de poursuites d'études</h2>
        <p class="help">
        Cette fonction génère un ensemble de fichiers permettant d'éditer des avis de poursuites d'études.
        <br/>
        De nombreux aspects sont paramétrables: 
        <a href="https://scodoc.org/AvisPoursuiteEtudes" target="_blank" rel="noopener noreferrer">
        voir la documentation</a>.
        </p>
        <form method="post" action="pe_view_sem_recap" id="pe_view_sem_recap_form" enctype="multipart/form-data">
        <div class="pe_template_up">
        Les templates sont généralement installés sur le serveur ou dans le paramétrage de ScoDoc.<br/> 
        Au besoin, vous pouvez spécifier ici votre propre fichier de template (<tt>un_avis.tex</tt>):
        <div class="pe_template_upb">Template: <input type="file" size="30" name="avis_tmpl_file"/></div>
        <div class="pe_template_upb">Pied de page: <input type="file" size="30" name="footer_tmpl_file"/></div>
        </div>
        <input type="submit" value="Générer les documents"/>
        <input type="hidden" name="formsemestre_id" value="{formsemestre_id}">
        </form>
        """.format(
            formsemestre_id=formsemestre_id
        ),
    ]
    return "\n".join(H) + html_sco_header.sco_footer()


# called from the web, POST or GET
def pe_view_sem_recap(
    formsemestre_id,
    avis_tmpl_file=None,
    footer_tmpl_file=None,
):
    """Génération des avis de poursuite d'étude"""
    if request.method == "GET":
        return _pe_view_sem_recap_form(formsemestre_id)
    prefs = sco_preferences.SemPreferences(formsemestre_id=formsemestre_id)

    semBase = sco_formsemestre.get_formsemestre(formsemestre_id)

    jury = pe_jurype.JuryPE(semBase)
    # Ajout avis LaTeX au même zip:
    etudids = list(jury.syntheseJury.keys())

    # Récupération du template latex, du footer latex et du tag identifiant les annotations relatives aux PE
    # (chaines unicodes, html non quoté)
    template_latex = ""
    # template fourni via le formulaire Web
    if avis_tmpl_file:
        template_latex = avis_tmpl_file.read()
        template_latex = template_latex
    else:
        # template indiqué dans préférences ScoDoc ?
        template_latex = pe_avislatex.get_code_latex_from_scodoc_preference(
            formsemestre_id, champ="pe_avis_latex_tmpl"
        )

    template_latex = template_latex.strip()
    if not template_latex:
        # pas de preference pour le template: utilise fichier du serveur
        template_latex = pe_avislatex.get_templates_from_distrib("avis")

    # Footer:
    footer_latex = ""
    # template fourni via le formulaire Web
    if footer_tmpl_file:
        footer_latex = footer_tmpl_file.read()
        footer_latex = footer_latex
    else:
        footer_latex = pe_avislatex.get_code_latex_from_scodoc_preference(
            formsemestre_id, champ="pe_avis_latex_footer"
        )
    footer_latex = footer_latex.strip()
    if not footer_latex:
        # pas de preference pour le footer: utilise fichier du serveur
        footer_latex = pe_avislatex.get_templates_from_distrib(
            "footer"
        )  # fallback: footer vides

    tag_annotation_pe = pe_avislatex.get_code_latex_from_scodoc_preference(
        formsemestre_id, champ="pe_tag_annotation_avis_latex"
    )

    # Ajout des annotations PE dans un fichier excel
    sT = pe_avislatex.table_syntheseAnnotationPE(jury.syntheseJury, tag_annotation_pe)
    if sT:
        jury.add_file_to_zip(
            jury.NOM_EXPORT_ZIP + "_annotationsPE" + scu.XLSX_SUFFIX, sT.excel()
        )

    latex_pages = {}  # Dictionnaire de la forme nom_fichier => contenu_latex
    for etudid in etudids:
        [nom_fichier, contenu_latex] = pe_avislatex.get_avis_poursuite_par_etudiant(
            jury,
            etudid,
            template_latex,
            tag_annotation_pe,
            footer_latex,
            prefs,
        )
        jury.add_file_to_zip("avis/" + nom_fichier + ".tex", contenu_latex)
        latex_pages[nom_fichier] = contenu_latex  # Sauvegarde dans un dico

    # Nouvelle version : 1 fichier par étudiant avec 1 fichier appelant créée ci-dessous
    doc_latex = "\n% -----\n".join(
        ["\\include{" + nom + "}" for nom in sorted(latex_pages.keys())]
    )
    jury.add_file_to_zip("avis/avis_poursuite.tex", doc_latex)

    # Ajoute image, LaTeX class file(s) and modeles
    pe_tools.add_pe_stuff_to_zip(jury.zipfile, jury.NOM_EXPORT_ZIP)
    data = jury.get_zipped_data()

    return send_file(
        data,
        mimetype="application/zip",
        download_name=scu.sanitize_filename(jury.NOM_EXPORT_ZIP + ".zip"),
        as_attachment=True,
    )
