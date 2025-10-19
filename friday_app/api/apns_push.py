import frappe
from apns2_client.client import APNsClient
from apns2_client.payload import Payload
import os


def _client():
    key_file = frappe.conf.get("APN_KEY_FILE")
    key_id = frappe.conf.get("APN_KEY_ID")
    team_id = frappe.conf.get("APN_TEAM_ID")
    bundle = frappe.conf.get("APN_BUNDLE_ID")

    if not all([key_file, key_id, team_id, bundle]):
        frappe.throw("Missing APNs configuration in site_config.json")

    client = APNsClient(
        key_file,
        use_sandbox=False,  # nastav True, ak testuješ na dev provisioning profile
        team_id=team_id,
        key_id=key_id
    )

    topic = f"{bundle}.voip"
    return client, topic


def send_incoming_call_push(device_token: str, caller_id: str, caller_name: str):
    """Pošle VoIP push notifikáciu na iPhone"""
    try:
        client, topic = _client()

        payload = Payload(
            alert={"title": "Incoming Call", "body": caller_name},
            sound=None,
            badge=0,
            content_available=True,
            custom={
                "type": "incoming_call",
                "callerId": caller_id,
                "callerName": caller_name
            }
        )

        client.send_notification(device_token, payload, topic=topic, priority=10)
        frappe.logger().info(f"APNs push sent to {device_token}")

    except Exception as e:
        frappe.log_error(f"APNs push error: {e}", "VoIP Push Failed")
        raise
