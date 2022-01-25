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

"""Gestion des images logos (nouveau ScoDoc 9)

Les logos sont `logo_header.<ext>`  et `logo_footer.<ext>`
avec `ext` membre de LOGOS_IMAGES_ALLOWED_TYPES (= jpg, png)

SCODOC_LOGOS_DIR   /opt/scodoc-data/config/logos
"""
import imghdr
import os

from flask import abort, current_app

from app.scodoc import sco_utils as scu


def get_logo_filename(logo_type: str, scodoc_dept: str) -> str:
    """return full filename for this logo, or "" if not found
    an existing file with extension.
        logo_type: "header" or "footer"
        scodoc-dept: acronym
    """
    # Search logos in dept specific dir (/opt/scodoc-data/config/logos/logos_<dept>),
    # then in config dir /opt/scodoc-data/config/logos/
    for image_dir in (
        scu.SCODOC_LOGOS_DIR + "/logos_" + scodoc_dept,
        scu.SCODOC_LOGOS_DIR,  # global logos
    ):
        for suffix in scu.LOGOS_IMAGES_ALLOWED_TYPES:
            filename = os.path.join(image_dir, f"logo_{logo_type}.{suffix}")
            if os.path.isfile(filename) and os.access(filename, os.R_OK):
                return filename

    return ""


def guess_image_type(stream) -> str:
    "guess image type from header in stream"
    header = stream.read(512)
    stream.seek(0)
    fmt = imghdr.what(None, header)
    if not fmt:
        return None
    return fmt if fmt != "jpeg" else "jpg"


def _ensure_directory_exists(filename):
    "create enclosing directory if necessary"
    directory = os.path.split(filename)[0]
    if not os.path.exists(directory):
        current_app.logger.info(f"sco_logos creating directory %s", directory)
        os.mkdir(directory)


def store_image(stream, basename):
    img_type = guess_image_type(stream)
    if img_type not in scu.LOGOS_IMAGES_ALLOWED_TYPES:
        abort(400, "type d'image invalide")
    filename = basename + "." + img_type
    _ensure_directory_exists(filename)
    with open(filename, "wb") as f:
        f.write(stream.read())
    current_app.logger.info(f"sco_logos.store_image %s", filename)
    # erase other formats if they exists
    for extension in set(scu.LOGOS_IMAGES_ALLOWED_TYPES) - set([img_type]):
        try:
            os.unlink(basename + "." + extension)
        except IOError:
            pass
