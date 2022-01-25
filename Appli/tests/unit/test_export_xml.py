# -*- coding: UTF-8 -*

"""Unit tests for XML exports

Usage: pytest tests/unit/test_export_xml.py
"""

# ScoDoc7 utilisait jaxml, obsolete et non portée en python3
# On teste ici les fonctions de remplacement, fournies par
# notre nouveau module sco_xml.py

import os
import re
import sys
import unittest

from app.scodoc import sco_xml
from app.scodoc.gen_tables import GenTable

# Legacy function
# import jaxml
# from app.scodoc import sco_utils as scu

# r = scu.simple_dictlist2xml([{"id": 1, "ues": [{"note": 10}, {}]}], tagname="infos")


def xml_normalize(x):
    "supprime espaces inutiles"
    x = re.sub(r"\s+", " ", str(x)).strip().replace("> <", "><")


def xmls_compare(x, y):
    return xml_normalize(x) == xml_normalize(y)


def test_export_xml(test_client):
    """exports XML compatibles ScoDoc 7"""
    # expected_result est le résultat de l'ancienne fonction ScoDoc7:
    for (data, expected_result) in (
        (
            [{"id": 1, "ues": [{"note": 10}, {}, {"valeur": 25}]}, {"bis": 2}],
            """<?xml version="1.0" encoding="utf-8"?>
    <infos id="1">
        <ues note="10" />
        <ues />
        <ues valeur="25" />
    </infos>
    <infos bis="2" />
    """,
        ),
        ([], """"""),
        (
            ["allo"],
            """<?xml version="1.0" encoding="utf-8"?>
    <infos code="allo" />
    """,
        ),
        (
            [{}],
            """<?xml version="1.0" encoding="utf-8"?>
    <infos />
    """,
        ),
        (
            [{"x": 1}],
            """<?xml version="1.0" encoding="utf-8"?>
    <infos x="1" />
    """,
        ),
        (
            [{"y": [1, 2, 3], "x": 1}],
            """<?xml version="1.0" encoding="utf-8"?>
    <infos x="1">
        <y code="1" />
        <y code="2" />
        <y code="3" />
    </infos>
    """,
        ),
        (
            [{"y": [{"x": 1}, {"y": [1, 2, 3]}], "x": 1}],
            """<?xml version="1.0" encoding="utf-8"?>
    <infos x="1">
        <y x="1" />
        <y>
            <y code="1" />
            <y code="2" />
            <y code="3" />
        </y>
    </infos>
    """,
        ),
    ):
        # x = scu.simple_dictlist2xml(data, tagname="infos")
        y = sco_xml.simple_dictlist2xml(data, tagname="infos")
        assert xmls_compare(expected_result, y)
        # print("""({}, '''{}'''),""".format(data, str(x)))

    # test du sendXML compatible ScoDoc7
    etuds = [{"x": 1, "etuds": ["allo", "mama"]}, {"x": 2, "etuds": ["un", "deux"]}]
    # Le résultat de l'ancien print(sendXML(etuds, tagname="etudiants"))
    expected_result = """
    <?xml version="1.0" encoding="utf-8"?>
    <etudiants_list>
        <etudiants x="1">
            <etuds code="allo" />
            <etuds code="mama" />
        </etudiants>
        <etudiants x="2">
            <etuds code="un" />
            <etuds code="deux" />
        </etudiants>
    </etudiants_list>
    """

    assert xmls_compare(
        expected_result,
        sco_xml.simple_dictlist2xml([{"etudiant": etuds}], tagname="etudiant_list"),
    )

    # ---- Tables
    table = GenTable(
        rows=[{"nom": "Toto", "age": 26}, {"nom": "Titi", "age": 21}],
        columns_ids=("nom", "age"),
    )
    table_xml = table.xml()

    expected_result = """
    <?xml version="1.0" encoding="utf-8"?>
    <table origin="" caption="" id="gt_806883">
        <row>
            <nom value="Toto" />
            <age value="26" />
        </row>
        <row>
            <nom value="Titi" />
            <age value="21" />
        </row>
    </table>
    """
    assert xmls_compare(table_xml, expected_result)