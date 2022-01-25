# -*- coding: UTF-8 -*

"""Unit tests for pydot

Ce test vérifie que le module pydot est compatible avec notre code.
(pydot a souyvent été buggué)

Usage: pytest tests/unit/test_pydot.py
"""

import pydot
from app.scodoc import sco_utils as scu


def test_pydot(test_client):
    g = pydot.Dot("graphname")
    g.add_node(pydot.Node("a"))
    g.add_node(pydot.Node("b"))
    n = g.get_node("a")
    assert isinstance(n, list)
    assert len(n) == 1
    assert [x.get_name() for x in g.get_node_list()] == ["a", "b"]
    #
    edges = [("a", "b"), ("b", "c"), ("c", "d")]
    g = scu.graph_from_edges(edges)
    assert len(g.get_node_list()) == 4
    n = g.get_node("d")[0]
    n.set_fontname("Helvetica")
    n.set_fontsize(8.0)
    n.set("label", "toto")
    assert "fontname=Helvetica" in g.to_string()
    assert "toto" in g.to_string()
