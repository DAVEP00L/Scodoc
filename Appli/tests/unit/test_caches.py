# -*- coding: UTF-8 -*

"""Unit tests for caches


Ce test suppose une base département existante.

Usage: pytest tests/unit/test_caches.py
"""


from flask import current_app, g

import app
from app import db
from app.scodoc import sco_cache
from app.scodoc import sco_evaluations
from app.scodoc import sco_formsemestre
from app.scodoc import notesdb as ndb
from config import TestConfig
from tests.unit.test_sco_basic import run_sco_basic

DEPT = TestConfig.DEPT_TEST


def test_notes_table(test_client):
    """Test construction et cache de NotesTable."""
    app.set_sco_dept(DEPT)
    assert g.scodoc_dept == DEPT
    # prépare le département avec quelques semestres:
    run_sco_basic()
    #
    sems = sco_formsemestre.do_formsemestre_list()
    assert len(sems)
    sem = sems[0]
    formsemestre_id = sem["formsemestre_id"]
    nt = sco_cache.NotesTableCache.get(formsemestre_id)
    assert nt
    assert sco_cache.NotesTableCache.get(formsemestre_id, compute=False)
    sco_cache.invalidate_formsemestre(formsemestre_id)
    assert not sco_cache.NotesTableCache.get(formsemestre_id, compute=False)
    # cache les 10 premiers
    for sem in sems[:10]:
        formsemestre_id = sem["formsemestre_id"]
        nt = sco_cache.NotesTableCache.get(formsemestre_id)
        assert sco_cache.NotesTableCache.get(formsemestre_id, compute=False)


def test_cache_evaluations(test_client):
    """"""
    # cherche un semestre ayant des evaluations
    app.set_sco_dept(DEPT)
    # prépare le département avec quelques semestres:
    run_sco_basic()
    #
    sems = sco_formsemestre.do_formsemestre_list()
    assert len(sems)
    sem_evals = []
    for sem in sems:
        sem_evals = sco_evaluations.do_evaluation_list_in_sem(
            sem["formsemestre_id"], with_etat=False
        )
        if sem_evals:
            break
    if not sem_evals:
        raise Exception("no evaluations")
    #
    evaluation_id = sem_evals[0]["evaluation_id"]
    eval_notes = sco_evaluations.do_evaluation_get_all_notes(evaluation_id)
    # should have been be cached, except if empty
    if eval_notes:
        assert sco_cache.EvaluationCache.get(evaluation_id)
    sco_cache.invalidate_formsemestre(sem["formsemestre_id"])
    # should have been erased from cache:
    assert not sco_cache.EvaluationCache.get(evaluation_id)
