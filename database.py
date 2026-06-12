# database.py
import sqlite3
from pathlib import Path

DB_PATH = Path("user_data.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            default_mode TEXT DEFAULT 'album'
        )
    ''')
    conn.commit()
    conn.close()

def get_user_mode(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT default_mode FROM user_settings WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else "album"

def set_user_mode(user_id: int, mode: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO user_settings (user_id, default_mode) 
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET default_mode = excluded.default_mode
    ''', (user_id, mode))
    conn.commit()
    conn.close()

# وقتی برنامه شروع میشه، دیتابیس ساخته میشه
init_db()
