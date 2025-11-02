import frappe
import time
import json
import jwt
from datetime import datetime


# ============= LOGGING =============

def log_info(msg: str):
    frappe.logger().info(f"[FRIDAY] {msg}")


def log_error(msg: str, title: str = "Friday Error"):
    frappe.log_error(message=msg, title=title)


# ============= TIME HELPERS =============

def now_iso() -> str:
    return datetime.utcnow().isoformat()


# ============= CLERK VERIFY =============
# číta clerk_api_key zo site_config.json

def verify_clerk_token(token: str):
    """
    Overí Clerk JWT cez Clerk API a vráti dict s userom.
    Vráti None ak token nie je validný.
    """
    clerk_key = frappe.conf.get("clerk_api_key")
    if not clerk_key:
        log_error("Missing clerk_api_key in site_config.json")
        return None

    import requests
    try:
        res = requests.post(
            "https://api.clerk.dev/v1/tokens/verify",
            headers={
                "Authorization": f"Bearer {clerk_key}",
                "Content-Type": "application/json"
            },
            json={"token": token}
        )
    except Exception as e:
        log_error(f"Clerk verify request failed: {str(e)}", "Clerk Auth Error")
        return None

    if res.status_code != 200:
        log_error(f"Clerk verify failed: {res.text}", "Clerk Auth Error")
        return None

    return res.json()


# ============= APNs SEND =============

def send_apns_notification(device_token: str, title: str, body: str, extra: dict | None = None):
    """
    Pošle APNs (alebo VoIP) notifikáciu na iOS.
    Údaje berie z Single Doctype 'APNs Push'.
    """
    if not device_token:
        log_error("send_apns_notification called without device_token")
        return

    try:
        settings = frappe.get_single("APNs Push")
    except Exception:
        log_error("APNs Push single doctype not found")
        return

    key_id = settings.key_id
    team_id = settings.team_id
    auth_key = settings.auth_key
    bundle_id = settings.bundle_id
    use_sandbox = settings.is_sandbox

    if not key_id or not team_id or not auth_key or not bundle_id:
        log_error("APNs settings incomplete")
        return

    # vygeneruj JWT pre Apple
    token = jwt.encode(
        {
            "iss": team_id,
            "iat": int(time.time())
        },
        auth_key,
        algorithm="ES256",
        headers={
            "alg": "ES256",
            "kid": key_id
        }
    )

    host = "api.sandbox.push.apple.com" if use_sandbox else "api.push.apple.com"

    from httpx import Client
    payload = {
        "aps": {
            "alert": {
                "title": title,
                "body": body
            },
            "sound": "default"
        }
    }
    if extra:
        payload.update(extra)

    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": bundle_id,
        "apns-push-type": "alert",
        "content-type": "application/json"
    }

    url = f"https://{host}/3/device/{device_token}"

    try:
        with Client(http2=True, timeout=10.0) as client:
            res = client.post(url, headers=headers, content=json.dumps(payload))
        if res.status_code != 200:
            log_error(f"APNs push failed ({res.status_code}): {res.text}")
        else:
            log_info(f"APNs push OK → {device_token[:8]}…")
    except Exception as e:
        log_error(f"APNs request failed: {str(e)}")


# ============= TOKEN UTILS =============

def deduct_minutes_from_user(user_id: str, minutes: int = 1):
    """
    Zoberie prvý aktívny token používateľa a odpočíta mu minúty.
    Jednoduchá verzia – stačí na MVP.
    """
    tokens = frappe.get_all(
        "Friday Token",
        filters={"owner_user": user_id, "status": "active"},
        fields=["name", "minutes_remaining"],
        order_by="created_at asc"
    )
    if not tokens:
        log_info(f"User {user_id} has no active tokens")
        return None

    tok = tokens[0]
    remaining = int(tok.minutes_remaining or 0)
    remaining = max(remaining - minutes, 0)

    frappe.db.set_value("Friday Token", tok.name, {
        "minutes_remaining": remaining,
        "last_used_at": now_iso()
    })
    if remaining == 0:
        frappe.db.set_value("Friday Token", tok.name, "status", "spent")

    frappe.db.commit()
    log_info(f"Deducted {minutes} minutes from token {tok.name} ({user_id})")
    return tok.name
