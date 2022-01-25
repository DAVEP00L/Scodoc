"""api.__init__
"""

from flask import Blueprint

bp = Blueprint("api", __name__)

from app.api import sco_api
from app.api import tokens
