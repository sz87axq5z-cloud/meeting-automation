"""図解パスワードラッパー HTML の暗号化・復号テスト。"""

from __future__ import annotations

import unittest

from app.services.infographic_password_html import (
    decrypt_password_gate_html,
    encrypt_plain_html_to_password_gate,
)
from app.services.infographic_gcs import build_gcs_public_url


class TestInfographicPasswordHtml(unittest.TestCase):
    def test_roundtrip_simple(self) -> None:
        plain = "<!DOCTYPE html><html><body><p>hello 日本語</p></body></html>"
        pw = "test-pass-abc"
        gate = encrypt_plain_html_to_password_gate(plain, pw)
        self.assertIn("ma-enc", gate)
        self.assertNotIn("hello 日本語", gate)
        out = decrypt_password_gate_html(gate, pw)
        self.assertEqual(out, plain)

    def test_roundtrip_large_markup(self) -> None:
        plain = "<!DOCTYPE html><html>" + ("<div>x</div>" * 500) + "</html>"
        pw = "x" * 40
        gate = encrypt_plain_html_to_password_gate(plain, pw)
        out = decrypt_password_gate_html(gate, pw)
        self.assertEqual(out, plain)

    def test_wrong_password_raises(self) -> None:
        plain = "<html><body>a</body></html>"
        gate = encrypt_plain_html_to_password_gate(plain, "right")
        with self.assertRaises(Exception):
            decrypt_password_gate_html(gate, "wrong")

    def test_empty_password_rejected(self) -> None:
        with self.assertRaises(ValueError):
            encrypt_plain_html_to_password_gate("<html></html>", "")


class TestInfographicGcsUrl(unittest.TestCase):
    def test_build_public_url_encodes_space(self) -> None:
        u = build_gcs_public_url("my-bucket", "infographics/a b.html")
        self.assertIn("my-bucket", u)
        self.assertIn("%20", u)


if __name__ == "__main__":
    unittest.main()
