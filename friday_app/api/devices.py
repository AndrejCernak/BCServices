import frappe
from frappe import _
import jwt
import time
import json
import http.client
from pathlib import Path
from friday_app.api.push import send_apns_notification



# --------------------------------------------
# 🔐 REGISTER DEVICE TOKENS
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def register_device(user_id: str, voip_token: str = None, apns_token: str = None):
    """Registruje alebo aktualizuje zariadenie používateľa pre VoIP / APNs push."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    if not frappe.db.exists("Friday User", {"user_id": user_id}):
        frappe.throw(_("User not found"))

    device_name = frappe.db.exists("Device", {"user": user_id})

    if device_name:
        doc = frappe.get_doc("Device", device_name)
        if voip_token:
            doc.voip_token = voip_token
        if apns_token:
            doc.apns_token = apns_token
        doc.save(ignore_permissions=True)
        msg = "Device updated"
    else:
        doc = frappe.get_doc({
            "doctype": "Device",
            "user": user_id,
            "voip_token": voip_token,
            "apns_token": apns_token
        })
        doc.insert(ignore_permissions=True)
        msg = "Device registered"

    frappe.db.commit()
    return {"success": True, "message": msg, "device_id": doc.name}


# --------------------------------------------
# 🔔 SEND VOIP PUSH
# --------------------------------------------
@frappe.whitelist(allow_guest=False)
def send_voip_push(user_id: str, call_id: str, caller_id: str):
    """Odošle VoIP push notifikáciu používateľovi (napr. prichádzajúci hovor)."""
    device_token = frappe.db.get_value("Device", {"user": user_id}, "voip_token")
    if not device_token:
        frappe.throw(_("No device token registered for this user."))

    payload = {
        "callId": call_id,
        "callerId": caller_id
    }

    response = _send_apns_notification(device_token, payload, push_type="voip")
    return {"status": "sent", "response": response}

