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
#   Emmanuel Viennet      emmanuel.viennet@gmail.com
#
##############################################################################

"""Extraction de données pour poursuites d'études

Recapitule tous les semestres validés dans une feuille excel.
"""
import collections

from flask import url_for, g, request

import app.scodoc.sco_utils as scu
from app.scodoc import sco_abs
from app.scodoc import sco_cache
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_preferences
from app.scodoc import sco_etud
import sco_version
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_codes_parcours import code_semestre_validant, code_semestre_attente


def etud_get_poursuite_info(sem, etud):
    """{ 'nom' : ..., 'semlist' : [ { 'semestre_id': , 'moy' : ... }, {}, ...] }"""
    I = {}
    I.update(etud)  # copie nom, prenom, civilite, ...

    # Now add each semester, starting from the first one
    semlist = []
    current_id = sem["semestre_id"]
    for sem_id in range(1, current_id + 1):
        sem_descr = None
        for s in etud["sems"]:
            if s["semestre_id"] == sem_id:
                etudid = etud["etudid"]
                nt = sco_cache.NotesTableCache.get(s["formsemestre_id"])
                dec = nt.get_etud_decision_sem(etudid)
                # Moyennes et rangs des UE
                ues = nt.get_ues(filter_sport=True)
                moy_ues = [
                    (
                        ue["acronyme"],
                        scu.fmt_note(nt.get_etud_ue_status(etudid, ue["ue_id"])["moy"]),
                    )
                    for ue in ues
                ]
                rg_ues = [
                    ("rang_" + ue["acronyme"], nt.ue_rangs[ue["ue_id"]][0][etudid])
                    for ue in ues
                ]

                # Moyennes et rang des modules
                modimpls = nt.get_modimpls()  # recupération des modules
                modules = []
                rangs = []
                for ue in ues:  # on parcourt chaque UE
                    for modimpl in modimpls:  # dans chaque UE les modules
                        if modimpl["module"]["ue_id"] == ue["ue_id"]:
                            codeModule = modimpl["module"]["code"]
                            noteModule = scu.fmt_note(
                                nt.get_etud_mod_moy(modimpl["moduleimpl_id"], etudid)
                            )
                            if noteModule != "NI":  # si étudiant inscrit au module
                                rangModule = nt.mod_rangs[modimpl["moduleimpl_id"]][0][
                                    etudid
                                ]
                                modules.append([codeModule, noteModule])
                                rangs.append(["rang_" + codeModule, rangModule])

                # Absences
                nbabs, nbabsjust = sco_abs.get_abs_count(etudid, nt.sem)
                if (
                    dec
                    and not sem_descr  # not sem_descr pour ne prendre que le semestre validé le plus récent
                    and (
                        code_semestre_validant(dec["code"])
                        or code_semestre_attente(dec["code"])
                    )
                    and nt.get_etud_etat(etudid) == "I"
                ):
                    d = [
                        ("moy", scu.fmt_note(nt.get_etud_moy_gen(etudid))),
                        ("moy_promo", scu.fmt_note(nt.moy_moy)),
                        ("rang", nt.get_etud_rang(etudid)),
                        ("effectif", len(nt.T)),
                        ("date_debut", s["date_debut"]),
                        ("date_fin", s["date_fin"]),
                        ("periode", "%s - %s" % (s["mois_debut"], s["mois_fin"])),
                        ("AbsNonJust", nbabs - nbabsjust),
                        ("AbsJust", nbabsjust),
                    ]
                    d += (
                        moy_ues + rg_ues + modules + rangs
                    )  # ajout des 2 champs notes des modules et classement dans chaque module
                    sem_descr = collections.OrderedDict(d)
        if not sem_descr:
            sem_descr = collections.OrderedDict(
                [
                    ("moy", ""),
                    ("moy_promo", ""),
                    ("rang", ""),
                    ("effectif", ""),
                    ("date_debut", ""),
                    ("date_fin", ""),
                    ("periode", ""),
                ]
            )
        sem_descr["semestre_id"] = sem_id
        semlist.append(sem_descr)

    I["semlist"] = semlist
    return I


def _flatten_info(info):
    # met la liste des infos semestres "a plat"
    # S1_moy, S1_rang, ..., S2_moy, ...
    ids = []
    for s in info["semlist"]:
        for k, v in s.items():
            if k != "semestre_id":
                label = "S%s_%s" % (s["semestre_id"], k)
                info[label] = v
                ids.append(label)
    return ids


def _getEtudInfoGroupes(group_ids, etat=None):
    """liste triée d'infos (dict) sur les etudiants du groupe indiqué.
    Attention: lent, car plusieurs requetes SQL par etudiant !
    """
    etuds = []
    for group_id in group_ids:
        members = sco_groups.get_group_members(group_id, etat=etat)
        for m in members:
            etud = sco_etud.get_etud_info(etudid=m["etudid"], filled=True)[0]
            etuds.append(etud)

    return etuds


def formsemestre_poursuite_report(formsemestre_id, format="html"):
    """Table avec informations "poursuite" """
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    etuds = _getEtudInfoGroupes([sco_groups.get_default_group(formsemestre_id)])

    infos = []
    ids = []
    for etud in etuds:
        fiche_url = url_for(
            "scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]
        )
        etud["_nom_target"] = fiche_url
        etud["_prenom_target"] = fiche_url
        etud["_nom_td_attrs"] = 'id="%s" class="etudinfo"' % (etud["etudid"])
        info = etud_get_poursuite_info(sem, etud)
        idd = _flatten_info(info)
        # On recupere la totalite des UEs dans ids
        for id in idd:
            if id not in ids:
                ids += [id]
        infos.append(info)
    #
    column_ids = (
        ("civilite_str", "nom", "prenom", "annee", "date_naissance")
        + tuple(ids)
        + ("debouche",)
    )
    titles = {}
    for c in column_ids:
        titles[c] = c
    tab = GenTable(
        titles=titles,
        columns_ids=column_ids,
        rows=infos,
        # html_col_width='4em',
        html_sortable=True,
        html_class="table_leftalign table_listegroupe",
        pdf_link=False,  # pas d'export pdf
        preferences=sco_preferences.SemPreferences(formsemestre_id),
    )
    tab.filename = scu.make_filename("poursuite " + sem["titreannee"])

    tab.origin = (
        "Généré par %s le " % sco_version.SCONAME + scu.timedate_human_repr() + ""
    )
    tab.caption = "Récapitulatif %s." % sem["titreannee"]
    tab.html_caption = "Récapitulatif %s." % sem["titreannee"]
    tab.base_url = "%s?formsemestre_id=%s" % (request.base_url, formsemestre_id)
    return tab.make_page(
        title="""<h2 class="formsemestre">Poursuite d'études</h2>""",
        init_qtip=True,
        javascripts=["js/etud_info.js"],
        format=format,
        with_html_headers=True,
    )
