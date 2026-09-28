from flask import Blueprint

kitchen_bp = Blueprint("kitchen", __name__, template_folder="templates")

from . import routes