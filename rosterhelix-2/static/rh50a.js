/* RosterHelix 5.0A — Navigation and workspace information architecture.
   Preserves original view IDs, event handlers, backend endpoints and RH atom. */
(()=>{'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const menu=[['home','Dashboard','⌂'],['start','Start / Sit','⚡'],['trade','Trade Analyzer','⇄'],['research','Research','◈'],['leagues','My Leagues','▤'],['settings','Settings & Data','⚙']];
const map={home:'home',start:'start',trade:'trade',players:'research',defense:'research',leagues:'leagues',account:'settings',accuracy:'settings'};
const storage={get(k,f){try{return JSON.parse(localStorage.getItem(k))??f}catch{return f}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const nav=$('.sidebar .nav');if(!nav)return;
const sidebar=$('.sidebar');sidebar.classList.add('rh50-sidebar');
nav.setAttribute('aria-label','Primary navigation');
nav.innerHTML=menu.map(([id,label,icon])=>`<button type="button" data-rh50-nav="${id}" aria-label="${label}"><span class="rh50-nav-icon" aria-hidden="true">${icon}</span><span class="rh50-nav-label">${label}</span></button>`).join('');
const foot=$('.sidefoot');if(foot)foot.textContent='ROSTERHELIX 5.0A · INTELLIGENCE WORKSPACE';
const current=()=>$$('main > .view.active, main .view.active').find(v=>map[v.id])?.id||'home';
function navigate(id){
 const target=id==='research'?'players':id==='settings'?'account':id;
 if(typeof window.go==='function')window.go(target);
 else {$$('.view').forEach(v=>v.classList.toggle('active',v.id===target));window.scrollTo(0,0)}
 sync();
}
nav.querySelectorAll('[data-rh50-nav]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.rh50Nav)));
const mobile=document.createElement('button');mobile.id='rh50MenuToggle';mobile.type='button';mobile.className='rh50-menu-toggle';mobile.setAttribute('aria-label','Open navigation');mobile.setAttribute('aria-expanded','false');mobile.textContent='☰';
const backdrop=document.createElement('button');backdrop.className='rh50-backdrop';backdrop.type='button';backdrop.setAttribute('aria-label','Close navigation');document.body.append(backdrop);
const top=$('.main .top');if(top){top.prepend(mobile);const brand=document.createElement('strong');brand.className='rh50-mobile-brand';brand.textContent='ROSTERHELIX';top.insertBefore(brand,mobile.nextSibling)}
function toggleMenu(open){document.body.classList.toggle('rh50-menu-open',open);mobile.setAttribute('aria-expanded',String(open));mobile.setAttribute('aria-label',open?'Close navigation':'Open navigation')}
mobile.onclick=()=>toggleMenu(!document.body.classList.contains('rh50-menu-open'));backdrop.onclick=()=>toggleMenu(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape')toggleMenu(false)});
function tabs(id,items){
 const host=$('#'+id);if(!host)return;
 const bar=document.createElement('div');bar.className='rh50-subnav';bar.setAttribute('role','navigation');bar.setAttribute('aria-label',id==='players'?'Research sections':'Settings sections');
 items.forEach(([target,label])=>{const b=document.createElement('button');b.type='button';b.dataset.rh50Target=target;b.textContent=label;b.onclick=()=>{if(typeof window.go==='function')window.go(target);else{$$('.view').forEach(v=>v.classList.toggle('active',v.id===target))}sync()};bar.append(b)});
 host.insertBefore(bar,host.firstChild);
}
tabs('players',[['players','Player Explorer'],['defense','Defense Explorer']]);
tabs('defense',[['players','Player Explorer'],['defense','Defense Explorer']]);
tabs('account',[['account','Account & Imports'],['accuracy','Projection Accuracy']]);
tabs('accuracy',[['account','Account & Imports'],['accuracy','Projection Accuracy']]);
// Model validation stays in the Start/Sit workspace, close to its predictions.
const start=$('#start'),trade=$('#trade'),players=$('#players'),defense=$('#defense');
function pageIntro(section,eyebrow,heading,subtitle){if(!section)return;const bar=document.createElement('div');bar.className='rh50-page-intro';bar.innerHTML=`<div><span class="rh50-kicker">${eyebrow}</span><h1>${heading}</h1><p>${subtitle}</p></div>`;section.insertBefore(bar,section.firstChild);section.classList.add('rh50-polished');}
pageIntro(start,'WEEKLY LINEUP INTELLIGENCE','Start / Sit','One matchup decision. All the supporting evidence in one workspace.');
pageIntro(trade,'REST-OF-SEASON RESEARCH','Trade Analyzer','Build a trade, inspect the players, and evaluate the evidence.');
pageIntro(players,'PLAYER RESEARCH','Research Center','Search player histories, trends, and opportunities.');
pageIntro(defense,'DEFENSIVE RESEARCH','Research Center','Compare historical points allowed and defensive matchup tendencies.');
pageIntro($('#leagues'),'PERSONALIZED FANTASY','My Leagues','Keep league scoring and roster context in one place.');
pageIntro($('#account'),'ACCOUNT AND PLATFORM','Settings & Data','Manage your account, data imports, and platform status.');
pageIntro($('#accuracy'),'MODEL TRANSPARENCY','Settings & Data','Inspect prediction accuracy and historical results.');
// Do not remove legacy elements or rewrite the underlying analytic tools.
// The 4.3 customize panel remains operational, with clearer framing.
const shell=$('.rh41-shell');if(shell){
 const banner=document.createElement('div');banner.className='rh50-dashboard-title';banner.innerHTML='<div><span class="rh50-kicker">YOUR PERSONAL ANALYTICS HUB</span><h2>Decision Center</h2><p>Start with a quick comparison, or personalize the tools below.</p></div><button type="button" id="rh50CustomizeShortcut" class="rh50-quiet-button">⚙ Edit workspace</button>';
 shell.prepend(banner);
 $('#rh50CustomizeShortcut').onclick=()=>{const edit=$('#rh43Customize');if(edit){edit.click();$('#rh43Editor')?.scrollIntoView({behavior:'smooth',block:'nearest'})}};
}
const hero=$('#home .hero');if(hero){hero.classList.add('rh50-hero');hero.setAttribute('aria-label','RosterHelix animated brand introduction');const kicker=$('#home .home-kicker');if(shell){if(kicker)$('#home').insertBefore(kicker,shell);$('#home').insertBefore(hero,shell)}}
// Global context: selectors are synced only where the legacy implementation supports them.
// Existing onchange events still run; avoid rewriting data requests or forcing automatic imports.
const header=$('.main .top');if(header){
 const context=document.createElement('div');context.className='rh50-context';context.innerHTML='<label>Season <select id="rh50Season" aria-label="Default NFL season"><option>2026</option><option>2025</option><option>2024</option><option>2023</option></select></label><label>Scoring <select id="rh50Scoring" aria-label="Default scoring"><option value="ppr">Full PPR</option><option value="half">Half PPR</option><option value="standard">Standard</option></select></label>';
 header.insertBefore(context,$('#authBadge'));
 const saved=storage.get('rh50_context',{season:'2026',scoring:'ppr'});
 $('#rh50Season').value=saved.season||'2026';$('#rh50Scoring').value=saved.scoring||'ppr';
 function apply(){
  const yr=$('#rh50Season').value,sc=$('#rh50Scoring').value;
  storage.set('rh50_context',{season:yr,scoring:sc});
  ['ssSeason','defSeason','accSeason','rh43TradeSeason'].forEach(id=>{const el=$('#'+id);if(el)el.value=yr});
  ['ssScoring','defScoring','accScoring','rh43TradeScoring','leagueScoring'].forEach(id=>{const el=$('#'+id);if(el)el.value=sc});
  const ex=$('#season');if(ex)ex.value=yr;
  // Keep existing 4.x scoring synchronization and data refresh behavior.
  const original=$('#players .scoring');if(original){original.value=sc;original.dispatchEvent(new Event('change',{bubbles:true}))}
 }
 $('#rh50Season').onchange=apply;$('#rh50Scoring').onchange=apply;
 // Restore only the UI selections; don't silently run searches or change saved league data.
 ['ssSeason','defSeason','accSeason','rh43TradeSeason'].forEach(id=>{const el=$('#'+id);if(el)el.value=saved.season||'2026'});
 ['ssScoring','defScoring','accScoring','rh43TradeScoring'].forEach(id=>{const el=$('#'+id);if(el)el.value=saved.scoring||'ppr'});
}
function sync(){
 const view=current(),group=map[view]||'home';
 nav.querySelectorAll('[data-rh50-nav]').forEach(b=>{const active=b.dataset.rh50Nav===group;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
 $$('.rh50-subnav [data-rh50-target]').forEach(b=>{const active=b.dataset.rh50Target===view;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
 toggleMenu(false);
}
// Observe class mutations from the original go() function and 4.x shortcuts.
const main=$('.main');if(main){let queued=false;new MutationObserver(mutations=>{if(!mutations.some(m=>m.type==='attributes'&&m.attributeName==='class'&&m.target.classList.contains('view')))return;if(!queued){queued=true;requestAnimationFrame(()=>{queued=false;sync()})}}).observe(main,{attributes:true,attributeFilter:['class'],subtree:true})}
sync();
})();
