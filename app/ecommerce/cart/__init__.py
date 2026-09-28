
from flask import Blueprint

cart_bp = Blueprint(
    "cart",
    __name__,
    url_prefix="/cart",
    template_folder="templates"
)

from . import routes
