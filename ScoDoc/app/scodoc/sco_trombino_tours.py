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

"""Photos: trombinoscopes - Version IUT Tours
   Code contribué par Jérôme Billoue, IUT de Tours, 2014
   Modification Jérome Billoue,Vincent Grimaud, IUT de Tours, 2017
"""

import io

from reportlab.lib import colors
from reportlab.lib import pagesizes
from reportlab.lib.pagesizes import A4, A3

import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import sco_abs
from app.scodoc import sco_groups
from app.scodoc import sco_groups_view
from app.scodoc import sco_preferences
from app.scodoc import sco_trombino
from app.scodoc import sco_etud
from app.scodoc.sco_pdf import *


# Paramétrage de l'aspect graphique:
PHOTOWIDTH = 2.8 * cm
COLWIDTH = 3.4 * cm
N_PER_ROW = 5


def pdf_trombino_tours(
    group_ids=[],  # liste des groupes à afficher
    formsemestre_id=None,  # utilisé si pas de groupes selectionné
):
    """Generation du trombinoscope en fichier PDF"""
    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, formsemestre_id=formsemestre_id
    )

    DeptName = sco_preferences.get_preference("DeptName")
    DeptFullName = sco_preferences.get_preference("DeptFullName")
    UnivName = sco_preferences.get_preference("UnivName")
    InstituteName = sco_preferences.get_preference("InstituteName")
    # Generate PDF page
    StyleSheet = styles.getSampleStyleSheet()
    objects = []
    T = Table(
        [
            [Paragraph(SU(InstituteName), StyleSheet["Heading3"])],
            [Paragraph(SU("Département " + DeptFullName), StyleSheet["Heading3"])],
            [
                Paragraph(
                    SU("Date ............ / ............ / ......................"),
                    StyleSheet["Normal"],
                ),
                Paragraph(
                    SU(
                        "Module ......................................................."
                    ),
                    StyleSheet["Normal"],
                ),
            ],
            [
                Paragraph(
                    SU("de ............h............ à ............h............ "),
                    StyleSheet["Normal"],
                ),
                Paragraph(
                    SU("Enseignant ................................................."),
                    StyleSheet["Normal"],
                ),
            ],
            [
                Table(
                    [
                        [
                            "Séance notée :",
                            " ",
                            "DS   ",
                            " ",
                            "TP Contrôle   ",
                            " ",
                            "Autre cas (TD ou TP noté, QCM, etc...)",
                        ]
                    ],
                    style=TableStyle(
                        [
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("BOX", (1, 0), (1, 0), 0.75, black),
                            ("BOX", (3, 0), (3, 0), 0.75, black),
                            ("BOX", (5, 0), (5, 0), 0.75, black),
                        ]
                    ),
                )
            ],
        ],
        colWidths=(COLWIDTH * N_PER_ROW) / 2,
        style=TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (0, 4), (1, 4)),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.75, black),
            ]
        ),
    )

    objects.append(T)

    groups = ""

    for group_id in groups_infos.group_ids:
        if group_id != "None":
            members, group, group_tit, sem, nbdem = sco_groups.get_group_infos(
                group_id, "I"
            )
            groups += " %s" % group_tit
            L = []
            currow = []

            if sem["semestre_id"] != -1:
                currow = [
                    Paragraph(
                        SU(
                            "<para align=center>Semestre %s</para>" % sem["semestre_id"]
                        ),
                        StyleSheet["Normal"],
                    )
                ]
            currow += [" "] * (N_PER_ROW - len(currow) - 1)
            currow += [
                Paragraph(
                    SU("<para align=center>%s</para>" % sem["anneescolaire"]),
                    StyleSheet["Normal"],
                )
            ]
            L.append(currow)
            currow = [" "] * N_PER_ROW
            L.append(currow)

            currow = []
            currow.append(
                Paragraph(
                    SU("<para align=center><b>" + group_tit + "</b></para>"),
                    StyleSheet["Heading3"],
                )
            )
            n = 1
            for m in members:
                img = sco_trombino._get_etud_platypus_image(m, image_width=PHOTOWIDTH)
                etud_main_group = sco_groups.get_etud_main_group(m["etudid"], sem)
                if group_id != etud_main_group["group_id"]:
                    text_group = " (" + etud_main_group["group_name"] + ")"
                else:
                    text_group = ""
                elem = Table(
                    [
                        [img],
                        [
                            Paragraph(
                                SU(
                                    "<para align=center><font size=8>"
                                    + sco_etud.format_prenom(m["prenom"])
                                    + " "
                                    + sco_etud.format_nom(m["nom"])
                                    + text_group
                                    + "</font></para>"
                                ),
                                StyleSheet["Normal"],
                            )
                        ],
                    ],
                    colWidths=[COLWIDTH],
                    style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]),
                )
                currow.append(elem)
                if n == (N_PER_ROW - 1):
                    L.append(currow)
                    currow = []
                n = (n + 1) % N_PER_ROW
            if currow:
                currow += [" "] * (N_PER_ROW - len(currow))
                L.append(currow)
            if not L:
                T = Paragraph(SU("Aucune photo à exporter !"), StyleSheet["Normal"])
            else:
                T = Table(
                    L,
                    colWidths=[COLWIDTH] * N_PER_ROW,
                    style=TableStyle(
                        [
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 1), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, 0), 10),
                            ("LINEBELOW", (1, 0), (-2, 0), 0.75, black),
                            ("VALIGN", (0, 0), (-1, 1), "MIDDLE"),
                            ("VALIGN", (0, 2), (-1, -1), "TOP"),
                            ("VALIGN", (0, 2), (0, 2), "MIDDLE"),
                            ("SPAN", (0, 0), (0, 1)),
                            ("SPAN", (-1, 0), (-1, 1)),
                        ]
                    ),
                )

            objects.append(T)

    T = Table(
        [
            [
                Paragraph(
                    SU(
                        "Nombre d'absents : ................. (Merci d'entourer les absents SVP)"
                    ),
                    StyleSheet["Normal"],
                )
            ]
        ],
        colWidths=(COLWIDTH * N_PER_ROW),
        style=TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 0.75, black),
            ]
        ),
    )

    objects.append(T)

    # Réduit sur une page
    objects = [KeepInFrame(0, 0, objects, mode="shrink")]
    # Build document
    report = io.BytesIO()  # in-memory document, no disk file
    filename = "trombino-%s-%s.pdf" % (DeptName, groups_infos.groups_filename)
    document = BaseDocTemplate(report)
    document.addPageTemplates(
        ScolarsPageTemplate(
            document,
            preferences=sco_preferences.SemPreferences(),
        )
    )
    document.build(objects)
    data = report.getvalue()

    return scu.sendPDFFile(data, filename)


# Feuille d'absences en pdf avec photos:


def pdf_feuille_releve_absences(
    group_ids=[],  # liste des groupes à afficher
    formsemestre_id=None,  # utilisé si pas de groupes selectionné
):
    """Generation de la feuille d'absence en fichier PDF, avec photos"""

    NB_CELL_AM = sco_preferences.get_preference("feuille_releve_abs_AM")
    NB_CELL_PM = sco_preferences.get_preference("feuille_releve_abs_PM")
    COLWIDTH = 0.85 * cm
    if sco_preferences.get_preference("feuille_releve_abs_samedi"):
        days = sco_abs.DAYNAMES[:6]  # Lundi, ..., Samedi
    else:
        days = sco_abs.DAYNAMES[:5]  # Lundi, ..., Vendredi
    nb_days = len(days)

    # Informations sur les groupes à afficher:
    groups_infos = sco_groups_view.DisplayedGroupsInfos(
        group_ids, formsemestre_id=formsemestre_id
    )

    DeptName = sco_preferences.get_preference("DeptName")
    DeptFullName = sco_preferences.get_preference("DeptFullName")
    UnivName = sco_preferences.get_preference("UnivName")
    InstituteName = sco_preferences.get_preference("InstituteName")
    # Generate PDF page
    StyleSheet = styles.getSampleStyleSheet()
    objects = [
        Table(
            [
                [
                    Paragraph(SU(InstituteName), StyleSheet["Heading3"]),
                    Paragraph(
                        SU(
                            "<para align=right>Semaine ..................................................................</para>"
                        ),
                        StyleSheet["Normal"],
                    ),
                ],
                [
                    Paragraph(
                        SU("Département " + DeptFullName), StyleSheet["Heading3"]
                    ),
                    "",
                ],
            ],
            style=TableStyle(
                [("SPAN", (0, 1), (1, 1)), ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]
            ),
        )
    ]

    currow = [""] * (NB_CELL_AM + 1 + NB_CELL_PM + 1)
    elem_day = Table(
        [currow],
        colWidths=([COLWIDTH] * (NB_CELL_AM + 1 + NB_CELL_PM + 1)),
        style=TableStyle(
            [
                ("GRID", (0, 0), (NB_CELL_AM - 1, 0), 0.25, black),
                (
                    "GRID",
                    (NB_CELL_AM + 1, 0),
                    (NB_CELL_AM + NB_CELL_PM, 0),
                    0.25,
                    black,
                ),
            ]
        ),
    )
    W = []
    currow = []
    for n in range(nb_days):
        currow.append(elem_day)
    W.append(currow)

    elem_week = Table(
        W,
        colWidths=([COLWIDTH * (NB_CELL_AM + 1 + NB_CELL_PM + 1)] * nb_days),
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    currow = []
    for n in range(nb_days):
        currow += [Paragraph(SU("<b>" + days[n] + "</b>"), StyleSheet["Normal"])]

    elem_day_name = Table(
        [currow],
        colWidths=([COLWIDTH * (NB_CELL_AM + 1 + NB_CELL_PM + 1)] * nb_days),
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )

    for group_id in groups_infos.group_ids:
        members, group, group_tit, sem, nbdem = sco_groups.get_group_infos(
            group_id, "I"
        )
        L = []

        currow = [
            Paragraph(SU("<b>Groupe " + group_tit + "</b>"), StyleSheet["Normal"])
        ]
        currow.append(elem_day_name)
        L.append(currow)

        currow = [Paragraph(SU("Initiales enseignant :"), StyleSheet["Normal"])]
        currow.append(elem_week)
        L.append(currow)

        currow = [Paragraph(SU("Initiales module :"), StyleSheet["Normal"])]
        currow.append(elem_week)
        L.append(currow)

        for m in members:
            currow = [
                Paragraph(
                    SU(
                        sco_etud.format_nom(m["nom"])
                        + " "
                        + sco_etud.format_prenom(m["prenom"])
                    ),
                    StyleSheet["Normal"],
                )
            ]
            currow.append(elem_week)
            L.append(currow)

        if not L:
            T = Paragraph(SU("Aucun étudiant !"), StyleSheet["Normal"])
        else:
            T = Table(
                L,
                colWidths=(
                    [5.0 * cm, (COLWIDTH * (NB_CELL_AM + 1 + NB_CELL_PM + 1) * nb_days)]
                ),
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                        (
                            "ROWBACKGROUNDS",
                            (0, 2),
                            (-1, -1),
                            (colors.white, colors.lightgrey),
                        ),
                    ]
                ),
            )

        objects.append(T)

    # Réduit sur une page
    objects = [KeepInFrame(0, 0, objects, mode="shrink")]
    # Build document
    report = io.BytesIO()  # in-memory document, no disk file
    filename = "absences-%s-%s.pdf" % (DeptName, groups_infos.groups_filename)
    if sco_preferences.get_preference("feuille_releve_abs_taille") == "A3":
        taille = A3
    elif sco_preferences.get_preference("feuille_releve_abs_taille") == "A4":
        taille = A4
    if sco_preferences.get_preference("feuille_releve_abs_format") == "Paysage":
        document = BaseDocTemplate(report, pagesize=landscape(taille))
    else:
        document = BaseDocTemplate(report, pagesize=taille)
    document.addPageTemplates(
        ScolarsPageTemplate(
            document,
            preferences=sco_preferences.SemPreferences(),
        )
    )
    document.build(objects)
    data = report.getvalue()

    return scu.sendPDFFile(data, filename)
