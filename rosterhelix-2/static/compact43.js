
/* RosterHelix 4.3: workspace personalization, multi-player trade research,
   compact player explorer, and defensive heatmap. Existing API unchanged. */
(()=>{'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const safeRead=(k,d)=>{try{return JSON.parse(localStorage.getItem(k))??d}catch{return d}};
const save=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch{}};
async function api(url){const r=await fetch(url,{credentials:'same-origin'}),d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
const season=()=>$('#ssSeason')?.value||$('#season')?.value||'2026';
const scoring=()=>$('#ssScoring')?.value||'ppr';
const cardRoot=$('.rh41-shell');
if(cardRoot){
 const tiles=$('.rh41-tiles'),grid=$('.rh41-grid'),workspace=$('.rh41-shell > .rh41-panel');
 const parts=[{id:'shortcuts',label:'Tool shortcuts',node:tiles},{id:'quick',label:'Quick Start/Sit and favorites',node:grid},{id:'workspace',label:'Split analytics workspace',node:workspace}].filter(p=>p.node);
 let order=safeRead('rh43_order',parts.map(p=>p.id)).filter(id=>parts.some(p=>p.id===id));
 parts.forEach(p=>{if(!order.includes(p.id))order.push(p.id)});
 let hidden=safeRead('rh43_hidden',[]).filter(id=>parts.some(p=>p.id===id));
 const bar=document.createElement('div');bar.className='rh43-custom-bar';
 bar.innerHTML='<div><b>My analytics workspace</b><small>Reorder and show only the panels you use</small></div><button type="button" class="rh43-btn" id="rh43Customize" aria-expanded="false">⚙ Customize</button>';
 cardRoot.insertBefore(bar,tiles);
 const editor=document.createElement('div');editor.id='rh43Editor';editor.className='rh43-editor';editor.hidden=true;bar.after(editor);
 const render=()=>{
  const anchor=editor;
  order.forEach(id=>{const part=parts.find(p=>p.id===id);if(part){cardRoot.appendChild(part.node);part.node.hidden=hidden.includes(id)}});
  editor.innerHTML=order.map((id,i)=>{const p=parts.find(p=>p.id===id);return `<div class="rh43-edit-row"><label><input type="checkbox" data-show="${id}" ${hidden.includes(id)?'':'checked'}> ${esc(p.label)}</label><span><button type="button" data-up="${id}" ${i===0?'disabled':''} aria-label="Move ${esc(p.label)} up">↑</button><button type="button" data-down="${id}" ${i===order.length-1?'disabled':''} aria-label="Move ${esc(p.label)} down">↓</button></span></div>`}).join('')+'<button type="button" id="rh43Reset" class="rh43-btn">Reset layout</button>';
  editor.querySelectorAll('[data-show]').forEach(el=>el.onchange=()=>{hidden=el.checked?hidden.filter(x=>x!==el.dataset.show):[...hidden,el.dataset.show];save('rh43_hidden',hidden);render()});
  editor.querySelectorAll('[data-up],[data-down]').forEach(el=>el.onclick=()=>{const id=el.dataset.up||el.dataset.down,i=order.indexOf(id),j=i+(el.dataset.up?-1:1);[order[i],order[j]]=[order[j],order[i]];save('rh43_order',order);render()});
  $('#rh43Reset').onclick=()=>{order=parts.map(p=>p.id);hidden=[];save('rh43_order',order);save('rh43_hidden',hidden);render()};
 };
 $('#rh43Customize').onclick=()=>{editor.hidden=!editor.hidden;$('#rh43Customize').setAttribute('aria-expanded',String(!editor.hidden))};
 render();
 // Restore split workspace tool choices and keep them between visits.
 for(const [id,key] of [['rh41Tool1','left'],['rh41Tool2','right']]){
  const sel=$('#'+id);if(!sel)continue;
  const remembered=safeRead('rh43_'+key,null);
  if(remembered&&[...sel.options].some(o=>o.value===remembered)){sel.value=remembered;sel.dispatchEvent(new Event('change'))}
  sel.addEventListener('change',()=>save('rh43_'+key,sel.value));
 }
}
// Trade Lab 2.0: multi-player historical comparisons, with explicit limitations.
const trade=$('#trade');
if(trade){
 const old=trade.querySelector('.panel');if(old)old.classList.add('rh43-legacy');
 const intro=document.createElement('div');intro.className='rh43-page-head';
 intro.innerHTML='<div><span class="rh43-kicker">TRADE RESEARCH</span><h2>Trade Lab 2.0</h2><p>Compare multiple players on each side using recorded fantasy production.</p></div><button type="button" id="rh43TradeLegacy" class="rh43-btn">Show original trade tool</button>';
 trade.insertBefore(intro,old);
 const app=document.createElement('div');app.className='rh43-trade-app';
 app.innerHTML=`<div class="rh43-trade-controls"><label>Season <input type="number" id="rh43TradeSeason" min="1999" max="2100" value="${esc(season())}"></label><label>Scoring <select id="rh43TradeScoring"><option value="ppr">Full PPR</option><option value="half">Half PPR</option><option value="standard">Standard</option></select></label><button class="primary" id="rh43TradeRun">Compare sides</button></div>
 <div class="rh43-trade-sides"><div class="rh43-trade-side"><h3>Team A gives</h3><div id="rh43TradeA"></div><button type="button" class="rh43-btn" data-add="A">+ Add player</button></div><div class="rh43-trade-side"><h3>Team B gives</h3><div id="rh43TradeB"></div><button type="button" class="rh43-btn" data-add="B">+ Add player</button></div></div>
 <div id="rh43TradeResult" class="rh43-output" aria-live="polite">Select players from suggestions and compare their historical production.</div><p class="rh43-disclaimer">Research aid, not a trade fairness verdict. Adding player PPG values does not account for roster slots, replacement value, positional scarcity, future roles, injuries, or playoff schedule.</p>`;
 old.before(app);
 $('#rh43TradeLegacy').onclick=()=>{old.classList.toggle('rh43-legacy');$('#rh43TradeLegacy').textContent=old.classList.contains('rh43-legacy')?'Show original trade tool':'Hide original trade tool'};
 const selections={A:[],B:[]};
 function add(side){
  const host=$('#rh43Trade'+side);if(host.children.length>=6)return;
  const row=document.createElement('div');row.className='rh43-player-entry';
  row.innerHTML='<div class="rh43-player-search"><input class="field" placeholder="Search a player (2+ letters)" aria-label="Player search"><div class="rh43-dropdown" hidden></div></div><button type="button" class="rh43-remove" aria-label="Remove player">×</button>';
  host.append(row);const input=row.querySelector('input'),menu=row.querySelector('.rh43-dropdown');
  row.querySelector('.rh43-remove').onclick=()=>row.remove();
  let token=0,timer;
  input.oninput=()=>{delete row.dataset.player;clearTimeout(timer);const q=input.value.trim(),n=++token;if(q.length<2){menu.hidden=true;return}
   menu.hidden=false;menu.textContent='Searching…';
   timer=setTimeout(async()=>{try{const d=await api('/api/search?'+new URLSearchParams({q,season:$('#rh43TradeSeason').value}));if(token!==n)return;
    menu.replaceChildren();const list=(d.players||[]).slice(0,10);
    if(!list.length){menu.textContent='No matching player';return}
    list.forEach(p=>{const b=document.createElement('button');b.type='button';b.textContent=`${p.player} · ${p.pos||'—'} · ${p.team||'—'}`;b.onclick=()=>{input.value=p.player;row.dataset.player=p.player;menu.hidden=true};menu.append(b)})
   }catch(e){if(token===n)menu.textContent=e.message}},180)
  };
  input.onkeydown=e=>{if(e.key==='Escape')menu.hidden=true;if(e.key==='Enter'&&!menu.hidden){const first=menu.querySelector('button');if(first){e.preventDefault();first.click()}}};
  document.addEventListener('pointerdown',e=>{if(!row.contains(e.target))menu.hidden=true});
 }
 trade.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>add(b.dataset.add));
 add('A');add('B');
 $('#rh43TradeRun').onclick=async()=>{
  const out=$('#rh43TradeResult'),names={};
  for(const side of ['A','B']){
   const rows=[...$('#rh43Trade'+side).children];
   if(!rows.length||rows.some(r=>!r.dataset.player||r.dataset.player!==r.querySelector('input').value.trim())){out.textContent=`Select valid Team ${side} players from the suggestions.`;return}
   names[side]=rows.map(r=>r.dataset.player);
  }
  if(new Set([...names.A,...names.B]).size!==names.A.length+names.B.length){out.textContent='Each player must appear only once.';return}
  out.textContent='Loading historical comparison…';
  try{
   const params=new URLSearchParams({season:$('#rh43TradeSeason').value,scoring:$('#rh43TradeScoring').value,type:'trade'});
   [...names.A,...names.B].forEach(n=>params.append('player',n));
   const d=await api('/api/analyze?'+params);
   const all=d.players||[],n=names.A.length;
   const side=(arr,label)=>{const sum=arr.reduce((v,p)=>v+Number(p.ppg||0),0);
    return `<div class="rh43-side-result"><h3>${label}</h3><strong>${sum.toFixed(1)} <small>sum of historical PPG</small></strong>${arr.map(p=>`<div class="rh43-stat-line"><span>${esc(p.name)} <small>${esc(p.position||'')} · ${p.games} games</small></span><b>${Number(p.ppg).toFixed(1)}</b></div>`).join('')}</div>`};
   out.innerHTML=`<div class="rh43-trade-sides">${side(all.slice(0,n),'Team A gives')}${side(all.slice(n),'Team B gives')}</div><p class="rh43-disclaimer">These totals are descriptive, not a projection or an exchange-value score. Comparing unequal player counts by summed PPG is particularly misleading.</p>`;
  }catch(e){out.textContent='Unable to compare: '+e.message}
 };
}
// Player Explorer compact results: filters existing cards without touching chart handlers.
const explorer=$('#players');
if(explorer){
 const head=explorer.querySelector('.explorer-head');
 if(head){
  const bar=document.createElement('div');bar.className='rh43-explorer-tools';
  bar.innerHTML='<label>Position <select id="rh43Position"><option value="">All positions</option><option>QB</option><option>RB</option><option>WR</option><option>TE</option></select></label><label>Sort <select id="rh43Sort"><option value="ppg">Fantasy PPG</option><option value="trend">Recent PPG</option><option value="games">Games recorded</option></select></label><span id="rh43PlayerCount" class="rh43-count"></span>';
  head.after(bar);
  const body=$('#playersBody'),cards=$('#playerCards');
  function apply(){
   const pos=$('#rh43Position').value,sort=$('#rh43Sort').value;
   // Existing player cards retain original click handlers and chart behavior.
   const rows=[...body.querySelectorAll('tr')];
   rows.sort((a,b)=>{const col=sort==='ppg'?4:sort==='trend'?5:3;return (Number(b.children[col]?.textContent)||0)-(Number(a.children[col]?.textContent)||0)});
   let shown=0;
   rows.forEach(row=>{const match=!pos||row.children[2]?.textContent.trim()===pos;row.hidden=!match;if(match){body.append(row);shown++}});
   if(cards){const cardNodes=[...cards.children];cardNodes.forEach(c=>{const txt=c.textContent;const match=!pos||new RegExp('\\b'+pos+'\\b').test(txt);c.hidden=!match})}
   $('#rh43PlayerCount').textContent=shown+' matching players';
  }
  $('#rh43Position').onchange=apply;$('#rh43Sort').onchange=apply;
  $('#searchBtn')?.addEventListener('click',()=>setTimeout(apply,350));setTimeout(apply,900);
 }
}
// Defense Explorer: compact visual heatmap based on real backend rows.
const defense=$('#defense'),defBody=$('#defBody');
if(defense&&defBody){
 const heat=document.createElement('div');heat.id='rh43Heatmap';heat.className='rh43-heatmap';
 defense.querySelector('.panel')?.insertBefore(heat,defense.querySelector('.tablewrap'));
 let pending=false;
 function render(){
  pending=false;const rows=[...defBody.querySelectorAll('tr')].filter(r=>r.children.length>=4);
  const items=rows.map(r=>({team:r.children[1].textContent.trim(),points:Number(r.children[3].textContent.replace(/[^0-9.-]/g,''))})).filter(x=>Number.isFinite(x.points));
  if(!items.length){heat.innerHTML='';return}
  const max=Math.max(...items.map(x=>x.points)),min=Math.min(...items.map(x=>x.points)),span=max-min||1;
  heat.innerHTML='<div class="rh43-heat-title"><b>Fantasy points allowed heatmap</b><small>Higher = more points allowed to selected position</small></div><div class="rh43-heat-grid">'+items.map(x=>{const pct=(x.points-min)/span,alpha=(.13+.72*pct).toFixed(2);return `<div class="rh43-heat-cell" style="--heat:${alpha}" title="${esc(x.team)}: ${x.points.toFixed(1)} FP allowed/week"><b>${esc(x.team)}</b><span>${x.points.toFixed(1)}</span></div>`}).join('')+'</div>';
 }
 new MutationObserver(()=>{if(!pending){pending=true;requestAnimationFrame(render)}}).observe(defBody,{childList:true});
 render();
}
})();
