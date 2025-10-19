import json, time, requests, jwt
import frappe
from jwt.algorithms import RSAAlgorithm

_JWKS_CACHE = {"keys": None, "ts": 0}

def _get_jwks():
    jwks_url = frappe.conf.get("CLERK_JWKS_URL")
    if not jwks_url:
        raise frappe.PermissionError("Missing CLERK_JWKS_URL")
    now = time.time()
    if _JWKS_CACHE["keys"] and now - _JWKS_CACHE["ts"] < 3600:
        return _JWKS_CACHE["keys"]
    resp = requests.get(jwks_url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    _JWKS_CACHE["keys"] = data["keys"]
    _JWKS_CACHE["ts"] = now
    return _JWKS_CACHE["keys"]

def verify_bearer_and_get_user_id():
    auth = frappe.get_request_header("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise frappe.PermissionError("Missing Bearer token")
    token = auth.split(" ", 1)[1].strip()
    issuer = frappe.conf.get("CLERK_ISSUER")
    keys = _get_jwks()
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = next((k for k in keys if k["kid"] == kid), None)
    if not key:
        raise frappe.PermissionError("Invalid JWKS kid")
    public_key = RSAAlgorithm.from_jwk(json.dumps(key))
    payload = jwt.decode(token, public_key, algorithms=["RS256"], audience=None, options={"verify_aud": False}, issuer=issuer)
    # Clerk subject => náš Friday User (pole clerk_id)
    clerk_sub = payload.get("sub")
    if not clerk_sub:
        raise frappe.PermissionError("No sub in token")
    # nájdeme Friday User podľa clerk_id
    user_name = frappe.db.get_value("Friday User", {"clerk_id": clerk_sub}, "name")
    if not user_name:
        # fallback: ak neexistuje, môžeme vytvoriť „light“ profil podľa emailu z payloadu
        email = payload.get("email")
        doc = frappe.get_doc({
            "doctype": "Friday User",
            "email": email or f"{clerk_sub}@example.invalid",
            "clerk_id": clerk_sub,
            "status": "active"
        })
        doc.insert(ignore_permissions=True)
        user_name = doc.name
        frappe.db.commit()
    return user_name
