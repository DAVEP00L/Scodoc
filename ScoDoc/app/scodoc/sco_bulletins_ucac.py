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

"""Generation bulletins de notes 

Format table "UCAC"
On redéfini la table centrale du bulletin de note et hérite de tout le reste du bulletin standard.

E. Viennet, juillet 2011
"""

import app.scodoc.sco_utils as scu
from app.scodoc.sco_pdf import blue, cm, mm
from app.scodoc.sco_pdf import Color, Paragraph, Spacer, Table

from app.scodoc import sco_preferences

from app.scodoc import sco_bulletins_generator
from app.scodoc import sco_bulletins_standard
from app.scodoc import gen_tables


class BulletinGeneratorUCAC(sco_bulletins_standard.BulletinGeneratorStandard):
    description = "style UCAC"  # la description doit être courte: elle apparait dans le menu de paramètrage ScoDoc
    supported_formats = ["html", "pdf"]

    PDF_LINEWIDTH = 1.25
    PDF_TITLEBGCOLOR = Color(
        170 / 255.0, 187 / 255.0, 204 / 255.0
    )  # couleur fond lignes titres UE
    # Inherited constants:
    # PDF_LINECOLOR = Color(0.,0,0)
    # PDF_MODSEPCOLOR = Color(170/255.,170/255.,170/255.) # lignes séparant les modules
    # PDF_UE_CUR_BG = Color(210/255.,210/255.,210/255.) # fond UE courantes non prises en compte
    # PDF_LIGHT_GRAY = Color(0.75,0.75,0.75)

    def build_bulletin_table(self):  # overload standard method
        """Génère la table centrale du bulletin de notes UCAC

        La version n'est ici pas utilisée (on ne montre jamais les notes des évaluations).

        Renvoie: colkeys, P, pdf_style, colWidths
        - colkeys: nom des colonnes de la table (clés)
        - table (liste de dicts de chaines de caracteres)
        - style (commandes table Platypus)
        - largeurs de colonnes pour PDF
        """
        I = self.infos
        formsemestre_id = I["formsemestre_id"]
        prefs = sco_preferences.SemPreferences(formsemestre_id)

        P = []  # elems pour générer table avec gen_table (liste de dicts)

        # Noms des colonnes à afficher:
        colkeys = [
            "code_ue",
            "titre_ue",
            "module",
            "note",
            "moyenne_ue",
            "coef",
            "total",
        ]
        if prefs["bul_show_abs_modules"]:
            colkeys.append("abs")

        # Largeur colonnes (pour PDF seulement):
        colWidths = {
            "code_ue": 20 * mm,
            "titre_ue": 40 * mm,
            "module": 42 * mm,
            "note": 22 * mm,
            "moyenne_ue": 22 * mm,
            "coef": 22 * mm,
            "total": 22 * mm,
            "abs": 22 * mm,
        }

        # 1ère ligne titres
        P.append(
            {
                "code_ue": "Code UE",
                "titre_ue": "Unités d'enseignement",
                "module": "Modules",
                "note": "Notes/20",
                "moyenne_ue": "Moyenne UE/20",
                "coef": "Coef.",
                "total": "Total",
                "abs": "Abs (J. / N.J.)",
                "_css_row_class": "bul_ucac_row_tit",
                "_pdf_row_markup": ["b"],
                "_pdf_style": [
                    ("BACKGROUND", (0, 0), (-1, 0), Color(0.75, 0.75, 0.75))
                ],
            }
        )

        # Quantités spécifiques à l'UCAC, calculées ici au vol:
        sum_coef_ues = 0.0  # somme des coefs des UE
        sum_pt_sem = 0.0  # somme des "points validés" (coef x moyenne UE)

        def list_ue(ue, ue_descr, nb_modules=0):
            # ligne décrivant UE
            moy_txt = ue["cur_moy_ue_txt"]
            # log("ue['ue_status']['cur_moy_ue'] = %s" % ue['ue_status']['cur_moy_ue'] )
            # log("ue['ue_status']['coef_ue'] = %s" % ue['ue_status']['coef_ue'] )
            try:
                total_pt_ue_v = (
                    ue["ue_status"]["cur_moy_ue"] * ue["ue_status"]["coef_ue"]
                )
                total_pt_ue = scu.fmt_note(total_pt_ue_v)
                # log('total_pt_ue = %s' % total_pt_ue)
            except:
                # log("ue['ue_status']['cur_moy_ue'] = %s" % ue['ue_status']['cur_moy_ue'] )
                # log("ue['ue_status']['coef_ue'] = %s" % ue['ue_status']['coef_ue'] )
                total_pt_ue_v = 0
                total_pt_ue = ""

            t = {
                "code_ue": ue["acronyme"],
                "titre_ue": "%s %s" % (ue["titre"], ue_descr or ""),
                "_titre_ue_colspan": 3,
                "moyenne_ue": moy_txt,  # moyenne de l'UE
                "coef": coef_ue,  # Attention: on affiche le coefficient de l'UE, et non le total des crédits
                "total": total_pt_ue,  # points (et non crédits),
                "_css_row_class": "bul_ucac_row_ue",
                "_pdf_style": [
                    ("BACKGROUND", (0, 0), (-1, 0), self.ue_color(ue_type=ue["type"]))
                ],
            }
            if (
                nb_modules > 0
            ):  # cases inutilisées par les lignes modules: span vertical
                t["_pdf_style"] += [
                    ("SPAN", (0, 0), (0, nb_modules)),
                    ("SPAN", (1, 0), (1, nb_modules)),
                    ("SPAN", (4, 0), (-1, nb_modules)),
                ]
            P.append(t)
            return total_pt_ue_v

        def list_modules(ue_modules, ue_type=None, rowstyle="", hidden=False):
            "Ajoute les lignes décrivant les modules d'une UE"
            pdf_style = [("LINEABOVE", (0, 2), (-1, 3), 1, self.PDF_MODSEPCOLOR)]
            if ue_type == "cur":  # UE courante non prise en compte (car capitalisee)
                pdf_style.append(("BACKGROUND", (0, 0), (-1, 0), self.PDF_UE_CUR_BG))

            for mod in ue_modules:
                if mod["mod_moy_txt"] == "NI":
                    continue  # saute les modules où on n'est pas inscrit
                P.append(
                    {
                        "module": mod["name"],
                        "note": mod["mod_moy_txt"],
                        "abs": mod["mod_abs_txt"],
                        "_pdf_style": pdf_style,
                        "_css_row_class": "bul_ucac_row_mod%s" % rowstyle,
                        "_hidden": hidden,
                    }
                )

        for ue in I["ues"]:
            # log('** ue %s' % ue['titre'])
            ue_descr = ue["ue_descr_txt"]
            coef_ue = ue["coef_ue_txt"]
            ue_type = None
            # --- UE capitalisée:
            if ue["ue_status"]["is_capitalized"]:
                if sco_preferences.get_preference(
                    "bul_show_ue_cap_details", formsemestre_id
                ):
                    nb_modules = len(ue["modules_capitalized"])
                    hidden = False
                    cssstyle = ""
                else:
                    nb_modules = 0
                    hidden = True
                    cssstyle = "sco_hide"
                pt = list_ue(ue, ue_descr, nb_modules=nb_modules)
                sum_pt_sem += pt
                coef_ue = ""
                # Notes des modules de l'UE capitalisée antérieurement:
                list_modules(
                    ue["modules_capitalized"],
                    hidden=hidden,
                    rowstyle=" bul_ucac_row_cap %s" % cssstyle,
                )

                ue_descr = "(en cours, non prise en compte)"
                ue_type = "cur"

            # --- UE ordinaire
            pt = list_ue(ue, ue_descr)
            if not ue["ue_status"]["is_capitalized"]:
                sum_pt_sem += pt
                sum_coef_ues += ue["ue_status"]["coef_ue"]

            if len(ue["modules"]) > 1:  # liste les autres modules
                list_modules(ue["modules"][1:], ue_type=ue_type)

        # Ligne "Total"
        P.append(
            {
                "code_ue": "Total",
                "moyenne_ue": I["moy_gen"],
                "coef": scu.fmt_note(sum_coef_ues),
                "total": scu.fmt_note(sum_pt_sem),
                "_code_ue_colspan": 4,
                "_css_row_class": "bul_ucac_row_total",
                "_pdf_row_markup": ["b"],
                "_pdf_style": [("BACKGROUND", (0, 0), (-1, 0), self.PDF_TITLEBGCOLOR)],
            }
        )

        # Ligne décision jury (toujours présente, ignore le paramètre)
        P.append(
            {
                "code_ue": "Décision",
                "_code_ue_colspan": 4,
                "moyenne_ue": I.get("decision_jury", "") or "",
                "_moyenne_ue_colspan": 3,
                "_css_row_class": "bul_ucac_row_decision",
                "_pdf_row_markup": ["b"],
                "_pdf_style": [("BACKGROUND", (0, 0), (-1, 0), self.PDF_TITLEBGCOLOR)],
            }
        )

        # Ligne "Mention" (figure toujours: le paramètre 'bul_show_mention' est ignoré)
        P.append(
            {
                "code_ue": "Mention",
                "_code_ue_colspan": 4,
                "moyenne_ue": I["mention"] or "",
                "_moyenne_ue_colspan": 3,
                "_css_row_class": "bul_ucac_row_mention",
                "_pdf_row_markup": ["b"],
                "_pdf_style": [
                    ("BACKGROUND", (0, 0), (-1, 0), self.PDF_TITLEBGCOLOR),
                    ("SPAN", (0, 0), (3, 0)),
                    ("SPAN", (4, 0), (-1, 0)),
                ],
            }
        )

        # Global pdf style comands:
        pdf_style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            (
                "INNERGRID",
                (0, 0),
                (-1, -1),
                self.PDF_LINEWIDTH,
                self.PDF_LINECOLOR,
            ),  # grille interne
            (
                "BOX",
                (0, 0),
                (-1, -1),
                self.PDF_LINEWIDTH,
                self.PDF_LINECOLOR,
            ),  # bordure extérieure
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                self.PDF_TITLEBGCOLOR,
            ),  # couleur fond ligne titre
        ]

        #    if len(P[0]) > 5:
        #    colWidths.append( 1.5*cm ) # absences/modules
        # log('len(P) = %s' % len(P) )
        # log( 'lens P=%s' % [ len(x) for x in P ] )
        # log('P=\n%s' % pprint.pformat(P))
        return colkeys, P, pdf_style, colWidths


# sco_bulletins_generator.register_bulletin_class(BulletinGeneratorUCAC)
