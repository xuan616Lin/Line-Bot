# db.py
import os
from urllib.parse import urlparse
import pg8000.native

DATABASE_URL = os.getenv("DATABASE_URL")
url = urlparse(DATABASE_URL)

def get_conn():
    return pg8000.native.Connection(
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
        database=url.path.lstrip("/"),
        ssl=True  # 如果你的 URL 帶 ?sslmode=require
    )
# 其餘 CRUD 同樣改用這個 get_conn()
