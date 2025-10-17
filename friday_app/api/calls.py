import frappe
from frappe import _
from frappe.utils import now_datetime, time_diff_in_seconds
from friday_app.api.push import send_voip_push
from datetime import datetime
import json
import http.client
import jwt
import time
import os

# --------------------------------------------
# START CALL
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def start_call(caller_id: str, advisor_id: str):
    if not caller_id or not advisor_id:
        frappe.throw(_("Missing caller_id or advisor_id"))

    caller = frappe.db.get_value("Friday User", {"user_id": caller_id}, "name")
    advisor = frappe.db.get_value("Friday User", {"user_id": advisor_id}, "name")
    if not caller or not advisor:
        frappe.throw(_("Caller or advisor not found"))

    token = frappe.get_all(
        "Friday Token",
        filters={"owner_user": caller_id, "status": "active"},
        fields=["name", "minutes_remaining"],
        order_by="created_at asc",
        limit=1
    )
    if not token:
        frappe.throw(_("No active tokens available"))
    token = token[0]

    if token.minutes_remaining <= 0:
        frappe.db.set_value("Friday Token", token.name, "status", "spent")
        frappe.throw(_("Token has no remaining minutes"))

    call = frappe.get_doc({
        "doctype": "Call Log",
        "caller": caller_id,
        "advisor": advisor_id,
        "started_at": now_datetime(),
        "used_token": token.name
    })
    call.insert(ignore_permissions=True)
    frappe.db.commit()

    send_voip_push(advisor_id, call.name, caller_id)

    return {
        "message": "Call started",
        "call_id": call.name,
        "token_id": token.name,
        "minutes_remaining": token.minutes_remaining
    }


# --------------------------------------------
# END CALL
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def end_call(call_id: str):
    if not call_id:
        frappe.throw(_("Missing call_id"))

    call = frappe.get_doc("Call Log", call_id)
    if not call:
        frappe.throw(_("Call not found"))

    if call.ended_at:
        return {"message": "Call already ended"}

    call.ended_at = now_datetime()
    duration_seconds = time_diff_in_seconds(call.ended_at, call.started_at)
    call.duration = int(duration_seconds / 60)
    call.save(ignore_permissions=True)

    token = frappe.get_doc("Friday Token", call.used_token)
    remaining = max(0, int(token.minutes_remaining) - call.duration)
    token.minutes_remaining = remaining
    token.status = "active" if remaining > 0 else "spent"
    token.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.get_doc({
        "doctype": "Transaction",
        "user": call.caller,
        "type": "call_usage",
        "amount_eur": 0,
        "seconds_delta": -call.duration * 60,
        "note": f"Call ended, duration {call.duration} minutes"
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "message": "Call ended",
        "duration_minutes": call.duration,
        "remaining": remaining
    }


# --------------------------------------------
# GET CALL LOG
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_call_log(user_id: str):
    if not user_id:
        frappe.throw(_("Missing user_id"))

    calls = frappe.get_all(
        "Call Log",
        filters=[
            ["caller", "=", user_id],
            ["advisor", "=", user_id]
        ],
        or_filters=True,
        fields=["name", "caller", "advisor", "started_at", "ended_at", "duration", "used_token"],
        order_by="started_at desc"
    )
    return {"calls": calls}


# --------------------------------------------
# GET ACTIVE CALL
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_active_call(user_id: str):
    if not user_id:
        frappe.throw(_("Missing user_id"))

    active = frappe.get_all(
        "Call Log",
        filters={"caller": user_id, "ended_at": ["is", "not set"]},
        fields=["name", "advisor", "started_at", "used_token"],
        limit=1
    )

    if not active:
        return {"active": False}

    return {"active": True, "call": active[0]}
