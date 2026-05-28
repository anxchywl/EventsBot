# Developer Instruction Guide: App Email Sender Setup

This document provides a comprehensive guide for setting up, configuring, testing, and securing the email verification system for the Nazarbayev University Events Mini App.

---

## 1. Email Provider Options

For reliable delivery to corporate addresses like `@nu.edu.kz`, we recommend one of the following secure email service providers:

1. **Amazon SES (Simple Email Service)**
   - *Best for:* Highly reliable, extremely low cost, production grade.
   - *Requirements:* Verify domainownership, request production access to move out of the SES sandbox.
2. **Mailgun / SendGrid**
   - *Best for:* Developer ease of integration, tracking delivery statistics.
   - *Requirements:* SMTP credentials configured via a custom subdomain (e.g. `mail.yourdomain.com`).
3. **Google Workspace SMTP**
   - *Best for:* Internal school accounts or smaller production scales.
   - *SMTP Host:* `smtp.gmail.com`
   - *Security:* Requires creating an **App Password** from the Google Account settings; direct account passwords will be blocked by 2FA.

---

## 2. SMTP & Application Environment Variables

Configure the following environment keys inside your `.env` file for mail dispatch.

```env
# Email server connection parameters
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_USERNAME=postmaster@sandbox.mailgun.org
EMAIL_PASSWORD=your_secure_smtp_password
EMAIL_FROM=NU Events Bot <noreply@nu.edu.kz>

# Expiration and resend throttling
EMAIL_CODE_TTL_MINUTES=10
EMAIL_RESEND_COOLDOWN_SECONDS=60
```

---

## 3. Local Development Setup (Console Fallback)

To ensure developers can test registration flows instantly without deploying active mail transfer agents, the application implements a **Console Fallback Mode**:

- **Active if:** `EMAIL_HOST` is unset, empty, or set to `"console"`.
- **Behavior:** The backend will skip real SMTP delivery and print the generated 6-digit verification code directly into the server logs/console.
- **Example Log:**
  ```text
  ==========================================================
  📧 LOCAL DEV EMAIL SENDER FALLBACK
  To: student@nu.edu.kz
  Subject: 348219 is your Nazarbayev University Events verification code
  Code: 348219
  ==========================================================
  ```
Simply copy the code from the server console and paste it into the mini app to proceed.

---

## 4. Production Setup & Credentials Rotation

When deploying to production:
1. Ensure `EMAIL_HOST` points to your verified production mail server.
2. **Credential Rotation Safeguards:**
   - Never commit plain passwords to Git. The `.env` file is ignored by git.
   - Store credentials as secure environment secrets in your hosting provider (e.g., GitHub Secrets, Heroku, AWS Secrets Manager, Docker Secrets).
   - **Safe Rotation Steps:**
     1. Generate a new SMTP password on your provider's dashboard.
     2. Update the environment variable on the server.
     3. Perform a rolling restart of the FastAPI application.
     4. Test a registration attempt using a development account to confirm delivery.
     5. Revoke the old credentials on the provider's dashboard.

---

## 5. Troubleshooting & Port Configuration

- **Port 587 (Recommended):** Uses standard SMTP with `STARTTLS` upgrade. Ensure port 587 is open on your firewall or cloud security group.
- **Port 465 (Direct SSL):** The service automatically detects port 465 and connects securely using `smtplib.SMTP_SSL`.
- **Port 25:** Highly discouraged. Most cloud hosts (AWS, GCP, DigitalOcean) block egress on port 25 to mitigate spam.
