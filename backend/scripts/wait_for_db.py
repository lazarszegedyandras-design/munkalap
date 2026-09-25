import sys
import time
from sqlalchemy import create_engine, text
from app.config import get_settings

url = get_settings().database_url
engine = create_engine(url, pool_pre_ping=True)
for attempt in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready")
        sys.exit(0)
    except Exception as exc:
        print(f"Waiting for database ({attempt + 1}/60): {exc}")
        time.sleep(1)
print("Database is not reachable", file=sys.stderr)
sys.exit(1)
