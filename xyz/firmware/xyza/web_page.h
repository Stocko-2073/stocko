#pragma once
static const char webPage[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XYZ · Machine control</title>
<style>
:root{color-scheme:dark;font:16px system-ui;background:#101619;color:#edf4f2}*{box-sizing:border-box}body{max-width:920px;margin:auto;padding:24px}header{display:flex;align-items:center;justify-content:space-between;gap:20px}h1{font-size:28px}h2{font-size:19px;margin-top:0}.muted,small{color:#b0c0be}main{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:20px}section{background:#1b262b;border:1px solid #36474c;border-radius:14px;padding:22px}.wide{grid-column:1/-1}button,select{font:inherit;padding:12px 16px;border-radius:8px;border:1px solid #60716f;background:#30443f;color:white;cursor:pointer}button:disabled{opacity:.4;cursor:default}button:focus-visible,select:focus-visible{outline:3px solid #84f4cf}button.primary{background:#a3eccd;color:#112c22;font-weight:650}#stop{background:#b8343d;font-weight:750;font-size:19px;min-width:135px}button{touch-action:manipulation}button:hover:enabled{filter:brightness(1.15)}.actions{display:flex;gap:10px;flex-wrap:wrap}.axis{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:center;margin-top:16px}.axis strong{grid-column:1/-1;order:-1;text-align:left}.coords{display:flex;gap:30px;flex-wrap:wrap;font:26px ui-monospace,monospace}.coords small{font:14px system-ui;display:block}.notice{color:#ffd899;line-height:1.5}#message{min-height:24px;margin-top:18px}p{line-height:1.5}label{display:block;margin-bottom:10px}@media(max-width:640px){main{grid-template-columns:1fr}body{padding:14px}header{align-items:flex-start}.coords{font-size:21px}}
</style>
<header><div><small>STOCKO / XYZ</small><h1>Machine control</h1><span id="status" role="status">Connecting…</span></div><button id="stop">STOP</button></header>
<main>
<section class="wide"><h2>Position from home</h2><div class="coords" id="coords">—</div><p class="notice" id="referenceNote"></p><div class="actions"><button id="confirm" data-op="confirm">Machine has not moved since restart</button><button id="reference" data-op="reference">I am at the saved home</button></div></section>
<section><h2>Jog to position</h2><p class="muted">One click, one move. Cruise speed: 1,000 pulses/sec with acceleration.</p><label for="step">Jog distance</label><select id="step"><option value="10">10 pulses ≈ 0.1 mm</option><option value="100">100 pulses ≈ 1 mm</option><option value="500">500 pulses ≈ 5 mm</option><option value="1000" selected>1000 pulses ≈ 10 mm</option></select><div id="axes"></div><p class="muted">Directions describe movement of the board or drill. Distances are approximate.</p><button class="primary" id="arm" data-op="arm">Enable motors</button></section>
<section><h2>Saved positions</h2><p>Jog to your working origin, then save home. XYZ will read zero here.</p><div class="actions"><button id="home" data-op="home">Set home here</button><button id="go-home" data-op="go-home">Go home</button></div><hr style="border:0;border-top:1px solid #36474c;margin:24px 0"><p>Raise the drill and move the board to an accessible position, then save it.</p><div class="actions"><button id="replace" data-op="replace">Set replace board here</button><button id="go-replace" data-op="go-replace">Replace board</button></div><p id="saved" class="muted"></p></section>
<section class="wide"><h2>Before moving</h2><p class="notice">No limit switches: check travel and drill clearance. Saved moves raise Z to the higher of the current and target positions, move X then Y, and lower Z to the target. That height must clear the board and fixtures.</p><p class="muted">Home and replace board are stored on the controller. After a reboot, confirm the machine has not moved, or jog to your saved home and select “I am at the saved home.” After an interrupted move, re-reference at home. Stop disables all motors. The spindle is not moved by this page.</p></section>
</main><div id="message" role="status" aria-live="polite"></div>
<script>
const $=id=>document.getElementById(id);let state=null,pending=false,online=false;const client=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
const jogLabels={X:['← Board left','Board right →'],Y:['Board toward tower','Board away from tower'],Z:['↓ Drill down','↑ Drill up']};
for(const axis of ['X','Y','Z']){const row=document.createElement('div');row.className='axis';for(const sign of [-1,0,1]){const el=document.createElement(sign?'button':'strong');el.textContent=sign?jogLabels[axis][sign>0?1:0]:(axis==='Z'?'Drill · Z':'Board · '+axis);if(sign){el.className='jog';el.disabled=true;el.onclick=()=>act('jog',{axis,pulses:sign*Number($('step').value)});}row.append(el);}$('axes').append(row);}
function render(){const s=state,blocked=!online||pending||!s||s.busy||!s.commissioned;document.querySelectorAll('[data-op],.jog').forEach(b=>b.disabled=blocked);if(!s)return;
$('status').textContent=!online?'Disconnected — controls unavailable':s.busy?'Moving':s.armed?'Motors enabled':'Motors disabled — '+(s.disableReason||'Stopped');
$('coords').replaceChildren();['X','Y','Z'].forEach((a,i)=>{const el=document.createElement('div');el.textContent=a+' '+(s.known?s.position[i]:'—');const unit=document.createElement('small');unit.textContent='pulses';el.append(unit);$('coords').append(el);});
$('referenceNote').textContent=!s.commissioned?'Motor mapping changed. Restore the commissioned mapping before using web controls.':s.known?'Position referenced. Re-reference if the machine slips or is moved by hand.':s.homeSet?'Position needs confirmation. Jog to saved home, or confirm an unchanged clean restart.':'Jog to your working origin and select “Set home here.”';
$('confirm').hidden=s.known||!s.homeSet||!s.recoverable;$('reference').hidden=s.known||!s.homeSet;
$('arm').disabled=blocked||s.armed;document.querySelectorAll('.jog').forEach(b=>b.disabled=blocked||!s.webArmed);
$('replace').disabled=blocked||!s.known||!s.homeSet;
$('go-home').disabled=blocked||!s.known||!s.homeSet||!s.webArmed;
$('go-replace').disabled=blocked||!s.known||!s.replaceSet||!s.webArmed;
$('saved').textContent=s.replaceSet?'Replace board from home: X '+s.replace[0]+', Y '+s.replace[1]+', Z '+s.replace[2]+' pulses.':'Replace board position not saved.';
}
async function post(op,extra={}){const response=await fetch('/api/action',{method:'POST',headers:{'X-XYZ-Control':'1','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({op,client,...extra}),signal:AbortSignal.timeout(1200)});const text=await response.text();if(!response.ok)throw Error(text);return text;}
async function act(op,extra={}){if(pending&&op!=='stop')return;if(op==='home'&&state?.homeSet&&!confirm(state.known?'Move the saved home to this position?':'Set a new home? This clears the old replace board position. To keep it, use “I am at the saved home” instead.'))return;pending=true;render();try{$('message').textContent=await post(op,extra);}catch(e){$('message').textContent=e.message;}finally{pending=false;await refresh();}}
async function refresh(){try{state=JSON.parse(await post('poll'));online=true;}catch{online=false;}render();}
$('stop').onclick=()=>act('stop');document.querySelectorAll('[data-op]').forEach(b=>b.onclick=()=>act(b.dataset.op));
document.addEventListener('keydown',e=>{if(e.code==='Escape'){e.preventDefault();act('stop');}});
// One request renews the owning page's lease and returns status. Retry even
// after a failed request; observers never renew another page's lease.
async function poll(){if(!document.hidden&&!pending)await refresh();setTimeout(poll,300);}
document.addEventListener('visibilitychange',()=>{if(document.hidden&&state?.webArmed)post('hidden').catch(()=>{});});
render();poll();
</script></html>)HTML";
