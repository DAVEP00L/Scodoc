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


""" Verification version logiciel vs version "stable" sur serveur
    N'effectue pas la mise à jour automatiquement, mais permet un affichage d'avertissement.

    Désactivé temporairement pour ScoDoc 9.
"""

from flask import current_app


def is_up_to_date():
    """True if up_to_date
    Returns status, message
    """
    current_app.logger.debug("Warning: is_up_to_date not implemented for ScoDoc9")
    return True, "unimplemented"


def html_up_to_date_box():
    """"""
    status, msg = is_up_to_date()
    if status:
        return ""
    return (
        """<div class="update_warning">
    <span>Attention: cette installation de ScoDoc n'est pas à jour.</span>
    <div class="update_warning_sub">Contactez votre administrateur. %s</div>
    </div>"""
        % msg
    )
