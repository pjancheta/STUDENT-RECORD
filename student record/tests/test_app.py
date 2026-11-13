import os
import unittest
from datetime import date
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")

from app import Admin, Student, create_app, db, normalize_database_url


class StudentRecordAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        admin = Admin(username="manager")
        admin.set_password("TestPassword!123")
        db.session.add(admin)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self):
        return self.client.post(
            "/login",
            data={"username": "manager", "password": "TestPassword!123"},
            follow_redirects=True,
        )

    def student_data(self, **overrides):
        data = {
            "student_id": "2025-0001",
            "first_name": "Avery",
            "middle_name": "Jordan",
            "last_name": "Rivera",
            "gender": "Female",
            "date_of_birth": "2005-04-12",
            "email": "avery@example.edu",
            "contact_number": "+1 (555) 010-0200",
            "address": "12 Campus Road, Brookfield",
            "course": "Computer Science",
            "year_level": "2",
        }
        data.update(overrides)
        return data

    def test_health_and_admin_route_protection(self):
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_csrf_rejects_post_without_token(self):
        protected_app = create_app(
            {
                "TESTING": False,
                "SECRET_KEY": "csrf-test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            }
        )
        response = protected_app.test_client().post(
            "/login", data={"username": "manager", "password": "TestPassword!123"}
        )
        self.assertEqual(response.status_code, 400)

    def test_render_postgres_urls_select_psycopg_driver(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@host/db"),
            "postgresql+psycopg://user:pass@host/db",
        )
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@host/db"),
            "postgresql+psycopg://user:pass@host/db",
        )

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        self.sign_in()
        self.client.post(
            "/students/new",
            data=self.student_data(first_name="=2+2"),
            follow_redirects=True,
        )
        export = self.client.get("/reports/export.csv")
        self.assertIn(b"'=2+2", export.data)

    def test_seed_admin_is_idempotent_and_requires_both_credentials(self):
        runner = self.app.test_cli_runner()
        with patch.dict(
            os.environ,
            {"ADMIN_USERNAME": "new-admin", "ADMIN_PASSWORD": "NewAdminPassword!234"},
        ):
            first = runner.invoke(args=["seed-admin"])
            second = runner.invoke(args=["seed-admin"])
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(second.exit_code, 0)
        admin = db.session.query(Admin).filter_by(username="new-admin").one()
        self.assertTrue(admin.check_password("NewAdminPassword!234"))
        with patch.dict(os.environ, {"ADMIN_USERNAME": "incomplete"}, clear=True):
            incomplete = runner.invoke(args=["seed-admin"])
        self.assertNotEqual(incomplete.exit_code, 0)
        self.assertIn("must both be configured", incomplete.output)

    def test_login_logout_and_bad_credentials(self):
        invalid = self.client.post(
            "/login", data={"username": "manager", "password": "wrong"}, follow_redirects=True
        )
        self.assertIn(b"incorrect", invalid.data)
        response = self.sign_in()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Student statistics", response.data)
        logged_out = self.client.post("/logout", follow_redirects=True)
        self.assertIn(b"Sign in to your account", logged_out.data)

    def test_student_create_search_filter_edit_delete_and_export(self):
        self.sign_in()
        created = self.client.post(
            "/students/new", data=self.student_data(), follow_redirects=True
        )
        self.assertIn(b"Student record added.", created.data)
        student = db.session.query(Student).one()

        search = self.client.get("/students?q=2025-0001&gender=Female&course=Computer+Science&year=2")
        self.assertIn(b"Avery Jordan Rivera", search.data)
        self.assertIn(b"2025-0001", search.data)
        self.assertIn(b"avery@example.edu", search.data)

        updated = self.client.post(
            f"/students/{student.id}/edit",
            data=self.student_data(first_name="Alex", email="alex@example.edu"),
            follow_redirects=True,
        )
        self.assertIn(b"Student record updated.", updated.data)
        self.assertEqual(student.first_name, "Alex")

        export = self.client.get("/reports/export.csv")
        self.assertEqual(export.status_code, 200)
        self.assertIn(b"alex@example.edu", export.data)
        self.assertIn("text/csv", export.content_type)

        deleted = self.client.post(f"/students/{student.id}/delete", follow_redirects=True)
        self.assertIn(b"record was deleted", deleted.data)
        self.assertEqual(db.session.query(Student).count(), 0)

    def test_form_validation_and_unique_student_id(self):
        self.sign_in()
        bad_date = self.client.post(
            "/students/new",
            data=self.student_data(date_of_birth=(date.today().isoformat())),
        )
        self.assertEqual(bad_date.status_code, 200)
        self.assertIn(b"Date of birth must be in the past.", bad_date.data)

        first = self.client.post("/students/new", data=self.student_data())
        self.assertEqual(first.status_code, 302)
        duplicate = self.client.post(
            "/students/new",
            data=self.student_data(email="different@example.edu"),
            follow_redirects=True,
        )
        self.assertIn(b"already in use", duplicate.data)
        self.assertEqual(db.session.query(Student).count(), 1)

    def test_password_change_requires_current_password_and_strong_new_password(self):
        self.sign_in()
        wrong_current = self.client.post(
            "/settings",
            data={
                "current_password": "not-the-password",
                "new_password": "NewStrongPassword!42",
                "confirm_password": "NewStrongPassword!42",
            },
            follow_redirects=True,
        )
        self.assertIn(b"current password is incorrect", wrong_current.data)
        changed = self.client.post(
            "/settings",
            data={
                "current_password": "TestPassword!123",
                "new_password": "NewStrongPassword!42",
                "confirm_password": "NewStrongPassword!42",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Password updated successfully.", changed.data)
        self.assertTrue(db.session.query(Admin).one().check_password("NewStrongPassword!42"))


if __name__ == "__main__":
    unittest.main()
