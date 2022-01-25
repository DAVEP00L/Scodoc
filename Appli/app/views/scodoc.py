# -*- mode: python -*-
# -*- coding: utf-8 -*-

##############################################################################
#
# ScoDoc
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

"""
Module main: page d'accueil, avec liste des départements

Emmanuel Viennet, 2021
"""
from app.auth.models import User
import os

import flask
from flask import abort, flash, url_for, redirect, render_template, send_file
from flask import request
from flask.app import Flask
import flask_login
from flask_login.utils import login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from werkzeug.exceptions import BadRequest, NotFound
from wtforms import SelectField, SubmitField
from wtforms.fields import IntegerField
from wtforms.fields.simple import BooleanField, StringField, TextAreaField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo

import app
from app.models import Departement, Identite
from app.models import FormSemestre, NotesFormsemestreInscription
from app.models import ScoDocSiteConfig
import sco_version
from app.scodoc import sco_logos
from app.scodoc import sco_find_etud
from app.scodoc import sco_utils as scu
from app.decorators import (
    admin_required,
    scodoc7func,
    scodoc,
    permission_required_compat_scodoc7,
)
from app.scodoc.sco_exceptions import AccessDenied
from app.scodoc.sco_permissions import Permission
from app.views import scodoc_bp as bp


@bp.route("/")
@bp.route("/ScoDoc")
@bp.route("/ScoDoc/index")
def index():
    "Page d'accueil: liste des départements"
    depts = (
        Departement.query.filter_by(visible=True).order_by(Departement.acronym).all()
    )
    return render_template(
        "scodoc.html",
        title=sco_version.SCONAME,
        current_app=flask.current_app,
        depts=depts,
        Permission=Permission,
    )


# Renvoie les url /ScoDoc/RT/ vers /ScoDoc/RT/Scolarite
@bp.route("/ScoDoc/<scodoc_dept>/")
def index_dept(scodoc_dept):
    return redirect(url_for("scolar.index_html", scodoc_dept=scodoc_dept))


@bp.route("/ScoDoc/table_etud_in_accessible_depts", methods=["POST"])
@login_required
def table_etud_in_accessible_depts():
    """recherche étudiants sur plusieurs départements"""
    return sco_find_etud.table_etud_in_accessible_depts(expnom=request.form["expnom"])


# Fonction d'API accessible sans aucun authentification
@bp.route("/ScoDoc/get_etud_dept")
def get_etud_dept():
    """Returns the dept acronym (eg "GEII") of an etud (identified by etudid,
    code_nip ou code_ine in the request).
    Ancienne API: ramène la chaine brute, texte sans JSON ou XML.
    """
    if "etudid" in request.args:
        # zero ou une réponse:
        etuds = [Identite.query.get(request.args["etudid"])]
    elif "code_nip" in request.args:
        # il peut y avoir plusieurs réponses si l'étudiant est passé par plusieurs départements
        etuds = Identite.query.filter_by(code_nip=request.args["code_nip"]).all()
    elif "code_ine" in request.args:
        etuds = Identite.query.filter_by(code_ine=request.args["code_ine"]).all()
    else:
        raise BadRequest(
            "missing argument (expected one among: etudid, code_nip or code_ine)"
        )
    if not etuds:
        raise NotFound("student not found")
    elif len(etuds) == 1:
        last_etud = etuds[0]
    else:
        # inscriptions dans plusieurs departements: cherche la plus recente
        last_etud = None
        last_date = None
        for etud in etuds:
            inscriptions = NotesFormsemestreInscription.query.filter_by(
                etudid=etud.id
            ).all()
            for ins in inscriptions:
                date_fin = FormSemestre.query.get(ins.formsemestre_id).date_fin
                if (last_date is None) or date_fin > last_date:
                    last_date = date_fin
                    last_etud = etud
        if not last_etud:
            # est présent dans plusieurs semestres mais inscrit dans aucun !
            # le choix a peu d'importance...
            last_etud = etuds[-1]

    return Departement.query.get(last_etud.dept_id).acronym


# Bricolage pour le portail IUTV avec ScoDoc 7: (DEPRECATED: NE PAS UTILISER !)
@bp.route(
    "/ScoDoc/search_inscr_etud_by_nip", methods=["GET"]
)  # pour compat anciens clients PHP
@scodoc
@scodoc7func
def search_inscr_etud_by_nip(code_nip, format="json", __ac_name="", __ac_password=""):
    auth_ok = False
    user_name = __ac_name
    user_password = __ac_password
    if user_name and user_password:
        u = User.query.filter_by(user_name=user_name).first()
        if u and u.check_password(user_password):
            auth_ok = True
            flask_login.login_user(u)
    if not auth_ok:
        abort(403)
    else:
        return sco_find_etud.search_inscr_etud_by_nip(code_nip=code_nip, format=format)


@bp.route("/ScoDoc/about")
@bp.route("/ScoDoc/Scolarite/<scodoc_dept>/about")
def about(scodoc_dept=None):
    "version info"
    return render_template(
        "about.html",
        version=scu.get_scodoc_version(),
        news=sco_version.SCONEWS,
        logo=scu.icontag("borgne_img"),
    )


# ---- CONFIGURATION


class ScoDocConfigurationForm(FlaskForm):
    "Panneau de configuration général"

    bonus_sport_func_name = SelectField(
        label="Fonction de calcul des bonus sport&culture",
        choices=[
            (x, x if x else "Aucune")
            for x in ScoDocSiteConfig.get_bonus_sport_func_names()
        ],
    )

    logo_header = FileField(
        label="Modifier l'image:",
        description="logo placé en haut des documents PDF",
        validators=[
            FileAllowed(
                scu.LOGOS_IMAGES_ALLOWED_TYPES,
                f"n'accepte que les fichiers image <tt>{','.join([e for e in scu.LOGOS_IMAGES_ALLOWED_TYPES])}</tt>",
            )
        ],
    )

    logo_footer = FileField(
        label="Modifier l'image:",
        description="logo placé en pied des documents PDF",
        validators=[
            FileAllowed(
                scu.LOGOS_IMAGES_ALLOWED_TYPES,
                f"n'accepte que les fichiers image <tt>{','.join([e for e in scu.LOGOS_IMAGES_ALLOWED_TYPES])}</tt>",
            )
        ],
    )

    submit = SubmitField("Enregistrer")


# Notes pour variables config: (valeurs par défaut des paramètres de département)
# Chaines simples
# SCOLAR_FONT = "Helvetica"
# SCOLAR_FONT_SIZE = 10
# SCOLAR_FONT_SIZE_FOOT = 6
# INSTITUTION_NAME = "<b>Institut Universitaire de Technologie - Université Georges Perec</b>"
# INSTITUTION_ADDRESS = "Web <b>www.sor.bonne.top</b> - 11, rue Simon Crubelier  - 75017 Paris"
# INSTITUTION_CITY = "Paris"
# Textareas:
# DEFAULT_PDF_FOOTER_TEMPLATE = "Edité par %(scodoc_name)s le %(day)s/%(month)s/%(year)s à %(hour)sh%(minute)s sur %(server_url)s"

# Booléens
# always_require_ine

# Logos:
# LOGO_FOOTER*, LOGO_HEADER*


@bp.route("/ScoDoc/configuration", methods=["GET", "POST"])
@admin_required
def configuration():
    "Panneau de configuration général"
    form = ScoDocConfigurationForm(
        bonus_sport_func_name=ScoDocSiteConfig.get_bonus_sport_func_name(),
    )
    if form.validate_on_submit():
        ScoDocSiteConfig.set_bonus_sport_func(form.bonus_sport_func_name.data)
        if form.logo_header.data:
            sco_logos.store_image(
                form.logo_header.data, os.path.join(scu.SCODOC_LOGOS_DIR, "logo_header")
            )
        if form.logo_footer.data:
            sco_logos.store_image(
                form.logo_footer.data, os.path.join(scu.SCODOC_LOGOS_DIR, "logo_footer")
            )
        app.clear_scodoc_cache()
        flash(f"Configuration enregistrée")
        return redirect(url_for("scodoc.index"))

    return render_template(
        "configuration.html",
        title="Configuration ScoDoc",
        form=form,
        scodoc_dept=None,
    )


def _return_logo(logo_type="header", scodoc_dept=""):
    # stockée dans /opt/scodoc-data/config/logos donc servie manuellement ici
    filename = sco_logos.get_logo_filename(logo_type, scodoc_dept)
    if filename:
        extension = os.path.splitext(filename)[1]
        return send_file(filename, mimetype=f"image/{extension}")
    else:
        return ""


@bp.route("/ScoDoc/logo_header")
@bp.route("/ScoDoc/<scodoc_dept>/logo_header")
def logo_header(scodoc_dept=""):
    "Image logo header"
    # "/opt/scodoc-data/config/logos/logo_header")
    return _return_logo(logo_type="header", scodoc_dept=scodoc_dept)


@bp.route("/ScoDoc/logo_footer")
@bp.route("/ScoDoc/<scodoc_dept>/logo_footer")
def logo_footer(scodoc_dept=""):
    "Image logo footer"
    return _return_logo(logo_type="footer", scodoc_dept=scodoc_dept)


# essais
# @bp.route("/testlog")
# def testlog():
#     import time
#     from flask import current_app
#     from app import log

#     log(f"testlog called: handlers={current_app.logger.handlers}")
#     current_app.logger.debug(f"testlog message DEBUG")
#     current_app.logger.info(f"testlog message INFO")
#     current_app.logger.warning(f"testlog message WARNING")
#     current_app.logger.error(f"testlog message ERROR")
#     current_app.logger.critical(f"testlog message CRITICAL")
#     raise SyntaxError("une erreur de syntaxe")
#     return "testlog completed at " + str(time.time())
