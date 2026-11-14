import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime

try:
    from app_paths import DB_PATH, DATA_DIR
except ImportError:
    try:
        from .app_paths import DB_PATH, DATA_DIR
    except ImportError:
        DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bookshelf.db"
        DATA_DIR = DB_PATH.parent

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 書籍表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT DEFAULT '未知作者',
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            cover_image TEXT DEFAULT '',
            total_pages INTEGER DEFAULT 1,
            current_progress REAL DEFAULT 0.0,
            last_location TEXT DEFAULT '1',
            category TEXT DEFAULT '預設書架',
            tags TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        ''')
        
        # 多重書籤表 (支援多色標、多分類、多標籤、引文摘錄、筆記)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookmarks (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL,
            location TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT DEFAULT '重要核心',
            color TEXT DEFAULT 'red',
            tags TEXT DEFAULT '[]',
            quote TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        ''')
        
        # 註解/編輯標記表 (仿 Acrobat 高亮、畫線、便籤、繪圖、文字方塊)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS annotations (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL,
            page_index INTEGER DEFAULT 0,
            type TEXT NOT NULL,
            color TEXT DEFAULT '#ffff00',
            data_json TEXT NOT NULL,
            text_content TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
        )
        ''')

        # 使用者與全域設定表 (字體大小、字型、字重、主題等偏好記憶)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        ''')
        
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)

