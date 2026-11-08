import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def test_biquge():
    print("=== Testing Biquge ===")
    url = "https://m.biquge.tw/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        print("Status:", r.status_code)
        soup = BeautifulSoup(r.text, 'html.parser')
        books = []
        seen = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            m = re.search(r'/book/(\d+)(?:\.html|/)', href)
            title = a.get_text(strip=True)
            if m and title and len(title) > 1 and not title.startswith("第") and not "章" in title[:4]:
                bid = m.group(1)
                if bid not in seen:
                    seen.add(bid)
                    books.append({"id": bid, "title": title, "url": f"https://m.biquge.tw/book/{bid}/"})
        print(f"Found {len(books)} books. First 5:", books[:5])
    except Exception as e:
        print("Biquge failed:", e)

def test_novel543():
    print("\n=== Testing Novel543 ===")
    url = "https://www.novel543.com/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        print("Status:", r.status_code)
        soup = BeautifulSoup(r.text, 'html.parser')
        books = []
        seen = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            m = re.search(r'/(\d+)/?(?:dir)?', href)
            title = a.get_text(strip=True)
            if m and title and len(title) > 1 and len(m.group(1)) >= 6:
                bid = m.group(1)
                if bid not in seen and not "章" in title:
                    seen.add(bid)
                    books.append({"id": bid, "title": title, "url": f"https://www.novel543.com/{bid}/dir"})
        print(f"Found {len(books)} books. First 5:", books[:5])
    except Exception as e:
        print("Novel543 failed:", e)

def test_timotxt():
    print("\n=== Testing Timotxt ===")
    url = "https://www.timotxt.com/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        print("Status:", r.status_code)
        soup = BeautifulSoup(r.text, 'html.parser')
        books = []
        seen = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            m = re.search(r'/(\d+)/dir', href)
            title = a.get_text(strip=True)
            if m and title and len(title) > 1:
                bid = m.group(1)
                if bid not in seen:
                    seen.add(bid)
                    books.append({"id": bid, "title": title, "url": f"https://www.timotxt.com/{bid}/dir"})
        print(f"Found {len(books)} books. First 5:", books[:5])
    except Exception as e:
        print("Timotxt failed:", e)

if __name__ == "__main__":
    test_biquge()
    test_novel543()
    test_timotxt()
