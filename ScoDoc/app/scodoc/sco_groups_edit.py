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

"""Formulaires gestion des groupes
"""
from flask import render_template

from app.scodoc import html_sco_header
from app.scodoc import sco_groups
from app.scodoc.sco_exceptions import AccessDenied


def affect_groups(partition_id):
    """Formulaire affectation des etudiants aux groupes de la partition.
    Permet aussi la creation et la suppression de groupes.
    """
    # réécrit pour 9.0.47 avec un template
    partition = sco_groups.get_partition(partition_id)
    formsemestre_id = partition["formsemestre_id"]
    if not sco_groups.sco_permissions_check.can_change_groups(formsemestre_id):
        raise AccessDenied("vous n'avez pas la permission de modifier les groupes")
    return render_template(
        "scolar/affect_groups.html",
        sco_header=html_sco_header.sco_header(
            page_title="Affectation aux groupes",
            javascripts=["js/groupmgr.js"],
            cssstyles=["css/groups.css"],
        ),
        sco_footer=html_sco_header.sco_footer(),
        partition=partition,
        partitions_list=sco_groups.get_partitions_list(
            formsemestre_id, with_default=False
        ),
        formsemestre_id=formsemestre_id,
    )
