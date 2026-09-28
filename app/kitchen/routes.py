import traceback

from flask import render_template, jsonify, request, current_app
from flask_login import login_required
from app.models import Order, OrderStatus
from app.extensions import db
from app import csrf
from . import kitchen_bp


@kitchen_bp.route("/")
@login_required
def kitchen_display():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    orders = Order.query.filter(
        Order.status.in_([OrderStatus.accepted, OrderStatus.preparing]),
        Order.created_at >= cutoff
    ).order_by(Order.created_at.desc()).all()

    return render_template("kitchen/kitchen.html", orders=orders)


@kitchen_bp.route("/latest-order")
@login_required
def latest_order():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    order = Order.query.filter(
        Order.status.in_([OrderStatus.accepted, OrderStatus.preparing]),
        Order.created_at >= cutoff
    ).order_by(Order.id.desc()).first()

    if not order:
        return jsonify({"order": None})

    return jsonify({
        "order": {
            "id":              order.id,
            "order_number":    order.order_number,
            "customer":        order.address.full_name if order.address else "Guest",
            "items": [
                {"name": item.product_name, "quantity": item.quantity}
                for item in order.items
            ],
            "prep_time":       order.prep_time,
            "delivery_method": order.delivery_method or "standard",
            "fulfillment_type": order.fulfillment_type or "delivery",
            "pickup_time":     order.pickup_time,
            "created_at":      order.created_at.strftime("%d %b %Y, %I:%M %p")
        }
    })


@kitchen_bp.route("/accepted-orders")
@login_required
def accepted_orders():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    orders = Order.query.filter(
        Order.status.in_([OrderStatus.accepted, OrderStatus.preparing]),
        Order.created_at >= cutoff
    ).order_by(Order.id.desc()).all()

    return jsonify({
        "orders": [
            {
                "id":              order.id,
                "order_number":    order.order_number,
                "customer":        order.address.full_name if order.address else "Guest",
                "items": [
                    {"name": item.product_name, "quantity": item.quantity}
                    for item in order.items
                ],
                "prep_time":       order.prep_time,
                "delivery_method": order.delivery_method or "standard",
                "fulfillment_type": order.fulfillment_type or "delivery",
                "pickup_time":     order.pickup_time,
                "created_at":      order.created_at.strftime("%d %b %Y, %I:%M %p")
            }
            for order in orders
        ]
    })


@kitchen_bp.route("/all-timer-states")
@login_required
def all_timer_states():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    orders = Order.query.filter(
        Order.status.in_([
            OrderStatus.accepted,
            OrderStatus.preparing,
            OrderStatus.completed
        ]),
        Order.created_at >= cutoff
    ).all()

    states = {}
    for order in orders:
        elapsed_seconds = 0
        if order.timer_started_at:
            elapsed_seconds = int(
                (datetime.utcnow() - order.timer_started_at).total_seconds()
            )

        total_seconds = (order.prep_time or 0) * 60
        remaining     = max(total_seconds - elapsed_seconds, 0)

        states[order.id] = {
            "timer_status":  order.timer_status or "pending",
            "remaining":     remaining,
            "total_seconds": total_seconds,
            "prep_time":     order.prep_time or 0
        }

    return jsonify({"states": states})


@kitchen_bp.route("/timer-state/<int:order_id>")
@login_required
def timer_state(order_id):
    from datetime import datetime
    order = Order.query.get_or_404(order_id)

    elapsed_seconds = 0
    if order.timer_started_at:
        elapsed_seconds = int(
            (datetime.utcnow() - order.timer_started_at).total_seconds()
        )

    total_seconds = (order.prep_time or 0) * 60
    remaining     = max(total_seconds - elapsed_seconds, 0)

    return jsonify({
        "timer_status":  order.timer_status or "pending",
        "remaining":     remaining,
        "total_seconds": total_seconds,
        "prep_time":     order.prep_time or 0
    })


@kitchen_bp.route("/start-timer/<int:order_id>", methods=["POST"])
@csrf.exempt
@login_required
def start_timer(order_id):
    from app.utils.email import send_order_preparing_customer
    from datetime import datetime

    order = Order.query.get_or_404(order_id)

    if order.timer_status in ("running", "completed"):
        return jsonify({"success": True, "already_started": True})

    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        customer_email = None
        customer_name  = None

    try:
        order.status           = OrderStatus.preparing
        order.timer_started_at = datetime.utcnow()
        order.timer_status     = "running"
        db.session.commit()

        if customer_email:
            send_order_preparing_customer(order)

        return jsonify({"success": True, "already_started": False})

    except Exception as e:
        db.session.rollback()
        print(f"Start timer error: {e}")
        return jsonify({"success": False})


@kitchen_bp.route("/add-time/<int:order_id>", methods=["POST"])
@csrf.exempt
@login_required
def add_time(order_id):
    from datetime import datetime
    from app.utils.email import send_order_time_extended_customer

    order = Order.query.get_or_404(order_id)

    if order.timer_status == "completed":
        return jsonify({"success": False, "error": "Order already completed"}), 400

    data = request.get_json(silent=True) or {}
    try:
        minutes = int(data.get("minutes", 2))
    except (TypeError, ValueError):
        minutes = 2

    if minutes <= 0 or minutes > 180:
        return jsonify({"success": False, "error": "Invalid minutes"}), 400

    try:
        order.prep_time = (order.prep_time or 0) + minutes
        db.session.commit()

        elapsed_seconds = 0
        if order.timer_started_at:
            elapsed_seconds = int(
                (datetime.utcnow() - order.timer_started_at).total_seconds()
            )

        total_seconds = (order.prep_time or 0) * 60
        remaining     = max(total_seconds - elapsed_seconds, 0)

        try:
            send_order_time_extended_customer(order, minutes)
        except Exception as e:
            # never let an email failure undo or block the time update itself
            current_app.logger.error(f"Time-extended notification failed: {e}")
            current_app.logger.error(traceback.format_exc())

        return jsonify({
            "success":       True,
            "prep_time":     order.prep_time,
            "remaining":     remaining,
            "total_seconds": total_seconds,
            "timer_status":  order.timer_status or "pending"
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Add time error: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({"success": False}), 500


@kitchen_bp.route("/complete-order/<int:order_id>", methods=["POST"])
@csrf.exempt
@login_required
def complete_order(order_id):
    from app.utils.email import send_order_completed_customer

    order = Order.query.get_or_404(order_id)

    if order.timer_status == "completed":
        return jsonify({"success": True, "already_completed": True})

    try:
        order.status       = OrderStatus.completed
        order.timer_status = "completed"
        db.session.commit()
        
        if order.user or order.guest_email:
            send_order_completed_customer(order)

        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        print(f"Complete order error: {e}")
        return jsonify({"success": False})


@kitchen_bp.route("/history-orders")
@login_required
def history_orders():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    orders = Order.query.filter(
        Order.status == OrderStatus.completed,
        Order.created_at >= cutoff
    ).order_by(Order.id.desc()).all()

    return jsonify({
        "orders": [
            {
                "id":              order.id,
                "order_number":    order.order_number,
                "customer":        order.address.full_name if order.address else "Guest",
                "items": [
                    {"name": item.product_name, "quantity": item.quantity}
                    for item in order.items
                ],
                "prep_time":       order.prep_time,
                "delivery_method": order.delivery_method or "standard",
                "fulfillment_type": order.fulfillment_type or "delivery",
                "pickup_time":     order.pickup_time,
                "created_at":      order.created_at.strftime("%d %b %Y, %I:%M %p"),
                "completed_at":    (
                    (order.timer_started_at + __import__('datetime').timedelta(minutes=order.prep_time or 0))
                    .strftime("%I:%M %p")
                ) if order.timer_started_at else "—"
            }
            for order in orders
        ]
    })


@kitchen_bp.route("/order-completed-age/<int:order_id>")
@login_required
def order_completed_age(order_id):
    from datetime import datetime, timedelta
    order = Order.query.get_or_404(order_id)

    if order.timer_status != "completed" or not order.timer_started_at:
        return jsonify({"minutes_since_completed": 0})

    # estimate completion time as started_at + prep_time
    completed_at = order.timer_started_at + timedelta(minutes=order.prep_time or 0)
    minutes      = (datetime.utcnow() - completed_at).total_seconds() / 60
    return jsonify({"minutes_since_completed": max(int(minutes), 0)})