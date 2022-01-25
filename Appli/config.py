# -*- coding: UTF-8 -*

import os
import uuid
from dotenv import load_dotenv

BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASEDIR, ".env"))


class Config:
    """General configuration. Mostly loaded from environment via .env"""

    SQLALCHEMY_DATABASE_URI = None  # set in subclass
    FLASK_ENV = None  # # set in subclass
    SECRET_KEY = os.environ.get("SECRET_KEY") or "90e01e75831e4176a3c70d29564b425f"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOG_TO_STDOUT = os.environ.get("LOG_TO_STDOUT")
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 25))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS") is not None
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    LANGUAGES = ["fr", "en"]  # unused for now
    SCODOC_ADMIN_MAIL = os.environ.get("SCODOC_ADMIN_MAIL")
    SCODOC_ADMIN_LOGIN = os.environ.get("SCODOC_ADMIN_LOGIN") or "admin"
    ADMINS = [SCODOC_ADMIN_MAIL]
    SCODOC_ERR_MAIL = os.environ.get("SCODOC_ERR_MAIL")
    BOOTSTRAP_SERVE_LOCAL = os.environ.get("BOOTSTRAP_SERVE_LOCAL")
    SCODOC_DIR = os.environ.get("SCODOC_DIR", "/opt/scodoc")
    SCODOC_VAR_DIR = os.environ.get("SCODOC_VAR_DIR", "/opt/scodoc-data")
    SCODOC_LOG_FILE = os.path.join(SCODOC_VAR_DIR, "log", "scodoc.log")
    # evite confusion avec le log nginx scodoc_error.log:
    SCODOC_ERR_FILE = os.path.join(SCODOC_VAR_DIR, "log", "scodoc_exc.log")
    #
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # Flask uploads (16Mo, en ligne avec nginx)

    # STATIC_URL_PATH = "/ScoDoc/static"
    # static_folder = "stat"
    # SERVER_NAME = os.environ.get("SERVER_NAME")


class ProdConfig(Config):
    FLASK_ENV = "production"
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SCODOC_DATABASE_URI") or "postgresql:///SCODOC"
    )
    PREFERRED_URL_SCHEME = "https"


class DevConfig(Config):
    FLASK_ENV = "development"
    DEBUG = True
    TESTING = False
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SCODOC_DATABASE_URI") or "postgresql:///SCODOC_DEV"
    )
    SECRET_KEY = os.environ.get("DEV_SECRET_KEY") or "bb3faec7d9a34eb68a8e3e710087d87a"


class TestConfig(DevConfig):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SCODOC_TEST_DATABASE_URI") or "postgresql:///SCODOC_TEST"
    )
    SERVER_NAME = os.environ.get("SCODOC_TEST_SERVER_NAME") or "test.gr"
    DEPT_TEST = "TEST_"  # nom du département, ne pas l'utiliser pour un "vrai"
    SECRET_KEY = os.environ.get("TEST_SECRET_KEY") or "c7ecff5db1594c208f573ff30e0f6bca"


mode = os.environ.get("FLASK_ENV", "production")
if mode == "production":
    RunningConfig = ProdConfig
elif mode == "development":
    RunningConfig = DevConfig
elif mode == "test":
    RunningConfig = TestConfig
