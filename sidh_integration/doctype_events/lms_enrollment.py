import frappe
from frappe.integrations.utils import make_post_request, create_request_log


def on_change(doc, method=None):
    if doc.is_sidh_enrollment:
        update_sidh_progress(doc)

def update_sidh_progress(doc):
    sidh_settings = frappe.get_single("SIDH Settings")
    update_progress_url = sidh_settings.base_url + "api/webhook-public/update/user-course-data"
    headers = {
        "Content-Type": "application/json",
        "client-id": sidh_settings.get_password("api_key", raise_exception=False),
        "client-secret": sidh_settings.get_password("api_secret", raise_exception=False)
    }
    data = {
        "CandidateId": get_candidate_id(doc.member),
        "CourseId": doc.name,
        "CourseStatusEnum": 0,
        "CourseCompletionPercentage": doc.progress,
        "courseEnrollmentDate": doc.creation
    }
    if doc.progress > 0:
        data["CourseStatusEnum"] = 1
    if doc.progress == 100:
        data["CourseStatusEnum"] = 2
    
    #TODO: Add other conditions for other CourseStatusEnum.

    integration_request = create_request_log(data, service_name="SIDH Progress Update", request_headers=headers)
    try:
        resp = make_post_request(update_progress_url, data=frappe.as_json(data), headers=headers)
        integration_request.update_status(resp, "Completed")
    except Exception as exc:
        integration_request.update_status(exc, "Failed")

def get_candidate_id(member):
    user = frappe.get_doc("User", member)
    return user.get_social_login_userid("sidh")