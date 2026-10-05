"""Remove PDF production; keep HTML, evaluation, review and approval unchanged."""
from pathlib import Path
import sys
root = Path(sys.argv[1])

def replace(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f'HTML-only patch anchor mismatch: {old[:75]}')
    return text.replace(old, new, 1)

p=root/'report_template_v0.1/render_report.py'
s=p.read_text()
s=replace(s,'import fitz\n','')
s=replace(s,'def render(answer_path: Path, html_path: Path, pdf_path: Path, snapshot_path: Path | None) -> None:', 'def render(answer_path: Path, html_path: Path, snapshot_path: Path | None) -> None:')
s=replace(s,'    pdf_path.parent.mkdir(parents=True, exist_ok=True)\n','')
start=s.index('    # PDF remains an internal/manual-review preview.')
end=s.index('\ndef main() -> None:',start)
s=s[:start]+'\n'+s[end:]
s=replace(s,"    parser.add_argument('--pdf', type=Path, required=True)\n",'')
s=replace(s,'render(args.answer.resolve(), args.html.resolve(), args.pdf.resolve(), args.snapshot.resolve() if args.snapshot else None)', 'render(args.answer.resolve(), args.html.resolve(), args.snapshot.resolve() if args.snapshot else None)')
p.write_text(s)

p=root/'workflow_pipeline_v0.1/process_tally_submission.mjs'
s=p.read_text()
for old,new in [
 ('function runRenderer(answerPath, htmlPath, pdfPath, snapshotPath)', 'function runRenderer(answerPath, htmlPath, snapshotPath)'),
 ("[renderer, answerPath, '--html', htmlPath, '--pdf', pdfPath, '--snapshot', snapshotPath]", "[renderer, answerPath, '--html', htmlPath, '--snapshot', snapshotPath]"),
 ("  const pdfPath = path.join(jobDir, 'report_preview.pdf');\n", ''),
 ('runRenderer(answerPath, htmlPath, pdfPath, evaluationPath);','runRenderer(answerPath, htmlPath, evaluationPath);'),
 ("review_artifact: 'pdf_review_preview'", "review_artifact: 'html_preview'"),
 ('      pdf_review_preview: pdfPath,\n', ''),
 ('      pdf_preview: pdfPath,\n', ''),
 ('      pdf_sha256: sha256File(pdfPath),\n', ''),
]: s=replace(s,old,new)
p.write_text(s)
print('HTML-only reports enabled; approval and report-access code unchanged')
