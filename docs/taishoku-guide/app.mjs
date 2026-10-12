import { buildGuide, sources } from './guide.mjs';
const fields = ['employment','work','reason','sickness','insurance'];
const results = document.querySelector('#results');
const tasks = document.querySelector('#tasks');
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function card(task, index) {
  const article = el('article', null, 'task');
  article.dataset.task = task.id;
  article.append(el('p', index === 0 ? 'まず、ここから' : 'あわせて進めること', 'step'), el('h3', task.title), el('p', task.action));
  const say = el('p', null, 'say');
  say.append(el('strong', 'そのまま伝える言葉'), document.createTextNode(`「${task.say}」`));
  article.append(say);
  if (task.timing) article.append(el('p', task.timing, 'notice'));
  const dl = el('dl');
  for (const [label,value] of [['連絡する先', task.where], ['手元に用意するもの', task.bring], ['分からない・そろわないとき', task.fallback]]) dl.append(el('dt',label),el('dd',value));
  article.append(dl);
  if (task.more?.length) {
    const details = el('details');
    details.append(el('summary','補足を読む'));
    task.more.forEach(text => details.append(el('p',text)));
    article.append(details);
  }
  const [label,url] = sources[task.source];
  const link = el('a',label); link.href = url; link.rel = 'noreferrer';
  const p = el('p'); p.append(link); article.append(p);
  if (task.extraSource) { const extra = el('a',task.extraSource[0]); extra.href=task.extraSource[1]; extra.rel='noreferrer'; const line=el('p'); line.append(extra); article.append(line); }
  return article;
}
document.querySelector('#show').addEventListener('click', () => {
  const input = Object.fromEntries(fields.map(id => [id, document.getElementById(id).value]));
  tasks.replaceChildren(...buildGuide(input).map(card));
  results.hidden = false;
  document.querySelector('#result-title').focus({preventScroll:true});
  results.scrollIntoView({block:'start'});
});
document.querySelector('#edit').addEventListener('click', () => {
  results.hidden = true;
  document.querySelector('#employment').focus();
});
// Do not restore previous answers after reload or back/forward navigation.
function reset() { fields.forEach(id => { document.getElementById(id).selectedIndex = 0; }); results.hidden = true; tasks.replaceChildren(); }
window.addEventListener('pageshow',reset);
document.querySelector('#load-status').hidden = true;
