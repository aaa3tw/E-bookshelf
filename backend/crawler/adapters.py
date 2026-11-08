"""
多站點適配器模組 (adapters.py)
支援：
1. 筆趣閣 (BiqugeAdapter: m.biquge.tw / www.biquge.tw)
2. 提莫書屋 (TimotxtAdapter: timotxt.com)
"""

import os
import json
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

try:
    from .cleaner import clean_chapter_html, clean_chapter_title, deobfuscate_hangul, to_traditional
except ImportError:
    from cleaner import clean_chapter_html, clean_chapter_title, deobfuscate_hangul, to_traditional

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}


class BaseAdapter:
    def __init__(self, base_url: str, session: requests.Session):
        self.base_url = base_url.strip()
        self.session = session
        self.book_id = "unknown"

    def fetch_url(self, url: str, retries: int = 4, timeout: int = 15) -> str | None:
        import time
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, headers=HEADERS, timeout=timeout)
                if resp.status_code == 200:
                    resp.encoding = resp.apparent_encoding or 'utf-8'
                    return resp.text
                elif resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * attempt)
            except Exception as e:
                if attempt == retries:
                    print(f"\n[Adapter Error] 連線失敗 ({url}): {e}")
                time.sleep(1.0 * attempt)
        return None

    def get_book_metadata(self) -> dict:
        raise NotImplementedError

    def get_chapter_list(self) -> list[dict]:
        raise NotImplementedError

    def fetch_chapter_content(self, chapter: dict) -> dict:
        raise NotImplementedError


class BiqugeAdapter(BaseAdapter):
    """筆趣閣 (m.biquge.tw / www.biquge.tw) 適配器"""
    def __init__(self, base_url: str, session: requests.Session):
        super().__init__(base_url, session)
        m = re.search(r'biquge\.tw/book/(\d+)', self.base_url)
        self.book_id = m.group(1) if m else "biquge_book"
        self.mobile_dir_url = f"https://m.biquge.tw/book/{self.book_id}/"
        self.mobile_info_url = f"https://m.biquge.tw/book/{self.book_id}.html"

    def get_book_metadata(self) -> dict:
        html = self.fetch_url(self.mobile_info_url)
        if not html:
            html = self.fetch_url(self.mobile_dir_url)

        soup = BeautifulSoup(html or "", 'html.parser')

        # 1. 書名
        title = "未知小說"
        meta_title = soup.find('meta', property='og:novel:book_name') or soup.find('meta', property='og:title')
        if meta_title and meta_title.get('content'):
            title = meta_title['content'].strip()
        else:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)

        # 2. 作者
        author = "佚名"
        meta_author = soup.find('meta', property='og:novel:author')
        if meta_author and meta_author.get('content'):
            author = meta_author['content'].strip()
        else:
            for p in soup.find_all(['p', 'span', 'a']):
                t = p.get_text(strip=True)
                if '作者' in t and len(t) < 30:
                    m_auth = re.search(r'作者[：:]\s*([^\s<]+)', t)
                    if m_auth:
                        author = m_auth.group(1).strip()
                        break

        # 3. 簡介
        intro = ""
        meta_desc = soup.find('meta', property='og:description')
        if meta_desc and meta_desc.get('content'):
            intro = meta_desc['content'].strip()
        else:
            intro_div = soup.find('div', class_='intro') or soup.find('div', class_='review')
            if intro_div:
                intro = intro_div.get_text('\n', strip=True)

        # 清理簡介中的開頭贅詞與 HTML 註釋
        intro = re.sub(r'<!--.*?-->', '', intro, flags=re.DOTALL)
        intro = re.sub(r'^(?:小說簡介[：:]\s*|作者[：:]\s*.*?\s+)?', '', intro).strip()

        # 4. 封面圖片
        cover_url = None
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or ''
            if src and 'nocover' not in src and ('img.biquge' in src or 'cover' in src or src.endswith('.jpg')):
                cover_url = src if src.startswith('http') else f"https://m.biquge.tw{src}"
                break

        return {
            'book_id': self.book_id,
            'source': '筆趣閣',
            'title': to_traditional(clean_chapter_title(title)),
            'author': to_traditional(author),
            'intro': to_traditional(intro),
            'cover_url': cover_url,
            'dir_url': self.mobile_dir_url,
        }

    def get_chapter_list(self) -> list[dict]:
        html = self.fetch_url(self.mobile_dir_url)
        if not html:
            raise ValueError(f"無法存取目錄頁面: {self.mobile_dir_url}")

        soup = BeautifulSoup(html, 'html.parser')
        chapters = []
        seen_urls = set()

        # 尋找章節列表容器
        container = (
            soup.find('div', class_='list-chapter') or
            soup.find('div', class_='booklist') or
            soup.find('div', class_='autoheight')
        )

        a_tags = container.find_all('a', href=True) if container else soup.find_all('a', href=True)

        for a in a_tags:
            href = a['href']
            # 只取本小說各章節連結（例如 /book/1108442/78790108.html）
            if f"/book/{self.book_id}/" in href and href.endswith('.html'):
                full_url = href if href.startswith('http') else f"https://m.biquge.tw{href}"
                raw_title = a.get_text(strip=True)
                title = clean_chapter_title(raw_title)

                if full_url not in seen_urls and title:
                    seen_urls.add(full_url)
                    chapters.append({
                        'index': len(chapters) + 1,
                        'title': title,
                        'url': full_url
                    })

        return chapters

    def fetch_chapter_content(self, chapter: dict) -> dict:
        current_url = chapter['url']
        all_paragraphs = []
        final_title = chapter['title']

        visited_pages = set()

        # 支援可能的多分頁章節自動合併（例如 _2.html）
        while current_url and current_url not in visited_pages:
            visited_pages.add(current_url)
            html = self.fetch_url(current_url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')
            h1 = soup.find('h1')
            if h1:
                final_title = clean_chapter_title(h1.get_text(strip=True))

            # 清理段落
            paras = clean_chapter_html(soup)
            all_paragraphs.extend(paras)

            # 檢查是否有「下一頁」分頁連結
            next_link = soup.find('a', id='next_url')
            if next_link and '下一頁' in next_link.get_text():
                next_href = next_link.get('href')
                if next_href and next_href != current_url and next_href.endswith('.html'):
                    current_url = next_href if next_href.startswith('http') else f"https://m.biquge.tw{next_href}"
                    continue
            break

        return {
            'index': chapter['index'],
            'title': final_title,
            'paragraphs': all_paragraphs
        }


class TimotxtAdapter(BaseAdapter):
    """提莫書屋 (timotxt.com) 適配器"""
    def __init__(self, base_url: str, session: requests.Session):
        super().__init__(base_url, session)
        m = re.search(r'timotxt\.com/(\d+)', self.base_url)
        self.book_id = m.group(1) if m else "timotxt_book"
        self.dir_url = f"https://www.timotxt.com/{self.book_id}/dir"
        self.info_url = f"https://www.timotxt.com/{self.book_id}/"

    def get_book_metadata(self) -> dict:
        html = self.fetch_url(self.info_url) or self.fetch_url(self.dir_url)
        soup = BeautifulSoup(html or "", 'html.parser')

        # 1. 書名
        title = "未知小說"
        h1 = soup.find('h1')
        if h1:
            title = re.sub(r'[\-_]?(?:章節列表|提莫書屋).*', '', h1.get_text(strip=True)).strip()
        elif soup.title:
            title = re.sub(r'[\-_]?(?:章節列表|提莫書屋).*', '', soup.title.get_text(strip=True)).strip()

        # 2. 作者
        author = "佚名"
        for tag in soup.find_all(['span', 'p', 'a']):
            text = tag.get_text(strip=True)
            if '作者：' in text or '作者:' in text:
                m_auth = re.search(r'作者[：:]\s*([^\s分類更新\r\n]+)', text)
                if m_auth:
                    author = m_auth.group(1).strip()
                    break
        if len(author) > 20:
            author = author[:20]

        # 3. 簡介
        intro = ""
        intro_div = soup.find('div', class_='intro') or soup.find('div', class_='desc')
        if intro_div:
            for span in intro_div.find_all(['p', 'span']):
                if '主角：' in span.get_text():
                    span.decompose()
            intro = intro_div.get_text('\n', strip=True)

        # 4. 封面圖
        cover_url = None
        cover_div = soup.find('div', class_='cover')
        if cover_div and cover_div.find('img'):
            cover_url = cover_div.find('img').get('src')
        elif soup.find('img'):
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'thumb' in src or 'cover' in src:
                    cover_url = src
                    break

        return {
            'book_id': self.book_id,
            'source': '提莫書屋',
            'title': to_traditional(title),
            'author': to_traditional(author),
            'intro': to_traditional(deobfuscate_hangul(intro)),
            'cover_url': cover_url,
            'dir_url': self.dir_url,
        }

    def get_chapter_list(self) -> list[dict]:
        html = self.fetch_url(self.dir_url)
        if not html:
            raise ValueError(f"無法存取目錄頁面: {self.dir_url}")

        soup = BeautifulSoup(html, 'html.parser')
        chapters = []
        seen_urls = set()

        chap_ul = soup.find('ul', class_='all')
        if chap_ul:
            a_tags = chap_ul.find_all('a', href=True)
        else:
            chap_container = soup.find('div', class_='chaplist')
            a_tags = chap_container.find_all('a', href=True) if chap_container else soup.find_all('a', href=True)

        for a in a_tags:
            href = a['href']
            if 'dir' in href or href.endswith(f'/{self.book_id}/'):
                continue
            if f'/{self.book_id}/' not in href and not href.endswith('.html'):
                continue

            full_url = href if href.startswith('http') else f"https://www.timotxt.com{href}"
            title = deobfuscate_hangul(a.get_text(strip=True))

            if full_url not in seen_urls:
                seen_urls.add(full_url)
                chapters.append({
                    'index': len(chapters) + 1,
                    'title': title,
                    'url': full_url
                })

        return chapters

    def fetch_chapter_content(self, chapter: dict) -> dict:
        html = self.fetch_url(chapter['url'])
        if not html:
            return {
                'index': chapter['index'],
                'title': chapter['title'],
                'paragraphs': ["【本章內容抓取超時或失敗】"]
            }

        soup = BeautifulSoup(html, 'html.parser')
        h1 = soup.find('h1')
        h1_title = deobfuscate_hangul(h1.get_text(strip=True)) if h1 else ""
        dir_title = chapter.get('title', '')
        title = dir_title if len(dir_title) >= len(h1_title) else (h1_title or dir_title)

        paragraphs = clean_chapter_html(soup)

        return {
            'index': chapter['index'],
            'title': title,
            'paragraphs': paragraphs
        }


class Novel543Adapter(BaseAdapter):
    """稷下書院 (novel543.com) 適配器"""
    def __init__(self, base_url: str, session: requests.Session):
        super().__init__(base_url, session)
        m = re.search(r'novel543\.com/(\d+)', self.base_url)
        self.book_id = m.group(1) if m else "novel543_book"
        self.dir_url = f"https://www.novel543.com/{self.book_id}/dir"
        self.info_url = f"https://www.novel543.com/{self.book_id}/"

    def get_book_metadata(self) -> dict:
        html = self.fetch_url(self.info_url) or self.fetch_url(self.dir_url)
        soup = BeautifulSoup(html or "", 'html.parser')

        # 1. 書名
        title = "未知小說"
        h1 = soup.find('h1')
        if h1:
            title = re.sub(r'[\-_]?(?:章節列表|稷下書院|最新章節|在線閱讀).*', '', h1.get_text(strip=True)).strip()
        elif soup.title:
            title = re.sub(r'[\-_]?(?:章節列表|稷下書院|最新章節|在線閱讀).*', '', soup.title.get_text(strip=True)).strip()

        # 2. 作者
        author = "佚名"
        for tag in soup.find_all(['span', 'p', 'a']):
            text = tag.get_text(strip=True)
            if '作者：' in text or '作者:' in text:
                m_auth = re.search(r'作者[：:]\s*([^\s分類更新\r\n]+)', text)
                if m_auth:
                    author = m_auth.group(1).strip()
                    break
        if len(author) > 20:
            author = author[:20]

        # 3. 簡介
        intro = ""
        intro_div = soup.find('div', class_='intro') or soup.find('div', class_='desc')
        if intro_div:
            intro = intro_div.get_text('\n', strip=True)

        # 4. 封面圖
        cover_url = None
        cover_div = soup.find('div', class_='cover')
        if cover_div and cover_div.find('img'):
            cover_url = cover_div.find('img').get('src')
        elif soup.find('img'):
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'thumb' in src or 'cover' in src:
                    cover_url = src
                    break

        return {
            'book_id': self.book_id,
            'source': '稷下書院',
            'title': to_traditional(title),
            'author': to_traditional(author),
            'intro': to_traditional(intro),
            'cover_url': cover_url,
            'dir_url': self.dir_url,
        }

    def get_chapter_list(self) -> list[dict]:
        html = self.fetch_url(self.dir_url)
        if not html:
            raise ValueError(f"無法存取目錄頁面: {self.dir_url}")

        soup = BeautifulSoup(html, 'html.parser')
        chapters = []
        seen_urls = set()

        chap_ul = soup.find('ul', class_='all')
        if chap_ul:
            a_tags = chap_ul.find_all('a', href=True)
        else:
            chap_container = soup.find('div', class_='chaplist')
            a_tags = chap_container.find_all('a', href=True) if chap_container else soup.find_all('a', href=True)

        for a in a_tags:
            href = a['href']
            if 'dir' in href or href.endswith(f'/{self.book_id}/'):
                continue
            if f'/{self.book_id}/' not in href and not href.endswith('.html'):
                continue

            full_url = href if href.startswith('http') else f"https://www.novel543.com{href}"
            raw_title = a.get_text(strip=True)
            title = clean_chapter_title(raw_title)

            if full_url not in seen_urls:
                seen_urls.add(full_url)
                chapters.append({
                    'index': len(chapters) + 1,
                    'title': title,
                    'url': full_url
                })

        return chapters

    def fetch_chapter_content(self, chapter: dict) -> dict:
        current_url = chapter['url']
        all_paragraphs = []
        final_title = chapter['title']

        visited_pages = set()

        # 解析基礎檔案名（如 8096_1）以便識別多分頁（如 8096_1_2.html）
        m_base = re.search(r'/([^/]+)\.html', current_url)
        base_name = m_base.group(1) if m_base else ""

        while current_url and current_url not in visited_pages:
            visited_pages.add(current_url)
            html = self.fetch_url(current_url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')
            h1 = soup.find('h1')
            if h1:
                final_title = clean_chapter_title(h1.get_text(strip=True))

            # 清理段落
            paras = clean_chapter_html(soup)
            all_paragraphs.extend(paras)

            # 尋找是否還有下一頁 (例如 8096_1_2.html)
            next_url_candidate = None
            for a in soup.find_all('a', href=True):
                if '下一' in a.get_text():
                    href = a['href']
                    full_href = href if href.startswith('http') else f"https://www.novel543.com{href}"
                    # 只有當下一個連結屬於同一章節的子頁面時才繼續抓
                    if base_name and f"{base_name}_" in href:
                        next_url_candidate = full_href
                        break

            if next_url_candidate and next_url_candidate not in visited_pages:
                current_url = next_url_candidate
            else:
                break

        return {
            'index': chapter['index'],
            'title': final_title,
            'paragraphs': all_paragraphs
        }


class PO18Adapter(BaseAdapter):
    """PO18 臉紅心跳 (po18.tw) 適配器"""
    def __init__(self, base_url: str, session: requests.Session):
        super().__init__(base_url, session)
        m = re.search(r'po18\.tw/books/(\d+)', self.base_url)
        self.book_id = m.group(1) if m else "po18_book"
        self.articles_url = f"https://www.po18.tw/books/{self.book_id}/articles"
        self.book_info_url = f"https://www.po18.tw/books/{self.book_id}"

        # 載入 PO18 專屬憑證 Cookie
        self._load_cookies()

    def _load_cookies(self):
        cookies_path = os.path.join(os.path.dirname(__file__), "po18_cookies.json")
        cookies = {}
        if os.path.exists(cookies_path):
            try:
                with open(cookies_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
            except Exception as e:
                print(f"[PO18] 讀取 cookie 失敗: {e}")

        if cookies:
            self.session.cookies.update(cookies)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.po18.tw/'
        })

    def get_book_metadata(self) -> dict:
        html = self.fetch_url(self.book_info_url)
        if not html:
            html = self.fetch_url(self.articles_url)

        soup = BeautifulSoup(html or "", 'html.parser')

        # 1. 書名
        title = "未知小說"
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)

        # 2. 作者
        author = "佚名"
        h2 = soup.find('h2')
        if h2:
            author = h2.get_text(strip=True)

        # 3. 簡介
        intro = ""
        intro_elem = soup.find('div', class_='B_I_content') or soup.find('div', class_='book_intro')
        if intro_elem:
            intro = intro_elem.get_text('\n', strip=True)

        # 4. 封面圖片
        cover_url = None
        cover_elem = soup.find('div', class_='book_cover')
        if cover_elem:
            img = cover_elem.find('img')
            if img and img.get('src'):
                cover_url = img['src']

        return {
            'book_id': self.book_id,
            'source': 'PO18臉紅心跳',
            'title': to_traditional(clean_chapter_title(title)),
            'author': to_traditional(author),
            'intro': to_traditional(intro),
            'cover_url': cover_url,
            'dir_url': self.articles_url,
        }

    def get_chapter_list(self) -> list[dict]:
        chapters = []
        page = 1
        max_page = 1

        while page <= max_page:
            url = f"https://www.po18.tw/books/{self.book_id}/articles?page={page}"
            html = self.fetch_url(url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            # 解析分頁標籤上限
            page_div = soup.find('div', class_='page')
            if page_div:
                page_nums = re.findall(r'page=(\d+)', str(page_div))
                if page_nums:
                    max_page = max(max_page, max([int(p) for p in page_nums]))

            items = soup.find_all('div', class_='c_l')
            if not items:
                break

            for item in items:
                name_div = item.find('div', class_='l_chaptname')
                if not name_div:
                    continue
                a = name_div.find('a')
                if not a or not a.get('href'):
                    # 若無超連結，代表為付費或未解鎖章節，依法略過
                    continue

                raw_title = a.get_text(strip=True)
                title = clean_chapter_title(raw_title)
                href = a['href']
                full_url = href if href.startswith('http') else f"https://www.po18.tw{href}"

                chapters.append({
                    'index': len(chapters) + 1,
                    'title': title,
                    'url': full_url
                })

            page += 1

        return chapters

    def fetch_chapter_content(self, chapter: dict) -> dict:
        m = re.search(r'/articles/(\d+)', chapter['url'])
        if not m:
            return {'index': chapter['index'], 'title': chapter['title'], 'paragraphs': []}

        article_id = m.group(1)
        content_url = f"https://www.po18.tw/books/{self.book_id}/articlescontent/{article_id}"
        headers = {
            'Referer': chapter['url'],
            'X-Requested-With': 'XMLHttpRequest'
        }

        paragraphs = []
        for attempt in range(1, 4):
            try:
                resp = self.session.get(content_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    # 若章節包含圖片插圖 (例如設定圖、插畫章節)，保留插圖標記
                    for img in soup.find_all('img'):
                        src = img.get('src') or ''
                        if src:
                            img.replace_with(f"\n【插圖：{src}】\n")

                    # 清理 PO18 內嵌隨機版權字串、標題與腳本
                    for tag in soup.find_all(['blockquote', 'h1', 'script', 'style']):
                        tag.decompose()

                    # 逐行拆分正文並反混淆與轉繁體
                    raw_lines = soup.get_text('\n').splitlines()
                    for line in raw_lines:
                        clean_line = to_traditional(deobfuscate_hangul(line.strip()))
                        if clean_line:
                            paragraphs.append(clean_line)
                    break
                elif resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * attempt)
            except Exception as e:
                time.sleep(1.0 * attempt)

        return {
            'index': chapter['index'],
            'title': chapter['title'],
            'paragraphs': paragraphs
        }


class IxdzsAdapter(BaseAdapter):
    """愛下電子書 (ixdzs.tw / ixdzs.com) 適配器"""
    def __init__(self, base_url: str, session: requests.Session):
        super().__init__(base_url, session)
        m = re.search(r'ixdzs\.(?:tw|com)/read/(\d+)', self.base_url)
        self.book_id = m.group(1) if m else "ixdzs_book"
        self.dir_url = f"https://ixdzs.tw/read/{self.book_id}/"

    def get_book_metadata(self) -> dict:
        html = self.fetch_url(self.dir_url)
        soup = BeautifulSoup(html or "", 'html.parser')

        # 1. 書名
        title = "未知小說"
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
        else:
            meta_t = soup.find('meta', property='og:title')
            if meta_t and meta_t.get('content'):
                title = meta_t['content'].strip()

        # 2. 作者
        author = "佚名"
        author_el = soup.find(class_='bauthor')
        if author_el:
            author = author_el.get_text(strip=True)
        else:
            meta_a = soup.find('meta', property='og:novel:author')
            if meta_a and meta_a.get('content'):
                author = meta_a['content'].strip()

        # 3. 簡介
        intro = ""
        meta_d = soup.find('meta', {'name': 'description'})
        if meta_d and meta_d.get('content'):
            intro = meta_d['content'].strip()
        else:
            intro_el = soup.find(class_='intro') or soup.find(class_='desc') or soup.find(class_='l-p2')
            if intro_el:
                intro = intro_el.get_text(strip=True)

        # 4. 封面圖
        cover_url = ""
        cover_img = soup.select_one('.n-img img') or soup.select_one('.cover img') or soup.select_one('.l-img img')
        if cover_img:
            cover_url = cover_img.get('src') or ''
        if not cover_url:
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if 'ixdzs.com' in src and ('.jpg' in src or '.png' in src):
                    cover_url = src
                    break

        return {
            'book_id': self.book_id,
            'source': '愛下電子書',
            'title': to_traditional(title),
            'author': to_traditional(author),
            'intro': to_traditional(intro),
            'cover_url': cover_url,
            'dir_url': self.dir_url,
        }

    def get_chapter_list(self) -> list[dict]:
        html = self.fetch_url(self.dir_url)
        soup = BeautifulSoup(html or "", 'html.parser')
        chapters = []
        seen_urls = set()

        # 目錄列表解析 id="a-list" (class="clist")
        container = soup.find(id='a-list') or soup.find(class_='clist') or soup
        idx = 1
        for a in container.find_all('a', href=True):
            href = a['href'].strip()
            m = re.search(r'/read/\d+/p\d+\.html', href)
            if not m:
                continue

            raw_title = a.get_text(strip=True)
            if not raw_title or raw_title in ("立即閱讀", "首頁", "目錄"):
                continue

            full_url = urllib.parse.urljoin("https://ixdzs.tw", href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            clean_title = clean_chapter_title(raw_title)
            chapters.append({
                'index': idx,
                'title': to_traditional(clean_title),
                'url': full_url,
                'chapter_id': href
            })
            idx += 1

        return chapters

    def fetch_chapter_content(self, chapter: dict) -> dict:
        url = chapter['url']
        html = self.fetch_url(url)
        if not html:
            return {
                'index': chapter['index'],
                'title': chapter['title'],
                'paragraphs': [f"【本章內容抓取超時: {chapter['title']}】"]
            }

        soup = BeautifulSoup(html, 'html.parser')
        content_div = soup.find(class_='page-content') or soup.find(class_='content') or soup.find('article')
        if not content_div:
            return {
                'index': chapter['index'],
                'title': chapter['title'],
                'paragraphs': [f"【無法解析章節內容: {chapter['title']}】"]
            }

        # 移除廣告、腳本、樣式與不相干標籤
        for tag in content_div.find_all(['script', 'style', 'div', 'h1', 'h2', 'h3']):
            tag.decompose()

        paragraphs = []
        p_tags = content_div.find_all('p')
        if p_tags:
            for p in p_tags:
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(to_traditional(text))
        else:
            lines = content_div.get_text('\n').splitlines()
            for line in lines:
                clean = line.strip()
                if clean:
                    paragraphs.append(to_traditional(clean))

        return {
            'index': chapter['index'],
            'title': chapter['title'],
            'paragraphs': paragraphs
        }


def get_adapter(target_url: str, session: requests.Session) -> BaseAdapter:
    """根據 URL 判斷並返回相應的站點適配器"""
    url_lower = target_url.lower()
    if 'ixdzs.tw' in url_lower or 'ixdzs.com' in url_lower or 'ixdzs' in url_lower:
        return IxdzsAdapter(target_url, session)
    elif 'po18.tw' in url_lower:
        return PO18Adapter(target_url, session)
    elif 'biquge.tw' in url_lower:
        return BiqugeAdapter(target_url, session)
    elif 'novel543.com' in url_lower:
        return Novel543Adapter(target_url, session)
    elif 'timotxt.com' in url_lower:
        return TimotxtAdapter(target_url, session)
    else:
        # 預設辨識
        if 'ixdzs' in url_lower:
            return IxdzsAdapter(target_url, session)
        elif 'po18' in url_lower:
            return PO18Adapter(target_url, session)
        elif 'biquge' in url_lower:
            return BiqugeAdapter(target_url, session)
        elif '543' in url_lower:
            return Novel543Adapter(target_url, session)
        return TimotxtAdapter(target_url, session)
