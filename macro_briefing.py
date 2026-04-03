import os, json, requests
import yfinance as yf
from datetime import datetime
import anthropic

# ── 1. 데이터 수집 ───────────────────────────────────────────────────────

def get_market_data():
    tickers = {
        'WTI유': 'CL=F', 'Brent유': 'BZ=F', '금': 'GC=F',
        'S&P500': '^GSPC', '나스닥': '^IXIC', '다우': '^DJI',
        'VIX': '^VIX', '미국10Y금리': '^TNX',
        '달러인덱스': 'DX-Y.NYB', 'USD/KRW': 'KRW=X',
        'KOSPI': '^KS11', 'SOX(반도체)': '^SOX',
    }
    results = {}
    for name, ticker in tickers.items():
        try:
            hist = yf.Ticker(ticker).history(period='5d')
            if len(hist) >= 2:
                cur, prv = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
                chg = (cur - prv) / prv * 100
                results[name] = {'value': f"{cur:,.2f}", 'change': chg}
            elif len(hist) == 1:
                results[name] = {'value': f"{hist['Close'].iloc[-1]:,.2f}", 'change': 0}
            else:
                results[name] = {'value': 'N/A', 'change': 0}
        except:
            results[name] = {'value': '오류', 'change': 0}
    return results

def get_fear_greed():
    try:
        d = requests.get('https://api.alternative.me/fng/', timeout=10).json()['data'][0]
        return {'value': d['value'], 'label': d['value_classification']}
    except:
        return {'value': '50', 'label': 'Neutral'}

# ── 2. Claude API 리포트 생성 ────────────────────────────────────────────

def generate_report(market_data, fear_greed):
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    today = datetime.now().strftime('%Y년 %m월 %d일')
    market_str = "\n".join([
        f"- {k}: {v['value']} ({'+' if v['change'] >= 0 else ''}{v['change']:.2f}%)"
        for k, v in market_data.items()
    ])

    prompt = f"""당신은 글로벌 매크로 전략 애널리스트입니다.
오늘({today}) 한국 주식시장 개장 전 매크로 브리핑을 작성하세요.

## 현재 시장 데이터:
{market_str}
- Fear & Greed Index: {fear_greed['value']}/100 ({fear_greed['label']})

## 지시사항:
1. 웹 검색으로 오늘의 최신 글로벌 매크로 뉴스를 확인하세요
2. 아래 JSON 스키마를 정확히 따르세요
3. 마크다운 코드블록 없이 순수 JSON만 반환하세요

{{
  "report_date": "{today}",
  "section1_issues": [
    {{"title": "이슈 제목", "detail": "상세 설명 2~3줄"}}
  ],
  "section2_chains": [
    {{"name": "체인명 (예: 체인 A: 전쟁→에너지)", "steps": ["단계1", "단계2", "단계3", "단계4"], "insight": "핵심 연결고리 한 줄"}}
  ],
  "section3_sectors": {{
    "benefit": [{{"name": "섹터명", "reason": "근거 한 줄"}}],
    "damage":  [{{"name": "섹터명", "reason": "근거 한 줄"}}]
  }},
  "section4_companies": {{
    "benefit": [{{"type": "기업 유형", "logic": "투자 논리 한 줄"}}],
    "damage":  [{{"type": "기업 유형", "logic": "피해 논리 한 줄"}}]
  }},
  "section5_sentiment": {{
    "overall": "종합 판정 (예: 극단 공포)",
    "fng_value": "{fear_greed['value']}",
    "indicators": [
      {{"name": "지표명", "value": "값/100", "level": "수준", "signal": "시그널 한 줄"}}
    ],
    "contrarian_comment": "역발상 분석 2~3줄",
    "scenarios": [
      {{"name": "시나리오 A", "content": "내용 한 줄"}},
      {{"name": "시나리오 B", "content": "내용 한 줄"}},
      {{"name": "기본 시나리오", "content": "내용 한 줄"}}
    ]
  }},
  "section6_matrix": {{
    "issues": ["①이슈1", "②이슈2", "③이슈3", "④이슈4", "⑤이슈5"],
    "compound_effects": [
      {{"title": "복합 효과 제목", "content": "내용 2줄"}}
    ],
    "kr_investor_points": ["한국 투자자 관점 포인트 1", "포인트 2", "포인트 3"]
  }}
}}

섹션별 개수 기준: issues 5개, chains 4~5개, sectors 각 5개, companies 각 5개, indicators 6개, compound_effects 3개"""

    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    # ── 아gentic loop: 웹검색 툴 호출이 끝날 때까지 반복 ──
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            tools=tools,
            messages=messages
        )

        # assistant 메시지 누적
        messages.append({"role": "assistant", "content": response.content})

        # stop_reason이 end_turn이면 최종 응답
        if response.stop_reason == "end_turn":
            break

        # tool_use가 있으면 tool_result를 messages에 추가하고 계속
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": ""  # SDK가 자동으로 웹검색 결과를 채워줌
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    # 최종 텍스트 추출
    text = ""
    for block in response.content:
        if hasattr(block, 'text'):
            text += block.text
    text = text.strip()

    # 코드블록 제거
    if '```' in text:
        parts = text.split('```')
        for part in parts:
            if part.startswith('json'):
                text = part[4:].strip()
                break
            elif '{' in part:
                text = part.strip()
                break

    # JSON 시작점 찾기
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]

    return json.loads(text)

# ── 3. 공통 CSS ──────────────────────────────────────────────────────────

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'Noto Sans KR', sans-serif;
  background: #0d1117;
  color: #e6edf3;
  width: 960px;
  padding: 44px 52px 52px;
}
.hdr {
  display: flex; justify-content: space-between; align-items: flex-end;
  border-bottom: 1px solid #30363d; padding-bottom: 18px; margin-bottom: 28px;
}
.hdr-title { font-size: 20px; font-weight: 700; color: #58a6ff; letter-spacing: -0.3px; }
.hdr-sub   { font-size: 12px; color: #484f58; }
.tag { font-size: 10px; font-weight: 700; letter-spacing: 1.8px; color: #484f58; text-transform: uppercase; margin-bottom: 18px; }
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 18px 22px; margin-bottom: 12px; }
.card-title { font-size: 14px; font-weight: 700; color: #f0f6fc; margin-bottom: 8px; }
.card-body  { font-size: 12.5px; color: #8b949e; line-height: 1.75; }
.badge { display:inline-block; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.bg   { background:#122820; color:#3fb950; border:1px solid #238636; }
.br   { background:#2d1214; color:#f85149; border:1px solid #da3633; }
.bb   { background:#0d2044; color:#58a6ff; border:1px solid #388bfd; }
.g    { color:#3fb950; } .r { color:#f85149; } .y { color:#e3b341; } .b { color:#58a6ff; }
table { width:100%; border-collapse:collapse; }
th { font-size:11px; font-weight:700; color:#58a6ff; letter-spacing:1px; padding:8px 12px; text-align:left; border-bottom:1px solid #21262d; }
td { font-size:12.5px; padding:9px 12px; border-bottom:1px solid #0d1117; vertical-align:top; line-height:1.6; }
td:first-child { font-weight:600; white-space:nowrap; min-width:140px; }
.insight { background:#1c2128; border-left:3px solid #388bfd; border-radius:4px; padding:10px 14px; margin-top:10px; font-size:12px; color:#8b949e; line-height:1.65; }
.step { display:flex; align-items:flex-start; margin-bottom:7px; font-size:12.5px; color:#c9d1d9; }
.arr  { color:#388bfd; margin-right:8px; flex-shrink:0; }
.footer { margin-top:28px; padding-top:14px; border-top:1px solid #21262d; font-size:11px; color:#30363d; text-align:right; }
</style>
"""

def hdr(title, date):
    return f'<div class="hdr"><div class="hdr-title">{title}</div><div class="hdr-sub">{date} · AI Research Dashboard</div></div>'

# ── 4. 섹션별 HTML ───────────────────────────────────────────────────────

def html_s1(d, mkt, fg):
    # 상단 시장 스냅샷
    keys = ['WTI유', 'S&P500', 'VIX', 'USD/KRW', 'KOSPI', '금']
    snap = ""
    for k in keys:
        if k in mkt:
            c = mkt[k]['change']
            cls = 'g' if c >= 0 else 'r'
            snap += f'<span style="margin-right:22px"><span style="color:#484f58;font-size:11px">{k} </span><span class="{cls}" style="font-size:13px;font-weight:600">{mkt[k]["value"]}</span><span style="font-size:11px;color:#484f58"> ({"+"}{ c:.1f}%)</span></span>'
    fv = int(fg['value']) if fg['value'].isdigit() else 50
    fg_cls = 'r' if fv < 25 else 'y' if fv < 50 else 'g'
    snap += f'<span><span style="color:#484f58;font-size:11px">F&G </span><span class="{fg_cls}" style="font-size:13px;font-weight:600">{fg["value"]}/100</span></span>'

    issues = ""
    circles = "①②③④⑤"
    for i, iss in enumerate(d['section1_issues']):
        issues += f'<div class="card"><div class="card-title">{circles[i]} {iss["title"]}</div><div class="card-body">{iss["detail"]}</div></div>'

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{BASE_CSS}</head><body>
{hdr("📌 핵심 글로벌 이슈", d['report_date'])}
<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px 18px;margin-bottom:24px;overflow:hidden">{snap}</div>
<div class="tag">Top Global Issues · {len(d['section1_issues'])}</div>
{issues}
<div class="footer">본 리포트는 AI 기반 분석 시스템에 의해 자동 생성되었습니다. 투자 판단의 최종 책임은 투자자 본인에게 있습니다.</div>
</body></html>"""

def html_s2(d):
    chains = ""
    for ch in d['section2_chains']:
        steps = "".join([f'<div class="step"><span class="arr">→</span><span>{s}</span></div>' for s in ch['steps']])
        chains += f'<div class="card"><div class="card-title">{ch["name"]}</div>{steps}<div class="insight">💡 {ch["insight"]}</div></div>'
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{BASE_CSS}</head><body>
{hdr("🔗 인과관계 체인 분석", d['report_date'])}
<div class="tag">Causal Chain Analysis</div>
{chains}
<div class="footer">본 리포트는 AI 기반 분석 시스템에 의해 자동 생성되었습니다.</div>
</body></html>"""

def html_s3(d):
    def rows(items, emoji, cls):
        return "".join([f'<tr><td><span class="{cls}">{emoji} {it["name"]}</span></td><td class="card-body">{it["reason"]}</td></tr>' for it in items])
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{BASE_CSS}</head><body>
{hdr("🟢 수혜 / 🔴 피해 섹터", d['report_date'])}
<div class="tag">Sector Impact Analysis</div>
<div class="card" style="margin-bottom:16px">
  <div style="margin-bottom:12px"><span class="badge bg">수혜 섹터</span></div>
  <table><tr><th>섹터</th><th>수혜 근거</th></tr>{rows(d['section3_sectors']['benefit'],'🟢','g')}</table>
</div>
<div class="card">
  <div style="margin-bottom:12px"><span class="badge br">피해 섹터</span></div>
  <table><tr><th>섹터</th><th>피해 근거</th></tr>{rows(d['section3_sectors']['damage'],'🔴','r')}</table>
</div>
<div class="footer">본 리포트는 AI 기반 분석 시스템에 의해 자동 생성되었습니다.</div>
</body></html>"""

def html_s4(d):
    def rows(items, emoji, cls, k1, k2):
        return "".join([f'<tr><td style="font-size:12px"><span class="{cls}">{emoji}</span> {it[k1]}</td><td class="card-body">{it[k2]}</td></tr>' for it in items])
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{BASE_CSS}</head><body>
{hdr("🏢 수혜 / 피해 기업 유형", d['report_date'])}
<div class="tag">Company Type Impact</div>
<div class="card" style="margin-bottom:16px">
  <div style="margin-bottom:12px"><span class="badge bg">수혜 기업</span></div>
  <table><tr><th>기업 유형</th><th>투자 논리</th></tr>{rows(d['section4_companies']['benefit'],'🟢','g','type','logic')}</table>
</div>
<div class="card">
  <div style="margin-bottom:12px"><span class="badge br">피해 기업</span></div>
  <table><tr><th>기업 유형</th><th>피해 논리</th></tr>{rows(d['section4_companies']['damage'],'🔴','r','type','logic')}</table>
</div>
<div class="footer">본 리포트는 AI 기반 분석 시스템에 의해 자동 생성되었습니다.</div>
</body></html>"""

def html_s5(d):
    s = d['section5_sentiment']
    fv = int(s['fng_value']) if str(s['fng_value']).isdigit() else 50
    fg_cls = 'r' if fv < 25 else 'y' if fv < 50 else 'g'

    inds = "".join([
        f'<tr><td>{ind["name"]}</td><td class="y">{ind["value"]}</td>'
        f'<td style="font-size:12px;color:#8b949e">{ind["level"]}</td>'
        f'<td style="font-size:12px;color:#58a6ff">{ind["signal"]}</td></tr>'
        for ind in s['indicators']
    ])
    scens = "".join([
        f'<div style="margin-bottom:9px;font-size:12.5px"><span class="b">▸</span> <strong style="color:#f0f6fc">{sc["name"]}</strong>: <span class="card-body">{sc["content"]}</span></div>'
        for sc in s['scenarios']
    ])
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{BASE_CSS}</head><body>
{hdr("📊 시장 심리 정량 분석", d['report_date'])}
<div class="tag">Sentiment & Quantitative Analysis</div>
<div class="card" style="margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <div class="card-title">종합 판정: <span class="{fg_cls}">{s['overall']}</span></div>
    <div class="badge br">Fear&Greed {s['fng_value']}/100</div>
  </div>
  <table><tr><th>지표</th><th>현재값</th><th>수준</th><th>시그널</th></tr>{inds}</table>
</div>
<div class="card" style="margin-bottom:14px">
  <div class="card-title" style="margin-bottom:8px">역발상(Contrarian) 분석</div>
  <div class="card-body">{s['contrarian_comment']}</div>
</div>
<div class="card">
  <div class="card-title" style="margin-bottom:12px">시나리오 전망</div>
  {scens}
</div>
<div class="footer">본 리포트는 AI 기반 분석 시스템에 의해 자동 생성되었습니다.</div>
</body></html>"""

def html_s6(d):
    s = d['section6_matrix']
    issues = s['issues']

    # 5×5 매트릭스 (간략 표기)
    short = [iss[:7] for iss in issues]
    symbols = [['—','▲강화','▲강화','▲강화','▲강화'],
               ['▲강화','—','▲강화','▲강화','▲강화'],
               ['—','▲고착','—','▲강화','▼완화'],
               ['▼완화','▼완화','▼압력','—','▲강화'],
               ['▲악화','▲추가','—','▲위축','—']]
    header_cells = "".join([f'<th style="font-size:10px">{s}</th>' for s in short])
    matrix_rows = ""
    for i, row in enumerate(symbols):
        cells = "".join([
            f'<td style="font-size:11px;text-align:center;color:#484f58">—</td>' if cell == '—'
            else f'<td style="font-size:11px;text-align:center;color:{"#3fb950" if "강화" in cell or "추가" in cell else "#f85149" if "완화" in cell or "압력" in cell or "위축" in cell or "악화" in cell else "#e3b341"}">{cell}</td>'
            for cell in row
        ])
        matrix_rows += f'<tr><td style="font-size:11px;color:#58a6ff;font-weight:600">{short[i]}</td>{cells}</tr>'

    compound = "".join([
        f'<div class="card"><div class="card-title">{"①②③"[i]} {ef["title"]}</div><div class="card-body">{ef["content"]}</div></div>'
        for i, ef in enumerate(s['compound_effects'][:3])
    ])

    kr_pts = "".join([f'<div style="margin-bottom:7px;font-size:12.5px"><span class="b">▸</span> <span class="card-body">{pt}</span></div>' for pt in s.get('kr_investor_points', [])])

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{BASE_CSS}</head><body>
{hdr("⚡ 크로스 임팩트 매트릭스", d['report_date'])}
<div class="tag">Cross-Impact Matrix</div>
<div class="card" style="margin-bottom:16px">
  <table><tr><th></th>{header_cells}</tr>{matrix_rows}</table>
</div>
<div class="tag">핵심 복합 효과</div>
{compound}
<div class="card" style="margin-top:4px">
  <div class="card-title" style="margin-bottom:12px">🇰🇷 한국 투자자 포인트</div>
  {kr_pts}
</div>
<div class="footer">본 리포트는 AI 기반 분석 시스템에 의해 자동 생성되었습니다. 투자 판단의 최종 책임은 투자자 본인에게 있습니다.</div>
</body></html>"""

# ── 5. HTML → PNG / PDF (Playwright) ────────────────────────────────────

def html_to_png(html, path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 960, 'height': 800})
        page.set_content(html, wait_until='networkidle')
        h = page.evaluate('document.body.scrollHeight')
        page.set_viewport_size({'width': 960, 'height': h})
        page.screenshot(path=path, full_page=True)
        browser.close()

def html_to_pdf(sections_html, path):
    from playwright.sync_api import sync_playwright
    combined = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      body {{ font-family:'Noto Sans KR',sans-serif; background:#0d1117; color:#e6edf3; }}
      .pg {{ page-break-after:always; padding:40px 48px; }}
      .pg:last-child {{ page-break-after:avoid; }}
    </style></head><body>"""
    for html in sections_html:
        body = html[html.find('<body>')+6 : html.find('</body>')]
        combined += f'<div class="pg">{body}</div>'
    combined += "</body></html>"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(combined, wait_until='networkidle')
        page.pdf(path=path, format='A4', print_background=True,
                 margin={'top':'0','bottom':'0','left':'0','right':'0'})
        browser.close()

# ── 6. 텔레그램 전송 ─────────────────────────────────────────────────────

def tg_document(path, caption, token, chat_id):
    with open(path, 'rb') as f:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={'chat_id': chat_id, 'caption': caption},
            files={'document': f}, timeout=60
        )

def tg_media_group(paths, token, chat_id):
    files, media = {}, []
    for i, p in enumerate(paths):
        key = f'img{i}'
        files[key] = open(p, 'rb')
        media.append({'type': 'photo', 'media': f'attach://{key}'})
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMediaGroup",
        data={'chat_id': chat_id, 'media': json.dumps(media)},
        files=files, timeout=120
    )
    for f in files.values():
        f.close()

# ── 7. 메인 ─────────────────────────────────────────────────────────────

def main():
    TOKEN   = os.environ['TELEGRAM_BOT_TOKEN']
    CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
    today   = datetime.now().strftime('%Y-%m-%d')

    print("① 시장 데이터 수집...")
    mkt = get_market_data()
    fg  = get_fear_greed()

    print("② Claude API 리포트 생성 (웹검색 포함)...")
    report = generate_report(mkt, fg)

    print("③ HTML 카드 생성...")
    htmls = [
        html_s1(report, mkt, fg),
        html_s2(report),
        html_s3(report),
        html_s4(report),
        html_s5(report),
        html_s6(report),
    ]

    print("④ 이미지 6장 생성...")
    img_paths = []
    names = ['01_이슈', '02_인과체인', '03_섹터', '04_기업', '05_심리', '06_매트릭스']
    for html, name in zip(htmls, names):
        p = f'/tmp/macro_{name}.png'
        html_to_png(html, p)
        img_paths.append(p)
        print(f"   {name} ✓")

    print("⑤ PDF 생성...")
    pdf_path = f'/tmp/macro_briefing_{today}.pdf'
    html_to_pdf(htmls, pdf_path)

    print("⑥ 텔레그램 전송...")
    tg_document(pdf_path, f'📊 글로벌 매크로 브리핑 {today}', TOKEN, CHAT_ID)
    tg_media_group(img_paths, TOKEN, CHAT_ID)

    print("완료!")

if __name__ == '__main__':
    main()
