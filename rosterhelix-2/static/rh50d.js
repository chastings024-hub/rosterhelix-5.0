/* 5.0D: transparent backtest diagnostic, no unvalidated prediction swap */
(()=>{'use strict';
const $=s=>document.querySelector(s);
const el=$('#start');if(!el)return;
const host=el.querySelector('.rh501-validation')||el;
const wrap=document.createElement('section');wrap.className='rh50d-validation';
wrap.innerHTML='<div class="rh50d-head"><div><strong>5.0D · Model validation gate</strong><p>Walk-forward comparison against the prior-season-average baseline. This does not retrain or silently replace the production formula.</p></div><button type="button" id="rh50dValidate">Run diagnostic</button></div><div id="rh50dResults" role="status">Select the season and scoring in Start/Sit, then run the diagnostic.</div>';
host.append(wrap);
const btn=$('#rh50dValidate'),out=$('#rh50dResults');
btn.addEventListener('click',async()=>{
 btn.disabled=true;out.textContent='Evaluating prior-week-only predictions…';
 try{const q=new URLSearchParams({season:$('#ssSeason')?.value||$('#rh50Season')?.value||'2026',scoring:$('#ssScoring')?.value||$('#rh50Scoring')?.value||'ppr'});
 const r=await fetch('/api/intelligence/validation?'+q);const d=await r.json();if(!r.ok)throw Error(d.error||'Unable to validate');
 if(!d.evaluated){out.textContent=d.notice||'Not enough imported games to validate.';return}
 const o=d.overall;out.innerHTML='';const stats=document.createElement('div');stats.className='rh50d-stats';
 for(const [label,value] of [['Player-games',d.evaluated],['Current model MAE',o.model_mae],['Historical baseline MAE',o.season_average_mae],['MAE improvement',d.mae_improvement],['Pairwise accuracy',d.pairwise_rank_accuracy==null?'—':(100*d.pairwise_rank_accuracy).toFixed(1)+'%']]){
 const cell=document.createElement('div'),strong=document.createElement('strong'),small=document.createElement('small');strong.textContent=String(value??'—');small.textContent=label;cell.append(strong,small);stats.append(cell)}
 const p=document.createElement('p');p.textContent=d.release_gate?.summary||'Diagnostic only';out.append(stats,p);
 }catch(e){out.textContent='Diagnostic unavailable: '+e.message}finally{btn.disabled=false}
});
const version=$('#home .version-chip');if(version)version.textContent='VERSION 5.0D';
})();