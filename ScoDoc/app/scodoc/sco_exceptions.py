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

"""Exception handling
"""

# --- Exceptions
MSGPERMDENIED = "l'utilisateur %s n'a pas le droit d'effectuer cette operation"


class ScoException(Exception):
    pass


class NoteProcessError(ScoException):
    "misc errors in process"
    pass


class InvalidEtudId(NoteProcessError):
    pass


class InvalidNoteValue(ScoException):
    pass


# Exception qui stoque dest_url, utilisee dans Zope standard_error_message
class ScoValueError(ScoException):
    def __init__(self, msg, dest_url=None):
        ScoException.__init__(self, msg)
        self.dest_url = dest_url


class FormatError(ScoValueError):
    pass


class ScoInvalidDept(ScoValueError):
    """departement invalide"""

    pass


class ScoConfigurationError(ScoValueError):
    """Configuration invalid"""

    pass


class ScoLockedFormError(ScoException):
    def __init__(self, msg=""):
        msg = (
            "Cette formation est verrouillée (car il y a un semestre verrouillé qui s'y réfère). "
            + str(msg)
        )
        ScoException.__init__(self, msg)


class ScoGenError(ScoException):
    "exception avec affichage d'une page explicative ad-hoc"

    def __init__(self, msg=""):
        ScoException.__init__(self, msg)


class AccessDenied(ScoGenError):
    pass


class ScoInvalidDateError(ScoValueError):
    pass


# Pour les API JSON
class APIInvalidParams(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv["message"] = self.message
        return rv
