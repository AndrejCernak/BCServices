import frappe
from frappe import _

# -------------------------------------------------------------
# 🧑‍💼 ADMIN API ENDPOINTS
# -------------------------------------------------------------

def _check_admin():
    """Helper na kontrolu, či request robí administrátor alebo oprávnený Clerk admin."""
    allowed_admins = ["Administrator", "user_30p94nuw9O2UHOEsXmDhV2SgP8N"]  # 👈 tvoj Clerk admin ID
    if frappe.session.user not in allowed_admins:
        frappe.throw(_("Not permitted"), frappe.PermissionError)


# -------------------------------------------------------------
# 🔹 ZOZNAM VŠETKÝCH POUŽÍVATEĽOV
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_all_users():
    _check_admin()

    users = frappe.get_all(
        "Friday User",
        fields=["name as id", "user_id as username", "role", "creation"]
    )

    clients = []
    for u in users:
        clients.append({
            "id": u.id,
            "username": u.username,
            "devices": [],  # môžeš neskôr doplniť reálne zariadenia
            "tokens": []    # zatiaľ prázdne, aby JSON matchol Swift model
        })

    return {
        "success": True,
        "clients": clients
    }



# -------------------------------------------------------------
# 🔹 RESET TOKENOV POUŽÍVATEĽA
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def reset_user_tokens(user_id: str):
    _check_admin()
    if not user_id:
        frappe.throw(_("Missing user_id"))
    deleted = frappe.db.delete("Friday Token", {"owner_user": user_id})
    frappe.db.commit()
    return {"success": True, "message": f"Deleted {deleted} tokens for user {user_id}"}


# -------------------------------------------------------------
# 🔹 PLATBY
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_payments():
    _check_admin()
    payments = frappe.get_all(
        "Payment",
        fields=["name", "buyer", "amount_eur", "status", "created_at"],
        order_by="created_at desc"
    )
    return {"success": True, "payments": payments}


# -------------------------------------------------------------
# 🔹 TRANSAKCIE
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_transactions():
    _check_admin()
    transactions = frappe.get_all(
        "Transaction",
        fields=["name", "user", "type", "amount_eur", "seconds_delta", "created_at"],
        order_by="created_at desc"
    )
    return {"success": True, "transactions": transactions}


# -------------------------------------------------------------
# 🔹 MINT TOKENOV
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def mint_tokens(year: int, quantity: int, price_eur: float):
    _check_admin()
    for _ in range(quantity):
        frappe.get_doc({
            "doctype": "Friday Token",
            "issued_year": year,
            "original_price_eur": price_eur
        }).insert(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "message": f"Minted {quantity} tokens for year {year}"}


# -------------------------------------------------------------
# 🔹 AKTUALIZOVAŤ AKTUÁLNU CENU
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def set_current_price(price_eur: float):
    _check_admin()
    settings = frappe.get_doc("Friday Settings", "Friday Settings")
    settings.current_price_eur = price_eur
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "message": f"Price updated to {price_eur} €"}


# -------------------------------------------------------------
# 🔹 DEBUG LOG
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def debug_log(message: str, user_id: str = None):
    frappe.logger("friday_debug").info(f"[{user_id}] {message}")
    return {"logged": True}
