import frappe
from frappe import _
from frappe.utils import flt


# --------------------------------------------
# 🧩 Helper: Admin kontrola
# --------------------------------------------
def _check_admin():
    """Helper na kontrolu, či request robí administrátor."""
    if frappe.session.user != "Administrator":
        frappe.throw(_("Not permitted"), frappe.PermissionError)


# --------------------------------------------
# 📜 GET USER TRANSACTIONS
# --------------------------------------------
@frappe.whitelist(allow_guest=False)
def get_user_transactions(user_id: str):
    """Vráti všetky transakcie používateľa, zoradené od najnovšej po najstaršiu."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    transactions = frappe.get_all(
        "Transaction",
        filters={"user": user_id},
        fields=["name", "type", "amount_eur", "seconds_delta", "note", "creation"],
        order_by="creation desc"
    )

    for t in transactions:
        t["minutes_delta"] = round(flt(t["seconds_delta"]) / 60, 2)

    return {"transactions": transactions}


# --------------------------------------------
# 💰 GET USER BALANCE
# --------------------------------------------
@frappe.whitelist(allow_guest=False)
def get_user_balance(user_id: str):
    """Spočíta celkové kúpené a spotrebované minúty používateľa."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    data = frappe.db.sql("""
        SELECT 
            SUM(CASE WHEN type IN ('friday_trade_buy', 'friday_purchase') THEN seconds_delta ELSE 0 END) AS bought_seconds,
            SUM(CASE WHEN type = 'friday_trade_sell' THEN seconds_delta ELSE 0 END) AS spent_seconds
        FROM `tabTransaction`
        WHERE user = %s
    """, user_id, as_dict=True)[0]

    bought = flt(data.bought_seconds or 0) / 60
    spent = abs(flt(data.spent_seconds or 0)) / 60
    remaining = max(0, bought - spent)

    return {
        "bought_minutes": round(bought, 2),
        "spent_minutes": round(spent, 2),
        "remaining_minutes": round(remaining, 2)
    }


# --------------------------------------------
# 🕒 GET RECENT ACTIVITY SUMMARY
# --------------------------------------------
@frappe.whitelist(allow_guest=False)
def get_recent_activity(user_id: str, limit: int = 5):
    """Vráti posledné transakcie (napr. na dashboard)."""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    transactions = frappe.get_all(
        "Transaction",
        filters={"user": user_id},
        fields=["type", "amount_eur", "seconds_delta", "note", "creation"],
        order_by="creation desc",
        limit=limit
    )

    for t in transactions:
        t["minutes_delta"] = round(flt(t["seconds_delta"]) / 60, 2)

    return {"recent": transactions}


# --------------------------------------------
# 🧹 CLEAR USER TRANSACTIONS (Admin only)
# --------------------------------------------
@frappe.whitelist()
def clear_user_transactions(user_id: str):
    """Vymaže všetky transakcie používateľa – len pre administrátora."""
    _check_admin()

    frappe.db.delete("Transaction", {"user": user_id})
    frappe.db.commit()
    return {"success": True, "message": f"All transactions cleared for {user_id}"}
