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

"""(Nouvelle) (Nouvelle) gestion des photos d'etudiants

Les images sont stockées dans .../var/scodoc/photos
L'attribut "photo_filename" de la table identite donne le nom du fichier image, 
sans extension (e.g. "F44/RT_EID31545").
Toutes les images sont converties en jpg, et stockées dans photo_filename.jpg en taille originale.
Elles sont aussi réduites en 90 pixels de hauteur, et stockées dans photo_filename.h90.jpg

Les images sont servies par ScoDoc, via la méthode getphotofile?etudid=xxx


## Historique:
 - jusqu'à novembre 2009, les images étaient stockées dans Zope (ZODB). 
 - jusqu'à v1908, stockées dans .../static/photos (et donc accessibles sans authentification).
 - support for legacy ZODB removed in v1909.

"""

from flask.helpers import make_response
from app.scodoc.sco_exceptions import ScoGenError
import datetime
import glob
import io
import os
import random
import requests
import time
import traceback

import PIL
from PIL import Image as PILImage

from flask import request, g

from config import Config

from app.scodoc import sco_etud
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app import log
from app.scodoc.scolog import logdb
import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu

# Full paths on server's filesystem. Something like "/opt/scodoc/var/scodoc/photos"
PHOTO_DIR = os.path.join(Config.SCODOC_VAR_DIR, "photos")
ICONS_DIR = os.path.join(Config.SCODOC_DIR, "app", "static", "icons")
UNKNOWN_IMAGE_PATH = os.path.join(ICONS_DIR, "unknown.jpg")
UNKNOWN_IMAGE_URL = "get_photo_image?etudid="  # with empty etudid => unknown face image
IMAGE_EXT = ".jpg"
JPG_QUALITY = 0.92
REDUCED_HEIGHT = 90  # pixels
MAX_FILE_SIZE = 1024 * 1024  # max allowed size for uploaded image, in bytes
H90 = ".h90"  # suffix for reduced size images


def photo_portal_url(etud):
    """Returns external URL to retreive photo on portal,
    or None if no portal configured"""
    photo_url = sco_portal_apogee.get_photo_url()
    if photo_url and etud["code_nip"]:
        return photo_url + "?nip=" + etud["code_nip"]
    else:
        return None


def etud_photo_url(etud, size="small", fast=False):
    """url to the image of the student, in "small" size or "orig" size.
    If ScoDoc doesn't have an image and a portal is configured, link to it.
    """
    photo_url = scu.ScoURL() + "/get_photo_image?etudid=%s&size=%s" % (
        etud["etudid"],
        size,
    )
    if fast:
        return photo_url
    path = photo_pathname(etud, size=size)
    if not path:
        # Portail ?
        ext_url = photo_portal_url(etud)
        if not ext_url:
            # fallback: Photo "unknown"
            photo_url = scu.ScoURL() + "/" + UNKNOWN_IMAGE_URL
        else:
            # essaie de copier la photo du portail
            new_path, _ = copy_portal_photo_to_fs(etud)
            if not new_path:
                # copy failed, can we use external url ?
                # nb: rarement utile, car le portail est rarement accessible sans authentification
                if scu.CONFIG.PUBLISH_PORTAL_PHOTO_URL:
                    photo_url = ext_url
                else:
                    photo_url = UNKNOWN_IMAGE_URL
    return photo_url


def get_photo_image(etudid=None, size="small"):
    """Returns photo image (HTTP response)
    If not etudid, use "unknown" image
    """
    if not etudid:
        filename = UNKNOWN_IMAGE_PATH
    else:
        etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
        filename = photo_pathname(etud, size=size)
        if not filename:
            filename = UNKNOWN_IMAGE_PATH
    return _http_jpeg_file(filename)


def _http_jpeg_file(filename):
    """returns an image as a Flask response"""
    st = os.stat(filename)
    last_modified = st.st_mtime  # float timestamp
    file_size = st.st_size
    header = request.headers.get("If-Modified-Since")
    if header is not None:
        header = header.split(";")[0]
        # Some proxies seem to send invalid date strings for this
        # header. If the date string is not valid, we ignore it
        # rather than raise an error to be generally consistent
        # with common servers such as Apache (which can usually
        # understand the screwy date string as a lucky side effect
        # of the way they parse it).
        try:
            dt = datetime.datetime.strptime(header, "%a, %d %b %Y %H:%M:%S GMT")
            mod_since = dt.timestamp()
        except ValueError:
            mod_since = None
        if (mod_since is not None) and last_modified <= mod_since:
            return "", 304  # not modified
    #
    last_modified_str = time.strftime(
        "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(last_modified)
    )
    response = make_response(open(filename, mode="rb").read())
    response.headers["Content-Type"] = "image/jpeg"
    response.headers["Last-Modified"] = last_modified_str
    response.headers["Cache-Control"] = "max-age=3600"
    response.headers["Content-Length"] = str(file_size)
    return response


def etud_photo_is_local(etud, size="small"):
    return photo_pathname(etud, size=size)


def etud_photo_html(etud=None, etudid=None, title=None, size="small"):
    """HTML img tag for the photo, either in small size (h90)
    or original size (size=="orig")
    """
    if not etud:
        if etudid:
            etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
        else:
            raise ValueError("etud_photo_html: either etud or etudid must be specified")
    photo_url = etud_photo_url(etud, size=size)
    nom = etud.get("nomprenom", etud["nom_disp"])
    if title is None:
        title = nom
    if not etud_photo_is_local(etud):
        fallback = (
            """onerror='this.onerror = null; this.src="%s"'""" % UNKNOWN_IMAGE_URL
        )
    else:
        fallback = ""
    if size == "small":
        height_attr = 'height="%s"' % REDUCED_HEIGHT
    else:
        height_attr = ""
    return '<img src="%s" alt="photo %s" title="%s" border="0" %s %s />' % (
        photo_url,
        nom,
        title,
        height_attr,
        fallback,
    )


def etud_photo_orig_html(etud=None, etudid=None, title=None):
    """HTML img tag for the photo, in full size.
    Full-size images are always stored locally in the filesystem.
    They are the original uploaded images, converted in jpeg.
    """
    return etud_photo_html(etud=etud, etudid=etudid, title=title, size="orig")


def photo_pathname(etud, size="orig"):
    """Returns full path of image file if etud has a photo (in the filesystem), or False.
    Do not distinguish the cases: no photo, or file missing.
    """
    if size == "small":
        version = H90
    elif size == "orig":
        version = ""
    else:
        raise ValueError("invalid size parameter for photo")
    if not etud["photo_filename"]:
        return False
    path = os.path.join(PHOTO_DIR, etud["photo_filename"]) + version + IMAGE_EXT
    if os.path.exists(path):
        return path
    else:
        return False


def store_photo(etud, data):
    """Store image for this etud.
    If there is an existing photo, it is erased and replaced.
    data is a bytes string with image raw data.

    Update database to store filename.

    Returns (status, msg)
    """
    # basic checks
    filesize = len(data)
    if filesize < 10 or filesize > MAX_FILE_SIZE:
        return 0, "Fichier image de taille invalide ! (%d)" % filesize
    try:
        filename = save_image(etud["etudid"], data)
    except PIL.UnidentifiedImageError:
        raise ScoGenError(msg="Fichier d'image invalide ou non format non supporté")
    # update database:
    etud["photo_filename"] = filename
    etud["foto"] = None

    cnx = ndb.GetDBConnexion()
    sco_etud.identite_edit_nocheck(cnx, etud)
    cnx.commit()
    #
    logdb(cnx, method="changePhoto", msg=filename, etudid=etud["etudid"])
    #
    return 1, "ok"


def suppress_photo(etud):
    """Suppress a photo"""
    log("suppress_photo etudid=%s" % etud["etudid"])
    rel_path = photo_pathname(etud)
    # 1- remove ref. from database
    etud["photo_filename"] = None
    cnx = ndb.GetDBConnexion()
    sco_etud.identite_edit_nocheck(cnx, etud)
    cnx.commit()
    # 2- erase images files
    if rel_path:
        # remove extension and glob
        rel_path = rel_path[: -len(IMAGE_EXT)]
        filenames = glob.glob(rel_path + "*" + IMAGE_EXT)
        for filename in filenames:
            log("removing file %s" % filename)
            os.remove(filename)
    # 3- log
    logdb(cnx, method="changePhoto", msg="suppression", etudid=etud["etudid"])


# ---------------------------------------------------------------------------
# Internal functions


def save_image(etudid, data):
    """data is a bytes string.
    Save image in JPEG in 2 sizes (original and h90).
    Returns filename (relative to PHOTO_DIR), without extension
    """
    data_file = io.BytesIO()
    data_file.write(data)
    data_file.seek(0)
    img = PILImage.open(data_file)
    filename = get_new_filename(etudid)
    path = os.path.join(PHOTO_DIR, filename)
    log("saving %dx%d jpeg to %s" % (img.size[0], img.size[1], path))
    img = img.convert("RGB")
    img.save(path + IMAGE_EXT, format="JPEG", quality=92)
    # resize:
    img = scale_height(img)
    log("saving %dx%d jpeg to %s.h90" % (img.size[0], img.size[1], filename))
    img.save(path + H90 + IMAGE_EXT, format="JPEG", quality=92)
    return filename


def scale_height(img, W=None, H=REDUCED_HEIGHT):
    if W is None:
        # keep aspect
        W = int((img.size[0] * H) / img.size[1])
    img.thumbnail((W, H), PILImage.ANTIALIAS)
    return img


def get_new_filename(etudid):
    """Constructs a random filename to store a new image.
    The path is constructed as: Fxx/etudid
    """
    dept = g.scodoc_dept
    return find_new_dir() + dept + "_" + str(etudid)


def find_new_dir():
    """select randomly a new subdirectory to store a new file.
    We define 100 subdirectories named from F00 to F99.
    Returns a path relative to the PHOTO_DIR.
    """
    d = "F" + "%02d" % random.randint(0, 99)
    path = os.path.join(PHOTO_DIR, d)
    if not os.path.exists(path):
        # ensure photos directory exists
        if not os.path.exists(PHOTO_DIR):
            os.mkdir(PHOTO_DIR)
        # create subdirectory
        log("creating directory %s" % path)
        os.mkdir(path)
    return d + "/"


def copy_portal_photo_to_fs(etud):
    """Copy the photo from portal (distant website) to local fs.
    Returns rel. path or None if copy failed, with a diagnostic message
    """
    sco_etud.format_etud_ident(etud)
    url = photo_portal_url(etud)
    if not url:
        return None, "%(nomprenom)s: pas de code NIP" % etud
    portal_timeout = sco_preferences.get_preference("portal_timeout")
    f = None
    try:
        log("copy_portal_photo_to_fs: getting %s" % url)
        r = requests.get(url, timeout=portal_timeout)
    except:
        # log("download failed: exception:\n%s" % traceback.format_exc())
        # log("called from:\n" + "".join(traceback.format_stack()))
        log("copy_portal_photo_to_fs: error.")
        return None, "%s: erreur chargement de %s" % (etud["nomprenom"], url)
    if r.status_code != 200:
        log(f"copy_portal_photo_to_fs: download failed {r.status_code }")
        return None, "%s: erreur chargement de %s" % (etud["nomprenom"], url)
    data = r.content  # image bytes
    try:
        status, diag = store_photo(etud, data)
    except:
        status = 0
        diag = "Erreur chargement photo du portail"
        log("copy_portal_photo_to_fs: failure (exception in store_photo)!")
    if status == 1:
        log("copy_portal_photo_to_fs: copied %s" % url)
        return photo_pathname(etud), "%s: photo chargée" % etud["nomprenom"]
    else:
        return None, "%s: <b>%s</b>" % (etud["nomprenom"], diag)
