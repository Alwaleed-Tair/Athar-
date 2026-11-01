"""
Outgoing e-mail. Plain SMTP via the standard library -- no third-party
service is assumed. Nothing is ever faked:

* SMTP configured      -> the message is really sent (result "SENT").
* ATHAR_MAIL_CONSOLE=1 -> dev only; the message is printed to the server
                          log (result "CONSOLE").
* neither              -> nothing is sent (result "NOT_CONFIGURED") and the
                          caller must tell the user honestly.
"""
import smtplib
import ssl
from email.message import EmailMessage

from . import config


def is_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_FROM)


def delivery_available() -> bool:
    return is_configured() or config.MAIL_CONSOLE


def send_mail(to: str, subject: str, text_body: str, html_body: str | None = None, reply_to: str | None = None) -> str:
    """Returns SENT | CONSOLE | NOT_CONFIGURED | FAILED. Never raises."""
    if not is_configured():
        if config.MAIL_CONSOLE:
            print(f"[ATHAR][MAIL-CONSOLE] To: {to}\nSubject: {subject}\n{text_body}\n")
            return "CONSOLE"
        return "NOT_CONFIGURED"

    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if config.SMTP_SECURITY == "ssl":
            server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
            if config.SMTP_SECURITY == "starttls":
                server.starttls(context=ssl.create_default_context())
        with server:
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return "SENT"
    except Exception as exc:  # network/auth errors must not crash the request
        print(f"[ATHAR] SMTP send failed: {type(exc).__name__}")
        return "FAILED"
