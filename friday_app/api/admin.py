import frappe
import jwt
import requests
from frappe import _

# Clerk public key endpoint (tvoj Clerk projekt)
CLERK_JWKS_URL = "https://notable-sawfly-17.clerk.accounts.dev/.well-known/jwks.json"

# Clerk admin user ID (z iOS appky)
CLERK_ADMIN_ID = "user_30p94nuw9O2UHOEsXmDhV2SgP8N"

# 🧩 Nastavenie loggera podľa Frappe dokumentácie
logger = frappe.logger("friday_debug", allow_site=True, file_count=50)


# -------------------------------------------------------------
# 🔐 Overenie admin prístupu
# -------------------------------------------------------------
def _check_admin():
    """Overí, či request prichádza od admina – buď cez Clerk JWT alebo cez Frappe Administrator."""
    auth_header = frappe.get_request_header("Authorization")

    # 🔹 Pokus o overenie Clerk JWT tokenu
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

        try:
            # ✅ Over Clerk JWT cez JWKS public key
            jwks = requests.get(CLERK_JWKS_URL).json()
            header = jwt.get_unverified_header(token)
            key = next((k for k in jwks["keys"] if k["kid"] == header["kid"]), None)

            if not key:
                logger.warning("❌ Invalid Clerk key — no matching 'kid'")
                frappe.throw(_("Invalid Clerk key"), frappe.PermissionError)

            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            payload = jwt.decode(token, public_key, algorithms=["RS256"], audience=None)

            # 🧠 Logni payload pre kontrolu
            logger.debug(f"JWT payload received: {payload}")

            # 🔹 Over Clerk ID
            if payload.get("sub") == CLERK_ADMIN_ID:
                logger.info(f"✅ Admin access confirmed for Clerk ID: {payload.get('sub')}")
                return
            else:
                logger.warning(f"❌ Clerk ID mismatch: {payload.get('sub')} vs expected {CLERK_ADMIN_ID}")
                frappe.throw(_("You are not an admin (Clerk ID mismatch)"), frappe.PermissionError)

        except Exception as e:
            logger.error(f"JWT verification failed: {str(e)}")
            frappe.throw(_(f"JWT verification failed: {str(e)}"), frappe.PermissionError)

    # 🔹 Ak nie je Authorization header, fallback na Frappe login
    if frappe.session.user != "Administrator":
        logger.warning(f"❌ Permission denied — current user: {frappe.session.user}")
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

    frappe.response["success"] = True
    frappe.response["clients"] = clients
    logger.info(f"✅ list_all_users called — returned {len(clients)} clients")
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

    logger.info(f"🗑️ reset_user_tokens executed — deleted {deleted} tokens for user {user_id}")
    return {"success": True, "message": f"Deleted {deleted} tokens for user {user_id}"}


# -------------------------------------------------------------
# 🔹 ZOZNAM PLATIEB
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_payments():
    _check_admin()

    payments = frappe.get_all(
        "Payment",
        fields=["name", "buyer", "amount_eur", "status", "created_at"],
        order_by="created_at desc"
    )

    logger.info(f"💶 list_payments returned {len(payments)} records")
    return {"payments": payments}


# -------------------------------------------------------------
# 🔹 ZOZNAM TRANSAKCIÍ
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def list_transactions():
    _check_admin()

    transactions = frappe.get_all(
        "Transaction",
        fields=["name", "user", "type", "amount_eur", "seconds_delta", "created_at"],
        order_by="created_at desc"
    )

    logger.info(f"🔁 list_transactions returned {len(transactions)} transactions")
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
    logger.info(f"🪙 Minted {quantity} tokens for year {year} at {price_eur} € each")
    return {"message": f"Minted {quantity} tokens for year {year}"}


# -------------------------------------------------------------
# 🔹 NASTAV AKTUÁLNU CENU
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def set_current_price(price_eur: float):
    _check_admin()

    settings = frappe.get_doc("Friday Settings", "Friday Settings")
    settings.current_price_eur = price_eur
    settings.save(ignore_permissions=True)
    frappe.db.commit()

    logger.info(f"💰 set_current_price updated to {price_eur} €")
    return {"message": f"Price updated to {price_eur} €"}


# -------------------------------------------------------------
# 🔹 DEBUG LOG (pre RemoteLogger zo Swift appky)
# -------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
def debug_log(message: str, user_id: str = None):
    """Logy posielané z iOS appky cez RemoteLogger.log()"""
    logger.info(f"[{user_id}] {message}")
    return {"logged": True}
