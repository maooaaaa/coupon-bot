import feedparser
import requests
import json
import os
import re
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
from time import mktime

# --- 設定エリア ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DATA_FILE = "data.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ソースリスト（ここにRSSHubで作ったTwitterのRSSを入れると最強になります）
RSS_URLS = [
    "https://prtimes.jp/gourmet.rdf",
    "https://prtimes.jp/technology.rdf",
    "https://touchlab.jp/feed/",
    "https://www.gizmodo.jp/index.xml",
    "https://corriente.top/feed/",
    "https://automaton-media.com/feed/",
    "https://rocketnews24.com/feed/",
]

# このキーワードが含まれていないと「激アツ」とみなさない
HOT_KEYWORDS = [
    "クーポン", "コード", "半額", "無料", "割引", "激安", "特価", 
    "円OFF", "ポイント", "全員", "配布", "エラー", "ミス"
]

def load_sent_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

def save_sent_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data[-300:], f, ensure_ascii=False, indent=2)

def is_within_24h(entry):
    """記事が24時間以内か判定"""
    if not hasattr(entry, 'published_parsed'):
        return True # 日付データがない場合は念のため通す
    
    published_time = datetime.fromtimestamp(mktime(entry.published_parsed))
    now = datetime.now()
    
    # 24時間以内ならTrue
    return (now - published_time) < timedelta(hours=24)

def deep_dive_for_code(url):
    """リンク先に実際にアクセスしてコードを探す（Deep Scan）"""
    try:
        # 負荷をかけないよう少し待つ
        time.sleep(1)
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code != 200: return None
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        text = soup.get_text()
        
        # 厳密なコード抽出ロジック
        return extract_strict_code(text)
    except:
        return None

def extract_strict_code(text):
    """
    精度優先のコード抽出
    """
    # パターン1: 「コード：XXXX」という明確な指定
    pattern1 = r'(?:クーポン|コード|Key|ID)[:：]\s*([a-zA-Z0-9\-_]{4,20})'
    match = re.search(pattern1, text)
    if match:
        code = match.group(1)
        if not re.search(r'(202[0-9]|http|jpg|png)', code):
            return code

    # パターン2: Amazonプロモコード風（大文字英数字6桁以上混合）
    # ※誤検知を減らすため、前後にスペースがあるもの限定
    pattern2 = r'\s([A-Z0-9]{6,12})\s'
    matches = re.findall(pattern2, text)
    
    ignore_list = ["IPHONE", "ANDROID", "WINDOWS", "UPDATE", "MOBILE", "TOKYO", "ONLINE"]
    
    for m in matches:
        # 数字と文字が両方混ざっていること（純粋な単語や数字だけを除外）
        if re.search(r'[A-Z]', m) and re.search(r'[0-9]', m):
            if m not in ignore_list:
                return m
    return None

def send_discord_embed(title, code, link, source_name, date_str):
    """コードがある場合だけ激アツ通知"""
    
    # コードがない記事は今回は無視する！（または簡易通知にする）
    if not code:
        # コードがなくても「半額」とか書いてあったら通知する救済措置
        if "半額" in title or "無料" in title:
            description = "👀 コードは見つかりませんでしたが、激アツの気配がします！"
            color = 0xFFA500 # オレンジ
        else:
            return # コードもなくて激アツワードもなければ通知しない（無視）

    else:
        description = f"🔥 **激アツコード抽出成功**\n```{code}```\n急いで入力してください！"
        color = 0xFF0000 # 赤（最高優先度）

    embed = {
        "title": f"⚡ {title}",
        "url": link,
        "description": description,
        "color": color,
        "footer": {
            "text": f"{source_name} • {date_str} (24h以内)"
        }
    }

    payload = {
        "username": "DeepCoupon Hunter",
        "embeds": [embed]
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
        time.sleep(2)
    except Exception as e:
        print(f"Discord send error: {e}")

def main():
    if not DISCORD_WEBHOOK_URL:
        print("Webhook URL error")
        return

    sent_urls = load_sent_data()
    new_sent_urls = sent_urls.copy()
    
    print("Fetching feeds with Deep Scan...")

    for rss_url in RSS_URLS:
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=10)
            feed = feedparser.parse(resp.content)
            source_name = feed.feed.title if 'title' in feed.feed else "News"
            
            # 各サイト最新5件だけチェック（深層スキャンの負荷軽減のため）
            for entry in feed.entries[:5]:
                link = entry.link
                title = entry.title
                
                # 1. 重複チェック
                if link in sent_urls: continue

                # 2. 時間チェック（24時間以内か？）
                if not is_within_24h(entry):
                    # 古い記事は無視
                    continue

                # 3. キーワード一次審査
                if not any(k in title for k in HOT_KEYWORDS):
                    continue

                print(f"  🔍 Deep Scanning: {title}...")

                # 4. 深層スキャン（リンク先に行ってコードを探す）
                # まず概要から探す
                description = entry.summary if 'summary' in entry else title
                code = extract_strict_code(BeautifulSoup(description, "html.parser").get_text())
                
                # 概要になければ、リンク先に突撃
                if not code:
                    code = deep_dive_for_code(link)

                # コードが見つかった、もしくはタイトルが超強力なら通知
                send_discord_embed(title, code, link, source_name, "Just Now")
                
                new_sent_urls.append(link)

        except Exception as e:
            print(f"Error checking {rss_url}: {e}")
            continue

    save_sent_data(new_sent_urls)
    print("Done.")

if __name__ == "__main__":
    main()
