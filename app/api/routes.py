import requests
from flask import request, jsonify, current_app
from . import api_bp


RESTAURANT_POSTCODE  = "302+High+Street+Cheltenham+GL50+3JF+UK"


def get_delivery_fee(miles):
    if miles <= 3:
        return 4.99
    elif miles <= 6:
        return 6.99
    elif miles <= 10:
        return 10.99
    elif miles <= 15:
        return 14.99
    elif miles <= 20:
        return 19.99
    elif miles <= 25:
        return 24.99
    elif miles <= 30:
        return 29.99
    else:
        return None


@api_bp.route("/lookup-address")
def lookup_address():

    postcode = request.args.get("postcode", "").strip()

    if not postcode:
        return jsonify({"error": "Postcode is required"}), 400

    api_key = current_app.config.get("IDEAL_POSTCODES_API_KEY")

    if not api_key:
        return jsonify({"error": "API key not configured"}), 500

    url = f"https://api.ideal-postcodes.co.uk/v1/postcodes/{postcode}"

    try:
        res = requests.get(url, params={"api_key": api_key}, timeout=5)
        data = res.json()

        if data.get("code") == 4020:
            return jsonify({"error": "API quota exhausted"}), 503

        if data.get("code") != 2000:
            return jsonify({"error": "Invalid postcode or no results"}), 400

        results = data.get("result", [])

        addresses = []
        for r in results:
            addresses.append({
                "line_1": r.get("line_1", ""),
                "line_2": r.get("line_2", ""),
                "post_town": r.get("post_town", ""),
                "county": r.get("county", ""),
                "postcode": r.get("postcode", "")
            })

        return jsonify({"addresses": addresses})

    except Exception as e:
        return jsonify({"error": "Server error", "details": str(e)}), 500


@api_bp.route("/calculate-delivery")
def calculate_delivery():

    postcode = request.args.get("postcode", "").strip()

    if not postcode:
        return jsonify({"error": "Postcode required"}), 400

    google_api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")

    if not google_api_key:
        return jsonify({"error": "Google Maps API key not configured"}), 500

    try:
        url = (
            f"https://maps.googleapis.com/maps/api/distancematrix/json"
            f"?origins={RESTAURANT_POSTCODE.replace(' ', '+')}"
            f"&destinations={postcode.replace(' ', '+')}+UK"
            f"&units=imperial"
            f"&key={google_api_key}"
        )

        resp = requests.get(url, timeout=5)
        data = resp.json()

        print("Google raw response:", data)

        if data.get("status") != "OK":
            return jsonify({
                "error": "Google API error",
                "details": data.get("status"),
                "message": data.get("error_message")
            }), 200

        element = data["rows"][0]["elements"][0]

        if element["status"] != "OK":
            return jsonify({
                "error": "Address not found or outside coverage",
                "element_status": element["status"]
            }), 200

        distance_meters = element["distance"]["value"]
        miles = round(distance_meters / 1609.34, 1)

        fee = get_delivery_fee(miles)

        return jsonify({
            "miles": miles,
            "fee": fee,
            "contact_for_quote": fee is None
        })

    except Exception as e:
        print("Delivery calc error:", e)
        return jsonify({"error": "Could not calculate distance", "details": str(e)}), 500