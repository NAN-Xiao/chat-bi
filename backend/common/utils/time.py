from datetime import datetime


def get_timestamp():
    dt_millis = int(datetime.now().timestamp() * 1000)
    return dt_millis