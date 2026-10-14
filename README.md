# Spur

Spur is a Flask event-management app for Vasantdada Patil College of Engineering. Students can browse events and register a crew; approved admins can publish events, upload event media, and review registrations.

## Run locally

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set a long random `SECRET_KEY`, initial admin email/password, and (optionally) SMTP settings. The app loads `.env` at startup. Never commit `.env`.
4. Start the app:

   ```powershell
   py app.py
   ```

5. Visit `http://127.0.0.1:5000`.

The initial admin is created at startup only when both `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` are configured. An existing configured admin password is refreshed from the environment at startup. A student can request organiser access from their profile; an existing admin approves requests in the dashboard. Event times use India Standard Time.

## Email

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and `SMTP_USE_TLS` to deliver verification and registration emails. Without an SMTP host, the app logs email previews and exposes a verification link for local demonstration. Do not use demo email mode for a public deployment.

## Deploy

The included `render.yaml` describes a Render web service and PostgreSQL database. In Render, create a new Blueprint from this repository, then enter `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` in the private environment-variable prompt. The requested admin account is not committed to source. Render generates `SECRET_KEY` automatically. The `/healthz` route provides a basic health check.

## Deployment notes

- Set `SECRET_KEY` to a unique, secret value before deployment; the built-in fallback is for local development only.
- Set `DATABASE_URL` to a persistent database connection string. SQLite is suitable for a local demo, not a multi-worker public deployment.
- Put `static/uploads` on persistent storage, or replace local uploads with an object-storage service before deploying across ephemeral instances.
- Email remains in demo mode until SMTP settings are configured in the hosting provider. Account verification and registration confirmations will not be delivered by email before then.
- Serve behind an HTTPS reverse proxy and run with a production WSGI server such as Waitress or Gunicorn. Keep debug mode off.
- Back up the database and uploaded event media together.

## Features

- College email domain checks and verification links.
- Separate student and admin sign-in, with password hashing and admin approval requests.
- Live and upcoming event lists, event galleries, QR/info file uploads, optional participant capacity, and event editing.
- Crew registration with participant names and confirmation email.
- CSRF protection for forms, upload size limits, and constrained upload file extensions.
