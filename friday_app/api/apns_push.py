import frappe
from pushjack import APNSClient


def _client():
    cert = frappe.conf.get("APN_KEY_FILE")
    bundle = frappe.conf.get("APN_BUNDLE_ID")
    if not all([cert, bundle]):
        frappe.throw("Missing APNs configuration in site_config.json")

    client = APNSClient(
        cert=cert,
        default_error_timeout=10,
        default_expiration_offset=2592000,
        default_batch_size=100,
        sandbox=False,  # True ak testuješ
    )
    topic = f"{bundle}.voip"
    return client, topic


def send_incoming_call_push(device_token: str, caller_id: str, caller_name: str):
    """Pošle VoIP push notifikáciu na iPhone"""
    try:
        client, topic = _client()

        alert = {"title": "Incoming Call", "body": caller_name}
        payload = {
            "aps": {
                "alert": alert,
                "sound": None,
                "badge": 0,
                "content-available": 1,
            },
            "type": "incoming_call",
            "callerId": caller_id,
            "callerName": caller_name,
        }

        res = client.send(device_token, payload, topic=topic, priority=10)
        frappe.logger().info(f"APNs push sent to {device_token}: {res}")

    except Exception as e:
        frappe.log_error(f"APNs push error: {e}", "VoIP Push Failed")
        raise
