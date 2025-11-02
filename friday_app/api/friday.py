import frappe
from frappe import _
from frappe.utils import now
from .utils import (
    log_info,
    log_error,
    now_iso,
    send_apns_notification,
    deduct_minutes_from_user,
    verify_clerk_token,
)


# =============== HELPERS ===============

def _get_current_user_id_from_clerk():
    auth_header = frappe.get_request_header("Authorization")
    if not auth_header:
        frappe.throw("Missing Authorization header", frappe.PermissionError)

    jwt_token = (
        auth_header.replace("Bearer ", "")
        .replace("Token ", "")
        .replace("token ", "")
        .strip()
    )
    clerk_user = verify_clerk_token(jwt_token)
    if not clerk_user:
        frappe.throw("Invalid Clerk token", frappe.PermissionError)

    clerk_id = clerk_user.get("sub") or clerk_user.get("id")
    user_id = frappe.db.get_value("Friday User", {"clerk_id": clerk_id}, "name")
    if not user_id:
        frappe.throw("Friday User not found", frappe.PermissionError)
    return user_id


# =============== ADMIN ===============

@frappe.whitelist(allow_guest=False)
def admin_clients():
    """
    Admin → potrebuje vidieť klientov + ich zariadenia + minúty.
    """
    # TEMP: vypneme admin check pre test
    # user_id = _get_current_user_id_from_clerk()
    # role = frappe.db.get_value("Friday User", user_id, "role")
    # if role != "admin":
    #     frappe.throw("Access denied: admin only", frappe.PermissionError)

    users = frappe.get_all(
        "Friday User",
        filters={"role": "client", "status": "active"},
        fields=["name as id", "username", "email", "status", "role"]
    )

    out = []
    for u in users:
        devices = frappe.get_all(
            "Device",
            filters={"user": u["id"]},
            fields=["voip_token as voipToken", "apns_token as apnsToken", "modified as updatedAt"]
        )
        tokens = frappe.get_all(
            "Friday Token",
            filters={"owner_user": u["id"], "status": ["in", ["active", "listed"]]},
            fields=["minutes_remaining as minutesRemaining", "status"]
        )
        out.append({
            "id": u["id"],
            "username": u.get("username") or u.get("email"),
            "devices": devices,
            "tokens": tokens
        })

    return {"success": True, "clients": out}

# =============== CALLS ===============

@frappe.whitelist(allow_guest=False, methods=["POST"])
def start_call():
    """
    Spustí hovor: caller → callee.
    - nájde device callee
    - pošle mu APNs
    - vytvorí Call Log
    """
    caller = _get_current_user_id_from_clerk()
    data = frappe.request.get_json() or {}
    callee = data.get("advisorId") or data.get("advisor_id") or data.get("callee_id")
    caller_name = data.get("caller_name") or frappe.db.get_value("Friday User", caller, "username") or "Volajúci"

    if not callee:
        frappe.throw("Missing callee_id")

    device = frappe.db.get_value(
        "Device",
        {"user": callee},
        ["voip_token", "apns_token"],
        as_dict=True
    )
    if not device or not (device.voip_token or device.apns_token):
        return {
            "success": False,
            "error": "User has no device token"
        }

    # vytvor call log
    call_id = frappe.generate_hash(length=12)
    doc = frappe.get_doc({
        "doctype": "Call Log",
        "caller": caller,
        "advisor": callee,
        "call_id": call_id,
        "status": "started",
        "started_at": now_iso()
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # pošli push
    send_apns_notification(
        device_token=device.voip_token or device.apns_token,
        title="Prichádzajúci hovor",
        body=f"Volá ti {caller_name}",
        extra={"call_id": call_id, "caller_id": caller}
    )

    log_info(f"Call {call_id} from {caller} → {callee}")
    return {"success": True, "callId": call_id}


@frappe.whitelist(allow_guest=False, methods=["POST"])
def end_call():
    """
    Klient alebo admin ukončí hovor.
    - označí Call Log ako ended
    - odpočíta minúty
    """
    user_id = _get_current_user_id_from_clerk()
    data = frappe.request.get_json() or {}
    call_id = data.get("call_id")
    duration = int(data.get("duration") or 1)

    if not call_id:
        frappe.throw("Missing call_id")

    if frappe.db.exists("Call Log", call_id):
        frappe.db.set_value("Call Log", call_id, {
            "ended_at": now_iso(),
            "status": "ended",
            "duration": duration
        })
        # odpočítaj minúty volajúcemu
        used_token = deduct_minutes_from_user(user_id, minutes=duration)
        if used_token:
            frappe.db.set_value("Call Log", call_id, "used_token", used_token)
        frappe.db.commit()
        log_info(f"Call {call_id} ended, duration {duration}")
        return {"success": True, "duration": duration}
    else:
        return {"success": False, "error": "Call not found"}


# =============== USER BALANCE ===============

@frappe.whitelist(allow_guest=False)
def balance(user_id=None):
    if not user_id:
        user_id = _get_current_user_id_from_clerk()
    tokens = frappe.get_all(
        "Friday Token",
        filters={"owner_user": user_id, "status": "active"},
        fields=["name", "minutes_remaining", "issued_year"]
    )
    total = sum([t.minutes_remaining for t in tokens]) if tokens else 0
    return {"success": True, "total_minutes": total, "tokens": tokens}
