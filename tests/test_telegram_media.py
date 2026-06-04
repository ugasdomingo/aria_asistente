import unittest

from aria_core.telegram_media import _select_attachment


class TelegramMediaTests(unittest.TestCase):
    def test_selects_largest_photo(self):
        kind, payload = _select_attachment(
            {
                "photo": [
                    {"file_id": "small", "file_size": 10},
                    {"file_id": "large", "file_size": 20},
                ]
            }
        )

        self.assertEqual(kind, "image")
        self.assertEqual(payload["file_id"], "large")

    def test_document_image_is_treated_as_image(self):
        kind, payload = _select_attachment(
            {"document": {"file_id": "doc", "mime_type": "image/png", "file_name": "x.png"}}
        )

        self.assertEqual(kind, "image")
        self.assertEqual(payload["file_id"], "doc")


if __name__ == "__main__":
    unittest.main()

