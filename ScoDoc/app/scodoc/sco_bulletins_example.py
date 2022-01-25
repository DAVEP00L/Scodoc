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

"""Generation bulletins de notes: exemple minimal pour les programmeurs
"""
from reportlab.platypus import Paragraph

from app.scodoc import sco_pdf
from app.scodoc import sco_bulletins_generator
from app.scodoc import sco_bulletins_standard


class BulletinGeneratorExample(sco_bulletins_standard.BulletinGeneratorStandard):
    """Un exemple simple de bulletin de notes en version PDF seulement.
    Part du bulletin standard et redéfini la partie centrale.
    """

    description = "exemple (ne pas utiliser)"  # la description doit être courte: elle apparait dans le menu de paramètrage
    supported_formats = [
        "pdf"
    ]  # indique que ce générateur ne peut produire que du PDF (la version web sera donc celle standard de ScoDoc)

    # En général, on veut définir un format de table spécial, sans changer le reste (titre, pied de page).
    # Si on veut changer le reste, surcharger les méthodes:
    #  .bul_title_pdf(self)  : partie haute du bulletin
    #  .bul_part_below(self, format='') : infos sous la table
    #  .bul_signatures_pdf(self) : signatures

    def bul_table(self, format=""):
        """Défini la partie centrale de notre bulletin PDF.
        Doit renvoyer une liste d'objets PLATYPUS
        """
        assert format == "pdf"  # garde fou
        return [
            Paragraph(
                sco_pdf.SU(
                    "L'étudiant %(nomprenom)s a une moyenne générale de %(moy_gen)s"
                    % self.infos
                ),
                self.CellStyle,  # un style pdf standard
            )
        ]


# Déclarer votre classe à ScoDoc:
# sco_bulletins_generator.register_bulletin_class(BulletinGeneratorExample)
