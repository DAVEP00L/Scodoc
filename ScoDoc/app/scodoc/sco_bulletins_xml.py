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

"""Génération du bulletin en format XML


Note: la structure de ce XML est issue de (mauvais) choix historiques
et ne peut pas être modifiée car d'autres logiciels l'utilisent (portail publication
bulletins etudiants).

Je recommande d'utiliser la version JSON.
Malheureusement, le code de génération JSON et XML sont séparés, ce qui est absurde et
complique la maintenance (si on ajoute des informations aux bulletins).

"""

# revu en juillet 21 pour utiliser ElementTree au lieu de jaxml

import datetime
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc import sco_abs
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_edit_ue
from app.scodoc import sco_evaluations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_photos
from app.scodoc import sco_preferences
from app.scodoc import sco_etud
from app.scodoc import sco_xml

# -------- Bulletin en XML
# (fonction séparée: n'utilise pas formsemestre_bulletinetud_dict()
#   pour simplifier le code, mais attention a la maintenance !)
#
def make_xml_formsemestre_bulletinetud(
    formsemestre_id,
    etudid,
    doc=None,  # XML document
    force_publishing=False,
    xml_nodate=False,
    xml_with_decisions=False,  # inclue les decisions même si non publiées
    version="long",
) -> str:
    "bulletin au format XML"
    from app.scodoc import sco_bulletins

    log("xml_bulletin( formsemestre_id=%s, etudid=%s )" % (formsemestre_id, etudid))

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if (not sem["bul_hide_xml"]) or force_publishing:
        published = "1"
    else:
        published = "0"
    if xml_nodate:
        docdate = ""
    else:
        docdate = datetime.datetime.now().isoformat()

    el = {
        "etudid": str(etudid),
        "formsemestre_id": str(formsemestre_id),
        "date": docdate,
        "publie": published,
    }
    if sem["etapes"]:
        el["etape_apo"] = str(sem["etapes"][0]) or ""
        n = 2
        for et in sem["etapes"][1:]:
            el["etape_apo" + str(n)] = str(et) or ""
            n += 1

    x = Element("bulletinetud", **el)
    if doc:
        is_appending = True
        doc.append(x)
    else:
        is_appending = False
        doc = x
    # Infos sur l'etudiant
    etudinfo = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    doc.append(
        Element(
            "etudiant",
            etudid=str(etudid),
            code_nip=str(etudinfo["code_nip"]),
            code_ine=str(etudinfo["code_ine"]),
            nom=scu.quote_xml_attr(etudinfo["nom"]),
            prenom=scu.quote_xml_attr(etudinfo["prenom"]),
            civilite=scu.quote_xml_attr(etudinfo["civilite_str"]),
            sexe=scu.quote_xml_attr(etudinfo["civilite_str"]),  # compat
            photo_url=scu.quote_xml_attr(sco_photos.etud_photo_url(etudinfo)),
            email=scu.quote_xml_attr(etudinfo["email"]),
            emailperso=scu.quote_xml_attr(etudinfo["emailperso"]),
        )
    )

    # Disponible pour publication ?
    if not published:
        return doc  # stop !

    # Groupes:
    partitions = sco_groups.get_partitions_list(formsemestre_id, with_default=False)
    partitions_etud_groups = {}  # { partition_id : { etudid : group } }
    for partition in partitions:
        pid = partition["partition_id"]
        partitions_etud_groups[pid] = sco_groups.get_etud_groups_in_partition(pid)

    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > toutes notes
    ues = nt.get_ues()
    modimpls = nt.get_modimpls()
    nbetuds = len(nt.rangs)
    mg = scu.fmt_note(nt.get_etud_moy_gen(etudid))
    if (
        nt.get_moduleimpls_attente()
        or sco_preferences.get_preference("bul_show_rangs", formsemestre_id) == 0
    ):
        # n'affiche pas le rang sur le bulletin s'il y a des
        # notes en attente dans ce semestre
        rang = ""
        rang_gr = {}
        ninscrits_gr = {}
    else:
        rang = str(nt.get_etud_rang(etudid))
        rang_gr, ninscrits_gr, gr_name = sco_bulletins.get_etud_rangs_groups(
            etudid, formsemestre_id, partitions, partitions_etud_groups, nt
        )

    doc.append(
        Element(
            "note",
            value=mg,
            min=scu.fmt_note(nt.moy_min),
            max=scu.fmt_note(nt.moy_max),
            moy=scu.fmt_note(nt.moy_moy),
        )
    )
    doc.append(Element("rang", value=str(rang), ninscrits=str(nbetuds)))

    if rang_gr:
        for partition in partitions:
            doc.append(
                Element(
                    "rang_group",
                    group_type=partition["partition_name"] or "",
                    group_name=gr_name[partition["partition_id"]] or "",
                    value=str(rang_gr[partition["partition_id"]]),
                    ninscrits=str(ninscrits_gr[partition["partition_id"]]),
                )
            )
    doc.append(Element("note_max", value="20"))  # notes toujours sur 20
    doc.append(Element("bonus_sport_culture", value=str(nt.bonus[etudid])))
    # Liste les UE / modules /evals
    for ue in ues:
        ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
        x_ue = Element(
            "ue",
            id=str(ue["ue_id"]),
            numero=scu.quote_xml_attr(ue["numero"]),
            acronyme=scu.quote_xml_attr(ue["acronyme"]),
            titre=scu.quote_xml_attr(ue["titre"]),
            code_apogee=scu.quote_xml_attr(ue["code_apogee"]),
        )
        doc.append(x_ue)
        if ue["type"] != sco_codes_parcours.UE_SPORT:
            v = ue_status["cur_moy_ue"]
        else:
            v = nt.bonus[etudid]
        x_ue.append(
            Element(
                "note",
                value=scu.fmt_note(v),
                min=scu.fmt_note(ue["min"]),
                max=scu.fmt_note(ue["max"]),
            )
        )
        try:
            ects_txt = str(int(ue["ects"]))
        except (ValueError, TypeError):
            ects_txt = ""
        x_ue.append(Element("ects", value=ects_txt))
        x_ue.append(Element("rang", value=str(nt.ue_rangs[ue["ue_id"]][0][etudid])))
        x_ue.append(Element("effectif", value=str(nt.ue_rangs[ue["ue_id"]][1])))
        # Liste les modules de l'UE
        ue_modimpls = [mod for mod in modimpls if mod["module"]["ue_id"] == ue["ue_id"]]
        for modimpl in ue_modimpls:
            mod_moy = scu.fmt_note(
                nt.get_etud_mod_moy(modimpl["moduleimpl_id"], etudid)
            )
            if mod_moy == "NI":  # ne mentionne pas les modules ou n'est pas inscrit
                continue
            mod = modimpl["module"]
            # if mod['ects'] is None:
            #    ects = ''
            # else:
            #    ects = str(mod['ects'])
            x_mod = Element(
                "module",
                id=str(modimpl["moduleimpl_id"]),
                code=str(mod["code"]),
                coefficient=str(mod["coefficient"]),
                numero=str(mod["numero"]),
                titre=scu.quote_xml_attr(mod["titre"]),
                abbrev=scu.quote_xml_attr(mod["abbrev"]),
                code_apogee=scu.quote_xml_attr(mod["code_apogee"])
                # ects=ects ects des modules maintenant inutilisés
            )
            x_ue.append(x_mod)
            modstat = nt.get_mod_stats(modimpl["moduleimpl_id"])
            x_mod.append(
                Element(
                    "note",
                    value=mod_moy,
                    min=scu.fmt_note(modstat["min"]),
                    max=scu.fmt_note(modstat["max"]),
                    moy=scu.fmt_note(modstat["moy"]),
                )
            )
            if sco_preferences.get_preference("bul_show_mod_rangs", formsemestre_id):
                x_mod.append(
                    Element(
                        "rang",
                        value=str(nt.mod_rangs[modimpl["moduleimpl_id"]][0][etudid]),
                    )
                )
                x_mod.append(
                    Element(
                        "effectif", value=str(nt.mod_rangs[modimpl["moduleimpl_id"]][1])
                    )
                )
            # --- notes de chaque eval:
            evals = nt.get_evals_in_mod(modimpl["moduleimpl_id"])
            if version != "short":
                for e in evals:
                    if e["visibulletin"] or version == "long":
                        x_eval = Element(
                            "evaluation",
                            jour=ndb.DateDMYtoISO(e["jour"], null_is_empty=True),
                            heure_debut=ndb.TimetoISO8601(
                                e["heure_debut"], null_is_empty=True
                            ),
                            heure_fin=ndb.TimetoISO8601(
                                e["heure_fin"], null_is_empty=True
                            ),
                            coefficient=str(e["coefficient"]),
                            evaluation_type=str(e["evaluation_type"]),
                            description=scu.quote_xml_attr(e["description"]),
                            # notes envoyées sur 20, ceci juste pour garder trace:
                            note_max_origin=str(e["note_max"]),
                        )
                        x_mod.append(x_eval)
                        val = e["notes"].get(etudid, {"value": "NP"})[
                            "value"
                        ]  # NA si etud demissionnaire
                        val = scu.fmt_note(val, note_max=e["note_max"])
                        x_eval.append(Element("note", value=val))
                # Evaluations incomplètes ou futures:
                complete_eval_ids = set([e["evaluation_id"] for e in evals])
                if sco_preferences.get_preference(
                    "bul_show_all_evals", formsemestre_id
                ):
                    all_evals = sco_evaluations.do_evaluation_list(
                        args={"moduleimpl_id": modimpl["moduleimpl_id"]}
                    )
                    all_evals.reverse()  # plus ancienne d'abord
                    for e in all_evals:
                        if e["evaluation_id"] not in complete_eval_ids:
                            x_eval = Element(
                                "evaluation",
                                jour=ndb.DateDMYtoISO(e["jour"], null_is_empty=True),
                                heure_debut=ndb.TimetoISO8601(
                                    e["heure_debut"], null_is_empty=True
                                ),
                                heure_fin=ndb.TimetoISO8601(
                                    e["heure_fin"], null_is_empty=True
                                ),
                                coefficient=str(e["coefficient"]),
                                description=scu.quote_xml_attr(e["description"]),
                                incomplete="1",
                                # notes envoyées sur 20, ceci juste pour garder trace:
                                note_max_origin=str(e["note_max"] or ""),
                            )
                            x_mod.append(x_eval)
        # UE capitalisee (listee seulement si meilleure que l'UE courante)
        if ue_status["is_capitalized"]:
            try:
                ects_txt = str(int(ue_status["ue"].get("ects", "")))
            except (ValueError, TypeError):
                ects_txt = ""
            x_ue = Element(
                "ue_capitalisee",
                id=str(ue["ue_id"]),
                numero=scu.quote_xml_attr(ue["numero"]),
                acronyme=scu.quote_xml_attr(ue["acronyme"]),
                titre=scu.quote_xml_attr(ue["titre"]),
            )
            doc.append(x_ue)
            x_ue.append(Element("note", value=scu.fmt_note(ue_status["moy"])))
            x_ue.append(Element("ects", value=ects_txt))
            x_ue.append(
                Element("coefficient_ue", value=scu.fmt_note(ue_status["coef_ue"]))
            )
            x_ue.append(
                Element(
                    "date_capitalisation",
                    value=ndb.DateDMYtoISO(ue_status["event_date"]),
                )
            )

    # --- Absences
    if sco_preferences.get_preference("bul_show_abs", formsemestre_id):
        nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
        doc.append(Element("absences", nbabs=str(nbabs), nbabsjust=str(nbabsjust)))
    # --- Decision Jury
    if (
        sco_preferences.get_preference("bul_show_decision", formsemestre_id)
        or xml_with_decisions
    ):
        infos, dpv = sco_bulletins.etud_descr_situation_semestre(
            etudid,
            formsemestre_id,
            format="xml",
            show_uevalid=sco_preferences.get_preference(
                "bul_show_uevalid", formsemestre_id
            ),
        )
        x_situation = Element("situation")
        x_situation.text = scu.quote_xml_attr(infos["situation"])
        doc.append(x_situation)
        if dpv:
            decision = dpv["decisions"][0]
            etat = decision["etat"]
            if decision["decision_sem"]:
                code = decision["decision_sem"]["code"] or ""
            else:
                code = ""
            if (
                decision["decision_sem"]
                and "compense_formsemestre_id" in decision["decision_sem"]
            ):
                doc.append(
                    Element(
                        "decision",
                        code=code,
                        etat=str(etat),
                        compense_formsemestre_id=str(
                            decision["decision_sem"]["compense_formsemestre_id"] or ""
                        ),
                    )
                )
            else:
                doc.append(Element("decision", code=code, etat=str(etat)))

            if decision[
                "decisions_ue"
            ]:  # and sco_preferences.get_preference( 'bul_show_uevalid', formsemestre_id): always publish (car utile pour export Apogee)
                for ue_id in decision["decisions_ue"].keys():
                    ue = sco_edit_ue.ue_list({"ue_id": ue_id})[0]
                    doc.append(
                        Element(
                            "decision_ue",
                            ue_id=str(ue["ue_id"]),
                            numero=scu.quote_xml_attr(ue["numero"]),
                            acronyme=scu.quote_xml_attr(ue["acronyme"]),
                            titre=scu.quote_xml_attr(ue["titre"]),
                            code=decision["decisions_ue"][ue_id]["code"],
                        )
                    )

            for aut in decision["autorisations"]:
                doc.append(
                    Element(
                        "autorisation_inscription", semestre_id=str(aut["semestre_id"])
                    )
                )
        else:
            doc.append(Element("decision", code="", etat="DEM"))
    # --- Appreciations
    cnx = ndb.GetDBConnexion()
    apprecs = sco_etud.appreciations_list(
        cnx, args={"etudid": etudid, "formsemestre_id": formsemestre_id}
    )
    for appr in apprecs:
        x_appr = Element(
            "appreciation",
            date=ndb.DateDMYtoISO(appr["date"]),
        )
        x_appr.text = scu.quote_xml_attr(appr["comment"])
        doc.append(x_appr)

    if is_appending:
        return None
    else:
        return sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING)
