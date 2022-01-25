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

"""Comparaison de deux fichiers Apogée (maquettes)

1) Vérifier:
etape_apogee, vdi_apogee, cod_dip_apogee, annee_scolaire
structure: col_ids (la comparaison portera sur les colonnes communes)


2) Comparer listes d'étudiants
 Présents dans A mais pas dans B
 Présents dans B mais pas dans A
 nombre communs

3) Comparer résultats
Pour chaque étudiant commun:
 Pour chaque colonne commune:
    comparer les résultats

"""

from app import log
from app.scodoc import sco_apogee_csv
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc import html_sco_header
from app.scodoc import sco_preferences

_help_txt = """
<div class="help">
<p>Outil de comparaison de fichiers (maquettes CSV) Apogée.
</p>
<p>Cet outil compare deux fichiers fournis. Aucune donnée stockée dans ScoDoc n'est utilisée.
</p>
</div>
"""


def apo_compare_csv_form():
    """Form: submit 2 CSV files to compare them."""
    H = [
        html_sco_header.sco_header(page_title="Comparaison de fichiers Apogée"),
        """<h2>Comparaison de fichiers Apogée</h2>
        <form id="apo_csv_add" action="apo_compare_csv" method="post" enctype="multipart/form-data">
        """,
        _help_txt,
        """
        <div class="apo_compare_csv_form_but">
        Fichier Apogée A: 
        <input type="file" size="30" name="A_file"/>
        </div>
        <div class="apo_compare_csv_form_but">
        Fichier Apogée B: 
        <input type="file" size="30" name="B_file"/>
        </div>
        <input type="checkbox" name="autodetect" checked/>autodétecter encodage</input>
        <div class="apo_compare_csv_form_submit">
        <input type="submit" value="Comparer ces fichiers"/>
        </div>
        </form>""",
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def apo_compare_csv(A_file, B_file, autodetect=True):
    """Page comparing 2 Apogee CSV files"""
    A = _load_apo_data(A_file, autodetect=autodetect)
    B = _load_apo_data(B_file, autodetect=autodetect)

    H = [
        html_sco_header.sco_header(page_title="Comparaison de fichiers Apogée"),
        "<h2>Comparaison de fichiers Apogée</h2>",
        _help_txt,
        '<div class="apo_compare_csv">',
        _apo_compare_csv(A, B),
        "</div>",
        """<p><a href="apo_compare_csv_form" class="stdlink">Autre comparaison</a></p>""",
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def _load_apo_data(csvfile, autodetect=True):
    "Read data from request variable and build ApoData"
    data = csvfile.read()
    if autodetect:
        data, message = sco_apogee_csv.fix_data_encoding(data)
        if message:
            log("apo_compare_csv: %s" % message)
        if not data:
            raise ScoValueError("apo_compare_csv: no data")
    apo_data = sco_apogee_csv.ApoData(data, orig_filename=csvfile.filename)
    return apo_data


def _apo_compare_csv(A, B):
    """Generate html report comparing A and B, two instances of ApoData
    representing Apogee CSV maquettes.
    """
    L = []
    # 1-- Check etape and codes
    L.append('<div class="section"><div class="tit">En-tête</div>')
    L.append('<div><span class="key">Nom fichier A:</span><span class="val_ok">')
    L.append(A.orig_filename)
    L.append("</span></div>")
    L.append('<div><span class="key">Nom fichier B:</span><span class="val_ok">')
    L.append(B.orig_filename)
    L.append("</span></div>")
    L.append('<div><span class="key">Étape Apogée:</span>')
    if A.etape_apogee != B.etape_apogee:
        L.append(
            '<span class="val_dif">%s != %s</span>' % (A.etape_apogee, B.etape_apogee)
        )
    else:
        L.append('<span class="val_ok">%s</span>' % (A.etape_apogee,))
    L.append("</div>")

    L.append('<div><span class="key">VDI Apogée:</span>')
    if A.vdi_apogee != B.vdi_apogee:
        L.append('<span class="val_dif">%s != %s</span>' % (A.vdi_apogee, B.vdi_apogee))
    else:
        L.append('<span class="val_ok">%s</span>' % (A.vdi_apogee,))
    L.append("</div>")

    L.append('<div><span class="key">Code diplôme :</span>')
    if A.cod_dip_apogee != B.cod_dip_apogee:
        L.append(
            '<span class="val_dif">%s != %s</span>'
            % (A.cod_dip_apogee, B.cod_dip_apogee)
        )
    else:
        L.append('<span class="val_ok">%s</span>' % (A.cod_dip_apogee,))
    L.append("</div>")

    L.append('<div><span class="key">Année scolaire :</span>')
    if A.annee_scolaire != B.annee_scolaire:
        L.append(
            '<span class="val_dif">%s != %s</span>'
            % (A.annee_scolaire, B.annee_scolaire)
        )
    else:
        L.append('<span class="val_ok">%s</span>' % (A.annee_scolaire,))
    L.append("</div>")

    # Colonnes:
    A_elts = set(A.apo_elts.keys())
    B_elts = set(B.apo_elts.keys())
    L.append('<div><span class="key">Éléments Apogée :</span>')
    if A_elts == B_elts:
        L.append('<span class="val_ok">%d</span>' % len(A_elts))
    else:
        elts_communs = A_elts.intersection(B_elts)
        elts_only_A = A_elts - A_elts.intersection(B_elts)
        elts_only_B = B_elts - A_elts.intersection(B_elts)
        L.append(
            '<span class="val_dif">différents (%d en commun, %d seulement dans A, %d seulement dans B)</span>'
            % (
                len(elts_communs),
                len(elts_only_A),
                len(elts_only_B),
            )
        )
        if elts_only_A:
            L.append(
                '<div span class="key">Éléments seulement dans A : </span><span class="val_dif">%s</span></div>'
                % ", ".join(sorted(elts_only_A))
            )
        if elts_only_B:
            L.append(
                '<div span class="key">Éléments seulement dans B : </span><span class="val_dif">%s</span></div>'
                % ", ".join(sorted(elts_only_B))
            )
    L.append("</div>")
    L.append("</div>")  # /section

    # 2--
    L.append('<div class="section"><div class="tit">Étudiants</div>')

    A_nips = set(A.etud_by_nip)
    B_nips = set(B.etud_by_nip)
    nb_etuds_communs = len(A_nips.intersection(B_nips))
    nb_etuds_dif = len(A_nips.union(B_nips) - A_nips.intersection(B_nips))
    L.append("""<div><span class="key">Liste d'étudiants :</span>""")
    if A_nips == B_nips:
        L.append(
            """<span class="s_ok">
        %d étudiants (tous présents dans chaque fichier)</span>
        """
            % len(A_nips)
        )
    else:
        L.append(
            '<span class="val_dif">différents (%d en commun, %d différents)</span>'
            % (nb_etuds_communs, nb_etuds_dif)
        )
    L.append("</div>")
    L.append("</div>")  # /section

    # 3-- Résultats de chaque étudiant:
    if nb_etuds_communs > 0:
        L.append(
            """<div class="section sec_table">
        <div class="tit">Différences de résultats des étudiants présents dans les deux fichiers</div>
        <p>
        """
        )
        T = apo_table_compare_etud_results(A, B)
        if T.get_nb_rows() > 0:
            L.append(T.html())
        else:
            L.append(
                """<p class="p_ok">aucune différence de résultats 
            sur les %d étudiants communs (<em>les éléments Apogée n'apparaissant pas dans les deux fichiers sont omis</em>)</p>
            """
                % nb_etuds_communs
            )
        L.append("</div>")  # /section

    return "\n".join(L)


def apo_table_compare_etud_results(A, B):
    """"""
    D = compare_etuds_res(A, B)
    T = GenTable(
        rows=D,
        titles={
            "nip": "NIP",
            "nom": "Nom",
            "prenom": "Prénom",
            "elt_code": "Element",
            "type_res": "Type",
            "val_A": "A: %s" % A.orig_filename or "",
            "val_B": "B: %s" % B.orig_filename or "",
        },
        columns_ids=("nip", "nom", "prenom", "elt_code", "type_res", "val_A", "val_B"),
        html_class="table_leftalign",
        html_with_td_classes=True,
        preferences=sco_preferences.SemPreferences(),
    )
    return T


def _build_etud_res(e, apo_data):
    r = {}
    for elt_code in apo_data.apo_elts:
        elt = apo_data.apo_elts[elt_code]
        col_ids_type = [
            (ec["apoL_a01_code"], ec["Type R\xc3\xa9s."]) for ec in elt.cols
        ]  # les colonnes de cet élément
        r[elt_code] = {}
        for (col_id, type_res) in col_ids_type:
            r[elt_code][type_res] = e.cols[col_id]
    return r


def compare_etud_res(r_A, r_B, remove_missing=True):
    """Pour chaque valeur difference dans les resultats d'un etudiant
    elt_code   type_res   val_A     val_B
    """
    diffs = []
    elt_codes = set(r_A).union(set(r_B))
    for elt_code in elt_codes:
        for type_res in r_A.get(elt_code, r_B.get(elt_code)):
            if elt_code not in r_A:
                if remove_missing:
                    continue
                else:
                    val_A = None  # element absent
            else:
                val_A = r_A[elt_code][type_res]
            if elt_code not in r_B:
                if remove_missing:
                    continue
                else:
                    val_B = None  # element absent
            else:
                val_B = r_B[elt_code][type_res]
            if type_res == "N":
                # Cas particulier pour les notes: compare les nombres
                try:
                    val_A_num = float(val_A.replace(",", "."))
                    val_B_num = float(val_B.replace(",", "."))
                except ValueError:
                    val_A_num, val_B_num = val_A, val_B
                val_A, val_B = val_A_num, val_B_num
            if val_A != val_B:
                diffs.append(
                    {
                        "elt_code": elt_code,
                        "type_res": type_res,
                        "val_A": val_A,
                        "val_B": val_B,
                    }
                )
    return diffs


def compare_etuds_res(A, B):
    """
    nip, nom, prenom, elt_code, type_res, val_A, val_B
    """
    A_nips = set(A.etud_by_nip)
    B_nips = set(B.etud_by_nip)
    common_nips = A_nips.intersection(B_nips)
    # A_not_B_nips = A_nips - B_nips
    # B_not_A_nips = B_nips - A_nips
    D = []
    for nip in common_nips:
        etu_A = A.etud_by_nip[nip]
        etu_B = B.etud_by_nip[nip]
        r_A = _build_etud_res(etu_A, A)
        r_B = _build_etud_res(etu_B, B)
        diffs = compare_etud_res(r_A, r_B)
        for d in diffs:
            d.update(
                {"nip": etu_A["nip"], "nom": etu_A["nom"], "prenom": etu_A["prenom"]}
            )
            D.append(d)
    return D
