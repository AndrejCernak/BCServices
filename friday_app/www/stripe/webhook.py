import frappe, stripe, json
from bcservices.api.payments import handle_stripe_event

no_cache = 1
no_sitemap = 1

def get_context(context):
    # nepoužíva sa
    pass

@frappe.whitelist(allow_guest=True, methods=["POST"])
def index():
    payload = frappe.request.data
    sig = frappe.get_request_header("Stripe-Signature")
    secret = frappe.conf.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        frappe.throw("Missing STRIPE_WEBHOOK_SECRET")
    stripe.api_key = frappe.conf.get("STRIPE_SECRET_KEY")
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=secret)
    except Exception as e:
        frappe.throw(f"Webhook error: {e}")
    handle_stripe_event(event)
    return "ok"
