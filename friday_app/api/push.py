import json, os
import frappe
from apns2.client import APNsClient
from apns2.payload import Payload

def _client():
    key_file = frappe.conf.get("APN_KEY_FILE")
    key_id = frappe.conf.get("APN_KEY_ID")
    team_id = frappe.conf.get("APN_TEAM_ID")
    bundle = frappe.conf.get("APN_BUNDLE_ID")
    if not all([key_file, key_id, team_id, bundle]):
        raise frappe.ValidationError("Missing APNs env")
    # VoIP topic = bundle + ".voip"
    client = APNsClient(key_file, use_sandbox=False, team_id=team_id, key_id=key_id)
    return client, f"{bundle}.voip"

def send_incoming_call_push(device_token: str, caller_id: str, caller_name: str):
    client, topic = _client()
    pl = Payload(alert={"title": "Incoming Call", "body": caller_name}, sound=None, badge=0, content_available=True, custom={"type": "incoming_call", "callerId": caller_id, "callerName": caller_name})
    client.send_notification(device_token, pl, topic=topic, priority=10)
