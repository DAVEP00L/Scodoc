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

"""Generation bulletins de notes dans l'ancien format de ScoDoc (avant juillet 2011).

 Code partiellement redondant, copié de l'ancien système de gestion des bulletins.

 Voir sco_bulletins_standard pour une version plus récente.

 CE FORMAT N'EVOLUERA PLUS ET EST CONSIDERE COMME OBSOLETE.
 
"""

import app.scodoc.sco_utils as scu
from app.scodoc.sco_permissions import Permission
from app.scodoc import sco_formsemestre
from app.scodoc import sco_pdf
from app.scodoc.sco_pdf import Color, Paragraph, Spacer, Table
from app.scodoc.sco_pdf import blue, cm, mm
from app.scodoc.sco_pdf import SU
from app.scodoc import sco_preferences
from app.scodoc import sco_bulletins_generator
from app.scodoc import sco_bulletins_pdf

# Important: Le nom de la classe ne doit pas changer (bien le choisir), car il sera stocké en base de données (dans les préférences)
class BulletinGeneratorLegacy(sco_bulletins_generator.BulletinGenerator):
    description = "Ancien format ScoDoc"  # la description doit être courte: elle apparait dans le menu de paramètrage ScoDoc
    supported_formats = ["html", "pdf"]

    def bul_title_pdf(self):
        """Génère la partie "titre" du bulletin de notes.
        Renvoie une liste d'objets platypus
        """
        objects = sco_bulletins_pdf.process_field(
            self.preferences["bul_pdf_title"], self.infos, self.FieldStyle
        )
        objects.append(
            Spacer(1, 5 * mm)
        )  # impose un espace vertical entre le titre et la table qui suit
        return objects

    def bul_table(self, format="html"):
        """Table bulletin"""
        if format == "pdf":
            return self.bul_table_pdf()
        elif format == "html":
            return self.bul_table_html()
        else:
            raise ValueError("invalid bulletin format (%s)" % format)

    def bul_table_pdf(self):
        """Génère la table centrale du bulletin de notes
        Renvoie une liste d'objets PLATYPUS (eg instance de Table).
        """
        P, pdfTableStyle, colWidths = _bulletin_pdf_table_legacy(
            self.infos, version=self.version
        )
        return [self.buildTableObject(P, pdfTableStyle, colWidths)]

    def bul_table_html(self):
        """Génère la table centrale du bulletin de notes: chaine HTML"""
        I = self.infos
        formsemestre_id = self.infos["formsemestre_id"]

        bul_show_abs_modules = sco_preferences.get_preference(
            "bul_show_abs_modules", formsemestre_id
        )

        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
        if sem["bul_bgcolor"]:
            bgcolor = sem["bul_bgcolor"]
        else:
            bgcolor = "background-color: rgb(255,255,240)"

        linktmpl = '<span onclick="toggle_vis_ue(this);" class="toggle_ue">%s</span>'
        minuslink = linktmpl % scu.icontag("minus_img", border="0", alt="-")
        pluslink = linktmpl % scu.icontag("plus_img", border="0", alt="+")

        H = ['<table class="notes_bulletin" style="background-color: %s;">' % bgcolor]

        if sco_preferences.get_preference("bul_show_minmax", formsemestre_id):
            minmax = (
                '<span class="bul_minmax" title="[min, max] promo">[%s, %s]</span>'
                % (I["moy_min"], I["moy_max"])
            )
            bargraph = ""
        else:
            minmax = ""
            bargraph = I["moy_gen_bargraph_html"]
        # 1ere ligne: titres
        H.append(
            '<tr><td class="note_bold">Moyenne</td><td class="note_bold cell_graph">%s%s%s%s</td>'
            % (I["moy_gen"], I["etud_etat_html"], minmax, bargraph)
        )
        H.append('<td class="note_bold">%s</td>' % I["rang_txt"])
        H.append('<td class="note_bold">Note/20</td><td class="note_bold">Coef</td>')
        if bul_show_abs_modules:
            H.append('<td class="note_bold">Abs (J. / N.J.)</td>')
        H.append("</tr>")

        def list_modules(ue_modules, rowstyle):
            for mod in ue_modules:
                if mod["mod_moy_txt"] == "NI":
                    continue  # saute les modules où on n'est pas inscrit
                H.append('<tr class="notes_bulletin_row_mod%s">' % rowstyle)
                if sco_preferences.get_preference(
                    "bul_show_minmax_mod", formsemestre_id
                ):
                    rang_minmax = '%s <span class="bul_minmax" title="[min, max] UE">[%s, %s]</span>' % (
                        mod["mod_rang_txt"],
                        scu.fmt_note(mod["stats"]["min"]),
                        scu.fmt_note(mod["stats"]["max"]),
                    )
                else:
                    rang_minmax = mod["mod_rang_txt"]  # vide si pas option rang
                H.append(
                    '<td>%s</td><td>%s</td><td>%s</td><td class="note">%s</td><td>%s</td>'
                    % (
                        mod["code_html"],
                        mod["name_html"],
                        rang_minmax,
                        mod["mod_moy_txt"],
                        mod["mod_coef_txt"],
                    )
                )
                if bul_show_abs_modules:
                    H.append("<td>%s</td>" % mod["mod_abs_txt"])
                H.append("</tr>")

                if self.version != "short":
                    # --- notes de chaque eval:
                    for e in mod["evaluations"]:
                        if e["visibulletin"] or self.version == "long":
                            H.append(
                                '<tr class="notes_bulletin_row_eval%s">' % rowstyle
                            )
                            H.append(
                                '<td>%s</td><td>%s</td><td class="bull_nom_eval">%s</td><td class="note">%s</td><td class="bull_coef_eval">%s</td></tr>'
                                % (
                                    "",
                                    "",
                                    e["name_html"],
                                    e["note_html"],
                                    e["coef_txt"],
                                )
                            )

        # Contenu table: UE apres UE
        for ue in I["ues"]:
            ue_descr = ue["ue_descr_html"]
            coef_ue = ue["coef_ue_txt"]
            rowstyle = ""
            plusminus = minuslink  #
            if ue["ue_status"]["is_capitalized"]:
                if sco_preferences.get_preference(
                    "bul_show_ue_cap_details", formsemestre_id
                ):
                    plusminus = minuslink
                    hide = ""
                else:
                    plusminus = pluslink
                    hide = "sco_hide"
                H.append('<tr class="notes_bulletin_row_ue">')
                H.append(
                    '<td class="note_bold">%s%s</td><td class="note_bold">%s</td><td>%s</td><td>%s</td><td>%s</td>'
                    % (
                        plusminus,
                        ue["acronyme"],
                        ue["moy_ue_txt"],
                        ue_descr,
                        "",
                        coef_ue,
                    )
                )
                if bul_show_abs_modules:
                    H.append("<td></td>")
                H.append("</tr>")
                list_modules(ue["modules_capitalized"], " bul_row_ue_cap %s" % hide)

                coef_ue = ""
                ue_descr = "(en cours, non prise en compte)"
                rowstyle = (
                    " bul_row_ue_cur"  # style css pour indiquer UE non prise en compte
                )

            H.append('<tr class="notes_bulletin_row_ue">')
            if sco_preferences.get_preference("bul_show_minmax", formsemestre_id):
                moy_txt = (
                    '%s <span class="bul_minmax" title="[min, max] UE">[%s, %s]</span>'
                    % (
                        scu.fmt_note(ue["cur_moy_ue_txt"]),
                        scu.fmt_note(ue["min"]),
                        scu.fmt_note(ue["max"]),
                    )
                )
            else:
                moy_txt = ue["cur_moy_ue_txt"]

            H.append(
                '<td class="note_bold">%s%s</td><td class="note_bold">%s</td><td>%s</td><td>%s</td><td>%s</td>'
                % (minuslink, ue["acronyme"], moy_txt, ue_descr, "", coef_ue)
            )
            if bul_show_abs_modules:
                H.append("<td></td>")
            H.append("</tr>")
            list_modules(ue["modules"], rowstyle)

        H.append("</table>")

        # ---------------
        return "\n".join(H)

    def bul_part_below(self, format="html"):
        """Génère les informations placées sous la table de notes
        (absences, appréciations, décisions de jury...)
        """
        if format == "pdf":
            return self.bul_part_below_pdf()
        elif format == "html":
            return self.bul_part_below_html()
        else:
            raise ValueError("invalid bulletin format (%s)" % format)

    def bul_part_below_pdf(self):
        """
        Renvoie une liste d'objets platypus
        """
        objects = []

        # ----- ABSENCES
        if self.preferences["bul_show_abs"]:
            nbabs = self.infos["nbabs"]
            nbabsjust = self.infos["nbabsjust"]
            objects.append(Spacer(1, 2 * mm))
            if nbabs:
                objects.append(
                    Paragraph(
                        SU(
                            "%d absences (1/2 journées), dont %d justifiées."
                            % (nbabs, nbabsjust)
                        ),
                        self.CellStyle,
                    )
                )
            else:
                objects.append(
                    Paragraph(SU("Pas d'absences signalées."), self.CellStyle)
                )

        # ----- APPRECIATIONS
        if self.infos.get("appreciations_list", False):
            objects.append(Spacer(1, 3 * mm))
            objects.append(
                Paragraph(
                    SU("Appréciation : " + "\n".join(self.infos["appreciations_txt"])),
                    self.CellStyle,
                )
            )

        # ----- DECISION JURY
        if self.preferences["bul_show_decision"]:
            objects += sco_bulletins_pdf.process_field(
                self.preferences["bul_pdf_caption"],
                self.infos,
                self.FieldStyle,
            )

        return objects

    def bul_part_below_html(self):
        """
        Renvoie chaine HTML
        """
        I = self.infos
        authuser = self.authuser
        H = []
        # --- Absences
        H.append(
            """<p>
        <a href="../Absences/CalAbs?etudid=%(etudid)s" class="bull_link">
        <b>Absences :</b> %(nbabs)s demi-journées, dont %(nbabsjust)s justifiées
        (pendant ce semestre).
        </a></p>
            """
            % I
        )
        # --- Decision Jury
        if I["situation"]:
            H.append("""<p class="bull_situation">%(situation)s</p>""" % I)
        # --- Appreciations
        # le dir. des etud peut ajouter des appreciations,
        # mais aussi le chef (perm. ScoEtudInscrit)
        can_edit_app = (authuser.id in self.infos["responsables"]) or (
            authuser.has_permission(Permission.ScoEtudInscrit)
        )
        H.append('<div class="bull_appreciations">')
        if I["appreciations_list"]:
            H.append("<p><b>Appréciations</b></p>")
        for app in I["appreciations_list"]:
            if can_edit_app:
                mlink = (
                    '<a class="stdlink" href="appreciation_add_form?id=%s">modifier</a> <a class="stdlink" href="appreciation_add_form?id=%s&suppress=1">supprimer</a>'
                    % (app["id"], app["id"])
                )
            else:
                mlink = ""
            H.append(
                '<p><span class="bull_appreciations_date">%s</span>%s<span class="bull_appreciations_link">%s</span></p>'
                % (app["date"], app["comment"], mlink)
            )
        if can_edit_app:
            H.append(
                '<p><a class="stdlink" href="appreciation_add_form?etudid=%(etudid)s&formsemestre_id=%(formsemestre_id)s">Ajouter une appréciation</a></p>'
                % self.infos
            )
        H.append("</div>")
        # ---------------
        return "\n".join(H)

    def bul_signatures_pdf(self):
        """Génère les signatures placées en bas du bulletin
        Renvoie une liste d'objets platypus
        """
        show_left = self.preferences["bul_show_sig_left"]
        show_right = self.preferences["bul_show_sig_right"]
        if show_left or show_right:
            if show_left:
                L = [
                    [
                        sco_bulletins_pdf.process_field(
                            self.preferences["bul_pdf_sig_left"],
                            self.infos,
                            self.FieldStyle,
                        )
                    ]
                ]
            else:
                L = [[""]]
            if show_right:
                L[0].append(
                    sco_bulletins_pdf.process_field(
                        self.preferences["bul_pdf_sig_right"],
                        self.infos,
                        self.FieldStyle,
                    )
                )
            else:
                L[0].append("")
            t = Table(L)
            t._argW[0] = 10 * cm  # fixe largeur colonne gauche

            return [Spacer(1, 1.5 * cm), t]  # espace vertical avant signatures
        else:
            return []


# sco_bulletins_generator.register_bulletin_class(BulletinGeneratorLegacy)


class BulTableStyle(object):
    """Construction du style de tables reportlab platypus pour les bulletins "classiques" """

    LINEWIDTH = 0.5
    LINECOLOR = Color(0, 0, 0)
    UEBGCOLOR = Color(
        170 / 255.0, 187 / 255.0, 204 / 255.0
    )  # couleur fond lignes titres UE
    MODSEPCOLOR = Color(
        170 / 255.0, 170 / 255.0, 170 / 255.0
    )  # lignes séparant les modules

    def __init__(self):
        self.pdfTableStyle = [
            ("LINEBELOW", (0, 0), (-1, 0), self.LINEWIDTH, self.LINECOLOR)
        ]
        self.tabline = 0

    def get_style(self):
        "get resulting style (a list of platypus table commands)"
        # ajoute cadre extérieur bleu:
        self.pdfTableStyle.append(("BOX", (0, 0), (-1, -1), 0.4, blue))

        return self.pdfTableStyle

    def newline(self, ue_type=None):
        self.tabline += 1
        if ue_type == "cur":  # UE courante non prise en compte (car capitalisee)
            self.pdfTableStyle.append(
                (
                    "BACKGROUND",
                    (0, self.tabline),
                    (-1, self.tabline),
                    Color(210 / 255.0, 210 / 255.0, 210 / 255.0),
                )
            )

    def ueline(self):  # met la ligne courante du tableau pdf en style 'UE'
        self.newline()
        i = self.tabline
        self.pdfTableStyle.append(("BACKGROUND", (0, i), (-1, i), self.UEBGCOLOR))

    def modline(
        self, ue_type=None
    ):  # met la ligne courante du tableau pdf en style 'Module'
        self.newline(ue_type=ue_type)
        i = self.tabline
        self.pdfTableStyle.append(("LINEABOVE", (0, i), (-1, i), 1, self.MODSEPCOLOR))


def _bulletin_pdf_table_legacy(I, version="long"):
    """Génère la table centrale du bulletin de notes
    Renvoie un triplet:
    - table (liste de listes de chaines de caracteres)
    - style (commandes table Platypus)
    - largeurs de colonnes
    """
    S = BulTableStyle()
    P = []  # elems pour gen. pdf
    formsemestre_id = I["formsemestre_id"]
    bul_show_abs_modules = sco_preferences.get_preference(
        "bul_show_abs_modules", formsemestre_id
    )

    if sco_preferences.get_preference("bul_show_minmax", formsemestre_id):
        minmax = ' <font size="8">[%s, %s]</font>' % (I["moy_min"], I["moy_max"])
    else:
        minmax = ""

    t = [
        "Moyenne",
        "%s%s%s" % (I["moy_gen"], I["etud_etat_html"], minmax),
        I["rang_txt"],
        "Note/20",
        "Coef",
    ]
    if bul_show_abs_modules:
        t.append("Abs (J. / N.J.)")
    P.append(sco_pdf.bold_paras(t))

    def list_modules(ue_modules, ue_type=None):
        "ajoute les lignes decrivant les modules d'une UE, avec eventuellement les évaluations de chacun"
        for mod in ue_modules:
            if mod["mod_moy_txt"] == "NI":
                continue  # saute les modules où on n'est pas inscrit
            S.modline(ue_type=ue_type)
            if sco_preferences.get_preference("bul_show_minmax_mod", formsemestre_id):
                rang_minmax = '%s <font size="8">[%s, %s]</font>' % (
                    mod["mod_rang_txt"],
                    scu.fmt_note(mod["stats"]["min"]),
                    scu.fmt_note(mod["stats"]["max"]),
                )
            else:
                rang_minmax = mod["mod_rang_txt"]  # vide si pas option rang
            t = [
                mod["code"],
                mod["name"],
                rang_minmax,
                mod["mod_moy_txt"],
                mod["mod_coef_txt"],
            ]
            if bul_show_abs_modules:
                t.append(mod["mod_abs_txt"])
            P.append(t)
            if version != "short":
                # --- notes de chaque eval:
                for e in mod["evaluations"]:
                    if e["visibulletin"] or version == "long":
                        S.newline(ue_type=ue_type)
                        t = ["", "", e["name"], e["note_txt"], e["coef_txt"]]
                        if bul_show_abs_modules:
                            t.append("")
                        P.append(t)

    for ue in I["ues"]:
        ue_descr = ue["ue_descr_txt"]
        coef_ue = ue["coef_ue_txt"]
        ue_type = None
        if ue["ue_status"]["is_capitalized"]:
            t = [ue["acronyme"], ue["moy_ue_txt"], ue_descr, "", coef_ue]
            if bul_show_abs_modules:
                t.append("")
            P.append(sco_pdf.bold_paras(t))
            coef_ue = ""
            ue_descr = "(en cours, non prise en compte)"
            S.ueline()
            if sco_preferences.get_preference(
                "bul_show_ue_cap_details", formsemestre_id
            ):
                list_modules(ue["modules_capitalized"])
            ue_type = "cur"

        if sco_preferences.get_preference("bul_show_minmax", formsemestre_id):
            moy_txt = '%s <font size="8">[%s, %s]</font>' % (
                ue["cur_moy_ue_txt"],
                ue["min"],
                ue["max"],
            )
        else:
            moy_txt = ue["cur_moy_ue_txt"]
        t = [ue["acronyme"], moy_txt, ue_descr, "", coef_ue]
        if bul_show_abs_modules:
            t.append("")
        P.append(sco_pdf.bold_paras(t))
        S.ueline()
        list_modules(ue["modules"], ue_type=ue_type)

    # Largeur colonnes:
    colWidths = [None, 5 * cm, 6 * cm, 2 * cm, 1.2 * cm]
    if len(P[0]) > 5:
        colWidths.append(1.5 * cm)  # absences/modules

    return P, S.get_style(), colWidths
