import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("app.services.email")

TEMPLATES = {
    "en": {
        "subject": "NU Events Verification",
        "title": "Verification",
        "hello": "Hello,",
        "intro": "Thank you for registering at NU Events. To complete your setup, please use the 6-digit verification code below:",
        "expires": "This verification code will expire in {ttl} minutes.",
        "ignore": "If you did not request this code, you can safely ignore this email.",
        "best_regards": "Best regards,<br>NU Events Team",
    },
    "ru": {
        "subject": "Верификация NU events",
        "title": "Подтверждение",
        "hello": "Здравствуйте,",
        "intro": "Спасибо за регистрацию в приложении NU Events. Для завершения настройки введите следующий 6-значный код подтверждения:",
        "expires": "Этот код подтверждения действителен в течение {ttl} минут.",
        "ignore": "Если вы не запрашивали этот код, просто проигнорируйте это письмо.",
        "best_regards": "С наилучшими пожеланиями,<br>Команда NU Events",
    },
    "kk": {
        "subject": "NU events верификациясы",
        "title": "Растау",
        "hello": "Сәлеметсіз бе,",
        "intro": "NU Events қосымшасына тіркелгеніңіз үшін рақмет. Орнатуды аяқтау үшін төмендегі 6 таңбалы растау кодын пайдаланыңыз:",
        "expires": "Бұл растау кодының жарамдылық мерзімі {ttl} минуттан кейін аяқталады.",
        "ignore": "Егер сіз бұл кодты сұрамаған болсаңыз, бұл хатты елемеуге болады.",
        "best_regards": "Құрметпен,<br>NU Events командасы",
    },
}


# send localized verification emails for account signup
def send_verification_email(
    email: str, code: str, lang: str = "en", theme: str = "light"
) -> None:
    """
    Sends a dynamically styled 6-digit verification code email.
    Subject is set to 'NU Events Verification'.
    Directly matches the user's active APP theme (Dark -> Purple tone, Light -> Blue tone).
    In both themes, the backdrop is completely transparent to integrate naturally into any phone mail client.
    """
    settings = get_settings()
    ttl = settings.email_code_ttl_minutes

    lang_code = (lang or "en").lower()[:2]
    if lang_code not in TEMPLATES:
        lang_code = "en"

    t = TEMPLATES[lang_code]
    subject = t["subject"]

    # include plaintext for clients that block html email
    body_text = (
        f"{t['hello']}\n\n"
        f"{t['intro']}\n\n"
        f"    {code}\n\n"
        f"{t['expires'].format(ttl=ttl)}\n"
        f"{t['ignore']}\n\n"
        f"Best regards,\n"
        f"NU Events Team"
    )

    # mirror the mini app theme in verification emails
    is_dark = (theme or "light").lower() == "dark"
    if is_dark:
        card_bg = "#ffffff"
        card_border = "#e2e8f0"
        text_color = "#1e293b"
        header_gradient = "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)"
        code_box_bg = "#faf5ff"
        code_box_border = "#e9d5ff"
        code_text_color = "#7c3aed"
        muted_text_color = "#94a3b8"
        warning_border = "#f1f5f9"
    else:
        card_bg = "#ffffff"
        card_border = "#e2e8f0"
        text_color = "#1e293b"
        header_gradient = "linear-gradient(135deg, #0284c7 0%, #0ea5e9 100%)"
        code_box_bg = "#f0f9ff"
        code_box_border = "#bae6fd"
        code_text_color = "#0284c7"
        muted_text_color = "#94a3b8"
        warning_border = "#f1f5f9"

    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: transparent !important;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: {text_color};
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      background: transparent !important;
      padding: 24px 0;
    }}
    .container {{
      max-width: 500px;
      margin: 0 auto;
      background: {card_bg};
      border: 1px solid {card_border};
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }}
    .header {{
      background: {header_gradient};
      padding: 32px 24px;
      text-align: center;
    }}
    .header h1 {{
      margin: 0;
      color: #ffffff;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
    }}
    .content {{
      padding: 36px 32px;
    }}
    .greeting {{
      font-size: 16px;
      font-weight: 700;
      margin-top: 0;
      margin-bottom: 12px;
      color: #0f172a;
    }}
    .text {{
      font-size: 15px;
      line-height: 1.6;
      margin-top: 0;
      margin-bottom: 28px;
      color: #475569;
    }}
    .code-box {{
      background-color: {code_box_bg};
      border: 1px solid {code_box_border};
      border-radius: 12px;
      padding: 24px;
      text-align: center;
      margin-bottom: 28px;
    }}
    .code-digits {{
      font-size: 38px;
      font-weight: 800;
      color: {code_text_color};
      letter-spacing: 6px;
      margin: 0;
      font-family: 'Courier New', Courier, monospace;
      cursor: pointer;
      display: inline-block;
      -webkit-user-select: all;
      -moz-user-select: all;
      -ms-user-select: all;
      user-select: all;
    }}
    .footer-text {{
      font-size: 13px;
      line-height: 1.5;
      color: {muted_text_color};
      margin-top: 0;
      margin-bottom: 12px;
    }}
    .footer-text.warning {{
      border-top: 1px solid {warning_border};
      padding-top: 16px;
      margin-bottom: 24px;
    }}
    .signature {{
      font-size: 14px;
      line-height: 1.5;
      color: #64748b;
      margin: 0;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <h1>{t["title"]}</h1>
      </div>
      <div class="content">
        <p class="greeting">{t["hello"]}</p>
        <p class="text">{t["intro"]}</p>
        <div class="code-box">
          <h2 class="code-digits">{code}</h2>
        </div>
        <p class="footer-text">{t["expires"].format(ttl=ttl)}</p>
        <p class="footer-text warning">{t["ignore"]}</p>
        <p class="signature">{t["best_regards"]}</p>
      </div>
    </div>
  </div>
</body>
</html>
"""

    # print emails locally when smtp is disabled
    if settings.email_host == "console" or settings.email_host is None:
        logger.info(
            f"\n==========================================================\n"
            f"📧 LOCAL DEV EMAIL SENDER FALLBACK ({lang_code.upper()} - {theme.upper()})\n"
            f"To: {email}\n"
            f"Subject: {subject}\n"
            f"Code: {code}\n"
            f"==========================================================\n"
        )
        return

    try:
        msg = EmailMessage()
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
        msg["Subject"] = subject
        msg["From"] = settings.email_from or f"{subject} <noreply@nu.edu.kz>"
        msg["To"] = email

        port = settings.email_port or 587
        use_ssl = port == 465
        ctx = ssl.create_default_context()

        if use_ssl:
            with smtplib.SMTP_SSL(
                settings.email_host, port, timeout=10, context=ctx
            ) as smtp:
                if settings.email_username and settings.email_password:
                    smtp.login(
                        settings.email_username,
                        settings.email_password.get_secret_value(),
                    )
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.email_host, port, timeout=10) as smtp:
                smtp.ehlo()
                if port == 587:
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                if settings.email_username and settings.email_password:
                    smtp.login(
                        settings.email_username,
                        settings.email_password.get_secret_value(),
                    )
                smtp.send_message(msg)
        logger.info(f"Successfully sent verification email to {email}")
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")
        raise RuntimeError("Failed to send verification email due to SMTP error") from e


# send password reset emails with neutral styling


RESET_TEMPLATES = {
    "en": {
        "subject": "Events Bot password reset code",
        "title": "Password Reset",
        "hello": "Hello,",
        "intro": "You requested a password reset for your NU Events account. Use the 6-digit code below to set a new password:",
        "expires": "This code expires in 10 minutes.",
        "ignore": "If you did not request this, you can safely ignore this email.",
        "best_regards": "Best regards,<br>NU Events Team",
    },
    "ru": {
        "subject": "Events Bot password reset code",
        "title": "Сброс пароля",
        "hello": "Здравствуйте,",
        "intro": "Вы запросили сброс пароля для вашего аккаунта NU Events. Используйте следующий 6-значный код для установки нового пароля:",
        "expires": "Срок действия кода истекает через 10 минут.",
        "ignore": "Если вы не запрашивали сброс пароля, проигнорируйте это письмо.",
        "best_regards": "С наилучшими пожеланиями,<br>Команда NU Events",
    },
    "kk": {
        "subject": "Events Bot password reset code",
        "title": "Құпиясөзді қалпына келтіру",
        "hello": "Сәлеметсіз бе,",
        "intro": "Сіз NU Events аккаунтыңыздың құпиясөзін қалпына келтіруді сұрадыңыз. Жаңа құпиясөз орнату үшін келесі 6 таңбалы кодты пайдаланыңыз:",
        "expires": "Кодтың жарамдылық мерзімі 10 минут.",
        "ignore": "Егер сіз бұл сұранысты жасамаған болсаңыз, бұл хатты елемеуге болады.",
        "best_regards": "Құрметпен,<br>NU Events командасы",
    },
}


# send password reset emails without depending on app theme
def send_password_reset_email(email: str, code: str, lang: str = "en") -> None:
    """
    Sends a styled password reset code email.
    Subject: Events Bot password reset code
    Never logs the code value.
    """
    settings = get_settings()

    lang_code = (lang or "en").lower()[:2]
    if lang_code not in RESET_TEMPLATES:
        lang_code = "en"

    t = RESET_TEMPLATES[lang_code]
    subject = t["subject"]

    body_text = (
        f"{t['hello']}\n\n"
        f"{t['intro']}\n\n"
        f"    {code}\n\n"
        f"{t['expires']}\n"
        f"{t['ignore']}\n\n"
        f"Best regards,\n"
        f"NU Events Team"
    )

    # keep reset emails visually neutral across themes
    card_bg = "#ffffff"
    card_border = "#e2e8f0"
    text_color = "#1e293b"
    header_gradient = "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)"
    code_box_bg = "#faf5ff"
    code_box_border = "#e9d5ff"
    code_text_color = "#7c3aed"
    muted_text_color = "#94a3b8"
    warning_border = "#f1f5f9"

    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: transparent !important;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: {text_color};
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{ width: 100%; background: transparent !important; padding: 24px 0; }}
    .container {{
      max-width: 500px;
      margin: 0 auto;
      background: {card_bg};
      border: 1px solid {card_border};
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }}
    .header {{
      background: {header_gradient};
      padding: 32px 24px;
      text-align: center;
    }}
    .header h1 {{ margin: 0; color: #ffffff; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
    .content {{ padding: 36px 32px; }}
    .greeting {{ font-size: 16px; font-weight: 700; margin-top: 0; margin-bottom: 12px; color: #0f172a; }}
    .text {{ font-size: 15px; line-height: 1.6; margin-top: 0; margin-bottom: 28px; color: #475569; }}
    .code-box {{
      background-color: {code_box_bg};
      border: 1px solid {code_box_border};
      border-radius: 12px;
      padding: 24px;
      text-align: center;
      margin-bottom: 28px;
    }}
    .code-digits {{
      font-size: 38px;
      font-weight: 800;
      color: {code_text_color};
      letter-spacing: 6px;
      margin: 0;
      font-family: 'Courier New', Courier, monospace;
      -webkit-user-select: all;
      -moz-user-select: all;
      user-select: all;
    }}
    .footer-text {{ font-size: 13px; line-height: 1.5; color: {muted_text_color}; margin-top: 0; margin-bottom: 12px; }}
    .footer-text.warning {{ border-top: 1px solid {warning_border}; padding-top: 16px; margin-bottom: 24px; }}
    .signature {{ font-size: 14px; line-height: 1.5; color: #64748b; margin: 0; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <h1>{t["title"]}</h1>
      </div>
      <div class="content">
        <p class="greeting">{t["hello"]}</p>
        <p class="text">{t["intro"]}</p>
        <div class="code-box">
          <h2 class="code-digits">{code}</h2>
        </div>
        <p class="footer-text">{t["expires"]}</p>
        <p class="footer-text warning">{t["ignore"]}</p>
        <p class="signature">{t["best_regards"]}</p>
      </div>
    </div>
  </div>
</body>
</html>
"""

    if settings.email_host == "console" or settings.email_host is None:
        logger.info(
            f"\n==========================================================\n"
            f"📧 LOCAL DEV PASSWORD RESET EMAIL ({lang_code.upper()})\n"
            f"To: {email}\n"
            f"Subject: {subject}\n"
            f"[reset code hidden]\n"
            f"==========================================================\n"
        )
        return

    try:
        msg = EmailMessage()
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
        msg["Subject"] = subject
        msg["From"] = settings.email_from or f"NU Events <noreply@nu.edu.kz>"
        msg["To"] = email

        port = settings.email_port or 587
        use_ssl = port == 465
        ctx = ssl.create_default_context()

        if use_ssl:
            with smtplib.SMTP_SSL(
                settings.email_host, port, timeout=10, context=ctx
            ) as smtp:
                if settings.email_username and settings.email_password:
                    smtp.login(
                        settings.email_username,
                        settings.email_password.get_secret_value(),
                    )
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.email_host, port, timeout=10) as smtp:
                smtp.ehlo()
                if port == 587:
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                if settings.email_username and settings.email_password:
                    smtp.login(
                        settings.email_username,
                        settings.email_password.get_secret_value(),
                    )
                smtp.send_message(msg)
        logger.info(f"Successfully sent password reset email to {email}")
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}: {e}")
        raise RuntimeError(
            "Failed to send password reset email due to SMTP error"
        ) from e
