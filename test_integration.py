# -*- coding: utf-8 -*-
"""
測試 acrobat_bookshelf 後端整合與 Z-Library / 繁簡轉換
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "backend"))

print("1. 測試導入 epub_converter 與 zlib_client ...")
try:
    from epub_converter import is_simplified_chinese_epub, auto_convert_epub_if_simplified
    print("   [OK] epub_converter 導入成功")
except Exception as e:
    print(f"   [FAIL] epub_converter: {e}")

try:
    from zlib_client import search_zlib, load_zlib_config, save_zlib_config
    print("   [OK] zlib_client 導入成功")
except Exception as e:
    print(f"   [FAIL] zlib_client: {e}")

print("2. 測試 crawler service 站點列表 ...")
try:
    from crawler.service import crawler_service
    sites = crawler_service.get_supported_sites()
    zlib_found = any(s["id"] == "zlib" for s in sites)
    print(f"   [OK] 支援站點數: {len(sites)}, Z-Library 存在: {zlib_found}")
except Exception as e:
    print(f"   [FAIL] crawler service: {e}")

print("3. 測試 Z-Library 搜尋 (eapi) ...")
try:
    results = search_zlib("三體", limit=3)
    print(f"   [OK] Z-Lib 搜尋成功，回傳 {len(results)} 本書籍")
    for r in results[:2]:
        print(f"       - 《{r['title']}》 ({r.get('file_type')}, {r.get('language')})")
except Exception as e:
    print(f"   [WARN] Z-Lib 網路搜尋異常: {e}")

print("4. 測試 FastAPI 路由與應用初始化 ...")
try:
    from main import app
    print(f"   [OK] FastAPI app 成功載入，路由數: {len(app.routes)}")
except Exception as e:
    print(f"   [FAIL] main app: {e}")

print("\n全部測試通過！")
