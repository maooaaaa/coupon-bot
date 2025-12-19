import requests
import json
import os
import re
from bs4 import BeautifulSoup
from datetime import datetime

# --- 設定エリア ---
# DiscordのウェブフックURL（GitHubのSecretsから読み込む設定）
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# ターゲットにするURL（例: 激安速報系のブログやRSS。ここは収集したいサイトに変えてください）
# ※サンプルとして、架空の構造を想定しています。実在する「激安速報」系のRSSやHTMLを指定します。
TARGET_URL = "https://example-coupon-news-site.com/feed" 

# データを保存するファイル名
DATA_FILE = "data.json"

def load_sent_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_sent_data(data):
    # 最新100件だけ保持して保存（ファイル肥大化防止）
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data[-100:], f, ensure_ascii=False, indent=2)

def extract_coupon_code(text):
    # テキストからクーポンコードっぽいものを抽出する正規表現
    # (英数字4文字以上、大文字含むなどを簡易的に判定)
    # ※精度を上げるには調整が必要です
    pattern = r'[A-Z0-9]{4,15}'
    matches = re.findall(pattern, text)
    if matches:
        # 明らかにクーポンじゃない単語（HTTPなど）を除外
        filtered = [m for m in matches if "HTTP" not in m and "202" not in m]
        if filtered:
            return filtered[0] # 最初に見つかったものをコードとする
    return "コードなし/要確認"

def send_discord(store_name, code, link):
    payload = {
        "content": f"**【{store_name}】**\n```{code}```\n[参照リンク]({link})"
    }
    headers = {'Content-Type': 'application/json'}
    requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers=headers)

def main():
    sent_urls = load_sent_data()
    
    # 1. データ取得（ここでは一般的なHTML解析の例）
    try:
        response = requests.get(TARGET_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- サイトに合わせてここを書き換える ---
        # 記事のリストを取得（class名はターゲットサイトをF12で確認して書き換えてください）
        # 例: 記事タイトルが h2、リンクが aタグ、本文にコードがある場合
        articles = soup.select("div.article-item") # 仮のセレクタ

        new_entries = []

        for article in articles:
            try:
                title_el = article.select_one("h2.title")
                link_el = article.select_one("a")
                
                if not title_el or not link_el:
                    continue

                title = title_el.text.strip()
                link = link_el['href']
                
                # すでに送信済みならスキップ
                if link in sent_urls:
                    continue

                # 詳細ページに行ってコードを探す（負荷対策でsleepを入れるべきですがActionsなら短時間で終わるならOK）
                # 今回は一覧から簡易抽出するロジックにします
                description = article.text.strip()
                
                # クーポンコード抽出
                code = extract_coupon_code(description)
                
                # 店名をタイトルから簡易抽出（正規表現などで調整推奨）
                store_name = title[:20] 

                # Discord送信
                print(f"Sending: {title}")
                send_discord(store_name, code, link)
                
                # 送信済みリストに追加
                sent_urls.append(link)
                
            except Exception as e:
                print(f"Error parsing article: {e}")
                continue

        # データを保存
        save_sent_data(sent_urls)

    except Exception as e:
        print(f"Global Error: {e}")

if __name__ == "__main__":
    if not DISCORD_WEBHOOK_URL:
        print("Error: Webhook URL is missing.")
    else:
        main()
