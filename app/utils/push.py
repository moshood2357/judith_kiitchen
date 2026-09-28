import json
import base64

from flask import current_app
from pywebpush import webpush, WebPushException
from py_vapid import Vapid01

from app.extensions import db
from app.models import PushSubscription


def send_order_push_notification(order):
    """
    Push a real browser/OS notification to every admin device that has
    subscribed, regardless of whether an admin tab is open. Safe to call
    from any order-creation path (Stripe webhook, Dojo webhook, or the
    success-page fallback) — failures here never block order creation,
    they're just logged.
    """
    private_key_b64 = current_app.config.get("VAPID_PRIVATE_KEY_B64")
    if not private_key_b64:
        current_app.logger.error("VAPID_PRIVATE_KEY_B64 not configured — skipping push")
        return

    private_pem = base64.b64decode(private_key_b64)

    try:
        vapid = Vapid01.from_pem(private_pem)
    except Exception:
        current_app.logger.error("Could not load VAPID private key — skipping push")
        return

    payload = json.dumps({
        "title": "🛎️ New Order",
        "body": f"Order {order.order_number} just came in.",
        "url": "/admin/dashboard",
    })

    subscriptions = PushSubscription.query.all()
    dead_subscription_ids = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": f"mailto:{current_app.config.get('ADMIN_EMAIL', 'admin@example.com')}"},
            )
        except WebPushException as ex:
            status = ex.response.status_code if ex.response is not None else None
            current_app.logger.error(f"Push failed for subscription {sub.id}: {ex}")
            # 404/410 means the browser has permanently discarded this
            # subscription (uninstalled, permission revoked, etc.) — clean it up
            if status in (404, 410):
                dead_subscription_ids.append(sub.id)
        except Exception as e:
            current_app.logger.error(f"Unexpected push error for subscription {sub.id}: {e}")

    if dead_subscription_ids:
        PushSubscription.query.filter(PushSubscription.id.in_(dead_subscription_ids)).delete(
            synchronize_session=False
        )
        db.session.commit()