"""
Walk-in (counter) orders for Judith's Kitchen.

Staff enter orders for customers who walk in without using the website.
Each one becomes a normal Order (fulfillment_type="walk_in", status=accepted,
payment_status=paid), so it shows on the kitchen display, goes through
Start Timer / Complete like any other order, and appears on the order board.

Routes (register with NO url_prefix):
    GET  /walk-in                 -> counter screen
    POST /walk-in                 -> create the order
    GET  /walk-in/ticket/<id>     -> big number to show / print for the customer

No schema change: Order.address_id is NOT NULL, so each walk-in gets a small
Address row holding the customer's name ("Walk-in" if none given).
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (Address, Category, Order, OrderItem, OrderStatus,
                        Payment, PaymentStatus, Product)
from . import walkin_bp

# ---- Settings -----------------------------------------------------------
# Who may create walk-in orders. Admins always can; add your kitchen/staff
# role names here if they are not admins.
STAFF_ROLES = ("admin", "staff", "kitchen")

PAYMENT_METHODS = {"cash": "Cash", "card": "Card (terminal)"}
DEFAULT_PREP_MINUTES = 15
STORE_COUNTRY = "United Kingdom"
# -------------------------------------------------------------------------


def is_staff():
    return current_user.is_authenticated and (
        current_user.is_admin or (current_user.role or "") in STAFF_ROLES
    )


def next_walkin_number():
    prefix = f"W{datetime.utcnow():%y%m%d}-"
    last = (Order.query
            .filter(Order.order_number.like(prefix + "%"))
            .order_by(Order.id.desc())
            .first())
    seq = int(last.order_number.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:03d}"


def unit_price(product):
    """Discount price when it's set and lower, otherwise the normal price."""
    if product.discount_price and product.discount_price < product.price:
        return product.discount_price
    return product.price


@walkin_bp.before_request
@login_required
def require_staff():
    if not is_staff():
        abort(403)


@walkin_bp.route("/", methods=["GET"])
def new_order():
    categories = (Category.query
                  .join(Product)
                  .filter(Product.is_active.is_(True))
                  .order_by(Category.name)
                  .distinct()
                  .all())
    menu = []
    for c in categories:
        products = [p for p in c.products if p.is_active]
        products.sort(key=lambda p: p.name)
        menu.append({
            "name": c.name,
            "products": [{"id": p.id, "name": p.name,
                          "price": f"{unit_price(p):.2f}"} for p in products],
        })
    return render_template("walkin/new.html", menu=menu,
                           payment_methods=PAYMENT_METHODS,
                           default_prep=DEFAULT_PREP_MINUTES)


@walkin_bp.route("/create", methods=["POST"])
def create_order():
    # ---- read + validate (never trust prices from the browser) ----------
    quantities = {}
    for key, value in request.form.items():
        if key.startswith("qty_"):
            try:
                pid, qty = int(key[4:]), int(value)
            except ValueError:
                continue
            if 0 < qty <= 50:
                quantities[pid] = qty

    if not quantities:
        flash("Add at least one item before placing the order.", "error")
        return redirect(url_for("walkin.new_order"))

    products = Product.query.filter(Product.id.in_(quantities),
                                    Product.is_active.is_(True)).all()
    if len(products) != len(quantities):
        flash("One of the items is no longer on the menu. Check the order and try again.", "error")
        return redirect(url_for("walkin.new_order"))

    method = request.form.get("payment_method", "cash")
    if method not in PAYMENT_METHODS:
        method = "cash"

    try:
        prep = int(request.form.get("prep_time", DEFAULT_PREP_MINUTES))
    except ValueError:
        prep = DEFAULT_PREP_MINUTES
    prep = max(1, min(prep, 180))

    name = (request.form.get("customer_name") or "").strip()[:150] or "Walk-in"
    note = (request.form.get("note") or "").strip()[:1000] or None

    subtotal = sum((unit_price(p) * quantities[p.id] for p in products), Decimal("0"))

    # ---- save -------------------------------------------------------------
    for attempt in range(3):  # retry if two tills grab the same number
        try:
            address = Address(full_name=name, phone="",
                              address_line_1="Walk-in (in store)",
                              city="In store", state="-", country=STORE_COUNTRY)
            db.session.add(address)
            db.session.flush()

            now = datetime.utcnow()
            order = Order(
                user_id=None,
                address_id=address.id,
                order_number=next_walkin_number(),
                subtotal=subtotal, shipping_fee=0, tax=0, total_amount=subtotal,
                delivery_method="walk_in",
                fulfillment_type="walk_in",
                status=OrderStatus.accepted,
                payment_status=PaymentStatus.paid,
                prep_time=prep,
                timer_status="pending",
                note=note,
                created_at=now,
            )
            db.session.add(order)
            db.session.flush()

            for p in products:
                db.session.add(OrderItem(
                    order_id=order.id, product_id=p.id,
                    quantity=quantities[p.id], price=unit_price(p),
                    product_name=p.name, product_image=p.image,
                ))

            db.session.add(Payment(
                order_id=order.id,
                payment_method=f"walk_in_{method}",
                amount=subtotal,
                status=PaymentStatus.paid,
                paid_at=now,
            ))
            db.session.commit()
            return redirect(url_for("walkin.ticket", order_id=order.id))

        except IntegrityError:
            db.session.rollback()
            continue
        except Exception:
            db.session.rollback()
            raise

    flash("Couldn't create the order number. Please place the order again.", "error")
    return redirect(url_for("walkin.new_order"))


@walkin_bp.route("/walk-in/ticket/<int:order_id>")
def ticket(order_id):
    order = Order.query.get_or_404(order_id)
    if order.fulfillment_type != "walk_in":
        abort(404)
    return render_template("walkin/ticket.html", order=order,
                           number=order.order_number,
                           method=PAYMENT_METHODS.get(
                               (order.payment.payment_method if order.payment else "")
                               .replace("walk_in_", ""), ""))
