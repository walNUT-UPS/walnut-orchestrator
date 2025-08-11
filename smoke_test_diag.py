import os
from sqlalchemy import create_engine, text
import inspect, traceback, sys

print("Starting diagnostic smoke test...")

try:
    # Set environment variables
    os.environ["WALNUT_DB_KEY"] = "test-key-12345678901234567890123456789012"

    # Import engine after setting env var
    from walnut.database.engine import engine

    with engine.connect() as conn:
        pass

except TypeError as e:
    print("TypeError:", e)
    traceback.print_exc()
    # Sanity: check that the patched method is in place
    print("create_function:", engine.raw_connection().connection.create_function)
    sys.exit(1)
except Exception as e:
    print(f"An error occurred: {e}")
    traceback.print_exc()
