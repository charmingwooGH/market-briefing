import os
import urllib.request
import json
from datetime import datetime
import yfinance as yf

def get_change_emoji(change):
    if change > 0:
        return "🔴"
    elif change < 0:
        return "🔵"
    return "⚪️"

def format_index(name, ticker):
    data = yf.Ticker(ticker)
    hist = data.history(period="2d")
    if len(hist) < 2:
        return f"{name}: 데이터 없음"
    prev_close = hist['Close'].iloc[-2]
    close = hist['Close'].iloc[-1]
    change = close - prev_close
    pct = (change / prev_close) * 100
    emoji = get_change_emoji(change)
    sign = "+" if change > 0 else ""
    return f"{emoji} {name}: {close:,.2f} ({sign}{change:,.2f}, {sign}{pct:.2f}%)"

def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    date_str = datetime.utcnow().strftime("%Y-%m-%d")

    lines = [
        "📊 미국 증시 브리핑",
        f"📅 {date_str} (전일 종가 기준)",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "[ 주요 지수 ]",
        format_index("다우존스", "^DJI"),
        format_index("S&P 500", "^GSPC"),
        format_index("나스닥", "^IXIC"),
        format_index("필라델피아 반도체", "^SOX"),
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🔴 상승  🔵 하락  ⚪️ 보합",
    ]

    send_telegram(token, chat_id, "\n".join(lines))
    print("전송 완료!")

if __name__ == "__main__":
    main()
