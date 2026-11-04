/* RosterHelix 4.2 - UI improvements; no backend changes. */
(()=>{'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const selected=new Map();
const season=()=>$('#ssSeason')?.value||'2026',scoring=()=>$('#ssScoring')?.value||'ppr';
async function api(path){const r=await fetch(path,{credentials:'same-origin'});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
function suggest(input){if(!input)return;input.removeAttribute('list');input.autocomplete='off';
 const wrap=document.createElement('span');wrap.className='rh42-search';input.before(wrap);wrap.append(input);
 const menu=document.createElement('div');menu.className='rh42-menu';menu.hidden=true;wrap.append(menu);
 let seq=0,timer;input.addEventListener('input',()=>{selected.delete(input.id);clearTimeout(timer);const text=input.value.trim(),id=++seq;if(text.length<2){menu.hidden=true;return}
  menu.hidden=false;menu.textContent='Searching…';timer=setTimeout(async()=>{try{const d=await api('/api/search?'+new URLSearchParams({q:text,season:season()}));if(seq!==id)return;
   menu.replaceChildren();const matches=(d.players||[]).slice(0,12);if(!matches.length){menu.textContent='No players found for this season.';return}
   for(const p of matches){const b=document.createElement('button');b.type='button';b.innerHTML=`<strong>${esc(p.player)}</strong><small>${esc(p.team)} · ${esc(p.pos)} · ${p.games} games</small>`;
    b.onclick=()=>{input.value=p.player;selected.set(input.id,p.player);menu.hidden=true};menu.append(b)}
  }catch(e){if(seq===id)menu.textContent=e.message}},190)});
 input.addEventListener('keydown',e=>{if(e.key==='Escape')menu.hidden=true;if(e.key==='Enter'&&!menu.hidden){const first=menu.querySelector('button');if(first){e.preventDefault();first.click()}}});
 document.addEventListener('pointerdown',e=>{if(!wrap.contains(e.target))menu.hidden=true});
}
for(const id of ['rh41Search','rh41A','rh41B','ssA','ssB'])suggest($('#'+id));
const exact=id=>{const el=$('#'+id);return el&&selected.get(id)===el.value.trim()?el.value.trim():null};
function openFull(a,b){$('#ssA').value=a;$('#ssB').value=b;document.querySelector('[data-view="start"]')?.click();$('#ssCompare')?.click()}
const qResult=$('#rh41QuickResult');
$('#rh41Compare')?.addEventListener('click',async e=>{e.stopImmediatePropagation();const a=exact('rh41A'),b=exact('rh41B');
 if(!a||!b){qResult.textContent='Select both players from the dropdown suggestions.';return}if(a===b){qResult.textContent='Choose two different players.';return}
 const btn=$('#rh41Compare');btn.disabled=true;qResult.textContent='Calculating projections…';
 try{const q=new URLSearchParams({season:season(),scoring:scoring()});q.append('player',a);q.append('player',b);
 const d=await api('/api/projection?'+q),p=d.players||[];
 qResult.innerHTML=`<div class="rh42-projections">${p.map(x=>`<div><b>${esc(x.name)}</b><strong>${Number(x.projected_points).toFixed(1)} <small>FP</small></strong><small>Estimated · no opponent selected</small></div>`).join('')}</div><div class="rh42-result-foot"><span>${d.recommended_start?'Model preference: '+esc(d.recommended_start):'No clear preference'} · ${Number(d.projection_edge||0).toFixed(1)} point edge</span><button type="button" class="rh41-action" id="rh42Full">Full analysis</button></div>`;
 $('#rh42Full').onclick=()=>openFull(a,b);
 }catch(err){qResult.textContent='Unable to compare: '+err.message}finally{btn.disabled=false}
},true);
$('#rh41Find')?.addEventListener('click',e=>{e.stopImmediatePropagation();const name=exact('rh41Search');if(!name){$('#rh41SearchInfo').textContent='Select a player from the dropdown first.';return}
 $('#search').value=name;document.querySelector('[data-view="players"]')?.click();$('#searchBtn')?.click()},true);
$('#rh41Pin')?.addEventListener('click',e=>{const name=exact('rh41Search');if(!name){e.stopImmediatePropagation();$('#rh41SearchInfo').textContent='Select a player from the dropdown first.'}},true);
// Keep original Start/Sit event handlers intact; organize their rendered output using tab visibility.
const start=$('#start'),panel=start?.querySelector('.panel'),out=$('#ssResult');if(start&&panel&&out){
 start.classList.add('rh42-start');const h=document.createElement('div');h.className='rh42-heading';h.innerHTML='<div><span class="eyebrow">LINEUP INTELLIGENCE</span><h2>Start / Sit</h2><p class="muted">One compact workspace for every lineup decision.</p></div><button type="button" class="secondary" id="rh42Swap">⇄ Swap players</button>';start.insertBefore(h,panel);
 const tabs=document.createElement('div');tabs.className='rh42-tabs';tabs.innerHTML=['Overview','Usage','Matchups','Projections'].map((n,i)=>`<button type="button" data-tab="${i}" class="${i===0?'active':''}">${n}</button>`).join('');out.before(tabs);
 let active=0;function organize(){const children=[...out.children];for(const el of children){let tab=0;
 if(el.classList.contains('matchup-board'))tab=2;
 else if(el.classList.contains('projection-board'))tab=3;
 else if(el.classList.contains('grid2'))tab=1;
 else if(el.classList.contains('notice')&&/Projection engine/i.test(el.textContent))tab=3;
 el.dataset.rh42Tab=String(tab);el.hidden=tab!==active;
 }}
 tabs.querySelectorAll('button').forEach(b=>b.onclick=()=>{active=Number(b.dataset.tab);tabs.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));organize()});
 const obs=new MutationObserver(()=>organize());obs.observe(out,{childList:true});
 $('#rh42Swap').onclick=()=>{const a=$('#ssA'),b=$('#ssB'),x=$('#ssOppA'),y=$('#ssOppB');[a.value,b.value]=[b.value,a.value];[x.value,y.value]=[y.value,x.value]};
 const title=start.querySelector(':scope > h1'),subtitle=start.querySelector(':scope > p.muted');if(title)title.hidden=true;if(subtitle)subtitle.hidden=true;
 const notice=start.querySelector(':scope > .notice');if(notice)notice.classList.add('rh42-note');
}
})();
