import sys
import os
from pathlib import Path

def get_app_dir() -> Path:
    """取得應用程式的根目錄（供持久化資料儲存：data/）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent.parent

def get_bundle_dir() -> Path:
    """取得靜態資源/代碼所在目錄（frontend、模板等）"""
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "frontend").exists():
            return exe_dir
        if (exe_dir / "_internal" / "frontend").exists():
            return exe_dir / "_internal"
        return exe_dir
    else:
        return Path(__file__).resolve().parent.parent

APP_DIR = get_app_dir()
BUNDLE_DIR = get_bundle_dir()

# 持久化資料夾（隨執行檔攜帶，升級時只要保留 data/ 資料庫與書本就不會遺失）
DATA_DIR = APP_DIR / "data"
BOOKS_DIR = DATA_DIR / "books"
COVERS_DIR = DATA_DIR / "covers"
THUMBS_DIR = DATA_DIR / "thumbnails"
CACHE_DIR = DATA_DIR / ".novel_cache"
DB_PATH = DATA_DIR / "bookshelf.db"
TRACKED_FILE = DATA_DIR / "tracked_novels.json"
ZLIB_CONFIG_FILE = DATA_DIR / "zlib_config.json"

# 前端靜態檔案
FRONTEND_DIR = BUNDLE_DIR / "frontend"
if not FRONTEND_DIR.exists() and (APP_DIR / "frontend").exists():
    FRONTEND_DIR = APP_DIR / "frontend"

BASE_DIR = APP_DIR

# 確保必要資料夾自動建立
for folder in [DATA_DIR, BOOKS_DIR, COVERS_DIR, THUMBS_DIR, CACHE_DIR]:
    folder.mkdir(parents=True, exist_ok=True)
