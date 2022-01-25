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

"""Feuille excel pour preparation des jurys
"""
import time

from openpyxl.styles.numbers import FORMAT_NUMBER_00

from flask import request
from flask_login import current_user

import app.scodoc.sco_utils as scu
from app.scodoc import sco_abs
from app.scodoc import sco_groups
from app.scodoc import sco_cache
from app.scodoc import sco_excel
from app.scodoc import sco_formsemestre
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_codes_parcours
import sco_version
from app.scodoc import sco_etud
from app.scodoc import sco_preferences
from app.scodoc.sco_excel import ScoExcelSheet


def feuille_preparation_jury(formsemestre_id):
    "Feuille excel pour preparation des jurys"
    nt = sco_cache.NotesTableCache.get(
        formsemestre_id
    )  # > get_etudids, get_etud_moy_gen, get_ues, get_etud_ue_status, get_etud_decision_sem, identdict,
    etudids = nt.get_etudids(sorted=True)  # tri par moy gen
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)

    etud_groups = sco_groups.formsemestre_get_etud_groupnames(formsemestre_id)
    main_partition_id = sco_groups.formsemestre_get_main_partition(formsemestre_id)[
        "partition_id"
    ]

    prev_moy_ue = scu.DictDefault(defaultvalue={})  # ue_code_s : { etudid : moy ue }
    prev_ue_acro = {}  # ue_code_s : acronyme (à afficher)
    prev_moy = {}  # moyennes gen sem prec
    moy_ue = scu.DictDefault(defaultvalue={})  # ue_acro : moyennes { etudid : moy ue }
    ue_acro = {}  # ue_code_s : acronyme (à afficher)
    moy = {}  # moyennes gen
    moy_inter = {}  # moyenne gen. sur les 2 derniers semestres
    code = {}  # decision existantes s'il y en a
    autorisations = {}
    prev_code = {}  # decisions sem prec
    assidu = {}
    parcours = {}  # etudid : parcours, sous la forme S1, S2, S2, S3
    groupestd = {}  # etudid : nom groupe principal
    nbabs = {}
    nbabsjust = {}
    for etudid in etudids:
        info = sco_etud.get_etud_info(etudid=etudid, filled=True)
        if not info:
            continue  # should not occur...
        etud = info[0]
        Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
        if Se.prev:
            ntp = sco_cache.NotesTableCache.get(
                Se.prev["formsemestre_id"]
            )  # > get_ues, get_etud_ue_status, get_etud_moy_gen, get_etud_decision_sem
            for ue in ntp.get_ues(filter_sport=True):
                ue_status = ntp.get_etud_ue_status(etudid, ue["ue_id"])
                ue_code_s = (
                    ue["ue_code"] + "_%s" % ntp.sem["semestre_id"]
                )  # code indentifiant l'UE
                prev_moy_ue[ue_code_s][etudid] = ue_status["moy"]
                #                prev_ue_acro[ue_code_s] = (ue['numero'], ue['acronyme'])
                prev_ue_acro[ue_code_s] = (ue["numero"], ue["acronyme"], ue["titre"])
            prev_moy[etudid] = ntp.get_etud_moy_gen(etudid)
            prev_decision = ntp.get_etud_decision_sem(etudid)
            if prev_decision:
                prev_code[etudid] = prev_decision["code"]
                if prev_decision["compense_formsemestre_id"]:
                    prev_code[etudid] += "+"  # indique qu'il a servi a compenser

        moy[etudid] = nt.get_etud_moy_gen(etudid)
        for ue in nt.get_ues(filter_sport=True):
            ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
            ue_code_s = ue["ue_code"] + "_%s" % nt.sem["semestre_id"]
            moy_ue[ue_code_s][etudid] = ue_status["moy"]
            #            ue_acro[ue_code_s] = (ue['numero'], ue['acronyme'])
            ue_acro[ue_code_s] = (ue["numero"], ue["acronyme"], ue["titre"])

        if Se.prev:
            try:
                moy_inter[etudid] = (moy[etudid] + prev_moy[etudid]) / 2.0
            except:
                pass

        decision = nt.get_etud_decision_sem(etudid)
        if decision:
            code[etudid] = decision["code"]
            if decision["compense_formsemestre_id"]:
                code[etudid] += "+"  # indique qu'il a servi a compenser
            assidu[etudid] = {False: "Non", True: "Oui"}.get(decision["assidu"], "")
        aut_list = sco_parcours_dut.formsemestre_get_autorisation_inscription(
            etudid, formsemestre_id
        )
        autorisations[etudid] = ", ".join(["S%s" % x["semestre_id"] for x in aut_list])
        # parcours:
        parcours[etudid] = Se.get_parcours_descr()
        # groupe principal (td)
        groupestd[etudid] = ""
        for s in etud["sems"]:
            if s["formsemestre_id"] == formsemestre_id:
                groupestd[etudid] = etud_groups.get(etudid, {}).get(
                    main_partition_id, ""
                )
        # absences:
        e_nbabs, e_nbabsjust = sco_abs.get_abs_count(etudid, sem)
        nbabs[etudid] = e_nbabs
        nbabsjust[etudid] = e_nbabs - e_nbabsjust

    # Codes des UE "semestre précédent":
    ue_prev_codes = list(prev_moy_ue.keys())
    ue_prev_codes.sort(
        key=lambda x, prev_ue_acro=prev_ue_acro: prev_ue_acro[  # pylint: disable=undefined-variable
            x
        ]
    )
    # Codes des UE "semestre courant":
    ue_codes = list(moy_ue.keys())
    ue_codes.sort(
        key=lambda x, ue_acro=ue_acro: ue_acro[x]  # pylint: disable=undefined-variable
    )

    sid = sem["semestre_id"]
    sn = sp = ""
    if sid >= 0:
        sn = "S%s" % sid
        if prev_moy:  # si qq chose dans precedent
            sp = "S%s" % (sid - 1)

    ws = sco_excel.ScoExcelSheet(sheet_name="Prepa Jury %s" % sn)
    # génération des styles
    style_bold = sco_excel.excel_make_style(size=10, bold=True)
    style_center = sco_excel.excel_make_style(halign="center")
    style_boldcenter = sco_excel.excel_make_style(bold=True, halign="center")
    style_moy = sco_excel.excel_make_style(
        bold=True, halign="center", bgcolor=sco_excel.COLORS.LIGHT_YELLOW
    )
    style_note = sco_excel.excel_make_style(
        halign="right", number_format=FORMAT_NUMBER_00
    )
    style_note_bold = sco_excel.excel_make_style(
        halign="right", bold=True, number_format="General"
    )

    # Première ligne
    ws.append_single_cell_row(
        "Feuille préparation Jury %s" % scu.unescape_html(sem["titreannee"]), style_bold
    )
    ws.append_blank_row()

    # Ligne de titre
    titles = ["Rang"]
    if sco_preferences.get_preference("prepa_jury_nip"):
        titles.append("NIP")
    if sco_preferences.get_preference("prepa_jury_ine"):
        titles.append("INE")
    titles += [
        "etudid",
        "Civ.",
        "Nom",
        "Prénom",
        "Naissance",
        "Bac",
        "Spe",
        "Rg Adm",
        "Parcours",
        "Groupe",
    ]
    if prev_moy:  # si qq chose dans precedent
        titles += [prev_ue_acro[x][1] for x in ue_prev_codes] + [
            "Moy %s" % sp,
            "Décision %s" % sp,
        ]
    titles += [ue_acro[x][1] for x in ue_codes] + ["Moy %s" % sn]
    if moy_inter:
        titles += ["Moy %s-%s" % (sp, sn)]
    titles += ["Abs", "Abs Injust."]
    if code:
        titles.append("Proposit. %s" % sn)
    if autorisations:
        titles.append("Autorisations")
    #    titles.append('Assidu')
    ws.append_row(ws.make_row(titles, style_boldcenter))
    if prev_moy:
        tit_prev_moy = "Moy " + sp
        col_prev_moy = titles.index(tit_prev_moy)
    tit_moy = "Moy " + sn
    col_moy = titles.index(tit_moy)
    col_abs = titles.index("Abs")

    def fmt(x):
        "reduit les notes a deux chiffres"
        x = scu.fmt_note(x, keep_numeric=False)
        try:
            return float(x)
        except:
            return x

    i = 1  # numero etudiant
    for etudid in etudids:
        cells = []
        etud = nt.identdict[etudid]
        cells.append(ws.make_cell(str(i)))
        if sco_preferences.get_preference("prepa_jury_nip"):
            cells.append(ws.make_cell(etud["code_nip"]))
        if sco_preferences.get_preference("prepa_jury_ine"):
            cells.append(ws.make_cell(["code_ine"]))
        cells += ws.make_row(
            [
                etudid,
                etud["civilite_str"],
                sco_etud.format_nom(etud["nom"]),
                sco_etud.format_prenom(etud["prenom"]),
                etud["date_naissance"],
                etud["bac"],
                etud["specialite"],
                etud["classement"],
                parcours[etudid],
                groupestd[etudid],
            ]
        )
        co = len(cells)
        if prev_moy:
            for ue_acro in ue_prev_codes:
                cells.append(
                    ws.make_cell(
                        fmt(prev_moy_ue.get(ue_acro, {}).get(etudid, "")), style_note
                    )
                )
                co += 1
            cells.append(
                ws.make_cell(fmt(prev_moy.get(etudid, "")), style_bold)
            )  # moy gen prev
            cells.append(
                ws.make_cell(fmt(prev_code.get(etudid, "")), style_moy)
            )  # decision prev
            co += 2

        for ue_acro in ue_codes:
            cells.append(
                ws.make_cell(fmt(moy_ue.get(ue_acro, {}).get(etudid, "")), style_note)
            )
            co += 1
        cells.append(ws.make_cell(fmt(moy.get(etudid, "")), style_note_bold))  # moy gen
        co += 1
        if moy_inter:
            cells.append(ws.make_cell(fmt(moy_inter.get(etudid, "")), style_note))
        cells.append(ws.make_cell(str(nbabs.get(etudid, "")), style_center))
        cells.append(ws.make_cell(str(nbabsjust.get(etudid, "")), style_center))
        if code:
            cells.append(ws.make_cell(code.get(etudid, ""), style_moy))
        cells.append(ws.make_cell(autorisations.get(etudid, ""), style_moy))
        #        l.append(assidu.get(etudid, ''))
        ws.append_row(cells)
        i += 1
    #
    ws.append_blank_row()
    # Explications des codes
    codes = list(sco_codes_parcours.CODES_EXPL.keys())
    codes.sort()
    ws.append_single_cell_row("Explication des codes")
    for code in codes:
        ws.append_row(
            ws.make_row(["", "", "", code, sco_codes_parcours.CODES_EXPL[code]])
        )
    ws.append_row(
        ws.make_row(
            [
                "",
                "",
                "",
                "ADM+",
                "indique que le semestre a déjà servi à en compenser un autre",
            ]
        )
    )
    # UE : Correspondances acronyme et titre complet
    ws.append_blank_row()
    ws.append_single_cell_row("Titre des UE")
    if prev_moy:
        for ue in ntp.get_ues(filter_sport=True):
            ws.append_row(ws.make_row(["", "", "", ue["acronyme"], ue["titre"]]))
    for ue in nt.get_ues(filter_sport=True):
        ws.append_row(ws.make_row(["", "", "", ue["acronyme"], ue["titre"]]))
    #
    ws.append_blank_row()
    ws.append_single_cell_row(
        "Préparé par %s le %s sur %s pour %s"
        % (
            sco_version.SCONAME,
            time.strftime("%d/%m/%Y"),
            request.url_root,
            current_user,
        )
    )
    xls = ws.generate()
    return scu.send_file(
        xls,
        f"PrepaJury{sn}",
        scu.XLSX_SUFFIX,
        mime=scu.XLSX_MIMETYPE,
    )
