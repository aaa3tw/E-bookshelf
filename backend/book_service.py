import os
import uuid
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
import pymupdf  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

try:
    from app_paths import DATA_DIR, BOOKS_DIR, COVERS_DIR, THUMBS_DIR
except ImportError:
    try:
        from .app_paths import DATA_DIR, BOOKS_DIR, COVERS_DIR, THUMBS_DIR
    except ImportError:
        DATA_DIR = Path(__file__).resolve().parent.parent / "data"
        BOOKS_DIR = DATA_DIR / "books"
        COVERS_DIR = DATA_DIR / "covers"
        THUMBS_DIR = DATA_DIR / "thumbnails"

COVERS_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

def generate_fallback_cover(title: str, author: str, output_path: Path, bg_color=(45, 55, 72)):
    """當沒有內嵌封面時，動態生成一張高質感簡約封面"""
    width, height = 400, 560
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 畫書脊與內邊框陰影飾條
    draw.rectangle([0, 0, 24, height], fill=(30, 40, 55))
    draw.rectangle([28, 20, width - 20, height - 20], outline=(80, 95, 120), width=2)
    
    # 書本格式裝飾標誌
    draw.rectangle([45, 40, 95, 65], fill=(220, 53, 69))
    draw.text((55, 45), "BOOK", fill=(255, 255, 255))
    
    display_title = title if len(title) <= 24 else title[:22] + "..."
    draw.text((45, 120), display_title, fill=(245, 245, 245))
    draw.text((45, 180), f"Author: {author}", fill=(180, 190, 205))
    draw.text((45, height - 60), "Acrobat Bookshelf", fill=(120, 130, 150))
    
    img.save(output_path, "PNG")

def process_pdf(file_path: Path, book_id: str):
    """解析 PDF 檔案資訊，抽取封面與目錄"""
    try:
        doc = pymupdf.open(file_path)
    except Exception as e:
        # 加密或損毀檔案防護
        cover_filename = f"{book_id}.png"
        generate_fallback_cover(file_path.stem, "未知作者", COVERS_DIR / cover_filename, bg_color=(120, 40, 40))
        return {
            "title": file_path.stem,
            "author": "受保護或未知作者",
            "total_pages": 1,
            "cover_image": f"/api/covers/{cover_filename}",
            "file_type": "pdf"
        }

    metadata = doc.metadata or {}
    title = metadata.get("title") or file_path.stem
    author = metadata.get("author") or "未知作者"
    total_pages = len(doc)
    
    cover_filename = f"{book_id}.png"
    cover_path = COVERS_DIR / cover_filename
    
    try:
        if total_pages > 0 and not doc.is_encrypted:
            first_page = doc[0]
            pix = first_page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
            pix.save(cover_path)
        else:
            generate_fallback_cover(title, author, cover_path, bg_color=(200, 35, 51))
    except Exception:
        generate_fallback_cover(title, author, cover_path, bg_color=(200, 35, 51))
        
    doc.close()
    return {
        "title": title.strip() or file_path.stem,
        "author": author.strip() or "未知作者",
        "total_pages": max(1, total_pages),
        "cover_image": f"/api/covers/{cover_filename}",
        "file_type": "pdf"
    }

def get_pdf_outline(file_path: Path):
    """取得 PDF 目錄大綱 (TOC)"""
    try:
        doc = pymupdf.open(file_path)
        toc = doc.get_toc()
        doc.close()
    except Exception:
        return []
    
    outline = []
    for item in toc:
        outline.append({
            "level": item[0],
            "title": item[1],
            "page": item[2]
        })
    return outline

def get_pdf_page_thumbnail(file_path: Path, book_id: str, page_number: int):
    """取得或快取單頁 PDF 縮圖"""
    thumb_name = f"{book_id}_p{page_number}.png"
    thumb_path = THUMBS_DIR / thumb_name
    if thumb_path.exists():
        return thumb_path
        
    try:
        doc = pymupdf.open(file_path)
        if 1 <= page_number <= len(doc):
            page = doc[page_number - 1]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(0.3, 0.3))
            pix.save(thumb_path)
        doc.close()
    except Exception:
        pass
    return thumb_path

def process_epub(file_path: Path, book_id: str):
    """解析 EPUB 檔案資訊，抽取封面與目錄"""
    try:
        book = epub.read_epub(str(file_path), {"ignore_ncx": False})
    except Exception as e:
        cover_filename = f"{book_id}.png"
        generate_fallback_cover(file_path.stem, "未知作者", COVERS_DIR / cover_filename, bg_color=(24, 76, 120))
        return {
            "title": file_path.stem,
            "author": "未知作者",
            "total_pages": 1,
            "cover_image": f"/api/covers/{cover_filename}",
            "file_type": "epub"
        }
    
    title_meta = book.get_metadata('DC', 'title')
    title = title_meta[0][0] if title_meta else file_path.stem
    
    creator_meta = book.get_metadata('DC', 'creator')
    author = creator_meta[0][0] if creator_meta else "未知作者"
    
    cover_filename = f"{book_id}.png"
    cover_path = COVERS_DIR / cover_filename
    has_cover = False
    
    for item in book.get_items_of_type(ebooklib.ITEM_COVER):
        with open(cover_path, 'wb') as f:
            f.write(item.get_content())
        has_cover = True
        break
        
    if not has_cover:
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            if "cover" in item.get_name().lower():
                with open(cover_path, 'wb') as f:
                    f.write(item.get_content())
                has_cover = True
                break
                
    if not has_cover:
        generate_fallback_cover(title, author, cover_path, bg_color=(24, 76, 120))
        
    docs = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    total_pages = max(1, len(docs))
    
    return {
        "title": title.strip() or file_path.stem,
        "author": author.strip() or "未知作者",
        "total_pages": total_pages,
        "cover_image": f"/api/covers/{cover_filename}",
        "file_type": "epub"
    }

def get_epub_toc(file_path: Path):
    """取得 EPUB 目錄清單"""
    try:
        book = epub.read_epub(str(file_path))
    except Exception:
        return []
        
    toc = []
    def extract_nav(nav_list, level=1):
        for item in nav_list:
            if isinstance(item, tuple):
                section, sub_items = item
                toc.append({
                    "level": level,
                    "title": getattr(section, 'title', str(section)),
                    "href": getattr(section, 'href', '')
                })
                extract_nav(sub_items, level + 1)
            elif isinstance(item, epub.Link):
                toc.append({
                    "level": level,
                    "title": item.title,
                    "href": item.href
                })
            elif hasattr(item, 'title'):
                toc.append({
                    "level": level,
                    "title": item.title,
                    "href": getattr(item, 'href', '')
                })

    extract_nav(book.toc)
    return toc

def get_epub_chapters(file_path: Path):
    """取得 EPUB 所有 HTML 章節，便於在線編輯文字與預覽"""
    book = epub.read_epub(str(file_path))
    chapters = []
    
    # 取得 zip 中的真實 namelist
    with zipfile.ZipFile(file_path, 'r') as zf:
        zip_names = zf.namelist()
        
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(content, 'html.parser')
        heading = soup.find(['h1', 'h2', 'h3', 'title'])
        title = heading.get_text().strip() if heading else item.get_name()
        
        # 尋找 zip 中的精確路徑
        item_name = item.get_name()
        exact_zip_path = item_name
        for z in zip_names:
            if z == item_name or z.endswith('/' + item_name) or item_name.endswith('/' + z):
                exact_zip_path = z
                break
                
        # 抽取純文字段落便於直接閱讀與文字編輯
        text_paragraphs = [p.get_text().strip() for p in soup.find_all('p') if p.get_text().strip()]
        plain_text = "\n\n".join(text_paragraphs)
        
        chapters.append({
            "id": item.get_id(),
            "file_name": exact_zip_path,
            "title": title or item.get_name(),
            "content": content,
            "plain_text": plain_text
        })
    return chapters

def update_epub_chapter(file_path: Path, chapter_file_name: str, new_content: str):
    """更新 EPUB 內部指定章節內容並重新包裝 (支援完整 HTML 或純文字更新)"""
    temp_epub = file_path.with_suffix('.tmp.epub')
    updated = False
    
    target_base = Path(chapter_file_name).name.lower()
    
    with zipfile.ZipFile(file_path, 'r') as zin:
        with zipfile.ZipFile(temp_epub, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                curr_base = Path(item.filename).name.lower()
                # 支援完全路徑比對或檔名比對
                if item.filename == chapter_file_name or curr_base == target_base:
                    # 如果使用者傳入的是純文字 (不含 <html>)，自動封裝成合法 HTML
                    if not new_content.strip().startswith('<html') and not new_content.strip().startswith('<!DOCTYPE'):
                        paragraphs = new_content.split('\n')
                        body_html = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
                        final_html = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter</title></head>
<body>{body_html}</body>
</html>'''
                    else:
                        final_html = new_content

                    zout.writestr(item, final_html.encode('utf-8'))
                    updated = True
                else:
                    zout.writestr(item, zin.read(item.filename))
                    
    if updated:
        shutil.move(str(temp_epub), str(file_path))
        return True
    else:
        if temp_epub.exists():
            temp_epub.unlink()
        return False

def export_annotated_pdf(file_path: Path, output_path: Path, annotations: list):
    """將前端產生的註解（高亮、下劃線、便籤筆記、自由繪圖）寫入 PDF 並輸出"""
    doc = pymupdf.open(file_path)
    
    for ann in annotations:
        page_idx = int(ann.get("page_index", 1)) - 1
        if page_idx < 0 or page_idx >= len(doc):
            continue
            
        page = doc[page_idx]
        ann_type = ann.get("type", "")
        data = ann.get("data", {})
        
        # 螢光筆高亮
        if ann_type == "highlight" and "rects" in data:
            for r in data["rects"]:
                rect = pymupdf.Rect(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])
                highlight = page.add_highlight_annot(rect)
                highlight.update()
                
        # 便籤註解
        elif ann_type == "note" and "point" in data:
            pt = pymupdf.Point(data["point"]["x"], data["point"]["y"])
            note = page.add_text_annot(pt, ann.get("text_content", ""))
            note.update()
            
        # 自由畫筆 / 塗鴉
        elif ann_type == "drawing" and "points" in data:
            pts = [pymupdf.Point(p["x"], p["y"]) for p in data["points"]]
            if len(pts) >= 2:
                stroke = page.add_ink_annot([pts])
                stroke.update()

    doc.save(str(output_path))
    doc.close()
    return True
