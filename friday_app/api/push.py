import os
import jwt
import time
import httpx
from datetime import datetime
import frappe
from frappe import _


# ----------------------------------------
# 🔐 GENERATE APNs AUTH TOKEN
# ----------------------------------------
def generate_apns_token():
    """Vytvorí JWT token pre Apple Push Notification Service (HTTP/2)"""
    key_id = frappe.conf.get("APN_KEY_ID")
    team_id = frappe.conf.get("APN_TEAM_ID")
    key_path = frappe.conf.get("APN_KEY_FILE")

    if not key_id or not team_id or not key_path:
        frappe.throw(_("Missing APNs configuration in site_config.json"))

    if not os.path.exists(key_path):
        frappe.throw(_("APN key file not found at path: ") + key_path)

    with open(key_path, "r") as f:
        secret = f.read()

    headers = {"alg": "ES256", "kid": key_id}
    payload = {"iss": team_id, "iat": int(time.time())}

    return jwt.encode(payload, secret, algorithm="ES256", headers=headers)


# ----------------------------------------
# 📡 SEND APNs NOTIFICATION (GENERIC)
# ----------------------------------------
def send_apns_notification(device_token: str, payload: dict, push_type: str = "voip"):
    """Všeobecná funkcia na poslanie APNs pushu (HTTP/2)."""
    bundle_id = frappe.conf.get("APN_BUNDLE_ID")
    apns_topic = f"{bundle_id}.{push_type}"
    auth_token = generate_apns_token()
    apns_url = f"https://api.push.apple.com/3/device/{device_token}"

    headers = {
        "authorization": f"bearer {auth_token}",
        "apns-topic": apns_topic,
        "apns-push-type": push_type,
        "content-type": "application/json",
        "apns-expiration": "30"
    }

    with httpx.Client(http2=True, timeout=10.0) as client:
        response = client.post(apns_url, headers=headers, json=payload)

    frappe.logger().info(f"[APNs] {push_type.upper()} push to {device_token}: {response.status_code} {response.text}")

    try:
        return response.json()
    except Exception:
        return {"raw": response.text, "status": response.status_code}


# ----------------------------------------
# 📞 SEND VoIP PUSH FOR CALL
# ----------------------------------------
@frappe.whitelist(allow_guest=True)
def send_voip_push(user_id: str, call_id: str, caller_id: str):
    """Pošle VoIP push notifikáciu používateľovi (napr. prichádzajúci hovor)."""
    if not user_id or not call_id or not caller_id:
        frappe.throw(_("Missing parameters"))

    # 🔹 Získaj device token
    device_token = frappe.db.get_value("Device", {"user": user_id}, "voip_token")
    if not device_token:
        frappe.throw(_("User has no registered VoIP token"))

    payload = {
        "aps": {"content-available": 1},
        "callId": call_id,
        "callerId": caller_id,
        "timestamp": datetime.utcnow().isoformat()
    }

    return send_apns_notification(device_token, payload, push_type="voip")
