from sqlalchemy.dialects.sqlite import pysqlite

from urllib.parse import parse_qs

class SQLCipherDialect(pysqlite.SQLiteDialect_pysqlite):
    name = "sqlcipher"

    @classmethod
    def dbapi(cls):
        from pysqlcipher3 import dbapi2
        return dbapi2

    def initialize(self, connection):
        super().initialize(connection)
        self.supports_regexp = False

    def create_connect_args(self, url):
        opts = url.translate_connect_args()
        opts.update(url.query)
        return [], opts

    def connect(self, *cargs, **cparams):
        key = cparams.pop("key", None)
        conn = super().connect(*cargs, **cparams)
        if key:
            escaped_key = key.replace("'", "''")
            conn.execute(f"PRAGMA key = '{escaped_key}'")
        return conn
