/* 5.0D.2 UI stabilization. Does not alter prediction, imports or scoring. */
(()=>{'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=1)=>Number.isFinite(Number(v))&&v!=null?Number(v).toFixed(d):'—';
const quick=$('#rh41QuickResult'),button=$('#rh41Compare');
if(quick&&button){
 // The original 4.1 Analyze handler immediately navigates to Start/Sit.
 // Handle only this action in capture phase to keep results on the dashboard.
 button.addEventListener('click',async e=>{
  e.preventDefault();e.stopImmediatePropagation();
  const a=$('#rh41A')?.value.trim(),b=$('#rh41B')?.value.trim();
  if(!a||!b||a===b){quick.textContent='Select two different offensive players.';return}
  const params=new URLSearchParams({season:$('#rh50Season')?.value||$('#ssSeason')?.value||'2026',scoring:$('#rh50Scoring')?.value||$('#ssScoring')?.value||'ppr'});
  params.append('player',a);params.append('player',b);
  button.disabled=true;quick.textContent='Calculating intelligence ratings…';
  try{
   const r=await fetch('/api/intelligence?'+params,{credentials:'same-origin'}),d=await r.json();
   if(!r.ok)throw Error(d.error||'Intelligence service unavailable');
   const players=d.players||[];if(players.length!==2)throw Error('Two players were not returned. Select valid names from suggestions.');
   const blocks=players.map(p=>`<div class="rh50d2-quick-player"><div><strong>${esc(p.name)}</strong><small>${esc(p.position)} · ${esc(p.team)}</small></div><div class="rh50d2-quick-score">${num(p.weekly?.rating)}<small>/100</small></div><div class="rh50d2-quick-proj">${num(p.weekly?.projected_points,2)} <small>projected FP</small></div></div>`).join('');
   const c=d.start_sit||{},edge=c.projected_edge_a_minus_b;
   quick.innerHTML=`<div class="rh50d2-quick-results">${blocks}</div><div class="rh50d2-quick-verdict"><span>${c.preferred_start?'Model preference: '+esc(c.preferred_start):'No projected edge'}</span><b>${edge==null?'—':(Number(edge)>0?'+':'')+num(edge,2)} FP (first − second)</b></div><div class="rh50d2-quick-actions"><small>Research ratings, not calibrated win probabilities. Opponents are not set in dashboard Quick Start/Sit.</small><button type="button" id="rh50d2Full" class="rh43-btn">Full matchup analysis</button></div>`;
   $('#rh50d2Full')?.addEventListener('click',()=>{
    if($('#ssA'))$('#ssA').value=a;if($('#ssB'))$('#ssB').value=b;
    if($('#ssSeason'))$('#ssSeason').value=params.get('season');if($('#ssScoring'))$('#ssScoring').value=params.get('scoring');
    const nav=document.querySelector('[data-rh50-nav="start"]')||document.querySelector('.nav [data-view="start"]');
    if(nav)nav.click();else if(typeof window.go==='function')window.go('start');
    $('#ssCompare')?.click();
   });
  }catch(err){quick.textContent='Quick Intelligence unavailable: '+err.message}
  finally{button.disabled=false}
 },true);
 // The 5.0C panel was placed outside the Quick Result; prevent a second stale set of numbers.
 const duplicate=quick.nextElementSibling;
 if(duplicate?.classList.contains('rh50c-quick'))duplicate.hidden=true;
}
// Keep trade autocomplete above cards without clipping, and label the two sides clearly.
const trade=$('#trade');if(trade){
 const a=trade.querySelector('#rh43TradeA')?.closest('.rh43-trade-side');
 const b=trade.querySelector('#rh43TradeB')?.closest('.rh43-trade-side');
 if(a?.querySelector('h3'))a.querySelector('h3').textContent='You give';
 if(b?.querySelector('h3'))b.querySelector('h3').textContent='You receive';
 const panel=trade.querySelector('.rh50c-panel');
 if(panel)panel.classList.add('rh50d2-trade-intelligence');
}
const version=$('#home .version-chip');if(version)version.textContent='VERSION 5.0D.2';
})();
