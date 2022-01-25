# -*- coding: UTF-8 -*
# pylint: disable=invalid-name

import datetime
import os
import socket
import sys
import time
import traceback

import logging
from logging.handlers import SMTPHandler, WatchedFileHandler

from flask import current_app, g, request
from flask import Flask
from flask import abort, has_request_context, jsonify
from flask import render_template
from flask.logging import default_handler
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_caching import Cache
import sqlalchemy

from app.scodoc.sco_exceptions import (
    AccessDenied,
    ScoGenError,
    ScoValueError,
    APIInvalidParams,
)
from config import DevConfig
import sco_version

db = SQLAlchemy()
migrate = Migrate(compare_type=True)
login = LoginManager()
login.login_view = "auth.login"
login.login_message = "Identifiez-vous pour accéder à cette page."
mail = Mail()
bootstrap = Bootstrap()
moment = Moment()

cache = Cache(  # XXX TODO: configuration file
    config={
        # see https://flask-caching.readthedocs.io/en/latest/index.html#configuring-flask-caching
        "CACHE_TYPE": "RedisCache",
        "CACHE_DEFAULT_TIMEOUT": 0,  # by default, never expire
    }
)


def handle_sco_value_error(exc):
    return render_template("sco_value_error.html", exc=exc), 404


def handle_access_denied(exc):
    return render_template("error_access_denied.html", exc=exc), 403


def internal_server_error(e):
    """Bugs scodoc, erreurs 500"""
    # note that we set the 500 status explicitly
    return (
        render_template(
            "error_500.html",
            SCOVERSION=sco_version.SCOVERSION,
            date=datetime.datetime.now().isoformat(),
        ),
        500,
    )


def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def render_raw_html(template_filename: str, **args) -> str:
    """Load and render an HTML file _without_ using Flask
    Necessary for 503 error mesage, when DB is down and Flask may be broken.
    """
    template_path = os.path.join(
        current_app.config["SCODOC_DIR"],
        "app",
        current_app.template_folder,
        template_filename,
    )
    with open(template_path) as f:
        txt = f.read().format(**args)
    return txt


def postgresql_server_error(e):
    """Erreur de connection au serveur postgresql (voir notesdb.open_db_connection)"""
    return render_raw_html("error_503.html", SCOVERSION=sco_version.SCOVERSION), 503


class LogRequestFormatter(logging.Formatter):
    """Ajoute URL et remote_addr for logging"""

    def format(self, record):
        if has_request_context():
            record.url = request.url
            record.remote_addr = request.remote_addr
        else:
            record.url = None
            record.remote_addr = None
        record.sco_user = current_user
        if has_request_context():
            record.sco_admin_mail = current_app.config["SCODOC_ADMIN_MAIL"]
        else:
            record.sco_admin_mail = "(pas de requête)"

        return super().format(record)


class LogExceptionFormatter(logging.Formatter):
    """Formatteur pour les exceptions: ajoute détails"""

    def format(self, record):
        if has_request_context():
            record.url = request.url
            record.remote_addr = request.environ.get(
                "HTTP_X_FORWARDED_FOR", request.remote_addr
            )
            record.http_referrer = request.referrer
            record.http_method = request.method
            if request.method == "GET":
                record.http_params = str(request.args)
            else:
                # rep = reprlib.Repr()  # abbrège
                record.http_params = str(request.form)[:2048]
        else:
            record.url = None
            record.remote_addr = None
            record.http_referrer = None
            record.http_method = None
            record.http_params = None
        record.sco_user = current_user

        if has_request_context():
            record.sco_admin_mail = current_app.config["SCODOC_ADMIN_MAIL"]
        else:
            record.sco_admin_mail = "(pas de requête)"
        return super().format(record)


class ScoSMTPHandler(SMTPHandler):
    def getSubject(self, record: logging.LogRecord) -> str:
        stack_summary = traceback.extract_tb(record.exc_info[2])
        frame_summary = stack_summary[-1]
        subject = f"ScoExc({sco_version.SCOVERSION}): {record.exc_info[0].__name__} in {frame_summary.name} {frame_summary.filename}"

        return subject


class ReverseProxied(object):
    """Adaptateur wsgi qui nous permet d'avoir toutes les URL calculées en https
    sauf quand on est en dev.
    La variable HTTP_X_FORWARDED_PROTO est positionnée par notre config nginx"""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        scheme = environ.get("HTTP_X_FORWARDED_PROTO")
        if scheme:
            environ["wsgi.url_scheme"] = scheme  # ou forcer à https ici ?
        return self.app(environ, start_response)


def create_app(config_class=DevConfig):
    app = Flask(__name__, static_url_path="/ScoDoc/static", static_folder="static")
    app.wsgi_app = ReverseProxied(app.wsgi_app)
    app.logger.setLevel(logging.DEBUG)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    mail.init_app(app)
    bootstrap.init_app(app)
    moment.init_app(app)
    cache.init_app(app)
    sco_cache.CACHE = cache

    app.register_error_handler(ScoGenError, handle_sco_value_error)
    app.register_error_handler(ScoValueError, handle_sco_value_error)
    app.register_error_handler(AccessDenied, handle_access_denied)
    app.register_error_handler(500, internal_server_error)
    app.register_error_handler(503, postgresql_server_error)
    app.register_error_handler(APIInvalidParams, handle_invalid_usage)

    from app.auth import bp as auth_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.views import scodoc_bp
    from app.views import scolar_bp
    from app.views import notes_bp
    from app.views import users_bp
    from app.views import absences_bp
    from app.api import bp as api_bp

    # https://scodoc.fr/ScoDoc
    app.register_blueprint(scodoc_bp)
    # https://scodoc.fr/ScoDoc/RT/Scolarite/...
    app.register_blueprint(scolar_bp, url_prefix="/ScoDoc/<scodoc_dept>/Scolarite")
    # https://scodoc.fr/ScoDoc/RT/Scolarite/Notes/...
    app.register_blueprint(notes_bp, url_prefix="/ScoDoc/<scodoc_dept>/Scolarite/Notes")
    # https://scodoc.fr/ScoDoc/RT/Scolarite/Users/...
    app.register_blueprint(users_bp, url_prefix="/ScoDoc/<scodoc_dept>/Scolarite/Users")
    # https://scodoc.fr/ScoDoc/RT/Scolarite/Absences/...
    app.register_blueprint(
        absences_bp, url_prefix="/ScoDoc/<scodoc_dept>/Scolarite/Absences"
    )
    app.register_blueprint(api_bp, url_prefix="/ScoDoc/api")
    scodoc_log_formatter = LogRequestFormatter(
        "[%(asctime)s] %(sco_user)s@%(remote_addr)s requested %(url)s\n"
        "%(levelname)s: %(message)s"
    )
    # les champs additionnels sont définis dans LogRequestFormatter
    scodoc_exc_formatter = LogExceptionFormatter(
        "[%(asctime)s] %(sco_user)s@%(remote_addr)s requested %(url)s\n"
        "%(levelname)s: %(message)s\n"
        "Referrer: %(http_referrer)s\n"
        "Method: %(http_method)s\n"
        "Params: %(http_params)s\n"
        "Admin mail: %(sco_admin_mail)s\n"
    )
    if not app.testing:
        if not app.debug:
            # --- Config logs pour PRODUCTION
            # On supprime le logguer par défaut qui va vers stderr et pollue les logs systemes
            app.logger.removeHandler(default_handler)
            # --- Mail des messages ERROR et CRITICAL
            if app.config["MAIL_SERVER"]:
                auth = None
                if app.config["MAIL_USERNAME"] or app.config["MAIL_PASSWORD"]:
                    auth = (app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
                secure = None
                if app.config["MAIL_USE_TLS"]:
                    secure = ()
                host_name = socket.gethostname()
                mail_handler = ScoSMTPHandler(
                    mailhost=(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]),
                    fromaddr="no-reply@" + app.config["MAIL_SERVER"],
                    toaddrs=["exception@scodoc.org"],
                    subject="ScoDoc Exception",  # unused see ScoSMTPHandler
                    credentials=auth,
                    secure=secure,
                )
                mail_handler.setFormatter(scodoc_exc_formatter)
                mail_handler.setLevel(logging.ERROR)
                app.logger.addHandler(mail_handler)
        else:
            # Pour logs en DEV uniquement:
            default_handler.setFormatter(scodoc_log_formatter)

        # Config logs pour DEV et PRODUCTION
        # Configuration des logs (actifs aussi en mode development)
        # usually /opt/scodoc-data/log/scodoc.log:
        # rotated by logrotate
        file_handler = WatchedFileHandler(
            app.config["SCODOC_LOG_FILE"], encoding="utf-8"
        )
        file_handler.setFormatter(scodoc_log_formatter)
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        # Log pour les erreurs (exceptions) uniquement:
        # usually /opt/scodoc-data/log/scodoc_exc.log
        file_handler = WatchedFileHandler(
            app.config["SCODOC_ERR_FILE"], encoding="utf-8"
        )
        file_handler.setFormatter(scodoc_exc_formatter)
        file_handler.setLevel(logging.ERROR)
        app.logger.addHandler(file_handler)

        # app.logger.setLevel(logging.INFO)
        app.logger.info(f"{sco_version.SCONAME} {sco_version.SCOVERSION} startup")
        app.logger.info(
            f"create_app({config_class.__name__}, {config_class.SQLALCHEMY_DATABASE_URI})"
        )
    # ---- INITIALISATION SPECIFIQUES A SCODOC
    from app.scodoc import sco_bulletins_generator

    from app.scodoc.sco_bulletins_legacy import BulletinGeneratorLegacy
    from app.scodoc.sco_bulletins_standard import BulletinGeneratorStandard
    from app.scodoc.sco_bulletins_ucac import BulletinGeneratorUCAC

    # l'ordre est important, le premeir sera le "défaut" pour les nouveaux départements.
    sco_bulletins_generator.register_bulletin_class(BulletinGeneratorStandard)
    sco_bulletins_generator.register_bulletin_class(BulletinGeneratorLegacy)
    sco_bulletins_generator.register_bulletin_class(BulletinGeneratorUCAC)
    if app.testing or app.debug:
        from app.scodoc.sco_bulletins_example import BulletinGeneratorExample

        sco_bulletins_generator.register_bulletin_class(BulletinGeneratorExample)

    return app


def set_sco_dept(scodoc_dept: str):
    """Set global g object to given dept and open db connection if needed"""
    # Check that dept exists
    try:
        dept = Departement.query.filter_by(acronym=scodoc_dept).first()
    except sqlalchemy.exc.OperationalError:
        abort(503)
    if not dept:
        raise ScoValueError(f"Invalid dept: {scodoc_dept}")
    g.scodoc_dept = scodoc_dept  # l'acronyme
    g.scodoc_dept_id = dept.id  # l'id
    if not hasattr(g, "db_conn"):
        ndb.open_db_connection()
    if not hasattr(g, "stored_get_formsemestre"):
        g.stored_get_formsemestre = {}


def user_db_init():
    """Initialize the users database.
    Check that basic roles and admin user exist.
    """
    from app.auth.models import User, Role

    current_app.logger.info("Init User's db")
    # Create roles:
    Role.insert_roles()
    current_app.logger.info("created initial roles")
    # Ensure that admin exists
    admin_mail = current_app.config.get("SCODOC_ADMIN_MAIL")
    if admin_mail:
        admin_user_name = current_app.config["SCODOC_ADMIN_LOGIN"]
        user = User.query.filter_by(user_name=admin_user_name).first()
        if not user:
            user = User(user_name=admin_user_name, email=admin_mail)
            try:
                db.session.add(user)
                db.session.commit()
            except:
                db.session.rollback()
                raise
            current_app.logger.info(
                "created initial admin user, login: {u.user_name}, email: {u.email}".format(
                    u=user
                )
            )


def sco_db_insert_constants():
    """Initialize Sco database: insert some constants (modalités, ...)."""
    from app import models

    current_app.logger.info("Init Sco db")
    # Modalités:
    models.NotesFormModalite.insert_modalites()


def initialize_scodoc_database(erase=False, create_all=False):
    """Initialize the database for unit tests
    Starts from an existing database and create all necessary
    SQL tables and functions.
    If erase is True, _erase_ all database content.
    """
    from app import models

    # - ERASE (the truncation sql function has been defined above)
    if erase:
        truncate_database()
    # - Create all tables
    if create_all:
        # managed by migrations, except for TESTS
        db.create_all()
    # - Insert initial roles and create super-admin user
    user_db_init()
    # - Insert some constant values (modalites, ...)
    sco_db_insert_constants()
    # - Flush cache
    clear_scodoc_cache()


def truncate_database():
    """Erase content of all tables (including users !) from
    the current database.
    """
    # use a stored SQL function, see createtables.sql
    try:
        db.session.execute("SELECT truncate_tables('scodoc');")
        db.session.commit()
    except:
        db.session.rollback()
        raise


def clear_scodoc_cache():
    """Clear ScoDoc cache
    This cache (currently Redis) is persistent between invocation
    and it may be necessary to clear it during developement or tests.
    """
    # attaque directement redis, court-circuite ScoDoc:
    import redis

    r = redis.Redis()
    r.flushall()
    # Also clear local caches:
    sco_preferences.clear_base_preferences()


# --------- Logging
def log(msg: str, silent_test=True):
    """log a message.
    If Flask app, use configured logger, else stderr.
    """
    if silent_test and current_app and current_app.config["TESTING"]:
        return
    try:
        dept = getattr(g, "scodoc_dept", "")
        msg = f" ({dept}) {msg}"
    except RuntimeError:
        # Flask Working outside of application context.
        pass

    if current_app:
        current_app.logger.info(msg)
    else:
        sys.stdout.flush()
        sys.stderr.write(
            "[%s] scodoc: %s\n" % (time.strftime("%a %b %d %H:%M:%S %Y"), msg)
        )
        sys.stderr.flush()


# Debug: log call stack
def log_call_stack():
    log("Call stack:\n" + "\n".join(x.strip() for x in traceback.format_stack()[:-1]))


# Alarms by email:
def send_scodoc_alarm(subject, txt):
    from app.scodoc import sco_preferences
    from app import email

    sender = sco_preferences.get_preference("email_from_addr")
    email.send_email(subject, sender, ["exception@scodoc.org"], txt)


from app.models import Departement
from app.scodoc import notesdb as ndb, sco_preferences
from app.scodoc import sco_cache

# admin_role = Role.query.filter_by(name="SuperAdmin").first()
# if admin_role:
#     admin = (
#         User.query.join(UserRole)
#         .filter((UserRole.user_id == User.id) & (UserRole.role_id == admin_role.id))
#         .first()
#     )
# else:
#     click.echo(
#         "Warning: user database not initialized !\n (use: flask user-db-init)"
#     )
#     admin = None
