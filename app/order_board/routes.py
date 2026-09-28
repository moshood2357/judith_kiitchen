"""
Customer-facing order status board for Judith's Kitchen.

Routes:
    /order-board        -> full-screen page for the TV above the counter
    /order-board/data   -> JSON polled by that page every few seconds

Lives in app/order_board/routes.py. The blueprint itself is created in
app/order_board/__init__.py (same pattern as the kitchen blueprint).

How an order moves across the board:
    Not shown  -> accepted, but Start Timer not clicked yet
    Preparing  -> Start Timer clicked (kitchen start_timer sets
                  status=preparing and timer_started_at)
    Ready      -> the countdown reaches zero (kitchen card shows DONE), or
                  the kitchen taps Complete - whichever comes first.
                  Picked up on the next poll, within ~4 seconds.
                  "+ time" in the kitchen pushes the Ready moment back too.
    Gone       -> READY_WINDOW_MINUTES after completion, or cancelled

Only order numbers are exposed - no names, items or totals.
"""
from datetime import datetime, timedelta

from flask import jsonify, render_template

from app.extensions import db
from app.models import Order, OrderStatus
from . import order_board_bp

# ---- Settings -----------------------------------------------------------
# Who is waiting in the restaurant: app pickup orders and counter walk-ins.
# Set to None to show every fulfillment type (including delivery).
FULFILLMENT_TYPES = ("pickup", "walk_in")

# A ready order drops off the board after this long.
READY_WINDOW_MINUTES = 20

# False: an order moves to Ready only when the kitchen taps Complete.
# True:  it also moves to Ready by itself when its countdown reaches zero,
#        even if nobody has tapped Complete yet.
AUTO_READY_WHEN_TIMER_ENDS = True

# Only look at orders created within this many hours (created_at is UTC).
LOOKBACK_HOURS = 18

# Show only the last N characters of order_number (e.g. 4). None = full number.
DISPLAY_LAST_CHARS = None

MAX_PER_COLUMN = 30
# -------------------------------------------------------------------------


def display_number(order):
    """The full order number, exactly as on the customer's ticket or receipt."""
    num = str(order.order_number)
    return num[-DISPLAY_LAST_CHARS:] if DISPLAY_LAST_CHARS else num


def timer_ends_at(order):
    if not order.timer_started_at:
        return None
    return order.timer_started_at + timedelta(minutes=order.prep_time or 0)


def ready_since(order):
    """
    When the kitchen tapped Complete (`ready_at`). Orders completed before
    that column existed fall back to timer start + prep time.
    """
    return order.ready_at or timer_ends_at(order)


def timer_started(order):
    return order.timer_started_at is not None and order.timer_status in ("running", "completed")


def fetch_board_orders():
    now = datetime.utcnow()  # matches created_at / timer_started_at (utcnow)

    query = Order.query.filter(
        Order.status.in_((OrderStatus.preparing, OrderStatus.completed)),
        Order.created_at >= now - timedelta(hours=LOOKBACK_HOURS),
    )
    if FULFILLMENT_TYPES:
        query = query.filter(Order.fulfillment_type.in_(FULFILLMENT_TYPES))

    orders = query.order_by(Order.timer_started_at.asc()).all()

    preparing, ready = [], []
    ready_cutoff = now - timedelta(minutes=READY_WINDOW_MINUTES)

    for o in orders:
        if o.status == OrderStatus.completed:
            since = ready_since(o)
            if since and since >= ready_cutoff:
                ready.append((since, display_number(o)))

        elif o.status == OrderStatus.preparing and timer_started(o):
            ends = timer_ends_at(o)
            if AUTO_READY_WHEN_TIMER_ENDS and ends and ends <= now:
                if ends >= ready_cutoff:
                    ready.append((ends, display_number(o)))
            else:
                preparing.append(display_number(o))
        # accepted orders (Start Timer not clicked yet) are not shown

    # Most recently ready first, so new numbers land at the top
    ready.sort(key=lambda pair: pair[0], reverse=True)

    return preparing[:MAX_PER_COLUMN], [n for _, n in ready][:MAX_PER_COLUMN]


@order_board_bp.route("/")
def order_board():
    return render_template("order_board.html")


@order_board_bp.route("/order-board/data")
def order_board_data():
    try:
        preparing, ready = fetch_board_orders()
    except Exception as exc:  # keep the TV alive; the page keeps last data
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        # Polling every few seconds - don't hold a session open between polls
        db.session.remove()

    resp = jsonify({"ok": True, "preparing": preparing, "ready": ready})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp