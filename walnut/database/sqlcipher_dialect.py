from sqlalchemy.dialects.sqlite import pysqlite

from urllib.parse import parse_qs

class SQLCipherDialect(pysqlite.SQLiteDialect_pysqlite):
    name = "sqlcipher"
    
    # Disable REGEXP function support to avoid create_function issues
    supports_regexp = False
    
    # Enable statement caching for better performance
    supports_statement_cache = True

    @classmethod
    def dbapi(cls):
        from pysqlcipher3 import dbapi2
        return dbapi2

    def initialize(self, connection):
        super().initialize(connection)
        # Ensure regexp is disabled after initialization too
        self.supports_regexp = False

    def on_connect(self):
        # Override the parent's on_connect to prevent REGEXP setup
        def connect(dbapi_connection, connection_record=None):
            # Don't call the parent's connect method which sets up REGEXP
            # Just run our custom initialization
            pass
        return connect

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
