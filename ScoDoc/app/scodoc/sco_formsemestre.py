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

"""Operations de base sur les formsemestres
"""
from app.scodoc.sco_exceptions import ScoValueError
import time
from operator import itemgetter

from flask import g, request

import app
from app.models import Departement
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_formations
from app.scodoc import sco_preferences
from app.scodoc import sco_users
from app.scodoc.gen_tables import GenTable
from app import log
from app.scodoc.sco_codes_parcours import NO_SEMESTRE_ID
from app.scodoc.sco_vdi import ApoEtapeVDI
import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu

_formsemestreEditor = ndb.EditableTable(
    "notes_formsemestre",
    "formsemestre_id",
    (
        "formsemestre_id",
        "semestre_id",
        "formation_id",
        "titre",
        "date_debut",
        "date_fin",
        "gestion_compensation",
        "gestion_semestrielle",
        "etat",
        "bul_hide_xml",
        "block_moyennes",
        "bul_bgcolor",
        "modalite",
        "resp_can_edit",
        "resp_can_change_ens",
        "ens_can_edit_eval",
        "elt_sem_apo",
        "elt_annee_apo",
    ),
    filter_dept=True,
    sortkey="date_debut",
    output_formators={
        "date_debut": ndb.DateISOtoDMY,
        "date_fin": ndb.DateISOtoDMY,
    },
    input_formators={
        "date_debut": ndb.DateDMYtoISO,
        "date_fin": ndb.DateDMYtoISO,
        "etat": bool,
        "gestion_compensation": bool,
        "bul_hide_xml": bool,
        "block_moyennes": bool,
        "gestion_semestrielle": bool,
        "gestion_compensation": bool,
        "gestion_semestrielle": bool,
        "resp_can_edit": bool,
        "resp_can_change_ens": bool,
        "ens_can_edit_eval": bool,
    },
)


def get_formsemestre(formsemestre_id, raise_soft_exc=False):
    "list ONE formsemestre"
    if formsemestre_id in g.stored_get_formsemestre:
        return g.stored_get_formsemestre[formsemestre_id]
    if not isinstance(formsemestre_id, int):
        raise ValueError("formsemestre_id must be an integer !")
    sems = do_formsemestre_list(args={"formsemestre_id": formsemestre_id})
    if not sems:
        log("get_formsemestre: invalid formsemestre_id (%s)" % formsemestre_id)
        if raise_soft_exc:
            raise ScoValueError(f"semestre {formsemestre_id} inconnu !")
        else:
            raise ValueError(f"semestre {formsemestre_id} inconnu !")
    g.stored_get_formsemestre[formsemestre_id] = sems[0]
    return sems[0]


def do_formsemestre_list(*a, **kw):
    "list formsemestres"
    # log('do_formsemestre_list: a=%s kw=%s' % (str(a),str(kw)))
    cnx = ndb.GetDBConnexion()

    sems = _formsemestreEditor.list(cnx, *a, **kw)

    # Ajoute les étapes Apogee et les responsables:
    for sem in sems:
        sem["etapes"] = read_formsemestre_etapes(sem["formsemestre_id"])
        sem["responsables"] = read_formsemestre_responsables(sem["formsemestre_id"])

    # Filtre sur code etape si indiqué:
    if "args" in kw:
        etape = kw["args"].get("etape_apo", None)
        if etape:
            sems = [sem for sem in sems if etape in sem["etapes"]]

    for sem in sems:
        _formsemestre_enrich(sem)

    # tri par date, le plus récent d'abord
    sems.sort(key=itemgetter("dateord", "semestre_id"), reverse=True)

    return sems


def _formsemestre_enrich(sem):
    """Ajoute champs souvent utiles: titre + annee et dateord (pour tris)"""
    # imports ici pour eviter refs circulaires
    from app.scodoc import sco_formsemestre_edit
    from app.scodoc import sco_etud

    F = sco_formations.formation_list(args={"formation_id": sem["formation_id"]})[0]
    parcours = sco_codes_parcours.get_parcours_from_code(F["type_parcours"])
    # 'S1', 'S2', ... ou '' pour les monosemestres
    if sem["semestre_id"] != NO_SEMESTRE_ID:
        sem["sem_id_txt"] = "S%s" % sem["semestre_id"]
    else:
        sem["sem_id_txt"] = ""
    # Nom avec numero semestre:
    sem["titre_num"] = sem["titre"]  # eg "DUT Informatique"
    if sem["semestre_id"] != NO_SEMESTRE_ID:
        sem["titre_num"] += " %s %s" % (
            parcours.SESSION_NAME,
            sem["semestre_id"],
        )  # eg "DUT Informatique semestre 2"

    sem["dateord"] = ndb.DateDMYtoISO(sem["date_debut"])
    sem["date_debut_iso"] = ndb.DateDMYtoISO(sem["date_debut"])
    sem["date_fin_iso"] = ndb.DateDMYtoISO(sem["date_fin"])
    try:
        mois_debut, annee_debut = sem["date_debut"].split("/")[1:]
    except:
        mois_debut, annee_debut = "", ""
    try:
        mois_fin, annee_fin = sem["date_fin"].split("/")[1:]
    except:
        mois_fin, annee_fin = "", ""
    sem["annee_debut"] = annee_debut
    sem["annee_fin"] = annee_fin
    sem["mois_debut_ord"] = int(mois_debut)
    sem["mois_fin_ord"] = int(mois_fin)

    sem["annee"] = annee_debut
    # 2007 ou 2007-2008:
    sem["anneescolaire"] = scu.annee_scolaire_repr(
        int(annee_debut), sem["mois_debut_ord"]
    )
    # La période: considère comme "S1" (ou S3) les débuts en aout-sept-octobre
    # devrait sans doute pouvoir etre changé...
    if sem["mois_debut_ord"] >= 8 and sem["mois_debut_ord"] <= 10:
        sem["periode"] = 1  # typiquement, début en septembre: S1, S3...
    else:
        sem["periode"] = 2  # typiquement, début en février: S2, S4...

    sem["titreannee"] = "%s %s  %s" % (
        sem["titre_num"],
        sem.get("modalite", ""),
        annee_debut,
    )
    if annee_fin != annee_debut:
        sem["titreannee"] += "-" + annee_fin
        sem["annee"] += "-" + annee_fin
    # et les dates sous la forme "oct 2007 - fev 2008"
    months = sco_etud.MONTH_NAMES_ABBREV
    if mois_debut:
        mois_debut = months[int(mois_debut) - 1]
    if mois_fin:
        mois_fin = months[int(mois_fin) - 1]
    sem["mois_debut"] = mois_debut + " " + annee_debut
    sem["mois_fin"] = mois_fin + " " + annee_fin
    sem["titremois"] = "%s %s  (%s - %s)" % (
        sem["titre_num"],
        sem.get("modalite", ""),
        sem["mois_debut"],
        sem["mois_fin"],
    )
    sem["session_id"] = sco_formsemestre_edit.get_formsemestre_session_id(
        sem, F, parcours
    )
    sem["etapes"] = read_formsemestre_etapes(sem["formsemestre_id"])
    sem["etapes_apo_str"] = formsemestre_etape_apo_str(sem)
    sem["responsables"] = read_formsemestre_responsables(sem["formsemestre_id"])


def formsemestre_etape_apo_str(sem):
    "chaine décrivant le(s) codes étapes Apogée"
    return etapes_apo_str(sem["etapes"])


def etapes_apo_str(etapes):
    "Chaine decrivant une liste d'instance de ApoEtapeVDI"
    return ", ".join([str(x) for x in etapes])


def do_formsemestre_create(args, silent=False):
    "create a formsemestre"
    from app.scodoc import sco_groups
    from app.scodoc import sco_news

    cnx = ndb.GetDBConnexion()
    formsemestre_id = _formsemestreEditor.create(cnx, args)
    if args["etapes"]:
        args["formsemestre_id"] = formsemestre_id
        write_formsemestre_etapes(args)
    if args["responsables"]:
        args["formsemestre_id"] = formsemestre_id
        write_formsemestre_responsables(args)

    # create default partition
    partition_id = sco_groups.partition_create(
        formsemestre_id,
        default=True,
        redirect=0,
    )
    _group_id = sco_groups.create_group(partition_id, default=True)

    # news
    if "titre" not in args:
        args["titre"] = "sans titre"
    args["formsemestre_id"] = formsemestre_id
    args["url"] = "Notes/formsemestre_status?formsemestre_id=%(formsemestre_id)s" % args
    if not silent:
        sco_news.add(
            typ=sco_news.NEWS_SEM,
            text='Création du semestre <a href="%(url)s">%(titre)s</a>' % args,
            url=args["url"],
        )
    return formsemestre_id


def do_formsemestre_edit(sem, cnx=None, **kw):
    """Apply modifications to formsemestre.
    Update etapes and resps. Invalidate cache."""
    if not cnx:
        cnx = ndb.GetDBConnexion()

    _formsemestreEditor.edit(cnx, sem, **kw)
    write_formsemestre_etapes(sem)
    write_formsemestre_responsables(sem)

    sco_cache.invalidate_formsemestre(
        formsemestre_id=sem["formsemestre_id"]
    )  # > modif formsemestre


def read_formsemestre_responsables(formsemestre_id: int) -> list[int]:  # py3.9+ syntax
    """recupere liste des responsables de ce semestre
    :returns: liste d'id
    """
    r = ndb.SimpleDictFetch(
        """SELECT responsable_id
        FROM notes_formsemestre_responsables
        WHERE formsemestre_id = %(formsemestre_id)s
        """,
        {"formsemestre_id": formsemestre_id},
    )
    return [x["responsable_id"] for x in r]


def write_formsemestre_responsables(sem):
    return _write_formsemestre_aux(sem, "responsables", "responsable_id")


# ----------------------  Coefs des UE

_formsemestre_uecoef_editor = ndb.EditableTable(
    "notes_formsemestre_uecoef",
    "formsemestre_uecoef_id",
    ("formsemestre_uecoef_id", "formsemestre_id", "ue_id", "coefficient"),
)

formsemestre_uecoef_create = _formsemestre_uecoef_editor.create
formsemestre_uecoef_edit = _formsemestre_uecoef_editor.edit
formsemestre_uecoef_list = _formsemestre_uecoef_editor.list
formsemestre_uecoef_delete = _formsemestre_uecoef_editor.delete


def do_formsemestre_uecoef_edit_or_create(cnx, formsemestre_id, ue_id, coef):
    "modify or create the coef"
    coefs = formsemestre_uecoef_list(
        cnx, args={"formsemestre_id": formsemestre_id, "ue_id": ue_id}
    )
    if coefs:
        formsemestre_uecoef_edit(
            cnx,
            args={
                "formsemestre_uecoef_id": coefs[0]["formsemestre_uecoef_id"],
                "coefficient": coef,
            },
        )
    else:
        formsemestre_uecoef_create(
            cnx,
            args={
                "formsemestre_id": formsemestre_id,
                "ue_id": ue_id,
                "coefficient": coef,
            },
        )


def do_formsemestre_uecoef_delete(cnx, formsemestre_id, ue_id):
    "delete coef for this (ue,sem)"
    coefs = formsemestre_uecoef_list(
        cnx, args={"formsemestre_id": formsemestre_id, "ue_id": ue_id}
    )
    if coefs:
        formsemestre_uecoef_delete(cnx, coefs[0]["formsemestre_uecoef_id"])


def read_formsemestre_etapes(formsemestre_id):
    """recupere liste des codes etapes associés à ce semestre
    :returns: liste d'instance de ApoEtapeVDI
    """
    r = ndb.SimpleDictFetch(
        """SELECT etape_apo
        FROM notes_formsemestre_etapes
        WHERE formsemestre_id = %(formsemestre_id)s
        """,
        {"formsemestre_id": formsemestre_id},
    )
    return [ApoEtapeVDI(x["etape_apo"]) for x in r if x["etape_apo"]]


def write_formsemestre_etapes(sem):
    return _write_formsemestre_aux(sem, "etapes", "etape_apo")


def _write_formsemestre_aux(sem, fieldname, valuename):
    """fieldname: 'etapes' ou 'responsables'
    valuename: 'etape_apo' ou 'responsable_id'
    """
    if not fieldname in sem:
        return
    # uniquify
    values = set([str(x) for x in sem[fieldname]])

    cnx = ndb.GetDBConnexion(autocommit=False)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    tablename = "notes_formsemestre_" + fieldname
    try:
        cursor.execute(
            "DELETE from " + tablename + " where formsemestre_id = %(formsemestre_id)s",
            {"formsemestre_id": sem["formsemestre_id"]},
        )
        for item in values:
            if item:
                cursor.execute(
                    "INSERT INTO "
                    + tablename
                    + " (formsemestre_id, "
                    + valuename
                    + ") VALUES (%(formsemestre_id)s, %("
                    + valuename
                    + ")s)",
                    {"formsemestre_id": sem["formsemestre_id"], valuename: item},
                )
    except:
        log("Warning: exception in write_formsemestre_aux !")
        cnx.rollback()
        raise
    cnx.commit()


def sem_set_responsable_name(sem):
    "ajoute champs responsable_name"
    sem["responsable_name"] = ", ".join(
        [
            sco_users.user_info(responsable_id)["nomprenom"]
            for responsable_id in sem["responsables"]
        ]
    )


def sem_in_semestre_scolaire(sem, year=False, saison=0):
    """n'utilise que la date de debut, pivot au 1er aout
    si annee non specifiée, année scolaire courante
    Patch Jmp: ajout du parametre optionnel saison
    1 = sept, 0 = janvier, None = année complète
    si saison non spécifiée: année complète
    pivot de saison au 1er décembre
    XXX TODO: la période (ici appelée "saison" devrait être éditable
    manuellement dans le formsemestre_edit afin de couvrir les cas particulier
    comme un semestre S2 qui commencerait en décembre... voire novembre.
    )
    """
    if not year:
        year = scu.AnneeScolaire()
    # est-on dans la même année universitaire ?
    if sem["mois_debut_ord"] > 7:
        if sem["annee_debut"] != str(year):
            return False
    else:
        if sem["annee_debut"] != str(year + 1):
            return False
    # rafinement éventuel sur le semestre
    # saison is None => pas de rafinement => True
    if saison == 0:
        return True
    elif saison == 1:  # calcul en fonction de la saison
        return sem["mois_debut_ord"] > 7 and sem["mois_debut_ord"] < 12
    else:  # saison == 0
        return sem["mois_debut_ord"] <= 7 or sem["mois_debut_ord"] == 12


def sem_in_annee_scolaire(sem, year=False):
    """Test si sem appartient à l'année scolaire year (int).
    N'utilise que la date de debut, pivot au 1er août.
    Si annee non specifiée, année scolaire courante
    """
    if not year:
        year = scu.AnneeScolaire()
    return ((sem["annee_debut"] == str(year)) and (sem["mois_debut_ord"] > 7)) or (
        (sem["annee_debut"] == str(year + 1)) and (sem["mois_debut_ord"] <= 7)
    )


def sem_une_annee(sem):
    """Test si sem est entièrement sur la même année scolaire.
    (ce n'est pas obligatoire mais si ce n'est pas le cas les exports Apogée ne vont pas fonctionner)
    pivot au 1er août.
    """
    if sem["date_debut_iso"] > sem["date_fin_iso"]:
        log("Warning: semestre %(formsemestre_id)s begins after ending !" % sem)
        return False

    debut = int(sem["annee_debut"])
    if sem["mois_debut_ord"] < 8:  # considere que debut sur l'anne scolaire precedente
        debut -= 1
    fin = int(sem["annee_fin"])
    if (
        sem["mois_fin_ord"] < 9
    ):  # 9 (sept) pour autoriser un début en sept et une fin en aout
        fin -= 1
    return debut == fin


def sem_est_courant(sem):
    """Vrai si la date actuelle (now) est dans le semestre (les dates de début et fin sont incluses)"""
    now = time.strftime("%Y-%m-%d")
    debut = ndb.DateDMYtoISO(sem["date_debut"])
    fin = ndb.DateDMYtoISO(sem["date_fin"])
    return (debut <= now) and (now <= fin)


def scodoc_get_all_unlocked_sems():
    """Liste de tous les semestres non verrouillés de _tous_ les départements
    (utilisé pour rapports d'activités)
    """
    cur_dept = g.scodoc_dept
    depts = Departement.query.filter_by(visible=True).all()
    semdepts = []
    try:
        for dept in depts:
            app.set_sco_dept(dept.acronym)
            semdepts += [(sem, dept) for sem in do_formsemestre_list() if sem["etat"]]
    finally:
        app.set_sco_dept(cur_dept)
    return semdepts


def table_formsemestres(
    sems,
    columns_ids=(),
    sup_columns_ids=(),
    html_title="<h2>Semestres</h2>",
    html_next_section="",
):
    """Une table presentant des semestres"""
    for sem in sems:
        sem_set_responsable_name(sem)
        sem["_titre_num_target"] = (
            "formsemestre_status?formsemestre_id=%s" % sem["formsemestre_id"]
        )

    if not columns_ids:
        columns_ids = (
            "etat",
            "modalite",
            "mois_debut",
            "mois_fin",
            "titre_num",
            "responsable_name",
            "etapes_apo_str",
        )
    columns_ids += sup_columns_ids

    titles = {
        "modalite": "",
        "mois_debut": "Début",
        "mois_fin": "Fin",
        "titre_num": "Semestre",
        "responsable_name": "Resp.",
        "etapes_apo_str": "Apo.",
    }
    if sems:
        preferences = sco_preferences.SemPreferences(sems[0]["formsemestre_id"])
    else:
        preferences = sco_preferences.SemPreferences()
    tab = GenTable(
        columns_ids=columns_ids,
        rows=sems,
        titles=titles,
        html_class="table_leftalign",
        html_sortable=True,
        html_title=html_title,
        html_next_section=html_next_section,
        html_empty_element="<p><em>aucun résultat</em></p>",
        page_title="Semestres",
        preferences=preferences,
    )
    return tab


def list_formsemestre_by_etape(etape_apo=False, annee_scolaire=False):
    """Liste des semestres de cette etape, pour l'annee scolaire indiquée (sinon, pour toutes)"""
    ds = {}  # formsemestre_id : sem
    if etape_apo:
        sems = do_formsemestre_list(args={"etape_apo": etape_apo})
        for sem in sems:
            if annee_scolaire:  # restriction annee scolaire
                if sem_in_annee_scolaire(sem, year=int(annee_scolaire)):
                    ds[sem["formsemestre_id"]] = sem
        sems = list(ds.values())
    else:
        sems = do_formsemestre_list()
        if annee_scolaire:
            sems = [
                sem
                for sem in sems
                if sem_in_annee_scolaire(sem, year=int(annee_scolaire))
            ]

    sems.sort(key=lambda s: (s["modalite"], s["dateord"]))
    return sems


def view_formsemestre_by_etape(etape_apo=None, format="html"):
    """Affiche table des semestres correspondants à l'étape"""
    if etape_apo:
        html_title = (
            """<h2>Semestres courants de l'étape <tt>%s</tt></h2>""" % etape_apo
        )
    else:
        html_title = """<h2>Semestres courants</h2>"""
    tab = table_formsemestres(
        list_formsemestre_by_etape(
            etape_apo=etape_apo, annee_scolaire=scu.AnneeScolaire()
        ),
        html_title=html_title,
        html_next_section="""<form action="view_formsemestre_by_etape">
    Etape: <input name="etape_apo" type="text" size="8"></input>    
        </form>""",
    )
    tab.base_url = "%s?etape_apo=%s" % (request.base_url, etape_apo or "")
    return tab.make_page(format=format)


def sem_has_etape(sem, code_etape):
    return code_etape in sem["etapes"]
