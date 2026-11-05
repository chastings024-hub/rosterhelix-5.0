/* RosterHelix 5.0C: verified 5.0B endpoint integration. No new scores invented. */
(()=>{'use strict';
const $=s=>document.querySelector(s);
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(x,d=1)=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(d):'—';
const season=()=>$('#rh50Season')?.value||$('#ssSeason')?.value||'2026';
const scoring=()=>$('#rh50Scoring')?.value||$('#ssScoring')?.value||'ppr';
function getNames(ids){return ids.map(id=>$(id)?.value.trim()||'').filter(Boolean)}
function params(names,year,score,opps=[]){const q=new URLSearchParams({season:year,scoring:score});names.forEach(n=>q.append('player',n));if(opps.length===names.length&&opps.every(Boolean))opps.forEach(o=>q.append('opponent',o));return q}
async function intelligence(names,year,score,opps=[]){
 const r=await fetch('/api/intelligence?'+params(names,year,score,opps),{credentials:'same-origin'});
 const d=await r.json();if(!r.ok||d.error)throw Error(d.error||'Intelligence API unavailable');return d;
}
function rating(p){return p.weekly?.rating==null?'—':number(p.weekly.rating)}
function card(p,focus='weekly'){
 const w=p.weekly||{},t=p.trade||{},v=focus==='trade'?t.rating:w.rating;
 const sub=focus==='trade'?(t.rating==null?'Not available — remaining schedule unverified':'Provisional rest-of-season rating'):'Weekly within-position rating';
 return `<article class="rh50c-player"><div class="rh50c-name"><strong>${escapeHTML(p.name)}</strong><span>${escapeHTML(p.position)} · ${escapeHTML(p.team)}</span></div>
 <div class="rh50c-score">${v==null?'—':number(v)}<small>/ 100</small></div><p class="rh50c-label">${sub}</p>
 <div class="rh50c-metrics"><div><b>${number(w.projected_points,2)}</b><small>Projected FP</small></div><div><b>${w.opponent?escapeHTML(w.opponent):'Not set'}</b><small>Opponent</small></div></div>
 <p class="rh50c-note">Recent ${number(p.explanation?.recent_ppg)} FP · Season ${number(p.explanation?.season_ppg)} FP · ${w.sample_games??'—'} games sampled</p></article>`;
}
function shell(title,subtitle){const el=document.createElement('section');el.className='rh50c-panel';el.innerHTML=`<div class="rh50c-heading"><div><span class="rh50c-kicker">ROSTERHELIX 5.0C · INTELLIGENCE</span><h3>${title}</h3><p>${subtitle}</p></div><span class="rh50c-experimental">Research preview</span></div><div class="rh50c-content" aria-live="polite">Enter players to see ratings.</div>`;return el}
function fill(el,d,mode='weekly'){
 const players=d.players||[],comparison=d.start_sit;
 const note='Ratings are relative within-position indices, not win probabilities. Historical floor/ceiling are not calibrated intervals.';
 const verdict=mode==='weekly'&&comparison&&players.length===2?`<div class="rh50c-verdict"><strong>${comparison.preferred_start?'Model preference: '+escapeHTML(comparison.preferred_start):'No projected edge'}</strong><span>Projected edge (first minus second): ${number(comparison.projected_edge_a_minus_b,2)} FP</span></div>`:'';
 el.querySelector('.rh50c-content').innerHTML=`<div class="rh50c-cards">${players.map(p=>card(p,mode)).join('')}</div>${verdict}<p class="rh50c-caution">${note} ${mode==='trade'?'Trade ratings are not additive, and this is not a roster-adjusted trade fairness verdict.':''}</p>`;
}
function error(el,e){el.querySelector('.rh50c-content').textContent='Unable to load intelligence ratings: '+e.message}
async function update(el,names,year,score,opps=[],mode='weekly'){
 if(!names.length){el.querySelector('.rh50c-content').textContent='Select players first.';return}
 el.querySelector('.rh50c-content').textContent='Calculating ratings…';
 try{const d=await intelligence(names,year,score,opps);fill(el,d,mode)}catch(e){error(el,e)}
}
// Main Start/Sit: use opponent selectors, so rating follows selected matchups.
const start=$('#start'),ss=$('#ssCompare');
if(start&&ss){
 const panel=shell('Weekly intelligence ratings','Matchup-adjusted when a valid opponent is selected.');
 const tabs=start.querySelector('.rh42-tabs'),target=tabs||start.querySelector('.rh42-start');
 if(target)target.before(panel);else start.append(panel);
 ss.addEventListener('click',()=>{
  const names=getNames(['#ssA','#ssB']);
  const opps=['#ssOppA','#ssOppB'].map(x=>$(x)?.value||'');
  update(panel,names,$('#ssSeason')?.value||season(),$('#ssScoring')?.value||scoring(),opps,'weekly');
 });
}
// Quick dashboard: show ratings only after user presses Analyze; keep original results and Full Analysis action.
const quick=$('#rh41QuickResult'),quickBtn=$('#rh41Compare');
if(quick){
 const panel=shell('Quick intelligence ratings','2026 weekly comparison from the research engine.');
 quick.after(panel);panel.classList.add('rh50c-quick');
 const host=$('#home');
 host?.addEventListener('click',e=>{
  if(!e.target.closest('button'))return;
  const b=e.target.closest('button');
  if(b.id==='rh42Full')return;
  if(b===quickBtn||b.textContent.trim()==='Analyze'&&b.closest('.rh41-panel')){
   const names=getNames(['#rh41A','#rh41B']);if(names.length===2)update(panel,names,season(),scoring());
  }
 });
}
// Trade Analyzer: show player-level ratings without summing percentile scores.
const trade=$('#trade'),tradeBtn=$('#rh43TradeRun');
if(trade&&tradeBtn){
 const result=$('#rh43TradeResult'),panel=shell('Player value intelligence','Individual ratings, projected points and schedule availability.');
 result?.after(panel);
 tradeBtn.addEventListener('click',()=>{
  const a=[...document.querySelectorAll('#rh43TradeA .rh43-player-entry input')].map(x=>x.value.trim()).filter(Boolean);
  const b=[...document.querySelectorAll('#rh43TradeB .rh43-player-entry input')].map(x=>x.value.trim()).filter(Boolean);
  const names=[...a,...b];if(!a.length||!b.length){panel.querySelector('.rh50c-content').textContent='Select players on both sides.';return}
  update(panel,names,$('#rh43TradeSeason')?.value||season(),$('#rh43TradeScoring')?.value||scoring(),[],'trade');
 });
}
// Visible version is for frontend; backend retains its independent model version.
const chip=$('#home .version-chip');if(chip)chip.textContent='VERSION 5.0C';
const foot=$('.main footer');if(foot)foot.textContent='RosterHelix 5.0C · Research ratings · Not affiliated with the NFL';
const side=$('.sidefoot');if(side)side.textContent='ROSTERHELIX 5.0C · INTELLIGENCE WORKSPACE';
})();
