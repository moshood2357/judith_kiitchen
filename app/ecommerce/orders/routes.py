from flask import abort, redirect, render_template, request, url_for, flash
from app import db
from flask_login import login_required, current_user
from sqlalchemy import func, and_, not_
from app.models import Order, OrderStatus, PaymentStatus
from app.ecommerce.orders import order_bp
from app.utils.decorators import admin_required


# =========================
# ONLINE ORDERS ONLY
# =========================
# Walk-in (counter) orders stay on the kitchen display and order board only.
# A walk-in is recognised by ANY of: fulfillment_type, delivery_method (the
# walk-in screen sets both to "walk_in") or its W260927-011 style number.
# coalesce() keeps older orders with empty columns - a plain `!= "walk_in"`
# would silently drop rows where the column is NULL.
NOT_WALK_IN = and_(
    func.coalesce(Order.fulfillment_type, "") != "walk_in",
    func.coalesce(Order.delivery_method, "") != "walk_in",
    not_(Order.order_number.like("W______-%")),
)


# =========================
# ORDER LIST VIEW
# =========================
@order_bp.route("/orders-list")
@login_required
@admin_required
def orders_list():
    page = request.args.get("page", 1, type=int)
    orders = (Order.query
              .filter(NOT_WALK_IN)
              .order_by(Order.id.desc())
              .paginate(page=page, per_page=20, error_out=False))
    return render_template("admin/orders.html", orders=orders)


@order_bp.route("/<int:id>")
@login_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    # Admins can open any order; customers only their own
    if not current_user.is_admin and order.user_id != current_user.id:
        abort(404)
    return render_template("orders/order_detail.html", order=order)


@order_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_order(id):
    order = Order.query.get_or_404(id)

    if request.method == 'POST':
        # update address
        order.address.full_name     = request.form.get('full_name', order.address.full_name)
        order.address.phone         = request.form.get('phone', order.address.phone)
        order.address.address_line_1 = request.form.get('address_line_1', order.address.address_line_1)
        order.address.address_line_2 = request.form.get('address_line_2', order.address.address_line_2)
        order.address.city          = request.form.get('city', order.address.city)
        order.address.state         = request.form.get('state', order.address.state)
        order.address.country       = request.form.get('country', order.address.country)
        order.address.postal_code   = request.form.get('postal_code', order.address.postal_code)

        # update order fields
        order.delivery_method  = request.form.get('delivery_method', order.delivery_method)
        order.status           = OrderStatus[request.form.get('status', order.status.value)]
        order.payment_status   = PaymentStatus[request.form.get('payment_status', order.payment_status.value)]

        db.session.commit()
        flash("Order updated successfully", "success")
        return redirect(url_for('admin.orders'))

    return render_template('orders/edit_order.html', order=order)