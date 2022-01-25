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

"""Gestion des groupes, nouvelle mouture (juin/nov 2009)

TODO:
Optimisation possible:
 revoir do_evaluation_listeetuds_groups() pour extraire aussi les groupes (de chaque etudiant)
 et éviter ainsi l'appel ulterieur à get_etud_groups() dans _make_table_notes

"""
import collections
import operator
import re
import time

from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import flask
from flask import g, request
from flask import url_for, make_response

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log, cache
from app.scodoc.scolog import logdb
from app.scodoc import html_sco_header
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_cache
from app.scodoc import sco_etud
from app.scodoc import sco_permissions_check
from app.scodoc import sco_xml
from app.scodoc.sco_exceptions import ScoException, AccessDenied, ScoValueError
from app.scodoc.sco_permissions import Permission
from app.scodoc.TrivialFormulator import TrivialFormulator


partitionEditor = ndb.EditableTable(
    "partition",
    "partition_id",
    (
        "partition_id",
        "formsemestre_id",
        "partition_name",
        "compute_ranks",
        "numero",
        "bul_show_rank",
        "show_in_lists",
    ),
    input_formators={
        "bul_show_rank": bool,
        "show_in_lists": bool,
    },
)

groupEditor = ndb.EditableTable(
    "group_descr", "group_id", ("group_id", "partition_id", "group_name")
)

group_list = groupEditor.list


def get_group(group_id):
    """Returns group object, with partition"""
    r = ndb.SimpleDictFetch(
        """SELECT gd.id AS group_id, gd.*, p.id AS partition_id, p.*
        FROM group_descr gd, partition p
        WHERE gd.id=%(group_id)s
        AND p.id = gd.partition_id
        """,
        {"group_id": group_id},
    )
    if not r:
        raise ValueError("invalid group_id (%s)" % group_id)
    return r[0]


def group_delete(group, force=False):
    """Delete a group."""
    # if not group['group_name'] and not force:
    #    raise ValueError('cannot suppress this group')
    # remove memberships:
    ndb.SimpleQuery("DELETE FROM group_membership WHERE group_id=%(group_id)s", group)
    # delete group:
    ndb.SimpleQuery("DELETE FROM group_descr WHERE id=%(group_id)s", group)


def get_partition(partition_id):
    r = ndb.SimpleDictFetch(
        """SELECT p.id AS partition_id, p.*
        FROM partition p
        WHERE p.id = %(partition_id)s
        """,
        {"partition_id": partition_id},
    )
    if not r:
        raise ValueError("invalid partition_id (%s)" % partition_id)
    return r[0]


def get_partitions_list(formsemestre_id, with_default=True):
    """Liste des partitions pour ce semestre (list of dicts)"""
    partitions = ndb.SimpleDictFetch(
        """SELECT p.id AS partition_id, p.*
        FROM partition p
        WHERE formsemestre_id=%(formsemestre_id)s 
        ORDER BY numero""",
        {"formsemestre_id": formsemestre_id},
    )
    # Move 'all' at end of list (for menus)
    R = [p for p in partitions if p["partition_name"] != None]
    if with_default:
        R += [p for p in partitions if p["partition_name"] == None]
    return R


def get_default_partition(formsemestre_id):
    """Get partition for 'all' students (this one always exists, with NULL name)"""
    r = ndb.SimpleDictFetch(
        """SELECT p.id AS partition_id, p.* FROM partition p
        WHERE formsemestre_id=%(formsemestre_id)s
        AND partition_name is NULL
        """,
        {"formsemestre_id": formsemestre_id},
    )
    if len(r) != 1:
        raise ScoException(
            "inconsistent partition: %d with NULL name for formsemestre_id=%s"
            % (len(r), formsemestre_id)
        )
    return r[0]


def get_formsemestre_groups(formsemestre_id, with_default=False):
    """Returns  ( partitions, { partition_id : { etudid : group } } )."""
    partitions = get_partitions_list(formsemestre_id, with_default=with_default)
    partitions_etud_groups = {}  # { partition_id : { etudid : group } }
    for partition in partitions:
        pid = partition["partition_id"]
        partitions_etud_groups[pid] = get_etud_groups_in_partition(pid)
    return partitions, partitions_etud_groups


def get_partition_groups(partition):
    """List of groups in this partition (list of dicts).
    Some groups may be empty."""
    return ndb.SimpleDictFetch(
        """SELECT gd.id AS group_id, p.id AS partition_id, gd.*, p.*
        FROM group_descr gd, partition p
        WHERE gd.partition_id=%(partition_id)s
        AND gd.partition_id=p.id
        ORDER BY group_name
        """,
        partition,
    )


def get_default_group(formsemestre_id, fix_if_missing=False):
    """Returns group_id for default ('tous') group"""
    r = ndb.SimpleDictFetch(
        """SELECT gd.id AS group_id
        FROM group_descr gd, partition p
        WHERE p.formsemestre_id=%(formsemestre_id)s
        AND p.partition_name is NULL
        AND p.id = gd.partition_id
        """,
        {"formsemestre_id": formsemestre_id},
    )
    if len(r) == 0 and fix_if_missing:
        # No default group (problem during sem creation)
        # Try to create it
        log(
            "*** Warning: get_default_group(formsemestre_id=%s): default group missing, recreating it"
            % formsemestre_id
        )
        try:
            partition_id = get_default_partition(formsemestre_id)["partition_id"]
        except ScoException:
            log("creating default partition for %s" % formsemestre_id)
            partition_id = partition_create(
                formsemestre_id, default=True, redirect=False
            )
        group_id = create_group(partition_id, default=True)
        return group_id
    # debug check
    if len(r) != 1:
        raise ScoException("invalid group structure for %s" % formsemestre_id)
    group_id = r[0]["group_id"]
    return group_id


def get_sem_groups(formsemestre_id):
    """Returns groups for this sem (in all partitions)."""
    return ndb.SimpleDictFetch(
        """SELECT gd.id AS group_id, p.id AS partition_id, gd.*, p.*
        FROM group_descr gd, partition p
        WHERE p.formsemestre_id=%(formsemestre_id)s
        AND p.id = gd.partition_id
        """,
        {"formsemestre_id": formsemestre_id},
    )


def get_group_members(group_id, etat=None):
    """Liste des etudiants d'un groupe.
    Si etat, filtre selon l'état de l'inscription
    Trié par nom_usuel (ou nom) puis prénom
    """
    req = """SELECT i.id as etudid, i.*, a.*, gm.*, ins.etat
    FROM identite i, adresse a, group_membership gm, 
    group_descr gd, partition p, notes_formsemestre_inscription ins 
    WHERE i.id = gm.etudid 
    and a.etudid = i.id 
    and ins.etudid = i.id 
    and ins.formsemestre_id = p.formsemestre_id 
    and p.id = gd.partition_id 
    and gd.id = gm.group_id 
    and gm.group_id=%(group_id)s
    """
    if etat is not None:
        req += " and ins.etat = %(etat)s"

    r = ndb.SimpleDictFetch(req, {"group_id": group_id, "etat": etat})

    for etud in r:
        sco_etud.format_etud_ident(etud)

    r.sort(key=operator.itemgetter("nom_disp", "prenom"))  # tri selon nom_usuel ou nom

    if scu.CONFIG.ALLOW_NULL_PRENOM:
        for x in r:
            x["prenom"] = x["prenom"] or ""

    return r


# obsolete:  sco_groups_view.DisplayedGroupsInfos
# def get_groups_members(group_ids, etat=None):
#     """Liste les étudiants d'une liste de groupes
#     chaque étudiant n'apparait qu'une seule fois dans le résultat.
#     La liste est triée par nom / prenom
#     """
#     D = {} # { etudid : etud  }
#     for group_id in group_ids:
#         members = get_group_members(group_id, etat=etat)
#         for m in members:
#             D[m['etudid']] = m
#     r = D.values()
#     r.sort(key=operator.itemgetter('nom_disp', 'prenom')) # tri selon nom_usuel ou nom

#     return r


def get_group_infos(group_id, etat=None):  # was _getlisteetud
    """legacy code: used by group_list and trombino"""
    from app.scodoc import sco_formsemestre

    cnx = ndb.GetDBConnexion()
    group = get_group(group_id)
    sem = sco_formsemestre.get_formsemestre(group["formsemestre_id"])

    members = get_group_members(group_id, etat=etat)
    # add human readable description of state:
    nbdem = 0
    for t in members:
        if t["etat"] == "I":
            t["etath"] = ""  # etudiant inscrit, ne l'indique pas dans la liste HTML
        elif t["etat"] == "D":
            events = sco_etud.scolar_events_list(
                cnx,
                args={
                    "etudid": t["etudid"],
                    "formsemestre_id": group["formsemestre_id"],
                },
            )
            for event in events:
                event_type = event["event_type"]
                if event_type == "DEMISSION":
                    t["date_dem"] = event["event_date"]
                    break
            if "date_dem" in t:
                t["etath"] = "démission le %s" % t["date_dem"]
            else:
                t["etath"] = "(dem.)"
            nbdem += 1
        elif t["etat"] == sco_codes_parcours.DEF:
            t["etath"] = "Défaillant"
        else:
            t["etath"] = t["etat"]
    # Add membership for all partitions, 'partition_id' : group
    for etud in members:  # long: comment eviter ces boucles ?
        etud_add_group_infos(etud, sem)

    if group["group_name"] != None:
        group_tit = "%s %s" % (group["partition_name"], group["group_name"])
    else:
        group_tit = "tous"

    return members, group, group_tit, sem, nbdem


def get_group_other_partitions(group):
    """Liste des partitions du même semestre que ce groupe,
    sans celle qui contient ce groupe.
    """
    other_partitions = [
        p
        for p in get_partitions_list(group["formsemestre_id"])
        if p["partition_id"] != group["partition_id"] and p["partition_name"]
    ]
    return other_partitions


def get_etud_groups(etudid, sem, exclude_default=False):
    """Infos sur groupes de l'etudiant dans ce semestre
    [ group + partition_name ]
    """
    req = """SELECT p.id AS partition_id, p.*, g.id AS group_id, g.*
    FROM group_descr g, partition p, group_membership gm 
    WHERE gm.etudid=%(etudid)s 
    and gm.group_id = g.id 
    and g.partition_id = p.id 
    and p.formsemestre_id = %(formsemestre_id)s
    """
    if exclude_default:
        req += " and p.partition_name is not NULL"
    groups = ndb.SimpleDictFetch(
        req + " ORDER BY p.numero",
        {"etudid": etudid, "formsemestre_id": sem["formsemestre_id"]},
    )
    return _sortgroups(groups)


def get_etud_main_group(etudid, sem):
    """Return main group (the first one) for etud, or default one if no groups"""
    groups = get_etud_groups(etudid, sem, exclude_default=True)
    if groups:
        return groups[0]
    else:
        return get_group(get_default_group(sem["formsemestre_id"]))


def formsemestre_get_main_partition(formsemestre_id):
    """Return main partition (the first one) for sem, or default one if no groups
    (rappel: default == tous, main == principale (groupes TD habituellement)
    """
    return get_partitions_list(formsemestre_id, with_default=True)[0]


def formsemestre_get_etud_groupnames(formsemestre_id, attr="group_name"):
    """Recupere les groupes de tous les etudiants d'un semestre
    { etudid : { partition_id : group_name  }}  (attr=group_name or group_id)
    """
    infos = ndb.SimpleDictFetch(
        """SELECT
        i.etudid AS etudid,
        p.id AS partition_id,
        gd.group_name,
        gd.id AS group_id
        FROM 
        notes_formsemestre_inscription i,
        partition p,
        group_descr gd,
        group_membership gm
        WHERE
        i.formsemestre_id=%(formsemestre_id)s
        and i.formsemestre_id = p.formsemestre_id
        and p.id = gd.partition_id
        and gm.etudid = i.etudid
        and gm.group_id = gd.id
        and p.partition_name is not NULL
        """,
        {"formsemestre_id": formsemestre_id},
    )
    R = {}
    for info in infos:
        if info["etudid"] in R:
            R[info["etudid"]][info["partition_id"]] = info[attr]
        else:
            R[info["etudid"]] = {info["partition_id"]: info[attr]}
    return R


def etud_add_group_infos(etud, sem, sep=" "):
    """Add informations on partitions and group memberships to etud (a dict with an etudid)"""
    etud[
        "partitions"
    ] = collections.OrderedDict()  # partition_id : group + partition_name
    if not sem:
        etud["groupes"] = ""
        return etud

    infos = ndb.SimpleDictFetch(
        """SELECT p.partition_name, g.*, g.id AS group_id
        FROM group_descr g, partition p, group_membership gm WHERE gm.etudid=%(etudid)s
        and gm.group_id = g.id
        and g.partition_id = p.id
        and p.formsemestre_id = %(formsemestre_id)s
        ORDER BY p.numero
        """,
        {"etudid": etud["etudid"], "formsemestre_id": sem["formsemestre_id"]},
    )

    for info in infos:
        if info["partition_name"]:
            etud["partitions"][info["partition_id"]] = info

    # resume textuel des groupes:
    etud["groupes"] = sep.join(
        [g["group_name"] for g in infos if g["group_name"] != None]
    )
    etud["partitionsgroupes"] = sep.join(
        [
            g["partition_name"] + ":" + g["group_name"]
            for g in infos
            if g["group_name"] != None
        ]
    )

    return etud


@cache.memoize(timeout=50)  # seconds
def get_etud_groups_in_partition(partition_id):
    """Returns { etudid : group }, with all students in this partition"""
    infos = ndb.SimpleDictFetch(
        """SELECT gd.id AS group_id, gd.*, etudid
        FROM group_descr gd, group_membership gm
        WHERE gd.partition_id = %(partition_id)s
        AND gm.group_id = gd.id
        """,
        {"partition_id": partition_id},
    )
    R = {}
    for i in infos:
        R[i["etudid"]] = i
    return R


def formsemestre_partition_list(formsemestre_id, format="xml"):
    """Get partitions and groups in this semestre
    Supported formats: xml, json
    """
    partitions = get_partitions_list(formsemestre_id, with_default=True)
    # Ajoute les groupes
    for p in partitions:
        p["group"] = get_partition_groups(p)
    return scu.sendResult(partitions, name="partition", format=format)


# Encore utilisé par groupmgr.js
def XMLgetGroupsInPartition(partition_id):  # was XMLgetGroupesTD
    """
    Deprecated: use group_list
    Liste des étudiants dans chaque groupe de cette partition.
    <group partition_id="" partition_name="" group_id="" group_name="">
    <etud etuid="" sexe="" nom="" prenom="" civilite="" origin=""/>
    </group>
    <group ...>
    ...
    """
    from app.scodoc import sco_formsemestre

    cnx = ndb.GetDBConnexion()

    t0 = time.time()
    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    groups = get_partition_groups(partition)
    nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > inscrdict
    etuds_set = set(nt.inscrdict)
    # Build XML:
    t1 = time.time()
    doc = Element("ajax-response")
    x_response = Element("response", type="object", id="MyUpdater")
    doc.append(x_response)
    for group in groups:
        x_group = Element(
            "group",
            partition_id=str(partition_id),
            partition_name=partition["partition_name"],
            group_id=str(group["group_id"]),
            group_name=group["group_name"],
        )
        x_response.append(x_group)
        for e in get_group_members(group["group_id"]):
            etud = sco_etud.get_etud_info(etudid=e["etudid"], filled=True)[0]
            # etud = sco_etud.get_etud_info_filled_by_etudid(e["etudid"], cnx)
            x_group.append(
                Element(
                    "etud",
                    etudid=str(e["etudid"]),
                    civilite=etud["civilite_str"],
                    sexe=etud["civilite_str"],  # compat
                    nom=sco_etud.format_nom(etud["nom"]),
                    prenom=sco_etud.format_prenom(etud["prenom"]),
                    origin=comp_origin(etud, sem),
                )
            )
            if e["etudid"] in etuds_set:
                etuds_set.remove(e["etudid"])  # etudiant vu dans un groupe

    # Ajoute les etudiants inscrits au semestre mais dans aucun groupe de cette partition:
    if etuds_set:
        x_group = Element(
            "group",
            partition_id=str(partition_id),
            partition_name=partition["partition_name"],
            group_id="_none_",
            group_name="",
        )
        doc.append(x_group)
        for etudid in etuds_set:
            etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
            # etud = sco_etud.get_etud_info_filled_by_etudid(etudid, cnx)
            x_group.append(
                Element(
                    "etud",
                    etudid=str(etud["etudid"]),
                    sexe=etud["civilite_str"],
                    nom=sco_etud.format_nom(etud["nom"]),
                    prenom=sco_etud.format_prenom(etud["prenom"]),
                    origin=comp_origin(etud, sem),
                )
            )
    t2 = time.time()
    log(f"XMLgetGroupsInPartition: {t2-t0} seconds ({t1-t0}+{t2-t1})")
    # XML response:
    data = sco_xml.XML_HEADER + ElementTree.tostring(doc).decode(scu.SCO_ENCODING)
    response = make_response(data)
    response.headers["Content-Type"] = scu.XML_MIMETYPE
    return response


def comp_origin(etud, cur_sem):
    """breve description de l'origine de l'étudiant (sem. precedent)
    (n'indique l'origine que si ce n'est pas le semestre precedent normal)
    """
    # cherche le semestre suivant le sem. courant dans la liste
    cur_sem_idx = None
    for i in range(len(etud["sems"])):
        if etud["sems"][i]["formsemestre_id"] == cur_sem["formsemestre_id"]:
            cur_sem_idx = i
            break

    if cur_sem_idx is None or (cur_sem_idx + 1) >= (len(etud["sems"]) - 1):
        return ""  # on pourrait indiquer le bac mais en general on ne l'a pas en debut d'annee

    prev_sem = etud["sems"][cur_sem_idx + 1]
    if prev_sem["semestre_id"] != (cur_sem["semestre_id"] - 1):
        return " (S%s)" % prev_sem["semestre_id"]
    else:
        return ""  # parcours normal, ne le signale pas


def set_group(etudid, group_id):
    """Inscrit l'étudiant au groupe.
    Return True if ok, False si deja inscrit.
    Warning: don't check if group_id exists (the caller should check).
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    args = {"etudid": etudid, "group_id": group_id}
    # déjà inscrit ?
    r = ndb.SimpleDictFetch(
        "SELECT * FROM group_membership gm WHERE etudid=%(etudid)s and group_id=%(group_id)s",
        args,
        cursor=cursor,
    )
    if len(r):
        return False
    # inscrit
    ndb.SimpleQuery(
        "INSERT INTO group_membership (etudid, group_id) VALUES (%(etudid)s, %(group_id)s)",
        args,
        cursor=cursor,
    )
    return True


def change_etud_group_in_partition(etudid, group_id, partition=None):
    """Inscrit etud au groupe de cette partition, et le desinscrit d'autres groupes de cette partition."""
    log("change_etud_group_in_partition: etudid=%s group_id=%s" % (etudid, group_id))

    # 0- La partition
    group = get_group(group_id)
    if partition:
        # verifie que le groupe est bien dans cette partition:
        if group["partition_id"] != partition["partition_id"]:
            raise ValueError(
                "inconsistent group/partition (group_id=%s, partition_id=%s)"
                % (group_id, partition["partition_id"])
            )
    else:
        partition = get_partition(group["partition_id"])
    # 1- Supprime membership dans cette partition
    ndb.SimpleQuery(
        """DELETE FROM group_membership gm
        WHERE EXISTS
        (SELECT 1 FROM  group_descr gd
            WHERE gm.etudid = %(etudid)s
            AND gm.group_id = gd.id
            AND gd.partition_id = %(partition_id)s)
        """,
        {"etudid": etudid, "partition_id": partition["partition_id"]},
    )
    # 2- associe au nouveau groupe
    set_group(etudid, group_id)

    # 3- log
    formsemestre_id = partition["formsemestre_id"]
    cnx = ndb.GetDBConnexion()
    logdb(
        cnx,
        method="changeGroup",
        etudid=etudid,
        msg="formsemestre_id=%s,partition_name=%s, group_name=%s"
        % (formsemestre_id, partition["partition_name"], group["group_name"]),
    )
    cnx.commit()
    # 4- invalidate cache
    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > change etud group


def setGroups(
    partition_id,
    groupsLists="",  # members of each existing group
    groupsToCreate="",  # name and members of new groups
    groupsToDelete="",  # groups to delete
):
    """Affect groups (Ajax request)
    groupsLists: lignes de la forme "group_id;etudid;...\n"
    groupsToCreate: lignes "group_name;etudid;...\n"
    groupsToDelete: group_id;group_id;...
    """
    from app.scodoc import sco_formsemestre

    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    log("***setGroups: partition_id=%s" % partition_id)
    log("groupsLists=%s" % groupsLists)
    log("groupsToCreate=%s" % groupsToCreate)
    log("groupsToDelete=%s" % groupsToDelete)
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        raise AccessDenied("Modification impossible: semestre verrouillé")

    groupsToDelete = [g for g in groupsToDelete.split(";") if g]

    etud_groups = formsemestre_get_etud_groupnames(formsemestre_id, attr="group_id")
    for line in groupsLists.split("\n"):  # for each group_id (one per line)
        fs = line.split(";")
        group_id = fs[0].strip()
        if not group_id:
            continue
        group = get_group(group_id)
        # Anciens membres du groupe:
        old_members = get_group_members(group_id)
        old_members_set = set([x["etudid"] for x in old_members])
        # Place dans ce groupe les etudiants indiqués:
        for etudid_str in fs[1:-1]:
            etudid = int(etudid_str)
            if etudid in old_members_set:
                old_members_set.remove(
                    etudid
                )  # a nouveau dans ce groupe, pas besoin de l'enlever
            if (etudid not in etud_groups) or (
                group_id != etud_groups[etudid].get(partition_id, "")
            ):  # pas le meme groupe qu'actuel
                change_etud_group_in_partition(etudid, group_id, partition)
        # Retire les anciens membres:
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        for etudid in old_members_set:
            log("removing %s from group %s" % (etudid, group_id))
            ndb.SimpleQuery(
                "DELETE FROM group_membership WHERE etudid=%(etudid)s and group_id=%(group_id)s",
                {"etudid": etudid, "group_id": group_id},
                cursor=cursor,
            )
            logdb(
                cnx,
                method="removeFromGroup",
                etudid=etudid,
                msg="formsemestre_id=%s,partition_name=%s, group_name=%s"
                % (formsemestre_id, partition["partition_name"], group["group_name"]),
            )

    # Supprime les groupes indiqués comme supprimés:
    for group_id in groupsToDelete:
        delete_group(group_id, partition_id=partition_id)

    # Crée les nouveaux groupes
    for line in groupsToCreate.split("\n"):  # for each group_name (one per line)
        fs = line.split(";")
        group_name = fs[0].strip()
        if not group_name:
            continue
        group_id = create_group(partition_id, group_name)
        # Place dans ce groupe les etudiants indiqués:
        for etudid in fs[1:-1]:
            change_etud_group_in_partition(etudid, group_id, partition)

    data = (
        '<?xml version="1.0" encoding="utf-8"?><response>Groupes enregistrés</response>'
    )
    response = make_response(data)
    response.headers["Content-Type"] = scu.XML_MIMETYPE
    return response


def create_group(partition_id, group_name="", default=False) -> int:
    """Create a new group in this partition"""
    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    #
    if group_name:
        group_name = group_name.strip()
    if not group_name and not default:
        raise ValueError("invalid group name: ()")
    # checkGroupName(group_name)
    if group_name in [g["group_name"] for g in get_partition_groups(partition)]:
        raise ValueError(
            "group_name %s already exists in partition" % group_name
        )  # XXX FIX: incorrect error handling (in AJAX)
    cnx = ndb.GetDBConnexion()
    group_id = groupEditor.create(
        cnx, {"partition_id": partition_id, "group_name": group_name}
    )
    log("create_group: created group_id=%s" % group_id)
    #
    return group_id


def delete_group(group_id, partition_id=None):
    """form suppression d'un groupe.
    (ne desinscrit pas les etudiants, change juste leur
    affectation aux groupes)
    partition_id est optionnel et ne sert que pour verifier que le groupe
    est bien dans cette partition.
    """
    group = get_group(group_id)
    if partition_id:
        if partition_id != group["partition_id"]:
            raise ValueError("inconsistent partition/group")
    else:
        partition_id = group["partition_id"]
    partition = get_partition(partition_id)
    if not sco_permissions_check.can_change_groups(partition["formsemestre_id"]):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    log(
        "delete_group: group_id=%s group_name=%s partition_name=%s"
        % (group_id, group["group_name"], partition["partition_name"])
    )
    group_delete(group)


def partition_create(
    formsemestre_id,
    partition_name="",
    default=False,
    numero=None,
    redirect=True,
):
    """Create a new partition"""
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    if partition_name:
        partition_name = str(partition_name).strip()
    if default:
        partition_name = None
    if not partition_name and not default:
        raise ScoValueError("Nom de partition invalide (vide)")
    redirect = int(redirect)
    # checkGroupName(partition_name)
    if partition_name in [
        p["partition_name"] for p in get_partitions_list(formsemestre_id)
    ]:
        raise ScoValueError(
            "Il existe déjà une partition %s dans ce semestre" % partition_name
        )

    cnx = ndb.GetDBConnexion()
    if numero is None:
        numero = (
            ndb.SimpleQuery(
                "SELECT MAX(id) FROM partition WHERE formsemestre_id=%(formsemestre_id)s",
                {"formsemestre_id": formsemestre_id},
            ).fetchone()[0]
            or 0
        )
    partition_id = partitionEditor.create(
        cnx,
        {
            "formsemestre_id": formsemestre_id,
            "partition_name": partition_name,
            "numero": numero,
        },
    )
    log("createPartition: created partition_id=%s" % partition_id)
    #
    if redirect:
        return flask.redirect(
            url_for(
                "scolar.editPartitionForm",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
            )
        )
    else:
        return partition_id


def get_arrow_icons_tags():
    """returns html tags for arrows"""
    #
    arrow_up = scu.icontag("arrow_up", title="remonter")
    arrow_down = scu.icontag("arrow_down", title="descendre")
    arrow_none = scu.icontag("arrow_none", title="")

    return arrow_up, arrow_down, arrow_none


def editPartitionForm(formsemestre_id=None):
    """Form to create/suppress partitions"""
    # ad-hoc form
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    partitions = get_partitions_list(formsemestre_id)
    arrow_up, arrow_down, arrow_none = get_arrow_icons_tags()
    suppricon = scu.icontag(
        "delete_small_img", border="0", alt="supprimer", title="Supprimer"
    )
    #
    H = [
        html_sco_header.sco_header(
            page_title="Partitions...",
            javascripts=["js/editPartitionForm.js"],
        ),
        r"""<script type="text/javascript">
          function checkname() {
 var val = document.editpart.partition_name.value.replace(/^\s+/, "").replace(/\s+$/, "");
 if (val.length > 0) {
   document.editpart.ok.disabled = false;
 } else {
   document.editpart.ok.disabled = true;
 }
}
          </script>
          """,
        r"""<h2>Partitions du semestre</h2>
          <form name="editpart" id="editpart" method="POST" action="partition_create">
          <div id="epmsg"></div>
          <table><tr class="eptit"><th></th><th></th><th></th><th>Partition</th><th>Groupes</th><th></th><th></th><th></th></tr>
    """,
    ]
    i = 0
    for p in partitions:
        if p["partition_name"] is not None:
            H.append(
                '<tr><td class="epnav"><a class="stdlink" href="partition_delete?partition_id=%s">%s</a>&nbsp;</td><td class="epnav">'
                % (p["partition_id"], suppricon)
            )
            if i != 0:
                H.append(
                    '<a href="partition_move?partition_id=%s&after=0">%s</a>'
                    % (p["partition_id"], arrow_up)
                )
            H.append('</td><td class="epnav">')
            if i < len(partitions) - 2:
                H.append(
                    '<a href="partition_move?partition_id=%s&after=1">%s</a>'
                    % (p["partition_id"], arrow_down)
                )
            i += 1
            H.append("</td>")
            pname = p["partition_name"] or ""
            H.append("<td>%s</td>" % pname)
            H.append("<td>")
            lg = [
                "%s (%d)"
                % (
                    group["group_name"],
                    len(get_group_members(group["group_id"])),
                )
                for group in get_partition_groups(p)
            ]
            H.append(", ".join(lg))
            H.append(
                f"""</td><td><a class="stdlink" href="{
                    url_for("scolar.affect_groups",
                    scodoc_dept=g.scodoc_dept,
                    partition_id=p["partition_id"])
                }">répartir</a></td>
                """
            )
            H.append(
                '<td><a class="stdlink" href="partition_rename?partition_id=%s">renommer</a></td>'
                % p["partition_id"]
            )
            # classement:
            H.append('<td width="250px">')
            if p["bul_show_rank"]:
                checked = 'checked="1"'
            else:
                checked = ""
            H.append(
                '<div><input type="checkbox" class="rkbox" data-partition_id="%s" %s onchange="update_rk(this);"/>afficher rang sur bulletins</div>'
                % (p["partition_id"], checked)
            )
            if p["show_in_lists"]:
                checked = 'checked="1"'
            else:
                checked = ""
            H.append(
                '<div><input type="checkbox" class="rkbox" data-partition_id="%s" %s onchange="update_show_in_list(this);"/>afficher sur noms groupes</div>'
                % (p["partition_id"], checked)
            )
            H.append("</td>")
            #
            H.append("</tr>")
    H.append("</table>")
    H.append('<div class="form_rename_partition">')
    H.append(
        '<input type="hidden" name="formsemestre_id" value="%s"/>' % formsemestre_id
    )
    H.append('<input type="hidden" name="redirect" value="1"/>')
    H.append(
        '<input type="text" name="partition_name" size="12" onkeyup="checkname();"/>'
    )
    H.append('<input type="submit" name="ok" disabled="1" value="Nouvelle partition"/>')
    H.append("</div></form>")
    H.append(
        """<div class="help">
    <p>Les partitions sont des découpages de l'ensemble des étudiants. 
    Par exemple, les "groupes de TD" sont une partition. 
    On peut créer autant de partitions que nécessaire. 
    </p>
    <ul>
    <li>Dans chaque partition, un nombre de groupes quelconque peuvent être créés (suivre le lien "répartir").
    <li>On peut faire afficher le classement de l'étudiant dans son groupe d'une partition en cochant "afficher rang sur bulletins" (ainsi, on peut afficher le classement en groupes de TD mais pas en groupe de TP, si ce sont deux partitions).
    </li>
    <li>Décocher "afficher sur noms groupes" pour ne pas que cette partition apparaisse dans les noms de groupes
    </li>    
    </ul>
    </div>
    """
    )
    return "\n".join(H) + html_sco_header.sco_footer()


def partition_set_attr(partition_id, attr, value):
    """Set partition attribute: bul_show_rank or show_in_lists"""
    if attr not in {"bul_show_rank", "show_in_lists"}:
        raise ValueError("invalid partition attribute: %s" % attr)

    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")

    log("partition_set_attr(%s, %s, %s)" % (partition_id, attr, value))
    value = int(value)

    cnx = ndb.GetDBConnexion()
    partition[attr] = value
    partitionEditor.edit(cnx, partition)
    # invalid bulletin cache
    sco_cache.invalidate_formsemestre(
        pdfonly=True, formsemestre_id=partition["formsemestre_id"]
    )
    return "enregistré"


def partition_delete(partition_id, force=False, redirect=1, dialog_confirmed=False):
    """Suppress a partition (and all groups within).
    default partition cannot be suppressed (unless force)"""
    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")

    if not partition["partition_name"] and not force:
        raise ValueError("cannot suppress this partition")
    redirect = int(redirect)
    cnx = ndb.GetDBConnexion()
    groups = get_partition_groups(partition)

    if not dialog_confirmed:
        if groups:
            grnames = "(" + ", ".join([g["group_name"] or "" for g in groups]) + ")"
        else:
            grnames = ""
        return scu.confirm_dialog(
            """<h2>Supprimer la partition "%s" ?</h2>
                <p>Les groupes %s de cette partition seront supprimés</p>
                """
            % (partition["partition_name"], grnames),
            dest_url="",
            cancel_url="editPartitionForm?formsemestre_id=%s" % formsemestre_id,
            parameters={"redirect": redirect, "partition_id": partition_id},
        )

    log("partition_delete: partition_id=%s" % partition_id)
    # 1- groups
    for group in groups:
        group_delete(group, force=force)
    # 2- partition
    partitionEditor.delete(cnx, partition_id)

    # redirect to partition edit page:
    if redirect:
        return flask.redirect(
            "editPartitionForm?formsemestre_id=" + str(formsemestre_id)
        )


def partition_move(partition_id, after=0, redirect=1):
    """Move before/after previous one (decrement/increment numero)"""
    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    #
    redirect = int(redirect)
    after = int(after)  # 0: deplace avant, 1 deplace apres
    if after not in (0, 1):
        raise ValueError('invalid value for "after"')
    others = get_partitions_list(formsemestre_id)
    if len(others) > 1:
        pidx = [p["partition_id"] for p in others].index(partition_id)
        # log("partition_move: after=%s pidx=%s" % (after, pidx))
        neigh = None  # partition to swap with
        if after == 0 and pidx > 0:
            neigh = others[pidx - 1]
        elif after == 1 and pidx < len(others) - 1:
            neigh = others[pidx + 1]
        if neigh:  #
            # swap numero between partition and its neighbor
            # log("moving partition %s" % partition_id)
            cnx = ndb.GetDBConnexion()
            # Si aucun numéro n'a été affecté, le met au minimum
            min_numero = (
                ndb.SimpleQuery(
                    "SELECT MIN(numero) FROM partition WHERE formsemestre_id=%(formsemestre_id)s",
                    {"formsemestre_id": formsemestre_id},
                ).fetchone()[0]
                or 0
            )
            if neigh["numero"] is None:
                neigh["numero"] = min_numero - 1
            if partition["numero"] is None:
                partition["numero"] = min_numero - 1 - after
            partition["numero"], neigh["numero"] = neigh["numero"], partition["numero"]
            partitionEditor.edit(cnx, partition)
            partitionEditor.edit(cnx, neigh)

    # redirect to partition edit page:
    if redirect:
        return flask.redirect(
            "editPartitionForm?formsemestre_id=" + str(formsemestre_id)
        )


def partition_rename(partition_id):
    """Form to rename a partition"""
    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    H = ["<h2>Renommer une partition</h2>"]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("partition_id", {"default": partition_id, "input_type": "hidden"}),
            (
                "partition_name",
                {
                    "title": "Nouveau nom",
                    "default": partition["partition_name"],
                    "allow_null": False,
                    "size": 12,
                },
            ),
        ),
        submitlabel="Renommer",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return (
            html_sco_header.sco_header()
            + "\n".join(H)
            + "\n"
            + tf[1]
            + html_sco_header.sco_footer()
        )
    elif tf[0] == -1:
        return flask.redirect(
            "editPartitionForm?formsemestre_id=" + str(formsemestre_id)
        )
    else:
        # form submission
        return partition_set_name(partition_id, tf[2]["partition_name"])


def partition_set_name(partition_id, partition_name, redirect=1):
    """Set partition name"""
    partition_name = str(partition_name).strip()
    if not partition_name:
        raise ValueError("partition name must be non empty")
    partition = get_partition(partition_id)
    if partition["partition_name"] is None:
        raise ValueError("can't set a name to default partition")
    formsemestre_id = partition["formsemestre_id"]

    # check unicity
    r = ndb.SimpleDictFetch(
        """SELECT p.* FROM partition p
        WHERE p.partition_name = %(partition_name)s
        AND formsemestre_id = %(formsemestre_id)s
        """,
        {"partition_name": partition_name, "formsemestre_id": formsemestre_id},
    )
    if len(r) > 1 or (len(r) == 1 and r[0]["id"] != partition_id):
        raise ScoValueError(
            "Partition %s déjà existante dans ce semestre !" % partition_name
        )

    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    redirect = int(redirect)
    cnx = ndb.GetDBConnexion()
    partitionEditor.edit(
        cnx, {"partition_id": partition_id, "partition_name": partition_name}
    )

    # redirect to partition edit page:
    if redirect:
        return flask.redirect(
            "editPartitionForm?formsemestre_id=" + str(formsemestre_id)
        )


def group_set_name(group_id, group_name, redirect=True):
    """Set group name"""
    if group_name:
        group_name = group_name.strip()
    if not group_name:
        raise ScoValueError("nom de groupe vide !")
    group = get_group(group_id)
    if group["group_name"] is None:
        raise ValueError("can't set a name to default group")
    formsemestre_id = group["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    redirect = int(redirect)
    cnx = ndb.GetDBConnexion()
    groupEditor.edit(cnx, {"group_id": group_id, "group_name": group_name})

    # redirect to partition edit page:
    if redirect:
        return flask.redirect(
            url_for(
                "scolar.affect_groups",
                scodoc_dept=g.scodoc_dept,
                partition_id=group["partition_id"],
            )
        )


def group_rename(group_id):
    """Form to rename a group"""
    group = get_group(group_id)
    formsemestre_id = group["formsemestre_id"]
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    H = ["<h2>Renommer un groupe de %s</h2>" % group["partition_name"]]
    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("group_id", {"default": group_id, "input_type": "hidden"}),
            (
                "group_name",
                {
                    "title": "Nouveau nom",
                    "default": group["group_name"],
                    "size": 12,
                    "allow_null": False,
                },
            ),
        ),
        submitlabel="Renommer",
        cancelbutton="Annuler",
    )
    if tf[0] == 0:
        return (
            html_sco_header.sco_header()
            + "\n".join(H)
            + "\n"
            + tf[1]
            + html_sco_header.sco_footer()
        )
    elif tf[0] == -1:
        return flask.redirect(
            url_for(
                "scolar.affect_groups",
                scodoc_dept=g.scodoc_dept,
                partition_id=group["partition_id"],
            )
        )
    else:
        # form submission
        return group_set_name(group_id, tf[2]["group_name"])


def groups_auto_repartition(partition_id=None):
    """Reparti les etudiants dans des groupes dans une partition, en respectant le niveau
    et la mixité.
    """
    from app.scodoc import sco_formsemestre

    partition = get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    # renvoie sur page édition groupes
    dest_url = url_for(
        "scolar.affect_groups", scodoc_dept=g.scodoc_dept, partition_id=partition_id
    )
    if not sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("Vous n'avez pas le droit d'effectuer cette opération !")
    sem = sco_formsemestre.get_formsemestre(formsemestre_id)

    descr = [
        ("partition_id", {"input_type": "hidden"}),
        (
            "groupNames",
            {
                "size": 40,
                "title": "Groupes à créer",
                "allow_null": False,
                "explanation": "noms des groupes à former, séparés par des virgules (les groupes existants seront effacés)",
            },
        ),
    ]

    H = [
        html_sco_header.sco_header(page_title="Répartition des groupes"),
        "<h2>Répartition des groupes de %s</h2>" % partition["partition_name"],
        "<p>Semestre %s</p>" % sem["titreannee"],
        """<p class="help">Les groupes existants seront <b>effacés</b> et remplacés par
          ceux créés ici. La répartition aléatoire tente d'uniformiser le niveau
          des groupes (en utilisant la dernière moyenne générale disponible pour
          chaque étudiant) et de maximiser la mixité de chaque groupe.</p>""",
    ]

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        descr,
        {},
        cancelbutton="Annuler",
        method="GET",
        submitlabel="Créer et peupler les groupes",
        name="tf",
    )
    if tf[0] == 0:
        return "\n".join(H) + "\n" + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(dest_url)
    else:
        # form submission
        log(
            "groups_auto_repartition( partition_id=%s partition_name=%s"
            % (partition_id, partition["partition_name"])
        )
        groupNames = tf[2]["groupNames"]
        group_names = sorted(set([x.strip() for x in groupNames.split(",")]))
        # Détruit les groupes existant de cette partition
        for old_group in get_partition_groups(partition):
            group_delete(old_group)
        # Crée les nouveaux groupes
        group_ids = []
        for group_name in group_names:
            # try:
            #     checkGroupName(group_name)
            # except:
            #     H.append('<p class="warning">Nom de groupe invalide: %s</p>'%group_name)
            #     return '\n'.join(H) + tf[1] + html_sco_header.sco_footer()
            group_ids.append(create_group(partition_id, group_name))
        #
        nt = sco_cache.NotesTableCache.get(formsemestre_id)  # > identdict
        identdict = nt.identdict
        # build:  { civilite : liste etudids trie par niveau croissant }
        civilites = set([x["civilite"] for x in identdict.values()])
        listes = {}
        for civilite in civilites:
            listes[civilite] = [
                (_get_prev_moy(x["etudid"], formsemestre_id), x["etudid"])
                for x in identdict.values()
                if x["civilite"] == civilite
            ]
            listes[civilite].sort()
            log("listes[%s] = %s" % (civilite, listes[civilite]))
        # affect aux groupes:
        n = len(identdict)
        igroup = 0
        nbgroups = len(group_ids)
        while n > 0:
            for civilite in civilites:
                if len(listes[civilite]):
                    n -= 1
                    etudid = listes[civilite].pop()[1]
                    group_id = group_ids[igroup]
                    igroup = (igroup + 1) % nbgroups
                    change_etud_group_in_partition(etudid, group_id, partition)
                    log("%s in group %s" % (etudid, group_id))
        return flask.redirect(dest_url)


def _get_prev_moy(etudid, formsemestre_id):
    """Donne la derniere moyenne generale calculee pour cette étudiant,
    ou 0 si on n'en trouve pas (nouvel inscrit,...).
    """
    from app.scodoc import sco_parcours_dut

    info = sco_etud.get_etud_info(etudid=etudid, filled=True)
    if not info:
        raise ScoValueError("etudiant invalide: etudid=%s" % etudid)
    etud = info[0]
    Se = sco_parcours_dut.SituationEtudParcours(etud, formsemestre_id)
    if Se.prev:
        nt = sco_cache.NotesTableCache.get(
            Se.prev["formsemestre_id"]
        )  # > get_etud_moy_gen
        return nt.get_etud_moy_gen(etudid)
    else:
        return 0.0


def create_etapes_partition(formsemestre_id, partition_name="apo_etapes"):
    """Crée une partition "apo_etapes" avec un groupe par étape Apogée.
    Cette partition n'est crée que si plusieurs étapes différentes existent dans ce
    semestre.
    Si la partition existe déjà, ses groupes sont mis à jour (les groupes devenant
     vides ne sont pas supprimés).
    """
    from app.scodoc import sco_formsemestre_inscriptions

    partition_name = str(partition_name)
    log("create_etapes_partition(%s)" % formsemestre_id)
    ins = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
        args={"formsemestre_id": formsemestre_id}
    )
    etapes = {i["etape"] for i in ins if i["etape"]}
    partitions = get_partitions_list(formsemestre_id, with_default=False)
    partition = None
    for p in partitions:
        if p["partition_name"] == partition_name:
            partition = p
            break
    if len(etapes) < 2 and not partition:
        return  # moins de deux étapes, pas de création
    if partition:
        pid = partition["partition_id"]
    else:
        pid = partition_create(
            formsemestre_id, partition_name=partition_name, redirect=False
        )
    partition = get_partition(pid)
    groups = get_partition_groups(partition)
    groups_by_names = {g["group_name"]: g for g in groups}
    for etape in etapes:
        if not (etape in groups_by_names):
            gid = create_group(pid, etape)
            g = get_group(gid)
            groups_by_names[etape] = g
    # Place les etudiants dans les groupes
    for i in ins:
        if i["etape"]:
            change_etud_group_in_partition(
                i["etudid"], groups_by_names[i["etape"]]["group_id"], partition
            )


def do_evaluation_listeetuds_groups(
    evaluation_id, groups=None, getallstudents=False, include_dems=False
):
    """Donne la liste des etudids inscrits a cette evaluation dans les
    groupes indiqués.
    Si getallstudents==True, donne tous les etudiants inscrits a cette
    evaluation.
    Si include_dems, compte aussi les etudiants démissionnaires
    (sinon, par défaut, seulement les 'I')
    """
    # nb: pour notes_table / do_evaluation_etat, getallstudents est vrai et include_dems faux
    fromtables = [
        "notes_moduleimpl_inscription Im",
        "notes_formsemestre_inscription Isem",
        "notes_moduleimpl M",
        "notes_evaluation E",
    ]
    # construit condition sur les groupes
    if not getallstudents:
        if not groups:
            return []  # no groups, so no students
        rg = ["gm.group_id = '%(group_id)s'" % g for g in groups]
        rq = """and Isem.etudid = gm.etudid
        and gd.partition_id = p.id 
        and p.formsemestre_id = Isem.formsemestre_id
        """
        r = rq + " AND (" + " or ".join(rg) + " )"
        fromtables += ["group_membership gm", "group_descr gd", "partition p"]
    else:
        r = ""

    # requete complete
    req = (
        "SELECT distinct Im.etudid FROM "
        + ", ".join(fromtables)
        + """ WHERE Isem.etudid = Im.etudid
        and Im.moduleimpl_id = M.id 
        and Isem.formsemestre_id = M.formsemestre_id 
        and E.moduleimpl_id = M.id 
        and E.id = %(evaluation_id)s
        """
    )
    if not include_dems:
        req += " and Isem.etat='I'"
    req += r
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor()
    cursor.execute(req, {"evaluation_id": evaluation_id})
    return [x[0] for x in cursor]


def do_evaluation_listegroupes(evaluation_id, include_default=False):
    """Donne la liste des groupes dans lesquels figurent des etudiants inscrits
    au module/semestre auquel appartient cette evaluation.
    Si include_default, inclue aussi le groupe par defaut ('tous')
    [ group ]
    """
    if include_default:
        c = ""
    else:
        c = " AND p.partition_name is not NULL"
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor()
    cursor.execute(
        """SELECT DISTINCT gd.id AS group_id
        FROM group_descr gd, group_membership gm, partition p, 
             notes_moduleimpl m, notes_evaluation e
        WHERE gm.group_id = gd.id
        and gd.partition_id = p.id
        and p.formsemestre_id = m.formsemestre_id
        and m.id = e.moduleimpl_id
        and e.id = %(evaluation_id)s
        """
        + c,
        {"evaluation_id": evaluation_id},
    )
    group_ids = [x[0] for x in cursor]
    return listgroups(group_ids)


def listgroups(group_ids):
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    groups = []
    for group_id in group_ids:
        cursor.execute(
            """SELECT gd.id AS group_id, gd.*, p.id AS partition_id, p.*
            FROM group_descr gd, partition p
            WHERE p.id = gd.partition_id
            AND gd.id = %(group_id)s
            """,
            {"group_id": group_id},
        )
        r = cursor.dictfetchall()
        if r:
            groups.append(r[0])
    return _sortgroups(groups)


def _sortgroups(groups):
    # Tri: place 'all' en tête, puis groupe par partition / nom de groupe
    R = [g for g in groups if g["partition_name"] is None]
    o = [g for g in groups if g["partition_name"] != None]
    o.sort(key=lambda x: (x["numero"] or 0, x["group_name"]))

    return R + o


def listgroups_filename(groups):
    """Build a filename representing groups"""
    return "gr" + "+".join([g["group_name"] or "tous" for g in groups])


def listgroups_abbrev(groups):
    """Human readable abbreviation descring groups (eg "A / AB / B3")
    Ne retient que les partitions avec show_in_lists
    """
    return " / ".join(
        [g["group_name"] for g in groups if g["group_name"] and g["show_in_lists"]]
    )


# form_group_choice replaces formChoixGroupe
def form_group_choice(
    formsemestre_id,
    allow_none=True,  #  offre un choix vide dans chaque partition
    select_default=True,  # Le groupe par defaut est mentionné (hidden).
    display_sem_title=False,
):
    """Partie de formulaire pour le choix d'un ou plusieurs groupes.
    Variable : group_ids
    """
    from app.scodoc import sco_formsemestre

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if display_sem_title:
        sem_title = "%s: " % sem["titremois"]
    else:
        sem_title = ""
    #
    H = ["""<table>"""]
    for p in get_partitions_list(formsemestre_id):
        if p["partition_name"] is None:
            if select_default:
                H.append(
                    '<input type="hidden" name="group_ids:list" value="%s"/>'
                    % get_partition_groups(p)[0]["group_id"]
                )
        else:
            H.append("<tr><td>Groupe de %(partition_name)s</td><td>" % p)
            H.append('<select name="group_ids:list">')
            if allow_none:
                H.append('<option value="">aucun</option>')
            for group in get_partition_groups(p):
                H.append(
                    '<option value="%s">%s %s</option>'
                    % (group["group_id"], sem_title, group["group_name"])
                )
            H.append("</select></td></tr>")
    H.append("""</table>""")
    return "\n".join(H)


def make_query_groups(group_ids):
    if group_ids:
        return "&".join(["group_ids%3Alist=" + str(group_id) for group_id in group_ids])
    else:
        return ""


class GroupIdInferer(object):
    """Sert à retrouver l'id d'un groupe dans un semestre donné
    à partir de son nom.
    Attention: il peut y avoir plusieurs groupes de même nom
    dans des partitions différentes. Dans ce cas, prend le dernier listé.
    On peut indiquer la partition en écrivant
    partition_name:group_name
    """

    def __init__(self, formsemestre_id):
        groups = get_sem_groups(formsemestre_id)
        self.name2group_id = {}
        self.partitionname2group_id = {}
        for group in groups:
            self.name2group_id[group["group_name"]] = group["group_id"]
            self.partitionname2group_id[
                (group["partition_name"], group["group_name"])
            ] = group["group_id"]

    def __getitem__(self, name):
        """Get group_id from group_name, or None is nonexistent.
        The group name can be prefixed by the partition's name, using
        syntax partition_name:group_name
        """
        l = name.split(":", 1)
        if len(l) > 1:
            partition_name, group_name = l
        else:
            partition_name = None
            group_name = name
        if partition_name is None:
            group_id = self.name2group_id.get(group_name, None)
            if group_id is None and name[-2:] == ".0":
                # si nom groupe numerique, excel ajoute parfois ".0" !
                group_name = group_name[:-2]
                group_id = self.name2group_id.get(group_name, None)
        else:
            group_id = self.partitionname2group_id.get(
                (partition_name, group_name), None
            )
        return group_id
