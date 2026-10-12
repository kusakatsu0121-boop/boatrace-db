from pathlib import Path
import sys
root=Path(sys.argv[1])/'report_template_v0.1'
p=root/'render_report.py';s=p.read_text()
for old,new in [("install(globals())","install(globals())\nfrom unattended_copy import install as install_unattended_copy\ninstall_unattended_copy(globals())"),("roadmap_rows(actions.get('timeline', []))","roadmap_rows(actions.get('timeline', []), answer)"),("task_rows(actions.get('timeline', []))","task_rows(actions.get('timeline', []), answer)"),("e(answer.get('reference_id', '未設定'))","e(answer.get('reference_id') or '')")]:
 assert s.count(old)==1,old
 s=s.replace(old,new)
s=s.replace("    html_path.parent.mkdir", "    if not answer.get('reference_id'):\n        document = document.replace('<span>受付番号 </span>', '')\n    if answer.get('employment_status') != 'retired' and answer.get('exit_date_status') != 'already_retired':\n        document = document.replace('退職したので、加入手続きと保険料を教えてください', '退職後に備えて、加入手続きと保険料を教えてください')\n    html_path.parent.mkdir")
s=s.replace("'document_title': f'{answer.get(\"display_name\", \"あなた\")}｜退職前後ワークフロー',", "'document_title': e(f'{answer.get(\"display_name\", \"あなた\")}｜退職前後ワークフロー'),")
p.write_text(s)
p=root/'report_template.html' ;s=p.read_text().replace('まず1つ目から進めてください。分からないときの聞き方も載せています。','期限のある手続きを先に確かめてください。別の窓口への相談は、並行して進められます。').replace('この順番で進める','手続きごとの進め方').replace('窓口では、書いてある言葉をそのまま伝えて大丈夫です。','窓口で伝える言葉と用意するものをまとめています。').replace('追加で確認したいこと','申請前に確かめること')
p.write_text(s)
print('unattended reader copy applied; evaluation and access controls unchanged')
