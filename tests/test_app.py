import os
import re
import unittest
from datetime import timedelta
from urllib.parse import urlparse

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.pop("INITIAL_ADMIN_EMAIL", None)
os.environ.pop("INITIAL_ADMIN_PASSWORD", None)

import app as spur


class SpurAppTests(unittest.TestCase):
    def setUp(self):
        self.app_context = spur.app.app_context()
        self.app_context.push()
        spur.db.drop_all()
        spur.db.create_all()
        self.client = spur.app.test_client()
        self.admin = spur.Student(
            name="Preview Admin", roll_number="ADMIN-TEST", branch="Other",
            email="admin@pvppcoe.ac.in", password_hash=spur.generate_password_hash("admin-password"),
            verified=True, is_admin=True,
        )
        now = spur.local_now()
        self.live_event = spur.Event(
            title="Live Robotics Demo", club="Robotics Club", start_at=now - timedelta(minutes=10),
            end_at=now + timedelta(hours=2), venue="Main Hall", branches="All branches",
            description="See student-built robots in action.", capacity=3,
        )
        self.upcoming_event = spur.Event(
            title="Upcoming Campus Hack Night", club="Computer Society", start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=4), venue="Innovation Lab", branches="All branches",
            description="Build a small project with a new team.",
        )
        spur.db.session.add_all([self.admin, self.live_event, self.upcoming_event])
        spur.db.session.commit()

    def tearDown(self):
        spur.db.session.remove()
        spur.db.drop_all()
        self.app_context.pop()

    def csrf(self, path):
        page = self.client.get(path).get_data(as_text=True)
        return re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)

    def login_student(self, student):
        with self.client.session_transaction() as session:
            session["student_id"] = student.id

    def test_public_pages_and_live_upcoming_event_cards_render(self):
        for path in ("/", "/login", "/signup", "/admin/login", "/healthz"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        home = self.client.get("/").get_data(as_text=True)
        self.assertIn("Live Robotics Demo", home)
        self.assertIn("Upcoming Campus Hack Night", home)
        preview = self.client.get(f"/events/{self.live_event.id}/preview").get_data(as_text=True)
        self.assertIn("See student-built robots in action.", preview)
        self.assertIn("Register", preview)

    def test_college_email_signup_requires_verification_before_registration(self):
        token = self.csrf("/signup")
        invalid = self.client.post("/signup", data={
            "csrf_token": token, "name": "Student One", "roll_number": "ST-001",
            "branch": "Computer Engineering", "email": "student@example.com", "password": "password123",
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertIsNone(spur.Student.query.filter_by(roll_number="ST-001").first())

        self.client.post("/signup", data={
            "csrf_token": token, "name": "Student One", "roll_number": "ST-001",
            "branch": "Computer Engineering", "email": "student@pvppcoe.ac.in", "password": "password123",
        })
        login_page = self.client.get("/login").get_data(as_text=True)
        match = re.search(r'Demo email verification link: <a href="([^"]+)"', login_page)
        self.assertIsNotNone(match)
        self.client.get(urlparse(match.group(1)).path)
        student = spur.Student.query.filter_by(roll_number="ST-001").first()
        self.assertTrue(student.verified)

    def test_admin_login_and_approval_gated_admin_request(self):
        student = spur.Student(
            name="Student Two", roll_number="ST-002", branch="Mechanical Engineering",
            email="student2@pvppcoe.ac.in", password_hash=spur.generate_password_hash("password123"), verified=True,
        )
        spur.db.session.add(student)
        spur.db.session.commit()
        self.login_student(student)
        response = self.client.post("/admin/request", data={"csrf_token": self.csrf("/profile")})
        self.assertEqual(response.status_code, 302)

        admin_token = self.csrf("/admin/login")
        response = self.client.post("/admin/login", data={
            "csrf_token": admin_token, "email": self.admin.email, "password": "admin-password",
        })
        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get("/admin").get_data(as_text=True)
        self.assertIn("Student Two", dashboard)

        approval_token = re.search(r'<meta name="csrf-token" content="([^"]+)"', dashboard).group(1)
        response = self.client.post(f"/admin/requests/{student.id}/approve", data={"csrf_token": approval_token})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(spur.db.session.get(spur.Student, student.id).is_admin)

    def test_event_registration_counts_names_and_prevents_duplicate(self):
        student = spur.Student(
            name="Student Three", roll_number="ST-003", branch="Civil Engineering",
            email="student3@pvppcoe.ac.in", password_hash=spur.generate_password_hash("password123"), verified=True,
        )
        spur.db.session.add(student)
        spur.db.session.commit()
        self.login_student(student)
        detail = self.client.get(f"/events/{self.live_event.id}").get_data(as_text=True)
        self.assertIn("Main Hall", detail)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', detail).group(1)
        response = self.client.post(f"/events/{self.live_event.id}/register", data={
            "csrf_token": token, "participant_count": "2", "participant_names": "Student Three\nFriend One",
        })
        self.assertEqual(response.status_code, 302)
        spur.db.session.refresh(self.live_event)
        self.assertEqual(self.live_event.participant_count, 2)

        detail = self.client.get(f"/events/{self.live_event.id}").get_data(as_text=True)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', detail).group(1)
        response = self.client.post(f"/events/{self.live_event.id}/register", data={
            "csrf_token": token, "participant_count": "1", "participant_names": "Student Three",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(spur.Registration.query.filter_by(student_id=student.id, event_id=self.live_event.id).count(), 1)


if __name__ == "__main__":
    unittest.main()
