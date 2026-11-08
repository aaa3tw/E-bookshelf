"""
小說抓取與追更整合服務模組 (service.py)
整合多站點爬蟲、下載進度管理、自動入庫書櫃與追更檢查
"""

import os
import re
import json
import uuid
import time
import shutil
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

from .cleaner import to_traditional, deobfuscate_hangul
from .adapters import get_adapter
from .downloader import NovelDownloader
from .searcher import parse_input_target, search_biquge, search_timotxt_ddg, search_novel543_ddg, search_ixdzs, search_by_book_name
from .exporter import export_epub, export_txt

# 路徑設定
CRAWLER_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CRAWLER_DIR.parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = ROOT_DIR / "data"
BOOKS_DIR = DATA_DIR / "books"
COVERS_DIR = DATA_DIR / "covers"
CACHE_DIR = DATA_DIR / ".novel_cache"

# 若舊有 novel_crawler 快取存在，建立相容鏈接或備用
LEGACY_CACHE_DIR = Path("E:/AI_project/novel_crawler/.novel_cache")
if not CACHE_DIR.exists() and LEGACY_CACHE_DIR.exists():
    DEFAULT_CACHE = str(LEGACY_CACHE_DIR)
else:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_CACHE = str(CACHE_DIR)

TRACKED_FILE = DATA_DIR / "tracked_novels.json"
LEGACY_TRACKED_FILE = Path("E:/AI_project/novel_crawler/bookshelf.json")

# 若 tracked_novels.json 不存在但舊版 bookshelf.json 存在，自動導入
if not TRACKED_FILE.exists() and LEGACY_TRACKED_FILE.exists():
    try:
        shutil.copy2(LEGACY_TRACKED_FILE, TRACKED_FILE)
    except Exception:
        pass

SUPPORTED_SITES = [
    {
        "id": "ixdzs",
        "name": "愛下電子書",
        "domain": "ixdzs.tw",
        "badge": "精品書庫",
        "desc": "優質繁體小說站，百萬小說免登入線上閱讀與下載",
        "supports": ["explore", "search", "url"]
    },
    {
        "id": "biquge",
        "name": "筆趣閣",
        "domain": "biquge.tw",
        "badge": "熱門推薦",
        "desc": "章節全面、更新迅速的經典小說站",
        "supports": ["explore", "search", "url"]
    },
    {
        "id": "novel543",
        "name": "稷下書院",
        "domain": "novel543.com",
        "badge": "精選榜單",
        "desc": "排版優良、各類熱門網路文學作品",
        "supports": ["explore", "search", "url"]
    },
    {
        "id": "timotxt",
        "name": "提莫書屋",
        "domain": "timotxt.com",
        "badge": "無廣告繁中",
        "desc": "支援韓文象形防爬字元自動還原與排版淨化",
        "supports": ["explore", "search", "url"]
    },
    {
        "id": "po18",
        "name": "PO18 臉紅心跳",
        "domain": "po18.tw",
        "badge": "原創浪漫",
        "desc": "知名女性向原創文學站點（支援書號或文章網址）",
        "supports": ["url"]
    }
]

# 支援小說分類定義 (跨站標準化)
CATEGORIES = [
    {"id": "all", "name": "全部推薦", "icon": "sparkles", "badge": "🔥 總榜"},
    {"id": "xuanhuan", "name": "玄幻奇幻", "icon": "flame", "badge": "⚔️ 玄幻"},
    {"id": "dushi", "name": "都市言情", "icon": "heart", "badge": "🏙️ 都市"},
    {"id": "wuxia", "name": "武俠仙俠", "icon": "sword", "badge": "🗡️ 仙俠"},
    {"id": "lishi", "name": "歷史軍事", "icon": "shield", "badge": "🛡️ 歷史"},
    {"id": "kehuan", "name": "科幻靈異", "icon": "orbit", "badge": "🚀 科幻"},
    {"id": "youxi", "name": "遊戲競技", "icon": "gamepad-2", "badge": "🎮 遊戲"},
    {"id": "danmei", "name": "青春校園", "icon": "book-open", "badge": "🌸 校園"}
]

# 全域下載任務狀態池
download_tasks: Dict[str, Dict[str, Any]] = {}
task_executor = ThreadPoolExecutor(max_workers=3)


class CrawlerService:
    def __init__(self):
        self.tracked_file = TRACKED_FILE
        self.tracked_books = self._load_tracked()
        self.deduplicate()

    def get_supported_categories(self) -> list:
        return CATEGORIES

    def _load_tracked(self) -> dict:
        if self.tracked_file.exists():
            try:
                with open(self.tracked_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_tracked(self):
        self.tracked_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tracked_file, 'w', encoding='utf-8') as f:
            json.dump(self.tracked_books, f, ensure_ascii=False, indent=2)

    def deduplicate(self):
        """自動去重：針對書名相同或 (title, author) 相同之書籍，保留下載章節較多的一筆"""
        seen_books = {}
        duplicates = []
        for k, b in list(self.tracked_books.items()):
            norm_title = to_traditional(b.get("title", "")).strip().lower()
            norm_title = re.sub(r'[\（\(\[\［].*?[\）\)\]\］]', '', norm_title).strip() or norm_title
            key = norm_title
            if key in seen_books:
                existing_key, existing_b = seen_books[key]
                if b.get("downloaded_count", 0) > existing_b.get("downloaded_count", 0):
                    duplicates.append(existing_key)
                    seen_books[key] = (k, b)
                else:
                    duplicates.append(k)
            else:
                seen_books[key] = (k, b)

        for dup in duplicates:
            if dup in self.tracked_books:
                del self.tracked_books[dup]
        if duplicates:
            self._save_tracked()

    def remove_tracked_book(self, book_key: str) -> bool:
        """從追更名冊中移除指定書籍 (支援精確 key、urldecode 或比對書名/書號)"""
        import urllib.parse
        target_keys = [book_key, urllib.parse.unquote(book_key), urllib.parse.quote(book_key)]
        
        # 1. 精確比對
        for tk in target_keys:
            if tk in self.tracked_books:
                del self.tracked_books[tk]
                self._save_tracked()
                return True
                
        # 2. 寬鬆比對 (匹配 book_id 或標題)
        clean_target = book_key.strip().lower()
        for k, b in list(self.tracked_books.items()):
            if k.lower() == clean_target or str(b.get("book_id", "")).lower() in clean_target or to_traditional(b.get("title", "")).strip().lower() == clean_target:
                del self.tracked_books[k]
                self._save_tracked()
                return True

        return False

    def remove_by_uuid_or_title(self, file_uuid: str, title: str):
        """當書櫃刪除書籍時，同步移除追更紀錄"""
        norm_t = to_traditional(title).strip().lower() if title else ""
        keys_to_del = []
        for k, v in self.tracked_books.items():
            if (file_uuid and v.get("file_uuid") == file_uuid) or (norm_t and to_traditional(v.get("title", "")).strip().lower() == norm_t):
                keys_to_del.append(k)
        for k in keys_to_del:
            del self.tracked_books[k]
        if keys_to_del:
            self._save_tracked()

    def sync_with_bookshelf(self) -> dict:
        """
        將已下載的小說 (包括 novel_crawler/downloads 中的書籍) 與 Acrobat Bookshelf 書櫃進行雙向同步
        """
        try:
            from database import get_db
            from book_service import process_epub
            from main import scan_existing_books
        except ImportError:
            from ..database import get_db
            from ..book_service import process_epub
            from ..main import scan_existing_books

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, author, file_path, file_name FROM books")
            existing_books = cursor.fetchall()

        shelf_by_title = {}
        for b in existing_books:
            clean_t = to_traditional(b["title"]).strip().lower()
            shelf_by_title[clean_t] = b

        imported_count = 0
        crawler_downloads_dir = Path("E:/AI_project/novel_crawler/downloads")
        
        if crawler_downloads_dir.exists():
            for ep_file in crawler_downloads_dir.glob("*.epub"):
                raw_name = ep_file.stem
                parts = raw_name.split("_")
                book_title = parts[0] if parts else raw_name
                norm_title = to_traditional(book_title).strip().lower()

                if norm_title not in shelf_by_title:
                    new_uuid = str(uuid.uuid4())
                    clean_filename = f"{new_uuid}_{to_traditional(raw_name)}.epub"
                    clean_filename = re.sub(r'[\/\\:\*\?"<>\|]', '_', clean_filename)
                    target_epub_path = BOOKS_DIR / clean_filename
                    
                    try:
                        shutil.copy2(ep_file, target_epub_path)
                        process_epub(target_epub_path, new_uuid)
                        imported_count += 1
                        shelf_by_title[norm_title] = {
                            "id": new_uuid,
                            "title": to_traditional(book_title),
                            "file_name": clean_filename
                        }
                    except Exception as e:
                        print(f"[Sync] 複製或解析 {ep_file.name} 失敗: {e}")

        scan_existing_books()

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, author, file_name FROM books")
            latest_shelf = cursor.fetchall()
        
        latest_by_title = {}
        for b in latest_shelf:
            t = to_traditional(b["title"]).strip().lower()
            latest_by_title[t] = b

        updated_tracker = 0
        for k, tr in self.tracked_books.items():
            tr_t = to_traditional(tr.get("title", "")).strip().lower()
            if tr_t in latest_by_title:
                shelf_item = latest_by_title[tr_t]
                if tr.get("file_uuid") != shelf_item["id"]:
                    tr["file_uuid"] = shelf_item["id"]
                    tr["file_name"] = shelf_item["file_name"]
                    updated_tracker += 1

        self.deduplicate()
        self._save_tracked()

        return {
            "imported_books": imported_count,
            "updated_tracker_refs": updated_tracker,
            "total_tracked": len(self.tracked_books),
            "total_shelf": len(latest_shelf)
        }

    def get_supported_sites(self) -> list:
        return SUPPORTED_SITES

    def get_site_explore(self, site_id: str, category: str = "all") -> list[dict]:
        """抓取指定小說網站的官方排行榜或指定分類書籍"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        novels = []
        seen = set()
        rank = 1
        cat = (category or "all").lower().strip()

        if site_id == "ixdzs":
            sort_map = {
                "all": "https://ixdzs.tw/sort/1/",
                "xuanhuan": "https://ixdzs.tw/sort/1/",
                "wuxia": "https://ixdzs.tw/sort/2/",
                "dushi": "https://ixdzs.tw/sort/3/",
                "lishi": "https://ixdzs.tw/sort/4/",
                "youxi": "https://ixdzs.tw/sort/5/",
                "kehuan": "https://ixdzs.tw/sort/6/",
                "danmei": "https://ixdzs.tw/sort/7/",
            }
            target_url = sort_map.get(cat, "https://ixdzs.tw/sort/1/")
            try:
                r = requests.get(target_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    for li in soup.find_all('li', class_='burl'):
                        h3 = li.find('h3')
                        if not h3:
                            continue
                        a = h3.find('a')
                        if not a or not a.get('href'):
                            continue
                        href = a['href']
                        m = re.search(r'/read/(\d+)', href)
                        if not m:
                            continue
                        bid = m.group(1)
                        if bid in seen:
                            continue
                        seen.add(bid)

                        title = a.get_text(strip=True)
                        author_el = li.find(class_='bauthor')
                        author = author_el.get_text(strip=True) if author_el else '佚名'
                        intro_el = li.find('p', class_='l-p2')
                        intro = intro_el.get_text(strip=True) if intro_el else ''
                        img_el = li.select_one('.l-img img')
                        cover_url = img_el.get('src', '') if img_el else ''

                        badge = f"TOP {rank}"
                        if rank == 1:
                            badge = "👑 榜首 TOP 1"
                        elif rank == 2:
                            badge = "🥈 TOP 2"
                        elif rank == 3:
                            badge = "🥉 TOP 3"
                        elif rank <= 10:
                            badge = f"🔥 TOP {rank}"

                        novels.append({
                            "rank": rank,
                            "book_id": bid,
                            "site": "ixdzs",
                            "site_name": "愛下電子書",
                            "title": to_traditional(title),
                            "author": to_traditional(author),
                            "intro": to_traditional(intro),
                            "category": cat,
                            "url": f"https://ixdzs.tw/read/{bid}/",
                            "cover_url": cover_url,
                            "badge": badge
                        })
                        rank += 1
            except Exception as e:
                print(f"[Explore] 愛下電子書排行出錯: {e}")

        elif site_id == "biquge":
            sort_map = {
                "all": "https://m.biquge.tw/top/",
                "xuanhuan": "https://m.biquge.tw/sort/xuanhuan/",
                "dushi": "https://m.biquge.tw/sort/dushi/",
                "wuxia": "https://m.biquge.tw/sort/wuxia/",
                "lishi": "https://m.biquge.tw/sort/lishi/",
                "kehuan": "https://m.biquge.tw/sort/kehuan/",
                "youxi": "https://m.biquge.tw/sort/youxi/",
                "danmei": "https://m.biquge.tw/sort/dushi/",
            }
            target_url = sort_map.get(cat, "https://m.biquge.tw/top/")
            try:
                r = requests.get(target_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    for item in soup.select('.item'):
                        a = item.select_one('dt a') or item.find('a', href=re.compile(r'/book/\d+'))
                        if not a:
                            continue
                        href = a.get('href', '')
                        m = re.search(r'/book/(\d+)', href)
                        if not m:
                            continue
                        bid = m.group(1)
                        if bid in seen:
                            continue
                        seen.add(bid)

                        title = a.get_text(strip=True)
                        author_el = item.select_one('.author')
                        author = author_el.get_text(strip=True) if author_el else '佚名'
                        intro_el = item.select_one('.intro')
                        intro = intro_el.get_text(strip=True) if intro_el else ''

                        img = item.select_one('img')
                        cover_url = ''
                        if img:
                            cover_url = img.get('data-src') or img.get('src') or ''
                            if cover_url.startswith('/'):
                                cover_url = 'https://m.biquge.tw' + cover_url
                            elif not cover_url.startswith('http'):
                                cover_url = ''
                        if not cover_url and len(bid) >= 4:
                            cover_url = f"https://img.biquge.tw/{bid[:4]}/{bid}/{bid}s.jpg"

                        cat_tag_el = item.select_one('.cover span')
                        cat_tag = cat_tag_el.get_text(strip=True) if cat_tag_el else ''

                        badge = f"TOP {rank}"
                        if rank == 1:
                            badge = "👑 榜首 TOP 1"
                        elif rank == 2:
                            badge = "🥈 TOP 2"
                        elif rank == 3:
                            badge = "🥉 TOP 3"
                        elif rank <= 10:
                            badge = f"🔥 TOP {rank}"

                        novels.append({
                            "rank": rank,
                            "book_id": bid,
                            "site": "biquge",
                            "site_name": "筆趣閣",
                            "title": to_traditional(title),
                            "author": to_traditional(author),
                            "intro": to_traditional(intro),
                            "category": cat_tag or cat,
                            "url": f"https://m.biquge.tw/book/{bid}/",
                            "cover_url": cover_url,
                            "badge": badge
                        })
                        rank += 1
            except Exception as e:
                print(f"[Explore] Biquge ranking error: {e}")

        elif site_id == "novel543":
            tag_map = {
                "all": "https://www.novel543.com/",
                "xuanhuan": "https://www.novel543.com/tags/%E7%8E%84%E5%B9%BB/",
                "dushi": "https://www.novel543.com/tags/%E9%83%BD%E5%B8%82/",
                "wuxia": "https://www.novel543.com/tags/%E4%BB%99%E4%BF%A0/",
                "lishi": "https://www.novel543.com/tags/%E6%AD%B7%E5%8F%B2/",
                "kehuan": "https://www.novel543.com/tags/%E7%A7%91%E5%B9%BB/",
                "youxi": "https://www.novel543.com/tags/%E9%81%8A%E6%88%B2/",
                "danmei": "https://www.novel543.com/tags/%E7%8F%BE%E4%BB%A3%E8%A8%80%E6%83%85/",
            }
            target_url = tag_map.get(cat, "https://www.novel543.com/")
            try:
                r = requests.get(target_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    media_items = soup.select('li.media')
                    if media_items:
                        for it in media_items:
                            a = it.select_one('h3 a') or it.select_one('a')
                            if not a:
                                continue
                            href = a.get('href', '')
                            m = re.search(r'/(\d{6,})/?', href)
                            if not m:
                                continue
                            bid = m.group(1)
                            if bid in seen:
                                continue
                            seen.add(bid)
                            title = a.get_text(strip=True)
                            author_el = it.select_one('.author')
                            author = author_el.get_text(strip=True) if author_el else '熱搜原創'
                            desc_el = it.select_one('.desc') or it.select_one('p')
                            intro = desc_el.get_text(strip=True) if desc_el else ''
                            img_el = it.select_one('img')
                            cover_url = img_el.get('src', '') if img_el else ''

                            badge = f"TOP {rank}"
                            if rank == 1:
                                badge = "👑 榜首 TOP 1"
                            elif rank == 2:
                                badge = "🥈 TOP 2"
                            elif rank == 3:
                                badge = "🥉 TOP 3"
                            elif rank <= 10:
                                badge = f"🔥 TOP {rank}"

                            novels.append({
                                "rank": rank,
                                "book_id": bid,
                                "site": "novel543",
                                "site_name": "稷下書院",
                                "title": to_traditional(title),
                                "author": to_traditional(author),
                                "intro": to_traditional(intro),
                                "category": cat,
                                "url": f"https://www.novel543.com/{bid}/dir",
                                "cover_url": cover_url,
                                "badge": badge
                            })
                            rank += 1
                    else:
                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            m = re.search(r'/(\d{6,})/?(?:dir)?', href)
                            title = a.get_text(strip=True)
                            if m and title and len(title) > 1 and not "章" in title and len(title) < 30:
                                bid = m.group(1)
                                if bid not in seen:
                                    seen.add(bid)
                                    badge = f"TOP {rank}"
                                    if rank == 1:
                                        badge = "👑 榜首 TOP 1"
                                    elif rank == 2:
                                        badge = "🥈 TOP 2"
                                    elif rank == 3:
                                        badge = "🥉 TOP 3"
                                    elif rank <= 10:
                                        badge = f"🔥 TOP {rank}"

                                    novels.append({
                                        "rank": rank,
                                        "book_id": bid,
                                        "site": "novel543",
                                        "site_name": "稷下書院",
                                        "title": to_traditional(title),
                                        "author": "熱搜原創",
                                        "intro": "稷下書院熱搜排行榜推薦作品",
                                        "category": cat,
                                        "url": f"https://www.novel543.com/{bid}/dir",
                                        "cover_url": "",
                                        "badge": badge
                                    })
                                    rank += 1
            except Exception as e:
                print(f"[Explore] Novel543 error: {e}")

        elif site_id == "timotxt":
            cid_map = {
                "all": "https://www.timotxt.com/",
                "xuanhuan": "https://www.timotxt.com/bookstack/?cid=5",
                "dushi": "https://www.timotxt.com/bookstack/?cid=4",
                "wuxia": "https://www.timotxt.com/bookstack/?cid=5",
                "lishi": "https://www.timotxt.com/bookstack/?cid=2",
                "kehuan": "https://www.timotxt.com/bookstack/?cid=10",
                "youxi": "https://www.timotxt.com/bookstack/?cid=25",
                "danmei": "https://www.timotxt.com/bookstack/?cid=1",
            }
            target_url = cid_map.get(cat, "https://www.timotxt.com/")
            try:
                r = requests.get(target_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, 'html.parser')
                    row_items = soup.select('li.row')
                    if row_items:
                        for it in row_items:
                            a = it.select_one('h3 a') or it.select_one('a')
                            if not a:
                                continue
                            href = a.get('href', '')
                            m = re.search(r'/(\d{6,})/?', href)
                            if not m:
                                continue
                            bid = m.group(1)
                            if bid in seen:
                                continue
                            seen.add(bid)
                            raw_title = a.get_text(strip=True)
                            title = deobfuscate_hangul(raw_title)
                            author_el = it.select_one('.author')
                            author = author_el.get_text(strip=True) if author_el else '熱搜榜單'
                            desc_el = it.select_one('.desc') or it.select_one('p')
                            intro = desc_el.get_text(strip=True) if desc_el else ''
                            img_el = it.select_one('img')
                            cover_url = img_el.get('src', '') if img_el else ''

                            badge = f"TOP {rank}"
                            if rank == 1:
                                badge = "👑 榜首 TOP 1"
                            elif rank == 2:
                                badge = "🥈 TOP 2"
                            elif rank == 3:
                                badge = "🥉 TOP 3"
                            elif rank <= 10:
                                badge = f"🔥 TOP {rank}"

                            novels.append({
                                "rank": rank,
                                "book_id": bid,
                                "site": "timotxt",
                                "site_name": "提莫書屋",
                                "title": to_traditional(title),
                                "author": to_traditional(author),
                                "intro": to_traditional(intro),
                                "category": cat,
                                "url": f"https://www.timotxt.com/{bid}/dir",
                                "cover_url": cover_url,
                                "badge": badge
                            })
                            rank += 1
                    else:
                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            m = re.search(r'/(\d{6,})/?(?:dir)?', href)
                            title = a.get_text(strip=True)
                            if m and title and len(title) > 1 and not title.startswith("第") and not "章" in title[:4] and len(title) < 35:
                                bid = m.group(1)
                                if bid not in seen:
                                    seen.add(bid)
                                    badge = f"TOP {rank}"
                                    if rank == 1:
                                        badge = "👑 榜首 TOP 1"
                                    elif rank == 2:
                                        badge = "🥈 TOP 2"
                                    elif rank == 3:
                                        badge = "🥉 TOP 3"
                                    elif rank <= 10:
                                        badge = f"🔥 TOP {rank}"

                                    novels.append({
                                        "rank": rank,
                                        "book_id": bid,
                                        "site": "timotxt",
                                        "site_name": "提莫書屋",
                                        "title": to_traditional(deobfuscate_hangul(title)),
                                        "author": "熱搜榜單",
                                        "intro": "提莫書屋繁體精選熱門榜單作品",
                                        "category": cat,
                                        "url": f"https://www.timotxt.com/{bid}/dir",
                                        "cover_url": "",
                                        "badge": badge
                                    })
                                    rank += 1
            except Exception as e:
                print(f"[Explore] Timotxt error: {e}")

        elif site_id == "po18":
            po18_database = {
                "all": [
                    {"book_id": "902326", "title": "和哥哥在亂交世界裡假裝do愛", "author": "歸霧", "intro": "PO18年度原創熱搜冠軍作品", "url": "https://www.po18.tw/books/902326/articles"},
                    {"book_id": "904717", "title": "快穿之慾女系統", "author": "素兮嬈嬈", "intro": "高人氣快穿系統經典榜單巨作", "url": "https://www.po18.tw/books/904717/articles"},
                    {"book_id": "903913", "title": "［系統］少女她越操越美（nph）", "author": "皇皇嬤嬤子", "intro": "讀者高評分推薦榜前列作品", "url": "https://www.po18.tw/books/903913/articles"},
                    {"book_id": "890935", "title": "澀澀小魚是真的會被幹透（NPH）", "author": "小魚卟嚕嚕", "intro": "PO18年度火熱原創連載", "url": "https://www.po18.tw/books/890935/articles"},
                    {"book_id": "891420", "title": "負距離告白（校園 h）", "author": "修修咪", "intro": "校園青春人氣榜首選作品", "url": "https://www.po18.tw/books/891420/articles"},
                    {"book_id": "903633", "title": "心機綠茶就該被狠狠懲罰（強制np）", "author": "裡春", "intro": "高討論度原創排行榜熱作", "url": "https://www.po18.tw/books/903633/articles"},
                ],
                "dushi": [
                    {"book_id": "902326", "title": "和哥哥在亂交世界裡假裝do愛", "author": "歸霧", "intro": "都市豪門禁忌熱搜冠軍", "url": "https://www.po18.tw/books/902326/articles"},
                    {"book_id": "903633", "title": "心機綠茶就該被狠狠懲罰（強制np）", "author": "裡春", "intro": "都市職場高人氣熱作", "url": "https://www.po18.tw/books/903633/articles"},
                ],
                "xuanhuan": [
                    {"book_id": "904717", "title": "快穿之慾女系統", "author": "素兮嬈嬈", "intro": "高人氣快穿系統經典榜單巨作", "url": "https://www.po18.tw/books/904717/articles"},
                    {"book_id": "903913", "title": "［系統］少女她越操越美（nph）", "author": "皇皇嬤嬤子", "intro": "快穿系統幻想熱榜作品", "url": "https://www.po18.tw/books/903913/articles"},
                ],
                "danmei": [
                    {"book_id": "891420", "title": "負距離告白（校園 h）", "author": "修修咪", "intro": "校園青春人氣榜首選作品", "url": "https://www.po18.tw/books/891420/articles"},
                    {"book_id": "890935", "title": "澀澀小魚是真的會被幹透（NPH）", "author": "小魚卟嚕嚕", "intro": "青春校園純愛連載", "url": "https://www.po18.tw/books/891420/articles"},
                ]
            }
            items = po18_database.get(cat, po18_database["all"])
            for it in items:
                badge = f"TOP {rank}"
                if rank == 1:
                    badge = "👑 榜首 TOP 1"
                elif rank == 2:
                    badge = "🥈 TOP 2"
                elif rank == 3:
                    badge = "🥉 TOP 3"
                else:
                    badge = f"🔥 TOP {rank}"

                novels.append({
                    "rank": rank,
                    "book_id": it["book_id"],
                    "site": "po18",
                    "site_name": "PO18 臉紅心跳",
                    "title": to_traditional(it["title"]),
                    "author": it["author"],
                    "intro": it["intro"],
                    "category": cat,
                    "url": it["url"],
                    "cover_url": "",
                    "badge": badge
                })
                rank += 1

        return novels[:30]

    def search_books(self, keyword: str, site_id: Optional[str] = None) -> list[dict]:
        """跨站或指定站點搜尋書籍"""
        kw = keyword.strip()
        if not kw:
            return []

        # 若使用者直接貼網址或書號
        direct_url = parse_input_target(kw)
        if direct_url:
            return [{
                "book_id": "direct",
                "site": "auto",
                "site_name": "直接網址解析",
                "title": f"解析目標: {kw}",
                "url": direct_url,
                "badge": "精確網址"
            }]

        results = []
        if site_id == "ixdzs" or not site_id:
            try:
                for b in search_ixdzs(kw):
                    results.append({
                        "book_id": b["book_id"],
                        "site": "ixdzs",
                        "site_name": "愛下電子書",
                        "title": to_traditional(b["title"]),
                        "author": to_traditional(b.get("author", "佚名")),
                        "intro": to_traditional(b.get("intro", "")),
                        "cover_url": b.get("cover_url", ""),
                        "url": b["dir_url"],
                        "badge": "愛下電子書"
                    })
            except Exception as e:
                print(f"[Search] Ixdzs failed: {e}")

        if site_id == "biquge" or not site_id:
            try:
                for b in search_biquge(kw):
                    results.append({
                        "book_id": b["book_id"],
                        "site": "biquge",
                        "site_name": "筆趣閣",
                        "title": to_traditional(b["title"]),
                        "url": b["dir_url"],
                        "badge": "筆趣閣"
                    })
            except Exception as e:
                print(f"[Search] Biquge failed: {e}")

        if site_id == "novel543" or not site_id:
            try:
                for b in search_novel543_ddg(kw):
                    results.append({
                        "book_id": b["book_id"],
                        "site": "novel543",
                        "site_name": "稷下書院",
                        "title": to_traditional(b["title"]),
                        "url": b["dir_url"],
                        "badge": "稷下書院"
                    })
            except Exception as e:
                print(f"[Search] Novel543 failed: {e}")

        if site_id == "timotxt" or not site_id:
            try:
                for b in search_timotxt_ddg(kw):
                    results.append({
                        "book_id": b["book_id"],
                        "site": "timotxt",
                        "site_name": "提莫書屋",
                        "title": to_traditional(deobfuscate_hangul(b["title"])),
                        "url": b["dir_url"],
                        "badge": "提莫書屋"
                    })
            except Exception as e:
                print(f"[Search] Timotxt failed: {e}")

        return results

    def parse_book_detail(self, url: str) -> dict:
        """解析書籍詳情與章節資訊"""
        clean_url = parse_input_target(url) or url.strip()
        downloader = NovelDownloader(base_url=clean_url, cache_dir=DEFAULT_CACHE)
        meta = downloader.get_book_metadata()
        chapters = downloader.get_chapter_list()

        return {
            "title": meta.get("title", "未知書名"),
            "author": meta.get("author", "未知作者"),
            "intro": meta.get("intro", ""),
            "cover_url": meta.get("cover_url", ""),
            "site": meta.get("source", downloader.site_name),
            "dir_url": clean_url,
            "book_id": downloader.book_id,
            "total_chapters": len(chapters),
            "latest_chapter": chapters[-1]["title"] if chapters else "無",
            "first_chapters": [c["title"] for c in chapters[:15]]
        }

    def start_download_task(self, url: str, export_format: str = "epub") -> str:
        """啟動非同步下載任務並返回 task_id"""
        task_id = str(uuid.uuid4())
        clean_url = parse_input_target(url) or url.strip()

        download_tasks[task_id] = {
            "id": task_id,
            "url": clean_url,
            "status": "pending",
            "progress": 0,
            "current": 0,
            "total": 0,
            "current_chapter": "初始化連線中...",
            "title": "正在連接源站...",
            "author": "",
            "message": "正在解析書籍資訊與目錄清單...",
            "book_id": None,
            "book_file": None,
            "error": None,
            "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        task_executor.submit(self._run_download_worker, task_id, clean_url, export_format)
        return task_id

    def _run_download_worker(self, task_id: str, url: str, export_format: str):
        """下載背景執行緒 worker"""
        task = download_tasks.get(task_id)
        if not task:
            return

        try:
            task["status"] = "connecting"
            downloader = NovelDownloader(base_url=url, cache_dir=DEFAULT_CACHE)
            
            # 1. 取得中繼資料
            meta = downloader.get_book_metadata()
            task["title"] = meta.get("title", "未知小說")
            task["author"] = meta.get("author", "佚名")
            task["message"] = f"《{task['title']}》目錄解析中..."

            # 2. 取得章節目錄
            chapters = downloader.get_chapter_list()
            total_chaps = len(chapters)
            task["total"] = total_chaps
            if total_chaps == 0:
                raise ValueError("未獲取到正文章節，請檢查目錄網址是否有效！")

            task["status"] = "downloading"
            task["message"] = f"開始下載正文（共 {total_chaps} 章）..."

            # 進度回調函式
            def on_progress(completed: int, total: int, chap_title: str):
                task["current"] = completed
                task["current_chapter"] = chap_title
                # 下載佔 10% ~ 90%
                pct = int(10 + (completed / max(1, total)) * 80)
                task["progress"] = min(90, pct)
                task["message"] = f"下載中 [{completed}/{total}]: {chap_title}"

            # 3. 多執行緒下載
            downloaded_chapters = downloader.download_all_chapters(chapters, progress_callback=on_progress)

            # 4. 封裝檔案 (90% ~ 98%)
            task["status"] = "packaging"
            task["progress"] = 92
            task["message"] = "正文下載完畢，正在封裝成電子書並匯入書櫃..."

            clean_title = re.sub(r'[\/\\:\*\?"<>\|]', '_', task['title'])
            clean_author = re.sub(r'[\/\\:\*\?"<>\|]', '_', task['author'])
            
            # 生成標準檔名
            file_uuid = str(uuid.uuid4())
            epub_filename = f"{file_uuid}_{clean_title}_{clean_author}.epub"
            epub_path = BOOKS_DIR / epub_filename

            cover_bytes = downloader.fetch_cover_bytes(meta.get('cover_url'))
            export_epub(meta, downloaded_chapters, str(epub_path), cover_bytes=cover_bytes)

            # 5. 匯入書櫃資料庫
            task["progress"] = 98
            task["message"] = "電子書封裝完成，正在註冊至書櫃資料庫..."
            
            # 調用書櫃核心解析服務 (相容匯入)
            try:
                try:
                    from book_service import process_epub
                    from main import scan_existing_books
                except ImportError:
                    from ..book_service import process_epub
                    from ..main import scan_existing_books
                process_epub(epub_path, file_uuid)
                scan_existing_books()
            except Exception as e:
                print(f"[Import Warning] 自動掃描書櫃失敗: {e}")

            # 6. 記錄至追更清單
            book_key = f"{meta.get('source', downloader.site_name)}_{meta.get('book_id', downloader.book_id)}"
            last_chap = downloaded_chapters[-1] if downloaded_chapters else {'title': '無'}
            
            self.tracked_books[book_key] = {
                'book_key': book_key,
                'book_id': meta.get('book_id', downloader.book_id),
                'source': meta.get('source', downloader.site_name),
                'title': task['title'],
                'author': task['author'],
                'dir_url': url,
                'cover_url': meta.get('cover_url', ''),
                'downloaded_count': len(downloaded_chapters),
                'last_chapter_title': last_chap.get('title', ''),
                'last_updated_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'file_uuid': file_uuid,
                'file_name': epub_filename
            }
            self._save_tracked()

            task["status"] = "completed"
            task["progress"] = 100
            task["book_file"] = epub_filename
            task["book_uuid"] = file_uuid
            task["message"] = f"🎉《{task['title']}》已成功下載並直接加入書櫃！"

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)
            task["message"] = f"下載失敗: {str(e)}"
            print(f"[Worker Error] {task_id}: {e}")

    def get_task_status(self, task_id: str) -> Optional[dict]:
        return download_tasks.get(task_id)

    def list_tracked_novels(self) -> list[dict]:
        """取得所有已追蹤小說列表"""
        return list(self.tracked_books.values())

    def check_update_single(self, book_key: str) -> dict:
        """檢查單本小說是否有新章節"""
        book = self.tracked_books.get(book_key)
        if not book:
            return {"error": "找不到此書籍追更記錄"}

        try:
            downloader = NovelDownloader(base_url=book['dir_url'], cache_dir=DEFAULT_CACHE)
            all_latest = downloader.get_chapter_list()
            cur_count = book.get('downloaded_count', 0)
            new_count = max(0, len(all_latest) - cur_count)
            latest_title = all_latest[-1]['title'] if all_latest else "無"

            return {
                "book_key": book_key,
                "title": book['title'],
                "current_count": cur_count,
                "latest_count": len(all_latest),
                "new_count": new_count,
                "has_update": new_count > 0,
                "latest_chapter_title": latest_title,
                "check_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            return {
                "book_key": book_key,
                "title": book['title'],
                "error": str(e),
                "has_update": False
            }

    def check_update_all(self) -> list[dict]:
        """批次檢查所有書籍更新"""
        results = []
        for b_key in list(self.tracked_books.keys()):
            res = self.check_update_single(b_key)
            results.append(res)
        return results

    def apply_update_task(self, book_key: str) -> str:
        """啟動指定小說增量追更下載任務"""
        book = self.tracked_books.get(book_key)
        if not book:
            raise ValueError("找不到書籍記錄！")
        return self.start_download_task(book['dir_url'], export_format="epub")


# 單例服務實例
crawler_service = CrawlerService()
