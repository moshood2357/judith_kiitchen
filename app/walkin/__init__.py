from flask import Blueprint

walkin_bp = Blueprint("walkin", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401
