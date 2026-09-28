import re
import uuid
import traceback
import json
import hmac
import requests
from hashlib import sha256

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    CartItem, OrderStatus, PaymentStatus, Cart, Order,
    CheckoutDraft, Address, OrderItem, Payment, Product
)

from flask import render_template, redirect, url_for, session, request, flash

from app import csrf
from app.ecommerce.checkout import checkout_bp

from app.utils.helpers import get_user_key
from app.utils.email import send_order_notification


# =========================
# EMAIL VALIDATOR
# =========================
def is_valid_email(email):
    if not email:
        return False
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email.strip()))


# =========================
# HELPER (GUEST SAFE)
# =========================
def get_identity():
    if current_user.is_authenticated:
        return {
            "type": "user",
            "id": current_user.id
        }
    else:
        return {
            "type": "guest",
            "key": session.get("user_key") or get_user_key()
        }


# =========================
# DETAILS
# =========================
@checkout_bp.route("/details", methods=["GET", "POST"])
def details():

    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired. Please start again.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    session["guest_email"] = draft.email

    identity = get_identity()

    if identity["type"] == "user":
        cart = Cart.query.filter_by(user_id=identity["id"]).first()
    else:
        cart = Cart.query.filter_by(user_key=identity["key"]).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    # =========================
    # PRE-POPULATE ON GET
    # =========================
    if request.method == "GET":

        draft_is_empty = not any([
            draft.full_name,
            draft.address_line_1,
            draft.city,
            draft.postal_code
        ])

        if draft_is_empty:

            if identity["type"] == "user":
                previous = (
                    CheckoutDraft.query
                    .filter_by(user_id=identity["id"], completed=True)
                    .order_by(CheckoutDraft.id.desc())
                    .first()
                )

            else:
                guest_email = session.get("guest_email")
                previous = (
                    CheckoutDraft.query
                    .filter(
                        CheckoutDraft.email == guest_email,
                        CheckoutDraft.completed == True
                    )
                    .order_by(CheckoutDraft.id.desc())
                    .first()
                ) if guest_email else None

            if previous:
                draft.full_name        = previous.full_name
                draft.email            = previous.email
                draft.phone            = previous.phone
                draft.address_line_1   = previous.address_line_1
                draft.address_line_2   = previous.address_line_2
                draft.city             = previous.city
                draft.state            = previous.state
                draft.postal_code      = previous.postal_code
                db.session.commit()

    # =========================
    # POST
    # =========================
    if request.method == "POST":

        draft.full_name = request.form.get("full_name")

        # only save email if it looks valid
        submitted_email = request.form.get("email", "").strip()
        if is_valid_email(submitted_email):
            draft.email = submitted_email

        draft.phone          = request.form.get("phone")

        fulfillment_type = request.form.get("fulfillment_type", "delivery")
        if fulfillment_type not in ("delivery", "pickup"):
            fulfillment_type = "delivery"
        draft.fulfillment_type = fulfillment_type

        if fulfillment_type == "pickup":
            pickup_date_str = request.form.get("pickup_date")
            draft.pickup_date = None
            if pickup_date_str:
                try:
                    draft.pickup_date = datetime.strptime(pickup_date_str, "%Y-%m-%d").date()
                except ValueError:
                    draft.pickup_date = None
            draft.pickup_time = request.form.get("pickup_time")
        else:
            draft.pickup_date = None
            draft.pickup_time = None

        draft.address_line_1 = request.form.get("address_line_1")
        draft.address_line_2 = request.form.get("address_line_2")
        draft.city           = request.form.get("city")
        draft.state          = request.form.get("state")
        draft.postal_code    = request.form.get("postal_code")
        draft.delivery_method = request.form.get("delivery_method")
        draft.delivery_miles = request.form.get("delivery_miles") or None
        draft.delivery_fee   = request.form.get("delivery_fee") or None
        draft.note = request.form.get("note", "").strip() or None

        same_as_delivery = request.form.get("same_as_delivery") == "on"
        draft.same_as_delivery = same_as_delivery

        if same_as_delivery:
            draft.billing_address_line_1 = draft.address_line_1
            draft.billing_address_line_2 = draft.address_line_2
            draft.billing_city           = draft.city
            draft.billing_state          = draft.state
            draft.billing_postcode       = draft.postal_code
        else:
            draft.billing_address_line_1 = request.form.get("billing_address_line_1")
            draft.billing_address_line_2 = request.form.get("billing_address_line_2")
            draft.billing_city           = request.form.get("billing_city")
            draft.billing_state          = request.form.get("billing_state")
            draft.billing_postcode       = request.form.get("billing_postcode")

        subtotal = sum(item.quantity * float(item.unit_price) for item in cart.items)

        if fulfillment_type == "pickup":
            shipping = 0
            draft.delivery_miles = None
            draft.delivery_fee   = None
        else:
            shipping = float(draft.delivery_fee or 0)

        # tax      = subtotal * 0.05

        draft.subtotal     = subtotal
        draft.shipping_fee = shipping
        # draft.tax          = tax
        draft.total        = subtotal + shipping

        db.session.commit()

        return redirect(url_for("checkout.summary"))

    products = {item.product_id: item.product for item in cart.items}
    total    = sum(item.quantity * float(item.unit_price) for item in cart.items)

    return render_template(
        "checkout/details.html",
        draft=draft,
        cart=cart,
        products=products,
        cart_total=total
    )


# =========================
# SUMMARY
# =========================
@checkout_bp.route("/summary")
def summary():

    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    identity = get_identity()

    if identity["type"] == "user":
        cart = Cart.query.filter_by(user_id=identity["id"]).first()
    else:
        cart = Cart.query.filter_by(user_key=identity["key"]).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    products = {item.product_id: item.product for item in cart.items}

    subtotal = sum(item.quantity * float(item.unit_price) for item in cart.items)

    if draft.fulfillment_type == "pickup":
        shipping = 0
    else:
        shipping = float(draft.delivery_fee or 0)

    # tax      = subtotal * 0.05

    draft.subtotal     = subtotal
    draft.shipping_fee = shipping
    # draft.tax          = tax
    draft.total        = subtotal + shipping

    db.session.commit()

    return render_template(
        "checkout/summary.html",
        draft=draft,
        cart=cart,
        products=products
    )


# =========================
# PAY (DOJO)
# =========================
@checkout_bp.route("/pay", methods=["POST"])
def pay():

    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        flash("Invalid checkout session.", "danger")
        return redirect(url_for("cart.view_cart"))

    identity = get_identity()

    if identity["type"] == "user":
        cart = Cart.query.filter_by(user_id=identity["id"]).first()
    else:
        cart = Cart.query.filter_by(user_key=identity["key"]).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    try:
        amount_minor = int(round(draft.total * 100))

        api_key  = current_app.config.get("DOJO_API_KEY")
        api_base = current_app.config.get("DOJO_API_BASE")

        payload = {
            "amount": {
                "value": amount_minor,
                "currencyCode": "GBP",
            },
            "reference": f"CHK-{checkout_id}-{uuid.uuid4().hex[:6]}",
            # required to accept a payment link without the full online
            # checkout SDK integration — see Dojo's payment links docs
            "isNotOnlineCheckout": True,
            "metadata": {
                "checkout_id": str(checkout_id),
                "user_id":     str(identity["id"]) if identity["type"] == "user" else "",
                "guest_key":   session.get("user_key", ""),
            },
            "config": {
                "redirectUrl": url_for("checkout.success", _external=True),
            },
        }

        resp = requests.post(
            f"{api_base}/payment-intents/",
            json=payload,
            headers={
                "Authorization": f"Basic {api_key}",
                "version": "2024-02-05",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        intent_id = resp.json()["id"]

        checkout_url = f"https://pay.dojo.tech/checkout/{intent_id}"

        return redirect(checkout_url)

    except Exception as e:
        current_app.logger.error(f"Dojo payment intent creation failed: {e}")
        current_app.logger.error(traceback.format_exc())
        flash("Payment could not be initiated. Please try again.", "danger")
        return redirect(url_for("checkout.summary"))


# =========================
# SUCCESS
# =========================
@checkout_bp.route("/success")
def success():

    # The order itself is created by dojo_webhook() when Dojo confirms
    # payment. Landing here only means Dojo redirected the customer back
    # after checkout — it doesn't guarantee the webhook has processed yet.
    if current_user.is_authenticated:
        order = Order.query.filter_by(user_id=current_user.id)\
            .order_by(Order.id.desc()).first()

        return render_template(
            "checkout/success.html",
            order=order,
            guest_email=None
        )

    else:
        guest_email = session.get("guest_email")
        order = Order.query.filter_by(guest_email=guest_email)\
            .order_by(Order.id.desc()).first()

        return render_template(
            "checkout/success.html",
            order=order,
            guest_email=guest_email
        )


# =========================
# DOJO WEBHOOK
# =========================
@checkout_bp.route("/dojo/webhook", methods=["POST"])
@csrf.exempt
def dojo_webhook():

    payload    = request.get_data(cache=False)
    sig_header = request.headers.get("dojo-signature") or request.headers.get("Dojo-Signature", "")
    endpoint_secret = current_app.config["DOJO_WEBHOOK_SECRET"] or ""

    try:
        digest = hmac.new(
            endpoint_secret.encode("utf-8"),
            msg=payload,
            digestmod=sha256,
        ).digest()
        expected_sig = "sha256=" + "-".join(f"{byte:02X}" for byte in digest)

    except Exception:
        current_app.logger.error(traceback.format_exc())
        return "Webhook verification failed", 400

    if not hmac.compare_digest(sig_header, expected_sig):
        current_app.logger.error("Dojo webhook signature mismatch")
        current_app.logger.error(
            f"Secret length: {len(endpoint_secret)} | "
            f"starts_with_space: {endpoint_secret != endpoint_secret.lstrip()} | "
            f"ends_with_space_or_newline: {endpoint_secret != endpoint_secret.rstrip()} | "
            f"has_quotes: {endpoint_secret.startswith(chr(34)) or endpoint_secret.endswith(chr(34))}"
        )
        current_app.logger.error(f"Payload length: {len(payload)} bytes")
        current_app.logger.error(f"Expected: {expected_sig}")
        current_app.logger.error(f"Got:      {sig_header!r}")
        return "Invalid signature", 400

    try:
        event = json.loads(payload.decode("utf-8"))
    except ValueError:
        current_app.logger.error("Invalid payload")
        return "Invalid payload", 400

    event_type = event.get("event", "")
    current_app.logger.info(f"Dojo webhook received: {event_type}")

    if event_type != "payment_intent.status_updated":
        return "success", 200

    data           = event.get("data") or {}
    payment_status = data.get("paymentStatus", "")
    intent_id      = data.get("paymentIntentId", "")

    current_app.logger.info(f"Payment intent {intent_id} status: {payment_status}")

    api_key  = current_app.config.get("DOJO_API_KEY")
    api_base = current_app.config.get("DOJO_API_BASE")

    # =========================
    # PAYMENT FAILED / DECLINED / CANCELLED
    # =========================
    if payment_status in ["Failed", "Declined", "Cancelled", "Rejected"]:
        current_app.logger.info(f"Payment {payment_status} for intent {intent_id}")

        try:
            fi_resp = requests.get(
                f"{api_base}/payment-intents/{intent_id}",
                headers={"Authorization": f"Basic {api_key}", "version": "2024-02-05"},
                timeout=10,
            )
            if fi_resp.ok:
                fi_metadata = fi_resp.json().get("metadata") or {}
                checkout_id = fi_metadata.get("checkout_id")

                if checkout_id:
                    draft = CheckoutDraft.query.filter_by(id=int(checkout_id)).first()

                    if draft and not draft.completed:
                        failed_address = Address(
                            user_id        = int(fi_metadata.get("user_id")) if fi_metadata.get("user_id") else None,
                            full_name      = draft.full_name or "Unknown",
                            phone          = draft.phone or "",
                            address_line_1 = draft.address_line_1 or "N/A",
                            address_line_2 = draft.address_line_2 or "",
                            city           = draft.city or "N/A",
                            state          = draft.state or "N/A",
                            country        = draft.country or "United Kingdom",
                            postal_code    = draft.postal_code or "N/A",
                        )
                        db.session.add(failed_address)
                        db.session.flush()

                        failed_order = Order(
                            user_id        = int(fi_metadata.get("user_id")) if fi_metadata.get("user_id") else None,
                            address_id     = failed_address.id,
                            order_number   = f"ORD-{uuid.uuid4().hex[:10].upper()}",
                            subtotal       = draft.subtotal or 0,
                            shipping_fee   = draft.shipping_fee or 0,
                            tax            = draft.tax or 0,
                            total_amount   = draft.total or 0,
                            delivery_method= draft.delivery_method,
                            fulfillment_type = draft.fulfillment_type or "delivery",
                            pickup_date    = draft.pickup_date,
                            pickup_time    = draft.pickup_time,
                            status         = OrderStatus.cancelled,
                            payment_status = PaymentStatus.failed,
                            guest_email    = draft.email,
                            note           = f"Payment {payment_status} via Dojo",
                        )
                        db.session.add(failed_order)
                        db.session.commit()
                        current_app.logger.info(f"Payment failed order created: {failed_order.order_number}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed order creation error: {e}")

        return "success", 200

    if payment_status != "Captured":
        current_app.logger.info(f"Ignoring unhandled status: {payment_status}")
        return "success", 200

    # =========================
    # PAYMENT CAPTURED
    # =========================
    try:
        intent_resp = requests.get(
            f"{api_base}/payment-intents/{intent_id}",
            headers={"Authorization": f"Basic {api_key}", "version": "2024-02-05"},
            timeout=10,
        )
        intent_resp.raise_for_status()
        metadata = intent_resp.json().get("metadata") or {}
    except Exception as e:
        current_app.logger.error(f"Failed to fetch Dojo payment intent {intent_id}: {e}")
        return "Failed to fetch payment intent", 500

    checkout_id = metadata.get("checkout_id")
    user_id     = metadata.get("user_id")
    guest_key   = metadata.get("guest_key")

    if not checkout_id:
        current_app.logger.error("Missing checkout_id in metadata")
        return "missing checkout_id", 200

    try:
        checkout_id = int(checkout_id)
    except (ValueError, TypeError):
        current_app.logger.error("Invalid checkout_id")
        return "invalid checkout id", 200

    try:
        # Prevent duplicate processing
        existing = Payment.query.filter_by(transaction_id=intent_id).first()
        if existing:
            current_app.logger.info(f"Transaction {intent_id} already processed")
            return "already processed", 200

        draft = CheckoutDraft.query.filter_by(id=checkout_id).first()
        if not draft:
            current_app.logger.error(f"Draft {checkout_id} not found")
            return "draft not found", 200

        # Create Address — pickup orders go to Judith Kitchen's own counter,
        # not the customer's home
        if draft.fulfillment_type == "pickup":
            address = Address(
                user_id=int(user_id) if user_id else None,
                full_name=draft.full_name or "",
                phone=draft.phone or "",
                address_line_1="302 High Street",
                address_line_2="",
                city="Cheltenham",
                state="Gloucestershire",
                country="United Kingdom",
                postal_code="GL50 3JF",
            )
        else:
            address = Address(
                user_id=int(user_id) if user_id else None,
                full_name=draft.full_name or "",
                phone=draft.phone or "",
                address_line_1=draft.address_line_1 or "",
                address_line_2=draft.address_line_2 or "",
                city=draft.city or "",
                state=draft.state or "",
                country=draft.country or "United Kingdom",
                postal_code=draft.postal_code or "",
            )
        db.session.add(address)
        db.session.flush()

        # Create Order
        guest_email_to_save = draft.email if is_valid_email(draft.email) else None

        order = Order(
           user_id=int(user_id) if user_id else None,
            address_id=address.id,
            order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}",
            subtotal=draft.subtotal,
            shipping_fee=draft.shipping_fee,
            delivery_method=draft.delivery_method,
            delivery_miles=draft.delivery_miles,
            delivery_fee=draft.delivery_fee,
            fulfillment_type=draft.fulfillment_type or "delivery",
            pickup_date=draft.pickup_date,
            pickup_time=draft.pickup_time,
            # tax=draft.tax,
            total_amount=draft.total,
            status=OrderStatus.processing,
            payment_status=PaymentStatus.paid,
            guest_email=guest_email_to_save if not user_id else None,
            note=draft.note,
        )
        db.session.add(order)
        db.session.flush()

        # Create Items & deduct stock safely
        try:
            cart_items = json.loads(draft.cart_snapshot or "[]")
        except json.JSONDecodeError:
            cart_items = []

        for item in cart_items:
            product_id = item.get("product_id")
            quantity   = item.get("quantity", 1)
            price      = item.get("price", 0)

            if not product_id:
                continue

            order_item = OrderItem(
                order_id=order.id,
                product_id=product_id,
                quantity=quantity,
                price=price,
                product_name=item.get("name", ""),
                product_image=item.get("image", ""),
            )
            db.session.add(order_item)

            # row-locked atomic stock deduction
            product = (
                db.session.query(Product)
                .with_for_update()
                .filter_by(id=product_id)
                .first()
            )
            if product and product.stock_quantity is not None:
                product.stock_quantity = max(0, product.stock_quantity - quantity)

        # Create Payment Record
        payment = Payment(
            order_id=order.id,
            payment_method="dojo",
            transaction_id=intent_id,
            amount=draft.total,
            status=PaymentStatus.paid,
            reference=intent_id,
            paid_at=datetime.utcnow(),
        )
        db.session.add(payment)

        # Clear Cart
        cart = None
        if user_id:
            try:
                cart = Cart.query.filter_by(user_id=int(user_id)).first()
            except (ValueError, TypeError):
                cart = None
        elif guest_key:
            cart = Cart.query.filter_by(user_key=guest_key).first()

        if cart:
            CartItem.query.filter_by(cart_id=cart.id).delete()

        # Update Draft status
        draft.completed    = True
        draft.completed_at = datetime.utcnow()

        # Commit entire transaction at once
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Database error while processing Dojo webhook: {e}")
        current_app.logger.error(traceback.format_exc())
        return "Internal server error", 500

    # Send notification outside the DB transaction
    try:
        send_order_notification(order)
    except Exception:
        current_app.logger.error("Email notification failed")
        current_app.logger.error(traceback.format_exc())

    current_app.logger.info(f"Order created and payment confirmed: {order.order_number}")
    return "success", 200