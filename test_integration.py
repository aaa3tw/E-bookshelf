import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_endpoints():
    print("1. 測試 /api/crawler/sites...")
    res = client.get("/api/crawler/sites")
    assert res.status_code == 200, res.text
    print(f"   ✓ 支援站點數: {len(res.json())}")

    print("\n2. 測試 /api/crawler/sync-bookshelf...")
    res = client.post("/api/crawler/sync-bookshelf")
    assert res.status_code == 200, res.text
    sync_data = res.json()["data"]
    print(f"   ✓ 書庫同步成功: 總追更 {sync_data['total_tracked']} 本, 書櫃藏書 {sync_data['total_shelf']} 本")

    print("\n3. 測試 /api/crawler/tracked (追更書架)...")
    res = client.get("/api/crawler/tracked")
    assert res.status_code == 200, res.text
    tracked = res.json()
    print(f"   ✓ 追更書籍數: {len(tracked)}")

    print("\n4. 測試書櫃書籍 /api/books...")
    res = client.get("/api/books")
    assert res.status_code == 200, res.text
    books = res.json()
    print(f"   ✓ 書櫃藏書總數: {len(books)}")

    print("\n5. 測試愛下電子書 (ixdzs.tw) 解析範例: https://ixdzs.tw/read/643431/#a-list ...")
    res = client.post("/api/crawler/parse", json={"url": "https://ixdzs.tw/read/643431/#a-list"})
    assert res.status_code == 200, res.text
    parsed = res.json()
    print(f"   ✓ 書名: {parsed['title']}")
    print(f"   ✓ 作者: {parsed['author']}")
    print(f"   ✓ 總章節數: {parsed['total_chapters']}")
    print(f"   ✓ 最新章節: {parsed['latest_chapter']}")
    assert parsed['total_chapters'] > 0, "未解析到章節"

    print("\n6. 測試愛下電子書探索排行榜 /api/crawler/explore?site=ixdzs&category=xuanhuan ...")
    res = client.get("/api/crawler/explore?site=ixdzs&category=xuanhuan")
    assert res.status_code == 200, res.text
    explore_list = res.json()
    print(f"   ✓ 取得排行榜書籍數: {len(explore_list)}")
    if explore_list:
        print(f"   ✓ 榜首 TOP 1: {explore_list[0]['title']} ({explore_list[0]['author']})")

    print("\n🎉 所有端點測試 100% 通過！")

if __name__ == "__main__":
    test_endpoints()
