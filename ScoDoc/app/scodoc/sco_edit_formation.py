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

"""Ajout/Modification/Supression formations
(portage from DTML)
"""
import flask
from flask import g, url_for, request

import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu
from app import log
from app.scodoc.TrivialFormulator import TrivialFormulator, tf_error_message
from app.scodoc.sco_exceptions import ScoValueError, ScoLockedFormError

from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_edit_module
from app.scodoc import sco_edit_ue
from app.scodoc import sco_formations
from app.scodoc import sco_formsemestre
from app.scodoc import sco_news


def formation_delete(formation_id=None, dialog_confirmed=False):
    """Delete a formation"""
    F = sco_formations.formation_list(args={"formation_id": formation_id})
    if not F:
        raise ScoValueError("formation inexistante !")
    F = F[0]

    H = [
        html_sco_header.sco_header(page_title="Suppression d'une formation"),
        """<h2>Suppression de la formation %(titre)s (%(acronyme)s)</h2>""" % F,
    ]

    sems = sco_formsemestre.do_formsemestre_list({"formation_id": formation_id})
    if sems:
        H.append(
            """<p class="warning">Impossible de supprimer cette formation, car les sessions suivantes l'utilisent:</p>
<ul>"""
        )
        for sem in sems:
            H.append(
                '<li><a href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titremois)s</a></li>'
                % sem
            )
        H.append('</ul><p><a href="%s">Revenir</a></p>' % scu.NotesURL())
    else:
        if not dialog_confirmed:
            return scu.confirm_dialog(
                """<h2>Confirmer la suppression de la formation %(titre)s (%(acronyme)s) ?</h2>
    <p><b>Attention:</b> la suppression d'une formation est <b>irréversible</b> et implique la supression de toutes les UE, matières et modules de la formation !
</p>
                """
                % F,
                OK="Supprimer cette formation",
                cancel_url=scu.NotesURL(),
                parameters={"formation_id": formation_id},
            )
        else:
            do_formation_delete(F["formation_id"])
            H.append(
                """<p>OK, formation supprimée.</p>
    <p><a class="stdlink" href="%s">continuer</a></p>"""
                % scu.NotesURL()
            )

    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def do_formation_delete(oid):
    """delete a formation (and all its UE, matieres, modules)
    XXX delete all ues, will break if there are validations ! USE WITH CARE !
    """
    F = sco_formations.formation_list(args={"formation_id": oid})[0]
    if sco_formations.formation_has_locked_sems(oid):
        raise ScoLockedFormError()
    cnx = ndb.GetDBConnexion()
    # delete all UE in this formation
    ues = sco_edit_ue.ue_list({"formation_id": oid})
    for ue in ues:
        sco_edit_ue.do_ue_delete(ue["ue_id"], force=True)

    sco_formations._formationEditor.delete(cnx, oid)

    # news
    sco_news.add(
        typ=sco_news.NEWS_FORM,
        object=oid,
        text="Suppression de la formation %(acronyme)s" % F,
        max_frequency=3,
    )


def formation_create():
    """Creation d'une formation"""
    return formation_edit(create=True)


def formation_edit(formation_id=None, create=False):
    """Edit or create a formation"""
    if create:
        H = [
            html_sco_header.sco_header(page_title="Création d'une formation"),
            """<h2>Création d'une formation</h2>

<p class="help">Une "formation" décrit une filière, comme un DUT ou une Licence. La formation se subdivise en unités pédagogiques (UE, matières, modules). Elle peut se diviser en plusieurs semestres (ou sessions), qui seront mis en place séparément.
</p>

<p>Le <tt>titre</tt> est le nom complet, parfois adapté pour mieux distinguer les modalités ou versions de programme pédagogique. Le <tt>titre_officiel</tt> est le nom complet du diplôme, qui apparaitra sur certains PV de jury de délivrance du diplôme.
</p>
""",
        ]
        submitlabel = "Créer cette formation"
        initvalues = {"type_parcours": sco_codes_parcours.DEFAULT_TYPE_PARCOURS}
        is_locked = False
    else:
        # edit an existing formation
        F = sco_formations.formation_list(args={"formation_id": formation_id})
        if not F:
            raise ScoValueError("formation inexistante !")
        initvalues = F[0]
        is_locked = sco_formations.formation_has_locked_sems(formation_id)
        submitlabel = "Modifier les valeurs"
        H = [
            html_sco_header.sco_header(page_title="Modification d'une formation"),
            """<h2>Modification de la formation %(acronyme)s</h2>""" % initvalues,
        ]
        if is_locked:
            H.append(
                '<p class="warning">Attention: Formation verrouillée, le type de parcours ne peut être modifié.</p>'
            )

    tf = TrivialFormulator(
        request.base_url,
        scu.get_request_args(),
        (
            ("formation_id", {"default": formation_id, "input_type": "hidden"}),
            (
                "acronyme",
                {
                    "size": 12,
                    "explanation": "identifiant de la formation (par ex. DUT R&T)",
                    "allow_null": False,
                },
            ),
            (
                "titre",
                {
                    "size": 80,
                    "explanation": "nom complet de la formation (ex: DUT Réseaux et Télécommunications",
                    "allow_null": False,
                },
            ),
            (
                "titre_officiel",
                {
                    "size": 80,
                    "explanation": "nom officiel (pour les PV de jury)",
                    "allow_null": False,
                },
            ),
            (
                "type_parcours",
                {
                    "input_type": "menu",
                    "title": "Type de parcours",
                    "type": "int",
                    "allowed_values": sco_codes_parcours.FORMATION_PARCOURS_TYPES,
                    "labels": sco_codes_parcours.FORMATION_PARCOURS_DESCRS,
                    "explanation": "détermine notamment le nombre de semestres et les règles de validation d'UE et de semestres (barres)",
                    "readonly": is_locked,
                },
            ),
            (
                "formation_code",
                {
                    "size": 12,
                    "title": "Code formation",
                    "explanation": "code interne. Toutes les formations partageant le même code sont compatibles (compensation de semestres, capitalisation d'UE).  Laisser vide si vous ne savez pas, ou entrer le code d'une formation existante.",
                },
            ),
            (
                "code_specialite",
                {
                    "size": 12,
                    "title": "Code spécialité",
                    "explanation": "optionel: code utilisé pour échanger avec d'autres logiciels et identifiant la filière ou spécialité (exemple: ASUR). N'est utilisé que s'il n'y a pas de numéro de semestre.",
                },
            ),
        ),
        initvalues=initvalues,
        submitlabel=submitlabel,
    )
    if tf[0] == 0:
        return "\n".join(H) + tf[1] + html_sco_header.sco_footer()
    elif tf[0] == -1:
        return flask.redirect(scu.NotesURL())
    else:
        # check unicity : constraint UNIQUE(acronyme,titre,version)
        if create:
            version = 1
        else:
            version = initvalues["version"]
        args = {
            "acronyme": tf[2]["acronyme"],
            "titre": tf[2]["titre"],
            "version": version,
        }
        ndb.quote_dict(args)
        others = sco_formations.formation_list(args=args)
        if others and ((len(others) > 1) or others[0]["formation_id"] != formation_id):
            return (
                "\n".join(H)
                + tf_error_message(
                    "Valeurs incorrectes: il existe déjà une formation avec même titre, acronyme et version."
                )
                + tf[1]
                + html_sco_header.sco_footer()
            )
        #
        if create:
            formation_id = do_formation_create(tf[2])
        else:
            do_formation_edit(tf[2])
        return flask.redirect(
            url_for(
                "notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=formation_id
            )
        )


def do_formation_create(args):
    "create a formation"
    cnx = ndb.GetDBConnexion()
    # check unique acronyme/titre/version
    a = args.copy()
    if "formation_id" in a:
        del a["formation_id"]
    F = sco_formations.formation_list(args=a)
    if len(F) > 0:
        log("do_formation_create: error: %d formations matching args=%s" % (len(F), a))
        raise ScoValueError("Formation non unique (%s) !" % str(a))
    # Si pas de formation_code, l'enleve (default SQL)
    if "formation_code" in args and not args["formation_code"]:
        del args["formation_code"]
    #
    r = sco_formations._formationEditor.create(cnx, args)

    sco_news.add(
        typ=sco_news.NEWS_FORM,
        text="Création de la formation %(titre)s (%(acronyme)s)" % args,
        max_frequency=3,
    )
    return r


def do_formation_edit(args):
    "edit a formation"
    # log('do_formation_edit( args=%s )'%args)

    # On autorise  la modif de la formation meme si elle est verrouillee
    # car cela ne change que du cosmetique, (sauf eventuellement le code formation ?)
    # mais si verrouillée on ne peut changer le type de parcours
    if sco_formations.formation_has_locked_sems(args["formation_id"]):
        if "type_parcours" in args:
            del args["type_parcours"]
    # On ne peut jamais supprimer le code formation:
    if "formation_code" in args and not args["formation_code"]:
        del args["formation_code"]

    cnx = ndb.GetDBConnexion()
    sco_formations._formationEditor.edit(cnx, args)
    invalidate_sems_in_formation(args["formation_id"])


def invalidate_sems_in_formation(formation_id):
    "Invalide les semestres utilisant cette formation"
    for sem in sco_formsemestre.do_formsemestre_list(
        args={"formation_id": formation_id}
    ):
        sco_cache.invalidate_formsemestre(
            formsemestre_id=sem["formsemestre_id"]
        )  # > formation modif.


def module_move(module_id, after=0, redirect=1):
    """Move before/after previous one (decrement/increment numero)"""
    module = sco_edit_module.module_list({"module_id": module_id})[0]
    redirect = int(redirect)
    after = int(after)  # 0: deplace avant, 1 deplace apres
    if after not in (0, 1):
        raise ValueError('invalid value for "after"')
    formation_id = module["formation_id"]
    others = sco_edit_module.module_list({"matiere_id": module["matiere_id"]})
    # log('others=%s' % others)
    if len(others) > 1:
        idx = [p["module_id"] for p in others].index(module_id)
        # log('module_move: after=%s idx=%s' % (after, idx))
        neigh = None  # object to swap with
        if after == 0 and idx > 0:
            neigh = others[idx - 1]
        elif after == 1 and idx < len(others) - 1:
            neigh = others[idx + 1]
        if neigh:  #
            # swap numero between partition and its neighbor
            # log('moving module %s' % module_id)
            cnx = ndb.GetDBConnexion()
            module["numero"], neigh["numero"] = neigh["numero"], module["numero"]
            if module["numero"] == neigh["numero"]:
                neigh["numero"] -= 2 * after - 1
            sco_edit_module._moduleEditor.edit(cnx, module)
            sco_edit_module._moduleEditor.edit(cnx, neigh)

    # redirect to ue_list page:
    if redirect:
        return flask.redirect(
            url_for(
                "notes.ue_table", scodoc_dept=g.scodoc_dept, formation_id=formation_id
            )
        )


def ue_move(ue_id, after=0, redirect=1):
    """Move UE before/after previous one (decrement/increment numero)"""
    o = sco_edit_ue.ue_list({"ue_id": ue_id})[0]
    # log('ue_move %s (#%s) after=%s' % (ue_id, o['numero'], after))
    redirect = int(redirect)
    after = int(after)  # 0: deplace avant, 1 deplace apres
    if after not in (0, 1):
        raise ValueError('invalid value for "after"')
    formation_id = o["formation_id"]
    others = sco_edit_ue.ue_list({"formation_id": formation_id})
    if len(others) > 1:
        idx = [p["ue_id"] for p in others].index(ue_id)
        neigh = None  # object to swap with
        if after == 0 and idx > 0:
            neigh = others[idx - 1]
        elif after == 1 and idx < len(others) - 1:
            neigh = others[idx + 1]
        if neigh:  #
            # swap numero between partition and its neighbor
            # log('moving ue %s (neigh #%s)' % (ue_id, neigh['numero']))
            cnx = ndb.GetDBConnexion()
            o["numero"], neigh["numero"] = neigh["numero"], o["numero"]
            if o["numero"] == neigh["numero"]:
                neigh["numero"] -= 2 * after - 1
            sco_edit_ue._ueEditor.edit(cnx, o)
            sco_edit_ue._ueEditor.edit(cnx, neigh)
    # redirect to ue_list page
    if redirect:
        return flask.redirect(
            url_for(
                "notes.ue_table",
                scodoc_dept=g.scodoc_dept,
                formation_id=o["formation_id"],
            )
        )
