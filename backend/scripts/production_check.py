"""
脚本说明：这个脚本放后端脚本相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from common.core.production import validate_production_settings

if __name__ == "__main__":
    try:
        errors = validate_production_settings()
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    if errors:
        print("Production checks are disabled, but these issues were found:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Production settings check passed.")
