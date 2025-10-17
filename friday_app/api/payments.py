import frappe
from frappe import _
import json
import stripe
from datetime import datetime


# --------------------------------------------
# 💳 STRIPE CONFIG
# --------------------------------------------
def get_stripe_client():
    """Načíta Stripe API key zo site_config.json"""
    api_key = frappe.conf.get("STRIPE_SECRET_KEY")
    if not api_key:
        frappe.throw(_("Missing STRIPE_SECRET_KEY in site_config.json"))
    stripe.api_key = api_key
    return stripe


# --------------------------------------------
# 🧾 CREATE CHECKOUT SESSION
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def create_checkout_session(user_id: str, minutes: int, price_eur: float):
    """Vytvorí Stripe Checkout session pre nákup tokenov (minút)."""
    if not user_id or not minutes or not price_eur:
        frappe.throw(_("Missing required parameters"))

    stripe_client = get_stripe_client()

    success_url = frappe.conf.get("FRONTEND_URL", "http://localhost:3000") + "/success?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = frappe.conf.get("FRONTEND_URL", "http://localhost:3000") + "/cancel"

    session = stripe_client.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Call Token – {minutes} min"},
                    "unit_amount": int(price_eur * 100)
                },
                "quantity": 1
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": user_id, "minutes": minutes, "price_eur": price_eur}
    )

    # 💾 Uložíme Payment Log
    existing = frappe.db.exists("Payment Log", {"stripe_session_id": session.id})
    if not existing:
        frappe.get_doc({
            "doctype": "Payment Log",
            "user": user_id,
            "stripe_session_id": session.id,
            "amount_eur": price_eur,
            "minutes": minutes,
            "status": "created"
        }).insert(ignore_permissions=True)
        frappe.db.commit()

    return {"session_url": session.url, "session_id": session.id}


# --------------------------------------------
# 🔁 STRIPE WEBHOOK HANDLER
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def stripe_webhook():
    """Webhook endpoint pre Stripe (vyvolá sa po zaplatení)."""
    stripe_client = get_stripe_client()

    payload = frappe.request.get_data(as_text=True)
    sig_header = frappe.get_request_header("stripe-signature")
    webhook_secret = frappe.conf.get("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        frappe.throw(_("Missing STRIPE_WEBHOOK_SECRET in site_config.json"))

    try:
        event = stripe_client.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except Exception as e:
        frappe.log_error(str(e), "Stripe Webhook Verification Failed")
        frappe.local.response.http_status_code = 400
        return {"error": str(e)}

    # ✅ Successful payment
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"]["user_id"]
        minutes = int(session["metadata"]["minutes"])
        amount = float(session["metadata"]["price_eur"])

        # 🪙 Vytvor nový token
        frappe.get_doc({
            "doctype": "Friday Token",
            "owner": user_id,
            "status": "active",
            "minutes_remaining": minutes
        }).insert(ignore_permissions=True)

        # 💼 Zaznamenaj transakciu
        frappe.get_doc({
            "doctype": "Transaction",
            "user": user_id,
            "type": "friday_trade_buy",
            "amount_eur": amount,
            "seconds_delta": minutes * 60,
            "note": f"Purchased {minutes} minutes via Stripe"
        }).insert(ignore_permissions=True)

        # 💾 Aktualizuj Payment Log
        frappe.db.set_value("Payment Log", {"stripe_session_id": session["id"]}, "status", "paid")
        frappe.db.commit()

        frappe.logger().info(f"✅ Stripe payment success: {user_id} bought {minutes} min")

    return {"status": "ok"}


# --------------------------------------------
# 📜 GET PAYMENT HISTORY
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_payment_history(user_id: str):
    """Vráti históriu platieb používateľa"""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    payments = frappe.get_all(
        "Payment Log",
        filters={"user": user_id},
        fields=["name", "amount_eur", "minutes", "status", "creation"],
        order_by="creation desc"
    )
    return {"payments": payments}
