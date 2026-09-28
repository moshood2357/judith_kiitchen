from flask import Blueprint

order_board_bp = Blueprint("order_board", __name__, template_folder="templates")

from . import routes