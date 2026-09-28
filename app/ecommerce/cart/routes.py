from itertools import product
import json

from flask import flash, redirect, render_template, jsonify, request, session, url_for
from flask_login import login_required, current_user

from app.utils.helpers import get_user_key
from . import cart_bp
from app.models import Product, CartItem, Cart, Wishlist, CheckoutDraft
from app.extensions import db

from flask_wtf.csrf import generate_csrf


# =========================
# VIEW CART
# =========================
@cart_bp.route('/')
def view_cart():

    user_key = get_user_key()

    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
    else:
        cart = Cart.query.filter_by(user_key=user_key).first()

    if not cart:
        return render_template('cart/cart.html', cart_items=[], total=0)

    cart_items = (
        db.session.query(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .filter(CartItem.cart_id == cart.id)
        .all()
    )

    total = sum(ci.quantity * p.price for ci, p in cart_items)

    return render_template(
        'cart/cart.html',
        cart_items=cart_items,
        total=total
    )


# =========================
# ADD TO CART
# =========================
@cart_bp.route('/add/<slug>', methods=['POST'])
def add_to_cart(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()
    source = request.form.get("source")

    user_key = get_user_key()

    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
    else:
        cart = Cart.query.filter_by(user_key=user_key).first()

    if not cart:
        if current_user.is_authenticated:
            cart = Cart(user_id=current_user.id)
        else:
            cart = Cart(user_key=user_key)

        db.session.add(cart)
        db.session.flush()

    item = CartItem.query.filter_by(
        cart_id=cart.id,
        product_id=product.id
    ).first()

    already_in_cart = item is not None

    if not item:
        db.session.add(CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=1,
            unit_price=product.price,
            from_wishlist=(source == "wishlist")
        ))

    if current_user.is_authenticated:
        Wishlist.query.filter_by(
            user_id=current_user.id,
            product_id=product.id
        ).delete()
    else:
        Wishlist.query.filter_by(
            user_key=user_key,
            product_id=product.id
        ).delete()

    db.session.commit()

    cart_count = db.session.query(
        db.func.coalesce(db.func.sum(CartItem.quantity), 0)
    ).filter_by(cart_id=cart.id).scalar() or 0

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
        "cart_count": cart_count,
        "already_in_cart": already_in_cart,
        "wishlist_count": wishlist_count
    })



# =========================
# REMOVE ITEM FROM CART
# =========================
@cart_bp.route('/remove/<int:item_id>', methods=['POST'])
def remove_item(item_id):

    user_key = get_user_key()

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        (
            (Cart.user_id == current_user.id)
            if current_user.is_authenticated
            else (Cart.user_key == user_key)
        )
    ).first_or_404()

    cart = item.cart
    slug = item.product.slug 


    db.session.delete(item)
    db.session.commit()

    cart_count = db.session.query(CartItem).filter_by(cart_id=cart.id).count()

    cart_total = db.session.query(
        db.func.sum(CartItem.quantity * Product.price)
    ).join(Product).filter(
        CartItem.cart_id == cart.id
    ).scalar() or 0

    return jsonify({
        "success": True,
        "cart_count": cart_count,
        "cart_total": cart_total,
         "slug": slug
    })



@cart_bp.route("/data")
def cart_data():
    user_key = get_user_key()

    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
    else:
        cart = Cart.query.filter_by(user_key=user_key).first()

    if not cart:
        return jsonify({"items": []})

    items = []

    for item in cart.items:
        product = item.product
        items.append({
            "id": item.id,
            "name": product.name,
            "price": item.unit_price,
            "quantity": item.quantity,
            "subtotal": item.unit_price * item.quantity,
            "image": product.image,
            "csrf": generate_csrf(),
            "slug": product.slug
        })

    return jsonify({"items": items})


@cart_bp.route("/data-count")
def cart_count():
    user_key = get_user_key()

    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
    else:
        cart = Cart.query.filter_by(user_key=user_key).first()

    if not cart:
        return jsonify({"cart_count": 0})

    return jsonify({"cart_count": len(cart.items)})


# =========================
# CHECKOUT START
# =========================
@cart_bp.route("/checkout/start")
def start_checkout():

    # =========================
    # IDENTIFY USER OR GUEST
    # =========================
    if current_user.is_authenticated:
        user_id = current_user.id
        guest_key = session.get("user_key")
    else:
        user_id = None
        guest_key = get_user_key()

    # =========================
    # MERGE GUEST CART → USER
    # =========================
    if current_user.is_authenticated and guest_key:

        guest_cart = Cart.query.filter_by(user_key=guest_key).first()
        user_cart = Cart.query.filter_by(user_id=user_id).first()

        if guest_cart:
            if not user_cart:
                guest_cart.user_id = user_id
                guest_cart.user_key = None
            else:
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

    # =========================
    # GET CART
    # =========================
    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=user_id).first()
    else:
        cart = Cart.query.filter_by(user_key=guest_key).first()

    if not cart or not cart.items:
        flash("Your cart is empty", "warning")
        return redirect(url_for("cart.view_cart"))

    # =========================
    # CREATE CHECKOUT DRAFT
    # =========================
    if current_user.is_authenticated:
        draft = CheckoutDraft.query.filter_by(user_id=user_id).first()
    else:
        draft = CheckoutDraft.query.filter_by(user_key=guest_key).first()

    if not draft:
        if current_user.is_authenticated:
            draft = CheckoutDraft(
                user_id=user_id,
                email=current_user.email
            )
        else:
            draft = CheckoutDraft(
                user_key=guest_key,
                email=session.get("guest_email")
            )

        db.session.add(draft)
        db.session.commit()

    # =========================
    # CART SNAPSHOT
    # =========================
    snapshot = []

    for item in cart.items:
        snapshot.append({
            "product_id": item.product_id,
            "name": item.product.name,
            "price": float(item.product.price),
            "quantity": item.quantity,
            "image": getattr(item.product, "image_url", None)
        })

    draft.cart_snapshot = json.dumps(snapshot)

    # =========================
    # SET SESSION
    # =========================
    session["checkout_id"] = draft.id

    db.session.commit()

    return redirect(url_for("checkout.details"))



# =========================
# INCREASE QTY
# =========================
@cart_bp.route('/increase/<int:item_id>', methods=['POST'])
def increase_qty(item_id):

    user_key = get_user_key()

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        (
            (Cart.user_id == current_user.id)
            if current_user.is_authenticated
            else (Cart.user_key == user_key)
        )
    ).first_or_404()

    item.quantity += 1
    db.session.commit()

    cart = item.cart

    cart_total = db.session.query(
        db.func.sum(CartItem.quantity * Product.price)
    ).join(Product).filter(
        CartItem.cart_id == cart.id
    ).scalar() or 0

    return jsonify({
        "success": True,
        "quantity": item.quantity,
        "subtotal": item.quantity * item.product.price,
        "deleted": False,
        "cart_total": cart_total
    })


# =========================
# DECREASE QTY
# =========================
@cart_bp.route('/decrease/<int:item_id>', methods=['POST'])
def decrease_qty(item_id):

    user_key = get_user_key()

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        (
            (Cart.user_id == current_user.id)
            if current_user.is_authenticated
            else (Cart.user_key == user_key)
        )
    ).first_or_404()

    cart = item.cart

    if item.quantity > 1:
        item.quantity -= 1
        db.session.commit()
        deleted = False
    else:
        db.session.delete(item)
        db.session.commit()
        deleted = True

    cart_total = db.session.query(
        db.func.sum(CartItem.quantity * Product.price)
    ).join(Product).filter(
        CartItem.cart_id == cart.id
    ).scalar() or 0

    return jsonify({
        "success": True,
        "quantity": item.quantity if not deleted else 0,
        "subtotal": item.quantity * item.product.price if not deleted else 0,
        "deleted": deleted,
        "cart_total": cart_total
    })