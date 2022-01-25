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

"""Gestion des caches

  Ré-écrite pour ScoDoc8, utilise flask_caching et REDIS

  ScoDoc est maintenant multiprocessus / mono-thread, avec un cache en mémoire partagé.
"""


# API ScoDoc8 pour les caches:
#  sco_cache.NotesTableCache.get( formsemestre_id)
#   => sco_cache.NotesTableCache.get(formsemestre_id)
#
#  sco_core.inval_cache(formsemestre_id=None, pdfonly=False, formsemestre_id_list=None)
#   => deprecated, NotesTableCache.invalidate_formsemestre(formsemestre_id=None, pdfonly=False)
#
#
# Nouvelles fonctions:
#  sco_cache.NotesTableCache.delete(formsemestre_id)
#  sco_cache.NotesTableCache.delete_many(formsemestre_id_list)
#
# Bulletins PDF:
#  sco_cache.SemBulletinsPDFCache.get(formsemestre_id, version)
#  sco_cache.SemBulletinsPDFCache.set(formsemestre_id, version, filename, pdfdoc)
#  sco_cache.SemBulletinsPDFCache.delete(formsemestre_id) suppr. toutes les versions

# Evaluations:
#  sco_cache.EvaluationCache.get(evaluation_id), set(evaluation_id, value), delete(evaluation_id),
#

import time
import traceback

from flask import g

from app.scodoc import notesdb as ndb
from app.scodoc import sco_utils as scu
from app import log

CACHE = None  # set in app.__init__.py


class ScoDocCache:
    """Cache for ScoDoc objects.
    keys are prefixed by the current departement.
    """

    timeout = None  # ttl, infinite by default
    prefix = ""

    @classmethod
    def _get_key(cls, oid):
        return g.scodoc_dept + "_" + cls.prefix + "_" + str(oid)

    @classmethod
    def get(cls, oid):
        """Returns cached object, or None"""
        key = cls._get_key(oid)
        try:
            return CACHE.get(key)
        except:
            log(f"XXX CACHE Warning: error in get(key={key})")
            log(traceback.format_exc())
            return None

    @classmethod
    def set(cls, oid, value):
        """Store value"""
        key = cls._get_key(oid)
        # log(f"CACHE key={key}, type={type(value)}, timeout={cls.timeout}")
        try:
            status = CACHE.set(key, value, timeout=cls.timeout)
            if not status:
                log("Error: cache set failed !")
        except:
            log("XXX CACHE Warning: error in set !!!")
            status = None
        return status

    @classmethod
    def delete(cls, oid):
        """Remove from cache"""
        CACHE.delete(cls._get_key(oid))

    @classmethod
    def delete_many(cls, oids):
        """Remove multiple keys at once"""
        # delete_many seems bugged:
        # CACHE.delete_many([cls._get_key(oid) for oid in oids])
        for oid in oids:
            cls.delete(oid)


class EvaluationCache(ScoDocCache):
    """Cache for evaluations.
    Clé: evaluation_id
    Valeur: { 'etudid' : note }
    """

    prefix = "EVAL"

    @classmethod
    def invalidate_sem(cls, formsemestre_id):
        "delete evaluations in this formsemestre from cache"
        req = """SELECT e.id
        FROM notes_formsemestre s, notes_evaluation e, notes_moduleimpl m 
        WHERE s.id = %(formsemestre_id)s and s.id=m.formsemestre_id and e.moduleimpl_id=m.id;
        """
        evaluation_ids = [
            x[0] for x in ndb.SimpleQuery(req, {"formsemestre_id": formsemestre_id})
        ]
        cls.delete_many(evaluation_ids)

    @classmethod
    def invalidate_all_sems(cls):
        "delete all evaluations in current dept from cache"
        evaluation_ids = [
            x[0]
            for x in ndb.SimpleQuery(
                """SELECT e.id
                FROM notes_evaluation e, notes_moduleimpl mi, notes_formsemestre s
                WHERE s.dept_id=%(dept_id)s
                AND s.id = mi.formsemestre_id
                AND mi.id = e.moduleimpl_id;
                """,
                {"dept_id": g.scodoc_dept_id},
            )
        ]
        cls.delete_many(evaluation_ids)


class AbsSemEtudCache(ScoDocCache):
    """Cache pour les comptes d'absences d'un étudiant dans un semestre.
    Ce cache étant indépendant des semestres, le compte peut être faux lorsqu'on
    change les dates début/fin d'un semestre.
    C'est pourquoi il expire après timeout secondes.
    Le timeout evite aussi d'éliminer explicitement ces éléments cachés lors
    des suppressions d'étudiants ou de semestres.
    Clé: etudid + "_" + date_debut + "_" + date_fin
    Valeur: (nb_abs, nb_abs_just)
    """

    prefix = "ABSE"
    timeout = 60 * 60  # ttl 60 minutes


class SemBulletinsPDFCache(ScoDocCache):
    """Cache pour les classeurs de bulletins PDF d'un semestre.
    Document pdf assez volumineux. La clé inclut le type de bulletin (version).
    Clé: formsemestre_id_version
    Valeur: (filename, pdfdoc)
    """

    prefix = "SBPDF"
    timeout = 12 * 60 * 60  # ttl 12h

    @classmethod
    def invalidate_sems(cls, formsemestre_ids):
        """Clear cached pdf for all given formsemestres"""
        for version in scu.BULLETINS_VERSIONS:
            oids = [
                str(formsemestre_id) + "_" + version
                for formsemestre_id in formsemestre_ids
            ]
            cls.delete_many(oids)


class SemInscriptionsCache(ScoDocCache):
    """Cache les inscriptions à un semestre.
    Clé: formsemestre_id
    Valeur: liste d'inscriptions
    [ {'formsemestre_inscription_id': 'SI78677', 'etudid': '1234', 'formsemestre_id': 'SEM012', 'etat': 'I', 'etape': ''}, ... ]
    """

    prefix = "SI"
    duration = 12 * 60 * 60  # ttl 12h


class NotesTableCache(ScoDocCache):
    """Cache pour les NotesTable
    Clé: formsemestre_id
    Valeur: NotesTable instance
    """

    prefix = "NT"

    @classmethod
    def get(cls, formsemestre_id, compute=True):
        """Returns NotesTable for this formsemestre
        Search in local cache (g.nt_cache) or global app cache (eg REDIS)
        If not in cache and compute is True, build it and cache it.
        """
        # try local cache (same request)
        if not hasattr(g, "nt_cache"):
            g.nt_cache = {}
        else:
            if formsemestre_id in g.nt_cache:
                return g.nt_cache[formsemestre_id]
        # try REDIS
        key = cls._get_key(formsemestre_id)
        nt = CACHE.get(key)
        if nt:
            g.nt_cache[formsemestre_id] = nt  # cache locally (same request)
            return nt
        if not compute:
            return None
        # Recompute requested table:
        from app.scodoc import notes_table

        t0 = time.time()
        nt = notes_table.NotesTable(formsemestre_id)
        t1 = time.time()
        _ = cls.set(formsemestre_id, nt)  # cache in REDIS
        t2 = time.time()
        log(f"cached formsemestre_id={formsemestre_id} ({(t1-t0):g}s +{(t2-t1):g}s)")
        g.nt_cache[formsemestre_id] = nt
        return nt


def invalidate_formsemestre(  # was inval_cache(formsemestre_id=None, pdfonly=False)
    formsemestre_id=None, pdfonly=False
):
    """expire cache pour un semestre (ou tous si formsemestre_id non spécifié).
    Si pdfonly, n'expire que les bulletins pdf cachés.
    """
    from app.scodoc import sco_parcours_dut

    if getattr(g, "defer_cache_invalidation", False):
        g.sem_to_invalidate.add(formsemestre_id)
        return
    log("inval_cache, formsemestre_id=%s pdfonly=%s" % (formsemestre_id, pdfonly))
    if formsemestre_id is None:
        # clear all caches
        log("----- invalidate_formsemestre: clearing all caches -----")
        formsemestre_ids = [
            x[0]
            for x in ndb.SimpleQuery(
                """SELECT id FROM notes_formsemestre s
                WHERE s.dept_id=%(dept_id)s
            """,
                {"dept_id": g.scodoc_dept_id},
            )
        ]
    else:
        formsemestre_ids = [
            formsemestre_id
        ] + sco_parcours_dut.list_formsemestre_utilisateurs_uecap(formsemestre_id)
        log(f"----- invalidate_formsemestre: clearing {formsemestre_ids} -----")

    if not pdfonly:
        # Delete cached notes and evaluations
        NotesTableCache.delete_many(formsemestre_ids)
        if formsemestre_id:
            for fid in formsemestre_ids:
                EvaluationCache.invalidate_sem(fid)
                if hasattr(g, "nt_cache") and fid in g.nt_cache:
                    del g.nt_cache[fid]
        else:
            # optimization when we invalidate all evaluations:
            EvaluationCache.invalidate_all_sems()
            if hasattr(g, "nt_cache"):
                del g.nt_cache
        SemInscriptionsCache.delete_many(formsemestre_ids)

    SemBulletinsPDFCache.invalidate_sems(formsemestre_ids)


class DefferedSemCacheManager:
    """Contexte pour effectuer des opérations indépendantes dans la
    même requete qui invalident le cache. Par exemple, quand on inscrit
    des étudiants un par un à un semestre, chaque inscription va invalider
    le cache, et la suivante va le reconstruire... pour l'invalider juste après.
    Ce context manager permet de grouper les invalidations.
    """

    def __enter__(self):
        assert not hasattr(g, "defer_cache_invalidation")
        g.defer_cache_invalidation = True
        g.sem_to_invalidate = set()
        return True

    def __exit__(self, exc_type, exc_value, exc_traceback):
        assert g.defer_cache_invalidation
        g.defer_cache_invalidation = False
        while g.sem_to_invalidate:
            formsemestre_id = g.sem_to_invalidate.pop()
            invalidate_formsemestre(formsemestre_id)
