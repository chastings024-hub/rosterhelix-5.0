/* RosterHelix 5.0C.2: offense-only autocomplete results.
   Applied before the legacy search handlers are registered. */
(()=>{'use strict';
const allowed=new Set(['QB','RB','WR','TE']);
const originalFetch=window.fetch.bind(window);
window.fetch=async function(input,init){
 const response=await originalFetch(input,init);
 try{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  if(url.origin!==location.origin||url.pathname!=='/api/search'||!response.ok)return response;
  const payload=await response.clone().json();
  if(!payload||!Array.isArray(payload.players))return response;
  const players=payload.players.filter(p=>allowed.has(String(p.pos||p.position||'').trim().toUpperCase()));
  const headers=new Headers(response.headers);
  headers.delete('content-length');headers.delete('content-encoding');
  headers.set('content-type','application/json; charset=utf-8');
  return new Response(JSON.stringify({...payload,players}),{status:response.status,statusText:response.statusText,headers});
 }catch(e){return response;}
};
})();
