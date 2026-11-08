import main
import database
import json

main.scan_existing_books()

with database.get_db() as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, file_type FROM books')
    books = cursor.fetchall()
    print('Current books in DB:')
    for b in books:
        print(f" - [{b['file_type']}] {b['title']} (id={b['id']})")
        
    for b in books:
        if b['file_type'] == 'pdf':
            b_id = b['id']
            cursor.execute('''
            INSERT OR IGNORE INTO bookmarks (id, book_id, location, title, category, color, tags, quote, note, created_at, updated_at)
            VALUES 
            ('bm_demo_1', ?, '1', '系統核心功能總覽', '重要核心', 'red', '["核心", "架構"]', '本系統專為深度閱讀、研究筆記與文件編輯設計。', '第一章的核心總結，非常清晰。', datetime('now'), datetime('now')),
            ('bm_demo_2', ?, '2', '五大多重書籤色彩規範', '待複習考點', 'yellow', '["色彩規範", "多重書籤"]', '紅/黃/綠/藍/紫 5 色分類', '記得按照顏色整理我的讀書卡片！', datetime('now'), datetime('now')),
            ('bm_demo_3', ?, '3', '筆記一鍵匯出 Markdown', '精選引用', 'green', '["匯出", "Markdown"]', '直接生成 Markdown 格式的完整讀書筆記！', '這個功能超級實用，能直接丟到 Obsidian 或 Notion！', datetime('now'), datetime('now'))
            ''', (b_id, b_id, b_id))
            break
    conn.commit()
    print('Sample multi-bookmarks added successfully!')

