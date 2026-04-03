import frappe
import razorpay


def get_context(context):
    course_id = frappe.form_dict.get("course")

    if not course_id:
        frappe.local.flags.redirect_location = "/"
        raise frappe.Redirect

    email = frappe.session.user
    if email == "Guest":
        frappe.local.flags.redirect_location = (
            f"/login?redirect-to=/sidh_payment?course={course_id}"
        )
        raise frappe.Redirect

    actual_course_id = frappe.db.get_value("LMS Course", {"name": course_id}, "name")
    if not actual_course_id:
        actual_course_id = frappe.db.get_value("LMS Course", {"name": course_id.lower()}, "name")
    if not actual_course_id:
        frappe.local.flags.redirect_location = "/"
        raise frappe.Redirect

    course_id = actual_course_id
    course    = frappe.get_doc("LMS Course", course_id)

    context.course    = course
    context.course_id = course_id
    context.email     = email
    context.full_name = frappe.db.get_value("User", email, "full_name")
    context.currency  = course.currency or "INR"
    context.amount    = course.course_price or 0

    if not course.paid_course:
        frappe.local.flags.redirect_location = f"/lms/courses/{course_id}"
        raise frappe.Redirect

    if frappe.db.exists("LMS Enrollment", {"course": course_id, "member": email}):
        frappe.local.flags.redirect_location = f"/lms/courses/{course_id}"
        raise frappe.Redirect

    settings   = frappe.get_single("Razorpay Settings")
    key_id     = settings.api_key
    key_secret = settings.get_password("api_secret", raise_exception=False)

    amount_paise = int(float(course.course_price or 0) * 100)

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        order  = client.order.create({
            "amount"  : amount_paise,
            "currency": course.currency or "INR",
            "notes"   : {"course_id": course_id, "email": email}
        })
        context.razorpay_key = key_id
        context.order_id     = order["id"]
        context.amount_paise = amount_paise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Razorpay Order Creation Failed")
        frappe.throw("Payment initialization failed. Please try again.")


@frappe.whitelist()
def verify_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, course_id):
    settings   = frappe.get_single("Razorpay Settings")
    key_id     = settings.api_key
    key_secret = settings.get_password("api_secret", raise_exception=False)

    client = razorpay.Client(auth=(key_id, key_secret))

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id"   : razorpay_order_id,
            "razorpay_payment_id" : razorpay_payment_id,
            "razorpay_signature"  : razorpay_signature
        })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Razorpay Signature Verification Failed")
        return {"status": "failed"}

    email = frappe.session.user
    enroll_user_after_payment(email, course_id, razorpay_payment_id)
    return {"status": "ok"}


def get_or_create_address(email, full_name):
    existing = frappe.db.get_value("Address", {"email_id": email}, "name")
    if existing:
        return existing
    addr = frappe.get_doc({
        "doctype"       : "Address",
        "address_title" : full_name or email,
        "address_type"  : "Billing",
        "address_line1" : "-",
        "city"          : "-",
        "country"       : "India",
        "email_id"      : email,
    })
    addr.flags.ignore_mandatory   = True
    addr.flags.ignore_permissions = True
    addr.flags.ignore_validate    = True
    addr.insert()
    frappe.db.commit()
    return addr.name


def enroll_user_after_payment(email, course_id, payment_id):
    if frappe.db.exists("LMS Enrollment", {"course": course_id, "member": email}):
        return
    try:
        course_doc = frappe.get_doc("LMS Course", course_id)
        full_name  = frappe.db.get_value("User", email, "full_name")

        if not frappe.db.exists("LMS Payment", {
            "payment_for_document_type": "LMS Course",
            "payment_for_document"     : course_id,
            "member"                   : email,
            "payment_received"         : True
        }):
            address     = get_or_create_address(email, full_name)
            lms_payment = frappe.get_doc({
                "doctype"                  : "LMS Payment",
                "payment_for_document_type": "LMS Course",
                "payment_for_document"     : course_id,
                "member"                   : email,
                "payment_received"         : True,
                "payment_id"               : payment_id,
                "billing_name"             : full_name or email,
                "source"                   : "Razorpay",
                "amount"                   : course_doc.course_price or 0,
                "currency"                 : course_doc.currency or "INR",
                "address"                  : address
            })
            lms_payment.flags.ignore_permissions = True
            lms_payment.insert()
            frappe.db.commit()

        enrollment = frappe.get_doc({
            "doctype"            : "LMS Enrollment",
            "course"             : course_id,
            "member"             : email,
            "member_type"        : "Student",
            "is_sidh_enrollment" : 0
        })
        enrollment.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "SIDH Payment Enrollment Failed")
        frappe.throw("Enrollment after payment failed")