import frappe, stripe, json
from frappe.utils import now
from .auth import verify_bearer_and_get_user_id

def _stripe():
    key = frappe.conf.get("STRIPE_SECRET_KEY")
    if not key:
        frappe.throw("Missing STRIPE_SECRET_KEY")
    stripe.api_key = key
    return stripe

def _get_current_price():
    return frappe.db.get_single_value("Friday Settings", "current_price_eur") or 0.0

@frappe.whitelist(allow_guest=False, methods=["POST"])
def checkout_treasury(quantity:int, year:int):
    buyer = verify_bearer_and_get_user_id()
    price = _get_current_price()  # Friday Settings.current_price_eur :contentReference[oaicite:13]{index=13}
    amount = float(price) * int(quantity)

    s = _stripe().checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "eur", "product_data": {"name": f"Friday {year} minutes"}, "unit_amount": int(round(price*100))}, "quantity": int(quantity)}],
        success_url=f"{frappe.conf.get('APP_URL')}/success",
        cancel_url=f"{frappe.conf.get('APP_URL')}/cancel",
        metadata={"type":"treasury","buyer":buyer,"quantity":str(quantity),"year":str(year)}
    )

    pay = frappe.get_doc({
        "doctype": "Payment",
        "buyer": buyer,
        "type": "treasury",
        "quantity": int(quantity),
        "year": int(year),
        "amount_eur": amount,
        "status": "pending",
        "stripe_session_id": s.id,
        "created_at": now()
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    return {"url": s.url}

@frappe.whitelist(allow_guest=False, methods=["POST"])
def checkout_listing(listing: str):
    buyer = verify_bearer_and_get_user_id()
    lst = frappe.get_doc("Friday Listing", listing)  # token, seller, price_eur, status=open :contentReference[oaicite:14]{index=14}
    if lst.status != "open":
        frappe.throw("Listing is not open")
    price_cents = int(round(float(lst.price_eur)*100))
    s = _stripe().checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "eur", "product_data": {"name": "Friday Listing"}, "unit_amount": price_cents}, "quantity": 1}],
        success_url=f"{frappe.conf.get('APP_URL')}/success",
        cancel_url=f"{frappe.conf.get('APP_URL')}/cancel",
        metadata={"type":"listing","buyer":buyer,"listing":listing,"token":lst.token,"seller":lst.seller}
    )
    pay = frappe.get_doc({
        "doctype": "Payment",
        "buyer": buyer,
        "listing": listing,
        "type": "listing",
        "quantity": 1,
        "amount_eur": float(lst.price_eur),
        "status": "pending",
        "stripe_session_id": s.id,
        "created_at": now()
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    return {"url": s.url}

# Fulfillment webhook (called from www/stripe/webhook.py)
def _fulfill_treasury(buyer: str, quantity: int, year: int, amount: float):
    price = (amount / max(quantity,1))
    # Mintneme presne N tokenov (minutes_remaining = 60) a priradíme buyerovi
    for _ in range(int(quantity)):
        tok = frappe.get_doc({
            "doctype":"Friday Token",
            "issued_year": int(year),
            "minutes_remaining": 60,
            "status":"active",
            "original_price_eur": price,
            "owner_user": buyer,
            "created_at": frappe.utils.now(),
            "updated_at": frappe.utils.now()
        }).insert(ignore_permissions=True)
        frappe.get_doc({
            "doctype":"Friday Purchase Item",
            "user": buyer,
            "token": tok.name,
            "unit_price_eur": price,
            "created_at": frappe.utils.now()
        }).insert(ignore_permissions=True)
        frappe.get_doc({
            "doctype":"Transaction",
            "user": buyer,
            "type":"friday_purchase",
            "amount_eur": price,
            "seconds_delta": 60*60,  # 60 min
            "note": f"Treasury {year}",
            "created_at": frappe.utils.now()
        }).insert(ignore_permissions=True)
    frappe.db.commit()

def _fulfill_listing(buyer: str, listing: str, token: str, seller: str, amount: float):
    # 1) zamkneme listing
    lst = frappe.get_doc("Friday Listing", listing)
    if lst.status != "open":
        return
    # 2) prevedieme token ownera
    tok = frappe.get_doc("Friday Token", token)  # owner_user, status ("listed" -> "active") :contentReference[oaicite:15]{index=15}
    tok.owner_user = buyer
    tok.status = "active"
    tok.updated_at = frappe.utils.now()
    tok.save(ignore_permissions=True)
    # 3) listing close
    lst.status = "sold"
    lst.closed_at = frappe.utils.now()
    lst.save(ignore_permissions=True)
    # 4) trade record
    platform_fee = round(amount * 0.05, 2)  # príklad fee (uprav ak máš inak)
    frappe.get_doc({
        "doctype":"Friday Trade",
        "listing": listing,
        "token": token,
        "seller": seller,
        "buyer": buyer,
        "price_eur": amount,
        "platform_fee_eur": platform_fee,
        "created_at": frappe.utils.now()
    }).insert(ignore_permissions=True)
    # 5) transakcie buyer/seller
    frappe.get_doc({
        "doctype":"Transaction","user": buyer,"type":"friday_trade_buy",
        "amount_eur": amount,"seconds_delta": 0,"note": f"Bought {token}","created_at": frappe.utils.now()
    }).insert(ignore_permissions=True)
    frappe.get_doc({
        "doctype":"Transaction","user": seller,"type":"friday_trade_sell",
        "amount_eur": amount - platform_fee,"seconds_delta": 0,"note": f"Sold {token}","created_at": frappe.utils.now()
    }).insert(ignore_permissions=True)
    frappe.db.commit()

def handle_stripe_event(evt: dict):
    typ = evt.get("type")
    data = evt.get("data", {}).get("object", {})
    if typ == "checkout.session.completed":
        md = data.get("metadata") or {}
        pay = frappe.db.get_value("Payment", {"stripe_session_id": data.get("id")}, ["name","type","buyer","quantity","year","listing","status","amount_eur"], as_dict=True)
        if not pay:
            return
        if pay.status == "succeeded":
            return
        # mark paid
        frappe.db.set_value("Payment", pay.name, {"status":"succeeded","stripe_payment_intent": data.get("payment_intent")})
        if md.get("type") == "treasury":
            _fulfill_treasury(pay.buyer, int(pay.quantity), int(pay.year), float(pay.amount_eur))
        elif md.get("type") == "listing":
            _fulfill_listing(pay.buyer, pay.listing, md.get("token"), md.get("seller"), float(pay.amount_eur))
