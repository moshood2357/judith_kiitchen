from flask import Blueprint

checkout_bp = Blueprint("checkout", __name__, template_folder="templates")



from . import routes
