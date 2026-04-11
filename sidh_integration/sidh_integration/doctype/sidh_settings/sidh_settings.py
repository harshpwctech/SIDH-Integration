# Copyright (c) 2026, Mytra and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SIDHSettings(Document):
	def validate(self):
		return
