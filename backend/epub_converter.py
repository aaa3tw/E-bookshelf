"""
EPUB / 文字繁簡偵測與繁體中文自動轉換模組 (epub_converter.py)
功能：
1. 自動偵測 EPUB / TXT 是否為簡體中文
2. 自動將簡體中文 EPUB 轉為繁體中文（台灣標準繁體 zh-TW / s2tw）
3. 支援就地替換或輸出為新檔案，自動保留所有版面樣式、封面與結構
"""

import os
import io
import shutil
import zipfile
import opencc

try:
    _cc_s2tw = opencc.OpenCC('s2tw')
    _cc_s2t = opencc.OpenCC('s2t')
    _cc_t2s = opencc.OpenCC('t2s')
except Exception as e:
    print(f"[Warning] OpenCC 初始化失敗: {e}")
    _cc_s2tw = None
    _cc_s2t = None
    _cc_t2s = None


def is_simplified_chinese_text(text: str, sample_size: int = 3000) -> bool:
    """判斷文字是否偏向簡體中文"""
    if not text or not _cc_s2t or not _cc_t2s:
        return False

    chars = [c for c in text if '\u4e00' <= c <= '\u9fff'][:sample_size]
    if len(chars) < 20:
        return False

    s_diff = sum(1 for c in chars if _cc_s2t.convert(c) != c)  # 原本是簡體字
    t_diff = sum(1 for c in chars if _cc_t2s.convert(c) != c)  # 原本是繁體字

    return s_diff > t_diff and s_diff > 10


def is_simplified_chinese_epub(epub_path: str, max_samples: int = 3000) -> bool:
    """檢測 EPUB 檔案內部章節正文是否為簡體中文"""
    if not os.path.exists(epub_path) or not _cc_s2t or not _cc_t2s:
        return False

    s_diff = 0
    t_diff = 0
    total = 0

    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            for name in zf.namelist():
                name_lower = name.lower()
                if name_lower.endswith(('.xhtml', '.html', '.htm')):
                    try:
                        raw = zf.read(name).decode('utf-8', errors='ignore')
                        chars = [c for c in raw if '\u4e00' <= c <= '\u9fff'][:1500]
                        total += len(chars)
                        for c in chars:
                            if _cc_s2t.convert(c) != c:
                                s_diff += 1
                            if _cc_t2s.convert(c) != c:
                                t_diff += 1
                    except Exception:
                        pass
                    if total >= max_samples:
                        break
    except Exception as e:
        print(f"[Warning] 讀取 EPUB 進行語言偵測失敗: {e}")
        return False

    return s_diff > t_diff and s_diff > 15


def convert_text_to_traditional(text: str) -> str:
    """轉換純文字為繁體中文"""
    if not text or not _cc_s2tw:
        return text
    try:
        return _cc_s2tw.convert(text)
    except Exception:
        return text


def convert_epub_to_traditional(epub_path: str, output_path: str | None = None) -> str:
    """
    將 EPUB 內部所有 HTML、XHTML、OPF、NCX 文字檔案轉換為繁體中文 (s2tw)。
    若未指定 output_path 則就地替換原檔案。
    """
    if not os.path.exists(epub_path) or not _cc_s2tw:
        return epub_path

    in_place = False
    if not output_path or os.path.abspath(epub_path) == os.path.abspath(output_path):
        output_path = epub_path
        in_place = True

    temp_path = epub_path + ".converting.tmp"

    try:
        with zipfile.ZipFile(epub_path, 'r') as zin, zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                content = zin.read(item.filename)
                name_lower = item.filename.lower()

                # 文字與元數據檔案
                if name_lower.endswith(('.xhtml', '.html', '.htm', '.opf', '.ncx', '.xml', '.txt')):
                    try:
                        text = content.decode('utf-8')
                        text = _cc_s2tw.convert(text)
                        # 將語言標籤修正為繁體中文
                        text = text.replace('zh-CN', 'zh-TW').replace('zh-Hans', 'zh-Hant')
                        content = text.encode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            text = content.decode('gbk')
                            text = _cc_s2tw.convert(text)
                            text = text.replace('zh-CN', 'zh-TW').replace('zh-Hans', 'zh-Hant')
                            content = text.encode('utf-8')
                        except Exception:
                            pass
                    except Exception:
                        pass

                zout.writestr(item, content)

        if in_place:
            shutil.move(temp_path, output_path)
        else:
            if os.path.exists(output_path):
                os.remove(output_path)
            shutil.move(temp_path, output_path)

        return output_path

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise RuntimeError(f"轉換 EPUB 為繁體中文失敗: {e}")


def auto_convert_epub_if_simplified(epub_path: str) -> bool:
    """
    如果 EPUB 是簡體中文，自動轉換為繁體中文並覆蓋原檔。
    若成功轉換返回 True，若原本就是繁體或無法轉換則返回 False。
    """
    if not os.path.exists(epub_path):
        return False

    if is_simplified_chinese_epub(epub_path):
        print(f"[繁簡轉換] 檢測到《{os.path.basename(epub_path)}》為簡體中文，正在自動翻譯轉換為繁體中文 (zh-TW)...")
        convert_epub_to_traditional(epub_path)
        print(f"[繁簡轉換] ✓《{os.path.basename(epub_path)}》已成功轉換為繁體中文！")
        return True
    return False
