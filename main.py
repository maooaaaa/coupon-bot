import feedparser
import requests
import json
import os
import re
from bs4 import BeautifulSoup
import time

# --- 設定エリア ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DATA_FILE = "data.json"

# 質の高い情報源リスト（ここを増やすと情報が増えます）
RSS_URLS = [
    # --- 【最強】公式プレスリリース（ここが一番早いです） ---
    # 飲食・グルメのキャンペーン・クーポン（マック、スタバ、回転寿司など）
    "https://prtimes.jp/gourmet.rdf",
    # テクノロジー・ガジェット・アプリのセール情報
    "https://prtimes.jp/technology.rdf",
    "https://prtimes.jp/app.rdf",
    # エンタメ・ゲームの無料配布やキャンペーン
    "https://prtimes.jp/entertainment.rdf",

    # --- 【厳選】ガジェット・PC・Amazonセール系 ---
    # Apple製品やAmazonセールの速報に強い
    "https://touchlab.jp/feed/",
    # ガジェット全般、タイムセール情報
    "https://www.gizmodo.jp/index.xml",
    # PC・スマホの特価情報、アプリセール
    "https://corriente.top/feed/",
    # 仕事効率化・ライフハック系（ソフトのセールなど）
    "https://www.lifehacker.jp/feed/index.xml",

    # --- 【生活】飲食・サブカル・激安系 ---
    # ロケットニュース24（「〜食べ放題」「激安」などの体験記事が多い）
    "https://rocketnews24.com/feed/",
    # ゲームの無料配布（Epic Gamesなど）やSteamセール情報
    "https://automaton-media.com/feed/",
]

# 収集対象とするキーワード（これらがタイトルに含まれる場合のみ通知）
# キーワードを「激安」「無料」系に特化
TARGET_KEYWORDS = [
    "クーポン", "コード", "半額", "セール", "無料", "割引", 
    "キャンペーン", "激安", "特価", "配布", "円OFF", "ポイント"
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
    # 最新200件だけ保持
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data[-200:], f, ensure_ascii=False, indent=2)

def extract_coupon_code(text):
    """
    テキストからクーポンコードらしきものを抽出する強化版ロジック
    """
    # 1. 「コード」「クーポン」の後ろにある英数字を優先的に探す
    # 例: "クーポンコード: SPECIAL2024" -> SPECIAL2024 を抜く
    keyword_pattern = r'(?:コード|クーポン|key)[：:]?\s*([a-zA-Z0-9\-_]{4,20})'
    match = re.search(keyword_pattern, text)
    if match:
        code = match.group(1)
        # 除外ワード（日付やHTTPなど）でなければ採用
        if not re.search(r'(202[0-9]|http)', code):
            return code

    # 2. 見つからない場合、汎用的な大文字英数字を探す
    general_pattern = r'\b[A-Z][A-Z0-9]{3,15}\b'
    matches = re.findall(general_pattern, text)
    
    # ノイズ除去（よく誤検知される単語）
    ignore_list = ["HTTP", "HTTPS", "HTML", "AMAZON", "SALE", "FREE", "WIFI", "2024", "2025"]
    
    for m in matches:
        if m not in ignore_list and not m.startswith("202"):
            return m
            
    return "コード記載なし/リンク先確認"

def send_discord(title, code, link, source_name):
    payload = {
        "content": (
            f"**{source_name}** で情報を検知！\n"
            f"商品: {title}\n"
            f"コード: ```{code}```\n"
            f"⬇️ [参照リンク]({link})"
        )
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
        time.sleep(1) # 連投制限対策
    except Exception as e:
        print(f"Discord send error: {e}")

def main():
    sent_urls = load_sent_data()
    new_sent_urls = sent_urls.copy()
    
    print("巡回開始...")

    for rss_url in RSS_URLS:
        try:
            print(f"Checking: {rss_url}")
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:10]: # 各サイト最新10件をチェック
                link = entry.link
                title = entry.title
                
                # すでに送信済みならスキップ
                if link in sent_urls:
                    continue

                # フィルタリング: キーワードが含まれているか確認
                if not any(k in title for k in TARGET_KEYWORDS):
                    continue

                # 詳細情報の取得（Descriptionからコードを探す）
                # feedparserは description や content を持っています
                description = ""
                if 'content' in entry:
                    description = entry.content[0].value
                elif 'summary' in entry:
                    description = entry.summary
                else:
                    description = title

                # HTMLタグを除去してテキスト化
                soup = BeautifulSoup(description, "html.parser")
                text_content = soup.get_text()

                # コード抽出
                code = extract_coupon_code(text_content)
                
                # 情報源の名前（ドメインなど）
                source_name = feed.feed.title if 'title' in feed.feed else "News"

                print(f"  -> Hit: {title}")
                send_discord(title, code, link, source_name)
                
                new_sent_urls.append(link)

        except Exception as e:
            print(f"Error checking {rss_url}: {e}")
            continue

    save_sent_data(new_sent_urls)
    print("巡回終了")

if __name__ == "__main__":
    if not DISCORD_WEBHOOK_URL:
        print("WebHook URLが設定されていません")
    else:
        main()
