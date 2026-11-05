/* First-name search improvements for Trade Lab, without changing stored player IDs. */
(function(){
 'use strict';
 const trade=document.getElementById('trade');
 if(!trade)return;
 for(const id of ['tradeA','tradeB']){
  const select=document.getElementById(id);
  if(!select||document.getElementById('rh60_'+id))continue;
  const input=document.createElement('input');
  input.id='rh60_'+id;input.className='field rh60-trade-filter';
  input.placeholder='Find player by first or last name';input.setAttribute('aria-label','Search '+id+' player');
  select.parentElement.insertBefore(input,select);
  input.addEventListener('input',()=>{
   const q=input.value.toLowerCase().trim();
   const options=[...select.options];
   options.forEach(option=>{option.hidden=!!q&&!option.textContent.toLowerCase().includes(q)});
   // Native select support for hiding options differs across browsers.
   // Select the first matching player, preserving original option values.
   const first=options.find(option=>!option.hidden);
   if(first)select.value=first.value;
  });
 }
})();
