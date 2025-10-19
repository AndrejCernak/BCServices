import frappe
from frappe.utils import now, now_datetime

def ensure_settings():
    # Ak neexistuje žiaden Friday Settings, vytvor default s cenou 0
    if not frappe.db.exists("Friday Settings"):
        doc = frappe.get_doc({
            "doctype": "Friday Settings",
            "current_price_eur": 0,
            "created_at": now(),
            "updated_at": now()
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
