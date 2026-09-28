import requests
from flask import current_app, url_for


def create_dojo_hosted_payment(*, amount_pence: int, currency: str, reference: str, metadata: dict | None = None) -> str:
    base    = current_app.config["DOJO_API_BASE"]
    api_key = current_app.config["DOJO_API_KEY"]

    payload = {
    "amount": {"value": int(amount_pence), "currencyCode": currency.upper()},
    "reference": str(reference)[:50],
    "captureMode": "Auto",
    "redirectUrl": url_for("checkout.success", _external=True),
    "config": {
        "redirectUrl": url_for("checkout.success", _external=True),
        "cancelUrl":   url_for("checkout.summary", _external=True),
    },
}
    if metadata:
        payload["metadata"] = {k: str(v) for k, v in metadata.items() if v is not None}

    resp = requests.post(
        f"{base}/payment-intents",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "version": "2024-02-05",
            "Authorization": f"Basic {api_key}",
        },
        timeout=20,
    )

    current_app.logger.error(f"Dojo Status: {resp.status_code}")
    current_app.logger.error(f"Dojo Response: {resp.text}")

    resp.raise_for_status()

    data = resp.json()
    return data["paymentLink"]



def create_terminal_payment(*, amount_pence: int, currency: str, reference: str) -> dict:
    """Create a payment intent and initiate it on a Dojo terminal."""

    base = current_app.config["DOJO_API_BASE"]
    api_key = current_app.config["DOJO_API_KEY"]
    terminal_id = current_app.config["DOJO_TERMINAL_ID"]

    headers = {
        "Content-Type": "application/json",
        "version": "2024-02-05",
        "Authorization": f"Basic {api_key}",
    }

    # 1. Create payment intent
    payload = {
        "amount": {
            "value": int(amount_pence),
            "currencyCode": currency.upper(),
        },
        "reference": str(reference)[:60],
        "captureMode": "Auto",
    }

    resp = requests.post(
        f"{base}/payment-intents",
        json=payload,
        headers=headers,
        timeout=20,
    )

    current_app.logger.info(
        f"Dojo payment intent status: {resp.status_code}"
    )
    current_app.logger.info(
        f"Dojo payment intent response: {resp.text}"
    )

    resp.raise_for_status()

    intent = resp.json()
    intent_id = intent["id"]

    # 2. Create terminal session
    terminal_payload = {
        "terminalId": terminal_id,
        "details": {
            "sale": {
                "paymentIntentId": intent_id
            },
            "sessionType": "Sale"
        }
    }

    terminal_resp = requests.post(
    f"{base}/terminal-sessions",
    json=terminal_payload,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "version": "2024-02-05",
        "Authorization": f"Basic {api_key}",
        "software-house-id": current_app.config["DOJO_SOFTWARE_HOUSE_ID"],
        "reseller-id": current_app.config.get("DOJO_RESELLER_ID", ""),
    },
    timeout=20,
)

    current_app.logger.error(
        f"DOJO TERMINAL STATUS: {terminal_resp.status_code}"
    )

    current_app.logger.error(
        f"DOJO TERMINAL RESPONSE: {terminal_resp.text}"
    )

    current_app.logger.error(
        f"DOJO TERMINAL REQUEST: {terminal_payload}"
    )


    terminal_resp.raise_for_status()

    session = terminal_resp.json()

    return {
        "intent_id": intent_id,
        "terminal_session_id": session.get("id"),
        "status": session.get("status", "InitiateRequested"),
        "amount": amount_pence / 100,
    }




def get_payment_intent_status(intent_id: str) -> str:
    """Poll payment intent status."""
    base    = current_app.config["DOJO_API_BASE"]
    api_key = current_app.config["DOJO_API_KEY"]

    resp = requests.get(
        f"{base}/payment-intents/{intent_id}",
        headers={
            "version":       "2024-02-05",
            "Authorization": f"Basic {api_key}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("status", "Unknown")


def cancel_terminal_session(terminal_id: str, session_id: str) -> bool:
    """Cancel an active terminal session."""
    base    = current_app.config["DOJO_API_BASE"]
    api_key = current_app.config["DOJO_API_KEY"]

    resp = requests.delete(
        f"{base}/terminals/{terminal_id}/terminal-sessions/{session_id}",
        headers={
            "version":       "2024-02-05",
            "Authorization": f"Basic {api_key}",
        },
        timeout=10,
    )
    return resp.status_code in [200, 204]