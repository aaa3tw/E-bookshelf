"""
檔案匯出模組 (exporter.py)
支援：
1. 匯出乾淨格式化的 TXT 檔案
2. 匯出標準 EPUB 檔案（含封面圖片、目錄導航、內文 CSS 樣式、中繼資料）
"""

import os
import re
from ebooklib import epub
try:
    from .cleaner import to_traditional
except ImportError:
    from cleaner import to_traditional


def export_txt(book_info: dict, chapters: list[dict], output_path: str):
    """
    匯出為純文字 TXT 檔案
    book_info: {'title': str, 'author': str, 'intro': str}
    chapters: [{'title': str, 'paragraphs': list[str]}]
    """
    title_str = to_traditional(book_info.get('title', '未知書名'))
    author_str = to_traditional(book_info.get('author', '佚名'))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        # 書籍資訊檔頭
        f.write(f"《{title_str}》\n")
        if book_info.get('author'):
            f.write(f"作者：{author_str}\n")
        f.write("=" * 40 + "\n\n")

        if book_info.get('intro'):
            f.write("【作品簡介】\n")
            # 簡介每行縮排
            for line in to_traditional(book_info['intro']).splitlines():
                line = line.strip()
                if line:
                    f.write(f"　　{line}\n")
            f.write("\n" + "=" * 40 + "\n\n")

        # 逐章寫入
        for chap in chapters:
            chap_title = to_traditional(chap.get('title', ''))
            f.write(f"\n\n{chap_title}\n\n")
            for para in chap.get('paragraphs', []):
                p = to_traditional(para.strip())
                if p:
                    f.write(f"　　{p}\n\n")

    print(f"[Exporter] TXT 已成功儲存至: {output_path}")


def export_epub(book_info: dict, chapters: list[dict], output_path: str, cover_bytes: bytes | None = None):
    """
    匯出為標準 EPUB 電子書
    支援內嵌封面、目錄層級與 CSS 閱讀樣式
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    book = epub.EpubBook()

    title_str = to_traditional(book_info.get('title', '小說'))
    author_str = to_traditional(book_info.get('author', '佚名'))

    # 1. 書籍元資料
    book_id = book_info.get('book_id', 'novel-download-1')
    book.set_identifier(f"timotxt-{book_id}")
    book.set_title(title_str)
    book.set_language('zh-TW')
    book.add_author(author_str)

    # 2. 閱讀 CSS 樣式
    css_content = '''
    @charset "utf-8";
    body {
        margin: 5% 6%;
        font-family: -apple-system, "Noto Serif CJK TC", "Source Han Serif TC", "Songti TC", "PMingLiU", serif;
        line-height: 1.85;
        letter-spacing: 0.05em;
        text-align: justify;
    }
    h1 {
        text-align: center;
        font-size: 1.45em;
        margin-top: 1.5em;
        margin-bottom: 1.5em;
        font-weight: bold;
    }
    p {
        margin-top: 0.5em;
        margin-bottom: 0.5em;
        text-indent: 2em;
    }
    .intro-box {
        border-left: 3px solid #888;
        padding-left: 1em;
        margin: 1.5em 0;
        color: #555;
    }
    '''
    style_item = epub.EpubItem(
        uid="style_nav",
        file_name="style/main.css",
        media_type="text/css",
        content=css_content.encode('utf-8')
    )
    book.add_item(style_item)

    # 3. 封面圖 (若有)
    if cover_bytes:
        try:
            book.set_cover("cover.jpg", cover_bytes)
        except Exception as e:
            print(f"[Exporter] 設定封面圖片失敗: {e}")

    # 4. 書籍簡介頁 (Intro)
    spine = ['cover'] if cover_bytes else []
    toc = []

    if book_info.get('intro'):
        intro_paras_html = "".join([f"<p>{to_traditional(p.strip())}</p>" for p in book_info['intro'].splitlines() if p.strip()])
        intro_content = f"""
        <html>
        <head>
            <title>書籍簡介</title>
            <link rel="stylesheet" href="style/main.css" type="text/css"/>
        </head>
        <body>
            <h1>{title_str}</h1>
            <p style="text-align:center; font-weight:bold;">作者：{author_str}</p>
            <hr/>
            <div class="intro-box">
                {intro_paras_html}
            </div>
        </body>
        </html>
        """
        intro_chapter = epub.EpubHtml(title="書籍簡介", file_name="intro.xhtml", lang="zh-TW")
        intro_chapter.set_content(intro_content.encode('utf-8'))
        intro_chapter.add_item(style_item)
        book.add_item(intro_chapter)
        spine.append(intro_chapter)
        toc.append(intro_chapter)

    # 5. 各章節頁面
    for idx, chap in enumerate(chapters, 1):
        file_name = f"chap_{idx:05d}.xhtml"
        title = to_traditional(chap.get('title', f"第 {idx} 章"))
        paras_html = "".join([f"<p>{to_traditional(p)}</p>" for p in chap.get('paragraphs', [])])
        
        chap_html = f"""
        <html>
        <head>
            <title>{title}</title>
            <link rel="stylesheet" href="style/main.css" type="text/css"/>
        </head>
        <body>
            <h1>{title}</h1>
            {paras_html}
        </body>
        </html>
        """
        epub_chap = epub.EpubHtml(title=title, file_name=file_name, lang="zh-TW")
        epub_chap.set_content(chap_html.encode('utf-8'))
        epub_chap.add_item(style_item)
        book.add_item(epub_chap)
        spine.append(epub_chap)
        toc.append(epub_chap)

    # 6. 目錄與導航綁定
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    # 寫入 EPUB 檔案
    epub.write_epub(output_path, book)
    print(f"[Exporter] EPUB 已成功儲存至: {output_path}")

