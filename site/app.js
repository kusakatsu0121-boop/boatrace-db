let feed=null,venueIndex=0,raceIndex=0,view="basic";
const $=id=>document.getElementById(id),venueStrip=$("venueStrip"),raceStrip=$("raceStrip"),raceHeader=$("raceHeader"),viewTabs=$("viewTabs"),tableWrap=$("tableWrap"),empty=$("empty");
const views=[["basic","基本"],["course","コース・ST"],["edge","状態・独自"]];
const has=v=>v!==undefined&&v!==null&&v!==""&&!Number.isNaN(Number(v));
const n=(v,d=1)=>has(v)?Number(v).toFixed(d):"—";
const pct=(v,d=1)=>has(v)?`${Number(v).toFixed(d)}%`:"—";
const st=v=>has(v)?Number(v).toFixed(3).replace(/^0/,""):"—";
const signed=(v,d=1,suffix="")=>has(v)?`${Number(v)>0?"+":""}${Number(v).toFixed(d)}${suffix}`:"—";
function chip(text,active,fn){const b=document.createElement("button");b.className=`chip${active?" active":""}`;b.textContent=text;b.onclick=fn;return b}
function tone(v,goodWhenPositive=true,threshold=0){if(!has(v)||Math.abs(Number(v))<threshold)return"neutral";const pos=Number(v)>0;return(pos===goodWhenPositive)?"good":"bad"}
function cell(value,cls="neutral",sub=""){return`<span class="val ${cls}">${value}</span>${sub?`<span class="subval">${sub}</span>`:""}`}
function row(label,entries,renderer){return`<tr><th class="row-label">${label}</th>${entries.map(e=>`<td>${renderer(e)}</td>`).join("")}</tr>`}
function section(label){return`<tr class="section-row"><th class="row-label">${label}</th>${"<td>●</td>".repeat(6)}</tr>`}
function renderVenues(){venueStrip.replaceChildren();(feed?.venues||[]).forEach((v,i)=>venueStrip.appendChild(chip(v.venue,i===venueIndex,()=>{venueIndex=i;raceIndex=0;renderAll()})))}
function renderRaces(){raceStrip.replaceChildren();const races=feed?.venues?.[venueIndex]?.races||[];races.forEach((r,i)=>raceStrip.appendChild(chip(`${r.race_no}R`,i===raceIndex,()=>{raceIndex=i;renderAll(false)})))}
function renderTabs(){viewTabs.replaceChildren();views.forEach(([key,label])=>{const b=document.createElement("button");b.className=`view-tab${view===key?" active":""}`;b.textContent=label;b.onclick=()=>{view=key;renderTabs();renderTable()};viewTabs.appendChild(b)})}
function header(entries){return`<thead><tr><th class="row-label">艇</th>${entries.map(e=>`<th class="boat-head boat-${e.boat_no}"><div class="boat-num">${e.boat_no}</div><div class="boat-name">${e.name||"—"}</div><div class="boat-grade">${e.class_grade||""}</div></th>`).join("")}</tr></thead>`}
function basicRows(es){return[
 row("F/L",es,e=>cell(`F${e.f_count??0}/L${e.l_count??0}`,(e.f_count||e.l_count)?"warn":"neutral")),
 row("全国勝率",es,e=>cell(n(e.national_win_rate,2))),
 row("全国3連",es,e=>cell(pct(e.national_3rate))),
 row("当地勝率",es,e=>cell(n(e.local_win_rate,2))),
 row("当地3連",es,e=>cell(pct(e.local_3rate))),
 row("公表ST",es,e=>cell(st(e.pub_avg_st))),
 row("モーター",es,e=>cell(e.motor_no??"—")),
 row("M2連",es,e=>cell(pct(e.motor_2rate))),
 row("M3連",es,e=>cell(pct(e.motor_3rate)))
].join("")}
function courseRows(es){return[
 row("実績数",es,e=>cell(e.course_n??"—")),
 row("1着率",es,e=>cell(pct(e.course_win1_rate))),
 row("3連率",es,e=>cell(pct(e.course_top3_rate))),
 row("平均ST",es,e=>cell(st(e.course_avg_st))),
 row("ST1着率",es,e=>cell(pct(e.course_st_top_rate))),
 row("STブレ",es,e=>cell(has(e.course_st_sd)?n(e.course_st_sd,3):"—")),
 section("全体参考"),
 row("全体3連",es,e=>cell(pct(e.all_top3_rate))),
 row("全体ST",es,e=>cell(st(e.all_avg_st)))
].join("")}
function edgeRows(es){return[
 section("直近状態"),
 row("直近5 3連",es,e=>cell(pct(e.recent5_top3_rate))),
 row("直近10 3連",es,e=>cell(pct(e.recent10_top3_rate))),
 row("直近20 3連",es,e=>cell(pct(e.recent20_top3_rate))),
 row("実力傾向",es,e=>{const t=e.trend||"不明";return cell(t,t==="上向き"?"good":t==="下向き"?"bad":"neutral")}),
 row("3連変化",es,e=>cell(signed(e.trend_top3_delta,1,"pt"),tone(e.trend_top3_delta,true,3))),
 row("ST変化",es,e=>cell(signed(e.trend_st_delta,3,"秒"),tone(e.trend_st_delta,false,.003))),
 section("独自指標"),
 row("強敵補正",es,e=>cell(signed(e.strong_field_perf,2),tone(e.strong_field_perf,true,.10),has(e.strong_field_n)?`n=${e.strong_field_n}`:"")),
 row("強敵3連",es,e=>cell(pct(e.strong_field_top3_rate),"neutral",has(e.strong_field_n)?`n=${e.strong_field_n}`:"")),
 row("M依存",es,e=>cell(signed(e.motor_dependency_delta,1,"pt"),Math.abs(Number(e.motor_dependency_delta||0))>=15?"warn":"neutral")),
 row("悪機3連",es,e=>cell(pct(e.bad_motor_top3_rate),"neutral",has(e.bad_motor_n)?`n=${e.bad_motor_n}`:"")),
 row("2走目差",es,e=>{if(!has(e.second_run_top3_rate)||!has(e.first_run_top3_rate))return cell("—");const d=Number(e.second_run_top3_rate)-Number(e.first_run_top3_rate);return cell(signed(d,1,"pt"),tone(d,true,5),has(e.second_run_n)?`n=${e.second_run_n}`:"")})
].join("")}
function renderTable(){const venue=feed?.venues?.[venueIndex],race=venue?.races?.[raceIndex];if(!race){tableWrap.innerHTML="";empty.classList.remove("hidden");return}empty.classList.add("hidden");const es=[...(race.entries||[])].sort((a,b)=>(a.boat_no||9)-(b.boat_no||9));while(es.length<6)es.push({boat_no:es.length+1});const body=view==="basic"?basicRows(es):view==="course"?courseRows(es):edgeRows(es);tableWrap.innerHTML=`<table class="race-table">${header(es)}<tbody>${body}</tbody></table>`}
function renderHeader(){const venue=feed?.venues?.[venueIndex],race=venue?.races?.[raceIndex];if(!race){raceHeader.innerHTML="";return}raceHeader.innerHTML=`<div class="race-title">${venue.venue} ${race.race_no}R ${race.race_name||""}</div><div class="race-sub">${[race.grade,race.day_label,race.event_title,race.deadline?`締切 ${race.deadline}`:null].filter(Boolean).join(" · ")}</div>`}
function renderAll(withVenues=true){try{if(withVenues)renderVenues();renderRaces();renderHeader();renderTabs();renderTable()}catch(err){console.error("render error",err);$("dateMeta").textContent=`${feed?.race_date||""} · 表示エラー`;}}
async function boot(){try{const res=await fetch(`./data/today.json?t=${Date.now()}`,{cache:"no-store"});if(!res.ok)throw new Error(`HTTP ${res.status}`);feed=await res.json();if(!Array.isArray(feed.venues)||!feed.venues.length)throw new Error("no venues");$("dateMeta").textContent=`${feed.race_date} · ${feed.venues.length}場 · ${feed.venues.reduce((s,v)=>s+(v.races?.length||0),0)}R`;renderAll();if("serviceWorker"in navigator)navigator.serviceWorker.register("./sw.js?v=2").catch(console.warn)}catch(err){console.error(err);$("dateMeta").textContent="データ読込エラー";empty.classList.remove("hidden")}}
boot();
