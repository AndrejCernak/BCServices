import frappe
import requests
import json
from datetime import datetime

# Clerk API kľúč z Configu (získaj ho z Clerk Dashboard a vlož do site_config.json)
CLERK_API_KEY = frappe.conf.get("clerk_api_key")

# ===============================
# 🔐 Helper: Verify Clerk JWT
# ===============================
def verify_clerk_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        frappe.throw("Unauthorized", frappe.PermissionError)

    token = auth_header.split(" ")[1]

    res = requests.get(
        "https://api.clerk.dev/v1/tokens/verify",
        headers={
            "Authorization": f"Bearer {CLERK_API_KEY}",
            "Content-Type": "application/json"
        },
        json={"token": token}
    )

    if res.status_code != 200:
        frappe.throw("Invalid or expired token", frappe.PermissionError)

    return res.json()  # obsahuje user_id, email, atď.


# ===============================
# 📲 1️⃣ Register Device
# ===============================
@frappe.whitelist(allow_guest=True)
def register_device(voipToken=None, apnsToken=None):
    auth = frappe.request.headers.get("Authorization")
    user_data = verify_clerk_token(auth)

    user_id = user_data.get("sub")
    username = user_data.get("username") or user_data.get("email")

    # skús nájsť už existujúce zariadenie
    existing = frappe.db.get_all("Friday Device", filters={"user_id": user_id}, pluck="name")
    if existing:
        doc = frappe.get_doc("Friday Device", existing[0])
        doc.voip_token = voipToken
        doc.apns_token = apnsToken
        doc.updated_at = frappe.utils.now()
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Friday Device",
            "user_id": user_id,
            "username": username,
            "voip_token": voipToken,
            "apns_token": apnsToken,
            "updated_at": frappe.utils.now()
        }).insert(ignore_permissions=True)

    return {"success": True}


# ===============================
# 👥 2️⃣ Get Admin Clients
# ===============================
@frappe.whitelist(allow_guest=True)
def admin_clients():
    auth = frappe.request.headers.get("Authorization")
    user_data = verify_clerk_token(auth)

    # tu môžeš obmedziť iba na admina ak chceš
    # if user_data.get("email") != "admin@example.com": frappe.throw("Forbidden")

    users = frappe.db.get_all("Friday User", fields=["name", "username"])
    result = []

    for u in users:
        devices = frappe.db.get_all(
            "Friday Device",
            filters={"user_id": u.name},
            fields=["voip_token", "updated_at"]
        )

        tokens = frappe.db.get_all(
            "Friday Token",
            filters={"user_id": u.name},
            fields=["minutes_remaining", "status"]
        )

        result.append({
            "id": u.name,
            "username": u.username,
            "devices": devices,
            "tokens": tokens
        })

    return {"success": True, "clients": result}


# ===============================
# 📞 3️⃣ Start Call
# ===============================
@frappe.whitelist(allow_guest=True)
def start_call(callerId=None, callerName=None, advisorId=None):
    auth = frappe.request.headers.get("Authorization")
    verify_clerk_token(auth)

    if not callerId or not advisorId:
        frappe.throw("Missing callerId or advisorId")

    # vytvor nový Call Log záznam
    call_doc = frappe.get_doc({
        "doctype": "Friday Call Log",
        "caller_id": callerId,
        "caller_name": callerName,
        "receiver_id": advisorId,
        "status": "ringing",
        "started_at": frappe.utils.now()
    }).insert(ignore_permissions=True)

    # nájdi VoIP token cieľa
    device = frappe.db.get_all("Friday Device", filters={"user_id": advisorId}, fields=["voip_token"], limit=1)
    if device and device[0].get("voip_token"):
        voip_token = device[0]["voip_token"]
        # (tu by šiel APNs push cez tvoju existujúcu apns_push.py funkciu)
        frappe.enqueue("friday_app.api.apns_push.send_voip_push", voip_token=voip_token, caller_name=callerName)

    return {"success": True, "callId": call_doc.name}


# ===============================
# 🔚 4️⃣ End Call
# ===============================
@frappe.whitelist(allow_guest=True)
def end_call(callId=None):
    auth = frappe.request.headers.get("Authorization")
    verify_clerk_token(auth)

    if not callId:
        frappe.throw("Missing callId")

    call = frappe.get_doc("Friday Call Log", callId)
    call.status = "ended"
    call.ended_at = frappe.utils.now()
    call.save(ignore_permissions=True)

    # (voliteľne odpočítať minúty podľa trvania)
    return {"success": True}


# ===============================
# 💰 5️⃣ SSO Redirect
# ===============================
@frappe.whitelist(allow_guest=True)
def sso(token=None):
    if not token:
        frappe.throw("Missing token")
    # len vráti URL redirect (napr. na tvoju webovú burzu)
    redirect_url = f"https://piatkove-tokeny.sk/burza?token={token}"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = redirect_url
    return
