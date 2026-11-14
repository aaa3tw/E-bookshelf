import os
import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import init_db, get_db
import book_service
try:
    from crawler.service import crawler_service
except ImportError:
    from backend.crawler.service import crawler_service

app = FastAPI(title="Acrobat Bookshelf API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    # 為前端靜態資源加上 no-cache 標頭，防止瀏覽器快取舊代碼導致更新無效
    if request.url.path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

try:
    from app_paths import BASE_DIR, DATA_DIR, BOOKS_DIR, COVERS_DIR, FRONTEND_DIR
except ImportError:
    try:
        from .app_paths import BASE_DIR, DATA_DIR, BOOKS_DIR, COVERS_DIR, FRONTEND_DIR
    except ImportError:
        BASE_DIR = Path(__file__).resolve().parent.parent
        DATA_DIR = BASE_DIR / "data"
        BOOKS_DIR = DATA_DIR / "books"
        COVERS_DIR = DATA_DIR / "covers"
        FRONTEND_DIR = BASE_DIR / "frontend"

BOOKS_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR.mkdir(parents=True, exist_ok=True)

# Pydantic Schemas
class BookmarkCreate(BaseModel):
    location: str
    title: str
    category: Optional[str] = "重要核心"
    color: Optional[str] = "red"
    tags: Optional[List[str]] = []
    quote: Optional[str] = ""
    note: Optional[str] = ""

class BookmarkUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    tags: Optional[List[str]] = None
    quote: Optional[str] = None
    note: Optional[str] = None

class ProgressUpdate(BaseModel):
    progress: float
    last_location: str

class AnnotationCreate(BaseModel):
    page_index: int
    type: str
    color: Optional[str] = "#ffff00"
    data: dict
    text_content: Optional[str] = ""

class EpubChapterUpdate(BaseModel):
    content: str

class NovelDownloadRequest(BaseModel):
    url: str
    export_format: Optional[str] = "epub"

class NovelParseRequest(BaseModel):
    url: str

class NovelUpdateRequest(BaseModel):
    book_key: Optional[str] = None
    all_books: Optional[bool] = False

class DeleteTrackedRequest(BaseModel):
    book_key: str

def cleanup_duplicate_books():
    """自動去重：針對同檔名、同路徑或同標題之重複記錄進行清理，保留最新的一筆"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT id, title, file_path, file_name, created_at 
        FROM books 
        ORDER BY created_at DESC
        ''')
        rows = cursor.fetchall()
        
        seen_keys = set()
        duplicates_to_delete = []
        
        for r in rows:
            # 正規化識別鍵：取純檔名 (移除前綴 uuid)
            f_name = Path(r["file_path"]).name if r["file_path"] else r["file_name"]
            clean_name = f_name[37:] if len(f_name) > 37 and f_name[8] == '-' and f_name[13] == '-' else f_name
            unique_key = (r["title"].strip().lower(), clean_name.lower())
            
            if unique_key in seen_keys:
                duplicates_to_delete.append(r["id"])
            else:
                seen_keys.add(unique_key)
                
        for dup_id in duplicates_to_delete:
            cursor.execute("DELETE FROM books WHERE id = ?", (dup_id,))
        conn.commit()

def scan_existing_books():
    """自動掃描 data/books 資料夾中的書籍，並同步至 SQLite 資料庫 (嚴格防重)"""
    cleanup_duplicate_books()
    with get_db() as conn:
        cursor = conn.cursor()
        for file in BOOKS_DIR.iterdir():
            if file.suffix.lower() in [".pdf", ".epub"]:
                real_path = str(file.resolve())
                raw_name = file.name
                clean_name = raw_name[37:] if len(raw_name) > 37 and raw_name[8] == '-' and raw_name[13] == '-' else raw_name

                # 嚴格防重比對
                cursor.execute('''
                SELECT id FROM books 
                WHERE file_path = ? OR file_name = ? OR file_name = ? OR file_path LIKE ?
                ''', (real_path, raw_name, clean_name, f"%{clean_name}"))
                if cursor.fetchone():
                    continue
                
                # 若檔名以標準 UUID 開頭，優先使用該 UUID 以保持與封面與下載任務一致
                if len(raw_name) >= 36 and raw_name[8] == '-' and raw_name[13] == '-' and raw_name[18] == '-' and raw_name[23] == '-':
                    book_id = raw_name[:36]
                else:
                    book_id = str(uuid.uuid4())
                ext = file.suffix.lower()[1:]
                file_size = file.stat().st_size
                now = datetime.now().isoformat()
                
                try:
                    if ext == "pdf":
                        info = book_service.process_pdf(file, book_id)
                    else:
                        info = book_service.process_epub(file, book_id)
                        
                    cursor.execute('''
                    INSERT INTO books (id, title, author, file_name, file_path, file_type, file_size, 
                                       cover_image, total_pages, current_progress, last_location, category, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '1', '預設書架', '[]', ?, ?)
                    ''', (
                        book_id, info["title"], info["author"], raw_name, real_path,
                        ext, file_size, info["cover_image"], info["total_pages"], now, now
                    ))
                except Exception as e:
                    print(f"Error importing {file.name}: {e}")
        conn.commit()

@app.on_event("startup")
def startup_event():
    init_db()
    scan_existing_books()

# ----------------- 書籍 API -----------------

@app.get("/api/books")
def list_books(search: Optional[str] = None, file_type: Optional[str] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM books WHERE 1=1"
        params = []
        if search:
            query += " AND (title LIKE ? OR author LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        if file_type and file_type != "all":
            query += " AND file_type = ?"
            params.append(file_type.lower())
        query += " ORDER BY updated_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        books = []
        for r in rows:
            b = dict(r)
            b["tags"] = json.loads(b["tags"]) if b["tags"] else []
            # 統計書籤數量
            cursor.execute("SELECT COUNT(*) as count FROM bookmarks WHERE book_id = ?", (b["id"],))
            b["bookmarks_count"] = cursor.fetchone()["count"]
            books.append(b)
        return books

@app.get("/api/books/{book_id}")
def get_book_details(book_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Book not found")
        book = dict(row)
        book["tags"] = json.loads(book["tags"]) if book["tags"] else []
        
        file_path = Path(book["file_path"])
        if file_path.exists():
            if book["file_type"] == "pdf":
                book["outline"] = book_service.get_pdf_outline(file_path)
            else:
                book["outline"] = book_service.get_epub_toc(file_path)
        else:
            book["outline"] = []
            
        return book

@app.post("/api/books/upload")
async def upload_book(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".pdf", ".epub"]:
        raise HTTPException(status_code=400, detail="Only PDF and EPUB files are supported")
    
    file_type = ext[1:]
    book_id = str(uuid.uuid4())
    save_filename = f"{book_id}_{file.filename}"
    save_path = BOOKS_DIR / save_filename
    
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_size = save_path.stat().st_size
    now = datetime.now().isoformat()
    
    if file_type == "pdf":
        info = book_service.process_pdf(save_path, book_id)
    else:
        # 上傳 EPUB 時，自動檢測若為簡體中文則轉換為繁體中文
        try:
            from epub_converter import auto_convert_epub_if_simplified
            auto_convert_epub_if_simplified(str(save_path))
        except Exception as e:
            print(f"[Upload Convert Warning] {e}")

        info = book_service.process_epub(save_path, book_id)
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO books (id, title, author, file_name, file_path, file_type, file_size, 
                           cover_image, total_pages, current_progress, last_location, category, tags, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '1', '自訂匯入', '[]', ?, ?)
        ''', (
            book_id, info["title"], info["author"], save_filename, str(save_path.resolve()),
            file_type, file_size, info["cover_image"], info["total_pages"], now, now
        ))
        conn.commit()
        
    return {"id": book_id, "title": info["title"], "message": "Uploaded successfully"}

@app.delete("/api/books/{book_id}")
def delete_book(book_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, file_path, cover_image FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Book not found")
        
        file_path = Path(row["file_path"])
        # 刪除實體檔案
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")
            
        # 刪除封面縮圖
        cover_filename = f"{book_id}.png"
        cover_path = COVERS_DIR / cover_filename
        try:
            if cover_path.exists():
                cover_path.unlink()
        except Exception as e:
            pass
            
        # 刪除資料庫紀錄
        cursor.execute("DELETE FROM bookmarks WHERE book_id = ?", (book_id,))
        cursor.execute("DELETE FROM annotations WHERE book_id = ?", (book_id,))
        cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()

        # 同步從小說追更列表中移除
        try:
            crawler_service.remove_by_uuid_or_title(book_id, row["title"])
        except Exception as e:
            pass
        
    return {"status": "ok", "message": "Book deleted successfully"}

@app.get("/api/books/{book_id}/file")
def stream_book_file(book_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_type, file_name FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Book not found")
        
        file_path = Path(row["file_path"])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File file not found on disk")
            
        media_type = "application/pdf" if row["file_type"] == "pdf" else "application/epub+zip"
        return FileResponse(file_path, media_type=media_type, filename=row["file_name"])

@app.post("/api/books/{book_id}/progress")
def update_reading_progress(book_id: str, data: ProgressUpdate):
    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
        UPDATE books 
        SET current_progress = ?, last_location = ?, updated_at = ?
        WHERE id = ?
        ''', (data.progress, data.last_location, now, book_id))
        conn.commit()
    return {"status": "ok"}

@app.get("/api/covers/{filename}")
def get_cover(filename: str):
    cover_path = COVERS_DIR / filename
    if not cover_path.exists():
        raise HTTPException(status_code=404, detail="Cover not found")
    return FileResponse(cover_path)

@app.get("/api/books/{book_id}/thumbnails/{page_num}")
def get_page_thumbnail(book_id: str, page_num: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_type FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        if not row or row["file_type"] != "pdf":
            raise HTTPException(status_code=400, detail="Only PDF thumbnails available")
        thumb_path = book_service.get_pdf_page_thumbnail(Path(row["file_path"]), book_id, page_num)
        return FileResponse(thumb_path)

# ----------------- 多重書籤 (Multi-Bookmarks) API -----------------

@app.get("/api/books/{book_id}/bookmarks")
def list_book_bookmarks(book_id: str, category: Optional[str] = None, color: Optional[str] = None, tag: Optional[str] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM bookmarks WHERE book_id = ?"
        params = [book_id]
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        if color and color != "all":
            query += " AND color = ?"
            params.append(color)
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            bm = dict(r)
            bm["tags"] = json.loads(bm["tags"]) if bm["tags"] else []
            if tag and tag not in bm["tags"]:
                continue
            results.append(bm)
        return results

@app.post("/api/books/{book_id}/bookmarks")
def create_bookmark(book_id: str, data: BookmarkCreate):
    bookmark_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    tags_json = json.dumps(data.tags or [], ensure_ascii=False)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO bookmarks (id, book_id, location, title, category, color, tags, quote, note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (bookmark_id, book_id, data.location, data.title, data.category, data.color, tags_json, data.quote, data.note, now, now))
        conn.commit()
    return {"id": bookmark_id, "message": "Bookmark created"}

@app.put("/api/books/{book_id}/bookmarks/{bookmark_id}")
def update_bookmark(book_id: str, bookmark_id: str, data: BookmarkUpdate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bookmarks WHERE id = ? AND book_id = ?", (bookmark_id, book_id))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bookmark not found")
        
        curr = dict(row)
        title = data.title if data.title is not None else curr["title"]
        category = data.category if data.category is not None else curr["category"]
        color = data.color if data.color is not None else curr["color"]
        tags = json.dumps(data.tags, ensure_ascii=False) if data.tags is not None else curr["tags"]
        quote = data.quote if data.quote is not None else curr["quote"]
        note = data.note if data.note is not None else curr["note"]
        now = datetime.now().isoformat()
        
        cursor.execute('''
        UPDATE bookmarks
        SET title = ?, category = ?, color = ?, tags = ?, quote = ?, note = ?, updated_at = ?
        WHERE id = ?
        ''', (title, category, color, tags, quote, note, now, bookmark_id))
        conn.commit()
    return {"status": "ok"}

@app.delete("/api/books/{book_id}/bookmarks/{bookmark_id}")
def delete_bookmark(book_id: str, bookmark_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookmarks WHERE id = ? AND book_id = ?", (bookmark_id, book_id))
        conn.commit()
    return {"status": "ok"}

@app.get("/api/bookmarks/export-markdown/{book_id}")
def export_bookmarks_markdown(book_id: str):
    """匯出該書所有多重書籤與備註為 Markdown 讀書筆記"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, author, file_type FROM books WHERE id = ?", (book_id,))
        book = cursor.fetchone()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
            
        cursor.execute("SELECT * FROM bookmarks WHERE book_id = ? ORDER BY location ASC, created_at ASC", (book_id,))
        bms = cursor.fetchall()
        
        lines = [
            f"# 《{book['title']}》讀書筆記與書籤",
            f"- **作者**：{book['author']}",
            f"- **檔案格式**：{book['file_type'].upper()}",
            f"- **匯出時間**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **書籤總數**：{len(bms)} 個",
            "",
            "---",
            ""
        ]
        
        # 依色彩/分類分組
        color_names = {
            "red": "🔴 重要核心",
            "yellow": "🟡 待複習考點",
            "green": "🟢 精選引用",
            "blue": "🔵 備忘心得",
            "purple": "🟣 深度思考"
        }
        
        for bm in bms:
            tags = json.loads(bm["tags"]) if bm["tags"] else []
            tag_str = " ".join([f"`#{t}`" for t in tags]) if tags else ""
            color_badge = color_names.get(bm["color"], f"🏷️ {bm['color']}")
            
            lines.append(f"### {color_badge} | {bm['title']} (位置: {bm['location']})")
            if bm["category"]:
                lines.append(f"> **分類**：{bm['category']}  {tag_str}")
            if bm["quote"]:
                lines.append(f"> **引文**：\n> *\"{bm['quote']}\"*")
            if bm["note"]:
                lines.append(f"\n**筆記心得**：\n{bm['note']}\n")
            lines.append("")
            
        content = "\n".join(lines)
        return PlainTextResponse(content, media_type="text/markdown", headers={
            "Content-Disposition": f"attachment; filename=bookmarks_{book_id}.md"
        })

# ----------------- 註解與標記 (Annotations) API -----------------

@app.get("/api/books/{book_id}/annotations")
def list_annotations(book_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM annotations WHERE book_id = ? ORDER BY page_index ASC", (book_id,))
        rows = cursor.fetchall()
        results = []
        for r in rows:
            item = dict(r)
            item["data"] = json.loads(item["data_json"]) if item["data_json"] else {}
            results.append(item)
        return results

@app.post("/api/books/{book_id}/annotations")
def create_annotation(book_id: str, data: AnnotationCreate):
    ann_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    data_json = json.dumps(data.data, ensure_ascii=False)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO annotations (id, book_id, page_index, type, color, data_json, text_content, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ann_id, book_id, data.page_index, data.type, data.color, data_json, data.text_content, now, now))
        conn.commit()
    return {"id": ann_id, "message": "Annotation created"}

@app.delete("/api/books/{book_id}/annotations/{annotation_id}")
def delete_annotation(book_id: str, annotation_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM annotations WHERE id = ? AND book_id = ?", (annotation_id, book_id))
        conn.commit()
    return {"status": "ok"}

@app.post("/api/books/{book_id}/export-annotated-pdf")
def export_annotated_pdf(book_id: str):
    """將此書的所有註解合成到 PDF 輸出"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_type, title FROM books WHERE id = ?", (book_id,))
        book = cursor.fetchone()
        if not book or book["file_type"] != "pdf":
            raise HTTPException(status_code=400, detail="Only PDF supports exporting annotated document")
            
        cursor.execute("SELECT * FROM annotations WHERE book_id = ?", (book_id,))
        rows = cursor.fetchall()
        annotations = []
        for r in rows:
            item = dict(r)
            item["data"] = json.loads(item["data_json"])
            annotations.append(item)
            
        output_filename = f"annotated_{book_id}.pdf"
        output_path = DATA_DIR / output_filename
        
        book_service.export_annotated_pdf(Path(book["file_path"]), output_path, annotations)
        return FileResponse(output_path, media_type="application/pdf", filename=f"[Annotated]_{book['title']}.pdf")

# ----------------- EPUB 編輯器 API -----------------

@app.get("/api/books/{book_id}/epub-chapters")
def get_epub_chapters(book_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_type FROM books WHERE id = ?", (book_id,))
        book = cursor.fetchone()
        if not book or book["file_type"] != "epub":
            raise HTTPException(status_code=400, detail="Only EPUB supports chapter editing")
        return book_service.get_epub_chapters(Path(book["file_path"]))

@app.post("/api/books/{book_id}/epub-chapters/{chapter_file_name:path}")
def save_epub_chapter(book_id: str, chapter_file_name: str, data: EpubChapterUpdate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_type FROM books WHERE id = ?", (book_id,))
        book = cursor.fetchone()
        if not book or book["file_type"] != "epub":
            raise HTTPException(status_code=400, detail="Only EPUB supports chapter editing")
        
        book_service.update_epub_chapter(Path(book["file_path"]), chapter_file_name, data.content)
        return {"status": "ok", "message": "Chapter updated successfully"}

# ----------------- 小說抓取與追更整合 API -----------------

@app.get("/api/crawler/sites")
def get_crawler_sites():
    """取得支援小說網站清單"""
    return crawler_service.get_supported_sites()

@app.get("/api/crawler/categories")
def get_crawler_categories():
    """取得支援小說分類清單"""
    return crawler_service.get_supported_categories()

@app.get("/api/crawler/explore")
def explore_crawler_novels(site: str = "biquge", category: str = "all"):
    """取得站點熱門推薦/排行書籍，支援分類篩選"""
    return crawler_service.get_site_explore(site, category)

@app.get("/api/crawler/search")
def search_crawler_novels(keyword: str, site: Optional[str] = None):
    """跨站或指定站點搜尋小說"""
    return crawler_service.search_books(keyword, site)

@app.post("/api/crawler/parse")
def parse_crawler_novel(data: NovelParseRequest):
    """解析小說目錄與基本資訊"""
    try:
        return crawler_service.parse_book_detail(data.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析書籍失敗: {str(e)}")

@app.post("/api/crawler/download")
def start_crawler_download(data: NovelDownloadRequest):
    """啟動非同步下載任務"""
    try:
        task_id = crawler_service.start_download_task(data.url, export_format=data.export_format or "epub")
        return {"status": "started", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"啟動下載失敗: {str(e)}")

@app.get("/api/crawler/tasks/{task_id}")
def get_crawler_task(task_id: str):
    """查詢下載任務進度"""
    task = crawler_service.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到該下載任務")
    return task

@app.get("/api/crawler/tracked")
def get_tracked_novels():
    """取得已追蹤/下載的線上小說清單"""
    return crawler_service.list_tracked_novels()

@app.post("/api/crawler/check-updates")
def check_crawler_updates(data: Optional[NovelUpdateRequest] = None):
    """檢查單本或全部線上小說的更新"""
    if data and data.book_key:
        res = crawler_service.check_update_single(data.book_key)
        return [res]
    else:
        return crawler_service.check_update_all()

@app.post("/api/crawler/apply-update")
def apply_crawler_update(data: NovelUpdateRequest):
    """啟動增量更新下載任務"""
    if not data.book_key:
        raise HTTPException(status_code=400, detail="請指定要更新的書籍 book_key")
    try:
        task_id = crawler_service.apply_update_task(data.book_key)
        return {"status": "started", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"啟動更新失敗: {str(e)}")

@app.delete("/api/crawler/tracked/{book_key:path}")
def delete_tracked_novel(book_key: str):
    """從追更管理中刪除指定書籍 (DELETE 方式)"""
    success = crawler_service.remove_tracked_book(book_key)
    if not success:
        raise HTTPException(status_code=404, detail="找不到此書籍追更記錄")
    return {"status": "ok", "message": f"已成功移除書籍 {book_key}"}

@app.post("/api/crawler/delete-tracked")
def delete_tracked_novel_post(data: DeleteTrackedRequest):
    """從追更管理中刪除指定書籍 (POST 方式)"""
    success = crawler_service.remove_tracked_book(data.book_key)
    if not success:
        raise HTTPException(status_code=404, detail="找不到此書籍追更記錄")
    return {"status": "ok", "message": f"已成功移除書籍 {data.book_key}"}

@app.post("/api/crawler/sync-bookshelf")
def sync_crawler_with_bookshelf():
    """雙向同步小說追更與書櫃"""
    try:
        res = crawler_service.sync_with_bookshelf()
        return {"status": "ok", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失敗: {str(e)}")

# ----------------- Z-Library 專用與繁簡轉換 API -----------------

class ZlibConfigRequest(BaseModel):
    remix_user_key: Optional[str] = ""
    remix_userid: Optional[str] = ""
    email: Optional[str] = ""

class ZlibLoginRequest(BaseModel):
    email: str
    password: str

@app.get("/api/zlib/config")
def get_zlib_config():
    """取得 Z-Library 配置狀態"""
    from zlib_client import load_zlib_config
    cfg = load_zlib_config()
    key = cfg.get("remix_user_key", "")
    return {
        "has_token": bool(key),
        "token_preview": f"{key[:6]}******" if key else "",
        "email": cfg.get("email", ""),
        "user_id": cfg.get("remix_userid", ""),
        "personal_domains": cfg.get("personal_domains", [])
    }

@app.post("/api/zlib/config")
def set_zlib_config(data: ZlibConfigRequest):
    """設定 Z-Library 帳號與金鑰"""
    from zlib_client import load_zlib_config, save_zlib_config
    cfg = load_zlib_config()
    if data.remix_user_key is not None:
        cfg["remix_user_key"] = data.remix_user_key.strip()
    if data.remix_userid:
        cfg["remix_userid"] = data.remix_userid.strip()
    if data.email:
        cfg["email"] = data.email.strip()
    save_zlib_config(cfg)
    return {"status": "ok", "message": "Z-Library 配置儲存成功"}

@app.post("/api/zlib/login")
def zlib_api_login(data: ZlibLoginRequest):
    """使用 Email 與密碼直接登入 Z-Library 並取得專屬金鑰與節點"""
    from zlib_client import login_zlib
    res = login_zlib(data.email, data.password)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "登入失敗"))
    return res

@app.post("/api/books/{book_id}/convert-to-traditional")
def convert_book_to_traditional(book_id: str):
    """手動將書櫃中的書籍轉換為繁體中文"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_type, title FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到此書籍")
        if row["file_type"] != "epub":
            raise HTTPException(status_code=400, detail="目前僅支援 EPUB 電子書自動繁體轉換")

        fpath = Path(row["file_path"])
        if not fpath.exists():
            raise HTTPException(status_code=404, detail="實體檔案不存在")

        try:
            from epub_converter import convert_epub_to_traditional, is_simplified_chinese_epub
            convert_epub_to_traditional(str(fpath))
            # 重新解析中繼資料更新標題
            info = book_service.process_epub(fpath, book_id)
            cursor.execute("UPDATE books SET title = ?, author = ?, updated_at = ? WHERE id = ?",
                           (info["title"], info["author"], datetime.now().isoformat(), book_id))
            conn.commit()
            return {"status": "ok", "message": f"《{info['title']}》已成功全量翻譯轉換為繁體中文！"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"轉換繁體失敗: {str(e)}")


class SettingPayload(BaseModel):
    value: str

@app.get("/api/settings")
def get_settings():
    """取得所有閱讀器持久化設定（字體大小、字型、字重、主題等）"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}

@app.post("/api/settings/{key}")
def set_setting(key: str, payload: SettingPayload):
    """更新或儲存指定設定"""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, payload.value, now)
        )
        conn.commit()
    return {"status": "ok", "key": key, "value": payload.value}


# 掛載前端靜態檔案
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8765, reload=False)

