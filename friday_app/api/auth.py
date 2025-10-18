import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def sso(token: str):
    """Presmeruje používateľa na frontend (Vercel appku) s Clerk tokenom."""
    if not token:
        frappe.throw(_("Missing token"))

    # 🔹 URL tvojho frontendu na Verceli
    frontend_url = frappe.conf.get("FRONTEND_URL", "https://frontendtokeny.vercel.app")

    # 🔹 Presmeruj na /login?token=<JWT>
    redirect_url = f"{frontend_url}/login?token={token}"

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = redirect_url
