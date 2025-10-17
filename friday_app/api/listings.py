import frappe
from frappe import _
from decimal import Decimal


# --------------------------------------------
# 🆕 CREATE LISTING
# --------------------------------------------
@frappe.whitelist()
def create_listing(user_id: str, token_id: str, price_eur: float):
    """Creates a new listing for a token."""
    if not frappe.db.exists("Friday Token", token_id):
        frappe.throw(_("Token not found"))

    # vytvor nový záznam
    doc = frappe.get_doc({
        "doctype": "Friday Listing",
        "seller": user_id,
        "token": token_id,
        "price_eur": Decimal(price_eur),
        "status": "open"  # nastav ako aktívny inzerát
    })
    doc.insert(ignore_permissions=True)

    # aktualizuj token
    frappe.db.set_value("Friday Token", token_id, "status", "listed")
    frappe.db.commit()

    return {"listing_id": doc.name, "price_eur": float(price_eur)}


# --------------------------------------------
# ❌ CANCEL LISTING
# --------------------------------------------
@frappe.whitelist()
def cancel_listing(listing_id: str):
    """Cancels an active listing."""
    if not frappe.db.exists("Friday Listing", listing_id):
        frappe.throw(_("Listing not found"))

    doc = frappe.get_doc("Friday Listing", listing_id)
    doc.status = "cancelled"
    doc.closed_at = frappe.utils.now()
    doc.save(ignore_permissions=True)

    # vráť token do stavu active
    frappe.db.set_value("Friday Token", doc.token, "status", "active")
    frappe.db.commit()

    return {"cancelled": listing_id}

# --------------------------------------------
# 💸 BUY LISTING
# --------------------------------------------
@frappe.whitelist()
def buy_listing(buyer_id: str, listing_id: str):
    """Kúpi token z otvoreného inzerátu (prevod vlastníctva + uzavretie listing-u)."""
    if not buyer_id or not listing_id:
        frappe.throw(_("Missing buyer_id or listing_id"))

    # Načítaj listing
    listing = frappe.get_doc("Friday Listing", listing_id)
    if not listing or listing.status != "open":
        frappe.throw(_("Listing not open or not found"))

    # Načítaj token
    token = frappe.get_doc("Friday Token", listing.token)
    if not token or token.status != "listed":
        frappe.throw(_("Token not available for purchase"))

    if token.minutes_remaining <= 0:
        frappe.throw(_("Token has no remaining minutes"))

    # Uzavri listing
    listing.status = "sold"
    listing.closed_at = frappe.utils.now()
    listing.save(ignore_permissions=True)

    # Prenes vlastníctvo tokenu
    token.owner_user = buyer_id
    token.status = "active"
    token.save(ignore_permissions=True)

    # Záznam transakcie
    frappe.get_doc({
        "doctype": "Transaction",
        "user": buyer_id,
        "type": "friday_trade_buy",
        "amount_eur": float(listing.price_eur or 0),
        "seconds_delta": 0,
        "note": f"Purchased token {token.name} from listing {listing.name}"
    }).insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "success": True,
        "message": "Listing purchased successfully",
        "listing_id": listing.name,
        "token_id": token.name,
        "price_eur": float(listing.price_eur or 0)
    }


# --------------------------------------------
# 📋 GET OPEN LISTINGS
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_open_listings():
    """Returns all open listings sorted by newest."""
    listings = frappe.get_all(
        "Friday Listing",
        filters={"status": "open"},
        fields=["name", "token", "seller", "price_eur", "created_at"],
        order_by="created_at desc"
    )
    return {"listings": listings}
