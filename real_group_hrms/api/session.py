import frappe

PWA_LOGIN_SOURCE = "hrms_pwa"
PWA_SESSION_MAX_AGE = 60 * 60 * 24 * 365 * 1  # 1 year 


def mark_pwa_session(login_manager=None):
    if frappe.request.path != "/api/method/login":
        return

    if frappe.form_dict.get("login_source") != PWA_LOGIN_SOURCE:
        return

    session_obj = getattr(frappe.local, "session_obj", None)
    if not session_obj or session_obj.user == "Guest":
        return

    session_obj.data.data.no_expiry = 1
    session_obj.data.data.login_source = PWA_LOGIN_SOURCE
    frappe.cache.hset("session", session_obj.sid, session_obj.data)
    frappe.db.set_value(
        "Sessions",
        {"sid": session_obj.sid},
        {"sessiondata": str(session_obj.data["data"])},
        update_modified=False,
    )

    cookie_manager = frappe.local.cookie_manager
    cookie_manager.set_cookie("sid", frappe.session.sid, max_age=PWA_SESSION_MAX_AGE, httponly=True)

    if login_manager:
        cookie_manager.set_cookie("user_id", login_manager.user, max_age=PWA_SESSION_MAX_AGE)
        cookie_manager.set_cookie("full_name", login_manager.full_name or "", max_age=PWA_SESSION_MAX_AGE)
        cookie_manager.set_cookie(
            "user_image",
            (getattr(login_manager.info, "user_image", "") if login_manager.info else "") or "",
            max_age=PWA_SESSION_MAX_AGE,
        )
        cookie_manager.set_cookie(
            "system_user",
            "no" if login_manager.user_type == "Website User" else "yes",
            max_age=PWA_SESSION_MAX_AGE,
        )
