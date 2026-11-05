/* 5.0E: compact Start/Sit and on-demand ablation diagnostics. */
(()=>{'use strict';
const start=document.getElementById('start');
if(start){
 const btn=document.createElement('button');btn.type='button';btn.className='rh50e-toggle';
 btn.textContent='Show detailed matchup and projection panels';btn.setAttribute('aria-expanded','false');
 const result=document.getElementById('ssResult');
 if(result)result.after(btn);
 btn.addEventListener('click',()=>{const expanded=start.classList.toggle('rh50e-expanded');btn.textContent=expanded?'Hide detailed matchup and projection panels':'Show detailed matchup and projection panels';btn.setAttribute('aria-expanded',String(expanded));});
}
const view=document.getElementById('accuracy');if(!view)return;
const lab=document.createElement('section');lab.className='rh50e-lab';lab.innerHTML=`<h3>Model Research Lab · Component Ablations</h3><p>Compare the production model against predefined changes to recent form, opportunity weighting, and matchup adjustments. Research only: live predictions remain unchanged.</p><div class="rh50e-controls"><label>Seasons <input id="rh50eYears" value="2023,2024,2025" aria-label="Research seasons"></label><label>Scoring <select id="rh50eScore"><option value="ppr">Full PPR</option><option value="half">Half PPR</option><option value="standard">Standard</option></select></label><label>Scan / season <select id="rh50eLimit"><option value="600">600</option><option value="1500" selected>1,500</option><option value="3000">3,000</option></select></label><button id="rh50eRun" type="button">Run research comparison</button></div><div class="rh50e-muted">Larger scans may take longer. These are exploratory comparisons, not independent proof of future accuracy.</div><div id="rh50eOutput" aria-live="polite"></div>`;
view.append(lab);
const out=lab.querySelector('#rh50eOutput'),run=lab.querySelector('#rh50eRun');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
run.addEventListener('click',async()=>{
 const years=lab.querySelector('#rh50eYears').value.trim();
 if(!/^\d{4}(,\d{4}){0,3}$/.test(years)){out.textContent='Enter 1–4 comma-separated seasons, such as 2023,2024,2025.';return;}
 const q=new URLSearchParams({seasons:years,scoring:lab.querySelector('#rh50eScore').value,limit:lab.querySelector('#rh50eLimit').value});
 run.disabled=true;out.textContent='Running walk-forward ablation comparisons…';
 try{
  const res=await fetch('/api/intelligence/research/ablation?'+q.toString());const d=await res.json();
  if(!res.ok||d.error)throw Error(d.error||'Unable to run comparison');
  const n=d.summary?.n||0;const recipes=d.ranked_recipes||[];
  const rows=recipes.map(x=>`<tr><td>${esc(x.recipe)}</td><td>${x.mae==null?'—':Number(x.mae).toFixed(3)}</td><td>${x.delta_vs_production==null?'—':Number(x.delta_vs_production).toFixed(3)}</td><td>${x.bias==null?'—':Number(x.bias).toFixed(3)}</td></tr>`).join('');
  const robustness=d.robustness||{};
  const robustnessRows=Object.entries(robustness.recipes||{}).map(([name,v])=>`<tr><td>${esc(name)}</td><td>${v.delta_mae?.toFixed(3)??'—'}</td><td>${v.bootstrap_95_interval?v.bootstrap_95_interval.map(n=>n.toFixed(3)).join(' to '):'Insufficient blocks'}</td><td>${v.improved_every_season?'Yes':'No'}</td></tr>`).join('');
  const robustnessHtml=`<h4>5.0E.2 · Robustness & uncertainty</h4><p>Paired week-block resampling (${robustness.week_blocks??0} week blocks). Positive delta favors the research recipe. These intervals do not prove future accuracy.</p><div class="rh50e-scroll"><table><thead><tr><th>Recipe</th><th>Δ MAE ↑</th><th>95% bootstrap range</th><th>Better in every season?</th></tr></thead><tbody>${robustnessRows}</tbody></table></div><p class="rh50e-muted">No automatic promotion: use a pre-registered held-out season and test a single selected recipe before considering production changes.</p>`;
  const positions=Object.entries(d.by_position||{}).map(([pos,x])=>`${esc(pos)}: ${x.n} games`).join(' · ');
  out.innerHTML=`<p><strong>${n.toLocaleString()} evaluated player-games</strong> · ${esc(positions)}</p><div class="rh50e-scroll"><table><thead><tr><th>Research recipe</th><th>MAE ↓</th><th>Improvement vs production ↑</th><th>Bias</th></tr></thead><tbody>${rows}</tbody></table></div>${robustnessHtml}<p class="rh50e-muted">A positive improvement means lower error than production on this sample. No automatic promotion. The historical evaluation excludes absences and does not yet include snaps, routes, injuries, or coverage schemes.</p>`;
 }catch(e){out.textContent='Research comparison failed: '+e.message}finally{run.disabled=false}
});
})();
