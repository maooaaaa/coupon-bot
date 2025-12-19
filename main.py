import feedparser
import requests
import json
import os
import re
from bs4 import BeautifulSoup
import time
import hashlib

# --- 設定エリア ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DATA_FILE = "data.json"

# ブラウザのふりをするヘッダー
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 巡回リスト（前回と同じ最強リスト）
RSS_URLS = [
    "https://prtimes.jp/gourmet.rdf",
    "https://prtimes.jp/technology.rdf",
    "https://prtimes.jp/app.rdf",
    "https://prtimes.jp/entertainment.rdf",
    "https://touchlab.jp/feed/",
    "https://www.gizmodo.jp/index.xml",
    "https://corriente.top/feed/",
    "https://www.lifehacker.jp/feed/index.xml",
    "https://rocketnews24.com/feed/",
    "https://automaton-media.com/feed/",
]

TARGET_KEYWORDS = [
    "クーポン", "コード", "半額", "セール", "無料", "割引", 
    "キャンペーン", "激安", "特価", "配布", "円OFF", "ポイント",
    "発売", "開始", "登場", "プレゼント"
]

def load_sent_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_sent_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data[-300:], f, ensure_ascii=False, indent=2)

def extract_image(entry):
    """RSSから画像URLを抜き出す"""
    # 1. media_content (PR Timesなど)
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    # 2. links (一部のブログ)
    if 'links' in entry:
        for link in entry.links:
            if link.get('type', '').startswith('image'):
                return link['href']
    # 3. description内のimgタグ
    if 'summary' in entry:
        soup = BeautifulSoup(entry.summary, 'html.parser')
        img = soup.find('img')
        if img and img.get('src'):
            return img['src']
    return None

def extract_coupon_code(text):
    """
    コード抽出ロジック（厳しめに判定し、ゴミを排除）
    """
    # 明確なキーワード指定がある場合
    keyword_pattern = r'(?:クーポン|コード|Key|ID)[:：]\s*([a-zA-Z0-9\-_]{4,20})'
    match = re.search(keyword_pattern, text, re.IGNORECASE)
    if match:
        code = match.group(1)
        if not re.search(r'(202[0-9]|http|jpg|png)', code):
            return code

    # Amazonなどでよくある「大文字英数字の羅列」
    # 条件: 6文字以上、全部大文字、英字と数字が混ざっていること
    general_pattern = r'\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*[0-9])[A-Z0-9]{6,15}\b'
    matches = re.findall(general_pattern, text)
    
    ignore_list = ["IPHONE", "ANDROID", "WINDOWS", "TOKYO", "JAPAN", "UPDATE"]
    for m in matches:
        if m not in ignore_list and not m.startswith("202"):
            return m
            
    return None # 見つからない場合はNoneを返す

def get_color(source_name):
    """サイトごとに色を変える"""
    name = source_name.lower()
    if "pr times" in name: return 0x1E90FF # Blue
    if "gizmodo" in name: return 0xFFD700 # Gold
    if "touch" in name: return 0xFF69B4 # Pink
    if "rocket" in name: return 0xDC143C # Red
    return 0x00FA9A # Default Green

def send_discord_embed(title, code, link, source_name, image_url, date_str):
    """リッチなEmbed形式で送信"""
    
    # 説明文の作成
    description = ""
    if code:
        description = f"🔥 **激アツ！クーポンコード発見**\n```{code}```\nここからコピーして使ってね！"
        color = 0xFF0000 # 赤（強調）
    else:
        description = "👇 **セール・キャンペーン詳細**\nコードは不要、もしくはリンク先でチェック！"
        color = get_color(source_name)

    embed = {
        "title": title,
        "url": link,
        "description": description,
        "color": color,
        "footer": {
            "text": f"{source_name} • {date_str}"
        }
    }

    if image_url:
        embed["image"] = {"url": image_url}

    payload = {
        "username": "激安ハンターBot",
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
    
    print("Fetching feeds...")

    for rss_url in RSS_URLS:
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=10)
            feed = feedparser.parse(resp.content)
            
            source_name = feed.feed.title if 'title' in feed.feed else "News"
            print(f"Checking: {source_name}")

            for entry in feed.entries[:5]: # 最新5件
                link = entry.link
                title = entry.title
                
                # 重複チェック
                if link in sent_urls: continue

                # キーワードチェック
                if not any(k in title for k in TARGET_KEYWORDS): continue

                print(f"  -> HIT: {title}")

                # 本文解析
                description = ""
                if 'content' in entry: description = entry.content[0].value
                elif 'summary' in entry: description = entry.summary
                else: description = title
                
                soup = BeautifulSoup(description, "html.parser")
                text_content = soup.get_text()
                
                # 情報抽出
                code = extract_coupon_code(text_content)
                image_url = extract_image(entry)
                
                # 日付
                date_str = time.strftime('%Y-%m-%d %H:%M')

                # Discord送信
                send_discord_embed(title, code, link, source_name, image_url, date_str)
                
                new_sent_urls.append(link)

        except Exception as e:
            print(f"Error: {e}")
            continue

    save_sent_data(new_sent_urls)
    print("Done.")

if __name__ == "__main__":
    main()
