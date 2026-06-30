import json

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from tools.migrate_datasource_config_encryption import (
    FERNET_PREFIX,
    decrypt_legacy_or_plaintext,
    encrypt_fernet,
)


def _legacy_ecb_encrypt(text: str, key: bytes) -> str:
    import base64

    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


def test_migration_reads_sqlbot_legacy_datasource_config():
    plain = '{"host":"127.0.0.1","database":"slg_bi_mock"}'
    encrypted = _legacy_ecb_encrypt(plain, b"SQLBot1234567890")

    decrypted, source = decrypt_legacy_or_plaintext(
        encrypted,
        [b"Zhishu1234567890", b"SQLBot1234567890"],
    )

    assert source == "legacy_ecb:SQLBot1234567890"
    assert json.loads(decrypted)["database"] == "slg_bi_mock"


def test_migration_writes_current_fernet_format():
    plain = '{"host":"127.0.0.1","database":"slg_bi_mock"}'
    secret = "s" * 48

    encrypted = encrypt_fernet(plain, secret)

    assert encrypted.startswith(FERNET_PREFIX)
    assert encrypted != plain
