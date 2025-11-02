import frappe
import requests

# Clerk API key – vlož do site_config.json:
# {
#   "clerk_api_key": "sk_test_..."
# }

CLERK_API_KEY = frappe.conf.get("clerk_api_key")


def verify_bearer_and_get_user_id():
    """
    Overí Clerk JWT token z hlavičky 'Authorization: Bearer <token>'
    a vráti user_id (sub) používateľa.
    """
    auth_header = frappe.request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        frappe.throw("Unauthorized: Missing Bearer token", frappe.PermissionError)

    token = auth_header.split(" ")[1]

    try:
        res = requests.post(
            "https://api.clerk.dev/v1/tokens/verify",
            headers={
                "Authorization": f"Bearer {CLERK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"token": token}
        )
    except Exception as e:
        frappe.log_error(f"Clerk verify request failed: {str(e)}", "Clerk Auth Error")
        frappe.throw("Authentication server unreachable", frappe.PermissionError)

    if res.status_code != 200:
        frappe.log_error(f"Clerk verify failed: {res.text}", "Clerk Auth Error")
        frappe.throw("Invalid or expired Clerk token", frappe.PermissionError)

    data = res.json()

    # Clerk odpoveď obsahuje kľúč "sub" – unikátne ID používateľa
    user_id = data.get("sub")
    if not user_id:
        frappe.throw("Invalid token: missing user_id", frappe.PermissionError)

    return user_id
