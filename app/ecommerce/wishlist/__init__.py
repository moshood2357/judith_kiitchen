
from flask import Blueprint

wishlist_bp = Blueprint(
    "wishlist",
    __name__,
    url_prefix="/wishlist",
    template_folder="templates"
)

from . import routes