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

"""Signature des bulletin pdf


XXX en projet, non finalisé: on peut utiliser en attendant les paramétrages des bulletins (malcommodes).


Il ne s'agit pas d'une "signature" électronique, mais simplement d'une image
que l'on intègre dans les documents pdf générés (bulletins, classeur des bulletins,
envois par mail).

La signature est controlée par:
- la présence d'un fichier .../ScoDoc/static/signatures/<DeptId>/<formsemestre_id>/bul_sig_{left|right}
   ou, à défaut, .../ScoDoc/signatures/<DeptId>/bul_sig_{left|right}
- les préférences booléennes bul_sig_left et bul_sig_right 
   (ne pas confondre avec bul_show_sig_left...)
- les préférences bul_sig_left_image_height et bul_sig_right_image_height 
    (hauteur de l'image, float, en mm)

API:
- form_change_bul_sig( side = "left" | "right", [formsemestre_id])
    affiche signature courante, soit globale soit pour le semestre
    upload nouvelle
- set_bul_sig( side = "left", [formsemestre_id], image )

Lien sur Scolarite/edit_preferences (sans formsemestre_id)
et sur page "réglages bulletin" (avec formsemestre_id)

"""
# import os


# def form_change_bul_sig(side, formsemestre_id=None):
#     """Change pdf signature"""
#     filename = _get_sig_existing_filename(
#         side, formsemestre_id=formsemestre_id
#     )
#     if side == "left":
#         sidetxt = "gauche"
#     elif side == "right":
#         sidetxt = "droite"
#     else:
#         raise ValueError("invalid value for 'side' parameter")
#     signatureloc = get_bul_sig_img()
#     H = [
#         self.sco_header(page_title="Changement de signature"),
#         """<h2>Changement de la signature bulletin de %(sidetxt)s</h2>
#             """
#         % (sidetxt,),
#     ]
#     "<p>Photo actuelle (%(signatureloc)s):      "


# def get_bul_sig_img(side, formsemestre_id=None):
#     "send back signature image data"
#     # slow, not cached, used for unfrequent access (do not bypass python)


# def _sig_filename(side, formsemestre_id=None):
#     if not side in ("left", "right"):
#         raise ValueError("side must be left or right")
#     dirs = [SCODOC_LOGOS_DIR, g.scodoc_dept]
#     if formsemestre_id:
#         dirs.append(formsemestre_id)
#     dirs.append("bul_sig_{}".format(side))
#     return os.path.join(*dirs)


# def _get_sig_existing_filename(side, formsemestre_id=None):
#     "full path to signature to use, or None if no signature available"
#     if formsemestre_id:
#         filename = _sig_filename(side, formsemestre_id=formsemestre_id)
#         if os.path.exists(filename):
#             return filename
#     filename = _sig_filename(side)
#     if os.path.exists(filename):
#         return filename
#     else:
#         return None
