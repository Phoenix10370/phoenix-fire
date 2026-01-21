import base64
import requests


GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"


def send_graph_email(access_token: str, subject: str, body_html: str, to_emails: list[str], cc_emails: list[str] | None,
                     attachment_name: str, attachment_bytes: bytes):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    to_recipients = [{"emailAddress": {"address": e}} for e in to_emails if e]
    cc_recipients = [{"emailAddress": {"address": e}} for e in (cc_emails or []) if e]

    payload = {
        "message": {
            "subject": subject or "",
            "body": {
                "contentType": "HTML",
                "content": body_html or "",
            },
            "toRecipients": to_recipients,
        },
        "saveToSentItems": True,
    }

    if cc_recipients:
        payload["message"]["ccRecipients"] = cc_recipients

    if attachment_bytes:
        payload["message"]["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_name,
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(attachment_bytes).decode("utf-8"),
            }
        ]

    r = requests.post(GRAPH_SENDMAIL_URL, headers=headers, json=payload, timeout=30)

    # Graph returns 202 Accepted on success
    if r.status_code not in (202, 200):
        raise RuntimeError(f"Graph sendMail failed: {r.status_code} {r.text}")

    return True
