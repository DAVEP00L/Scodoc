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

"""Edition des PV de jury

PV Jury IUTV 2006: on détaillait 8 cas:
Jury de semestre n
    On a 8 types de décisions:
    Passages:
    1. passage de ceux qui ont validés Sn-1
    2. passage avec compensation Sn-1, Sn
    3. passage sans validation de Sn avec validation d'UE
    4. passage sans validation de Sn sans validation d'UE

    Redoublements:
    5. redoublement de Sn-1 et Sn sans validation d'UE pour Sn
    6. redoublement de Sn-1 et Sn avec validation d'UE pour Sn

    Reports
    7. report sans validation d'UE

    8. non validation de Sn-1 et Sn et non redoublement
"""

import time
from operator import itemgetter
from reportlab.platypus import Paragraph
from reportlab.lib import styles

import flask
from flask import url_for, g, request

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_pdf
from app.scodoc import sco_preferences
from app.scodoc import sco_pvpdf
from app.scodoc import sco_etud
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_codes_parcours import NO_SEMESTRE_ID
from app.scodoc.sco_pdf import PDFLOCK
from app.scodoc.TrivialFormulator import TrivialFormulator


def _descr_decisions_ues(nt, etudid, decisions_ue, decision_sem):
    """Liste des UE validées dans ce semestre"""
    if not decisions_ue:
        return []
    uelist = []
    # Les UE validées dans ce semestre:
    for ue_id in decisions_ue.keys():
        try:
            if decisions_ue[ue_id] and (
                decisions_ue[ue_id]["code"] == sco_codes_parcours.ADM
                or (
                    # XXX ceci devrait dépendre du parcours et non pas être une option ! #sco8
                    scu.CONFIG.CAPITALIZE_ALL_UES
                    and sco_codes_parcours.code_semestre_validant(decision_sem["code"])
                )
            ):
                ue = sco_edit_ue.ue_list(args={"ue_id": ue_id})[0]
                uelist.append(ue)
        except:
            log("descr_decisions_ues: ue_id=%s decisions_ue=%s" % (ue_id, decisions_ue))
    # Les UE capitalisées dans d'autres semestres:
    for ue in nt.ue_capitalisees[etudid]:
        try:
            uelist.append(nt.get_etud_ue_status(etudid, ue["ue_id"])["ue"])
        except KeyError:
            pass
    uelist.sort(key=itemgetter("numero"))

    return uelist


def _descr_decision_sem(etat, decision_sem):
    "résumé textuel de la décision de semestre"
    if etat == "D":
        decision = "Démission"
    else:
        if decision_sem:
            cod = decision_sem["code"]
            decision = sco_codes_parcours.CODES_EXPL.get(cod, "")  # + ' (%s)' % cod
        else:
            decision = ""
    return decision


def _descr_decision_sem_abbrev(etat, decision_sem):
    "résumé textuel tres court (code) de la décision de semestre"
    if etat == "D":
        decision = "Démission"
    else:
        if decision_sem:
            decision = decision_sem["code"]
        else:
            decision = ""
    return decision


def descr_autorisations(autorisations):
    "résumé textuel des autorisations d'inscription (-> 'S1, S3' )"
    alist = []
    for aut in autorisations:
        alist.append("S" + str(aut["semestre_id"]))
    return ", ".join(alist)


def _comp_ects_by_ue_code_and_type(nt, decision_ues):
    """Calcul somme des ECTS validés dans ce semestre (sans les UE capitalisées)
    decision_ues est le resultat de nt.get_etud_decision_ues
    Chaque resultat est un dict: { ue_code : ects }
    """
    if not decision_ues:
        return {}, {}

    ects_by_ue_code = {}
    ects_by_ue_type = scu.DictDefault(defaultvalue=0)  # { ue_type : ects validés }
    for ue_id in decision_ues:
        d = decision_ues[ue_id]
        ue = nt.uedict[ue_id]
        ects_by_ue_code[ue["ue_code"]] = d["ects"]
        ects_by_ue_type[ue["type"]] += d["ects"]

    return ects_by_ue_code, ects_by_ue_type


def _comp_ects_capitalises_by_ue_code(nt, etudid):
    """Calcul somme des ECTS des UE capitalisees"""
    ues = nt.get_ues()
    ects_by_ue_code = {}
    for ue in ues:
        ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
        if ue_status["is_capitalized"]:
            try:
                ects_val = float(ue_status["ue"]["ects"])
            except (ValueError, TypeError):
                ects_val = 0.0
            ects_by_ue_code[ue["ue_code"]] = ects_val

    return ects_by_ue_code


def _sum_ects_dicts(s, t):
    """Somme deux dictionnaires { ue_code : ects },
    quand une UE de même code apparait deux fois, prend celle avec le plus d'ECTS.
    """
    sum_ects = sum(s.values()) + sum(t.values())
    for ue_code in set(s).intersection(set(t)):
        sum_ects -= min(s[ue_code], t[ue_code])
    return sum_ects


def dict_pvjury(
    formsemestre_id,
    etudids=None,
    with_prev=False,
    with_parcours_decisions=False,
):
    """Données pour édition jury
    etudids == None => tous les inscrits, sinon donne la liste des ids
    Si with_prev: ajoute infos sur code jury semestre precedent
    Si with_parcours_decisions: ajoute infos sur code decision jury de tous les semestre du parcours
    Résultat:
    {
    'date' : date de la decision la plus recente,
    'formsemestre' : sem,
    'formation' : { 'acronyme' :, 'titre': ... }
    'decisions' : { [ { 'identite' : {'nom' :, 'prenom':,  ...,},
                        'etat' : I ou D ou DEF
                        'decision_sem' : {'code':, 'code_prev': },
                        'decisions_ue' : {  ue_id : { 'code' : ADM|CMP|AJ, 'event_date' :,
                                             'acronyme', 'numero': } },
                        'autorisations' : [ { 'semestre_id' : { ... } } ],
                        'validation_parcours' : True si parcours validé (diplome obtenu)
                        'prev_code' : code (calculé slt si with_prev),
                        'mention' : mention (en fct moy gen),
                        'sum_ects' : total ECTS acquis dans ce semestre (incluant les UE capitalisées)
                        'sum_ects_capitalises' : somme des ECTS des UE capitalisees
                    }
                    ]
                  },
     'decisions_dict' : { etudid : decision (comme ci-dessus) },
    }
    """
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etudids, get_etud_etat, get_etud_decision_sem, get_etud_decision_ues
    if etudids is None:
        etudids = nt.get_etudids()
    if not etudids:
        return {}
    cnx = ndb.GetDBConnexion()
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    max_date = "0000-01-01"
    has_prev = False  # vrai si au moins un etudiant a un code prev
    semestre_non_terminal = False  # True si au moins un etudiant a un devenir

    L = []
    D = {}  # même chose que L, mais { etudid : dec }
    for etudid in etudids:
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
        semestre_non_terminal = semestre_non_terminal or Se.semestre_non_terminal
        d = {}
        d["identite"] = nt.identdict[etudid]
        d["etat"] = nt.get_etud_etat(
            etudid
        )  # I|D|DEF  (inscription ou démission ou défaillant)
        d["decision_sem"] = nt.get_etud_decision_sem(etudid)
        d["decisions_ue"] = nt.get_etud_decision_ues(etudid)
        d["last_formsemestre_id"] = Se.get_semestres()[
            -1
        ]  # id du dernier semestre (chronologiquement) dans lequel il a été inscrit

        ects_capitalises_by_ue_code = _comp_ects_capitalises_by_ue_code(nt, etudid)
        d["sum_ects_capitalises"] = sum(ects_capitalises_by_ue_code.values())
        ects_by_ue_code, ects_by_ue_type = _comp_ects_by_ue_code_and_type(
            nt, d["decisions_ue"]
        )
        d["sum_ects"] = _sum_ects_dicts(ects_capitalises_by_ue_code, ects_by_ue_code)
        d["sum_ects_by_type"] = ects_by_ue_type

        if d["decision_sem"] and sco_codes_parcours.code_semestre_validant(
            d["decision_sem"]["code"]
        ):
            d["mention"] = scu.get_mention(nt.get_etud_moy_gen(etudid))
        else:
            d["mention"] = ""
        # Versions "en français": (avec les UE capitalisées d'ailleurs)
        dec_ue_list = _descr_decisions_ues(
            nt, etudid, d["decisions_ue"], d["decision_sem"]
        )
        d["decisions_ue_nb"] = len(
            dec_ue_list
        )  # avec les UE capitalisées, donc des éventuels doublons
        # Mais sur la description (eg sur les bulletins), on ne veut pas
        # afficher ces doublons: on uniquifie sur ue_code
        _codes = set()
        ue_uniq = []
        for ue in dec_ue_list:
            if ue["ue_code"] not in _codes:
                ue_uniq.append(ue)
                _codes.add(ue["ue_code"])

        d["decisions_ue_descr"] = ", ".join([ue["acronyme"] for ue in ue_uniq])
        d["decision_sem_descr"] = _descr_decision_sem(d["etat"], d["decision_sem"])

        d["autorisations"] = sco_parcours_dut.formsemestre_get_autorisation_inscription(
            etudid, formsemestre_id
        )
        d["autorisations_descr"] = descr_autorisations(d["autorisations"])

        d["validation_parcours"] = Se.parcours_validated()
        d["parcours"] = Se.get_parcours_descr(filter_futur=True)
        if with_parcours_decisions:
            d["parcours_decisions"] = Se.get_parcours_decisions()
        # Observations sur les compensations:
        compensators = sco_parcours_dut.scolar_formsemestre_validation_list(
            cnx, args={"compense_formsemestre_id": formsemestre_id, "etudid": etudid}
        )
        obs = []
        for compensator in compensators:
            # nb: il ne devrait y en avoir qu'un !
            csem = sco_formsemestre.get_formsemestre(compensator["formsemestre_id"])
            obs.append(
                "%s compensé par %s (%s)"
                % (sem["sem_id_txt"], csem["sem_id_txt"], csem["anneescolaire"])
            )

        if d["decision_sem"] and d["decision_sem"]["compense_formsemestre_id"]:
            compensed = sco_formsemestre.get_formsemestre(
                d["decision_sem"]["compense_formsemestre_id"]
            )
            obs.append(
                "%s compense %s (%s)"
                % (
                    sem["sem_id_txt"],
                    compensed["sem_id_txt"],
                    compensed["anneescolaire"],
                )
            )

        d["observation"] = ", ".join(obs)

        # Cherche la date de decision (sem ou UE) la plus récente:
        if d["decision_sem"]:
            date = ndb.DateDMYtoISO(d["decision_sem"]["event_date"])
            if date and date > max_date:  # decision plus recente
                max_date = date
        if d["decisions_ue"]:
            for dec_ue in d["decisions_ue"].values():
                if dec_ue:
                    date = ndb.DateDMYtoISO(dec_ue["event_date"])
                    if date and date > max_date:  # decision plus recente
                        max_date = date
        # Code semestre precedent
        if with_prev:  # optionnel car un peu long...
            info = sco_etud.get_etud_info(etudid=etudid, filled=True)
            if not info:
                continue  # should not occur
            etud = info[0]
            if Se.prev and Se.prev_decision:
                d["prev_decision_sem"] = Se.prev_decision
                d["prev_code"] = Se.prev_decision["code"]
                d["prev_code_descr"] = _descr_decision_sem("I", Se.prev_decision)
                d["prev"] = Se.prev
                has_prev = True
            else:
                d["prev_decision_sem"] = None
                d["prev_code"] = ""
                d["prev_code_descr"] = ""
            d["Se"] = Se

        L.append(d)
        D[etudid] = d

    return {
        "date": ndb.DateISOtoDMY(max_date),
        "formsemestre": sem,
        "has_prev": has_prev,
        "semestre_non_terminal": semestre_non_terminal,
        "formation": sco_formations.formation_list(
            args={"formation_id": sem["formation_id"]}
        )[0],
        "decisions": L,
        "decisions_dict": D,
    }


def pvjury_table(
    dpv,
    only_diplome=False,
    anonymous=False,
    with_parcours_decisions=False,
    with_paragraph_nom=False,  # cellule paragraphe avec nom, date, code NIP
):
    """idem mais rend list de dicts
    Si only_diplome, n'extrait que les etudiants qui valident leur diplome.
    """
    sem = dpv["formsemestre"]
    formsemestre_id = sem["formsemestre_id"]
    sem_id_txt_sp = sem["sem_id_txt"]
    if sem_id_txt_sp:
        sem_id_txt_sp = " " + sem_id_txt_sp
    titles = {
        "etudid": "etudid",
        "code_nip": "NIP",
        "nomprenom": "Nom",  # si with_paragraph_nom, sera un Paragraph
        "parcours": "Parcours",
        "decision": "Décision" + sem_id_txt_sp,
        "mention": "Mention",
        "ue_cap": "UE" + sem_id_txt_sp + " capitalisées",
        "ects": "ECTS",
        "devenir": "Devenir",
        "validation_parcours_code": "Résultat au diplôme",
        "observations": "Observations",
    }
    if anonymous:
        titles["nomprenom"] = "Code"
    columns_ids = ["nomprenom", "parcours"]

    if with_parcours_decisions:
        all_idx = set()
        for e in dpv["decisions"]:
            all_idx |= set(e["parcours_decisions"].keys())
        sem_ids = sorted(all_idx)
        for i in sem_ids:
            if i != NO_SEMESTRE_ID:
                titles[i] = "S%d" % i
            else:
                titles[i] = "S"  # pas très parlant ?
            columns_ids += [i]

    if dpv["has_prev"]:
        id_prev = sem["semestre_id"] - 1  # numero du semestre precedent
        titles["prev_decision"] = "Décision S%s" % id_prev
        columns_ids += ["prev_decision"]

    columns_ids += ["decision"]
    if sco_preferences.get_preference("bul_show_mention", formsemestre_id):
        columns_ids += ["mention"]
    columns_ids += ["ue_cap"]
    if sco_preferences.get_preference("bul_show_ects", formsemestre_id):
        columns_ids += ["ects"]

    # XXX if not dpv["semestre_non_terminal"]:
    # La colonne doit être présente: redoublants validant leur diplome
    # en répétant un semestre ancien: exemple: S1 (ADM), S2 (ADM), S3 (AJ), S4 (ADM), S3 (ADM)=> diplôme
    columns_ids += ["validation_parcours_code"]
    columns_ids += ["devenir"]
    columns_ids += ["observations"]

    lines = []
    for e in dpv["decisions"]:
        sco_etud.format_etud_ident(e["identite"])
        l = {
            "etudid": e["identite"]["etudid"],
            "code_nip": e["identite"]["code_nip"],
            "nomprenom": e["identite"]["nomprenom"],
            "_nomprenom_target": url_for(
                "scolar.ficheEtud",
                scodoc_dept=g.scodoc_dept,
                etudid=e["identite"]["etudid"],
            ),
            "_nomprenom_td_attrs": 'id="%s" class="etudinfo"' % e["identite"]["etudid"],
            "parcours": e["parcours"],
            "decision": _descr_decision_sem_abbrev(e["etat"], e["decision_sem"]),
            "ue_cap": e["decisions_ue_descr"],
            "validation_parcours_code": "ADM" if e["validation_parcours"] else "",
            "devenir": e["autorisations_descr"],
            "observations": ndb.unquote(e["observation"]),
            "mention": e["mention"],
            "ects": str(e["sum_ects"]),
        }
        if with_paragraph_nom:
            cell_style = styles.ParagraphStyle({})
            cell_style.fontSize = sco_preferences.get_preference(
                "SCOLAR_FONT_SIZE", formsemestre_id
            )
            cell_style.fontName = sco_preferences.get_preference(
                "PV_FONTNAME", formsemestre_id
            )
            cell_style.leading = 1.0 * sco_preferences.get_preference(
                "SCOLAR_FONT_SIZE", formsemestre_id
            )  # vertical space
            i = e["identite"]
            l["nomprenom"] = [
                Paragraph(sco_pdf.SU(i["nomprenom"]), cell_style),
                Paragraph(sco_pdf.SU(i["code_nip"]), cell_style),
                Paragraph(
                    sco_pdf.SU(
                        "Né le %s" % i["date_naissance"]
                        + (" à %s" % i["lieu_naissance"] if i["lieu_naissance"] else "")
                        + (" (%s)" % i["dept_naissance"] if i["dept_naissance"] else "")
                    ),
                    cell_style,
                ),
            ]
        if anonymous:
            # Mode anonyme: affiche INE ou sinon NIP, ou id
            l["nomprenom"] = (
                e["identite"]["code_ine"]
                or e["identite"]["code_nip"]
                or e["identite"]["etudid"]
            )
        if with_parcours_decisions:
            for i in e[
                "parcours_decisions"
            ]:  # or equivalently: l.update(e['parcours_decisions'])
                l[i] = e["parcours_decisions"][i]

        if e["validation_parcours"]:
            l["devenir"] = "Diplôme obtenu"
        if dpv["has_prev"]:
            l["prev_decision"] = _descr_decision_sem_abbrev(
                None, e["prev_decision_sem"]
            )
        if e["validation_parcours"] or not only_diplome:
            lines.append(l)
    return lines, titles, columns_ids


def formsemestre_pvjury(formsemestre_id, format="html", publish=True):
    """Page récapitulant les décisions de jury
    dpv: result of dict_pvjury
    """
    footer = html_sco_header.sco_footer()

    dpv = dict_pvjury(formsemestre_id, with_prev=True)
    if not dpv:
        if format == "html":
            return (
                html_sco_header.sco_header()
                + "<h2>Aucune information disponible !</h2>"
                + footer
            )
        else:
            return None
    sem = dpv["formsemestre"]
    formsemestre_id = sem["formsemestre_id"]

    rows, titles, columns_ids = pvjury_table(dpv)
    if format != "html" and format != "pdf":
        columns_ids = ["etudid", "code_nip"] + columns_ids

    tab = GenTable(
        rows=rows,
        titles=titles,
        columns_ids=columns_ids,
        filename=scu.make_filename("decisions " + sem["titreannee"]),
        origin="Généré par %s le " % scu.sco_version.SCONAME
        + scu.timedate_human_repr()
        + "",
        caption="Décisions jury pour " + sem["titreannee"],
        html_class="table_leftalign",
        html_sortable=True,
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )
    if format != "html":
        return tab.make_page(
            format=format,
            with_html_headers=False,
            publish=publish,
        )
    tab.base_url = "%s?formsemestre_id=%s" % (request.base_url, formsemestre_id)
    H = [
        html_sco_header.html_sem_header(
            "Décisions du jury pour le semestre",
            sem,
            init_qtip=True,
            javascripts=["js/etud_info.js"],
        ),
        """<p>(dernière modif le %s)</p>""" % dpv["date"],
    ]

    H.append(
        '<ul><li><a class="stdlink" href="formsemestre_lettres_individuelles?formsemestre_id=%s">Courriers individuels (classeur pdf)</a></li>'
        % formsemestre_id
    )
    H.append(
        '<li><a class="stdlink" href="formsemestre_pvjury_pdf?formsemestre_id=%s">PV officiel (pdf)</a></li></ul>'
        % formsemestre_id
    )

    H.append(tab.html())

    # Count number of cases for each decision
    counts = scu.DictDefault()
    for row in rows:
        counts[row["decision"]] += 1
        # add codes for previous (for explanation, without count)
        if "prev_decision" in row and row["prev_decision"]:
            counts[row["prev_decision"]] += 0
    # Légende des codes
    codes = list(counts.keys())  # sco_codes_parcours.CODES_EXPL.keys()
    codes.sort()
    H.append("<h3>Explication des codes</h3>")
    lines = []
    for code in codes:
        lines.append(
            {
                "code": code,
                "count": counts[code],
                "expl": sco_codes_parcours.CODES_EXPL.get(code, ""),
            }
        )

    H.append(
        GenTable(
            rows=lines,
            titles={"code": "Code", "count": "Nombre", "expl": ""},
            columns_ids=("code", "count", "expl"),
            html_class="table_leftalign",
            html_sortable=True,
            preferences=sco_preferences.SemPreferences(formsemestre_id),
        ).html()
    )
    H.append("<p></p>")  # force space at bottom
    return "\n".join(H) + footer


# ---------------------------------------------------------------------------


def formsemestre_pvjury_pdf(formsemestre_id, group_ids=[], etudid=None):
    """Generation PV jury en PDF: saisie des paramètres
    Si etudid, PV pour un seul etudiant. Sinon, tout les inscrits au groupe indiqué.
    """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    # Mise à jour des groupes d'étapes:
    sco_groups.create_etapes_partition(formsemestre_id)
    groups_infos = None
    if etudid:
        # PV pour ce seul étudiant:
        etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
        etuddescr = '<a class="discretelink" href="ficheEtud?etudid=%s">%s</a>' % (
            etudid,
            etud["nomprenom"],
        )
        etudids = [etudid]
    else:
        etuddescr = ""
        if not group_ids:
            # tous les inscrits du semestre
            group_ids = [sco_groups.get_default_group(formsemestre_id)]

        groups_infos = sco_groups_view.DisplayedGroupsInfos(
            group_ids, formsemestre_id=formsemestre_id
        )
        etudids = [m["etudid"] for m in groups_infos.members]

    H = [
        html_sco_header.html_sem_header(
            "Edition du PV de jury %s" % etuddescr,
            sem=sem,
            javascripts=sco_groups_view.JAVASCRIPTS,
            cssstyles=sco_groups_view.CSSSTYLES,
            init_qtip=True,
        ),
        """<p class="help">Utiliser cette page pour éditer des versions provisoires des PV.
          <span class="fontred">Il est recommandé d'archiver les versions définitives: <a href="formsemestre_archive?formsemestre_id=%s">voir cette page</a></span>
          </p>"""
        % formsemestre_id,
    ]
    F = [
        """<p><em>Voir aussi si besoin les réglages sur la page "Paramétrage" (accessible à l'administrateur du département).</em>
        </p>""",
        html_sco_header.sco_footer(),
    ]
    descr = descrform_pvjury(sem)
    if etudid:
        descr.append(("etudid", {"input_type": "hidden"}))

    if groups_infos:
        menu_choix_groupe = (
            """<div class="group_ids_sel_menu">Groupes d'étudiants à lister sur le PV: """
            + sco_groups_view.menu_groups_choice(groups_infos)
            + """</div>"""
        )
    else:
        menu_choix_groupe = ""  # un seul etudiant à editer
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        cancelbutton="Annuler",
        method="get",
        submitlabel="Générer document",
        name="tf",
        formid="group_selector",
        html_foot_markup=menu_choix_groupe,
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + "\n".join(F)
    elif tf[0] == -1:
        return flask.redirect(
            "formsemestre_pvjury?formsemestre_id=%s" % (formsemestre_id)
        )
    else:
        # submit
        dpv = dict_pvjury(formsemestre_id, etudids=etudids, with_prev=True)
        if tf[2]["showTitle"]:
            tf[2]["showTitle"] = True
        else:
            tf[2]["showTitle"] = False
        if tf[2]["anonymous"]:
            tf[2]["anonymous"] = True
        else:
            tf[2]["anonymous"] = False
        try:
            PDFLOCK.acquire()
            pdfdoc = sco_pvpdf.pvjury_pdf(
                dpv,
                numeroArrete=tf[2]["numeroArrete"],
                VDICode=tf[2]["VDICode"],
                date_commission=tf[2]["date_commission"],
                date_jury=tf[2]["date_jury"],
                showTitle=tf[2]["showTitle"],
                pv_title=tf[2]["pv_title"],
                with_paragraph_nom=tf[2]["with_paragraph_nom"],
                anonymous=tf[2]["anonymous"],
            )
        finally:
            PDFLOCK.release()
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        dt = time.strftime("%Y-%m-%d")
        if groups_infos:
            groups_filename = "-" + groups_infos.groups_filename
        else:
            groups_filename = ""
        filename = "PV-%s%s-%s.pdf" % (sem["titre_num"], groups_filename, dt)
        return scu.sendPDFFile(pdfdoc, filename)


def descrform_pvjury(sem):
    """Définition de formulaire pour PV jury PDF"""
    F = sco_formations.formation_list(formation_id=sem["formation_id"])[0]
    return [
        (
            "date_commission",
            {
                "input_type": "text",
                "size": 50,
                "title": "Date de la commission",
                "explanation": "(format libre)",
            },
        ),
        (
            "date_jury",
            {
                "input_type": "text",
                "size": 50,
                "title": "Date du Jury",
                "explanation": "(si le jury a eu lieu)",
            },
        ),
        (
            "numeroArrete",
            {
                "input_type": "text",
                "size": 50,
                "title": "Numéro de l'arrêté du président",
                "explanation": "le président de l'Université prend chaque année un arrêté formant les jurys",
            },
        ),
        (
            "VDICode",
            {
                "input_type": "text",
                "size": 15,
                "title": "VDI et Code",
                "explanation": "VDI et code du diplôme Apogée (format libre, n'est pas vérifié par ScoDoc)",
            },
        ),
        (
            "pv_title",
            {
                "input_type": "text",
                "size": 64,
                "title": "Titre du PV",
                "explanation": "par défaut, titre officiel de la formation",
                "default": F["titre_officiel"],
            },
        ),
        (
            "showTitle",
            {
                "input_type": "checkbox",
                "title": "Indiquer en plus le titre du semestre sur le PV",
                "explanation": '(le titre est "%s")' % sem["titre"],
                "labels": [""],
                "allowed_values": ("1",),
            },
        ),
        (
            "with_paragraph_nom",
            {
                "input_type": "boolcheckbox",
                "title": "Avec date naissance et code",
                "explanation": "ajoute informations sous le nom",
                "default": True,
            },
        ),
        (
            "anonymous",
            {
                "input_type": "checkbox",
                "title": "PV anonyme",
                "explanation": "remplace nom par code étudiant (INE ou NIP)",
                "labels": [""],
                "allowed_values": ("1",),
            },
        ),
        ("formsemestre_id", {"input_type": "hidden"}),
    ]


def formsemestre_lettres_individuelles(formsemestre_id, group_ids=[]):
    "Lettres avis jury en PDF"
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not group_ids:
        # tous les inscrits du semestre
        group_ids = [sco_groups.get_default_group(formsemestre_id)]
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, formsemestre_id=formsemestre_id
    )
    etudids = [m["etudid"] for m in groups_infos.members]

    H = [
        html_sco_header.html_sem_header(
            "Édition des lettres individuelles",
            sem=sem,
            javascripts=sco_groups_view.JAVASCRIPTS,
            cssstyles=sco_groups_view.CSSSTYLES,
            init_qtip=True,
        ),
        """<p class="help">Utiliser cette page pour éditer des versions provisoires des PV.
          <span class="fontred">Il est recommandé d'archiver les versions définitives: <a href="formsemestre_archive?formsemestre_id=%s">voir cette page</a></span></p>
         """
        % formsemestre_id,
    ]
    F = html_sco_header.sco_footer()
    descr = descrform_lettres_individuelles()
    menu_choix_groupe = (
        """<div class="group_ids_sel_menu">Groupes d'étudiants à lister: """
        + sco_groups_view.menu_groups_choice(groups_infos)
        + """</div>"""
    )

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        cancelbutton="Annuler",
        method="POST",
        submitlabel="Générer document",
        name="tf",
        formid="group_selector",
        html_foot_markup=menu_choix_groupe,
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + F
    elif tf[0] == -1:
        return flask.redirect(
            "formsemestre_pvjury?formsemestre_id=%s" % (formsemestre_id)
        )
    else:
        # submit
        sf = tf[2]["signature"]
        signature = sf.read()  # image of signature
        try:
            PDFLOCK.acquire()
            pdfdoc = sco_pvpdf.pdf_lettres_individuelles(
                formsemestre_id,
                etudids=etudids,
                date_jury=tf[2]["date_jury"],
                date_commission=tf[2]["date_commission"],
                signature=signature,
            )
        finally:
            PDFLOCK.release()
        if not pdfdoc:
            return flask.redirect(
                "formsemestre_status?formsemestre_id={}&head_message=Aucun%20%C3%A9tudiant%20n%27a%20de%20d%C3%A9cision%20de%20jury".format(
                    formsemestre_id
                )
            )
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        dt = time.strftime("%Y-%m-%d")
        groups_filename = "-" + groups_infos.groups_filename
        filename = "lettres-%s%s-%s.pdf" % (sem["titre_num"], groups_filename, dt)
        return scu.sendPDFFile(pdfdoc, filename)


def descrform_lettres_individuelles():
    return [
        (
            "date_commission",
            {
                "input_type": "text",
                "size": 50,
                "title": "Date de la commission",
                "explanation": "(format libre)",
            },
        ),
        (
            "date_jury",
            {
                "input_type": "text",
                "size": 50,
                "title": "Date du Jury",
                "explanation": "(si le jury a eu lieu)",
            },
        ),
        (
            "signature",
            {
                "input_type": "file",
                "size": 30,
                "explanation": "optionnel: image scannée de la signature",
            },
        ),
        ("formsemestre_id", {"input_type": "hidden"}),
    ]
