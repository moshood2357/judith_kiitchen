
from flask import session
from flask_login import current_user

from app.models import Cart
from app.models import CartItem
from app.models import Wishlist
from app.extensions import db
from app.utils.helpers import get_user_key



def merge_cart(user_id, guest_key):
    guest_cart = Cart.query.filter_by(user_key=guest_key).first()
    user_cart = Cart.query.filter_by(user_id=user_id).first()

    if not guest_cart:
        return

    if not user_cart:
        guest_cart.user_id = user_id
        guest_cart.user_key = None
        db.session.commit()
        return

    # merge items
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


def merge_wishlist(user_id, guest_key):
    guest_items = Wishlist.query.filter_by(user_key=guest_key).all()

    for item in guest_items:
        exists = Wishlist.query.filter_by(
            user_id=user_id,
            product_id=item.product_id
        ).first()

        if not exists:
            db.session.add(Wishlist(
                user_id=user_id,
                product_id=item.product_id
            ))

    Wishlist.query.filter_by(user_key=guest_key).delete()
    db.session.commit()

    

# def get_wishlist_count():

#     user_key = get_user_key()

#     if current_user.is_authenticated:
#         return Wishlist.query.filter_by(user_id=current_user.id).count()

#     return Wishlist.query.filter_by(user_key=user_key).count()

def get_cart_count():

    user_key = get_user_key()

    if current_user.is_authenticated:
        return db.session.query(CartItem).join(Cart).filter(
            Cart.user_id == current_user.id
        ).count()

    return db.session.query(CartItem).join(Cart).filter(
        Cart.user_key == user_key
    ).count()



def get_wishlist_count():

    user_key = get_user_key()

    if current_user.is_authenticated:
        return Wishlist.query.filter_by(user_id=current_user.id).count()

    return Wishlist.query.filter_by(user_key=user_key).count()





def merge_guest_cart_to_user(user):

    guest_key = session.get("user_key")

    if not guest_key:
        return

    guest_cart = Cart.query.filter_by(user_key=guest_key).first()

    if not guest_cart:
        return

    # ensure user has a cart container
    user_cart = Cart.query.filter_by(user_id=user.id).first()

    if not user_cart:
        user_cart = Cart(user_id=user.id)
        db.session.add(user_cart)
        db.session.flush()  # ensures user_cart.id exists

    # merge items safely
    for item in guest_cart.items:

        existing = CartItem.query.filter_by(
            cart_id=user_cart.id,
            product_id=item.product_id
        ).first()

        if existing:
            existing.quantity += item.quantity
        else:
            db.session.add(CartItem(
                cart_id=user_cart.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                product_name=item.product_name,
                product_image=item.product_image
            ))

    # remove guest cart safely
    db.session.delete(guest_cart)

    db.session.commit()

    session.pop("user_key", None)