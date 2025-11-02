import frappe
from friday_app.api.utils import (
    log_info,
    log_error,
    success_response,
    error_response,
    require_fields,
    now_iso
)
from friday_app.api.auth import verify_clerk_token
from friday_app.api.apns_push import send_voip_push


# -----------------------------
# 👥 Admin - Zobrazenie klientov
# -----------------------------
@frappe.whitelist(allow_guest=False)
def admin_clients():
    """Získa zoznam všetkých klientov s ich zariadeniami a tokenmi."""
    try:
        clients = frappe.get_all(
            "Friday User",
            fields=["name as id", "username"]
        )

        for c in clients:
            c["devices"] = frappe.get_all(
                "Friday Device",
                filters={"user": c["id"]},
                fields=["voip_token as voipToken", "modified as updatedAt"]
            )
            c["tokens"] = frappe.get_all(
                "Friday Token",
                filters={"user": c["id"]},
                fields=["minutes_remaining as minutesRemaining", "status"]
            )

        return {"message": clients}

    except Exception as e:
        log_error(str(e), "Admin Clients Error")
        return error_response("Failed to load clients")


# -----------------------------
# 📱 Registrácia zariadenia
# -----------------------------
@frappe.whitelist(allow_guest=True)
def register_device():
    """
    Uloží alebo aktualizuje VoIP token zariadenia používateľa.
    Swift appka volá tento endpoint po prihlásení.
    """
    try:
        data = frappe.request.get_json()
        require_fields(data, ["user_id", "voip_token"])

        user_id = data["user_id"]
        voip_token = data["voip_token"]

        existing = frappe.get_all("Friday Device", filters={"user": user_id})
        if existing:
            frappe.db.set_value(
                "Friday Device", existing[0].name, "voip_token", voip_token
            )
            frappe.db.set_value(
                "Friday Device", existing[0].name, "modified", now_iso()
            )
            log_info(f"🔁 Updated VoIP token for user {user_id}")
        else:
            doc = frappe.get_doc({
                "doctype": "Friday Device",
                "user": user_id,
                "voip_token": voip_token
            })
            doc.insert()
            log_info(f"✅ Registered new device for user {user_id}")

        frappe.db.commit()
        return success_response(message="Device registered successfully")

    except Exception as e:
        log_error(str(e), "Register Device Error")
        return error_response("Failed to register device")


# -----------------------------
# 📞 Spustenie hovoru
# -----------------------------
@frappe.whitelist(allow_guest=False)
def start_call():
    """
    Admin alebo klient spustí hovor.
    - uloží záznam do Friday Call Log
    - pošle APNs VoIP notifikáciu druhému účastníkovi
    """
    try:
        data = frappe.request.get_json()
        require_fields(data, ["caller_id", "callee_id", "caller_name"])

        caller_id = data["caller_id"]
        callee_id = data["callee_id"]
        caller_name = data["caller_name"]

        voip = frappe.db.get_value("Friday Device", {"user": callee_id}, "voip_token")
        if not voip:
            return error_response("Recipient has no VoIP token")

        call_id = frappe.generate_hash(length=10)
        frappe.get_doc({
            "doctype": "Friday Call Log",
            "name": call_id,
            "caller": caller_id,
            "callee": callee_id,
            "status": "ringing",
            "started_at": now_iso()
        }).insert(ignore_permissions=True)

        frappe.db.commit()
        log_info(f"📞 New call {call_id} from {caller_name} → {callee_id}")

        # posielame push notifikáciu
        frappe.enqueue(
            "friday_app.api.apns_push.send_voip_push",
            voip_token=voip,
            caller_name=caller_name
        )

        return success_response(
            data={"callId": call_id},
            message="Call started successfully"
        )

    except Exception as e:
        log_error(str(e), "Start Call Error")
        return error_response("Failed to start call")


# -----------------------------
# 🚪 Ukončenie hovoru
# -----------------------------
@frappe.whitelist(allow_guest=False)
def end_call():
    """Označí hovor ako ukončený v databáze."""
    try:
        data = frappe.request.get_json()
        require_fields(data, ["call_id"])

        call_id = data["call_id"]
        if frappe.db.exists("Friday Call Log", call_id):
            frappe.db.set_value("Friday Call Log", call_id, "status", "ended")
            frappe.db.set_value("Friday Call Log", call_id, "ended_at", now_iso())
            frappe.db.commit()
            log_info(f"🔚 Call {call_id} marked as ended")
            return success_response(message="Call ended")
        else:
            return error_response("Call not found", status_code=404)

    except Exception as e:
        log_error(str(e), "End Call Error")
        return error_response("Failed to end call")


# -----------------------------
# 🔐 Overenie tokenu
# -----------------------------
@frappe.whitelist(allow_guest=True)
def verify_token():
    """Overí Clerk JWT token (volané z appky)."""
    try:
        token = frappe.get_request_header("Authorization")
        if not token:
            return error_response("Missing Authorization header", 401)

        valid, user_id = verify_clerk_token(token.replace("Bearer ", "").replace("token ", ""))
        if not valid:
            return error_response("Invalid token", 403)

        return success_response({"user_id": user_id}, "Token valid")

    except Exception as e:
        log_error(str(e), "Verify Token Error")
        return error_response("Token verification failed")
