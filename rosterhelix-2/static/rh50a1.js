/* RosterHelix 5.0A.1 — navigation repair and hierarchy refinement.
   Keeps all existing data endpoints, animations and analytics intact. */
(()=>{'use strict';
const $=s=>document.querySelector(s);
const goTo=(view)=>{if(typeof window.go==='function'){window.go(view)}else{document.querySelectorAll('.view').forEach(el=>el.classList.toggle('active',el.id===view));window.scrollTo({top:0,behavior:'instant'})}};
// The 4.2 Full analysis action used a legacy [data-view="start"] button.
// 5.0A replaced those buttons with [data-rh50-nav], breaking that navigation.
// Capture the action at document level so it also handles dynamically rendered results.
document.addEventListener('click',e=>{
 const action=e.target.closest('#rh42Full');if(!action)return;
 e.preventDefault();e.stopImmediatePropagation();
 const a=$('#rh41A')?.value.trim(),b=$('#rh41B')?.value.trim();
 if(!a||!b){const out=$('#rh41QuickResult');if(out)out.textContent='Choose two players first.';return}
 const pa=$('#ssA'),pb=$('#ssB');if(pa)pa.value=a;if(pb)pb.value=b;
 const yr=$('#rh50Season')?.value,sc=$('#rh50Scoring')?.value;
 if(yr&&$('#ssSeason'))$('#ssSeason').value=yr;
 if(sc&&$('#ssScoring'))$('#ssScoring').value=sc;
 goTo('start');
 // Existing comparison handler fetches the original analytics and projections.
 $('#ssCompare')?.click();
},true);
// Remove redundant headings without touching working tools or customization logic.
const shell=$('.rh41-shell');
if(shell){
 const banner=$('.rh50-dashboard-title');
 if(banner){const title=banner.querySelector('h2');if(title)title.textContent='Your workspace';
 const sub=banner.querySelector('p');if(sub)sub.textContent='Quick decisions and personalized research in one place.';
 // A second Customize button is already provided by the actual workspace editor.
 banner.querySelector('#rh50CustomizeShortcut')?.remove();}
 const head=shell.querySelector(':scope > .rh41-head');if(head){head.classList.add('rh501-tools-head');
 const title=head.querySelector('h2');if(title){title.innerHTML='Quick access';}
 const sub=head.querySelector('.rh41-sub');if(sub)sub.textContent='Jump directly to an analyzer';}
 const panel=$('.rh41-grid > .rh41-panel');if(panel)panel.classList.add('rh501-quick');
}
// Keep the swap action in the top page header, remove duplicate Start/Sit heading.
const start=$('#start'),intro=start?.querySelector('.rh50-page-intro'),old=start?.querySelector('.rh42-heading');
if(intro&&old){const swap=old.querySelector('#rh42Swap');if(swap){swap.classList.add('rh501-swap');intro.append(swap)}old.remove()}
// Put the model validation lab in an expandable advanced section so the weekly
// decision stays first; preserve its button, results and event listeners.
const lab=start?.querySelector('.rh44-model');
const candidate=lab||[...(start?.children||[])].find(el=>el.textContent?.includes('Model Validation Lab')&&el.querySelector('#rh44Run, #model44Run, [id*="Backtest"], [id*="backtest"]'));
if(candidate&&candidate.parentElement===start){const details=document.createElement('details');details.className='rh501-validation';
 const summary=document.createElement('summary');summary.textContent='Advanced · Model Validation Lab';candidate.before(details);details.append(summary,candidate)}
// Remove outdated release labels while keeping the actual backend unchanged.
const version=$('#home .version-chip');if(version)version.textContent='VERSION 5.0A.1';
const footer=document.querySelector('.main footer');if(footer)footer.textContent='RosterHelix 5.0A.1 · Public analytics · Transparent methodology · Not affiliated with the NFL';
const sidefoot=$('.sidefoot');if(sidefoot)sidefoot.textContent='ROSTERHELIX 5.0A.1 · INTELLIGENCE WORKSPACE';
// Keep a consistent version label even when the sidebar is collapsed.
})();
