import frappe
from frappe import _
from frappe.utils import now_datetime, flt
from datetime import datetime, timedelta
from decimal import Decimal
import pytz


# --------------------------------------------
# 🔹 KONŠTANTY (možno upraviť vo Friday Settings)
# --------------------------------------------
FRIDAY_BASE_YEAR = 2025
FRIDAY_BASE_PRICE_EUR = 450
MAX_PRIMARY_TOKENS_PER_USER = 20


# --------------------------------------------
# 📈 POMOCNÉ FUNKCIE
# --------------------------------------------
def price_for_year(year: int) -> float:
    """Vypočíta cenu pre daný rok – rast o 10% ročne"""
    diff = year - FRIDAY_BASE_YEAR
    price = FRIDAY_BASE_PRICE_EUR * (1.1 ** diff)
    return round(price, 2)


def is_friday_in_bratislava(now=None) -> bool:
    """Zistí, či je aktuálne piatok v časovom pásme Bratislavy"""
    if not now:
        now = datetime.utcnow()
    tz = pytz.timezone("Europe/Bratislava")
    local = now.astimezone(tz)
    return local.weekday() == 4  # 0=Mon ... 4=Fri


def count_fridays_in_year(year: int) -> int:
    """Spočíta počet piatkov v danom roku"""
    tz = pytz.timezone("Europe/Bratislava")
    d = datetime(year, 1, 1, tzinfo=pytz.utc)
    count = 0
    while d.year == year:
        if d.astimezone(tz).weekday() == 4:
            count += 1
        d += timedelta(days=1)
    return count


# --------------------------------------------
# 🪙 CREATE TOKEN
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def create_token(user_id: str, issued_year: int):
    """Vytvorí nový Friday Token pre používateľa"""
    if not user_id:
        frappe.throw(_("Missing user_id"))
    if not issued_year:
        frappe.throw(_("Missing issued_year"))

    # 🔹 Získame 'name' z Friday User
    user_name = frappe.db.get_value("Friday User", {"user_id": user_id}, "name")
    if not user_name:
        frappe.throw(_("User not found"))

    # 🔹 Overíme počet aktívnych tokenov (či neprekračuje limit)
    active_count = frappe.db.count("Friday Token", {"owner_user": user_id, "status": "active"})
    if active_count >= MAX_PRIMARY_TOKENS_PER_USER:
        frappe.throw(_("Max token limit reached"))

    # 🔹 Získame cenu
    settings_price = frappe.db.get_value("Friday Settings", "1", "current_price_eur")
    price = float(settings_price or price_for_year(int(issued_year)))

    # 🔹 Vytvor token
    token = frappe.get_doc({
        "doctype": "Friday Token",
        "issued_year": int(issued_year),
        "minutes_remaining": 60,
        "status": "active",
        "original_price_eur": price,
        "owner": user_name,        # Link na Friday User
        "owner_user": user_id      # String ID pre API volania
    })
    token.insert(ignore_permissions=True)
    frappe.db.commit()

    # 🔹 Zapíš transakciu
    frappe.get_doc({
        "doctype": "Transaction",
        "user": user_name,
        "type": "friday_purchase",
        "amount_eur": price,
        "seconds_delta": 60 * 60,
        "note": f"Purchased Friday token for year {issued_year}"
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "message": "Token created",
        "token_id": token.name,
        "price_eur": price
    }


# --------------------------------------------
# 🧾 GET TOKENS
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_tokens(user_id: str):
    """Získa všetky tokeny používateľa"""
    if not user_id:
        frappe.throw(_("Missing user_id"))

    tokens = frappe.get_all(
        "Friday Token",
        filters={"owner_user": user_id},
        fields=[
            "name",
            "issued_year",
            "status",
            "minutes_remaining",
            "original_price_eur",
            "creation"
        ],
        order_by="creation desc"
    )
    return {"tokens": tokens}


# --------------------------------------------
# ⏳ SPEND MINUTES
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def spend_minutes(user_id: str, minutes: int):
    """Odpočíta minúty z aktívneho tokenu používateľa"""
    if not user_id or not minutes:
        frappe.throw(_("Missing user_id or minutes"))

    token = frappe.get_all(
        "Friday Token",
        filters={"owner_user": user_id, "status": "active"},
        fields=["name", "minutes_remaining"],
        order_by="creation asc",
        limit=1
    )

    if not token:
        frappe.throw(_("No active tokens available"))

    token = token[0]
    remaining = int(token.minutes_remaining) - int(minutes)
    new_status = "spent" if remaining <= 0 else "active"
    remaining = max(0, remaining)

    frappe.db.set_value("Friday Token", token.name, {
        "minutes_remaining": remaining,
        "status": new_status
    })
    frappe.db.commit()

    frappe.get_doc({
        "doctype": "Transaction",
        "user": user_id,
        "type": "friday_trade_sell",
        "amount_eur": 0,
        "seconds_delta": -minutes * 60,
        "note": f"Spent {minutes} minutes"
    }).insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "message": "Minutes spent",
        "token": token.name,
        "remaining": remaining
    }


# --------------------------------------------
# 💰 GET PRICE FOR YEAR
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def get_price_for_year(year: int):
    """Vráti aktuálnu cenu tokenu pre daný rok"""
    return {"year": year, "price_eur": price_for_year(int(year))}


# --------------------------------------------
# 📊 SUPPLY OVERVIEW
# --------------------------------------------
@frappe.whitelist(allow_guest=True)
def supply():
    """Return total minted, active, listed, and spent tokens + current price."""
    total = frappe.db.count("Friday Token")
    active = frappe.db.count("Friday Token", {"status": "active"})
    listed = frappe.db.count("Friday Token", {"status": "listed"})
    spent = frappe.db.count("Friday Token", {"status": "spent"})

    price = frappe.db.get_value("Friday Settings", "1", "current_price_eur")

    return {
        "total": total,
        "active": active,
        "listed": listed,
        "spent": spent,
        "current_price_eur": float(price or 0)
    }
