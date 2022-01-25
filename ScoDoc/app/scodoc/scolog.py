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

"""Logging des opérations en base de données
"""

from flask import request
from flask_login import current_user
import app.scodoc.notesdb as ndb


def logdb(cnx=None, method=None, etudid=None, msg=None, commit=True):
    "Add entry"
    if not cnx:
        raise ValueError("logdb: cnx is None")

    args = {
        "authenticated_user": current_user.user_name,
    }

    args.update({"method": method, "etudid": etudid, "msg": msg})
    ndb.quote_dict(args)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """INSERT INTO scolog
        (authenticated_user,method,etudid,msg)
        VALUES
        (%(authenticated_user)s,%(method)s,%(etudid)s,%(msg)s)""",
        args,
    )
    if commit:
        cnx.commit()


def loglist(cnx, method=None, authenticated_user=None):
    """List of events logged for these method and user"""
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(
        """SELECT * FROM scolog
        WHERE method=%(method)s
        AND authenticated_user=%(authenticated_user)s""",
        {"method": method, "authenticated_user": authenticated_user},
    )
    return cursor.dictfetchall()
