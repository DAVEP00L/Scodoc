# -*- mode: python -*-
# -*- coding: utf-8 -*-

"""Functions checking permissions for some common operations
"""
from flask import g
from flask_login import current_user

from app.auth.models import User

import app.scodoc.notesdb as ndb
from app.scodoc.sco_permissions import Permission
from app.scodoc import html_sco_header
from app.scodoc import sco_etud
from app.scodoc import sco_exceptions
from app.scodoc import sco_moduleimpl


def can_edit_notes(authuser, moduleimpl_id, allow_ens=True):
    """True if authuser can enter or edit notes in this module.
    If allow_ens, grant access to all ens in this module

    Si des décisions de jury ont déjà été saisies dans ce semestre,
    seul le directeur des études peut saisir des notes (et il ne devrait pas).
    """
    from app.scodoc import sco_formsemestre
    from app.scodoc import sco_parcours_dut

    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])
    if not sem["etat"]:
        return False  # semestre verrouillé

    if sco_parcours_dut.formsemestre_has_decisions(sem["formsemestre_id"]):
        # il y a des décisions de jury dans ce semestre !
        return (
            authuser.has_permission(Permission.ScoEditAllNotes)
            or authuser.id in sem["responsables"]
        )
    else:
        if (
            (not authuser.has_permission(Permission.ScoEditAllNotes))
            and authuser.id != M["responsable_id"]
            and authuser.id not in sem["responsables"]
        ):
            # enseignant (chargé de TD) ?
            if allow_ens:
                for ens in M["ens"]:
                    if ens["ens_id"] == authuser.id:
                        return True
            return False
        else:
            return True


def can_edit_evaluation(moduleimpl_id=None):
    """Vérifie que l'on a le droit de modifier, créer ou détruire une
    évaluation dans ce module.
    Sinon, lance une exception.
    (nb: n'implique pas le droit de saisir ou modifier des notes)
    """
    from app.scodoc import sco_formsemestre

    # acces pour resp. moduleimpl et resp. form semestre (dir etud)
    if moduleimpl_id is None:
        raise ValueError("no moduleimpl specified")  # bug
    M = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
    sem = sco_formsemestre.get_formsemestre(M["formsemestre_id"])

    if (
        current_user.has_permission(Permission.ScoEditAllEvals)
        or current_user.id == M["responsable_id"]
        or current_user.id in sem["responsables"]
    ):
        return True
    elif sem["ens_can_edit_eval"]:
        for ens in M["ens"]:
            if ens["ens_id"] == current_user.id:
                return True

    return False


def can_suppress_annotation(annotation_id):
    """True if current user can suppress this annotation
    Seuls l'auteur de l'annotation et le chef de dept peuvent supprimer
    une annotation.
    """
    cnx = ndb.GetDBConnexion()
    annos = sco_etud.etud_annotations_list(cnx, args={"id": annotation_id})
    if len(annos) != 1:
        raise sco_exceptions.ScoValueError("annotation inexistante !")
    anno = annos[0]
    return (current_user.user_name == anno["author"]) or current_user.has_permission(
        Permission.ScoEtudAddAnnotations
    )


def can_edit_suivi():
    """Vrai si l'utilisateur peut modifier les informations de suivi sur la page etud" """
    return current_user.has_permission(Permission.ScoEtudChangeAdr)


def can_validate_sem(formsemestre_id):
    "Vrai si utilisateur peut saisir decision de jury dans ce semestre"
    from app.scodoc import sco_formsemestre

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        return False  # semestre verrouillé

    return is_chef_or_diretud(sem)


def can_edit_pv(formsemestre_id):
    "Vrai si utilisateur peut editer un PV de jury de ce semestre"
    from app.scodoc import sco_formsemestre

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if is_chef_or_diretud(sem):
        return True
    # Autorise les secrétariats, repérés via la permission ScoEtudChangeAdr
    # (ceci nous évite d'ajouter une permission Zope aux installations existantes)
    return current_user.has_permission(Permission.ScoEtudChangeAdr)


def is_chef_or_diretud(sem):
    "Vrai si utilisateur est admin, chef dept ou responsable du semestre"
    if (
        current_user.has_permission(Permission.ScoImplement)
        or current_user.id in sem["responsables"]
    ):
        return True
    return False


def check_access_diretud(formsemestre_id, required_permission=Permission.ScoImplement):
    """Check if access granted: responsable or ScoImplement
    Return True|False, HTML_error_page
    """
    from app.scodoc import sco_formsemestre

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    header = html_sco_header.sco_header(page_title="Accès interdit")
    footer = html_sco_header.sco_footer()
    if (current_user.id not in sem["responsables"]) and not current_user.has_permission(
        required_permission
    ):
        return (
            False,
            "\n".join(
                [
                    header,
                    "<h2>Opération non autorisée pour %s</h2>" % current_user,
                    "<p>Responsable de ce semestre : <b>%s</b></p>"
                    % ", ".join(
                        [User.query.get(i).get_prenomnom() for i in sem["responsables"]]
                    ),
                    footer,
                ]
            ),
        )
    else:
        return True, ""


def can_change_groups(formsemestre_id):
    "Vrai si l'utilisateur peut changer les groupes dans ce semestre"
    from app.scodoc import sco_formsemestre

    sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    if not sem["etat"]:
        return False  # semestre verrouillé
    if current_user.has_permission(Permission.ScoEtudChangeGroups):
        return True  # admin, chef dept
    if current_user.id in sem["responsables"]:
        return True
    return False


def can_handle_passwd(user, allow_admindepts=False):
    """True if the current user can see or change passwd info of user.
    If allow_admindepts, allow Admin from all depts (so they can view users from other depts
    and add roles to them).
    user is a User instance.
    """
    if not user:
        return False
    if current_user.is_administrator():
        return True  # super admin
    # Anyone can change his own passwd (or see his informations)
    if user.user_name == current_user.user_name:
        return True
    # If don't have permission in the current dept, abort
    if not current_user.has_permission(Permission.ScoUsersAdmin, g.scodoc_dept):
        return False
    # Now check that current_user can manage users from this departement
    if not current_user.dept:
        return True  # if no dept, can access users from all depts !
    if (current_user.dept == user.dept) or allow_admindepts:
        return True
    else:
        return False
