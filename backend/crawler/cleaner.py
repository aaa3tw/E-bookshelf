"""
智慧廣告與雜訊清理模組 (cleaner.py)
包含：
1. 韓文象形防爬混淆字元自動還原 (Hangul Deobfuscation)
2. DOM 標籤廣告過濾 (adBlock, data-ad, script, style 等)
3. 段落語意廣告/水印/改版提示過濾
"""

import re
import opencc
from bs4 import BeautifulSoup, Tag

try:
    _cc_s2tw = opencc.OpenCC('s2tw')
except Exception:
    _cc_s2tw = None


def to_traditional(text: str) -> str:
    """將簡體中文轉換為繁體中文（台灣標準字形）"""
    if not text:
        return ""
    if _cc_s2tw:
        try:
            return _cc_s2tw.convert(text)
        except Exception:
            return text
    return text


# 盜版站常見防盜爬韓文象形替代字字典（依字形與上下文還原）
HANGUL_REPLACE_MAP = {
    '괗': '二',
    '굛': '十',
    '궝': '七',
    '귷': '八',
    '그': '人',
    '극': '入',
    '깇': '九',
    '깊': '了',
    '꺅': '刀',
    '꺆': '力',
    '꺗': '又',
    '꺘': '三',
    '꺛': '乾',
    '꺱': '土',
    '꺲': '工',
    '꺳': '才',
    '꺴': '寸',
    '꺵': '丈',
    '꺶': '大',
    '껗': '上',
    '께': '小',
    '껙': '口',
    '껚': '山',
    '껛': '巾',
    '껜': '千',
    '껦': '弓',
    '껡': '亡',
    '껣': '之',
    '껥': '已',
    '껧': '己',
    '껩': '也',
    '꼇': '川',
    '꼊': '麼',
    '꼋': '久',
    '꼎': '凡',
    '꼐': '及',
    '꽬': '夫',
    '꽭': '天',
    '꽮': '元',
    '꽱': '扎',
    '꾉': '五',
    '꾊': '支',
    '꾦': '犬',
    '꾨': '尤',
    '꾩': '匹',
    '꾫': '巨',
    '꾬': '牙',
    '꾮': '互',
    '꾿': '切',
    '꿀': '止',
    '꿁': '少',
    '꿂': '日',
    '꿗': '中',
    '꿛': '手',
    '꿢': '午',
    '꿤': '升',
    '꿧': '片',
    '꿨': '化',
    '꿩': '仇',
    '꿮': '爪',
    '꿯': '反',
    '꿰': '介',
    '꿫': '仍',
    '꿭': '斤',
    '꿷': '今',
    '꿵': '父',
    '꿸': '凶',
    '꿹': '乏',
    '뀑': '丹',
    '뀐': '欠',
    '뀔': '勾',
    '뀖': '六',
    '뀗': '文',
    '뀘': '方',
    '뀙': '火',
    '뀞': '心',
    '뀟': '尺',
    '뀧': '巴',
    '뀪': '以',
    '뀬': '予',
    '냪': '幻',
    '냫': '玉',
    '냬': '末',
    '냭': '未',
    '녈': '打',
    '녉': '巧',
    '녊': '正',
    '녌': '功',
    '녍': '扔',
    '녠': '甘',
    '녡': '世',
    '녢': '古',
    '녤': '本',
    '녦': '可',
    '녨': '左',
    '녪': '石',
    '녿': '右',
    '놀': '滿',
    '놂': '平',
    '놅': '的',
    '놆': '是',
    '놇': '在',
    '놊': '不',
    '놋': '有',
    '놌': '和',
    '놖': '我',
    '놘': '由',
    '놙': '只',
    '놚': '要',
    '놛': '他',
    '뇽': '叫',
    '뇾': '用',
    '눁': '四',
    '눂': '失',
    '눃': '生',
    '누': '到',
    '눑': '代',
    '눒': '作',
    '눓': '地',
    '눕': '出',
    '늀': '就',
    '늁': '分',
    '늂': '乎',
    '늄': '令',
    '늅': '成',
    '늉': '句',
    '늌': '外',
    '늳': '冬',
    '늵': '包',
    '덿': '主',
    '뎃': '年',
    '뎀': '市',
    '돗': '它',
    '땡': '百',
    '땢': '同',
    '땣': '能',
    '땤': '而',
    '떘': '下',
    '떚': '子',
}

# 廣告/水印/改版/導流語意過濾的正則規則列表
AD_PATTERNS = [
    re.compile(r'網站即將改版.*?閱讀進度丟失', re.IGNORECASE),
    re.compile(r'溫馨提示\s*[:：]?', re.IGNORECASE),
    re.compile(r'請大家及時保存.*?書架.*?閱讀記錄', re.IGNORECASE),
    re.compile(r'給您帶來的不便.*?敬請諒解', re.IGNORECASE),
    re.compile(r'請收藏本站|最新網址|免費閱讀|筆趣閣|提莫書屋|黃金屋|稷下書院', re.IGNORECASE),
    re.compile(r'如果覺得本書不錯.*?請記得加入書架', re.IGNORECASE),
    re.compile(r'應廣大讀者.*?VIP會員免廣告', re.IGNORECASE),
    re.compile(r'現推出VIP會員.*?免廣告', re.IGNORECASE),
    re.compile(r'https?://[a-zA-Z0-9.\-_/]+', re.IGNORECASE),
    re.compile(r'www\.[a-zA-Z0-9.\-_/]+', re.IGNORECASE),
    re.compile(r'^[（(【]?\s*本章完\s*[）)】]?$'),
    re.compile(r'^[（(【]?\s*(投推薦票|加入書籤|上一頁|下一頁|回目錄|返回目錄)\s*[）)】]?$'),
    re.compile(r'第\s*\d+\s*頁\s*/\s*共\s*\d+\s*頁'),
    re.compile(r'純文字在線閱讀本站域名'),
    re.compile(r'章節錯誤.*?點此舉報', re.IGNORECASE),
    re.compile(r'筆趣閣小說.*?版權所有', re.IGNORECASE),
]


def clean_chapter_title(title: str) -> str:
    """清理章節標題中的分頁標記與後贅詞，並轉為繁體中文"""
    if not title:
        return ""
    t = deobfuscate_hangul(title.strip())
    # 清理如 （1 / 1）、(1/2)、[1/2] 等
    t = re.sub(r'[（(\[]\s*\d+\s*/\s*\d+\s*[）)\]]', '', t)
    # 清理網站後綴
    t = re.sub(r'[\-_]?(?:筆趣閣小說|筆趣閣|提莫書屋|最新章節|在線閱讀).*', '', t)
    t = to_traditional(t)
    return t.strip()


def deobfuscate_hangul(text: str) -> str:
    """將文本中的防爬韓文字元替換為正常的繁體/簡體中文"""
    if not text:
        return ""
    # 逐字比對替換
    chars = [HANGUL_REPLACE_MAP.get(ch, ch) for ch in text]
    return "".join(chars)


def is_ad_paragraph(para: str) -> bool:
    """判斷某段文字是否為廣告或雜訊"""
    p = para.strip()
    if not p:
        return True
    
    # 檢查長度與特殊規則
    for pattern in AD_PATTERNS:
        if pattern.search(p):
            # 若整段很短且包含廣告詞，直接過濾
            if len(p) < 150:
                return True
            # 如果是專門的改版提示句，即使字數多也過濾
            if "閱讀進度丟失" in p or "溫馨提示" in p or "書架" in p and "保存" in p:
                return True

    return False


def clean_chapter_html(html_soup: BeautifulSoup) -> list[str]:
    """
    從章節 BeautifulSoup 物件中提取出乾淨的段落清單：
    1. 移除 DOM 中的廣告區塊與 script/style
    2. 提取 p 標籤文字
    3. 執行字元反混淆
    4. 過濾廣告段落
    """
    content_div = html_soup.find('div', class_='content')
    if not content_div:
        content_div = (
            html_soup.find('div', id='chaptercontent') or
            html_soup.find('div', class_='read-content') or
            html_soup.find('div', id='content') or
            html_soup.find('div', class_='chapter-content')
        )

    if not content_div:
        return []

    # 1. 移除廣告 DOM 元素
    for bad_tag in content_div.find_all(['script', 'style', 'button', 'input']):
        bad_tag.decompose()

    for ad_elem in content_div.find_all(lambda tag: isinstance(tag, Tag) and (
        any('ad' in str(c).lower() for c in tag.get('class', [])) or
        tag.get('data-ad') is not None or
        'notice' in str(tag.get('class', [])).lower() or
        'banner' in str(tag.get('class', [])).lower()
    )):
        ad_elem.decompose()

    # 2. 提取段落
    cleaned_paragraphs = []
    
    # 優先抓取 p 標籤
    p_tags = content_div.find_all('p')
    if p_tags:
        for p in p_tags:
            text = p.get_text(strip=True)
            text = to_traditional(deobfuscate_hangul(text))
            if not is_ad_paragraph(text):
                cleaned_paragraphs.append(text)
    else:
        # 若沒有 p 標籤，按換行分割
        raw_text = content_div.get_text('\n')
        for line in raw_text.splitlines():
            line = line.strip()
            line = to_traditional(deobfuscate_hangul(line))
            if not is_ad_paragraph(line):
                cleaned_paragraphs.append(line)

    return cleaned_paragraphs

