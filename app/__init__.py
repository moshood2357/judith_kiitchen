import os
import uuid

from dotenv import load_dotenv
import stripe

from flask import Flask, send_from_directory, session
from flask_ckeditor import CKEditor
from flask_compress import Compress
from flask_login import current_user
from flask_wtf import CSRFProtect
# from flask_socketio import SocketIO

from app.services.cart_service import get_cart_count, get_wishlist_count
from .extensions import db, migrate, login_manager
from app.models import Cart, CartItem, Wishlist, User

load_dotenv()

ckeditor = CKEditor()
csrf = CSRFProtect()



def create_app(config_class="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_class)

    app.config["SECRET_KEY"]              = os.environ.get("SECRET_KEY", "dev-only-key")
    app.config["IDEAL_POSTCODES_API_KEY"] = os.getenv("IDEAL_POSTCODES_API_KEY")
    app.config["STRIPE_SECRET_KEY"]       = os.getenv("STRIPE_SECRET_KEY")
    app.config["STRIPE_WEBHOOK_SECRET"]   = os.getenv("STRIPE_WEBHOOK_SECRET")
    app.config["BREVO_API_KEY"]           = os.getenv("BREVO_API_KEY")
    app.config["BREVO_SENDER_EMAIL"]      = os.getenv("BREVO_SENDER_EMAIL")
    app.config["ADMIN_EMAIL"]             = os.getenv("ADMIN_EMAIL", "info@r2systemsolution.co.uk")
    app.config["DOJO_API_KEY"]            = os.getenv("DOJO_API_KEY")
    app.config["DOJO_API_BASE"]           = os.getenv("DOJO_API_BASE")
    app.config["DOJO_WEBHOOK_SECRET"]     = os.getenv("DOJO_WEBHOOK_SECRET")

    app.config["GOOGLE_MAPS_API_KEY"] = os.environ.get("GOOGLE_MAPS_API_KEY")

    
    

    stripe.api_key = app.config["STRIPE_SECRET_KEY"]

    upload_folder = os.path.join(app.root_path, "static", "uploads")
    app.config["UPLOAD_FOLDER"] = upload_folder
    os.makedirs(upload_folder, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    ckeditor.init_app(app)
    csrf.init_app(app)
    Compress(app)
    

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_counts():
        return {
            "cart_count":     get_cart_count(),
            "wishlist_count": get_wishlist_count()
        }

    @app.context_processor
    def inject_cart_data():
        if current_user.is_authenticated:
            cart = Cart.query.filter_by(user_id=current_user.id).first()
            if cart:
                cart_product_ids = [
                    item[0] for item in
                    db.session.query(CartItem.product_id).filter_by(cart_id=cart.id).all()
                ]
            else:
                cart_product_ids = []
            return dict(cart_product_ids=cart_product_ids)
        return dict(cart_product_ids=[])

    @app.before_request
    def create_guest_session():
        if "guest_id" not in session:
            session["guest_id"] = str(uuid.uuid4())

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon"
        )

    from app.models import (
        User, Address, Category, Product,
        Cart, CartItem, Wishlist,
        Order, OrderItem, Payment,
        Review, Coupon, NewsletterSubscriber
    )

    from .main import main as main_bp
    from .admin import admin_bp
    from .auth import auth_bp
    from .api import api_bp
    from app.ecommerce.cart import cart_bp
    from app.ecommerce.wishlist import wishlist_bp
    from app.ecommerce.checkout import checkout_bp
    from app.ecommerce.orders import order_bp
    from app.kitchen import kitchen_bp
    from app.order_board import order_board_bp
    from app.walkin import walkin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(checkout_bp,  url_prefix="/checkout")
    app.register_blueprint(api_bp,       url_prefix="/api")
    app.register_blueprint(order_bp,     url_prefix="/orders")
    app.register_blueprint(kitchen_bp,   url_prefix="/kitchen")
    app.register_blueprint(order_board_bp, url_prefix="/order-board")
    app.register_blueprint(walkin_bp,    url_prefix="/walk-in")
    return app