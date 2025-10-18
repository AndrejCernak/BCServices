import frappe
import jwt
import requests
from frappe import _

# Clerk public key endpoint (nahrad podľa tvojho Clerk projectu)
CLERK_JWKS_URL = "https://notable-sawfly-17.clerk.accounts.dev/.well-known/jwks.json"

# Clerk admin user ID (z tvojej iOS appky)
CLERK_ADMIN_ID = "user_30p94nuw9O2UHOEsXmDhV2SgP8N"

def _check_admin():
    """Overí, či request prichádza od admina – buď cez Clerk JWT alebo cez Frappe Administrator."""
    auth_header = frappe.get_request_header("Authorization")

    # 🔹 1. Pokus o overenie Clerk JWT tokenu
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

        try:
            # ✅ Clerk overenie cez JWKS (public key)
            jwks = requests.get(CLERK_JWKS_URL).json()
            header = jwt.get_unverified_header(token)
            key = next(
                (k for k in jwks["keys"] if k["kid"] == header["kid"]),
                None
            )

            if not key:
                frappe.throw(_("Invalid Clerk key"), frappe.PermissionError)

            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            payload = jwt.decode(token, public_key, algorithms=["RS256"], audience=None)

            # 🧠 Skontroluj Clerk user ID
            if payload.get("sub") == CLERK_ADMIN_ID:
                # Admin potvrdený ✅
                return
            else:
                frappe.throw(_("You are not an admin (Clerk ID mismatch)"), frappe.PermissionError)

        except Exception as e:
            frappe.throw(_(f"JWT verification failed: {str(e)}"), frappe.PermissionError)

    # 🔹 2. Ak nie je Authorization header, fallback na Frappe login
    if frappe.session.user != "Administrator":
        frappe.throw(_("Not permitted"), frappe.PermissionError)


# -------------------------------------------------------------
# 🔹 ZOZNAM VŠETKÝCH POUŽÍVATEĽOV (pre iOS AdminView)
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_all_users():
    _check_admin()

    users = frappe.get_all(
        "Friday User",
        fields=["clerk_id", "username", "first_name", "last_name", "role", "status", "email", "creation"],
        order_by="creation desc"
    )

    clients = []
    for u in users:
        clients.append({
            "id": u.clerk_id or u.email,
            "username": u.username or f"{u.first_name} {u.last_name}".strip(),
            "devices": [],
            "tokens": []
        })

    # 🟢 TOTO je správny spôsob, ako poslať JSON priamo
    frappe.response["success"] = True
    frappe.response["clients"] = clients
    return



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
    return {"payments": payments}


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
    return {"transactions": transactions}


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
    return {"message": f"Minted {quantity} tokens for year {year}"}


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
    return {"message": f"Price updated to {price_eur} €"}


# -------------------------------------------------------------
# 🔹 DEBUG LOG (pre RemoteLogger zo Swift appky)
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def debug_log(message: str, user_id: str = None):
    frappe.logger("friday_debug").info(f"[{user_id}] {message}")
    return {"logged": True}
