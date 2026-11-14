import unittest
import os
import tempfile
import time
from services.auth_service import AuthService
from services.session_store import SessionStore

class TestAuthService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "test_auth.db")
        self.auth = AuthService(db_path=db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_signup_and_login_success(self):
        user, token, err = self.auth.signup("testuser", "test@example.com", "Password123!")
        self.assertIsNone(err)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "testuser")
        self.assertEqual(user["email"], "test@example.com")
        self.assertTrue(user["user_id"].startswith("user_"))

        # Verify token works
        verified_user = self.auth.verify_token(token)
        self.assertIsNotNone(verified_user)
        self.assertEqual(verified_user["user_id"], user["user_id"])

        # Login with email
        l_user, l_token, l_err = self.auth.login("test@example.com", "Password123!")
        self.assertIsNone(l_err)
        self.assertEqual(l_user["user_id"], user["user_id"])

        # Login with username
        l_user2, l_token2, l_err2 = self.auth.login("testuser", "Password123!")
        self.assertIsNone(l_err2)
        self.assertEqual(l_user2["user_id"], user["user_id"])

    def test_duplicate_user_rejected(self):
        self.auth.signup("alice", "alice@example.com", "pass1234")
        _, _, err = self.auth.signup("alice", "another@example.com", "pass1234")
        self.assertIn("already registered", err.lower())

        _, _, err2 = self.auth.signup("unique_alice", "alice@example.com", "pass1234")
        self.assertIn("already registered", err2.lower())

    def test_wrong_password_rejected(self):
        self.auth.signup("bob", "bob@example.com", "correct_pass")
        u, t, err = self.auth.login("bob", "wrong_pass")
        self.assertIsNone(u)
        self.assertIn("invalid credentials", err.lower())

    def test_token_revocation(self):
        user, token, _ = self.auth.signup("charlie", "charlie@example.com", "pass1234")
        self.assertIsNotNone(self.auth.verify_token(token))
        self.auth.revoke_token(token)
        self.assertIsNone(self.auth.verify_token(token))

    def test_session_store_user_isolation(self):
        store = SessionStore()
        s1 = store.create(user_id="user_A")
        s2 = store.create(user_id="user_B")

        # user_A can require s1
        req1 = store.require(s1.session_id, user_id="user_A")
        self.assertEqual(req1.session_id, s1.session_id)

        # user_B cannot require s1
        with self.assertRaises(PermissionError):
            store.require(s1.session_id, user_id="user_B")

        # user_A cannot delete user_B's session
        with self.assertRaises(PermissionError):
            store.clear_session_data(s2.session_id, user_id="user_A")

if __name__ == "__main__":
    unittest.main()
