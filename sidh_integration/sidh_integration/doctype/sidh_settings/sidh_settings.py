# Copyright (c) 2026, Mytra and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.data import get_url
from frappe.model.document import Document


class SIDHSettings(Document):
	def validate(self):
		if not self.sso_url:
			self.sso_url = get_url("/api/method/sidh_integration.sidh_sso.handle_sidh_sso")
		if self.base_url and self.base_url[-1] != "/":
			self.base_url = self.base_url + "/"
