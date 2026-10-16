import unittest

from clean_python import message


class CleanPythonTests(unittest.TestCase):
    def test_message_is_deterministic(self) -> None:
        self.assertEqual(message(), "clean-python")


if __name__ == "__main__":
    unittest.main()
