# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Definition of ScoDoc default roles
"""

from app.scodoc.sco_permissions import Permission as p

SCO_ROLES_DEFAULTS = {
    "Observateur": (p.ScoObservateur,),
    "Ens": (
        p.ScoAbsAddBillet,
        p.ScoAbsChange,
        p.ScoEnsView,
        p.ScoEntrepriseView,
        p.ScoEtudAddAnnotations,
        p.ScoObservateur,
        p.ScoUsersView,
        p.ScoView,
    ),
    "Secr": (
        p.ScoAbsAddBillet,
        p.ScoAbsChange,
        p.ScoEditApo,
        p.ScoEntrepriseChange,
        p.ScoEntrepriseView,
        p.ScoEtudAddAnnotations,
        p.ScoEtudChangeAdr,
        p.ScoObservateur,
        p.ScoUsersView,
        p.ScoView,
    ),
    # Admin est le chef du département, pas le "super admin"
    # on doit donc lister toutes ses permissions:
    "Admin": (
        p.ScoAbsAddBillet,
        p.ScoAbsChange,
        p.ScoChangeFormation,
        p.ScoChangePreferences,
        p.ScoEditAllEvals,
        p.ScoEditAllNotes,
        p.ScoEditApo,
        p.ScoEditFormationTags,
        p.ScoEnsView,
        p.ScoEntrepriseChange,
        p.ScoEntrepriseView,
        p.ScoEtudAddAnnotations,
        p.ScoEtudChangeAdr,
        p.ScoEtudChangeGroups,
        p.ScoEtudInscrit,
        p.ScoImplement,
        p.ScoObservateur,
        p.ScoUsersAdmin,
        p.ScoUsersView,
        p.ScoView,
    ),
    # RespPE est le responsable poursuites d'études
    # il peut ajouter des tags sur les formations:
    # (doit avoir un rôle Ens en plus !)
    "RespPe": (p.ScoEditFormationTags,),
    # Super Admin est un root: création/suppression de départements
    # _tous_ les droits
    # Afin d'avoir tous les droits, il ne doit pas être asscoié à un département
    "SuperAdmin": p.ALL_PERMISSIONS,
}
