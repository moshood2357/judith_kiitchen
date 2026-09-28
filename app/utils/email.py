import os
import requests

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

BREVO_API_KEY = os.getenv("BREVO_API_KEY") 


def send_email(to, subject, html_content, sender_name="Judith Kitchen", sender_email=None):
    """
    Send transactional email via Brevo API
    """

    if not sender_email:
        sender_email = os.getenv("BREVO_SENDER_EMAIL")

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email
        },
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers)

        if response.status_code not in [200, 201, 202]:
            print("Email failed:", response.text)

        return {
            "success": response.status_code in [200, 201, 202],
            "status_code": response.status_code,
            "response": response.json() if response.text else {}
        }

    except Exception as e:
        print("Email exception:", str(e))
        return {
            "success": False,
            "error": str(e)
        }


import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from flask import current_app


# =========================
# ADMIN NOTIFICATION
# =========================
def send_order_notification(order):
    """Notify admin when a new order is placed."""
    _send_email(
        to_email=current_app.config["ADMIN_EMAIL"],
        to_name="Admin",
        subject=f"New Order - {order.order_number}",
        html_content=_build_order_html(
            order,
            heading="New Order Received!",
            intro="A new order has been placed and is awaiting your review."
        )
    )


# =========================
# CUSTOMER CONFIRMATION
# =========================
def send_order_confirmation_customer(order):
    """Send confirmation email to customer when order is accepted."""
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email found for order", order.order_number)
        return

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} is Confirmed!",
        html_content=_build_order_html(
            order,
            heading="Your Order is Confirmed!",
            intro=f"Hi {customer_name}, your order has been accepted and confirmed."
        )
    )


# =========================
# ORDER PREPARING
# =========================
def send_order_preparing_customer(order):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for preparing notification")
        return

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} is Being Prepared",
        html_content=_build_order_html(
            order,
            heading="Your Order is Being Prepared!",
            intro=f"Hi {customer_name}, great news! The kitchen has started preparing your order. It should be ready in approximately {order.prep_time} minutes."
        )
    )


# =========================
# ORDER COMPLETED
# =========================
def send_order_completed_customer(order):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for completed notification")
        return

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} is Ready!",
        html_content=_build_order_html(
            order,
            heading="Your Order is Ready!",
            intro=f"Hi {customer_name}, your order is ready! Thank you for choosing Judith Kitchen."
        )
    )


# =========================
# PREP TIME EXTENDED
# =========================
def send_order_time_extended_customer(order, added_minutes):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for time-extended notification")
        return

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Update on Your Order {order.order_number}",
        html_content=_build_order_html(
            order,
            heading="Your Order Needs a Little More Time",
            intro=(
                f"Hi {customer_name}, we're still working on your order and it's taking "
                f"a bit longer than expected. We've added {added_minutes} extra minute"
                f"{'s' if added_minutes != 1 else ''} to the prep time — it should now be "
                f"ready in approximately {order.prep_time} minutes from when it started. "
                f"Thanks so much for your patience!"
            )
        )
    )


# =========================
# SHARED HTML BUILDER
# =========================
def _build_order_html(order, heading, intro):

    items_html = ""
    for item in order.items:
        items_html += f"""
            <tr>
                <td style="padding:10px;border-bottom:1px solid #eee;">{item.product_name}</td>
                <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{item.quantity}</td>
                <td style="padding:10px;border-bottom:1px solid #eee;text-align:right;">£{float(item.price):.2f}</td>
                <td style="padding:10px;border-bottom:1px solid #eee;text-align:right;">£{float(item.price) * item.quantity:.2f}</td>
            </tr>
        """

    address_html = ""
    if order.address:
        a = order.address
        address_html = f"""
            {a.full_name}<br>
            {a.phone}<br>
            {a.address_line_1}<br>
            {f"{a.address_line_2}<br>" if a.address_line_2 else ""}
            {a.city}, {a.state} {a.postal_code or ""}<br>
            {a.country}
        """

    prep_html = ""
    if order.prep_time:
        prep_html = f"""
            <div style="background:#fef9c3;padding:14px;border-radius:8px;
                        color:#854d0e;margin:16px 0;font-size:0.95rem;">
                 Estimated preparation time: <strong>{order.prep_time} minutes</strong>
            </div>
        """

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1e293b;">

        <div style="background:#0f172a;padding:24px;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:1.4rem;">{heading}</h1>
        </div>

        <div style="padding:24px;">

            <p style="font-size:0.95rem;color:#475569;margin-bottom:16px;">{intro}</p>

            {prep_html}

            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                <tr style="background:#f8fafc;">
                    <td style="padding:10px;font-weight:600;width:40%;">Order Number</td>
                    <td style="padding:10px;">{order.order_number}</td>
                </tr>
                <tr>
                    <td style="padding:10px;font-weight:600;">Date</td>
                    <td style="padding:10px;">{order.created_at.strftime("%d %b %Y, %I:%M %p")}</td>
                </tr>
                <tr style="background:#f8fafc;">
                    <td style="padding:10px;font-weight:600;">Delivery Method</td>
                    <td style="padding:10px;">{order.delivery_method or "—"}</td>
                </tr>
                <tr>
                    <td style="padding:10px;font-weight:600;">Payment Status</td>
                    <td style="padding:10px;">{order.payment_status.value}</td>
                </tr>
            </table>

            <h3 style="border-bottom:2px solid #f1f5f9;padding-bottom:8px;margin-bottom:12px;">
                Items
            </h3>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                <thead>
                    <tr style="background:#f8fafc;">
                        <th style="padding:10px;text-align:left;">Product</th>
                        <th style="padding:10px;text-align:center;">Qty</th>
                        <th style="padding:10px;text-align:right;">Price</th>
                        <th style="padding:10px;text-align:right;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
            </table>

            <table style="width:100%;margin-bottom:24px;">
                <tr>
                    <td style="padding:6px 0;color:#475569;">Subtotal</td>
                    <td style="padding:6px 0;text-align:right;">£{float(order.subtotal):.2f}</td>
                </tr>
                <tr>
                    <td style="padding:6px 0;color:#475569;">Shipping</td>
                    <td style="padding:6px 0;text-align:right;">£{float(order.shipping_fee):.2f}</td>
                </tr>
                <tr>
                    <td style="padding:6px 0;color:#475569;">Tax</td>
                    <td style="padding:6px 0;text-align:right;">£{float(order.tax):.2f}</td>
                </tr>
                <tr style="font-weight:700;font-size:1.05em;border-top:2px solid #e2e8f0;">
                    <td style="padding-top:10px;">Total</td>
                    <td style="padding-top:10px;text-align:right;">£{float(order.total_amount):.2f}</td>
                </tr>
            </table>

            <h3 style="border-bottom:2px solid #f1f5f9;padding-bottom:8px;margin-bottom:12px;">
                Shipping Address
            </h3>
            <p style="line-height:1.9;color:#475569;font-size:0.9rem;">
                {address_html}
            </p>

        </div>

        <div style="background:#f8fafc;padding:16px;text-align:center;
                    color:#94a3b8;font-size:0.82rem;border-top:1px solid #e2e8f0;">
            Judith Kitchen - Thank you for your order
        </div>

    </div>
    """


# =========================
# SEND VIA BREVO
# =========================
def _send_email(to_email, to_name, subject, html_content):
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = current_app.config["BREVO_API_KEY"]

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email, "name": to_name}],
        sender={
            "email": current_app.config["BREVO_SENDER_EMAIL"],
            "name":  "Judith Kitchen"
        },
        subject=subject,
        html_content=html_content
    )

    try:
        api_instance.send_transac_email(send_smtp_email)
        current_app.logger.info(f"Email sent to {to_email} - {subject}")
    except ApiException as e:
        current_app.logger.error(f"Brevo email error: {e}")


# =========================
# ORDER REJECTED
# =========================
def send_order_rejected_customer(order, reason):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for rejection notification")
        return

    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1e293b;">
        <div style="background:#0f172a;padding:24px;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:1.4rem;">Order Update</h1>
        </div>
        <div style="padding:24px;">
            <p style="font-size:0.95rem;color:#475569;margin-bottom:16px;">
                Hi {customer_name}, unfortunately your order <strong>{order.order_number}</strong>
                could not be fulfilled at this time.
            </p>
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin:16px 0;">
                <p style="margin:0;font-weight:600;color:#991b1b;">Reason:</p>
                <p style="margin:8px 0 0;color:#7f1d1d;">{reason}</p>
            </div>
            <p style="color:#475569;font-size:0.9rem;">
                If you have any questions, please contact us. We apologise for any inconvenience.
            </p>
        </div>
        <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:0.82rem;border-top:1px solid #e2e8f0;">
            Judith Kitchen &mdash; We appreciate your patience
        </div>
    </div>
    """

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} — Update",
        html_content=html_content
    )