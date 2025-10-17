import frappe
import requests

@frappe.whitelist()
def create_clerk_user(email: str, first_name: str = None, last_name: str = None, username: str = None, password: str = None):
    """Vytvorí nového používateľa v Clerk s heslom a public metadata."""

    api_key = frappe.conf.get("CLERK_API_KEY")
    if not api_key:
        frappe.throw("Missing CLERK_API_KEY in site_config.json")

    if not password:
        frappe.throw("Password is required for Clerk user creation.")

    url = "https://api.clerk.com/v1/users"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "email_address": [email],
        "first_name": first_name or "",
        "last_name": last_name or "",
        "username": username or "",
        "password": password,
        "public_metadata": {
            "role": "client"   # 👈 automaticky pridáme public metadata
        }
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code not in [200, 201]:
        frappe.log_error(response.text, "Clerk API Error")
        frappe.throw(f"Failed to create Clerk user: {response.text}")

    return response.json()
