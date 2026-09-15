#pragma once
static const char webPage[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XYZ · Stripboard cutter</title>
<style>
:root{color-scheme:dark;--bg:#0f1417;--card:#171f24;--raise:#212c32;--line:#2d3b41;--text:#e9f1ef;--muted:#9fb2ae;--accent:#8ee6c3;--ink:#0f2a20;--warn:#f3c65f;--danger:#e04b55;--ok:#62d6a4;font:16px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--text)}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;padding:0 20px 90px}
.bar{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:16px;max-width:1000px;margin:0 auto 20px;padding:12px 0;background:var(--bg);border-bottom:1px solid var(--line)}
.brand{font-weight:700;letter-spacing:.02em;line-height:1.2}.brand small{display:block;font-weight:400;color:var(--muted);font-size:12px}
.pill{display:inline-flex;align-items:center;gap:8px;min-width:0;padding:6px 12px;border-radius:999px;background:var(--raise);font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill::before{content:"";flex:none;width:9px;height:9px;border-radius:50%;background:var(--muted)}
.pill[data-tone=ok]::before{background:var(--ok);box-shadow:0 0 0 3px #62d6a433}.pill[data-tone=busy]::before{background:var(--warn);animation:blink 1s infinite}.pill[data-tone=bad]::before{background:var(--danger)}
@keyframes blink{50%{opacity:.25}}
#stop{flex:none;margin-left:auto;background:var(--danger);color:#fff;font-weight:800;font-size:18px;letter-spacing:.06em;padding:14px 26px;border:0;border-radius:12px;box-shadow:0 4px 0 #8f232b}
#stop:hover{background:#ea5a63}#stop:active{transform:translateY(3px);box-shadow:0 1px 0 #8f232b}
main{max-width:1000px;margin:auto;display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:20px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:0 0 14px}
button,input{font:inherit;color:var(--text);background:var(--raise);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
button{cursor:pointer;touch-action:manipulation}button:hover:enabled{border-color:#4b5f66;background:#2a3840}button:disabled{opacity:.35;cursor:not-allowed}
button:focus-visible,input:focus-visible,.seg label:focus-within{outline:3px solid var(--accent);outline-offset:2px}
.primary{background:var(--accent);color:var(--ink);border-color:transparent;font-weight:700}.primary:hover:enabled{background:#a6f0d2;border-color:transparent}
.dro{display:grid;grid-template-columns:3fr 2fr;gap:10px}
.dro div{background:var(--bg);border-radius:12px;padding:10px 14px;min-width:0}.dro span,.dro small{display:block;font-size:12px;color:var(--muted)}
.dro b{display:block;font:600 34px/1.1 ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums;margin:3px 0}
.dro small{font-size:13px;color:var(--text)}.dro small.off{color:var(--warn)}
.ref{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;font-size:14px;color:var(--muted)}
.badge{flex:none;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;background:var(--raise);color:var(--warn)}.badge[data-tone=ok]{color:var(--ok)}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.gate{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:22px;padding:12px 14px;border-radius:12px;background:var(--raise);font-size:14px}.gate span{flex:1 1 280px}
.move{display:grid;grid-template-columns:auto auto;gap:10px 24px;justify-content:center;align-items:end}
.seg{display:grid;gap:4px;padding:4px;background:var(--bg);border-radius:12px}.seg.xy{grid-template-columns:repeat(4,1fr)}.seg.z{grid-template-columns:1fr}
.seg label{position:relative;padding:7px 4px;border-radius:9px;text-align:center;font-weight:600;font-size:14px;cursor:pointer;white-space:nowrap}
.seg small{display:block;font-weight:400;font-size:11px;color:var(--muted)}.seg input{position:absolute;inset:0;margin:0;padding:0;opacity:0;cursor:pointer}
.seg label:has(:checked){background:var(--raise);box-shadow:inset 0 0 0 1px var(--accent)}
.pad{display:grid;grid-template-columns:repeat(3,84px);grid-auto-rows:84px;gap:6px}.zpad{display:grid;grid-template-columns:84px;grid-auto-rows:84px;gap:6px}
.hub{display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);text-align:center}
.hub b{font:600 22px/1.1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:0;text-transform:none;color:var(--text)}
.jog{display:flex;flex-direction:column;gap:3px;align-items:center;justify-content:center;padding:6px;font-size:12px;line-height:1.15;text-align:center;color:var(--muted)}
.jog i{font-style:normal;font-size:26px;line-height:1;color:var(--text)}.jog:disabled i{color:var(--muted)}.jog span{font-weight:600;color:var(--text)}.jog:disabled span{color:var(--muted)}
.goto{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:22px;padding-top:18px;border-top:1px solid var(--line)}
.goto input{width:7em;text-transform:uppercase;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.goto .hint{flex:1 1 200px;margin:0}
.row{display:flex;align-items:center;gap:10px;padding:14px 0;border-top:1px solid var(--line)}.row:first-of-type{border-top:0;padding-top:0}
.row div{flex:1;min-width:0}.row b{display:block}.row small,.hint,.muted{color:var(--muted);font-size:13px}.hint{margin:6px 0 0;min-height:1.2em}
details{margin-top:20px;padding:0 4px;color:var(--muted);font-size:14px}summary{cursor:pointer;color:var(--text);font-weight:600;padding:4px 0}details p{margin:10px 0}
.warn{color:var(--warn)}
#message{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:min(90vw,560px);padding:12px 18px;border-radius:12px;background:#243036;border:1px solid var(--line);box-shadow:0 8px 30px #0008;font-size:14px;opacity:0;transition:opacity .3s;pointer-events:none}
#message.show{opacity:1}#message.err{border-color:var(--danger);color:#ffd9dc}
@media(max-width:720px){main{grid-template-columns:1fr}body{padding:0 12px 90px}.card{padding:16px}.bar{gap:10px}.brand small{display:none}.pill{font-size:13px}#stop{padding:12px 18px}.dro{grid-template-columns:1fr 1fr}.dro b{font-size:26px}.move{gap:8px 12px}.pad{grid-template-columns:repeat(3,72px);grid-auto-rows:72px}.zpad{grid-template-columns:72px;grid-auto-rows:72px}.seg label{font-size:13px;padding:6px 2px}}
</style>
<header class="bar"><div class="brand">XYZ<small>Stripboard cutter</small></div><span id="status" class="pill" role="status">Connecting…</span><button id="stop" title="Stop all motion and turn the motors off (Esc)">STOP</button></header>
<main>
<section class="card">
<h2>Drill position</h2>
<div class="dro"><div><span>Hole under the drill</span><b id="here">—</b><small id="hereNote">Position unknown</small></div><div><span>Drill height</span><b id="height">—</b><small id="heightNote">from A1 height</small></div></div>
<div class="ref"><span id="referenceNote"></span><span class="badge" id="refBadge">Position unknown</span></div>
<div class="actions" id="refActions"><button id="confirm" data-op="confirm">Nothing has moved since power-off</button><button id="reference" data-op="reference">The drill is above A1 now</button></div>
<div class="gate" id="gate"><span id="gateText"></span><button class="primary" id="arm" data-op="arm">Turn on motors</button></div>
<h2 style="margin-top:26px">Move the drill</h2>
<div class="move">
<div class="seg xy" role="radiogroup" aria-label="Move across the board by"><label><input type="radio" name="xy" value="254" checked>1 hole<small>2.54 mm</small></label><label><input type="radio" name="xy" value="762">3 holes<small>7.62 mm</small></label><label><input type="radio" name="xy" value="100">1 mm<small>fine</small></label><label><input type="radio" name="xy" value="10">0.1 mm<small>fine</small></label></div>
<div class="seg z" role="radiogroup" aria-label="Raise or lower by"><label><input type="radio" name="z" value="500">5 mm</label><label><input type="radio" name="z" value="100" checked>1 mm</label><label><input type="radio" name="z" value="10">0.1 mm</label></div>
<div class="pad" id="xy"></div><div class="zpad" id="z"></div>
</div>
<p class="muted" style="text-align:center;margin:14px 0 0">Arrows say where the drill goes over the board: columns count to the left, rows count forward from A. One press, one move.</p>
<div class="goto"><label for="hole"><b>Go to hole</b></label><input id="hole" placeholder="D12" autocomplete="off" spellcheck="false" maxlength="4"><button id="go" class="primary">Go</button><p class="hint" id="goHint">Straight-line travel at the current drill height. Raise the drill first if it is in a cut.</p></div>
</section>
<aside>
<section class="card"><h2>Board</h2>
<div class="row"><div><b>A1</b><small id="a1Info"></small></div><button id="go-home" data-op="go-home">Go to A1</button><button id="home" data-op="home" title="Save the drill's current position as hole A1">Set A1 here</button></div>
<div class="row"><div><b>Board swap</b><small id="swapInfo"></small></div><button id="go-replace" data-op="go-replace">Swap board</button><button id="replace" data-op="replace" title="Save the drill's current position as the board swap position">Set here</button></div>
<p class="hint" id="savedHint"></p>
</section>
<details><summary><span class="warn">No limit switches.</span> Check travel and drill clearance before every move.</summary>
<p>Go to A1 and Swap board raise the drill to the higher of the two heights, cross the board in a straight line, then lower it. Go to hole crosses the same way at the current drill height, only within A1 to Z34. Crossing moves both axes together at four times the arrow speed; the arrows also keep the current height. The spindle is never run from this page.</p>
<p>Positions count commanded steps, not measured movement, at a provisional 100 steps per millimetre. A1 and the swap position are stored on the controller. After a reboot, confirm that nothing moved, or put the drill back above A1 and confirm it there. After an interrupted move, confirm at A1 again.</p>
<p>STOP or Escape cancels motion and turns all motors off. Hiding this page, losing Wi-Fi, or a stalled connection also turns them off. This is a software stop, not an emergency-stop circuit.</p></details>
</aside>
</main><div id="message" role="status" aria-live="polite"></div>
<script>
const $=id=>document.getElementById(id);const PPM=100,PITCH=254,COLS=34,ROWS=26; // Boards run A1 to Z34.
let state=null,pending=false,online=false,xyStep=PITCH,zStep=100,hideTimer;
const client=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
const rowName=i=>(i>=26?rowName(Math.floor(i/26)-1):'')+String.fromCharCode(65+i%26);
const holeName=(col,row)=>col>=1&&col<=COLS&&row>=0&&row<ROWS?rowName(row)+col:null;
const mm=p=>(p/PPM).toFixed(p%PPM?p%10?2:1:0)+' mm';
const stepText=p=>p%PITCH?mm(p):p/PITCH+(p===PITCH?' hole':' holes');
// Raw steps from A1 to the board grid: columns run along +X, rows along -Y.
function grid(p){const qx=Math.round(p[0]/PITCH),qy=Math.round(-p[1]/PITCH),rx=p[0]-qx*PITCH,ry=-p[1]-qy*PITCH;return{col:qx+1,row:qy,name:holeName(qx+1,qy),rx,ry,on:!rx&&!ry};}
function place(g){if(!g.name)return'Off the board (A1 to Z34)';if(g.on)return'Column '+g.col+' · Row '+rowName(g.row)+' · on the grid';const parts=[];if(g.rx)parts.push(mm(Math.abs(g.rx))+(g.rx>0?' left':' right'));if(g.ry)parts.push(mm(Math.abs(g.ry))+(g.ry>0?' forward':' back'));return parts.join(', ')+' of '+g.name;}
function parseHole(t){const m=/^\s*([A-Za-z]{1,2})\s*(\d{1,3})\s*$/.exec(t||'');if(!m)return null;let row=0;for(const ch of m[1].toUpperCase())row=row*26+ch.charCodeAt(0)-64;const col=+m[2];return holeName(col,row-1)?{col,row:row-1}:null;}
const arrows=[];
function jog(axis,sign,glyph,dir){const b=document.createElement('button');b.className='jog';b.disabled=true;const i=document.createElement('i');i.textContent=glyph;const t=document.createElement('span');b.append(i);b.append(t);b.onclick=()=>act('jog',{axis,pulses:sign*(axis==='Z'?zStep:xyStep)});arrows.push({b,t,axis,sign,dir});return b;}
function hub(title,sub){const d=document.createElement('div');d.className='hub';const b=document.createElement('b');b.id=title;b.textContent='—';const s=document.createElement('span');s.textContent=sub;d.append(b);d.append(s);return d;}
const xy={1:['Y',1,'↑','Back'],3:['X',1,'←','Left'],5:['X',-1,'→','Right'],7:['Y',-1,'↓','Forward']};
for(let i=0;i<9;i++)$('xy').append(i===4?hub('hub','drill'):xy[i]?jog(...xy[i]):document.createElement('div'));
$('z').append(jog('Z',1,'▲','Up'));$('z').append(hub('zhub','height'));$('z').append(jog('Z',-1,'▼','Down'));
document.addEventListener('change',e=>{if(e.target.name==='xy')xyStep=+e.target.value;if(e.target.name==='z')zStep=+e.target.value;render();});
function render(){const s=state,blocked=!online||pending||!s||s.busy||!s.commissioned;document.querySelectorAll('[data-op],.jog').forEach(b=>b.disabled=blocked);$('go').disabled=true;
const st=$('status');if(!online){st.textContent='Disconnected';st.dataset.tone='bad';}if(!s)return;
if(online){st.textContent=s.busy?'Moving':s.armed?'Motors on':'Motors off · '+(s.disableReason||'Stopped');st.dataset.tone=s.busy?'busy':s.armed?'ok':'off';}
const g=s.known?grid(s.position):null,z=s.position[2];
$('here').textContent=g?g.name||'Off board':'—';$('hereNote').textContent=g?place(g):'Position unknown';$('hereNote').className=g&&g.name&&!g.on?'off':'';
$('height').textContent=s.known?(z<0?'−':'+')+mm(Math.abs(z)):'—';$('heightNote').textContent=s.known?(z<0?'below':'above')+' the A1 height':'Position unknown';
$('hub').textContent=g?(g.on?'':'≈')+(g.name||'—'):'—';$('zhub').textContent=s.known?(z<0?'−':'+')+(Math.abs(z)/PPM).toFixed(1):'—';
const whole=!(xyStep%PITCH),n=xyStep/PITCH;
arrows.forEach(a=>{let t=a.dir+' '+stepText(a.axis==='Z'?zStep:xyStep);if(a.axis!=='Z'&&g&&g.on&&whole){const col=g.col+(a.axis==='X'?a.sign*n:0),row=g.row-(a.axis==='Y'?a.sign*n:0);t=holeName(col,row)||'Off board';}a.t.textContent=t;a.b.title=a.dir+' '+stepText(a.axis==='Z'?zStep:xyStep)+(t.includes(' ')?'':' to '+t);});
$('refBadge').textContent=!s.homeSet?'A1 not set':s.known?'Position known':'Position unknown';$('refBadge').dataset.tone=s.known?'ok':'warn';
$('referenceNote').textContent=!s.commissioned?'Motor mapping changed. Restore the commissioned mapping before using this page.':s.known?'If the machine slips or is moved by hand, put the drill back above A1 and set A1 again.':s.homeSet?'Say where the drill is before moving by holes.':'Put the drill above hole A1, the top-right hole at the corner stops, then set A1.';
$('confirm').hidden=s.known||!s.homeSet||!s.recoverable;$('reference').hidden=s.known||!s.homeSet;$('refActions').hidden=$('confirm').hidden&&$('reference').hidden;
const why=!online||!s.commissioned||s.webArmed?'':s.armed?'Another page or the USB console controls the motors. Press STOP to release them, then turn them on here.':'Motors are off. Turn them on to move the drill.';
$('gate').hidden=!why;$('gateText').textContent=why;$('arm').hidden=s.armed;$('arm').disabled=blocked||s.armed;
document.querySelectorAll('.jog').forEach(b=>b.disabled=blocked||!s.webArmed);
const travel=blocked||!s.known||!s.homeSet||!s.webArmed;
$('go').disabled=travel;$('go-home').disabled=travel;$('go-replace').disabled=travel||!s.replaceSet;$('replace').disabled=blocked||!s.known||!s.homeSet;
$('a1Info').textContent=s.homeSet?'Top-right hole, at the corner stops. Position reads A1 here.':'Not set. Put the drill above hole A1, then set it.';
const r=s.replaceSet?grid(s.replace):null,rz=s.replace[2];
$('swapInfo').textContent=r?'Drill parks '+(r.on&&r.name?'at '+r.name:mm(s.replace[0])+' left, '+mm(-s.replace[1])+' forward of A1')+', '+mm(Math.abs(rz))+(rz<0?' below':' above')+' A1 height.':'Not set. Raise the drill and move the board clear of it, then set here.';
$('savedHint').textContent=!s.homeSet?'':!s.known?'Confirm the position before saving or travelling.':!s.webArmed?'Turn on the motors to travel.':'Travel raises the drill to the higher of the two heights, crosses the board, then lowers it.';
}
function say(text,error){const m=$('message');m.textContent=text;m.className='show'+(error?' err':'');clearTimeout(hideTimer);if(!error)hideTimer=setTimeout(()=>{m.className='';},3500);}
async function post(op,extra={}){const response=await fetch('/api/action',{method:'POST',headers:{'X-XYZ-Control':'1','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({op,client,...extra}),signal:AbortSignal.timeout(1200)});const text=await response.text();if(!response.ok)throw Error(text);return text;}
async function act(op,extra={}){if(pending&&op!=='stop')return;if(op==='home'&&state?.homeSet&&!confirm(state.known?'Move A1 to the drill’s current position?':'Set a new A1 here? This clears the saved board swap position. If the drill is already above the old A1, use “The drill is above A1 now” instead.'))return;pending=true;render();try{say(await post(op,extra));}catch(e){say(e.message,true);}finally{pending=false;await refresh();}}
async function refresh(){try{state=JSON.parse(await post('poll'));online=true;}catch{online=false;}render();}
function goHole(){const h=parseHole($('hole').value);if(!h){say('Enter a hole from A1 to Z34: row letter, then column number.',true);return;}return act('goto',{x:(h.col-1)*PITCH,y:-h.row*PITCH});}
$('go').onclick=goHole;$('hole').onkeydown=e=>{if(e.key==='Enter'&&!$('go').disabled)goHole();};
$('hole').oninput=()=>{const h=parseHole($('hole').value);$('goHint').textContent=h?'Go to column '+h.col+', row '+rowName(h.row)+' in a straight line at the current drill height.':'Straight-line travel at the current drill height. Raise the drill first if it is in a cut.';};
$('stop').onclick=()=>act('stop');document.querySelectorAll('[data-op]').forEach(b=>b.onclick=()=>act(b.dataset.op));
document.addEventListener('keydown',e=>{if(e.code==='Escape'){e.preventDefault();act('stop');}});
// One request renews the owning page's lease and returns status. Retry even
// after a failed request; observers never renew another page's lease.
async function poll(){if(!document.hidden&&!pending)await refresh();setTimeout(poll,300);}
document.addEventListener('visibilitychange',()=>{if(document.hidden&&state?.webArmed)post('hidden').catch(()=>{});});
render();poll();
</script></html>)HTML";
