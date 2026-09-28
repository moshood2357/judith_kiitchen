from flask import Blueprint

ecommerce = Blueprint("ecommerce", __name__)

from .cart import cart_bp
from .wishlist import wishlist_bp
from . import routes, checkout, orders