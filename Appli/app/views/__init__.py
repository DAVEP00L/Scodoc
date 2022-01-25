# -*- coding: UTF-8 -*
"""ScoDoc Flask views
"""
import datetime

from flask import Blueprint
from flask import g, current_app
from flask_login import current_user

from app import db
from app.scodoc import notesdb as ndb

scodoc_bp = Blueprint("scodoc", __name__)
scolar_bp = Blueprint("scolar", __name__)
notes_bp = Blueprint("notes", __name__)
users_bp = Blueprint("users", __name__)
absences_bp = Blueprint("absences", __name__)

from app.views import scodoc, notes, scolar, absences, users


# Cette fonction est bien appelée avant toutes les requêtes
# de tous les blueprints
# mais apparemment elle n'a pas acces aux arguments
@scodoc_bp.before_app_request
def start_scodoc_request():
    """Affecte toutes les requêtes, de tous les blueprints"""
    # current_app.logger.info(f"start_scodoc_request")
    ndb.open_db_connection()
    if current_user and current_user.is_authenticated:
        current_user.last_seen = datetime.datetime.utcnow()
        db.session.commit()
    # caches locaux (durée de vie=la requête en cours)
    g.stored_get_formsemestre = {}
    # g.stored_etud_info = {} optim en cours, voir si utile


@scodoc_bp.teardown_app_request
def close_dept_db_connection(arg):
    # current_app.logger.info("close_db_connection")
    ndb.close_db_connection()
