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

import os
import codecs
import re
from app.pe import pe_tagtable
from app.pe import pe_jurype
from app.pe import pe_tools

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.gen_tables import GenTable, SeqGenTable
from app.scodoc import sco_preferences
from app.scodoc import sco_etud


DEBUG = False  # Pour debug et repérage des prints à changer en Log

DONNEE_MANQUANTE = (
    ""  # Caractère de remplacement des données manquantes dans un avis PE
)

# ----------------------------------------------------------------------------------------
def get_code_latex_from_modele(fichier):
    """Lit le code latex à partir d'un modèle. Renvoie une chaine unicode.

    Le fichier doit contenir le chemin relatif
    vers le modele : attention pas de vérification du format d'encodage
    Le fichier doit donc etre enregistré avec le même codage que ScoDoc (utf-8)
    """
    fid_latex = codecs.open(fichier, "r", encoding=scu.SCO_ENCODING)
    un_avis_latex = fid_latex.read()
    fid_latex.close()
    return un_avis_latex


# ----------------------------------------------------------------------------------------
def get_code_latex_from_scodoc_preference(formsemestre_id, champ="pe_avis_latex_tmpl"):
    """
    Extrait le template (ou le tag d'annotation au regard du champ fourni) des préférences LaTeX
    et s'assure qu'il est renvoyé au format unicode
    """
    template_latex = sco_preferences.get_preference(champ, formsemestre_id)

    return template_latex or ""


# ----------------------------------------------------------------------------------------
def get_tags_latex(code_latex):
    """Recherche tous les tags présents dans un code latex (ce code étant obtenu
    à la lecture d'un modèle d'avis pe).
    Ces tags sont répérés par les balises **, débutant et finissant le tag
    et sont renvoyés sous la forme d'une liste.

    result: liste de chaines unicode
    """
    if code_latex:
        # changé par EV: était r"([\*]{2}[a-zA-Z0-9:éèàâêëïôöù]+[\*]{2})"
        res = re.findall(r"([\*]{2}[^ \t\n\r\f\v\*]+[\*]{2})", code_latex)
        return [tag[2:-2] for tag in res]
    else:
        return []


def comp_latex_parcourstimeline(etudiant, promo, taille=17):
    """Interprète un tag dans un avis latex **parcourstimeline**
    et génère le code latex permettant de retracer le parcours d'un étudiant
    sous la forme d'une frise temporelle.
    Nota: modeles/parcourstimeline.tex doit avoir été inclu dans le préambule

    result: chaine unicode (EV:)
    """
    codelatexDebut = (
        """"
    \\begin{parcourstimeline}{**debut**}{**fin**}{**nbreSemestres**}{%d}
    """
        % taille
    )

    modeleEvent = """
    \\parcoursevent{**nosem**}{**nomsem**}{**descr**}
    """

    codelatexFin = """
    \\end{parcourstimeline}
    """
    reslatex = codelatexDebut
    reslatex = reslatex.replace("**debut**", etudiant["entree"])
    reslatex = reslatex.replace("**fin**", str(etudiant["promo"]))
    reslatex = reslatex.replace("**nbreSemestres**", str(etudiant["nbSemestres"]))
    # Tri du parcours par ordre croissant : de la forme descr, nom sem date-date
    parcours = etudiant["parcours"][::-1]  # EV: XXX je ne comprend pas ce commentaire ?

    for no_sem in range(etudiant["nbSemestres"]):
        descr = modeleEvent
        nom_semestre_dans_parcours = parcours[no_sem]["nom_semestre_dans_parcours"]
        descr = descr.replace("**nosem**", str(no_sem + 1))
        if no_sem % 2 == 0:
            descr = descr.replace("**nomsem**", nom_semestre_dans_parcours)
            descr = descr.replace("**descr**", "")
        else:
            descr = descr.replace("**nomsem**", "")
            descr = descr.replace("**descr**", nom_semestre_dans_parcours)
        reslatex += descr
    reslatex += codelatexFin
    return reslatex


# ----------------------------------------------------------------------------------------
def interprete_tag_latex(tag):
    """Découpe les tags latex de la forme S1:groupe:dut:min et renvoie si possible
    le résultat sous la forme d'un quadruplet.
    """
    infotag = tag.split(":")
    if len(infotag) == 4:
        return (
            infotag[0].upper(),
            infotag[1].lower(),
            infotag[2].lower(),
            infotag[3].lower(),
        )
    else:
        return (None, None, None, None)


# ----------------------------------------------------------------------------------------
def get_code_latex_avis_etudiant(
    donnees_etudiant, un_avis_latex, annotationPE, footer_latex, prefs
):
    """
    Renvoie le code latex permettant de générer l'avis d'un étudiant en utilisant ses
    donnees_etudiant contenu dans le dictionnaire de synthèse du jury PE et en suivant un
    fichier modele donné

    result: chaine unicode
    """
    if not donnees_etudiant or not un_avis_latex:  # Cas d'un template vide
        return annotationPE if annotationPE else ""

    # Le template latex (corps + footer)
    code = un_avis_latex + "\n\n" + footer_latex

    # Recherche des tags dans le fichier
    tags_latex = get_tags_latex(code)
    if DEBUG:
        log("Les tags" + str(tags_latex))

    # Interprète et remplace chaque tags latex par les données numériques de l'étudiant (y compris les
    # tags "macros" tels que parcourstimeline
    for tag_latex in tags_latex:
        # les tags numériques
        valeur = DONNEE_MANQUANTE

        if ":" in tag_latex:
            (aggregat, groupe, tag_scodoc, champ) = interprete_tag_latex(tag_latex)
            valeur = str_from_syntheseJury(
                donnees_etudiant, aggregat, groupe, tag_scodoc, champ
            )

        # La macro parcourstimeline
        elif tag_latex == "parcourstimeline":
            valeur = comp_latex_parcourstimeline(
                donnees_etudiant, donnees_etudiant["promo"]
            )

        # Le tag annotationPE
        elif tag_latex == "annotation":
            valeur = annotationPE

        # Le tag bilanParTag
        elif tag_latex == "bilanParTag":
            valeur = get_bilanParTag(donnees_etudiant)

        # Les tags "simples": par ex. nom, prenom, civilite, ...
        else:
            if tag_latex in donnees_etudiant:
                valeur = donnees_etudiant[tag_latex]
            elif tag_latex in prefs:  # les champs **NomResponsablePE**, ...
                valeur = pe_tools.escape_for_latex(prefs[tag_latex])

        # Vérification des pb d'encodage (debug)
        # assert isinstance(tag_latex, unicode)
        # assert isinstance(valeur, unicode)

        # Substitution
        code = code.replace("**" + tag_latex + "**", valeur)
    return code


# ----------------------------------------------------------------------------------------
def get_annotation_PE(etudid, tag_annotation_pe):
    """Renvoie l'annotation PE dans la liste de ces annotations ;
    Cette annotation est reconnue par la présence d'un tag **PE**
    (cf. .get_preferences -> pe_tag_annotation_avis_latex).

    Result: chaine unicode
    """
    if tag_annotation_pe:
        cnx = ndb.GetDBConnexion()
        annotations = sco_etud.etud_annotations_list(
            cnx, args={"etudid": etudid}
        )  # Les annotations de l'étudiant
        annotationsPE = []

        exp = re.compile(r"^" + tag_annotation_pe)

        for a in annotations:
            commentaire = scu.unescape_html(a["comment"])
            if exp.match(commentaire):  # tag en début de commentaire ?
                a["comment_u"] = commentaire  # unicode, HTML non quoté
                annotationsPE.append(
                    a
                )  # sauvegarde l'annotation si elle contient le tag

        if annotationsPE:  # Si des annotations existent, prend la plus récente
            annotationPE = sorted(annotationsPE, key=lambda a: a["date"], reverse=True)[
                0
            ]["comment_u"]

            annotationPE = exp.sub(
                "", annotationPE
            )  # Suppression du tag d'annotation PE
            annotationPE = annotationPE.replace("\r", "")  # Suppression des \r
            annotationPE = annotationPE.replace(
                "<br/>", "\n\n"
            )  # Interprète les retours chariots html
            return annotationPE
    return ""  # pas d'annotations


# ----------------------------------------------------------------------------------------
def str_from_syntheseJury(donnees_etudiant, aggregat, groupe, tag_scodoc, champ):
    """Extrait du dictionnaire de synthèse du juryPE pour un étudiant donnée,
    une valeur indiquée par un champ ;
    si champ est une liste, renvoie la liste des valeurs extraites.

    Result: chaine unicode ou liste de chaines unicode
    """

    if isinstance(champ, list):
        return [
            str_from_syntheseJury(donnees_etudiant, aggregat, groupe, tag_scodoc, chp)
            for chp in champ
        ]
    else:  # champ = str à priori
        valeur = DONNEE_MANQUANTE
        if (
            (aggregat in donnees_etudiant)
            and (groupe in donnees_etudiant[aggregat])
            and (tag_scodoc in donnees_etudiant[aggregat][groupe])
        ):
            donnees_numeriques = donnees_etudiant[aggregat][groupe][tag_scodoc]
            if champ == "rang":
                valeur = "%s/%d" % (
                    donnees_numeriques[
                        pe_tagtable.TableTag.FORMAT_DONNEES_ETUDIANTS.index("rang")
                    ],
                    donnees_numeriques[
                        pe_tagtable.TableTag.FORMAT_DONNEES_ETUDIANTS.index(
                            "nbinscrits"
                        )
                    ],
                )
            elif champ in pe_tagtable.TableTag.FORMAT_DONNEES_ETUDIANTS:
                indice_champ = pe_tagtable.TableTag.FORMAT_DONNEES_ETUDIANTS.index(
                    champ
                )
                if (
                    len(donnees_numeriques) > indice_champ
                    and donnees_numeriques[indice_champ] != None
                ):
                    if isinstance(
                        donnees_numeriques[indice_champ], float
                    ):  # valeur numérique avec formattage unicode
                        valeur = "%2.2f" % donnees_numeriques[indice_champ]
                    else:
                        valeur = "%s" % donnees_numeriques[indice_champ]

        return valeur


# ----------------------------------------------------------------------------------------
def get_bilanParTag(donnees_etudiant, groupe="groupe"):
    """Renvoie le code latex d'un tableau récapitulant, pour tous les tags trouvés dans
    les données étudiants, ses résultats.
    result: chaine unicode
    """

    entete = [
        (
            agg,
            pe_jurype.JuryPE.PARCOURS[agg]["affichage_court"],
            pe_jurype.JuryPE.PARCOURS[agg]["ordre"],
        )
        for agg in pe_jurype.JuryPE.PARCOURS
    ]
    entete = sorted(entete, key=lambda t: t[2])

    lignes = []
    valeurs = {"note": [], "rang": []}
    for (indice_aggregat, (aggregat, intitule, _)) in enumerate(entete):
        # print("> " + aggregat)
        # listeTags = jury.get_allTagForAggregat(aggregat)  # les tags de l'aggrégat
        listeTags = [
            tag for tag in donnees_etudiant[aggregat][groupe].keys() if tag != "dut"
        ]  #
        for tag in listeTags:

            if tag not in lignes:
                lignes.append(tag)
                valeurs["note"].append(
                    [""] * len(entete)
                )  # Ajout d'une ligne de données
                valeurs["rang"].append(
                    [""] * len(entete)
                )  # Ajout d'une ligne de données
            indice_tag = lignes.index(tag)  # l'indice de ligne du tag

            # print(" --- " + tag + "(" + str(indice_tag) + "," + str(indice_aggregat) + ")")
            [note, rang] = str_from_syntheseJury(
                donnees_etudiant, aggregat, groupe, tag, ["note", "rang"]
            )
            valeurs["note"][indice_tag][indice_aggregat] = "" + note + ""
            valeurs["rang"][indice_tag][indice_aggregat] = (
                ("\\textit{" + rang + "}") if note else ""
            )  # rang masqué si pas de notes

    code_latex = "\\begin{tabular}{|c|" + "|c" * (len(entete)) + "|}\n"
    code_latex += "\\hline \n"
    code_latex += (
        " & "
        + " & ".join(["\\textbf{" + intitule + "}" for (agg, intitule, _) in entete])
        + " \\\\ \n"
    )
    code_latex += "\\hline"
    code_latex += "\\hline \n"
    for (i, ligne_val) in enumerate(valeurs["note"]):
        titre = lignes[i]  # règle le pb d'encodage
        code_latex += "\\textbf{" + titre + "} & " + " & ".join(ligne_val) + "\\\\ \n"
        code_latex += (
            " & "
            + " & ".join(
                ["{\\scriptsize " + clsmt + "}" for clsmt in valeurs["rang"][i]]
            )
            + "\\\\ \n"
        )
        code_latex += "\\hline \n"
    code_latex += "\\end{tabular}"

    return code_latex


# ----------------------------------------------------------------------------------------
def get_avis_poursuite_par_etudiant(
    jury, etudid, template_latex, tag_annotation_pe, footer_latex, prefs
):
    """Renvoie un nom de fichier et le contenu de l'avis latex d'un étudiant dont l'etudid est fourni.
    result: [ chaine unicode, chaine unicode ]
    """
    if pe_tools.PE_DEBUG:
        pe_tools.pe_print(jury.syntheseJury[etudid]["nom"] + " " + str(etudid))

    civilite_str = jury.syntheseJury[etudid]["civilite_str"]
    nom = jury.syntheseJury[etudid]["nom"].replace(" ", "-")
    prenom = jury.syntheseJury[etudid]["prenom"].replace(" ", "-")

    nom_fichier = scu.sanitize_filename(
        "avis_poursuite_%s_%s_%s" % (nom, prenom, etudid)
    )
    if pe_tools.PE_DEBUG:
        pe_tools.pe_print("fichier latex =" + nom_fichier, type(nom_fichier))

    # Entete (commentaire)
    contenu_latex = (
        "%% ---- Etudiant: " + civilite_str + " " + nom + " " + prenom + "\n"
    )

    # les annnotations
    annotationPE = get_annotation_PE(etudid, tag_annotation_pe=tag_annotation_pe)
    if pe_tools.PE_DEBUG:
        pe_tools.pe_print(annotationPE, type(annotationPE))

    # le LaTeX
    avis = get_code_latex_avis_etudiant(
        jury.syntheseJury[etudid], template_latex, annotationPE, footer_latex, prefs
    )
    # if pe_tools.PE_DEBUG: pe_tools.pe_print(avis, type(avis))
    contenu_latex += avis + "\n"

    return [nom_fichier, contenu_latex]


def get_templates_from_distrib(template="avis"):
    """Récupère le template (soit un_avis.tex soit le footer.tex) à partir des fichiers mémorisés dans la distrib des avis pe (distrib local
    ou par défaut et le renvoie"""
    if template == "avis":
        pe_local_tmpl = pe_tools.PE_LOCAL_AVIS_LATEX_TMPL
        pe_default_tmpl = pe_tools.PE_DEFAULT_AVIS_LATEX_TMPL
    elif template == "footer":
        pe_local_tmpl = pe_tools.PE_LOCAL_FOOTER_TMPL
        pe_default_tmpl = pe_tools.PE_DEFAULT_FOOTER_TMPL

    if template in ["avis", "footer"]:
        # pas de preference pour le template: utilise fichier du serveur
        if os.path.exists(pe_local_tmpl):
            template_latex = get_code_latex_from_modele(pe_local_tmpl)
        else:
            if os.path.exists(pe_default_tmpl):
                template_latex = get_code_latex_from_modele(pe_default_tmpl)
            else:
                template_latex = ""  # fallback: avis vides
        return template_latex


# ----------------------------------------------------------------------------------------
def table_syntheseAnnotationPE(syntheseJury, tag_annotation_pe):
    """Génère un fichier excel synthétisant les annotations PE telles qu'inscrites dans les fiches de chaque étudiant"""
    sT = SeqGenTable()  # le fichier excel à générer

    # Les etudids des étudiants à afficher, triés par ordre alphabétiques de nom+prénom
    donnees_tries = sorted(
        [
            (etudid, syntheseJury[etudid]["nom"] + " " + syntheseJury[etudid]["prenom"])
            for etudid in syntheseJury.keys()
        ],
        key=lambda c: c[1],
    )
    etudids = [e[0] for e in donnees_tries]
    if not etudids:  # Si pas d'étudiants
        T = GenTable(
            columns_ids=["pas d'étudiants"],
            rows=[],
            titles={"pas d'étudiants": "pas d'étudiants"},
            html_sortable=True,
            xls_sheet_name="dut",
        )
        sT.add_genTable("Annotation PE", T)
        return sT

    # Si des étudiants
    maxParcours = max(
        [syntheseJury[etudid]["nbSemestres"] for etudid in etudids]
    )  # le nombre de semestre le + grand

    infos = ["civilite", "nom", "prenom", "age", "nbSemestres"]
    entete = ["etudid"]
    entete.extend(infos)
    entete.extend(["P%d" % i for i in range(1, maxParcours + 1)])  # ajout du parcours
    entete.append("Annotation PE")
    columns_ids = entete  # les id et les titres de colonnes sont ici identiques
    titles = {i: i for i in columns_ids}

    rows = []
    for (
        etudid
    ) in etudids:  # parcours des étudiants par ordre alphabétique des nom+prénom
        e = syntheseJury[etudid]
        # Les info générales:
        row = {
            "etudid": etudid,
            "civilite": e["civilite"],
            "nom": e["nom"],
            "prenom": e["prenom"],
            "age": e["age"],
            "nbSemestres": e["nbSemestres"],
        }
        # Les parcours: P1, P2, ...
        n = 1
        for p in e["parcours"]:
            row["P%d" % n] = p["titreannee"]
            n += 1

        # L'annotation PE
        annotationPE = get_annotation_PE(etudid, tag_annotation_pe=tag_annotation_pe)
        row["Annotation PE"] = annotationPE if annotationPE else ""
        rows.append(row)

    T = GenTable(
        columns_ids=columns_ids,
        rows=rows,
        titles=titles,
        html_sortable=True,
        xls_sheet_name="Annotation PE",
    )
    sT.add_genTable("Annotation PE", T)
    return sT
