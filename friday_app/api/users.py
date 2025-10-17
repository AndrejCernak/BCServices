import frappe
from frappe import _


# --------------------------------------------
# 🔐 Helper – kontrola admin prístupu
# --------------------------------------------
def _check_admin():
    if frappe.session.user != "Administrator":
        frappe.throw(_("Not permitted"), frappe.PermissionError)


# --------------------------------------------
# 🔄 SYNC USER (Clerk ID)
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def sync_user(user_id, role):
    """Synchronizuje používateľa podľa user_id (Clerk ID)."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    user_name = frappe.db.get_value("Friday User", {"user_id": user_id}, "name")

    if user_name:
        frappe.db.set_value("Friday User", user_name, "role", role)
        frappe.db.commit()
        return {"message": "User updated", "user_id": user_id}
    else:
        doc = frappe.get_doc({
            "doctype": "Friday User",
            "user_id": user_id,
            "role": role
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"message": "User created", "user_id": user_id}


# --------------------------------------------
# 📱 REGISTER DEVICE
# --------------------------------------------
@frappe.whitelist(allow_guest=False)
def register_device(user_id: str, voip_token: str = None, apns_token: str = None):
    """Registruje alebo aktualizuje zariadenie používateľa."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    # zisti 'name' podľa user_id
    user_name = frappe.db.get_value("Friday User", {"user_id": user_id}, "name")
    if not user_name:
        frappe.throw(_("User not found"))

    device_name = frappe.db.exists("Device", {"user": user_name})
    if device_name:
        device = frappe.get_doc("Device", device_name)
        if voip_token:
            device.voip_token = voip_token
        if apns_token:
            device.apns_token = apns_token
        device.save(ignore_permissions=True)
        msg = "Device updated"
    else:
        device = frappe.get_doc({
            "doctype": "Device",
            "user": user_name,
            "voip_token": voip_token,
            "apns_token": apns_token
        })
        device.insert(ignore_permissions=True)
        msg = "Device registered"

    frappe.db.commit()
    return {"success": True, "message": msg, "device": device.name}



# --------------------------------------------
# 👤 GET USER DETAILS
# --------------------------------------------
@frappe.whitelist(allow_guest=False)
def get_user(user_id: str):
    """Vráti detaily používateľa vrátane tokenov a zariadení."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    user_doc = frappe.db.get_value(
        "Friday User",
        {"user_id": user_id},
        ["name", "user_id", "role", "creation"],
        as_dict=True
    )

    if not user_doc:
        frappe.throw(_("User not found"))

    tokens = frappe.get_all(
        "Friday Token",
        filters={"owner": user_id},
        fields=["name", "status", "issued_year"]
    )

    devices = frappe.get_all(
        "Device",
        filters={"user": user_id},
        fields=["name", "voip_token", "apns_token"]
    )

    return {"user": user_doc, "tokens": tokens, "devices": devices}


# --------------------------------------------
# 🗑️ DELETE USER (Admin only)
# --------------------------------------------
@frappe.whitelist()
def delete_user(user_id: str):
    """Vymaže používateľa a všetky jeho tokeny a zariadenia."""
    _check_admin()

    frappe.db.delete("Device", {"user": user_id})
    frappe.db.delete("Friday Token", {"owner": user_id})
    frappe.db.delete("Friday User", {"user_id": user_id})
    frappe.db.commit()

    return {"deleted": True, "user_id": user_id}


# --------------------------------------------
# 🔑 SSO REDIRECT (Clerk / OAuth)
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def sso_redirect(token: str):
    """Simuluje pôvodný Clerk SSO redirect endpoint."""
    if not token:
        frappe.throw(_("Missing token"))

    frontend_url = frappe.conf.get("FRONTEND_URL", "https://frontendtokeny.vercel.app")
    redirect_url = f"{frontend_url}/login?token={token}"

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = redirect_url


# --------------------------------------------
# 📋 LIST ALL USERS (Admin only)
# --------------------------------------------
@frappe.whitelist()
def list_all_users():
    """Vráti všetkých používateľov (len pre administrátora)."""
    _check_admin()
    users = frappe.get_all(
        "Friday User",
        fields=["name", "user_id", "role", "creation"],
        order_by="creation desc"
    )
    return {"users": users}
