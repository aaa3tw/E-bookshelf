import os
import sys
import time
import subprocess
import webbrowser
import threading
import multiprocessing
from pathlib import Path

# 強制設定 Windows 控制台輸出為 UTF-8 (以避免 CP950 / Big5 繁體中文環境報錯閃退)
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Windows PyInstaller multiprocessing 支援
multiprocessing.freeze_support()

# 設定工作路徑
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    APP_DIR = Path(sys.executable).resolve().parent
    BACKEND_DIR = BASE_DIR / "backend"
    if not BACKEND_DIR.exists():
        BACKEND_DIR = BASE_DIR
else:
    BASE_DIR = Path(__file__).resolve().parent
    APP_DIR = BASE_DIR
    BACKEND_DIR = BASE_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.chdir(APP_DIR)

def launch_desktop_window(url: str):
    """
    優先以 Windows 原生 Edge 獨立應用程式視窗模式 (--app) 開啟，
    呈現純粹無網址列、無分頁標籤的專業桌面應用程式體驗；
    若環境無 Edge，自動備援使用系統預設瀏覽器。
    """
    time.sleep(1.2)
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    edge_exe = None
    for p in edge_paths:
        if os.path.exists(p):
            edge_exe = p
            break

    if edge_exe:
        try:
            print("  [+] 正在以獨立應用程式視窗啟動電子書櫃...")
            subprocess.Popen([
                edge_exe,
                f"--app={url}",
                "--window-size=1360,900"
            ])
            return
        except Exception as e:
            print(f"  [!] Edge 視窗模式啟動提示: {e}")

    # 備援：以預設瀏覽器開啟
    print(f"  [+] 正在以預設瀏覽器開啟：{url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass


def check_existing_bookshelf(port=8765) -> bool:
    """檢查指定端口是否已經有執行中的電子書櫃服務"""
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/books", headers={'User-Agent': 'AcrobatLauncher'})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False

def find_available_port(start_port=8765) -> int:
    """尋找可用端口"""
    import socket
    for p in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return start_port


def main():
    print("=" * 64)
    print("  [Acrobat Bookshelf] 電子書櫃與專業閱讀系統 (免安裝可攜版)")
    print("=" * 64)

    # 檢查是否已在運行
    if check_existing_bookshelf(8765):
        print("  [*] 偵測到電子書櫃伺服器已在背景運行中！")
        print("  [*] 正在為您直接開啟應用程式視窗...")
        launch_desktop_window("http://127.0.0.1:8765")
        time.sleep(1.5)
        print("  [+] 視窗已開啟。")
        return

    print("[1/3] 正在載入核心模組與書庫資料庫...")

    try:
        from app_paths import DATA_DIR, FRONTEND_DIR, DB_PATH
        from database import init_db
        init_db()
        print(f"  [+] 資料庫初始化完成: {DB_PATH}")
    except Exception as e:
        print(f"  [-] 資料庫初始化失敗: {e}")
        input("\n按 Enter 鍵結束...")
        return

    try:
        from crawler.service import crawler_service
        crawler_service.sync_with_bookshelf()
        print("  [+] 書櫃與追更模組就緒")
    except Exception as e:
        print(f"  [!] 自動同步書庫提示: {e}")

    print("[2/3] 正在載入後端 Web 服務...")
    try:
        from main import app
        print("  [+] 後端應用程式載入成功")
    except Exception as e:
        print(f"  [-] 載入應用程式失敗: {e}")
        input("\n按 Enter 鍵結束...")
        return

    port = find_available_port(8765)
    url = f"http://127.0.0.1:{port}"
    print(f"[3/3] 正在啟動本機伺服器：{url} ...")

    # 啟動非同步視窗守護線程
    threading.Thread(target=launch_desktop_window, args=(url,), daemon=True).start()

    print("=" * 64)
    print("  * 電子書櫃已就緒！")
    print(f"  * 本機訪問位址: {url}")
    print("  * 提示：保持此視窗開啟即可持續使用書櫃，按 Ctrl+C 可關閉程式。")
    print("=" * 64)

    # 啟動 uvicorn (直接傳入 app 物件以相容 PyInstaller 打包環境)
    import uvicorn
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        print("\n伺服器已正常關閉。")


if __name__ == "__main__":
    main()
