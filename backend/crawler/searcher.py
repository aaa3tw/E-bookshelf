"""
書名搜尋與網址解析模組 (searcher.py)
支援多站點：
1. 提莫書屋 (timotxt.com)
2. 筆趣閣 (m.biquge.tw / www.biquge.tw)
"""

import re
import urllib.parse
import requests
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def parse_input_target(input_text: str) -> str | None:
    """
    檢查輸入是否直接為 URL 或包含書號
    若為 URL 則返回標準的目錄頁網址
    """
    text = input_text.strip()
    if not text:
        return None

    # 1. 筆趣閣 (biquge.tw) 網址匹配
    m_bq = re.search(r'biquge\.tw/book/(\d+)', text)
    if m_bq:
        book_id = m_bq.group(1)
        return f"https://m.biquge.tw/book/{book_id}/"

    # 2. 稷下書院 (novel543.com) 網址匹配
    m_543 = re.search(r'novel543\.com/(\d+)', text)
    if m_543:
        book_id = m_543.group(1)
        return f"https://www.novel543.com/{book_id}/dir"

    # 3. 提莫書屋 (timotxt.com) 網址匹配
    m_timo = re.search(r'timotxt\.com/(\d+)', text)
    if m_timo:
        book_id = m_timo.group(1)
        return f"https://www.timotxt.com/{book_id}/dir"

    # 4. PO18 臉紅心跳 (po18.tw) 網址匹配
    m_po18 = re.search(r'po18\.tw/books/(\d+)', text)
    if m_po18:
        book_id = m_po18.group(1)
        return f"https://www.po18.tw/books/{book_id}/articles"

    # 5. 愛下電子書 (ixdzs.tw / ixdzs.com) 網址匹配
    m_ix = re.search(r'ixdzs\.(?:tw|com)/read/(\d+)', text)
    if m_ix:
        book_id = m_ix.group(1)
        return f"https://ixdzs.tw/read/{book_id}/"

    # 6. 其他完整網址直接返回
    if text.startswith('http://') or text.startswith('https://'):
        return text

    # 4. 純數字書號 (若使用者直接輸入 1108442 或 2111601572)
    if text.isdigit() and len(text) >= 6:
        # 預設先檢查筆趣閣是否存在
        try:
            r = requests.get(f"https://m.biquge.tw/book/{text}/", headers=HEADERS, timeout=3)
            if r.status_code == 200 and '筆趣閣' in r.text:
                return f"https://m.biquge.tw/book/{text}/"
        except Exception:
            pass
        # 否則作為 timotxt
        return f"https://www.timotxt.com/{text}/dir"

    return None


def search_biquge(book_name: str) -> list[dict]:
    """搜尋筆趣閣 (m.biquge.tw) 站內搜尋"""
    results = []
    seen_ids = set()
    encoded_kw = urllib.parse.quote(book_name.strip())
    search_url = f"https://m.biquge.tw/search/?searchkey={encoded_kw}"

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 尋找所有書名連結 /book/{id}.html 或 /book/{id}/
            for a in soup.find_all('a', href=True):
                href = a['href']
                m = re.search(r'/book/(\d+)(?:\.html|/)', href)
                title = a.get_text(strip=True)
                if m and title and len(title) > 1:
                    book_id = m.group(1)
                    if book_id not in seen_ids and not title.startswith("第") and not "章" in title[:4]:
                        seen_ids.add(book_id)
                        results.append({
                            'source': '筆趣閣',
                            'title': title,
                            'book_id': book_id,
                            'dir_url': f"https://m.biquge.tw/book/{book_id}/",
                            'book_url': f"https://m.biquge.tw/book/{book_id}.html",
                        })
    except Exception as e:
        print(f"[Searcher] 筆趣閣站內搜尋失敗: {e}")

    return results


def search_timotxt_ddg(book_name: str) -> list[dict]:
    """透過 DuckDuckGo 檢索 timotxt.com"""
    results = []
    seen_ids = set()
    query = f"site:timotxt.com {book_name.strip()}"
    encoded_q = urllib.parse.quote(query)
    ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

    try:
        session = cffi_requests.Session(impersonate="chrome120")
        resp = session.get(ddg_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for result_div in soup.find_all('div', class_='result'):
                title_link = result_div.find('a', class_='result__a')
                if not title_link:
                    continue

                raw_href = title_link.get('href', '')
                title_text = title_link.get_text(strip=True)

                real_url = raw_href
                if 'uddg=' in raw_href:
                    match_url = re.search(r'uddg=([^&]+)', raw_href)
                    if match_url:
                        real_url = urllib.parse.unquote(match_url.group(1))

                match_id = re.search(r'timotxt\.com/(\d+)', real_url)
                if match_id:
                    book_id = match_id.group(1)
                    if book_id not in seen_ids:
                        seen_ids.add(book_id)
                        clean_title = re.sub(r'[\-_]?(?:章節列表|提莫書屋|最新章節|在線閱讀).*', '', title_text).strip()
                        if not clean_title:
                            clean_title = book_name
                        results.append({
                            'source': '提莫書屋',
                            'title': clean_title,
                            'book_id': book_id,
                            'dir_url': f"https://www.timotxt.com/{book_id}/dir",
                            'book_url': f"https://www.timotxt.com/{book_id}/",
                        })
    except Exception as e:
        print(f"[Searcher] DuckDuckGo 檢索失敗: {e}")

    return results


def search_novel543_ddg(book_name: str) -> list[dict]:
    """透過 DuckDuckGo 檢索 novel543.com"""
    results = []
    seen_ids = set()
    query = f"site:novel543.com {book_name.strip()}"
    encoded_q = urllib.parse.quote(query)
    ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

    try:
        session = cffi_requests.Session(impersonate="chrome120")
        resp = session.get(ddg_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for result_div in soup.find_all('div', class_='result'):
                title_link = result_div.find('a', class_='result__a')
                if not title_link:
                    continue

                raw_href = urllib.parse.unquote(title_link.get('href', ''))
                title_text = title_link.get_text(strip=True)

                match_id = re.search(r'novel543\.com/(\d+)', raw_href)
                if match_id:
                    book_id = match_id.group(1)
                    if book_id not in seen_ids:
                        seen_ids.add(book_id)
                        clean_title = re.sub(r'[\-_]?(?:章節列表|稷下書院|最新章節|在線閱讀).*', '', title_text).strip()
                        if not clean_title:
                            clean_title = book_name
                        results.append({
                            'source': '稷下書院',
                            'title': clean_title,
                            'book_id': book_id,
                            'dir_url': f"https://www.novel543.com/{book_id}/dir",
                            'book_url': f"https://www.novel543.com/{book_id}/",
                        })
    except Exception as e:
        print(f"[Searcher] DuckDuckGo 檢索 novel543 失敗: {e}")

    return results


def search_ixdzs(book_name: str) -> list[dict]:
    """愛下電子書 (ixdzs.tw) 站內搜尋"""
    results = []
    seen_ids = set()
    try:
        resp = requests.get(
            "https://ixdzs.tw/bsearch",
            params={"q": book_name.strip()},
            headers=HEADERS,
            timeout=8
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
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
                book_id = m.group(1)
                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)

                title = a.get_text(strip=True)
                author_el = li.find(class_='bauthor')
                author = author_el.get_text(strip=True) if author_el else '佚名'
                intro_el = li.find('p', class_='l-p2')
                intro = intro_el.get_text(strip=True) if intro_el else ''
                img_el = li.select_one('.l-img img')
                cover_url = img_el.get('src', '') if img_el else ''

                results.append({
                    'source': '愛下電子書',
                    'title': title,
                    'author': author,
                    'intro': intro,
                    'cover_url': cover_url,
                    'book_id': book_id,
                    'dir_url': f"https://ixdzs.tw/read/{book_id}/",
                    'book_url': f"https://ixdzs.tw/read/{book_id}/",
                })
    except Exception as e:
        print(f"[Searcher] 愛下電子書搜尋出錯: {e}")
    return results


def search_by_book_name(book_name: str) -> list[dict]:
    """
    聚合多個小說網站進行搜尋
    返回候選書籍列表: [{'source': ..., 'title': ..., 'book_id': ..., 'dir_url': ...}]
    """
    results = []
    # 1. 愛下電子書
    ix_results = search_ixdzs(book_name)
    results.extend(ix_results[:4])

    # 2. 筆趣閣
    bq_results = search_biquge(book_name)
    results.extend(bq_results[:4])

    # 3. 稷下書院 (novel543)
    n543_results = search_novel543_ddg(book_name)
    results.extend(n543_results[:4])

    # 4. 提莫書屋
    timo_results = search_timotxt_ddg(book_name)
    results.extend(timo_results[:3])

    return results
