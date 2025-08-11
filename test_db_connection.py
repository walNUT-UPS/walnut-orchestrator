import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

print("Starting database connection test...")

try:
    DB_PATH = "data/test.db"
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    KEY = "test-key-12345678901234567890123456789012"

    print(f"Database path: {DB_PATH}")
    print(f"Key: {KEY}")

    db_url = f"sqlite+pysqlcipher://:{KEY}@/{DB_PATH}"
    print(f"Database URL: {db_url}")

    print("Creating engine...")
    engine = create_engine(db_url)
    print("Engine created.")

    print("Creating session...")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    print("Session created.")

    print("Querying database...")
    result = session.execute(text("SELECT 1"))
    print("Query executed.")

    print(f"Result: {result.scalar()}")

    session.close()
    print("Session closed.")

    print("Test successful!")

except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
