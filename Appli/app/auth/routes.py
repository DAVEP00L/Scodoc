# -*- coding: UTF-8 -*
"""
auth.routes.py
"""

from app.scodoc.sco_exceptions import ScoValueError
from flask import current_app, g, flash, render_template
from flask import redirect, url_for, request
from flask_login.utils import login_required
from werkzeug.urls import url_parse
from flask_login import login_user, logout_user, current_user

from app import db
from app.auth import bp
from app.auth.forms import (
    LoginForm,
    UserCreationForm,
    ResetPasswordRequestForm,
    ResetPasswordForm,
    DeactivateUserForm,
)
from app.auth.models import Permission
from app.auth.models import User
from app.auth.email import send_password_reset_email
from app.decorators import admin_required
from app.decorators import permission_required

_ = lambda x: x  # sans babel
_l = _


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("scodoc.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(user_name=form.user_name.data).first()
        if user is None or not user.check_password(form.password.data):
            current_app.logger.info("login: invalid (%s)", form.user_name.data)
            flash(_("Nom ou mot de passe invalide"))
            return redirect(url_for("auth.login"))
        login_user(user, remember=form.remember_me.data)
        current_app.logger.info("login: success (%s)", form.user_name.data)
        next_page = request.args.get("next")
        if not next_page or url_parse(next_page).netloc != "":
            next_page = url_for("scodoc.index")
        return redirect(next_page)
    message = request.args.get("message", "")
    return render_template(
        "auth/login.html", title=_("Sign In"), form=form, message=message
    )


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("scodoc.index"))


@bp.route("/create_user", methods=["GET", "POST"])
@admin_required
def create_user():
    "Form creating new user"
    form = UserCreationForm()
    if form.validate_on_submit():
        user = User(user_name=form.user_name.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("User {} created".format(user.user_name))
        return redirect(url_for("scodoc.index"))
    return render_template(
        "auth/register.html", title=u"Création utilisateur", form=form
    )


@bp.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    """Form demande renvoi de mot de passe par mail
    Si l'utilisateur est déjà authentifié, le renvoie simplement sur
    la page d'accueil.
    """
    if current_user.is_authenticated:
        return redirect(url_for("scodoc.index"))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        users = User.query.filter_by(email=form.email.data).all()
        if len(users) == 1:
            send_password_reset_email(users[0])
        elif len(users) > 1:
            current_app.logger.info(
                "reset_password_request: multiple users with email '{}' (ignoring)".format(
                    form.email.data
                )
            )
        else:
            current_app.logger.info(
                "reset_password_request: for unkown user '{}'".format(form.email.data)
            )
        flash(
            _("Voir les instructions envoyées par mail (pensez à regarder vos spams)")
        )
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/reset_password_request.html", title=_("Reset Password"), form=form
    )


@bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("scodoc.index"))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for("scodoc.index"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(_("Votre mot de passe a été changé."))
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form, user=user)
