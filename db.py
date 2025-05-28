import os
from urllib.parse import urlparse
import pg8000
from dotenv import load_dotenv
load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
url = urlparse(DATABASE_URL)

def get_conn():
    return pg8000.connect(
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
        database=url.path.lstrip("/")
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # 建立三張表格
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
      user_id TEXT NOT NULL,
      topic   TEXT NOT NULL,
      PRIMARY KEY(user_id, topic)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS push_topics (
      user_id    TEXT NOT NULL,
      topic      TEXT NOT NULL,
      is_enabled BOOLEAN NOT NULL,
      PRIMARY KEY(user_id, topic)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS push_schedule (
      user_id   TEXT PRIMARY KEY,
      push_time TEXT NOT NULL
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

def list_subscriptions(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT topic FROM subscriptions WHERE user_id=%s", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

def add_subscription(user_id, topic):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
      "INSERT INTO subscriptions(user_id, topic) VALUES(%s, %s) ON CONFLICT DO NOTHING",
      (user_id, topic)
    )
    conn.commit()
    cur.close()
    conn.close()

def remove_subscription(user_id, topic):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
      "DELETE FROM subscriptions WHERE user_id=%s AND topic=%s",
      (user_id, topic)
    )
    conn.commit()
    cur.close()
    conn.close()

def list_push_topics(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
      "SELECT topic, is_enabled FROM push_topics WHERE user_id=%s",
      (user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r[0]: r[1] for r in rows}

def set_push_choice(user_id, topic, choice: bool):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO push_topics(user_id, topic, is_enabled)
      VALUES(%s, %s, %s)
      ON CONFLICT(user_id, topic) DO UPDATE SET is_enabled=EXCLUDED.is_enabled
    """, (user_id, topic, choice))
    conn.commit()
    cur.close()
    conn.close()

def set_push_time(user_id, push_time: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO push_schedule(user_id, push_time)
      VALUES(%s, %s)
      ON CONFLICT(user_id) DO UPDATE SET push_time=EXCLUDED.push_time
    """, (user_id, push_time))
    conn.commit()
    cur.close()
    conn.close()

def get_push_time(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT push_time FROM push_schedule WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def list_push_schedule():
    """
    從資料庫撈出所有使用者的推播時間設定，
    回傳格式為 dict: { user_id: push_time, ... }
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, push_time FROM push_schedule")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    # 把 list of tuples 轉成 dict
    return {user_id: push_time for user_id, push_time in rows}
