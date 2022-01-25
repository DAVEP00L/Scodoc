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

"""Gestion des tags sur les modules

   Implementation expérimentale (Jul. 2016) pour grouper les modules sur
   les avis de poursuites d'études.


   Pour l'UI, voir https://goodies.pixabay.com/jquery/tag-editor/demo.html
"""
import http

from flask import g, url_for

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc import sco_cache
from app.scodoc import sco_edit_module
from app.scodoc import sco_etud
from app.scodoc.sco_exceptions import ScoValueError, AccessDenied
from app.scodoc.sco_permissions import Permission

# Opérations à implementer:
#  + liste des modules des formations de code donné (formation_code) avec ce tag
#  + liste de tous les noms de tag
#  + tag pour un nom
#  + creer un tag (nom)
#  + lier un tag à un module
#  + enlever un tag d'un module (si c'est le dernier, supprimer le tag lui même)
#
# API publiée:
#   module_tag_list_all  -> tous les noms d etags (pour l'autocomplete)
#   module_tag_list( module_id ) -> les noms de tags associés à ce module
#   module_tag_set( module_id, taglist ) -> modifie les tags


class ScoTag(object):
    """Generic tags for ScoDoc"""

    # must be overloaded:
    tag_table = None  # table (tag_id, title)
    assoc_table = None  # table (tag_id, object_id)
    obj_colname = None  # column name for object_id in assoc_table

    def __init__(self, title, object_id=""):
        """Load tag, or create if does not exist"""
        self.title = title.strip()
        if not self.title:
            raise ScoValueError("invalid empty tag")
        r = ndb.SimpleDictFetch(
            "SELECT id as tag_id, * FROM "
            + self.tag_table
            + " WHERE dept_id=%(dept_id)s AND title = %(title)s",
            {"dept_id": g.scodoc_dept_id, "title": self.title},
        )
        if r:
            self.tag_id = r[0]["tag_id"]
        else:
            # Create new tag:
            # log("creating new tag: %s" % self.title)
            cnx = ndb.GetDBConnexion()
            self.tag_id = ndb.DBInsertDict(
                cnx,
                self.tag_table,
                {"title": self.title, "dept_id": g.scodoc_dept_id},
                commit=True,
            )
        if object_id:
            self.tag_object(object_id)

    def __repr__(self):  # debug
        return '<tag "%s">' % self.title

    def delete(self):
        """Delete this tag.
        This object should not be used after this call !
        """
        args = {"tag_id": self.tag_id}
        ndb.SimpleQuery(
            "DELETE FROM " + self.tag_table + " t WHERE t.id = %(tag_id)s",
            args,
        )

    def tag_object(self, object_id):
        """Associate tag to given object"""
        args = {self.obj_colname: object_id, "tag_id": self.tag_id}
        r = ndb.SimpleDictFetch(
            "SELECT * FROM "
            + self.assoc_table
            + " a WHERE a."
            + self.obj_colname
            + " = %("
            + self.obj_colname
            + ")s AND a.tag_id = %(tag_id)s",
            args,
        )
        if not r:
            # log("tag %s with %s" % (object_id, self.title))
            cnx = ndb.GetDBConnexion()
            query = f"""INSERT INTO {self.assoc_table} 
                (tag_id, {self.obj_colname}) 
                VALUES"""
            ndb.SimpleQuery(
                query + " (%(tag_id)s, %(object_id)s)",
                {"tag_id": self.tag_id, "object_id": object_id},
            )
            cnx.commit()

    def remove_tag_from_object(self, object_id):
        """Remove tag from module.
        If no more modules tagged with this tag, delete it.
        Return True if Tag still exists.
        """
        # log("removing tag %s from %s" % (self.title, object_id))
        args = {"object_id": object_id, "tag_id": self.tag_id}
        ndb.SimpleQuery(
            "DELETE FROM  "
            + self.assoc_table
            + " a WHERE a."
            + self.obj_colname
            + " = %(object_id)s AND a.tag_id = %(tag_id)s",
            args,
        )
        r = ndb.SimpleDictFetch(
            """SELECT * FROM notes_modules_tags mt WHERE tag_id = %(tag_id)s
            """,
            args,
        )
        if not r:
            # tag no more used, delete
            ndb.SimpleQuery(
                """DELETE FROM notes_tags t WHERE t.id = %(tag_id)s""",
                args,
            )


class ModuleTag(ScoTag):
    """Tags sur les modules dans les programmes pédagogiques"""

    tag_table = "notes_tags"  # table (tag_id, title)
    assoc_table = "notes_modules_tags"  # table (tag_id, object_id)
    obj_colname = "module_id"  # column name for object_id in assoc_table

    def list_modules(self, formation_code=""):
        """Liste des modules des formations de code donné (formation_code) avec ce tag"""
        args = {"tag_id": self.tag_id}
        if not formation_code:
            # tous les modules de toutes les formations !
            r = ndb.SimpleDictFetch(
                "SELECT id AS"
                + self.obj_colname
                + " FROM "
                + self.assoc_table
                + " WHERE tag_id = %(tag_id)s",
                args,
            )
        else:
            args["formation_code"] = formation_code

            r = ndb.SimpleDictFetch(
                """SELECT mt.module_id 
                FROM notes_modules_tags mt, notes_modules m, notes_formations f
                WHERE mt.tag_id = %(tag_id)s
                AND m.id = mt.module_id
                AND m.formation_id = f.id
                AND f.formation_code = %(formation_code)s
                """,
                args,
            )
        return [x["module_id"] for x in r]


# API


def module_tag_search(term):
    """List all used tag names (for auto-completion)"""
    # restrict charset to avoid injections
    if not scu.ALPHANUM_EXP.match(term):
        data = []
    else:
        r = ndb.SimpleDictFetch(
            "SELECT title FROM notes_tags WHERE title LIKE %(term)s AND dept_id=%(dept_id)s",
            {
                "term": term + "%",
                "dept_id": g.scodoc_dept_id,
            },
        )
        data = [x["title"] for x in r]

    return scu.sendJSON(data)


def module_tag_list(module_id=""):
    """les noms de tags associés à ce module"""
    r = ndb.SimpleDictFetch(
        """SELECT t.title
          FROM notes_modules_tags mt, notes_tags t
          WHERE mt.tag_id = t.id
          AND mt.module_id = %(module_id)s
          """,
        {"module_id": module_id},
    )
    return [x["title"] for x in r]


def module_tag_set(module_id="", taglist=None):
    """taglist may either be:
    a string with tag names separated by commas ("un;deux")
    or a list of strings (["un", "deux"])
    """
    if not taglist:
        taglist = []
    elif isinstance(taglist, str):
        taglist = taglist.split(",")
    taglist = [t.strip() for t in taglist]
    # log("module_tag_set: module_id=%s taglist=%s" % (module_id, taglist))
    # Sanity check:
    Mod = sco_edit_module.module_list(args={"module_id": module_id})
    if not Mod:
        raise ScoValueError("invalid module !")

    newtags = set(taglist)
    oldtags = set(module_tag_list(module_id))
    to_del = oldtags - newtags
    to_add = newtags - oldtags

    # should be atomic, but it's not.
    for tagname in to_add:
        t = ModuleTag(tagname, object_id=module_id)
    for tagname in to_del:
        t = ModuleTag(tagname)
        t.remove_tag_from_object(module_id)

    return "", http.HTTPStatus.NO_CONTENT


def get_etud_tagged_modules(etudid, tagname):
    """Liste d'infos sur les modules de ce semestre avec ce tag.
    Cherche dans tous les semestres dans lesquel l'étudiant est ou a été inscrit.
    Construit la liste des modules avec le tag donné par tagname
    """
    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]
    R = []
    for sem in etud["sems"]:
        nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
        modimpls = nt.get_modimpls()
        for modimpl in modimpls:
            tags = module_tag_list(module_id=modimpl["module_id"])
            if tagname in tags:
                moy = nt.get_etud_mod_moy(
                    modimpl["moduleimpl_id"], etudid
                )  # ou NI si non inscrit
                R.append(
                    {
                        "sem": sem,
                        "moy": moy,  # valeur réelle, ou NI (non inscrit au module ou NA (pas de note)
                        "moduleimpl": modimpl,
                        "tags": tags,
                    }
                )
    return R


def split_tagname_coeff(tag, separateur=":"):
    """Découpe un tag saisi par un utilisateur pour en extraire un tagname
    (chaine de caractère correspondant au tag)
    et un éventuel coefficient de pondération, avec le séparateur fourni (par défaut ":").
    Renvoie le résultat sous la forme d'une liste [tagname, pond] où pond est un float

    Auteur: CB
    """
    if separateur in tag:
        temp = tag.split(":")
        try:
            pond = float(temp[1])
            return [temp[0], pond]
        except:
            return [tag, 1.0]  # renvoie tout le tag si le découpage à échouer
    else:
        # initialise le coeff de pondération à 1 lorsqu'aucun coeff de pondération n'est indiqué dans le tag
        return [tag, 1.0]


"""Tests:
from debug import *
from app.scodoc.sco_tag_module import *
_ = go_dept(app, 'RT').Notes

t = ModuleTag( 'essai')
t.tag_module('totoro') # error (module invalide)
t.tag_module('MOD21460')
t.delete() # detruit tag et assoc
t = ModuleTag( 'essai2')
t.tag_module('MOD21460')
t.tag_module('MOD21464')
t.list_modules()
t.list_modules(formation_code='ccc') # empty list
t.list_modules(formation_code='FCOD2')


Un essai de get_etud_tagged_modules:
from debug import *
from app.scodoc.sco_tag_module import *
_ = go_dept(app, 'GEA').Notes

etudid='GEAEID80687'
etud = sco_etud.get_etud_info( etudid=etudid, filled=True)[0]
sem = etud['sems'][0]

[ tm['moy'] for tm in get_etud_tagged_modules( etudid, 'allo') ]

# si besoin après modif par le Web:
# sco_cache.invalidate_formsemestre()
"""
