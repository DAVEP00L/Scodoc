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

"""Fonctions sur les moduleimpl
"""

from flask_login import current_user

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app.scodoc.sco_permissions import Permission
from app.scodoc.sco_exceptions import ScoValueError, AccessDenied
from app import log
from app.scodoc import scolog
from app.scodoc import sco_formsemestre
from app.scodoc import sco_cache

# --- Gestion des "Implémentations de Modules"
# Un "moduleimpl" correspond a la mise en oeuvre d'un module
# dans une formation spécifique, à une date spécifique.
_moduleimplEditor = ndb.EditableTable(
    "notes_moduleimpl",
    "moduleimpl_id",
    (
        "moduleimpl_id",
        "module_id",
        "formsemestre_id",
        "responsable_id",
        "computation_expr",
    ),
)

_modules_enseignantsEditor = ndb.EditableTable(
    "notes_modules_enseignants",
    None,  # pas d'id dans cette Table d'association
    (
        "moduleimpl_id",  # associe moduleimpl
        "ens_id",  # a l'id de l'enseignant (User.id)
    ),
)


def do_moduleimpl_create(args):
    "create a moduleimpl"
    cnx = ndb.GetDBConnexion()
    r = _moduleimplEditor.create(cnx, args)
    sco_cache.invalidate_formsemestre(
        formsemestre_id=args["formsemestre_id"]
    )  # > creation moduleimpl
    return r


def do_moduleimpl_delete(oid, formsemestre_id=None):
    "delete moduleimpl (desinscrit tous les etudiants)"
    cnx = ndb.GetDBConnexion()
    # --- desinscription des etudiants
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = (
        "DELETE FROM notes_moduleimpl_inscription WHERE moduleimpl_id=%(moduleimpl_id)s"
    )
    cursor.execute(req, {"moduleimpl_id": oid})
    # --- suppression des enseignants
    cursor.execute(
        "DELETE FROM notes_modules_enseignants WHERE moduleimpl_id=%(moduleimpl_id)s",
        {"moduleimpl_id": oid},
    )
    # --- suppression des references dans les absences
    cursor.execute(
        "UPDATE absences SET moduleimpl_id=NULL WHERE moduleimpl_id=%(moduleimpl_id)s",
        {"moduleimpl_id": oid},
    )
    # --- destruction du moduleimpl
    _moduleimplEditor.delete(cnx, oid)
    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > moduleimpl_delete


def moduleimpl_list(moduleimpl_id=None, formsemestre_id=None, module_id=None):
    "list moduleimpls"
    args = locals()
    cnx = ndb.GetDBConnexion()
    modimpls = _moduleimplEditor.list(cnx, args)
    # Ajoute la liste des enseignants
    for mo in modimpls:
        mo["ens"] = do_ens_list(args={"moduleimpl_id": mo["moduleimpl_id"]})
    return modimpls


def do_moduleimpl_edit(args, formsemestre_id=None, cnx=None):
    "edit a moduleimpl"
    if not cnx:
        cnx = ndb.GetDBConnexion()
    _moduleimplEditor.edit(cnx, args)

    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > modif moduleimpl


def moduleimpl_withmodule_list(
    moduleimpl_id=None, formsemestre_id=None, module_id=None
):
    """Liste les moduleimpls et ajoute dans chacun
    l'UE, la matière et le module auxquels ils appartiennent.
    Tri la liste par semestre/UE/numero_matiere/numero_module.

    Attention: Cette fonction fait partie de l'API ScoDoc 7 et est publiée.
    """
    from app.scodoc import sco_edit_ue
    from app.scodoc import sco_edit_matiere
    from app.scodoc import sco_edit_module

    modimpls = moduleimpl_list(
        **{
            "moduleimpl_id": moduleimpl_id,
            "formsemestre_id": formsemestre_id,
            "module_id": module_id,
        }
    )
    ues = {}
    matieres = {}
    modules = {}
    for mi in modimpls:
        module_id = mi["module_id"]
        if not mi["module_id"] in modules:
            modules[module_id] = sco_edit_module.module_list(
                args={"module_id": module_id}
            )[0]
        mi["module"] = modules[module_id]
        ue_id = mi["module"]["ue_id"]
        if not ue_id in ues:
            ues[ue_id] = sco_edit_ue.ue_list(args={"ue_id": ue_id})[0]
        mi["ue"] = ues[ue_id]
        matiere_id = mi["module"]["matiere_id"]
        if not matiere_id in matieres:
            matieres[matiere_id] = sco_edit_matiere.matiere_list(
                args={"matiere_id": matiere_id}
            )[0]
        mi["matiere"] = matieres[matiere_id]

    # tri par semestre/UE/numero_matiere/numero_module
    modimpls.sort(
        key=lambda x: (
            x["ue"]["numero"],
            x["ue"]["ue_id"],
            x["matiere"]["numero"],
            x["matiere"]["matiere_id"],
            x["module"]["numero"],
            x["module"]["code"],
        )
    )

    return modimpls


def moduleimpls_in_external_ue(ue_id):
    """List of modimpls in this ue"""
    cursor = ndb.SimpleQuery(
        """SELECT DISTINCT mi.*
        FROM notes_ue u, notes_moduleimpl mi, notes_modules m
        WHERE u.is_external is true
        AND  mi.module_id = m.id AND m.ue_id = %(ue_id)s
        """,
        {"ue_id": ue_id},
    )
    return cursor.dictfetchall()


def do_moduleimpl_inscription_list(moduleimpl_id=None, etudid=None):
    "list moduleimpl_inscriptions"
    args = locals()
    cnx = ndb.GetDBConnexion()
    return _moduleimpl_inscriptionEditor.list(cnx, args)


def moduleimpl_listeetuds(moduleimpl_id):
    "retourne liste des etudids inscrits a ce module"
    req = """SELECT DISTINCT Im.etudid 
    FROM notes_moduleimpl_inscription Im, 
    notes_formsemestre_inscription Isem, 
    notes_moduleimpl M 
    WHERE Isem.etudid = Im.etudid 
    and Im.moduleimpl_id = M.id 
    and M.id = %(moduleimpl_id)s
    """
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    cursor.execute(req, {"moduleimpl_id": moduleimpl_id})
    res = cursor.fetchall()
    return [x[0] for x in res]


def do_moduleimpl_inscrit_tout_semestre(moduleimpl_id, formsemestre_id):
    "inscrit tous les etudiants inscrit au semestre a ce module"
    # UNUSED
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    req = """INSERT INTO notes_moduleimpl_inscription
                            (moduleimpl_id, etudid)
                SELECT %(moduleimpl_id)s, I.etudid
                FROM  notes_formsemestre_inscription I
                WHERE I.formsemestre_id=%(formsemestre_id)s
    """
    args = {"moduleimpl_id": moduleimpl_id, "formsemestre_id": formsemestre_id}
    cursor.execute(req, args)


# --- Inscriptions aux modules
_moduleimpl_inscriptionEditor = ndb.EditableTable(
    "notes_moduleimpl_inscription",
    "moduleimpl_inscription_id",
    ("moduleimpl_inscription_id", "etudid", "moduleimpl_id"),
)


def do_moduleimpl_inscription_create(args, formsemestre_id=None):
    "create a moduleimpl_inscription"
    cnx = ndb.GetDBConnexion()
    r = _moduleimpl_inscriptionEditor.create(cnx, args)
    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > moduleimpl_inscription
    scolog.logdb(
        cnx,
        method="moduleimpl_inscription",
        etudid=args["etudid"],
        msg="inscription module %s" % args["moduleimpl_id"],
        commit=False,
    )
    return r


def do_moduleimpl_inscription_delete(oid, formsemestre_id=None):
    "delete moduleimpl_inscription"
    cnx = ndb.GetDBConnexion()
    _moduleimpl_inscriptionEditor.delete(cnx, oid)
    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > moduleimpl_inscription


def do_moduleimpl_inscrit_etuds(moduleimpl_id, formsemestre_id, etudids, reset=False):
    """Inscrit les etudiants (liste d'etudids) a ce module.
    Si reset, desinscrit tous les autres.
    """
    from app.scodoc import sco_formsemestre_inscriptions

    # Verifie qu'ils sont tous bien inscrits au semestre
    for etudid in etudids:
        insem = sco_formsemestre_inscriptions.do_formsemestre_inscription_list(
            args={"formsemestre_id": formsemestre_id, "etudid": etudid}
        )
        if not insem:
            raise ScoValueError("%s n'est pas inscrit au semestre !" % etudid)

    # Desinscriptions
    if reset:
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        cursor.execute(
            "delete from notes_moduleimpl_inscription where moduleimpl_id = %(moduleimpl_id)s",
            {"moduleimpl_id": moduleimpl_id},
        )
    # Inscriptions au module:
    inmod_set = set(
        [
            # hum ?
            x["etudid"]
            for x in do_moduleimpl_inscription_list(moduleimpl_id=moduleimpl_id)
        ]
    )
    for etudid in etudids:
        # deja inscrit ?
        if not etudid in inmod_set:
            do_moduleimpl_inscription_create(
                {"moduleimpl_id": moduleimpl_id, "etudid": etudid},
                formsemestre_id=formsemestre_id,
            )

    sco_cache.invalidate_formsemestre(
        formsemestre_id=formsemestre_id
    )  # > moduleimpl_inscrit_etuds


def do_ens_list(*args, **kw):
    "liste les enseignants d'un moduleimpl (pas le responsable)"
    cnx = ndb.GetDBConnexion()
    ens = _modules_enseignantsEditor.list(cnx, *args, **kw)
    return ens


def do_ens_edit(*args, **kw):
    "edit ens"
    cnx = ndb.GetDBConnexion()
    _modules_enseignantsEditor.edit(cnx, *args, **kw)


def do_ens_create(args):
    "create ens"
    cnx = ndb.GetDBConnexion()
    r = _modules_enseignantsEditor.create(cnx, args)
    return r


def can_change_module_resp(moduleimpl_id):
    """Check if current user can modify module resp. (raise exception if not).
    = Admin, et dir des etud. (si option l'y autorise)
    """
    M = moduleimpl_withmodule_list(moduleimpl_id=moduleimpl_id)[0]
    # -- check lock
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
    if not sem["etat"]:
        raise ScoValueError("Modification impossible: semestre verrouille")
    # -- check access
    # admin ou resp. semestre avec flag resp_can_change_resp
    if not current_user.has_permission(Permission.ScoImplement) and (
        (current_user.id not in sem["responsables"]) or (not sem["resp_can_change_ens"])
    ):
        raise AccessDenied("Modification impossible pour %s" % current_user)
    return M, sem


def can_change_ens(moduleimpl_id, raise_exc=True):
    "check if current user can modify ens list (raise exception if not)"
    M = moduleimpl_withmodule_list(moduleimpl_id=moduleimpl_id)[0]
    # -- check lock
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
    if not sem["etat"]:
        if raise_exc:
            raise ScoValueError("Modification impossible: semestre verrouille")
        else:
            return False
    # -- check access
    # admin, resp. module ou resp. semestre
    if (
        current_user.id != M["responsable_id"]
        and not current_user.has_permission(Permission.ScoImplement)
        and (current_user.id not in sem["responsables"])
    ):
        if raise_exc:
            raise AccessDenied("Modification impossible pour %s" % current_user)
        else:
            return False
    return M, sem
