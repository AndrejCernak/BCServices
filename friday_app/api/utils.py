import frappe
from datetime import datetime

# -----------------------------
# 🧰 Helpery pre logovanie
# -----------------------------

def log_info(message: str):
    """Zaloguje správu do Frappe loggera aj do konzoly."""
    frappe.logger().info(f"[FridayApp] {message}")
    print(f"[FridayApp] {message}")


def log_error(message: str, title="Friday Error"):
    """Zaloguje chybu do Frappe error logov."""
    frappe.log_error(title=title, message=message)
    print(f"[FridayApp:ERROR] {message}")


# -----------------------------
# 🕒 Čas a formátovanie
# -----------------------------

def now_iso():
    """Vráti aktuálny čas v ISO formáte (UTC)."""
    return datetime.utcnow().isoformat()


# -----------------------------
# ✅ Odpovede pre API
# -----------------------------

def success_response(data=None, message="OK"):
    """Jednotný formát úspešnej odpovede."""
    return {
        "success": True,
        "message": message,
        "data": data or {}
    }


def error_response(error_message="Unexpected error", status_code=400):
    """Jednotný formát chybovej odpovede."""
    frappe.local.response["http_status_code"] = status_code
    return {
        "success": False,
        "error": error_message
    }


# -----------------------------
# 🔍 Overenie dát
# -----------------------------

def require_fields(data: dict, required: list):
    """
    Overí, či všetky požadované polia existujú v `data`.
    Ak nie, vyhodí frappe.throw().
    """
    missing = [f for f in required if f not in data or data[f] in [None, ""]]
    if missing:
        frappe.throw(f"Missing required fields: {', '.join(missing)}")
