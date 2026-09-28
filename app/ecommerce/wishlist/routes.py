from flask import jsonify, render_template, request
from flask_login import current_user

from app.utils.helpers import get_user_key
from app.extensions import db
from app.models import Wishlist, Product
from . import wishlist_bp


# =========================
# VIEW WISHLIST
# =========================
@wishlist_bp.route('/wishlist')
def view_wishlist():

    user_key = get_user_key()

    if current_user.is_authenticated:
        wishlist_items = (
            db.session.query(Wishlist, Product)
            .join(Product, Wishlist.product_id == Product.id)
            .filter(Wishlist.user_id == current_user.id)
            .all()
        )
    else:
        wishlist_items = (
            db.session.query(Wishlist, Product)
            .join(Product, Wishlist.product_id == Product.id)
            .filter(Wishlist.user_key == user_key)
            .all()
        )

    return render_template(
        "wishlist/wishlist.html",
        wishlist_items=wishlist_items
    )


# =========================
# ADD / TOGGLE WISHLIST
# =========================
@wishlist_bp.route('/add/<slug>', methods=['POST'])
def add_to_wishlist(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()
    user_key = get_user_key()

    if current_user.is_authenticated:
        item = Wishlist.query.filter_by(
            user_id=current_user.id,
            product_id=product.id
        ).first()
    else:
        item = Wishlist.query.filter_by(
            user_key=user_key,
            product_id=product.id
        ).first()

    if item:
        db.session.delete(item)
        action = "removed"
    else:
        db.session.add(Wishlist(
            user_id=current_user.id if current_user.is_authenticated else None,
            user_key=None if current_user.is_authenticated else user_key,
            product_id=product.id
        ))
        action = "added"

    db.session.commit()

    if current_user.is_authenticated:
        wishlist_count = Wishlist.query.filter_by(
            user_id=current_user.id
        ).count()
    else:
        wishlist_count = Wishlist.query.filter_by(
            user_key=user_key
        ).count()

    return jsonify({
        "success": True,
        "action": action,
        "wishlist_count": wishlist_count
    })


# =========================
# REMOVE FROM WISHLIST
# =========================
@wishlist_bp.route('/remove/<slug>', methods=['POST'])
def remove_from_wishlist(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()
    user_key = get_user_key()

    if current_user.is_authenticated:
        item = Wishlist.query.filter_by(
            user_id=current_user.id,
            product_id=product.id
        ).first()
    else:
        item = Wishlist.query.filter_by(
            user_key=user_key,
            product_id=product.id
        ).first()

    if item:
        db.session.delete(item)
        db.session.commit()

    if current_user.is_authenticated:
        wishlist_count = Wishlist.query.filter_by(
            user_id=current_user.id
        ).count()
    else:
        wishlist_count = Wishlist.query.filter_by(
            user_key=user_key
        ).count()

    return jsonify({
        "success": True,
        "message": "Item removed from wishlist",
        "wishlist_count": wishlist_count
    })