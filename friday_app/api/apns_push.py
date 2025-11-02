import json
import httpx
import jwt
import time
import frappe

# ⚙️ Konfigurácia — vlož do site_config.json
# {
#   "apns_key_id": "ABC123XYZ",
#   "apns_team_id": "DEF456TUV",
#   "apns_auth_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
#   "apns_bundle_id": "com.yourcompany.yourapp.voip",
#   "apns_use_sandbox": 1
# }

APNS_KEY_ID = frappe.conf.get("apns_key_id")
APNS_TEAM_ID = frappe.conf.get("apns_team_id")
APNS_AUTH_KEY = frappe.conf.get("apns_auth_key")
APNS_BUNDLE_ID = frappe.conf.get("apns_bundle_id")
APNS_USE_SANDBOX = bool(frappe.conf.get("apns_use_sandbox"))


def _generate_jwt_token():
    """Generuje krátkodobý JWT token pre Apple APNs komunikáciu."""
    headers = {"alg": "ES256", "kid": APNS_KEY_ID}
    payload = {
        "iss": APNS_TEAM_ID,
        "iat": int(time.time())
    }
    return jwt.encode(payload, APNS_AUTH_KEY, algorithm="ES256", headers=headers)


@frappe.whitelist()
def send_voip_push(voip_token, caller_name="Neznámy"):
    """
    Pošle VoIP push notifikáciu na iOS zariadenie.
    Používa HTTP/2 APNs API (priamo cez Apple servery).
    """
    if not voip_token:
        frappe.throw("Missing VoIP token")

    jwt_token = _generate_jwt_token()

    apns_url = (
        f"https://api.sandbox.push.apple.com/3/device/{voip_token}"
        if APNS_USE_SANDBOX
        else f"https://api.push.apple.com/3/device/{voip_token}"
    )

    payload = {
        "aps": {
            "alert": {
                "title": "Prichádzajúci hovor",
                "body": f"Volá ti {caller_name}"
            },
            "sound": "default",
            "category": "INCOMING_CALL"
        },
        "caller_name": caller_name,
        "call_type": "voip"
    }

    headers = {
        "apns-topic": APNS_BUNDLE_ID,
        "apns-push-type": "voip",
        "authorization": f"bearer {jwt_token}",
        "content-type": "application/json"
    }

    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            res = client.post(apns_url, headers=headers, data=json.dumps(payload))

        if res.status_code == 200:
            frappe.logger().info(f"✅ APNs VoIP push sent to {voip_token[:8]}…")
            return {"success": True}
        else:
            frappe.log_error(
                f"❌ APNs push failed ({res.status_code}): {res.text}",
                "APNs Push Error"
            )
            return {"success": False, "error": res.text}

    except Exception as e:
        frappe.log_error(f"APNs request failed: {str(e)}", "APNs Push Exception")
        return {"success": False, "error": str(e)}
