import frappe
from frappe.model.document import Document
from friday_app.api import clerk_integration

class FridayUser(Document):
    def after_insert(self):
        """Po vytvorení Friday Usera sa automaticky vytvorí Clerk account."""
        try:
            clerk_user = clerk_integration.create_clerk_user(
                email=self.email,  # používame email namiesto user_id
                first_name=self.first_name,
                last_name=self.last_name,
                username=self.username,
                password=self.password
            )

            clerk_id = clerk_user.get("id")
            if clerk_id:
                self.db_set("clerk_id", clerk_id)
                frappe.logger().info(f"✅ Clerk user created: {clerk_id} for {self.email}")

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Clerk Sync Error")
            frappe.throw(f"Clerk sync failed: {e}")
