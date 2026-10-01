import sqlite3
import tempfile
import unittest
import gc
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

import fitness_mvp as mvp


class PrivacyAuthContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "users.db"
        self.user_db = patch.object(mvp, "USER_DB", self.db_path)
        self.user_db.start()
        mvp.init_user_db()

    def tearDown(self):
        self.user_db.stop()
        gc.collect()
        self.temp.cleanup()

    def test_signup_accepts_only_minimum_profile_and_stores_no_personal_fields(self):
        body = mvp.SignupBody(
            username="minimal", password="pw", sex="F", age=40,
            height_cm=160, weight_kg=60,
        )
        mvp.signup(body)
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT name,email,phone,birth_date,sex,age,height_cm,weight_kg,profile_completed "
                "FROM users WHERE username='minimal'"
            ).fetchone()
        db.close()
        self.assertEqual(row, ("", "", "", "", "F", 40, 160.0, 60.0, 1))

    def test_signup_and_profile_reject_personal_fields(self):
        with self.assertRaises(ValidationError):
            mvp.SignupBody(
                username="x", password="pw", sex="M", age=30,
                height_cm=175, weight_kg=70, name="fake",
            )
        with self.assertRaises(ValidationError):
            mvp.ProfileBody(
                sex="M", age=30, height_cm=175, weight_kg=70,
                phone="010-0000-0000",
            )

    def test_login_and_profile_response_expose_only_minimum_fields(self):
        mvp.signup(mvp.SignupBody(
            username="minimal", password="pw", sex="M", age=30,
            height_cm=175, weight_kg=70,
        ))
        response = mvp.login(mvp.LoginBody(username="minimal", password="pw"))
        self.assertEqual(set(response), {"token", "username", "profile"})
        self.assertEqual(
            set(response["profile"]),
            {"username", "sex", "age", "height_cm", "weight_kg", "profile_completed"},
        )

    def test_profile_update_is_owned_by_token_and_survives_relogin_and_db_reopen(self):
        mvp.signup(mvp.SignupBody(
            username="owner", password="pw", sex="M", age=30,
            height_cm=175, weight_kg=70,
        ))
        mvp.signup(mvp.SignupBody(
            username="other", password="pw", sex="F", age=31,
            height_cm=160, weight_kg=55,
        ))
        login = mvp.login(mvp.LoginBody(username="owner", password="pw"))
        authorization = f"Bearer {login['token']}"
        updated = mvp.update_profile(
            mvp.ProfileBody(sex="F", age=47, height_cm=167.5, weight_kg=68.2),
            authorization,
        )
        self.assertEqual(
            {key: updated[key] for key in ("username", "sex", "age", "height_cm", "weight_kg")},
            {"username": "owner", "sex": "F", "age": 47, "height_cm": 167.5, "weight_kg": 68.2},
        )
        self.assertEqual(mvp.get_profile(authorization), updated)

        # Reopening/initializing the same SQLite file models a process restart.
        mvp.init_user_db()
        relogin = mvp.login(mvp.LoginBody(username="owner", password="pw"))
        self.assertEqual(relogin["profile"], updated)
        self.assertEqual(mvp.login(mvp.LoginBody(username="other", password="pw"))["profile"]["age"], 31)

    def test_expired_token_is_rejected_and_its_conversation_is_removed(self):
        mvp.signup(mvp.SignupBody(
            username="expired", password="pw", sex="M", age=40,
            height_cm=175, weight_kg=70,
        ))
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO auth_sessions(token,username,created_at) VALUES(?,?,?)",
                ("expired-token", "expired", "2000-01-01T00:00:00+00:00"),
            )
            db.execute(
                "INSERT INTO chat_conversations(token,username,conversation_id,role,content,created_at) VALUES(?,?,?,?,?,?)",
                ("expired-token", "expired", "expired-chat", "user", "old", "2000-01-01T00:00:00+00:00"),
            )
        self.assertIsNone(mvp._auth("Bearer expired-token"))
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM auth_sessions WHERE token='expired-token'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM chat_conversations WHERE token='expired-token'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
