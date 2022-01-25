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

"""Dump base de données pour debug et support technique

Le principe est le suivant:
 1- S'il existe une base en cours d'anonymisation, s'arrête et affiche un msg d'erreur l'utilisateur,
    qui peut décider de la supprimer.

 2- ScoDoc lance un script qui duplique la base (la copie de SCORT devient ANORT)
     -  (si elle existe deja, s'arrête)
createdb -E UTF-8 ANORT
pg_dump SCORT | psql ANORT


 3- ScoDoc lance le script d'anonymisation config/anonymize_db.py qui:
     - vide ou anonymise certaines colonnes
     - dump cette base modifiée
     - supprime cette base.

 4- La copie dump anonymisé est uploadée.


"""
import os
import fcntl
import subprocess
import requests

from flask_login import current_user

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc import html_sco_header
from app.scodoc import sco_preferences
from app.scodoc import sco_users
import sco_version
from app.scodoc.sco_exceptions import ScoValueError

SCO_DUMP_LOCK = "/tmp/scodump.lock"


def sco_dump_and_send_db():
    """Dump base de données et l'envoie anonymisée pour debug"""
    H = [html_sco_header.sco_header(page_title="Assistance technique")]
    # get currect (dept) DB name:
    cursor = ndb.SimpleQuery("SELECT current_database()", {})
    db_name = cursor.fetchone()[0]
    ano_db_name = "ANO" + db_name
    # Lock
    try:
        x = open(SCO_DUMP_LOCK, "w+")
        fcntl.flock(x, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        raise ScoValueError(
            "Un envoi de la base "
            + db_name
            + " est déjà en cours, re-essayer plus tard"
        )

    try:
        # Drop if exists
        _drop_ano_db(ano_db_name)

        # Duplicate database
        _duplicate_db(db_name, ano_db_name)

        # Anonymisation
        _anonymize_db(ano_db_name)

        # Send
        r = _send_db(ano_db_name)
        if (
            r.status_code
            == requests.codes.INSUFFICIENT_STORAGE  # pylint: disable=no-member
        ):
            H.append(
                """<p class="warning">
            Erreur: espace serveur trop plein.
            Merci de contacter <a href="mailto:{0}">{0}</a></p>""".format(
                    scu.SCO_DEV_MAIL
                )
            )
        elif r.status_code == requests.codes.OK:  # pylint: disable=no-member
            H.append("""<p>Opération effectuée.</p>""")
        else:
            H.append(
                """<p class="warning">
            Erreur: code <tt>{0} {1}</tt>
            Merci de contacter <a href="mailto:{2}">{2}</a></p>""".format(
                    r.status_code, r.reason, scu.SCO_DEV_MAIL
                )
            )

    finally:
        # Drop anonymized database
        # XXX _drop_ano_db(ano_db_name)
        # Remove lock
        fcntl.flock(x, fcntl.LOCK_UN)

    log("sco_dump_and_send_db: done.")
    return "\n".join(H) + html_sco_header.sco_footer()


def _duplicate_db(db_name, ano_db_name):
    """Create new database, and copy old one into"""
    cmd = ["createdb", "-E", "UTF-8", ano_db_name]
    log("sco_dump_and_send_db/_duplicate_db: {}".format(cmd))
    try:
        _ = subprocess.check_output(cmd)
    except subprocess.CalledProcessError as e:
        log("sco_dump_and_send_db: exception createdb {}".format(e))
        raise ScoValueError(
            "erreur lors de la creation de la base {}".format(ano_db_name)
        )

    cmd = "pg_dump {} | psql {}".format(db_name, ano_db_name)
    log("sco_dump_and_send_db/_duplicate_db: {}".format(cmd))
    try:
        _ = subprocess.check_output(cmd, shell=1)
    except subprocess.CalledProcessError as e:
        log("sco_dump_and_send_db: exception {}".format(e))
        raise ScoValueError(
            "erreur lors de la duplication de la base {} vers {}".format(
                db_name, ano_db_name
            )
        )


def _anonymize_db(ano_db_name):
    """Anonymize a departement database"""
    cmd = os.path.join(scu.SCO_TOOLS_DIR, "anonymize_db.py")
    log("_anonymize_db: {}".format(cmd))
    try:
        _ = subprocess.check_output([cmd, ano_db_name])
    except subprocess.CalledProcessError as e:
        log("sco_dump_and_send_db: exception in anonymisation: {}".format(e))
        raise ScoValueError(
            "erreur lors de l'anonymisation de la base {}".format(ano_db_name)
        )


def _get_scodoc_serial():
    try:
        with open(os.path.join(scu.SCODOC_VERSION_DIR, "scodoc.sn")) as f:
            return int(f.read())
    except:
        return 0


def _send_db(ano_db_name):
    """Dump this (anonymized) database and send it to tech support"""
    log(f"dumping anonymized database {ano_db_name}")
    try:
        dump = subprocess.check_output(
            f"pg_dump --format=custom {ano_db_name}", shell=1
        )
    except subprocess.CalledProcessError as e:
        log(f"sco_dump_and_send_db: exception in anonymisation: {e}")
        raise ScoValueError(f"erreur lors de l'anonymisation de la base {ano_db_name}")

    log("uploading anonymized dump...")
    files = {"file": (ano_db_name + ".dump", dump)}
    r = requests.post(
        scu.SCO_DUMP_UP_URL,
        files=files,
        data={
            "dept_name": sco_preferences.get_preference("DeptName"),
            "serial": _get_scodoc_serial(),
            "sco_user": str(current_user),
            "sent_by": sco_users.user_info(str(current_user))["nomcomplet"],
            "sco_version": sco_version.SCOVERSION,
            "sco_fullversion": scu.get_scodoc_version(),
        },
    )
    return r


def _drop_ano_db(ano_db_name):
    """drop temp database if it exists"""
    existing_databases = [
        s.split("|")[0].strip()
        for s in subprocess.check_output(["psql", "-l"])
        .decode(scu.SCO_ENCODING)
        .split("\n")[3:]
    ]
    if ano_db_name not in existing_databases:
        log("_drop_ano_db: no temp db, nothing to drop")
        return
    cmd = ["dropdb", ano_db_name]
    log("sco_dump_and_send_db: {}".format(cmd))
    try:
        _ = subprocess.check_output(cmd)
    except subprocess.CalledProcessError as e:
        log("sco_dump_and_send_db: exception dropdb {}".format(e))
        raise ScoValueError(
            "erreur lors de la suppression de la base {}".format(ano_db_name)
        )
