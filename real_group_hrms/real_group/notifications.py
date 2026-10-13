import frappe
from hrms.controllers.employee_reminders import get_employees_who_are_born_today

def send_birthday_wishes():

	sender = get_sender_email()
	employees_born_today = get_employees_who_are_born_today()

	bcc_emails = []
	for company, birthday_persons in employees_born_today.items():
		for person in birthday_persons:
			if person.company_email:
				bcc_emails.append(person.company_email)
			if person.personal_email:
				bcc_emails.append(person.personal_email)

	reminder_text, message = get_birthday_reminder_text_and_message()

	print(bcc_emails, reminder_text, message, sender)
	send_birthday_reminder(bcc_emails, reminder_text, message, sender)

def get_sender_email():
	
	email_account = frappe.db.get_single_value("Real Group Settings", "email_account")

	if not email_account:
		email_account = frappe.db.get_all("Email Account", fields=["name", "email_id"], filters={"default_outgoing": 1})
	
		if email_account:
			return email_account[0].email_id

	return frappe.db.get_value("Email Account", email_account, "email_id")

def get_birthday_reminder_text_and_message():

	reminder_text = frappe.db.get_single_value("Real Group Settings", "birthday_wish_subject")
	message = frappe.db.get_single_value("Real Group Settings", "birthday_wish_message")

	return reminder_text, message

def send_birthday_reminder(recipients, reminder_text, message, sender=None):
	frappe.sendmail(
		sender=sender,
		# recipients='yogeshsharma@realgroup.org',
		# recipients=sender,
		# bcc=recipients,
		recipients=recipients,
		subject=reminder_text,
		content=message,
		header="&nbsp;"
	)