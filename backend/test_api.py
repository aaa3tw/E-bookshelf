from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
books = client.get('/api/books').json()
for b in books:
    if b['bookmarks_count'] > 0:
        b_id = b['id']
        print(f"Testing book: {b['title']}")
        resp = client.get(f"/api/bookmarks/export-markdown/{b_id}")
        print("=== Exported Markdown Content ===")
        print(resp.text)
