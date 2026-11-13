# Student Record Management System

ScholarDesk is a responsive, administrator-only student record manager built with Flask, Flask-SQLAlchemy, PostgreSQL, and Bootstrap-inspired custom CSS. It includes a dashboard, student CRUD, search and filters, pagination, CSV reports, password settings, CSRF protection, and a Render Blueprint.

## Features

- Admin sign-in, secure Werkzeug password hashing, protected sessions, logout, and password change.
- Create, view, edit, and confirm-before-delete student records.
- Search by student ID or name; filter by gender, course, and year.
- Ten records per page, course/year reports, and UTF-8 CSV export.
- Server-side validation, unique student IDs and emails, SQLAlchemy ORM, and CSRF-protected forms.
- Responsive layouts for mobile, tablet, and desktop.
- Gunicorn production startup and Render-managed PostgreSQL.

## Requirements

- Python 3.10 or newer
- Git
- PostgreSQL 14+ for local PostgreSQL testing (SQLite is used automatically if `DATABASE_URL` is unset)
- A Render account and a GitHub repository for hosted deployment

## Run locally

### 1. Install Python, VS Code, and Git

Install current versions from [python.org](https://www.python.org/downloads/), [code.visualstudio.com](https://code.visualstudio.com/), and [git-scm.com](https://git-scm.com/downloads). During Python setup on Windows, enable **Add Python to PATH**.

Confirm installation in a new terminal:

```powershell
py --version
git --version
```

### 2. Create/open the project

Open this project folder in VS Code. In the VS Code terminal, run:

```powershell
cd "C:\path\to\student record"
py -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
# source .venv/bin/activate
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of `python` below; changing machine-wide execution policy is not required.

### 3. Install packages and configure secrets

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` locally. Set a long, random `SECRET_KEY`, an `ADMIN_USERNAME`, and a unique `ADMIN_PASSWORD` of at least 12 characters. Never add `.env` to Git.

Generate a signing secret without putting it in your source code:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The `.env.example` database URL illustrates PostgreSQL. If you have not installed PostgreSQL locally, leave `DATABASE_URL` unset (or remove that example line) and the app uses a local SQLite database. SQLite is for development only; hosted Render uses PostgreSQL.

### 4. Set up PostgreSQL locally (optional)

Install PostgreSQL and create an empty database named `student_records`, then set `DATABASE_URL` in `.env`, for example:

```text
DATABASE_URL=postgresql://postgres:YOUR_LOCAL_PASSWORD@localhost:5432/student_records
```

Do not use the example password in a real environment. The application accepts Render's `postgres://` URL format too and normalizes it to the installed Psycopg 3 SQLAlchemy driver.

### 5. Initialize tables and run

```powershell
flask --app app db upgrade
flask --app app seed-admin
flask --app app run --debug
```

Open <http://127.0.0.1:5000>. Sign in using the admin username and password from `.env`. The included initial migration creates the tables; `seed-admin` creates the configured initial administrator. Running the seed command again is safe and will not replace an existing administrator's password.

To run the production server locally:

```powershell
gunicorn app:app
```

On Windows, Gunicorn is not supported natively. Use `flask --app app run` on Windows for local development; verify Gunicorn in a Linux environment, Docker container, or Render.

## Test

The test suite uses a temporary SQLite database and does not require a PostgreSQL server:

```powershell
python -m unittest discover -s tests -v
```

It exercises authentication, access control, create/list/search/filter/edit/delete, CSV export, validation, and password changes. A real PostgreSQL URL can be separately smoke-tested by setting `DATABASE_URL` and running `flask --app app db upgrade`.

## Database migrations

The application exposes Flask-Migrate for schema changes. The initial migration is included. After changing a model, generate and apply a migration:

```powershell
flask --app app db migrate -m "Describe schema change"
flask --app app db upgrade
```

Commit the generated migration files. Render applies committed migrations and then runs the idempotent `seed-admin` command before deployment, so a new database is initialized and existing data is preserved.

## GitHub setup and push

### 6. Create a GitHub account and repository

Create a repository on GitHub (for example `student-record-management`). Do not initialize it with files if you already have this local project.

### 7. Push the project

From the project directory:

```powershell
git init
git add .
git status
git commit -m "Build student record management system"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/student-record-management.git
git push -u origin main
```

Review `git status` before commit and make sure `.env`, database files, and credentials are not listed. The `.gitignore` already excludes these local files.

## Deploy to Render

### 8. Create a Render account

Sign up at [render.com](https://render.com/) and connect the GitHub account containing the repository.

### 9. Connect the repository

In the Render Dashboard, choose **New → Blueprint**, select the GitHub repository, and select the `main` branch. Render reads `render.yaml` and proposes a managed PostgreSQL database and web service.

### 10. Configure database and secrets

Review the Blueprint resources. `DATABASE_URL` is wired to the private connection string for the provisioned database, and Render generates a private `SECRET_KEY`. Render prompts for `ADMIN_USERNAME` and `ADMIN_PASSWORD` because they are marked `sync: false`. Set these in Render's secret environment-variable form; do not put real values in `render.yaml`, GitHub, screenshots, or chat. Use a unique password with 12+ characters.

The Blueprint uses a paid Starter web service and Basic PostgreSQL plan. Confirm the current plan and pricing shown in Render before creating resources. If changing plans, edit `render.yaml` to a plan currently available for your account.

### 11. Deploy

Approve **Apply** in Render. The web service installs `requirements.txt`, runs `flask --app app init-db` before deployment, and starts with Gunicorn. In service settings, keep **Auto-Deploy** enabled (the Blueprint's `autoDeployTrigger: commit` deploys commits pushed to the connected branch).

### 12. Verify deployment and database

Wait for Render to show a successful deployment. Open the service's **Events/Logs** and confirm the build, pre-deploy database initialization, and Gunicorn startup all complete. Visit `https://YOUR-SERVICE.onrender.com/health`; it should return `{"status":"ok"}`. This health response confirms the web process is responding, not database health by itself; sign in and create a test student to verify database connectivity and persistence. Do not consider deployment complete until Render reports success and the live site works.

### 13. Test the live website

Sign in using the initial admin credentials entered in Render. Add a test student, find it using search and filters, edit it, view the reports/CSV export, and delete the test record. Restart/redeploy the service, then verify records remain present (they are stored in PostgreSQL, not the web process filesystem). Change the initial password from **Settings** after first sign-in.

Every new commit pushed to `main` triggers a Render deployment while Auto-Deploy is enabled. To use another deployment branch, change the branch in Render's Blueprint/service settings and push to that branch.

## Configuration reference

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Render: yes | SQLAlchemy PostgreSQL connection URL |
| `SECRET_KEY` | yes | Signs sessions and CSRF tokens; use a random secret |
| `ADMIN_USERNAME` | Initial setup | Username for the first admin created by `init-db` |
| `ADMIN_PASSWORD` | Initial setup | Initial admin password (minimum 12 characters) |
| `SESSION_COOKIE_SECURE` | Render: true | Sends the session cookie only over HTTPS |

If `ADMIN_USERNAME`/`ADMIN_PASSWORD` are unset, migrations still create the tables but no admin is created; set both variables in the environment and rerun `flask --app app seed-admin`. The initializer deliberately does not reset an existing admin password.

## Project layout

```text
migrations/            Versioned database schema migrations
app.py                 Flask app, forms, models, routes, CLI initializer
templates/             Responsive Jinja templates
static/css/style.css   Dashboard and mobile styles
static/js/app.js       Menu, confirmation, and small UI interactions
tests/test_app.py      CRUD/authentication regression tests
render.yaml            Render Blueprint for web + PostgreSQL services
Procfile               Gunicorn production start command
requirements.txt       Python dependencies
.env.example           Safe local environment-variable template
```
#   S T U D E N T - R E C O R D  
 