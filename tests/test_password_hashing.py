from apps.system.crud.user import authenticate
from apps.system.models.user import UserModel
from common.core.security import (
    default_password_hash,
    is_md5_password_hash,
    md5pwd,
    verify_stored_password,
)


class _Result:
    def __init__(self, user):
        self.user = user

    def first(self):
        return self.user


class _Session:
    def __init__(self, user):
        self.user = user
        self.added = []

    def exec(self, _statement):
        return _Result(self.user)

    def add(self, value):
        self.added.append(value)


def test_default_password_hash_is_not_md5():
    password_hash = default_password_hash()

    assert not is_md5_password_hash(password_hash)
    assert password_hash.startswith("$2")
    assert verify_stored_password("elex@123", password_hash) == (True, False)


def test_authenticate_rehashes_legacy_md5_password():
    user = UserModel(
        account="demo",
        name="Demo",
        email="demo@example.com",
        status=1,
        password=md5pwd("Secret123!"),
    )
    session = _Session(user)

    result = authenticate(session=session, account="demo", password="Secret123!")

    assert result is not None
    assert result.account == "demo"
    assert session.added == [user]
    assert not is_md5_password_hash(user.password)
    assert verify_stored_password("Secret123!", user.password) == (True, False)
