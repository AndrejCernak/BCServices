import frappe
from frappe import _
from .utils import verify_clerk_token, log_info, log_error
from frappe.utils import now


@frappe.whitelist(allow_guest=True, methods=["POST", "GET"])
def sync_user():
    """
    iOS → po prihlásení cez Clerk pošle JWT.
    My overíme u Clerka a uložíme / aktualizujeme Friday User.
    """
    auth_header = frappe.get_request_header("Authorization")
    if not auth_header:
        frappe.throw(_("Missing Authorization header"))

    jwt_token = (
        auth_header.replace("Bearer ", "")
        .replace("Token ", "")
        .replace("token ", "")
        .strip()
    )

    clerk_user = verify_clerk_token(jwt_token)
    if not clerk_user:
        frappe.throw(_("Invalid Clerk token"))

    clerk_id = clerk_user.get("sub") or clerk_user.get("id")
    email = clerk_user.get("email") or (
        clerk_user.get("email_addresses", [{}])[0].get("email_address")
        if isinstance(clerk_user.get("email_addresses"), list)
        else None
    )
    username = clerk_user.get("username") or (email.split("@")[0] if email else None)
    first_name = clerk_user.get("first_name")
    last_name = clerk_user.get("last_name")

    if not clerk_id:
        frappe.throw(_("Clerk user id not found"))

    existing = frappe.db.get_value("Friday User", {"clerk_id": clerk_id}, "name")
    if not existing:
        doc = frappe.get_doc({
            "doctype": "Friday User",
            "clerk_id": clerk_id,
            "email": email,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "role": "client",
            "status": "active"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log_info(f"Created Friday User for {email}")
        return {"success": True, "created": True, "user_id": doc.name}
    else:
        frappe.db.set_value("Friday User", existing, {
            "email": email,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "status": "active"
        })
        frappe.db.commit()
        log_info(f"Updated Friday User {existing}")
        return {"success": True, "updated": True, "user_id": existing}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_device():
    """
    iOS → pošle voip_token + apns_token.
    My si z JWT zistíme, kto je používateľ a uložíme zariadenie.
    """
    auth_header = frappe.get_request_header("Authorization")
    if not auth_header:
        frappe.throw(_("Missing Authorization header"))

    jwt_token = (
        auth_header.replace("Bearer ", "")
        .replace("Token ", "")
        .replace("token ", "")
        .strip()
    )
    clerk_user = verify_clerk_token(jwt_token)
    if not clerk_user:
        frappe.throw(_("Invalid Clerk token"))

    clerk_id = clerk_user.get("sub") or clerk_user.get("id")
    user_id = frappe.db.get_value("Friday User", {"clerk_id": clerk_id}, "name")
    if not user_id:
        frappe.throw(_("Friday User not found"))

    data = frappe.request.get_json() or {}
    voip_token = data.get("voip_token")
    apns_token = data.get("apns_token")
    device_type = data.get("device_type") or "iOS"

    if not voip_token and not apns_token:
        frappe.throw(_("Missing voip_token or apns_token"))

    existing = frappe.db.get_value("Device", {"user": user_id}, "name")
    payload = {
        "user": user_id,
        "voip_token": voip_token,
        "apns_token": apns_token,
        "device_type": device_type
    }

    if existing:
        doc = frappe.get_doc("Device", existing)
        for k, v in payload.items():
            if v:
                setattr(doc, k, v)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        log_info(f"Updated device for {user_id}")
        return {"success": True, "updated": True}
    else:
        payload["doctype"] = "Device"
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log_info(f"Registered new device for {user_id}")
        return {"success": True, "created": True}


@frappe.whitelist(allow_guest=False)
def me():
    """
    Vráti info o prihlásenom používateľovi (podľa JWT).
    """
    auth_header = frappe.get_request_header("Authorization")
    if not auth_header:
        frappe.throw(_("Missing Authorization header"))

    jwt_token = (
        auth_header.replace("Bearer ", "")
        .replace("Token ", "")
        .replace("token ", "")
        .strip()
    )
    clerk_user = verify_clerk_token(jwt_token)
    if not clerk_user:
        frappe.throw(_("Invalid Clerk token"))

    clerk_id = clerk_user.get("sub") or clerk_user.get("id")
    user = frappe.db.get_value(
        "Friday User",
        {"clerk_id": clerk_id},
        ["name", "email", "username", "role", "status"],
        as_dict=True
    )
    return {"success": True, "user": user}
