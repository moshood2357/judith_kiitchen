import re
import uuid

from flask_login import current_user
from flask import session
from app.models import Cart, CartItem
from app.extensions import db

def generate_slug(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    
    return f"{text}-{uuid.uuid4().hex[:6]}"




def get_user_key():
    if current_user.is_authenticated:
        return str(current_user.id)

    if "user_key" not in session:
        session["user_key"] = str(uuid.uuid4())

    return session["user_key"]


def merge_guest_to_user(user):
    guest_key = session.get("user_key")

    if not guest_key:
        return

    guest_cart = Cart.query.filter_by(user_key=guest_key).first()
    user_cart = Cart.query.filter_by(user_id=user.id).first()

    if guest_cart:

        # If user has no cart yet → assign guest cart
        if not user_cart:
            guest_cart.user_id = user.id
            guest_cart.user_key = None

        else:
            # Merge items
            for item in guest_cart.items:
                existing = CartItem.query.filter_by(
                    cart_id=user_cart.id,
                    product_id=item.product_id
                ).first()

                if existing:
                    existing.quantity += item.quantity
                else:
                    item.cart_id = user_cart.id

            db.session.delete(guest_cart)

        db.session.commit()

    session.pop("user_key", None)