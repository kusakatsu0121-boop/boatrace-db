#!/usr/bin/env python3
"""Make instant-report status pages plain and user-facing; do not change decisions."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
target = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
text = target.read_text(encoding='utf-8')

start = text.find('function processingPage() {')
marker = '\n}\n\nfunction safeId'
end = text.find(marker, start)
if start < 0 or end < 0:
    raise SystemExit('processingPage boundary not found')
end += 2
new_processing = r'''function processingPage() {
  return `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3">
<title>回答を整理しています</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f5f7fb;color:#18202a}
main{max-width:560px;margin:10vh auto;padding:24px 18px}
.card{background:#fff;border:1px solid #e5e9ef;border-radius:20px;padding:30px 22px;box-shadow:0 10px 30px rgba(20,35,55,.07)}
.dot{width:14px;height:14px;border-radius:50%;background:#16263a;animation:p 1.2s ease-in-out infinite;margin-bottom:18px}
@keyframes p{50%{opacity:.25;transform:scale(.8)}}
h1{font-size:24px;margin:0 0 12px}p{line-height:1.8;margin:0;color:#4f5a67}
</style>
</head>
<body><main><div class="card"><div class="dot"></div><h1>回答を受け付けました</h1><p>いま、回答内容を整理しています。結果が出るまでこのままお待ちください。確認が必要な場合は、分からない点と次に確認することを表示します。</p></div></main></body>
</html>`;
}'''
text = text[:start] + new_processing + text[end:]

replacements = [
    (
        "const title = review ? '確認が必要な項目があります' : 'レポートを表示できませんでした';",
        "const title = review ? '回答を受け付けました' : '処理を完了できませんでした';",
        'review title'
    ),
    (
        "? '回答は受け付けましたが、給付の判断に確認が必要なため、レポートはまだ公開していません。'",
        "? '今回は、回答だけでは確定できない項目があるため、正式レポートはまだ出していません。下の「次に確認すること」だけご確認ください。'",
        'review explanation'
    ),
    (
        ": 'レポートの処理が正常に完了しませんでした。回答内容に問題があると決まったわけではありません。';",
        ": '処理に失敗しました。回答内容が間違っているとは限りません。少し時間を置いて、最初からもう一度お試しください。';",
        'failure explanation'
    ),
    (
        '<h2 style="font-size:1.1rem">確認すること</h2>',
        '<h2 style="font-size:1.1rem">今回、確認できていないこと</h2>',
        'details heading'
    ),
    (
        '同じ回答を再送信せず、運営者にお問い合わせください。',
        '同じ内容をそのまま送り直しても結果は変わりません。確認できる情報が増えたら、最初からもう一度お試しください。',
        'final instruction'
    ),
]
for old, new, label in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, got {count}')
    text = text.replace(old, new, 1)

target.write_text(text, encoding='utf-8')
print('user-facing status copy patched; no calculation, approval, token, or delivery changes')
