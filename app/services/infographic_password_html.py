"""
平文の図解 HTML を、ブラウザ上でパスワード入力後に Web Crypto で復号する単一 HTML に包む。

Python 側は cryptography（AES-256-GCM + PBKDF2-HMAC-SHA256）で暗号化し、
JavaScript 側は同パラメータで復号する。
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Web Crypto の deriveKey(AES-GCM 256) と整合
_PBKDF2_ITERATIONS = 100_000
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_plain_html_to_password_gate(plain_html: str, password: str) -> str:
    """
    平文 HTML を暗号化し、パスワード入力 UI 付きの単一 HTML 文字列を返す。
    """
    if not password:
        raise ValueError("password must be non-empty")
    plain_bytes = plain_html.encode("utf-8")
    salt = _random_bytes(_SALT_LEN)
    nonce = _random_bytes(_NONCE_LEN)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plain_bytes, None)

    payload = {
        "v": 1,
        "s": base64.b64encode(salt).decode("ascii"),
        "i": base64.b64encode(nonce).decode("ascii"),
        "c": base64.b64encode(ciphertext).decode("ascii"),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    return _WRAPPER_TEMPLATE.replace("%%PAYLOAD_JSON%%", payload_json)


def _random_bytes(n: int) -> bytes:
    import os

    return os.urandom(n)


def decrypt_password_gate_html(bundle_html: str, password: str) -> str:
    """
    テスト用: ラッパー HTML から平文 HTML を復号する（Python 実装）。
    """
    m = re.search(
        r'<script\s+type="application/json"\s+id="ma-enc"[^>]*>\s*(\{[\s\S]*?\})\s*</script>',
        bundle_html,
    )
    if not m:
        raise ValueError("ma-enc payload not found")
    data: dict[str, Any] = json.loads(m.group(1))
    salt = base64.b64decode(data["s"])
    nonce = base64.b64decode(data["i"])
    ciphertext = base64.b64decode(data["c"])
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    plain = aesgcm.decrypt(nonce, ciphertext, None)
    return plain.decode("utf-8")


_WRAPPER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>図解を表示する — パスワード入力</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f2f4f8; color: #1a1f2e; }
    .card { background: #fff; padding: 1.75rem 1.5rem; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.08); max-width: 22rem; width: calc(100% - 2rem); }
    h1 { font-size: 1.05rem; margin: 0 0 0.5rem; font-weight: 600; }
    p { font-size: 0.85rem; color: #5c6478; margin: 0 0 1rem; line-height: 1.5; }
    label { display: block; font-size: 0.8rem; margin-bottom: 0.35rem; font-weight: 500; }
    input[type="password"] { width: 100%; padding: 0.55rem 0.65rem; font-size: 1rem; border: 1px solid #ccd; border-radius: 8px; }
    button { margin-top: 1rem; width: 100%; padding: 0.6rem; font-size: 0.95rem; font-weight: 600; border: none; border-radius: 8px; background: #2d6a4f; color: #fff; cursor: pointer; }
    button:hover { background: #245a42; }
    .err { color: #b42318; font-size: 0.8rem; margin-top: 0.65rem; min-height: 1.2em; }
  </style>
</head>
<body>
  <div class="card" id="gate">
    <h1>パスワードを入力してください</h1>
    <p>共有されたパスワードを入力すると、会議の図解が表示されます。ブラウザ内でのみ復号されます。</p>
    <label for="pw">パスワード</label>
    <input type="password" id="pw" autocomplete="off" />
    <button type="button" id="go">表示する</button>
    <div class="err" id="err" aria-live="polite"></div>
  </div>
  <script type="application/json" id="ma-enc">%%PAYLOAD_JSON%%</script>
  <script>
(function () {
  var PBKDF2_ITER = 100000;
  function b64ToBuf(b64) {
    var bin = atob(b64);
    var u = new Uint8Array(bin.length);
    for (var j = 0; j < bin.length; j++) u[j] = bin.charCodeAt(j);
    return u;
  }
  function el(id) { return document.getElementById(id); }
  var raw = el("ma-enc").textContent.trim();
  var payload = JSON.parse(raw);
  if (payload.v !== 1) { el("err").textContent = "未対応のデータ形式です。"; return; }
  var saltB64 = payload.s, ivB64 = payload.i, ctB64 = payload.c;

  async function unlock() {
    el("err").textContent = "";
    var password = el("pw").value;
    if (!password) { el("err").textContent = "パスワードを入力してください。"; return; }
    try {
      var salt = b64ToBuf(saltB64);
      var iv = b64ToBuf(ivB64);
      var ct = b64ToBuf(ctB64);
      var enc = new TextEncoder();
      var pwBuf = enc.encode(password);
      var keyMaterial = await crypto.subtle.importKey("raw", pwBuf, { name: "PBKDF2" }, false, ["deriveKey"]);
      var key = await crypto.subtle.deriveKey(
        { name: "PBKDF2", salt: salt, iterations: PBKDF2_ITER, hash: "SHA-256" },
        keyMaterial,
        { name: "AES-GCM", length: 256 },
        false,
        ["decrypt"]
      );
      var ptBuf = await crypto.subtle.decrypt({ name: "AES-GCM", iv: iv }, key, ct);
      var html = new TextDecoder("utf-8").decode(ptBuf);
      document.open();
      document.write(html);
      document.close();
    } catch (e) {
      el("err").textContent = "パスワードが違うか、データが壊れています。";
    }
  }
  el("go").addEventListener("click", function () { unlock(); });
  el("pw").addEventListener("keydown", function (ev) { if (ev.key === "Enter") unlock(); });
})();
  </script>
</body>
</html>
"""
