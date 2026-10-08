import pytest
from apps.db.interval_time_zone import interval_mysql_time_zone


class Connection:
    def __init__(self, available=True): self.zone = "SYSTEM"; self.available = available
    def execute(self, statement, params=None):
        text = str(statement)
        value = None
        if text.startswith("SELECT @@"): value = self.zone
        elif text.startswith("SELECT CONVERT"): value = "date" if self.available else None
        elif params: self.zone = params["zone"]
        else: self.zone = "+00:00"
        return type("Result", (), {"scalar": lambda _: value})()
    def invalidate(self): self.invalid = True


@pytest.mark.parametrize("error", [False, True])
def test_timezone_restored_after_success_or_failure(error):
    connection = Connection()
    try:
        with interval_mysql_time_zone(connection, ["Asia/Shanghai"]):
            assert connection.zone == "+00:00"
            if error: raise RuntimeError("query failed")
    except RuntimeError: pass
    assert connection.zone == "SYSTEM"


def test_missing_timezone_database_fails_without_leaking_session_setting():
    connection = Connection(False)
    with pytest.raises(ValueError):
        with interval_mysql_time_zone(connection, ["Asia/Shanghai"]): pytest.fail("query must not run")
    assert connection.zone == "SYSTEM"

@pytest.mark.parametrize('available',[True,False])
def test_explicit_epoch_timezone_conversions_verify_without_session_mutation(available):
    class ReadOnlyTimezoneConnection(Connection):
        def execute(self,statement,params=None):
            assert str(statement).startswith('SELECT CONVERT_TZ'), '显式时区转换不能读写会话时区'
            return super().execute(statement,params)
    connection = ReadOnlyTimezoneConnection(available)
    if available:
        with interval_mysql_time_zone(connection,['Asia/Shanghai'],enforce_utc=False):
            assert connection.zone == 'SYSTEM'
    else:
        with pytest.raises(ValueError):
            with interval_mysql_time_zone(connection,['Asia/Shanghai'],enforce_utc=False):
                pytest.fail('缺少时区能力时不能执行查询')
