import frappe
from frappe.utils import now, now_datetime
from .auth import verify_bearer_and_get_user_id
from .apns_push import send_incoming_call_push

# ---------- Supply & Balance ----------
@frappe.whitelist()
def admin_clients():
    """Vráti zoznam všetkých klientov pre admina"""
    users = frappe.get_all(
        "Friday User",
        fields=["name", "username", "email", "first_name", "last_name", "status"]
    )

    result = []
    for u in users:
        devices = frappe.get_all(
            "Device",
            filters={"user": u["name"]},
            fields=["voip_token", "updated_at"]
        )
        tokens = frappe.get_all(
            "Friday Token",
            filters={"owner_user": u["name"]},
            fields=["minutes_remaining", "status"]
        )

        result.append({
            "id": u["name"],
            "username": u.get("username") or u.get("email"),
            "devices": devices,
            "tokens": tokens
        })

    return result

@frappe.whitelist(allow_guest=False)
def supply(year: int):
    """Cena + dostupnosť treasury (jednoducho: vráti current_price a dummy supply).
    Ak chceš presný supply, môžeš držať tabuľku „treasury pool“, ale teraz vezmeme len cenu."""
    verify_bearer_and_get_user_id()
    price = frappe.db.get_single_value("Friday Settings", "current_price_eur") or 0.0  # :contentReference[oaicite:22]{index=22}
    # dostupnosť: počet ne-listnutých a ne-spent tokenov pre daný rok (ak mintuješ vopred do treasury)
    available = frappe.db.count("Friday Token", {"issued_year": int(year), "status": ["in", ["active","listed"]]})  # :contentReference[oaicite:23]{index=23}
    return {"year": int(year), "price_eur": float(price), "available": int(available)}

@frappe.whitelist(allow_guest=False)
def balance():
    user = verify_bearer_and_get_user_id()
    # sumár minút a zoznam tokenov
    tokens = frappe.get_all("Friday Token", filters={"owner_user": user, "status": ["!=", "spent"]},
                            fields=["name","issued_year","minutes_remaining","status","original_price_eur","updated_at"])
    total_minutes = sum([t["minutes_remaining"] for t in tokens]) if tokens else 0
    return {"user": user, "total_minutes": int(total_minutes), "tokens": tokens}  # :contentReference[oaicite:24]{index=24}

# ---------- Listings (burza) ----------

@frappe.whitelist(allow_guest=False, methods=["POST"])
def list_token(token: str, price_eur: float):
    user = verify_bearer_and_get_user_id()
    tok = frappe.get_doc("Friday Token", token)  # owner_user, status :contentReference[oaicite:25]{index=25}
    if tok.owner_user != user:
        frappe.throw("Not your token")
    if tok.status == "listed":
        frappe.throw("Already listed")
    if tok.minutes_remaining <= 0:
        frappe.throw("Token has no minutes")
    # create listing
    lst = frappe.get_doc({
        "doctype":"Friday Listing",
        "token": token,
        "seller": user,
        "price_eur": float(price_eur),
        "status": "open",
        "created_at": now()
    }).insert(ignore_permissions=True)
    # mark token listed
    tok.status = "listed"
    tok.updated_at = now()
    tok.save(ignore_permissions=True)
    frappe.db.commit()
    return {"listing": lst.name}  # :contentReference[oaicite:26]{index=26}

@frappe.whitelist(allow_guest=False, methods=["POST"])
def cancel_listing(listing: str):
    user = verify_bearer_and_get_user_id()
    lst = frappe.get_doc("Friday Listing", listing)  # seller, status :contentReference[oaicite:27]{index=27}
    if lst.seller != user:
        frappe.throw("Not your listing")
    if lst.status != "open":
        frappe.throw("Cannot cancel")
    lst.status = "cancelled"
    lst.closed_at = now()
    lst.save(ignore_permissions=True)
    # unlist token
    tok = frappe.get_doc("Friday Token", lst.token)  # :contentReference[oaicite:28]{index=28}
    tok.status = "active"
    tok.updated_at = now()
    tok.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}

@frappe.whitelist(allow_guest=True)
def listings():
    rows = frappe.get_all("Friday Listing", filters={"status":"open"}, fields=["name","token","seller","price_eur","created_at"])  # :contentReference[oaicite:29]{index=29}
    return {"listings": rows}

# ---------- Calls (VoIP) ----------

@frappe.whitelist(allow_guest=False, methods=["POST"])
def register_device(voip_token: str=None, apns_token: str=None):
    user = verify_bearer_and_get_user_id()
    existing = frappe.db.get_value("Device", {"user": user}, "name")  # :contentReference[oaicite:30]{index=30}
    payload = {"user": user, "updated_at": now()}
    if voip_token: payload["voip_token"] = voip_token
    if apns_token: payload["apns_token"] = apns_token
    if existing:
        doc = frappe.get_doc("Device", existing)
        for k,v in payload.items(): setattr(doc, k, v)
        doc.save(ignore_permissions=True)
    else:
        payload["created_at"] = now()
        frappe.get_doc({"doctype":"Device", **payload}).insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}

@frappe.whitelist(allow_guest=False, methods=["POST"])
def call_user(advisor: str, caller_name: str="Caller"):
    user = verify_bearer_and_get_user_id()
    # nájdeme device poradcu
    dev = frappe.db.get_value("Device", {"user": advisor}, ["name","voip_token"], as_dict=True)  # :contentReference[oaicite:31]{index=31}
    if not dev or not dev.voip_token:
        frappe.throw("Advisor not reachable")
    # pošleme VoIP push
    send_incoming_call_push(dev.voip_token, caller_id=user, caller_name=caller_name)
    # založíme Call Log (started)
    cl = frappe.get_doc({"doctype":"Call Log","caller": user,"advisor": advisor,"started_at": now()}).insert(ignore_permissions=True)  # :contentReference[oaicite:32]{index=32}
    frappe.db.commit()
    return {"call_id": cl.name}

@frappe.whitelist(allow_guest=False, methods=["POST"])
def end_call(call_id: str):
    user = verify_bearer_and_get_user_id()
    cl = frappe.get_doc("Call Log", call_id)  # caller, advisor, started_at, ended_at, duration :contentReference[oaicite:33]{index=33}
    cl.ended_at = now()
    # vypočítame trvanie v sekundách
    started = frappe.utils.get_datetime(cl.started_at)
    ended = frappe.utils.get_datetime(cl.ended_at)
    dur = int((ended - started).total_seconds())
    cl.duration = dur
    cl.save(ignore_permissions=True)
    # TODO: znížiť minutes_remaining na jednom z tokenov usera (ak máš takú business logiku)
    frappe.db.commit()
    return {"duration": dur}

@frappe.whitelist(allow_guest=False)
def calls_history():
    user = verify_bearer_and_get_user_id()
    rows = frappe.get_all("Call Log", filters={"caller": user}, fields=["name","advisor","started_at","ended_at","duration","used_token"], order_by="started_at desc")  # :contentReference[oaicite:34]{index=34}
    return {"calls": rows}

# ---------- Admin ----------

@frappe.whitelist(allow_guest=False, methods=["POST"])
def admin_mint(quantity: int, year: int, price_eur: float=None):
    """Admin: vygeneruje 'treasury' tokeny (bez ownera) – ak ich chceš mintovať dopredu."""
    _ = verify_bearer_and_get_user_id()
    for _i in range(int(quantity)):
        frappe.get_doc({
            "doctype":"Friday Token",
            "issued_year": int(year),
            "minutes_remaining": 60,
            "status":"active",
            "original_price_eur": float(price_eur) if price_eur is not None else None,
            "created_at": now(),
            "updated_at": now()
        }).insert(ignore_permissions=True)  # :contentReference[oaicite:35]{index=35}
    frappe.db.commit()
    return {"ok": True}

@frappe.whitelist(allow_guest=False, methods=["POST"])
def admin_set_price(price_eur: float):
    _ = verify_bearer_and_get_user_id()
    fs = frappe.get_all("Friday Settings", fields=["name"])
    if fs:
        frappe.db.set_value("Friday Settings", fs[0].name, {"current_price_eur": float(price_eur), "updated_at": now()})
    else:
        frappe.get_doc({"doctype":"Friday Settings","current_price_eur": float(price_eur),"created_at": now(),"updated_at": now()}).insert(ignore_permissions=True)  # :contentReference[oaicite:36]{index=36}
    frappe.db.commit()
    return {"ok": True}
