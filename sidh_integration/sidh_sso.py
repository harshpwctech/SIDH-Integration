import frappe
import base64
import json
import time
from Crypto.Cipher import AES
from frappe import _
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from frappe.core.doctype.user.user import User

class SignupDisabledError(frappe.PermissionError): ...

@frappe.whitelist(allow_guest=True)
def handle_sidh_sso():
    token = frappe.request.args.get("token")
    if not token:
        frappe.respond_as_web_page(_("Invalid Request"), _("No token provided by SIDH"), http_status_code=417)
        return
    
    return validate_token_data(token)

def validate_token_data(token):
    settings = frappe.get_single("SIDH Settings")
    api_key = settings.get_password(fieldname="api_key", raise_exception=False)
    api_secret = settings.get_password(fieldname="api_secret",  raise_exception=False)
    data = decrypt_token(token, api_secret, api_key)
    if not data:
        return
    if not (validate_token_expiry(data) and validate_payload(data)):
        return
    user = get_email(data)
    if not user:
        frappe.respond_as_web_page(
			_("Invalid Request"), _("Please ensure that your profile has an email address")
            )
        return
    try:
        if update_sidh_user(user, data) is False:
            return
    except SignupDisabledError:
        return frappe.respond_as_web_page(
			"Signup is Disabled",
			"Sorry. Signup from Website is disabled.",
			success=False,
			http_status_code=403,
		)
    
    frappe.local.login_manager.login_as(user)
    frappe.db.commit()

    course_id = data.get("course_id")

    if not frappe.db.get_value("LMS Course", {"name": course_id}, "name"):
        return frappe.respond_as_web_page(
			"Course not found",
			f"Course '{course_id}' not found. Please contact Administrator",
			success=False,
			http_status_code=403,
		)

    already_enrolled = frappe.db.exists(
            "LMS Enrollment", {"course": course_id, "member": user}
        )
    
    if not already_enrolled:
        enroll_user_in_course(user, course_id)
    redirect_to = f"/lms/courses/{course_id}"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = redirect_to


def unpad(byte_array):
    last_byte = byte_array[-1]
    return byte_array[0:-last_byte]

def decrypt_token(token, crypto_key, crypto_iv):
    try:
        byte_array = base64.b64decode(token)
        key = base64.b64decode(crypto_key)
        iv = base64.b64decode(crypto_iv)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(byte_array)).decode("UTF-8")
        return json.loads(decrypted)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SIDH SSO Decryption Failed")
        frappe.respond_as_web_page(
            _("Error"),
            _("Token Decryption Failed. Please contact Administrator."),
            http_status_code=403
        )
        return

def validate_token_expiry(data):
    token_time = data.get("time_stamp")
    if not token_time:
        frappe.respond_as_web_page(
            _("Error"),
            _("Invalid token: missing timestamp"),
            http_status_code=403
        )
        return False
    if int(time.time() * 1000) - token_time > 30000:
        frappe.respond_as_web_page(
            _("Error"),
            _("Token expired"),
            http_status_code=403
        )
        return False
    
    return True
        

def validate_payload(data):
    for field in ["candidate_id", "candidate_name", "course_id"]:
        if not data.get(field):
            frappe.respond_as_web_page(
                _("Error"),
                _(f"Invalid token: missing field '{field}'"),
                http_status_code=403
            )
            return False
    
    return True

def get_email(data):
    return (data.get("candidate_email"))

def get_user_record(user: str, data: dict) -> "User":
    from frappe.website.utils import is_signup_disabled
    
    try:
        return frappe.get_doc("User", user)
    except frappe.DoesNotExistError:
        if is_signup_disabled():
            raise SignupDisabledError
    if gender := data.get("gender", "").title():
        frappe.get_doc({"doctype": "Gender", "gender": gender}).insert(
			ignore_permissions=True, ignore_if_duplicate=True
		)
    user: User = frappe.new_doc("User")
    user.update({
        "doctype": "User",
        "first_name": data.get("candidate_name", "").strip(),
        "last_name": data.get("last_name", "").strip(),
        "gender": gender,
        "email": (data.get("candidate_email")),
        "enabled": 1,
        "new_password": frappe.generate_hash(),
        "user_type": "Website User",
    })
    return user

def update_sidh_user(user: str, data: dict):
    user: User = get_user_record(user, data)
    update_user_record = user.is_new()

    if not user.enabled:
        frappe.respond_as_web_page(_("Not Allowed"), _("User {0} is disabled").format(user.email))
        return False

    if not user.get_social_login_userid("sidh"):
        update_user_record = True
        user.set_social_login_userid("sidh", userid=str(data.get("candidate_id")))

    if update_user_record:
        user.flags.ignore_permissions = True
        user.flags.no_welcome_mail = True
        
        if default_role := frappe.db.get_single_value("Portal Settings", "default_role"):
            user.add_roles(default_role)
        
        user.save()

def enroll_user_in_course(email, course_id):
    try:
        enrollment = frappe.get_doc({
            "doctype": "LMS Enrollment",
            "course": course_id,
            "member": email,
            "member_type": "Student",
            "is_sidh_enrollment": 1
        })
        enrollment.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SIDH SSO Enrollment Failed")
        frappe.throw("Enrollment failed")