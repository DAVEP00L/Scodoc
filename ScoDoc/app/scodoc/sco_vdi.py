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

"""Classe stockant le VDI avec le code étape (noms de fichiers maquettes et code semestres)
"""
from app.scodoc.sco_exceptions import ScoValueError


class ApoEtapeVDI(object):
    _ETAPE_VDI_SEP = "!"

    def __init__(self, etape_vdi=None, etape="", vdi=""):
        """Build from string representation, e.g. 'V1RT!111'"""
        if etape_vdi:
            self.etape_vdi = etape_vdi
            self.etape, self.vdi = self.split_etape_vdi(etape_vdi)
        elif etape:
            if self._ETAPE_VDI_SEP in etape:
                raise ScoValueError("valeur code etape invalide")
            self.etape, self.vdi = etape, vdi
            self.etape_vdi = self.concat_etape_vdi(etape, vdi)
        else:
            self.etape_vdi, self.etape, self.vdi = "", "", ""

    def __repr__(self):
        return self.__class__.__name__ + "('" + str(self) + "')"

    def __str__(self):
        return self.etape_vdi

    def _cmp(self, other):
        """Test égalité de deux codes étapes.
        Si le VDI des deux est spécifié, on l'utilise. Sinon, seul le code étape est pris en compte.
        Donc V1RT == V1RT!111, V1RT!110 == V1RT, V1RT!77 != V1RT!78, ...

        Compare the two objects x (=self) and y and return an integer according to
        the outcome. The return value is negative if x < y, zero if x == y
        and strictly positive if x > y.
        """
        if other is None:
            return -1
        if isinstance(other, str):
            other = ApoEtapeVDI(other)

        if self.vdi and other.vdi:
            x = (self.etape, self.vdi)
            y = (other.etape, other.vdi)
        else:
            x = self.etape
            y = other.etape

        return (x > y) - (x < y)

    def __eq__(self, other):
        return self._cmp(other) == 0

    def __ne__(self, other):
        return self._cmp(other) != 0

    def __lt__(self, other):
        return self._cmp(other) < 0

    def __le__(self, other):
        return self._cmp(other) <= 0

    def __gt__(self, other):
        return self._cmp(other) > 0

    def __ge__(self, other):
        return self._cmp(other) >= 0

    def split_etape_vdi(self, etape_vdi):
        """Etape Apogee can be stored as 'V1RT' or, including the VDI version,
        as 'V1RT!111'
        Returns etape, VDI
        """
        if etape_vdi:
            t = etape_vdi.split(self._ETAPE_VDI_SEP)
            if len(t) == 1:
                etape = etape_vdi
                vdi = ""
            elif len(t) == 2:
                etape, vdi = t
            else:
                raise ValueError("invalid code etape")
            return etape, vdi
        else:
            return etape_vdi, ""

    def concat_etape_vdi(self, etape, vdi=""):
        if vdi:
            return self._ETAPE_VDI_SEP.join([etape, vdi])
        else:
            return etape


# [ ApoEtapeVDI('V1RT!111'), ApoEtapeVDI('V1RT!112'), ApoEtapeVDI('VCRT'), ApoEtapeVDI('V1RT') ]
