import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auth


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "test_users.db"
        self.database_patch = patch.object(auth, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.addCleanup(self.temp_directory.cleanup)

    def test_registration_and_login(self) -> None:
        user = auth.register_user("Alex Green", "ALEX@example.com", "strong-pass-1")

        self.assertEqual(user.full_name, "Alex Green")
        self.assertEqual(user.email, "alex@example.com")
        self.assertEqual(
            auth.authenticate_user("alex@example.com", "strong-pass-1"), user
        )

    def test_wrong_password_is_rejected(self) -> None:
        auth.register_user("Alex Green", "alex@example.com", "strong-pass-1")

        self.assertIsNone(
            auth.authenticate_user("alex@example.com", "incorrect-pass")
        )

    def test_duplicate_email_is_rejected_case_insensitively(self) -> None:
        auth.register_user("Alex Green", "alex@example.com", "strong-pass-1")

        with self.assertRaisesRegex(ValueError, "already exists"):
            auth.register_user("Another Person", "ALEX@example.com", "strong-pass-2")

    def test_registration_validates_password_length(self) -> None:
        with self.assertRaisesRegex(ValueError, "8 and 128"):
            auth.register_user("Alex Green", "alex@example.com", "short")


if __name__ == "__main__":
    unittest.main()
