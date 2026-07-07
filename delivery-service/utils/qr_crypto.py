"""
QR encryption/decryption utility — Delivery Service
No Django dependency; reads QR_SECRET_KEY from env directly.
"""
import os
import json
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def _get_key() -> bytes:
    raw = os.environ.get("QR_SECRET_KEY", "your-qr-secret-key")
    return hashlib.sha256(raw.encode()).digest()


def encrypt_qr_data(data: dict) -> str:
    key = _get_key()
    iv = os.urandom(16)
    plaintext = json.dumps(data).encode("utf-8")
    pad_len = 16 - (len(plaintext) % 16)
    plaintext += bytes([pad_len] * pad_len)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    return f"{iv.hex()}:{ciphertext.hex()}"


def decrypt_qr_data(encrypted: str) -> dict:
    parts = encrypted.split(":")
    if len(parts) != 2:
        raise ValueError("Invalid encrypted QR format")
    iv_hex, ct_hex = parts
    key = _get_key()
    iv = bytes.fromhex(iv_hex)
    ciphertext = bytes.fromhex(ct_hex)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    pad_len = padded[-1]
    plaintext = padded[:-pad_len]
    return json.loads(plaintext.decode("utf-8"))
