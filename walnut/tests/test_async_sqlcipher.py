import asyncio
import os
import tempfile
import pytest
from walnut.database.async_sqlcipher import AsyncSQLCipherConnection

@pytest.mark.asyncio
async def test_async_sqlcipher_connection():
    # Use a temporary file for the database
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        key = "testkey"
        conn = AsyncSQLCipherConnection(db_path, key)
        await conn.connect()
        # Create a table
        await conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        # Insert a row
        await conn.execute("INSERT INTO test (value) VALUES (?)", ("hello",))
        # Query the row
        cursor = await conn.execute("SELECT * FROM test")
        rows = await conn.fetchall(cursor)
        assert len(rows) == 1
        assert rows[0][1] == "hello"
        await conn.commit()
        # Clean up
        await conn.execute("DROP TABLE test")
        await conn.commit()
