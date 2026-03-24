import frappe
import base64
import json
import time
from Crypto.Cipher import AES

def unpad(byte_array):
    last_byte = byte_array[-1]
    return byte_array[0:-last_byte]

@frappe.whitelist(allow_guest=True)
def handle_sidh_sso():

    settings   = frappe.get_single("SIDH Settings")
    CRYPTO_KEY = settings.get_password(fieldname="crypto_key", raise_exception=False)
    CRYPTO_IV  = settings.get_password(fieldname="crypto_iv", raise_exception=False)

    token = frappe.request.args.get("token")
    if not token:
        frappe.throw("No token provided")

    try:
        byte_array = base64.b64decode(token)
        key        = base64.b64decode(CRYPTO_KEY)
        iv         = base64.b64decode(CRYPTO_IV)
        cipher     = AES.new(key, AES.MODE_CBC, iv)
        decrypted  = unpad(
            cipher.decrypt(byte_array)
        ).decode("UTF-8")
        data = json.loads(decrypted)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SIDH SSO Decryption Failed")
        frappe.throw("Decryption failed")

    current_time = int(time.time() * 1000)
    token_time   = data.get("time_stamp")
    if current_time - token_time > 30000:
        frappe.throw("Token expired")

    candidate_name = data.get("candidate_name")
    last_name      = data.get("last_name")
    candidate_id   = data.get("candidate_id")
    course_id      = data.get("course_id")
    email = (
        data.get("candidate_email")
        or candidate_id + "@sidh.in"
    )

    if not frappe.db.exists("User", email):
        try:
            user = frappe.get_doc({
                "doctype"    : "User",
                "email"      : email,
                "first_name" : candidate_name,
                "last_name"  : last_name,
                "enabled"    : 1,
                "user_type"  : "Website User"
            })
            user.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "SIDH SSO User Creation Failed")
            frappe.throw("User creation failed")

    frappe.local.login_manager.login_as(email)

    if not frappe.db.exists("LMS Enrollment", {
        "course" : course_id,
        "member" : email
    }):
        try:
            enrollment = frappe.get_doc({
                "doctype"     : "LMS Enrollment",
                "course"      : course_id,
                "member"      : email,
                "member_type" : "Student"
            })
            enrollment.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "SIDH SSO Enrollment Failed")
            frappe.throw("Enrollment failed")

    frappe.local.response["type"]     = "redirect"
    frappe.local.response["location"] = (
        "/lms/courses/" + course_id
    )