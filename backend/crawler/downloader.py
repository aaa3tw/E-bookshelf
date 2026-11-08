"""
核心下載與爬取模組 (downloader.py)
整合多站點適配器架構
"""

import os
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from tqdm import tqdm

try:
    from .adapters import get_adapter
    from .cleaner import deobfuscate_hangul, to_traditional
except ImportError:
    from adapters import get_adapter
    from cleaner import deobfuscate_hangul, to_traditional

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CACHE_DIR = os.path.join(BASE_DIR, ".novel_cache")


def is_valid_paragraphs(paras: list) -> bool:
    """檢查段落是否為有效正文（非空且不為錯誤提示）"""
    if not paras or len(paras) == 0:
        return False
    if len(paras) == 1 and any(err in paras[0] for err in ["【本章內容抓取超時", "【下載異常"]):
        return False
    return True


class NovelDownloader:
    def __init__(self, base_url: str, cache_dir: str = DEFAULT_CACHE_DIR, max_workers: int = 5):
        self.base_url = base_url.strip()
        self.cache_dir = cache_dir
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        # 取得對應站點適配器
        self.adapter = get_adapter(self.base_url, self.session)
        self.site_name = self.adapter.__class__.__name__.replace("Adapter", "").lower()
        self.book_id = self.adapter.book_id

        # 依站點與書號建立獨立快取資料夾
        self.book_cache_dir = os.path.join(self.cache_dir, f"{self.site_name}_{self.book_id}")
        # 相容歷史舊格式快取目錄 (如直接為純數字 2111601572)
        if not os.path.exists(self.book_cache_dir):
            legacy_dir = os.path.join(self.cache_dir, self.book_id)
            if os.path.exists(legacy_dir):
                self.book_cache_dir = legacy_dir
        os.makedirs(self.book_cache_dir, exist_ok=True)

    def get_book_metadata(self) -> dict:
        """
        抓取書籍基本資訊（書名、作者、簡介、封面圖 URL）
        """
        meta_cache_path = os.path.join(self.book_cache_dir, "meta.json")
        if os.path.exists(meta_cache_path):
            try:
                with open(meta_cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    if cached.get('author') and len(cached['author']) <= 25:
                        cached['title'] = to_traditional(cached.get('title', ''))
                        cached['author'] = to_traditional(cached.get('author', ''))
                        cached['intro'] = to_traditional(cached.get('intro', ''))
                        return cached
            except Exception:
                pass

        book_info = self.adapter.get_book_metadata()
        book_info['title'] = to_traditional(book_info.get('title', ''))
        book_info['author'] = to_traditional(book_info.get('author', ''))
        book_info['intro'] = to_traditional(book_info.get('intro', ''))

        # 儲存快取
        with open(meta_cache_path, 'w', encoding='utf-8') as f:
            json.dump(book_info, f, ensure_ascii=False, indent=2)

        return book_info

    def get_chapter_list(self) -> list[dict]:
        """
        獲取正文章節目錄列表
        """
        return self.adapter.get_chapter_list()

    def download_single_chapter(self, chapter: dict) -> dict:
        """
        下載單一章節（若快取存在且非空則直接讀取）
        """
        chap_idx = chapter['index']
        cache_file = os.path.join(self.book_cache_dir, f"chap_{chap_idx:05d}.json")

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    paras = cached.get('paragraphs', [])
                    # 只有當快取中的段落有效時，才視為命中快取
                    if is_valid_paragraphs(paras):
                        # 自我修復：檢查快取內文是否含有舊韓文，若有則重新經過最新字典修復並覆寫存檔
                        raw_p_text = ''.join(paras)
                        if re.search(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]', raw_p_text):
                            cached['paragraphs'] = [deobfuscate_hangul(p) for p in paras]
                            cached['title'] = deobfuscate_hangul(cached.get('title', ''))
                            with open(cache_file, 'w', encoding='utf-8') as f_out:
                                json.dump(cached, f_out, ensure_ascii=False)
                        cached['title'] = to_traditional(cached.get('title', ''))
                        cached['paragraphs'] = [to_traditional(p) for p in cached.get('paragraphs', [])]
                        return cached
            except Exception:
                pass

        # 透過適配器抓取內文
        result = self.adapter.fetch_chapter_content(chapter)
        if result:
            result['title'] = to_traditional(result.get('title', ''))
            result['paragraphs'] = [to_traditional(p) for p in result.get('paragraphs', [])]

        # 關鍵：只有在成功抓取到有效段落內容時才存入快取，避免快取中毒
        if is_valid_paragraphs(result.get('paragraphs')):
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False)

        return result

    def download_all_chapters(self, chapters: list[dict], limit: int | None = None, progress_callback=None) -> list[dict]:
        """
        多執行緒下載所有章節，並包含自動補抓機制
        """
        if limit:
            chapters = chapters[:limit]

        total = len(chapters)
        results = [None] * total
        completed_count = 0

        print(f"\n[Downloader] 開始平行下載共 {total} 章（執行緒: {self.max_workers}）...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(self.download_single_chapter, chap): i
                for i, chap in enumerate(chapters)
            }

            with tqdm(total=total, desc="下載進度", unit="章") as pbar:
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        res = future.result()
                        results[idx] = res
                    except Exception as e:
                        print(f"\n[Error] 下載章節第 {idx+1} 章失敗: {e}")
                        results[idx] = {
                            'index': idx + 1,
                            'title': chapters[idx]['title'],
                            'paragraphs': []
                        }
                    completed_count += 1
                    pbar.update(1)
                    if progress_callback:
                        try:
                            chap_title = chapters[idx].get('title', f"第 {idx+1} 章")
                            progress_callback(completed_count, total, chap_title)
                        except Exception:
                            pass

        # 自動檢查並進行漏抓補償（最多嘗試 3 輪補抓）
        for retry_round in range(1, 4):
            missing_indices = [
                i for i, r in enumerate(results)
                if not r or not is_valid_paragraphs(r.get('paragraphs'))
            ]
            if not missing_indices:
                break

            print(f"\n[Downloader] 檢測到 {len(missing_indices)} 個章節內容無效/超時，正在進行第 {retry_round} 輪自動補抓...")
            time.sleep(1.0)
            for m_idx in missing_indices:
                try:
                    re_result = self.adapter.fetch_chapter_content(chapters[m_idx])
                    if is_valid_paragraphs(re_result.get('paragraphs')):
                        results[m_idx] = re_result
                        cache_file = os.path.join(self.book_cache_dir, f"chap_{m_idx+1:05d}.json")
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(re_result, f, ensure_ascii=False)
                        print(f"  成功補抓第 {m_idx+1} 章: {re_result['title']}")
                except Exception as e:
                    print(f"  補抓第 {m_idx+1} 章失敗: {e}")
                time.sleep(0.5)

        return results

    def fetch_cover_bytes(self, cover_url: str | None) -> bytes | None:
        """下載封面圖片位元組"""
        if not cover_url:
            return None
        try:
            resp = self.session.get(cover_url, timeout=10)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            print(f"[Downloader] 封面圖下載失敗: {e}")
        return None
