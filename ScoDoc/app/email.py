# -*- coding: UTF-8 -*
from threading import Thread
from flask import current_app
from flask_mail import Message
from app import mail


def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)


def send_email(
    subject: str, sender: str, recipients: list, text_body: str, html_body=""
):
    """
    Send an email
    If html_body is specified, build a multipart message with HTML content,
    else send a plain text email.
    """
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    send_message(msg)


def send_message(msg):
    Thread(
        target=send_async_email, args=(current_app._get_current_object(), msg)
    ).start()
