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

"""Tableau recapitulatif des notes d'un semestre
"""
import datetime
import json
import time
from xml.etree import ElementTree

from flask import request
from flask import make_response

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_bac
from app.scodoc import sco_bulletins_json
from app.scodoc import sco_bulletins_xml
from app.scodoc import sco_bulletins, sco_excel
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_evaluations
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_groups
from app.scodoc import sco_permissions
from app.scodoc import sco_permissions_check
from app.scodoc import sco_preferences
from app.scodoc import sco_etud
from app.scodoc import sco_users
from app.scodoc import sco_xml
from app.scodoc.sco_codes_parcours import DEF, UE_SPORT


def formsemestre_recapcomplet(
    formsemestre_id=None,
    modejury=False,  # affiche lien saisie decision jury
    hidemodules=False,  # cache colonnes notes modules
    hidebac=False,  # cache colonne Bac
    tabformat="html",
    sortcol=None,
    xml_with_decisions=False,  # XML avec decisions
    rank_partition_id=None,  # si None, calcul rang global
    pref_override=True,  # si vrai, les prefs ont la priorite sur le param hidebac
    force_publishing=True,  # publie les XML/JSON meme si bulletins non publiés
):
    """Page récapitulant les notes d'un semestre.
    Grand tableau récapitulatif avec toutes les notes de modules
    pour tous les étudiants, les moyennes par UE et générale,
    trié par moyenne générale décroissante.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
    # traduit du DTML
    modejury = int(modejury)
    hidemodules = (
        int(hidemodules) or parcours.UE_IS_MODULE
    )  # cache les colonnes des modules
    pref_override = int(pref_override)
    if pref_override:
        hidebac = int(sco_preferences.get_preference("recap_hidebac", formsemestre_id))
    else:
        hidebac = int(hidebac)
    xml_with_decisions = int(xml_with_decisions)
    force_publishing = int(force_publishing)
    isFile = tabformat in ("csv", "xls", "xml", "xlsall", "json")
    H = []
    if not isFile:
        H += [
            html_sco_header.sco_header(
                page_title="Récapitulatif",
                no_side_bar=True,
                init_qtip=True,
                javascripts=["libjs/sorttable.js", "js/etud_info.js"],
            ),
            sco_formsemestre_status.formsemestre_status_head(
                formsemestre_id=formsemestre_id
            ),
            '<form name="f" method="get" action="%s">' % request.base_url,
            '<input type="hidden" name="formsemestre_id" value="%s"></input>'
            % formsemestre_id,
            '<input type="hidden" name="pref_override" value="0"></input>',
        ]
        if modejury:
            H.append(
                '<input type="hidden" name="modejury" value="%s"></input>' % modejury
            )
        H.append(
            '<select name="tabformat" onchange="document.f.submit()" class="noprint">'
        )
        for (format, label) in (
            ("html", "HTML"),
            ("xls", "Fichier tableur (Excel)"),
            ("xlsall", "Fichier tableur avec toutes les évals"),
            ("csv", "Fichier tableur (CSV)"),
            ("xml", "Fichier XML"),
            ("json", "JSON"),
        ):
            if format == tabformat:
                selected = " selected"
            else:
                selected = ""
            H.append('<option value="%s"%s>%s</option>' % (format, selected, label))
        H.append("</select>")

        H.append(
            """(cliquer sur un nom pour afficher son bulletin ou <a class="stdlink" href="%s/Notes/formsemestre_bulletins_pdf?formsemestre_id=%s">ici avoir le classeur papier</a>)"""
            % (scu.ScoURL(), formsemestre_id)
        )
        if not parcours.UE_IS_MODULE:
            H.append(
                """<input type="checkbox" name="hidemodules" value="1" onchange="document.f.submit()" """
            )
            if hidemodules:
                H.append("checked")
            H.append(""" >cacher les modules</input>""")
        H.append(
            """<input type="checkbox" name="hidebac" value="1" onchange="document.f.submit()" """
        )
        if hidebac:
            H.append("checked")
        H.append(""" >cacher bac</input>""")
    data = do_formsemestre_recapcomplet(
        formsemestre_id,
        format=tabformat,
        hidemodules=hidemodules,
        hidebac=hidebac,
        modejury=modejury,
        sortcol=sortcol,
        xml_with_decisions=xml_with_decisions,
        rank_partition_id=rank_partition_id,
        force_publishing=force_publishing,
    )
    if tabformat == "xml":
        response = make_response(data)
        response.headers["Content-Type"] = scu.XML_MIMETYPE
        return response
    H.append(data)

    if not isFile:
        H.append("</form>")
        H.append(
            """<p><a class="stdlink" href="formsemestre_pvjury?formsemestre_id=%s">Voir les décisions du jury</a></p>"""
            % formsemestre_id
        )
        if sco_permissions_check.can_validate_sem(formsemestre_id):
            H.append("<p>")
            if modejury:
                H.append(
                    """<a class="stdlink" href="formsemestre_validation_auto?formsemestre_id=%s">Calcul automatique des décisions du jury</a></p>"""
                    % (formsemestre_id,)
                )
            else:
                H.append(
                    """<a class="stdlink" href="formsemestre_recapcomplet?formsemestre_id=%s&modejury=1&hidemodules=1">Saisie des décisions du jury</a>"""
                    % formsemestre_id
                )
            H.append("</p>")
        if sco_preferences.get_preference("use_ue_coefs", formsemestre_id):
            H.append(
                """
            <p class="infop">utilise les coefficients d'UE pour calculer la moyenne générale.</p>
            """
            )
        H.append(html_sco_header.sco_footer())
    # HTML or binary data ?
    if len(H) > 1:
        return "".join(H)
    elif len(H) == 1:
        return H[0]
    else:
        return H


def do_formsemestre_recapcomplet(
    formsemestre_id=None,
    format="html",  # html, xml, xls, xlsall, json
    hidemodules=False,  # ne pas montrer les modules (ignoré en XML)
    hidebac=False,  # pas de colonne Bac (ignoré en XML)
    xml_nodate=False,  # format XML sans dates (sert pour debug cache: comparaison de XML)
    modejury=False,  # saisie décisions jury
    sortcol=None,  # indice colonne a trier dans table T
    xml_with_decisions=False,
    disable_etudlink=False,
    rank_partition_id=None,  # si None, calcul rang global
    force_publishing=True,
):
    """Calcule et renvoie le tableau récapitulatif."""
    data, filename, format = make_formsemestre_recapcomplet(
        formsemestre_id=formsemestre_id,
        format=format,
        hidemodules=hidemodules,
        hidebac=hidebac,
        xml_nodate=xml_nodate,
        modejury=modejury,
        sortcol=sortcol,
        xml_with_decisions=xml_with_decisions,
        disable_etudlink=disable_etudlink,
        rank_partition_id=rank_partition_id,
        force_publishing=force_publishing,
    )
    if format == "xml" or format == "html":
        return data
    elif format == "csv":
        return scu.send_file(data, filename=filename, mime=scu.CSV_MIMETYPE)
    elif format.startswith("xls") or format.startswith("xlsx"):
        return scu.send_file(data, filename=filename, mime=scu.XLSX_MIMETYPE)
    elif format == "json":
        js = json.dumps(data, indent=1, cls=scu.ScoDocJSONEncoder)
        return scu.send_file(
            js, filename=filename, suffix=scu.JSON_SUFFIX, mime=scu.JSON_MIMETYPE
        )
    else:
        raise ValueError("unknown format %s" % format)


def make_formsemestre_recapcomplet(
    formsemestre_id=None,
    format="html",  # html, xml, xls, xlsall, json
    hidemodules=False,  # ne pas montrer les modules (ignoré en XML)
    hidebac=False,  # pas de colonne Bac (ignoré en XML)
    xml_nodate=False,  # format XML sans dates (sert pour debug cache: comparaison de XML)
    modejury=False,  # saisie décisions jury
    sortcol=None,  # indice colonne a trier dans table T
    xml_with_decisions=False,
    disable_etudlink=False,
    rank_partition_id=None,  # si None, calcul rang global
    force_publishing=True,  # donne bulletins JSON/XML meme si non publiés
):
    """Grand tableau récapitulatif avec toutes les notes de modules
    pour tous les étudiants, les moyennes par UE et générale,
    trié par moyenne générale décroissante.
    """
    civ_nom_prenom = False  # 3 colonnes différentes ou une seule avec prénom abrégé ?
    if format == "xml":
        return _formsemestre_recapcomplet_xml(
            formsemestre_id,
            xml_nodate,
            xml_with_decisions=xml_with_decisions,
            force_publishing=force_publishing,
        )
    elif format == "json":
        return _formsemestre_recapcomplet_json(
            formsemestre_id,
            xml_nodate=xml_nodate,
            xml_with_decisions=xml_with_decisions,
            force_publishing=force_publishing,
        )
    if format[:3] == "xls":
        civ_nom_prenom = True  # 3 cols: civilite, nom, prenom
        keep_numeric = True  # pas de conversion des notes en strings
    else:
        keep_numeric = False

    if hidebac:
        admission_extra_cols = []
    else:
        admission_extra_cols = [
            "type_admission",
            "classement",
            "apb_groupe",
            "apb_classement_gr",
        ]

    sem = sco_formsemestre.do_formsemestre_list(
        args={"formsemestre_id": formsemestre_id}
    )[0]
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # >  get_modimpls, get_ues, get_table_moyennes_triees, get_etud_decision_sem, get_etud_etat, get_etud_rang, get_nom_short, get_mod_stats, nt.moy_moy, get_etud_decision_sem,
    modimpls = nt.get_modimpls()
    ues = nt.get_ues()  # incluant le(s) UE de sport
    #
    partitions, partitions_etud_groups = sco_groups.get_formsemestre_groups(
        formsemestre_id
    )
    if rank_partition_id and format == "html":
        # Calcul rang sur une partition et non sur l'ensemble
        # seulement en format HTML (car colonnes rangs toujours presentes en xls)
        rank_partition = sco_groups.get_partition(rank_partition_id)
        rank_label = "Rg (%s)" % rank_partition["partition_name"]
    else:
        rank_partition = sco_groups.get_default_partition(formsemestre_id)
        rank_label = "Rg"

    T = nt.get_table_moyennes_triees()
    if not T:
        return "", "", format

    # Construit une liste de listes de chaines: le champs du tableau resultat (HTML ou CSV)
    F = []
    h = [rank_label]
    if civ_nom_prenom:
        h += ["Civilité", "Nom", "Prénom"]
    else:
        h += ["Nom"]
    if not hidebac:
        h.append("Bac")

    # Si CSV ou XLS, indique tous les groupes
    if format[:3] == "xls" or format == "csv":
        for partition in partitions:
            h.append("%s" % partition["partition_name"])
    else:
        h.append("Gr")

    h.append("Moy")
    # Ajoute rangs dans groupe seulement si CSV ou XLS
    if format[:3] == "xls" or format == "csv":
        for partition in partitions:
            h.append("rang_%s" % partition["partition_name"])

    cod2mod = {}  # code : moduleimpl
    mod_evals = {}  # moduleimpl_id : liste de toutes les evals de ce module
    for ue in ues:
        if ue["type"] != UE_SPORT:
            h.append(ue["acronyme"])
        else:  # UE_SPORT:
            # n'affiche pas la moyenne d'UE dans ce cas
            # mais laisse col. vide si modules affichés (pour séparer les UE)
            if not hidemodules:
                h.append("")
            pass
        if not hidemodules and not ue["is_external"]:
            for modimpl in modimpls:
                if modimpl["module"]["ue_id"] == ue["ue_id"]:
                    code = modimpl["module"]["code"]
                    h.append(code)
                    cod2mod[code] = modimpl  # pour fabriquer le lien
                    if format == "xlsall":
                        evals = nt.get_mod_evaluation_etat_list(
                            modimpl["moduleimpl_id"]
                        )
                        mod_evals[modimpl["moduleimpl_id"]] = evals
                        h += _list_notes_evals_titles(code, evals)

    h += admission_extra_cols
    h += ["code_nip", "etudid"]
    F.append(h)

    ue_index = []  # indices des moy UE dans l (pour appliquer style css)

    def fmtnum(val):  # conversion en nombre pour cellules excel
        if keep_numeric:
            try:
                return float(val)
            except:
                return val
        else:
            return val

    # Compte les decisions de jury
    codes_nb = scu.DictDefault(defaultvalue=0)
    #
    is_dem = {}  # etudid : bool
    for t in T:
        etudid = t[-1]
        dec = nt.get_etud_decision_sem(etudid)
        if dec:
            codes_nb[dec["code"]] += 1
        etud_etat = nt.get_etud_etat(etudid)
        if etud_etat == "D":
            gr_name = "Dém."
            is_dem[etudid] = True
        elif etud_etat == DEF:
            gr_name = "Déf."
            is_dem[etudid] = False
        else:
            group = sco_groups.get_etud_main_group(etudid, sem)
            gr_name = group["group_name"] or ""
            is_dem[etudid] = False
        if rank_partition_id:
            rang_gr, _, rank_gr_name = sco_bulletins.get_etud_rangs_groups(
                etudid, formsemestre_id, partitions, partitions_etud_groups, nt
            )
            if rank_gr_name[rank_partition_id]:
                rank = "%s %s" % (
                    rank_gr_name[rank_partition_id],
                    rang_gr[rank_partition_id],
                )
            else:
                rank = ""
        else:
            rank = nt.get_etud_rang(etudid)

        e = nt.identdict[etudid]
        if civ_nom_prenom:
            sco_etud.format_etud_ident(e)
            l = [rank, e["civilite_str"], e["nom_disp"], e["prenom"]]  # civ, nom prenom
        else:
            l = [rank, nt.get_nom_short(etudid)]  # rang, nom,

        if not hidebac:
            bac = sco_bac.Baccalaureat(e["bac"], e["specialite"])
            l.append(bac.abbrev())

        if format[:3] == "xls" or format == "csv":  # tous les groupes
            for partition in partitions:
                group = partitions_etud_groups[partition["partition_id"]].get(
                    etudid, None
                )
                if group:
                    l.append(group["group_name"])
                else:
                    l.append("")
        else:
            l.append(gr_name)  # groupe

        l.append(fmtnum(scu.fmt_note(t[0], keep_numeric=keep_numeric)))  # moy_gen
        # Ajoute rangs dans groupes seulement si CSV ou XLS
        if format[:3] == "xls" or format == "csv":
            rang_gr, _, gr_name = sco_bulletins.get_etud_rangs_groups(
                etudid, formsemestre_id, partitions, partitions_etud_groups, nt
            )

            for partition in partitions:
                l.append(rang_gr[partition["partition_id"]])
        i = 0
        for ue in ues:
            i += 1
            if ue["type"] != UE_SPORT:
                l.append(
                    fmtnum(scu.fmt_note(t[i], keep_numeric=keep_numeric))
                )  # moyenne etud dans ue
            else:  # UE_SPORT:
                # n'affiche pas la moyenne d'UE dans ce cas
                if not hidemodules:
                    l.append("")
            ue_index.append(len(l) - 1)
            if not hidemodules and not ue["is_external"]:
                j = 0
                for modimpl in modimpls:
                    if modimpl["module"]["ue_id"] == ue["ue_id"]:
                        l.append(
                            fmtnum(
                                scu.fmt_note(
                                    t[j + len(ues) + 1], keep_numeric=keep_numeric
                                )
                            )
                        )  # moyenne etud dans module
                        if format == "xlsall":
                            l += _list_notes_evals(
                                mod_evals[modimpl["moduleimpl_id"]], etudid
                            )
                    j += 1
        if not hidebac:
            for k in admission_extra_cols:
                l.append(e[k])
        l.append(
            nt.identdict[etudid]["code_nip"] or ""
        )  # avant-derniere colonne = code_nip
        l.append(etudid)  # derniere colonne = etudid
        F.append(l)

    # Dernière ligne: moyennes, min et max des UEs et modules
    if not hidemodules:  # moy/min/max dans chaque module
        mods_stats = {}  # moduleimpl_id : stats
        for modimpl in modimpls:
            mods_stats[modimpl["moduleimpl_id"]] = nt.get_mod_stats(
                modimpl["moduleimpl_id"]
            )

    def add_bottom_stat(key, title, corner_value=""):
        l = ["", title]
        if civ_nom_prenom:
            l += ["", ""]
        if not hidebac:
            l.append("")
        if format[:3] == "xls" or format == "csv":
            l += [""] * len(partitions)
        else:
            l += [""]
        l.append(corner_value)
        if format[:3] == "xls" or format == "csv":
            for _ in partitions:
                l += [""]  # rangs dans les groupes
        for ue in ues:
            if ue["type"] != UE_SPORT:
                if key == "nb_valid_evals":
                    l.append("")
                elif key == "coef":
                    if sco_preferences.get_preference("use_ue_coefs", formsemestre_id):
                        l.append("%2.3f" % ue["coefficient"])
                    else:
                        l.append("")
                else:
                    if key == "ects":
                        if keep_numeric:
                            l.append(ue[key])
                        else:
                            l.append(str(ue[key]))
                    else:
                        l.append(scu.fmt_note(ue[key], keep_numeric=keep_numeric))
            else:  # UE_SPORT:
                # n'affiche pas la moyenne d'UE dans ce cas
                if not hidemodules:
                    l.append("")
            ue_index.append(len(l) - 1)
            if not hidemodules and not ue["is_external"]:
                for modimpl in modimpls:
                    if modimpl["module"]["ue_id"] == ue["ue_id"]:
                        if key == "coef":
                            coef = modimpl["module"]["coefficient"]
                            if format[:3] != "xls":
                                coef = str(coef)
                            l.append(coef)
                        elif key == "ects":
                            l.append("")  # ECTS module ?
                        else:
                            val = mods_stats[modimpl["moduleimpl_id"]][key]
                            if key == "nb_valid_evals":
                                if (
                                    format[:3] != "xls"
                                ):  # garde val numerique pour excel
                                    val = str(val)
                            else:  # moyenne du module
                                val = scu.fmt_note(val, keep_numeric=keep_numeric)
                            l.append(val)

                        if format == "xlsall":
                            l += _list_notes_evals_stats(
                                mod_evals[modimpl["moduleimpl_id"]], key
                            )
        if modejury:
            l.append("")  # case vide sur ligne "Moyennes"

        l += [""] * len(admission_extra_cols)  # infos admission vides ici
        F.append(l + ["", ""])  # ajoute cellules code_nip et etudid inutilisees ici

    add_bottom_stat(
        "min", "Min", corner_value=scu.fmt_note(nt.moy_min, keep_numeric=keep_numeric)
    )
    add_bottom_stat(
        "max", "Max", corner_value=scu.fmt_note(nt.moy_max, keep_numeric=keep_numeric)
    )
    add_bottom_stat(
        "moy",
        "Moyennes",
        corner_value=scu.fmt_note(nt.moy_moy, keep_numeric=keep_numeric),
    )
    add_bottom_stat("coef", "Coef")
    add_bottom_stat("nb_valid_evals", "Nb évals")
    add_bottom_stat("ects", "ECTS")

    # Generation table au format demandé
    if format == "html":
        # Table format HTML
        H = [
            """
        <script type="text/javascript">
        function va_saisir(formsemestre_id, etudid) {
        loc = 'formsemestre_validation_etud_form?formsemestre_id='+formsemestre_id+'&etudid='+etudid;
        if (SORT_COLUMN_INDEX) {
           loc += '&sortcol=' + SORT_COLUMN_INDEX;
        }
        loc += '#etudid' + etudid;   
        document.location=loc;
        }
        </script>        
        <table class="notes_recapcomplet sortable" id="recapcomplet">
        """
        ]
        if sortcol:  # sort table using JS sorttable
            H.append(
                """<script type="text/javascript">
            function resort_recap() {
            var clid = %d;
            // element <a place par sorttable (ligne de titre)
            lnk = document.getElementById("recap_trtit").childNodes[clid].childNodes[0];
            ts_resortTable(lnk,clid);
            // Scroll window:
            eid = document.location.hash;
            if (eid) {
              var eid = eid.substring(1); // remove #
              var e = document.getElementById(eid);
              if (e) {
                var y = e.offsetTop + e.offsetParent.offsetTop;            
                window.scrollTo(0,y);                
                } 
              
            }
            }
            addEvent(window, "load", resort_recap);
            </script>
            """
                % (int(sortcol))
            )
        cells = '<tr class="recap_row_tit sortbottom" id="recap_trtit">'
        for i in range(len(F[0]) - 2):
            if i in ue_index:
                cls = "recap_tit_ue"
            else:
                cls = "recap_tit"
            if (
                i == 0 or F[0][i] == "classement"
            ):  # Rang: force tri numerique pour sortable
                cls = cls + " sortnumeric"
            if F[0][i] in cod2mod:  # lien vers etat module
                mod = cod2mod[F[0][i]]
                cells += '<td class="%s"><a href="moduleimpl_status?moduleimpl_id=%s" title="%s (%s)">%s</a></td>' % (
                    cls,
                    mod["moduleimpl_id"],
                    mod["module"]["titre"],
                    sco_users.user_info(mod["responsable_id"])["nomcomplet"],
                    F[0][i],
                )
            else:
                cells += '<td class="%s">%s</td>' % (cls, F[0][i])
        if modejury:
            cells += '<td class="recap_tit">Décision</td>'
        ligne_titres = cells + "</tr>"
        H.append(ligne_titres)  # titres
        if disable_etudlink:
            etudlink = "%(name)s"
        else:
            etudlink = '<a href="formsemestre_bulletinetud?formsemestre_id=%(formsemestre_id)s&etudid=%(etudid)s&version=selectedevals" id="%(etudid)s" class="etudinfo">%(name)s</a>'
        ir = 0
        nblines = len(F) - 1
        for l in F[1:]:
            etudid = l[-1]
            if ir >= nblines - 6:
                # dernieres lignes:
                el = l[1]
                styl = (
                    "recap_row_min",
                    "recap_row_max",
                    "recap_row_moy",
                    "recap_row_coef",
                    "recap_row_nbeval",
                    "recap_row_ects",
                )[ir - nblines + 6]
                cells = '<tr class="%s sortbottom">' % styl
            else:
                el = etudlink % {
                    "formsemestre_id": formsemestre_id,
                    "etudid": etudid,
                    "name": l[1],
                }
                if ir % 2 == 0:
                    cells = '<tr class="recap_row_even" id="etudid%s">' % etudid
                else:
                    cells = '<tr class="recap_row_odd" id="etudid%s">' % etudid
            ir += 1
            # XXX nsn = [ x.replace('NA', '-') for x in l[:-2] ]
            # notes sans le NA:
            nsn = l[:-2]  # copy
            for i in range(len(nsn)):
                if nsn[i] == "NA":
                    nsn[i] = "-"
            cells += '<td class="recap_col">%s</td>' % nsn[0]  # rang
            cells += '<td class="recap_col">%s</td>' % el  # nom etud (lien)
            if not hidebac:
                cells += '<td class="recap_col_bac">%s</td>' % nsn[2]  # bac
                idx_col_gr = 3
            else:
                idx_col_gr = 2
            cells += '<td class="recap_col">%s</td>' % nsn[idx_col_gr]  # group name

            # Style si moyenne generale < barre
            idx_col_moy = idx_col_gr + 1
            cssclass = "recap_col_moy"
            try:
                if float(nsn[idx_col_moy]) < (
                    nt.parcours.BARRE_MOY - scu.NOTES_TOLERANCE
                ):
                    cssclass = "recap_col_moy_inf"
            except:
                pass
            cells += '<td class="%s">%s</td>' % (cssclass, nsn[idx_col_moy])
            ue_number = 0
            for i in range(idx_col_moy + 1, len(nsn)):
                if i in ue_index:
                    cssclass = "recap_col_ue"
                    # grise si moy UE < barre
                    ue = ues[ue_number]
                    ue_number += 1

                    if (ir < (nblines - 4)) or (ir == nblines - 3):
                        try:
                            if float(nsn[i]) < nt.parcours.get_barre_ue(
                                ue["type"]
                            ):  # NOTES_BARRE_UE
                                cssclass = "recap_col_ue_inf"
                            elif float(nsn[i]) >= nt.parcours.NOTES_BARRE_VALID_UE:
                                cssclass = "recap_col_ue_val"
                        except:
                            pass
                else:
                    cssclass = "recap_col"
                    if (
                        ir == nblines - 3
                    ):  # si moyenne generale module < barre ue, surligne:
                        try:
                            if float(nsn[i]) < nt.parcours.get_barre_ue(ue["type"]):
                                cssclass = "recap_col_moy_inf"
                        except:
                            pass
                cells += '<td class="%s">%s</td>' % (cssclass, nsn[i])
            if modejury and etudid:
                decision_sem = nt.get_etud_decision_sem(etudid)
                if is_dem[etudid]:
                    code = "DEM"
                    act = ""
                elif decision_sem:
                    code = decision_sem["code"]
                    act = "(modifier)"
                else:
                    code = ""
                    act = "saisir"
                cells += '<td class="decision">%s' % code
                if act:
                    # cells += ' <a href="formsemestre_validation_etud_form?formsemestre_id=%s&etudid=%s">%s</a>' % (formsemestre_id, etudid, act)
                    cells += (
                        """ <a href="#" onclick="va_saisir('%s', '%s')">%s</a>"""
                        % (formsemestre_id, etudid, act)
                    )
                cells += "</td>"
            H.append(cells + "</tr>")

        H.append(ligne_titres)
        H.append("</table>")

        # Form pour choisir partition de classement:
        if not modejury and partitions:
            H.append("Afficher le rang des groupes de: ")
            if not rank_partition_id:
                checked = "checked"
            else:
                checked = ""
            H.append(
                '<input type="radio" name="rank_partition_id" value="" onchange="document.f.submit()" %s/>tous '
                % (checked)
            )
            for p in partitions:
                if p["partition_id"] == rank_partition_id:
                    checked = "checked"
                else:
                    checked = ""
                H.append(
                    '<input type="radio" name="rank_partition_id" value="%s" onchange="document.f.submit()" %s/>%s '
                    % (p["partition_id"], checked, p["partition_name"])
                )

        # recap des decisions jury (nombre dans chaque code):
        if codes_nb:
            H.append("<h4>Décisions du jury</h4><table>")
            cods = list(codes_nb.keys())
            cods.sort()
            for cod in cods:
                H.append("<tr><td>%s</td><td>%d</td></tr>" % (cod, codes_nb[cod]))
            H.append("</table>")
        return "\n".join(H), "", "html"
    elif format == "csv":
        CSV = scu.CSV_LINESEP.join(
            [scu.CSV_FIELDSEP.join([str(x) for x in l]) for l in F]
        )
        semname = sem["titre_num"].replace(" ", "_")
        date = time.strftime("%d-%m-%Y")
        filename = "notes_modules-%s-%s.csv" % (semname, date)
        return CSV, filename, "csv"
    elif format[:3] == "xls":
        semname = sem["titre_num"].replace(" ", "_")
        date = time.strftime("%d-%m-%Y")
        if format == "xls":
            filename = "notes_modules-%s-%s%s" % (semname, date, scu.XLSX_SUFFIX)
        else:
            filename = "notes_modules_evals-%s-%s%s" % (semname, date, scu.XLSX_SUFFIX)
        sheet_name = "notes %s %s" % (semname, date)
        if len(sheet_name) > 31:
            sheet_name = "notes %s %s" % ("...", date)
        xls = sco_excel.excel_simple_table(
            titles=["etudid", "code_nip"] + F[0][:-2],
            lines=[
                [x[-1], x[-2]] + x[:-2] for x in F[1:]
            ],  # reordonne cols (etudid et nip en 1er),
            sheet_name=sheet_name,
        )
        return xls, filename, "xls"
    else:
        raise ValueError("unknown format %s" % format)


def _list_notes_evals(evals, etudid):
    """Liste des notes des evaluations completes de ce module
    (pour table xls avec evals)
    """
    L = []
    for e in evals:
        if (
            e["etat"]["evalcomplete"]
            or e["etat"]["evalattente"]
            or e["publish_incomplete"]
        ):
            NotesDB = sco_evaluations.do_evaluation_get_all_notes(e["evaluation_id"])
            if etudid in NotesDB:
                val = NotesDB[etudid]["value"]
            else:
                # Note manquante mais prise en compte immédiate: affiche ATT
                val = scu.NOTES_ATTENTE
            val_fmt = scu.fmt_note(val, keep_numeric=True)
            L.append(val_fmt)
    return L


def _list_notes_evals_titles(codemodule, evals):
    """Liste des titres des evals completes"""
    L = []
    eval_index = len(evals) - 1
    for e in evals:
        if (
            e["etat"]["evalcomplete"]
            or e["etat"]["evalattente"]
            or e["publish_incomplete"]
        ):
            L.append(codemodule + "-" + str(eval_index) + "-" + e["jour"].isoformat())
        eval_index -= 1
    return L


def _list_notes_evals_stats(evals, key):
    """Liste des stats (moy, ou rien!) des evals completes"""
    L = []
    for e in evals:
        if (
            e["etat"]["evalcomplete"]
            or e["etat"]["evalattente"]
            or e["publish_incomplete"]
        ):
            if key == "moy":
                val = e["etat"]["moy_num"]
                L.append(scu.fmt_note(val, keep_numeric=True))
            elif key == "max":
                L.append(e["note_max"])
            elif key == "min":
                L.append(0.0)
            elif key == "coef":
                L.append(e["coefficient"])
            else:
                L.append("")  # on n'a pas sous la main min/max
    return L


def _formsemestre_recapcomplet_xml(
    formsemestre_id,
    xml_nodate,
    xml_with_decisions=False,
    force_publishing=True,
):
    "XML export: liste tous les bulletins XML."

    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_table_moyennes_triees
    T = nt.get_table_moyennes_triees()
    if not T:
        return "", "", "xml"

    if xml_nodate:
        docdate = ""
    else:
        docdate = datetime.datetime.now().isoformat()
    doc = ElementTree.Element(
        "recapsemestre", formsemestre_id=str(formsemestre_id), date=docdate
    )
    evals = sco_evaluations.do_evaluation_etat_in_sem(formsemestre_id)
    doc.append(
        ElementTree.Element(
            "evals_info",
            nb_evals_completes=str(evals["nb_evals_completes"]),
            nb_evals_en_cours=str(evals["nb_evals_en_cours"]),
            nb_evals_vides=str(evals["nb_evals_vides"]),
            date_derniere_note=str(evals["last_modif"]),
        )
    )
    for t in T:
        etudid = t[-1]
        sco_bulletins_xml.make_xml_formsemestre_bulletinetud(
            formsemestre_id,
            etudid,
            doc=doc,
            force_publishing=force_publishing,
            xml_nodate=xml_nodate,
            xml_with_decisions=xml_with_decisions,
        )
    return (
        sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING),
        "",
        "xml",
    )


def _formsemestre_recapcomplet_json(
    formsemestre_id,
    xml_nodate=False,
    xml_with_decisions=False,
    force_publishing=True,
):
    """JSON export: liste tous les bulletins JSON
    :param xml_nodate(bool): indique la date courante (attribut docdate)
    :param force_publishing: donne les bulletins même si non "publiés sur portail"
    :returns: dict, "", "json"
    """
    if xml_nodate:
        docdate = ""
    else:
        docdate = datetime.datetime.now().isoformat()
    evals = sco_evaluations.do_evaluation_etat_in_sem(formsemestre_id)
    J = {
        "docdate": docdate,
        "formsemestre_id": formsemestre_id,
        "evals_info": {
            "nb_evals_completes": evals["nb_evals_completes"],
            "nb_evals_en_cours": evals["nb_evals_en_cours"],
            "nb_evals_vides": evals["nb_evals_vides"],
            "date_derniere_note": evals["last_modif"],
        },
        "bulletins": [],
    }
    bulletins = J["bulletins"]
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > get_table_moyennes_triees
    T = nt.get_table_moyennes_triees()
    for t in T:
        etudid = t[-1]
        bulletins.append(
            sco_bulletins_json.formsemestre_bulletinetud_published_dict(
                formsemestre_id,
                etudid,
                force_publishing=force_publishing,
                xml_with_decisions=xml_with_decisions,
            )
        )
    return J, "", "json"


def formsemestres_bulletins(annee_scolaire):
    """Tous les bulletins des semestres publiés des semestres de l'année indiquée.
    :param annee_scolaire(int): année de début de l'année scoalaire
    :returns: JSON
    """
    jslist = []
    sems = sco_formsemestre.list_formsemestre_by_etape(annee_scolaire=annee_scolaire)
    log("formsemestres_bulletins(%s): %d sems" % (annee_scolaire, len(sems)))
    for sem in sems:
        J, _, _ = _formsemestre_recapcomplet_json(
            sem["formsemestre_id"], force_publishing=False
        )
        jslist.append(J)

    return scu.sendJSON(jslist)
