import os
import sys
import time
import webbrowser
import threading
from pathlib import Path

# 將 backend 目錄加入 sys.path
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)

def main():
    print("=" * 60)
    print("  Acrobat Bookshelf - 電子書櫃與專業閱讀編輯系統")
    print("=" * 60)
    print("[1/2] 正在檢查與初始化資料庫與書庫...")
    
    # 匯入後端模組
    try:
        from database import init_db
        init_db()
        print("  ✓ 資料庫初始化完成")
    except Exception as e:
        print(f"  ✕ 資料庫初始化失敗: {e}")
        return

    try:
        from crawler.service import crawler_service
        crawler_service.sync_with_bookshelf()
        print("  ✓ 書櫃與小說追更資料庫雙向同步完成")
    except Exception as e:
        print(f"  ! 自動同步書庫提示: {e}")

    try:
        from main import app
        print("  ✓ 後端應用程式載入成功")
    except Exception as e:
        print(f"  ✕ 載入應用程式失敗: {e}")
        return

    port = 8765
    url = f"http://127.0.0.1:{port}"
    print(f"[2/2] 正在啟動伺服器：{url} ...")
    
    # 自動在 1.5 秒後開啟瀏覽器
    def open_browser():
        time.sleep(1.5)
        print(f"  ✓ 自動在瀏覽器中開啟：{url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    # 啟動 Uvicorn
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

if __name__ == "__main__":
    main()
