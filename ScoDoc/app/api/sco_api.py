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

"""API ScoDoc 9
"""
# PAS ENCORE IMPLEMENTEE, juste un essai
# Pour P. Bouron, il faudrait en priorité l'équivalent de
# Scolarite/Notes/moduleimpl_withmodule_list (alias scodoc7 do_moduleimpl_withmodule_list)
# Scolarite/Notes/evaluation_create
# Scolarite/Notes/evaluation_delete
# Scolarite/Notes/formation_list
# Scolarite/Notes/formsemestre_list
# Scolarite/Notes/formsemestre_partition_list
# Scolarite/Notes/groups_view
# Scolarite/Notes/moduleimpl_status
# Scolarite/setGroups

from flask import jsonify, request, url_for, abort
from app import db
from app.api import bp
from app.api.auth import token_auth
from app.api.errors import bad_request

from app import models


@bp.route("list_depts", methods=["GET"])
@token_auth.login_required
def list_depts():
    depts = models.Departement.query.filter_by(visible=True).all()
    data = [d.to_dict() for d in depts]
    return jsonify(data)
