// Render the exact finalizer notice without calling approve, persistence or delivery.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
const [file, dir] = process.argv.slice(2);
const source=fs.readFileSync(file,'utf8');
const start=source.indexOf('const REPORT_CAUTION_MARKER');
const end=source.indexOf('export async function finalizeInstantReport',start);
if(start<0||end<0) throw new Error('notice anchors changed');
const add=vm.runInNewContext(source.slice(start,end)+'\naddReportCaution',{fs,path});
for(const name of fs.readdirSync(dir)){
 const job=path.join(dir,name);
 fs.copyFileSync(path.join(job,'report.html'),path.join(job,'report_preview.html'));
 add(job);
 const before=fs.readFileSync(path.join(job,'report_preview.html'),'utf8');
 add(job);
 if(before!==fs.readFileSync(path.join(job,'report_preview.html'),'utf8'))throw new Error('notice not idempotent');
}
console.log('7 final HTML previews; no approval or delivery');
