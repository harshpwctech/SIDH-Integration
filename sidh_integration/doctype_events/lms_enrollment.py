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
        "client_id": sidh_settings.api_key,
        "client_secret": sidh_settings.get_password("api_secret", raise_exception=False)
    }
    data = {
        "CourseStatusEnum": 0,
        "CandidateId": get_candidate_id(doc.member),
        "CourseId": doc.course,
        "CertificationUrl": "",
        "IsFavorite": "",
        "CourseCompletionPercentage": doc.progress,
        "CourseEnrollmentDate": "", #doc.creation
        "CourseCompletionDate": "",
        "Paid": "",
        "Amount": 0,
        "TransId": "",
        "CertificationStatus": "",
        "CertificationIssueDate": "",
        "CertificationType": "",
        "CertificationPercentage": 0,
        "AssessmentTaken": "",
        "AssessmentDate": "",
        "AssessmentNumberQuestion": 0,
        "AssessmentNumberAnswer": 0,
        "AssessmentNumberCorrect": 0,
        "AssessmentPercentage": 0,
        "Review": "",
        "Rating": 0,
        "PrevRating": 0
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
        response_data = (exc.response.json() if exc.response else str(exc))
        integration_request.update_status(response_data, "Failed")

def get_candidate_id(member):
    user = frappe.get_doc("User", member)
    return user.get_social_login_userid("sidh")