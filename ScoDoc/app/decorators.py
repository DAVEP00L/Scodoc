# -*- coding: UTF-8 -*
"""Decorators for permissions, roles and ScoDoc7 Zope compatibility
"""
import functools
from functools import wraps
import inspect
import types
import logging

import werkzeug
from werkzeug.exceptions import BadRequest
import flask
from flask import g, current_app, request
from flask import abort, url_for, redirect
from flask_login import current_user
from flask_login import login_required
import flask_login

import app
from app.auth.models import User
import app.scodoc.sco_utils as scu


class ZUser(object):
    "Emulating Zope User"

    def __init__(self):
        "create, based on `flask_login.current_user`"
        self.username = current_user.user_name

    def __str__(self):
        return self.username

    def has_permission(self, perm, dept=None):
        """check if this user as the permission `perm`
        in departement given by `g.scodoc_dept`.
        """
        raise NotImplementedError()


def scodoc(func):
    """Décorateur pour toutes les fonctions ScoDoc
    Affecte le département à g
    et ouvre la connexion à la base

    Set `g.scodoc_dept` and `g.scodoc_dept_id` if `scodoc_dept` is present
    in the argument (for routes like
    `/<scodoc_dept>/Scolarite/sco_exemple`).
    """

    @wraps(func)
    def scodoc_function(*args, **kwargs):
        # print("@scodoc")
        # interdit les POST si pas loggué
        if (
            request.method == "POST"
            and not current_user.is_authenticated
            and not request.form.get(
                "__ac_password"
            )  # exception pour compat API ScoDoc7
        ):
            current_app.logger.info(
                "POST by non authenticated user (request.form=%s)",
                str(request.form)[:2048],
            )
            return redirect(
                url_for(
                    "auth.login",
                    message="La page a expiré. Identifiez-vous et recommencez l'opération",
                )
            )
        if "scodoc_dept" in kwargs:
            dept_acronym = kwargs["scodoc_dept"]
            # current_app.logger.info("setting dept to " + dept_acronym)
            app.set_sco_dept(dept_acronym)
            del kwargs["scodoc_dept"]
        elif not hasattr(g, "scodoc_dept"):
            # current_app.logger.info("setting dept to None")
            g.scodoc_dept = None
            g.scodoc_dept_id = -1  # invalide

        return func(*args, **kwargs)

    return scodoc_function


def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            scodoc_dept = getattr(g, "scodoc_dept", None)
            if not current_user.has_permission(permission, scodoc_dept):
                abort(403)
            return f(*args, **kwargs)

        return login_required(decorated_function)

    return decorator


def permission_required_compat_scodoc7(permission):
    """Décorateur pour les fonctions utilisées comme API dans ScoDoc 7
    Comme @permission_required mais autorise de passer directement
    les informations d'auth en paramètres:
        __ac_name, __ac_password
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # cherche les paramètre d'auth:
            # print("@permission_required_compat_scodoc7")
            auth_ok = False
            if request.method == "GET":
                user_name = request.args.get("__ac_name")
                user_password = request.args.get("__ac_password")
            elif request.method == "POST":
                user_name = request.form.get("__ac_name")
                user_password = request.form.get("__ac_password")
            else:
                abort(405)  # method not allowed
            if user_name and user_password:
                u = User.query.filter_by(user_name=user_name).first()
                if u and u.check_password(user_password):
                    auth_ok = True
                    flask_login.login_user(u)
            # reprend le chemin classique:
            scodoc_dept = getattr(g, "scodoc_dept", None)

            if not current_user.has_permission(permission, scodoc_dept):
                abort(403)
            if auth_ok:
                return f(*args, **kwargs)
            else:
                return login_required(f)(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(f):
    from app.auth.models import Permission

    return permission_required(Permission.ScoSuperAdmin)(f)


def scodoc7func(func):
    """Décorateur pour intégrer les fonctions Zope 2 de ScoDoc 7.
    Les paramètres de la query string deviennent des (keywords) paramètres de la fonction.
    """

    @wraps(func)
    def scodoc7func_decorator(*args, **kwargs):
        """Decorator allowing legacy Zope published methods to be called via Flask
        routes without modification.

        There are two cases: the function can be called
        1. via a Flask route ("top level call")
        2.  or be called directly from Python.

        """
        # print("@scodoc7func")
        # Détermine si on est appelé via une route ("toplevel")
        # ou par un appel de fonction python normal.
        top_level = not hasattr(g, "scodoc7_decorated")
        if not top_level:
            # ne "redécore" pas
            return func(*args, **kwargs)
        g.scodoc7_decorated = True
        # --- Emulate Zope's REQUEST
        # REQUEST = ZRequest()
        # g.zrequest = REQUEST
        # args from query string (get) or form (post)
        req_args = scu.get_request_args()
        ## --- Add positional arguments
        pos_arg_values = []
        argspec = inspect.getfullargspec(func)
        # current_app.logger.info("argspec=%s" % str(argspec))
        nb_default_args = len(argspec.defaults) if argspec.defaults else 0
        if nb_default_args:
            arg_names = argspec.args[:-nb_default_args]
        else:
            arg_names = argspec.args
        for arg_name in arg_names:  # pour chaque arg de la fonction vue
            if arg_name == "REQUEST":  # ne devrait plus arriver !
                # debug check, TODO remove after tests
                raise ValueError("invalid REQUEST parameter !")
            else:
                # peut produire une KeyError s'il manque un argument attendu:
                v = req_args[arg_name]
                # try to convert all arguments to INTEGERS
                # necessary for db ids and boolean values
                try:
                    v = int(v)
                except ValueError:
                    pass
                pos_arg_values.append(v)
        # current_app.logger.info("pos_arg_values=%s" % pos_arg_values)
        # current_app.logger.info("req_args=%s" % req_args)
        # Add keyword arguments
        if nb_default_args:
            for arg_name in argspec.args[-nb_default_args:]:
                # if arg_name == "REQUEST":  # special case
                #    kwargs[arg_name] = REQUEST
                if arg_name in req_args:
                    # set argument kw optionnel
                    v = req_args[arg_name]
                    # try to convert all arguments to INTEGERS
                    # necessary for db ids and boolean values
                    try:
                        v = int(v)
                    except (ValueError, TypeError):
                        pass
                    kwargs[arg_name] = v
        # current_app.logger.info(
        #    "scodoc7func_decorator: top_level=%s, pos_arg_values=%s, kwargs=%s"
        #    % (top_level, pos_arg_values, kwargs)
        # )
        value = func(*pos_arg_values, **kwargs)

        if not top_level:
            return value
        else:
            if isinstance(value, werkzeug.wrappers.response.Response):
                return value  # redirected
            # Build response, adding collected http headers:
            headers = []
            kw = {"response": value, "status": 200}
            # if g.zrequest:
            #     headers = g.zrequest.RESPONSE.headers
            #     if not headers:
            #         # no customized header, speedup:
            #         return value
            #     if "content-type" in headers:
            #         kw["mimetype"] = headers["content-type"]
            r = flask.Response(**kw)
            for h in headers:
                r.headers[h] = headers[h]
            return r

    return scodoc7func_decorator
