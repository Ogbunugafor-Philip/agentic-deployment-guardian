import pytest

from app.crypto import decrypt, encrypt


def test_round_trip():
    data = b"sensitive raw log bytes \x00\x01 with unicode \xe2\x80\x94"
    blob = encrypt(data)
    assert blob != data
    assert decrypt(blob) == data


def test_nonce_is_random():
    data = b"same plaintext"
    assert encrypt(data) != encrypt(data)  # different nonce each time


def test_tampered_ciphertext_fails():
    blob = bytearray(encrypt(b"hello"))
    blob[-1] ^= 0xFF  # flip a bit in the tag/ciphertext
    with pytest.raises(Exception):
        decrypt(bytes(blob))
