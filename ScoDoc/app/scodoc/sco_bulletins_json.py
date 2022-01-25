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

"""Génération du bulletin en format JSON (beta, non completement testé)

"""
import datetime
import json

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc import sco_abs
from app.scodoc import sco_cache
from app.scodoc import sco_edit_ue
from app.scodoc import sco_evaluations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_photos
from app.scodoc import sco_preferences
from app.scodoc import sco_etud

# -------- Bulletin en JSON


def make_json_formsemestre_bulletinetud(
    formsemestre_id: int,
    etudid: int,
    xml_with_decisions=False,
    version="long",
    force_publishing=False,  # force publication meme si semestre non publie sur "portail"
) -> str:
    """Renvoie bulletin en chaine JSON"""

    d = formsemestre_bulletinetud_published_dict(
        formsemestre_id,
        etudid,
        force_publishing=force_publishing,
        xml_with_decisions=xml_with_decisions,
        version=version,
    )

    return json.dumps(d, cls=scu.ScoDocJSONEncoder)


# (fonction séparée: n'utilise pas formsemestre_bulletinetud_dict()
#   pour simplifier le code, mais attention a la maintenance !)
#
def formsemestre_bulletinetud_published_dict(
    formsemestre_id,
    etudid,
    force_publishing=False,
    xml_nodate=False,
    xml_with_decisions=False,  # inclue les decisions même si non publiées
    version="long",
):
    """Dictionnaire representant les informations _publiees_ du bulletin de notes
    Utilisé pour JSON, devrait l'être aussi pour XML. (todo)
    """
    from app.scodoc import sco_bulletins

    d = {}

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if (not sem["bul_hide_xml"]) or force_publishing:
        published = 1
    else:
        published = 0
    if xml_nodate:
        docdate = ""
    else:
        docdate = datetime.datetime.now().isoformat()

    el = {
        "etudid": etudid,
        "formsemestre_id": formsemestre_id,
        "date": docdate,
        "publie": published,
        "etapes": sem["etapes"],
    }
    # backward compat:
    if sem["etapes"]:
        el["etape_apo"] = sem["etapes"][0] or ""
        n = 2
        for et in sem["etapes"][1:]:
            el["etape_apo" + str(n)] = et or ""
            n += 1
    d.update(**el)

    # Infos sur l'etudiant
    etudinfo = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]

    d["etudiant"] = dict(
        etudid=etudid,
        code_nip=etudinfo["code_nip"],
        code_ine=etudinfo["code_ine"],
        nom=scu.quote_xml_attr(etudinfo["nom"]),
        prenom=scu.quote_xml_attr(etudinfo["prenom"]),
        civilite=scu.quote_xml_attr(etudinfo["civilite_str"]),
        photo_url=scu.quote_xml_attr(sco_photos.etud_photo_url(etudinfo, fast=True)),
        email=scu.quote_xml_attr(etudinfo["email"]),
        emailperso=scu.quote_xml_attr(etudinfo["emailperso"]),
    )
    d["etudiant"]["sexe"] = d["etudiant"]["civilite"]  # backward compat for our clients
    # Disponible pour publication ?
    if not published:
        return d  # stop !

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

    d["note"] = dict(
        value=mg,
        min=scu.fmt_note(nt.moy_min),
        max=scu.fmt_note(nt.moy_max),
        moy=scu.fmt_note(nt.moy_moy),
    )
    d["rang"] = dict(value=rang, ninscrits=nbetuds)
    d["rang_group"] = []
    if rang_gr:
        for partition in partitions:
            d["rang_group"].append(
                dict(
                    group_type=partition["partition_name"],
                    group_name=gr_name[partition["partition_id"]],
                    value=rang_gr[partition["partition_id"]],
                    ninscrits=ninscrits_gr[partition["partition_id"]],
                )
            )

    d["note_max"] = dict(value=20)  # notes toujours sur 20
    d["bonus_sport_culture"] = dict(value=nt.bonus[etudid])

    # Liste les UE / modules /evals
    d["ue"] = []
    d["ue_capitalisee"] = []
    for ue in ues:
        ue_status = nt.get_etud_ue_status(etudid, ue["ue_id"])
        if ue["ects"] is None:
            ects_txt = ""
        else:
            ects_txt = f"{ue['ects']:2.3g}"
        u = dict(
            id=ue["ue_id"],
            numero=scu.quote_xml_attr(ue["numero"]),
            acronyme=scu.quote_xml_attr(ue["acronyme"]),
            titre=scu.quote_xml_attr(ue["titre"]),
            note=dict(
                value=scu.fmt_note(ue_status["cur_moy_ue"]),
                min=scu.fmt_note(ue["min"]),
                max=scu.fmt_note(ue["max"]),
                moy=scu.fmt_note(
                    ue["moy"]
                ),  # CM : ajout pour faire apparaitre la moyenne des UE
            ),
            rang=str(nt.ue_rangs[ue["ue_id"]][0][etudid]),
            effectif=str(nt.ue_rangs[ue["ue_id"]][1]),
            ects=ects_txt,
            code_apogee=scu.quote_xml_attr(ue["code_apogee"]),
        )
        d["ue"].append(u)
        u["module"] = []
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
            modstat = nt.get_mod_stats(modimpl["moduleimpl_id"])

            m = dict(
                id=modimpl["moduleimpl_id"],
                code=mod["code"],
                coefficient=mod["coefficient"],
                numero=mod["numero"],
                titre=scu.quote_xml_attr(mod["titre"]),
                abbrev=scu.quote_xml_attr(mod["abbrev"]),
                # ects=ects, ects des modules maintenant inutilisés
                note=dict(value=mod_moy),
                code_apogee=scu.quote_xml_attr(mod["code_apogee"]),
            )
            m["note"].update(modstat)
            for k in ("min", "max", "moy"):  # formatte toutes les notes
                m["note"][k] = scu.fmt_note(m["note"][k])

            u["module"].append(m)
            if sco_preferences.get_preference("bul_show_mod_rangs", formsemestre_id):
                m["rang"] = dict(
                    value=nt.mod_rangs[modimpl["moduleimpl_id"]][0][etudid]
                )
                m["effectif"] = dict(value=nt.mod_rangs[modimpl["moduleimpl_id"]][1])

            # --- notes de chaque eval:
            evals = nt.get_evals_in_mod(modimpl["moduleimpl_id"])
            m["evaluation"] = []
            if version != "short":
                for e in evals:
                    if e["visibulletin"] or version == "long":
                        val = e["notes"].get(etudid, {"value": "NP"})[
                            "value"
                        ]  # NA si etud demissionnaire
                        val = scu.fmt_note(val, note_max=e["note_max"])
                        m["evaluation"].append(
                            dict(
                                jour=ndb.DateDMYtoISO(e["jour"], null_is_empty=True),
                                heure_debut=ndb.TimetoISO8601(
                                    e["heure_debut"], null_is_empty=True
                                ),
                                heure_fin=ndb.TimetoISO8601(
                                    e["heure_fin"], null_is_empty=True
                                ),
                                coefficient=e["coefficient"],
                                evaluation_type=e["evaluation_type"],
                                evaluation_id=e[
                                    "evaluation_id"
                                ],  # CM : ajout pour permettre de faire le lien sur les bulletins en ligne avec l'évaluation
                                description=scu.quote_xml_attr(e["description"]),
                                note=val,
                            )
                        )
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
                            m["evaluation"].append(
                                dict(
                                    jour=ndb.DateDMYtoISO(
                                        e["jour"], null_is_empty=True
                                    ),
                                    heure_debut=ndb.TimetoISO8601(
                                        e["heure_debut"], null_is_empty=True
                                    ),
                                    heure_fin=ndb.TimetoISO8601(
                                        e["heure_fin"], null_is_empty=True
                                    ),
                                    coefficient=e["coefficient"],
                                    description=scu.quote_xml_attr(e["description"]),
                                    incomplete="1",
                                )
                            )

        # UE capitalisee (listee seulement si meilleure que l'UE courante)
        if ue_status["is_capitalized"]:
            try:
                ects_txt = str(int(ue_status["ue"].get("ects", "")))
            except:
                ects_txt = ""
            d["ue_capitalisee"].append(
                dict(
                    id=ue["ue_id"],
                    numero=scu.quote_xml_attr(ue["numero"]),
                    acronyme=scu.quote_xml_attr(ue["acronyme"]),
                    titre=scu.quote_xml_attr(ue["titre"]),
                    note=scu.fmt_note(ue_status["moy"]),
                    coefficient_ue=scu.fmt_note(ue_status["coef_ue"]),
                    date_capitalisation=ndb.DateDMYtoISO(ue_status["event_date"]),
                    ects=ects_txt,
                )
            )

    # --- Absences
    if sco_preferences.get_preference("bul_show_abs", formsemestre_id):
        nbabs, nbabsjust = sco_abs.get_abs_count(etudid, sem)
        d["absences"] = dict(nbabs=nbabs, nbabsjust=nbabsjust)

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
        d["situation"] = scu.quote_xml_attr(infos["situation"])
        if dpv:
            decision = dpv["decisions"][0]
            etat = decision["etat"]
            if decision["decision_sem"]:
                code = decision["decision_sem"]["code"]
            else:
                code = ""

            d["decision"] = dict(code=code, etat=etat)
            if (
                decision["decision_sem"]
                and "compense_formsemestre_id" in decision["decision_sem"]
            ):
                d["decision"]["compense_formsemestre_id"] = decision["decision_sem"][
                    "compense_formsemestre_id"
                ]

            d["decision_ue"] = []
            if decision[
                "decisions_ue"
            ]:  # and sco_preferences.get_preference( 'bul_show_uevalid', formsemestre_id): always publish (car utile pour export Apogee)
                for ue_id in decision["decisions_ue"].keys():
                    ue = sco_edit_ue.ue_list({"ue_id": ue_id})[0]
                    d["decision_ue"].append(
                        dict(
                            ue_id=ue["ue_id"],
                            numero=scu.quote_xml_attr(ue["numero"]),
                            acronyme=scu.quote_xml_attr(ue["acronyme"]),
                            titre=scu.quote_xml_attr(ue["titre"]),
                            code=decision["decisions_ue"][ue_id]["code"],
                            ects=scu.quote_xml_attr(ue["ects"] or ""),
                        )
                    )
            d["autorisation_inscription"] = []
            for aut in decision["autorisations"]:
                d["autorisation_inscription"].append(
                    dict(semestre_id=aut["semestre_id"])
                )
        else:
            d["decision"] = dict(code="", etat="DEM")

    # --- Appreciations
    cnx = ndb.GetDBConnexion()
    apprecs = sco_etud.appreciations_list(
        cnx, args={"etudid": etudid, "formsemestre_id": formsemestre_id}
    )
    d["appreciation"] = []
    for app in apprecs:
        d["appreciation"].append(
            dict(
                comment=scu.quote_xml_attr(app["comment"]),
                date=ndb.DateDMYtoISO(app["date"]),
            )
        )

    #
    return d
