import os
import urllib.request
import json
from datetime import datetime, timezone, timedelta
import yfinance as yf

KST = timezone(timedelta(hours=9))


def get_emoji(change, up_is_good=True):
    """굿 = 🟢, 배드 = 🔴, 보합 = ⚪️"""
    if abs(change) < 1e-6:
        return "⚪️"
    if change > 0:
        return "🟢" if up_is_good else "🔴"
    else:
        return "🟢" if not up_is_good else "🔴"


def format_item(name, ticker, up_is_good=True, decimals=2):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")
        if len(hist) < 2:
            return f"⚪️ {name}: 데이터 없음"
        prev_close = hist["Close"].iloc[-2]
        close = hist["Close"].iloc[-1]
        change = close - prev_close
        pct = (change / prev_close) * 100
        emoji = get_emoji(change, up_is_good)
        sign = "+" if change > 0 else ""
        fmt = f",.{decimals}f"
        return f"{emoji} {name}: {close:{fmt}} ({sign}{change:{fmt}}, {sign}{pct:.2f}%)"
    except Exception:
        return f"⚪️ {name}: 데이터 없음"


def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    now_kst = datetime.now(KST)
    date_str = now_kst.strftime("%Y-%m-%d (%a)")

    lines = [
        f"📅 {date_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "[ MACRO ]",
        format_item("WTI", "CL=F", up_is_good=False),
        format_item("US 10Y", "^TNX", up_is_good=False),
        format_item("DXY", "DX-Y.NYB", up_is_good=False),
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "[ US MKT ]",
        format_item("DJI", "^DJI"),
        format_item("S&P500", "^GSPC"),
        format_item("Nasdaq", "^IXIC"),
        format_item("MU", "MU"),
        format_item("NVDA", "NVDA"),
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "[ KR MKT ]",
        format_item("EWY", "EWY"),
        format_item("SOX", "^SOX"),
        format_item("KRW/$", "KRW=X", up_is_good=False),
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    send_telegram(token, chat_id, "\n".join(lines))
    print("전송 완료!")


if __name__ == "__main__":
    main()
