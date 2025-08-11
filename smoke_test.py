import os
from sqlalchemy import create_engine, text

print("Starting smoke test...")

try:
    # Set environment variables
    os.environ["WALNUT_DB_KEY"] = "test-key-12345678901234567890123456789012"

    # Import engine after setting env var
    from walnut.database.engine import engine

    with engine.connect() as conn:
        print("Connection successful.")
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS sanity (id INTEGER PRIMARY KEY, v TEXT)")
        print("Table created.")
        conn.exec_driver_sql("INSERT INTO sanity (v) VALUES ('ok')")
        print("Data inserted.")
        rows = conn.exec_driver_sql("SELECT v FROM sanity").fetchall()
        print(f"Rows: {rows}")
        assert rows == [('ok',)]
        print("Smoke test passed!")

except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
