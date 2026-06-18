from common.core.migrations import run_migrations
from common.core.production import validate_production_settings


if __name__ == "__main__":
    try:
        validate_production_settings()
        run_migrations()
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    print("Database migrations applied.")
