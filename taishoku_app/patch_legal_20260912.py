from pathlib import Path
import json
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('taishoku_app/runtime').resolve()
render = root / 'report_template_v0.1' / 'render_report.py'
template = root / 'report_template_v0.1' / 'report_template.html'
rules = root / 'workflow_rule_package_v0.1' / 'workflow_rules_v0.1.json'

notice = ('<div class="notice compact"><strong>「退職給付金」という名前について</strong>'
          '<p>広告などで「退職給付金」と呼ばれることがありますが、「退職給付金」という名称の公的制度が別にあるわけではありません。'
          'このレポートでは、基本手当・再就職手当・傷病手当金など、実際の制度名ごとに案内します。'
          '給付の可否・金額・期間は、それぞれの制度の要件と行政機関等の審査で決まります。</p></div>')

source_entries = [
    ("厚生労働省｜令和8年8月からの基本手当日額", "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000160564_00050.html"),
    ("ハローワーク那覇｜退職給付金をうたう民間サービスへの注意", "https://jsite.mhlw.go.jp/okinawa-roudoukyoku/naha_retirement_benefits_202603.html"),
    ("国民生活センター｜失業給付等の申請サポートに関する注意", "https://www.kokusen.go.jp/news/data/n-20251203_1.html"),
]

text = render.read_text(encoding='utf-8')
if "TEMPLATE_VERSION = '0.2.4'" in text:
    text = text.replace("TEMPLATE_VERSION = '0.2.4'", "TEMPLATE_VERSION = '0.2.5'", 1)
elif "TEMPLATE_VERSION = '0.2.5'" not in text:
    raise SystemExit('unexpected TEMPLATE_VERSION')

marker = "SOURCE_URLS = [\n"
if marker not in text:
    raise SystemExit('SOURCE_URLS marker not found')
for label, url in source_entries:
    if url not in text:
        entry = f"    ({label!r}, {url!r}),\n"
        text = text.replace(marker, marker + entry, 1)
render.write_text(text, encoding='utf-8')

html = template.read_text(encoding='utf-8')
placeholder = '{{employment_benefit_summary}}'
if notice not in html:
    if placeholder not in html:
        raise SystemExit('employment_benefit_summary placeholder not found')
    html = html.replace(placeholder, notice + '\n      ' + placeholder, 1)
template.write_text(html, encoding='utf-8')

data = json.loads(rules.read_text(encoding='utf-8'))
if data.get('rule_version') != '0.2.0':
    raise SystemExit(f"unexpected rule_version: {data.get('rule_version')}")
data['verified_at'] = '2026-09-07'
urls = data.setdefault('source_urls', [])
for _, url in source_entries:
    if url not in urls:
        urls.append(url)
rules.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

# Build-time assertions: fail closed if the approved patch is incomplete.
render_after = render.read_text(encoding='utf-8')
template_after = template.read_text(encoding='utf-8')
rules_after = json.loads(rules.read_text(encoding='utf-8'))
assert "TEMPLATE_VERSION = '0.2.5'" in render_after
assert notice in template_after
assert rules_after['verified_at'] == '2026-09-07'
assert rules_after['rule_version'] == '0.2.0'
for _, url in source_entries:
    assert url in render_after
    assert url in rules_after['source_urls']
print('approved legal/source patch applied')
