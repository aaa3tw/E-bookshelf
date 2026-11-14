"""
Z-Library 整合模組 (zlib_client.py)
網址：https://zh.z-lib.by
提供：
1. 搜尋書籍 (Search by title / author / keyword)
2. 登入取得個人專屬金鑰與網域 (Login by email & password via eapi)
3. 支援 API 檔案下載 (支援個人網域、remix-userid 與 remix-userkey)
4. 網頁直達連結引導 (免帳號在瀏覽器中下載)
"""

import os
import re
import json
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL = "https://zh.z-lib.by"
try:
    from app_paths import ZLIB_CONFIG_FILE as CONFIG_FILE
except ImportError:
    try:
        from .app_paths import ZLIB_CONFIG_FILE as CONFIG_FILE
    except ImportError:
        CONFIG_FILE = Path(__file__).parent / "zlib_config.json"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}


def load_zlib_config() -> dict:
    """載入使用者儲存的 Z-Library 登入金鑰與個人配置"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"remix_user_key": "", "remix_userid": "", "email": "", "personal_domains": []}


def save_zlib_config(data: dict):
    """儲存 Z-Library 登入金鑰配置"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Z-Lib] 儲存配置失敗: {e}")


def login_zlib(email: str, password: str) -> dict:
    """
    透過 Z-Library 官方 eapi 進行帳號密碼登入
    成功時獲取 remix_userkey, remix_userid 與 personal_domains 並自動存檔
    """
    if not email or not password:
        return {'success': False, 'message': '請輸入 Email 與密碼'}

    post_data = {
        'email': email.strip(),
        'password': password.strip()
    }
    encoded = urllib.parse.urlencode(post_data).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}/eapi/user/login",
        data=encoded,
        headers=DEFAULT_HEADERS
    )
    req.method = 'POST'

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            if data.get('success') == 1 or 'user' in data:
                user = data.get('user', {})
                user_id = str(user.get('id', ''))
                user_key = user.get('remix_userkey') or user.get('remix_user_key', '')

                # 提取個人網域
                personal_domains = user.get('personal_domains', [])
                if not personal_domains and 'domains' in user:
                    personal_domains = user.get('domains', [])

                config = {
                    'email': email.strip(),
                    'remix_userid': user_id,
                    'remix_user_key': user_key,
                    'personal_domains': personal_domains
                }
                save_zlib_config(config)
                return {
                    'success': True,
                    'message': 'Z-Library 登入綁定成功！已為您啟用全自動高速下載。',
                    'config': config
                }
            else:
                err = data.get('error', '登入失敗，請確認帳號與密碼')
                return {'success': False, 'message': err}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='ignore')
        try:
            err_json = json.loads(err_body)
            msg = err_json.get('error', err_body)
        except Exception:
            msg = err_body
        return {'success': False, 'message': f"登入失敗: {msg}"}
    except Exception as e:
        return {'success': False, 'message': f"連線異常: {str(e)}"}


def search_zlib(keyword: str, extension: str | None = "epub", limit: int = 15) -> list[dict]:
    """
    透過 Z-Library 官方 API 檢索書籍
    支援格式過濾 (預設 epub)
    返回候選書籍列表
    """
    results = []
    kw = keyword.strip()
    if not kw:
        return results

    clean_kw = re.sub(r'[《》【】\[\]\(\)]', ' ', kw).strip()
    config = load_zlib_config()
    token = config.get('remix_user_key', '')
    user_id = config.get('remix_userid', '')

    headers = dict(DEFAULT_HEADERS)
    if token:
        headers['Cookie'] = f"remix_user_key={token}; remix_userkey={token}"
        headers['remix-userkey'] = token
        if user_id:
            headers['Cookie'] += f"; remix_userid={user_id}"
            headers['remix-userid'] = str(user_id)

    post_data = {
        'message': clean_kw,
        'limit': limit,
    }
    if extension:
        post_data['extensions[]'] = extension

    encoded_data = urllib.parse.urlencode(post_data).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}/eapi/book/search",
        data=encoded_data,
        headers=headers
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            books = data.get('books', [])
            for b in books:
                b_ext = b.get('extension', '').lower()
                b_id = str(b.get('id', ''))
                b_hash = b.get('hash', '')
                results.append({
                    'source': 'Z-Library',
                    'title': b.get('title', '未知書名'),
                    'author': b.get('author', '佚名'),
                    'book_id': b_id,
                    'hash': b_hash,
                    'extension': b_ext,
                    'filesize': b.get('filesizeString', ''),
                    'year': b.get('year', ''),
                    'publisher': b.get('publisher', ''),
                    'cover_url': b.get('cover', ''),
                    'web_url': f"{BASE_URL}/book/{b_id}/{b_hash}",
                    'dl_key': b.get('dl', '')
                })
    except Exception as e:
        print(f"[Z-Lib] 搜尋失敗: {e}")

    return results


def download_zlib_book(book_id: str, book_hash: str, output_path: str, user_token: str | None = None) -> tuple[bool, str]:
    """
    下載 Z-Library 書籍
    Z-Library 下載檔案需帶入 remix-userid 與 remix-userkey (Header / Cookie)
    回傳: (is_success, error_message_or_filepath)
    """
    config = load_zlib_config()
    token = user_token or config.get('remix_user_key', '')
    user_id = config.get('remix_userid', '')
    personal_domains = config.get('personal_domains', [])

    if not token:
        web_direct = f"{BASE_URL}/book/{book_id}/{book_hash}"
        return False, f"AUTH_REQUIRED: 尚未綁定 Z-Library 帳號或金鑰。請在右上角「Z-Lib 設定」中輸入 Email 與密碼直接登入！亦可點選開啟官方下載頁：{web_direct}"

    # 建構所有可用網域候選列表 (個人網域優先)
    domains_to_try = []
    for d in personal_domains:
        if d:
            dom = d if d.startswith('http') else f"https://{d}"
            if dom not in domains_to_try:
                domains_to_try.append(dom)

    for d in [BASE_URL, "https://zh.z-lib.by", "https://z-lib.sk", "https://singlelogin.re"]:
        if d not in domains_to_try:
            domains_to_try.append(d)

    headers = dict(DEFAULT_HEADERS)
    headers['Cookie'] = f"remix_user_key={token}; remix_userkey={token}"
    headers['remix-userkey'] = token
    headers['remix_userkey'] = token
    if user_id:
        headers['Cookie'] += f"; remix_userid={user_id}"
        headers['remix-userid'] = str(user_id)
        headers['remix_userid'] = str(user_id)

    last_error = ""
    for domain in domains_to_try:
        url = f"{domain}/eapi/book/{book_id}/{book_hash}/file"
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                    # 關鍵：若 API 成功回傳 downloadLink，立即自高速 CDN 下載檔案實體！
                    dl_link = data.get('file', {}).get('downloadLink')
                    if dl_link:
                        print(f"[Z-Lib] 成功獲取檔案 CDN 下載連結，正在串流下載...")
                        dl_req = urllib.request.Request(dl_link, headers=DEFAULT_HEADERS)
                        with urllib.request.urlopen(dl_req, timeout=60) as dl_resp:
                            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                            with open(output_path, 'wb') as f:
                                f.write(dl_resp.read())
                        print(f"[Z-Lib] ✓ 書籍已成功自 CDN 下載完成: {output_path}")
                        return True, output_path

                    err_msg = data.get('error', '未知錯誤')
                    last_error = f"{err_msg}"
                    continue

                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(resp.read())

                print(f"[Z-Lib] ✓ 書籍已成功下載至: {output_path}")
                return True, output_path

        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            try:
                err_json = json.loads(err_body)
                last_error = err_json.get('error', err_body)
            except Exception:
                last_error = err_body

            print(f"[Z-Lib] 節點 {domain} 錯誤 ({e.code}): {last_error}")
            if e.code == 400 and ("登录" in last_error or "账户" in last_error or "login" in last_error.lower()):
                return False, "AUTH_EXPIRED: Z-Library 帳號登入憑證已失效，請在右上角「Z-Lib 設定」重新登入帳號或更新金鑰！"
        except Exception as e:
            last_error = str(e)
            print(f"[Z-Lib] 節點 {domain} 異常: {e}")

    web_direct = f"{BASE_URL}/book/{book_id}/{book_hash}"
    return False, f"Z-Library 下載失敗 ({last_error or '節點連線逾時'})。您可點選開啟官方下載頁：{web_direct}"
