# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Definition of ScoDoc permissions
    used by auth
"""

# Définition des permissions: ne pas changer les numéros ou l'ordre des lignes !
_SCO_PERMISSIONS = (
    # permission bit, symbol, description
    # ScoSuperAdmin est utilisé pour:
    #   - ZScoDoc: add/delete departments
    #   - tous rôles lors creation utilisateurs
    (1 << 1, "ScoSuperAdmin", "Super Administrateur"),
    (1 << 2, "ScoView", "Voir"),
    (1 << 3, "ScoEnsView", "Voir les parties pour les enseignants"),
    (1 << 4, "ScoObservateur", "Observer (accès lecture restreint aux bulletins)"),
    (1 << 5, "ScoUsersAdmin", "Gérer les utilisateurs"),
    (1 << 6, "ScoUsersView", "Voir les utilisateurs"),
    (1 << 7, "ScoChangePreferences", "Modifier les préférences"),
    (1 << 8, "ScoChangeFormation", "Changer les formations"),
    (1 << 9, "ScoEditFormationTags", "Tagguer les formations"),
    (1 << 10, "ScoEditAllNotes", "Modifier toutes les notes"),
    (1 << 11, "ScoEditAllEvals", "Modifier toutes les evaluations"),
    (1 << 12, "ScoImplement", "Mettre en place une formation (créer un semestre)"),
    (1 << 13, "ScoAbsChange", "Saisir des absences"),
    (1 << 14, "ScoAbsAddBillet", "Saisir des billets d'absences"),
    # changer adresse/photo ou pour envoyer bulletins par mail ou pour debouche
    (1 << 15, "ScoEtudChangeAdr", "Changer les addresses d'étudiants"),
    (1 << 16, "ScoEtudChangeGroups", "Modifier les groupes"),
    # aussi pour demissions, diplomes:
    (1 << 17, "ScoEtudInscrit", "Inscrire des étudiants"),
    # aussi pour archives:
    (1 << 18, "ScoEtudAddAnnotations", "Éditer les annotations"),
    (1 << 19, "ScoEntrepriseView", "Voir la section 'entreprises'"),
    (1 << 20, "ScoEntrepriseChange", "Modifier les entreprises"),
    (1 << 21, "ScoEditPVJury", "Éditer les PV de jury"),
    # ajouter maquettes Apogee (=> chef dept et secr):
    (1 << 22, "ScoEditApo", "Ajouter des maquettes Apogées"),
)


class Permission(object):
    "Permissions for ScoDoc"
    NBITS = 1  # maximum bits used (for formatting)
    ALL_PERMISSIONS = [-1]
    description = {}  # { symbol : blah blah }
    permission_by_name = {}  # { symbol : int }

    @staticmethod
    def init_permissions():
        for (perm, symbol, description) in _SCO_PERMISSIONS:
            setattr(Permission, symbol, perm)
            Permission.description[symbol] = description
            Permission.permission_by_name[symbol] = perm
        Permission.NBITS = len(_SCO_PERMISSIONS)

    @staticmethod
    def get_by_name(permission_name: str) -> int:
        """Return permission mode (integer bit field), or None if it doesn't exist."""
        return Permission.permission_by_name.get(permission_name)


Permission.init_permissions()
