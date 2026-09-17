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
.link{color:var(--muted);font-size:12px;white-space:nowrap}.link.slow{color:var(--warn)}
.pill::before{content:"";flex:none;width:9px;height:9px;border-radius:50%;background:var(--muted)}
.pill[data-tone=ok]::before{background:var(--ok);box-shadow:0 0 0 3px #62d6a433}.pill[data-tone=busy]::before{background:var(--warn);animation:blink 1s infinite}.pill[data-tone=bad]::before{background:var(--danger)}
@keyframes blink{50%{opacity:.25}}
#stop{flex:none;margin-left:auto;background:var(--danger);color:#fff;font-weight:800;font-size:18px;letter-spacing:.06em;padding:14px 26px;border:0;border-radius:12px;box-shadow:0 4px 0 #8f232b}
#stop:hover{background:#ea5a63}#stop:active{transform:translateY(3px);box-shadow:0 1px 0 #8f232b}
main{max-width:1000px;margin:auto;display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:20px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:0 0 14px}
button,input,textarea{font:inherit;color:var(--text);background:var(--raise);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
button{cursor:pointer;touch-action:manipulation}button:hover:enabled{border-color:#4b5f66;background:#2a3840}button:disabled{opacity:.35;cursor:not-allowed}
button:focus-visible,input:focus-visible,textarea:focus-visible,.seg label:focus-within{outline:3px solid var(--accent);outline-offset:2px}
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
#cutList{display:block;width:100%;min-height:7em;resize:vertical;margin:8px 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.cut-controls{margin-top:22px;padding-top:18px;border-top:1px solid var(--line)}
.cut-fields{display:grid;grid-template-columns:minmax(0,1fr) 7em;gap:10px 16px;align-items:center}.cut-fields input{width:100%;min-width:0}
.row{display:flex;align-items:center;gap:10px;padding:14px 0;border-top:1px solid var(--line)}.row:first-of-type{border-top:0;padding-top:0}
.row div{flex:1;min-width:0}.row b{display:block}.row small,.hint,.muted{color:var(--muted);font-size:13px}.hint{margin:6px 0 0;min-height:1.2em}
details{margin-top:20px;padding:0 4px;color:var(--muted);font-size:14px}summary{cursor:pointer;color:var(--text);font-weight:600;padding:4px 0}details p{margin:10px 0}
.warn{color:var(--warn)}
.mesh-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:12px}.mesh-grid button[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
#message{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:min(90vw,560px);padding:12px 18px;border-radius:12px;background:#243036;border:1px solid var(--line);box-shadow:0 8px 30px #0008;font-size:14px;opacity:0;transition:opacity .3s;pointer-events:none}
#message.show{opacity:1}#message.err{border-color:var(--danger);color:#ffd9dc}
@media(max-width:720px){.link{display:none}main{grid-template-columns:1fr}body{padding:0 12px 90px}.card{padding:16px}.bar{gap:10px}.brand small{display:none}.pill{font-size:13px}#stop{padding:12px 18px}.dro{grid-template-columns:1fr 1fr}.dro b{font-size:26px}.move{gap:8px 12px}.pad{grid-template-columns:repeat(3,72px);grid-auto-rows:72px}.zpad{grid-template-columns:72px;grid-auto-rows:72px}.seg label{font-size:13px;padding:6px 2px}}
</style>
<header class="bar"><div class="brand">XYZ<small>Stripboard cutter</small></div><span id="status" class="pill" role="status">Connecting…</span><small id="link" class="link" title="Round trip of the last status request, and the slowest in the past minute"></small><button id="stop" title="Stop all motion and turn the motors off (Esc)">STOP</button></header>
<main>
<section class="card">
<h2>Drill position</h2>
<div class="dro"><div><span>Hole</span><b id="here">—</b><small id="hereNote">Position unknown</small></div><div><span>Drill height</span><b id="height">—</b><small id="heightNote">relative to A1</small></div></div>
<div class="ref"><span id="referenceNote"></span><span class="badge" id="refBadge">Position unknown</span></div>
<div class="actions" id="refActions"><button id="confirm" data-op="confirm">Nothing moved since power-off</button><button id="reference" data-op="reference">Drill is above A1</button></div>
<div class="gate" id="gate"><span id="gateText"></span><button class="primary" id="arm" data-op="arm">Motors on</button><button id="disarm" data-op="stop" title="Turn the motors off; the drill may settle under gravity">Motors off</button></div>
<div class="goto"><label for="hole"><b>Go to hole</b></label><input id="hole" placeholder="D12" autocomplete="off" spellcheck="false" maxlength="4"><button id="go" class="primary">Go</button><p class="hint" id="goHint">Lift 1 mm → travel straight → lower 1 mm.</p></div>
<h2 style="margin-top:26px">Move</h2>
<div class="move">
<div class="seg xy" role="radiogroup" aria-label="Move across the board by"><label><input type="radio" name="xy" value="1h" checked>1 hole<small>2.54 mm</small></label><label><input type="radio" name="xy" value="3h">3 holes<small>7.62 mm</small></label><label><input type="radio" name="xy" value="100">1 mm<small>fine</small></label><label><input type="radio" name="xy" value="10">0.1 mm<small>fine</small></label></div>
<div class="seg z" role="radiogroup" aria-label="Raise or lower by"><label><input type="radio" name="z" value="500">5 mm</label><label><input type="radio" name="z" value="100" checked>1 mm</label><label><input type="radio" name="z" value="10">0.1 mm</label></div>
<div class="pad" id="xy"></div><div class="zpad" id="z"></div>
</div>
<p class="muted" style="text-align:center;margin:14px 0 0">Columns increase ← · Rows increase ↓ · One press per move.</p>
<div class="cut-controls"><h2>Cut trace</h2><div class="cut-fields">
<label for="cutDepth">Depth (mm)</label><input id="cutDepth" type="number" min="0.1" max="10" step="0.1" value="1">
<label for="cutRpm">Drill speed (RPM)</label><input id="cutRpm" type="number" min="1" max="240" step="1" value="60">
<label for="cutAccel">Drill acceleration (RPM/s)</label><input id="cutAccel" type="number" min="15" max="750" step="1" value="75">
<label for="cutFeed">Plunge/retract (mm/s)</label><input id="cutFeed" type="number" min="0.1" max="20" step="0.1" value="2">
</div><div class="actions"><button id="cut" class="primary">Cut</button><button id="saveCut">Save settings</button></div></div>
<p class="hint">Spins while lowering and raising, with two turns at full depth. Returns to the starting height. Settings are saved when you cut, or press Save settings.</p>
<p class="hint" id="cutHint">Position the bit before cutting. Runs on the controller; STOP cancels.</p>

</section>
<aside>
<section class="card"><h2>Board</h2>
<div class="row"><div><b>A1</b><small id="a1Info"></small></div><button id="go-home" data-op="go-home">Go to A1</button><button id="home" data-op="home" title="Save the drill's current position as hole A1">Set A1 here</button></div>
<div class="row"><div><b>Z34</b><small id="spanInfo"></small></div><button id="go-span">Go to Z34</button><button id="span" data-op="span" title="Save the drill's current position as hole Z34; holes in between are interpolated">Set Z34 here</button></div>
<div class="row"><div><b>Board swap</b><small id="swapInfo"></small></div><button id="go-replace" data-op="go-replace">Swap board</button><button id="replace" data-op="replace" title="Save the drill's current position as the board swap position">Set here</button></div>
<p class="hint" id="savedHint"></p>
</section>
<section class="card" style="margin-top:20px"><h2>Bed calibration · XYZ</h2>
<p class="hint" id="meshInfo">No mesh saved.</p>
<div class="actions"><button id="mesh-start" data-op="mesh-start">Start at A1</button><button id="mesh-clear" data-op="mesh-clear">Clear mesh</button></div>
<div id="meshEditor" hidden>
<div class="mesh-grid" id="meshGrid" role="group" aria-label="Calibration points, columns increase left"></div>
<div class="actions"><button id="mesh-go">Go to A17</button><button id="mesh-save">Save A17</button></div>
<p class="hint">Go stays raised. Fine-jog to the hole and touch the surface; Save.</p>
<div class="actions"><button class="primary" id="mesh-apply" data-op="mesh-apply">Apply mesh</button><button id="mesh-cancel" data-op="mesh-cancel">Cancel</button></div>
</div></section>
<section class="card" style="margin-top:20px"><h2>Cut a list</h2>
<label for="cutList">Coordinates, separated by commas</label>
<textarea id="cutList" rows="4" maxlength="8192" placeholder="A1, N15, Z34" spellcheck="false" aria-describedby="batchHint"></textarea>
<p class="hint">Uses the current cut settings. Travels with clearance, then cuts each hole in order and returns to A1. Runs on the controller. Cancel Cut All finishes the current cut and returns to A1; STOP stops immediately.</p>
<div class="actions"><button id="cutAll" class="primary">Cut All</button><button id="cancelCutAll" hidden title="Finish the current cut, skip the remaining holes, and return to A1">Cancel Cut All</button></div>
<p class="hint" id="batchHint" role="status">Enter up to 884 coordinates, A1–Z34.</p>
</section>
<details><summary><span class="warn">No limit switches.</span> Check travel & clearance before moving.</summary>
<p><b>Travel:</b> A1 and Swap board use the higher endpoint height. Hole moves (A1–Z34) lift 1 mm and return to the starting height. Travel is straight, at 4× arrow speed. XY arrows keep the current height. Only Cut and Cut All run the spindle.</p>
<p><b>Position:</b> Estimated from steps at a provisional 100 steps/mm. Default pitch is 2.54 mm; setting Z34 calibrates the grid between A1 and Z34. A1, Z34 and swap are saved on the controller.</p>
<p><b>Mesh:</b> Touch the A1 surface, then Start at A1. Measure all nine XYZ points at the same tip contact height and Apply mesh. Hole travel and whole-hole steps interpolate XYZ and preserve height above the bed, lifting over the highest mesh point first. Millimetre jogs stay manual. Outside the board, bed height holds at the nearest mesh edge. A1 and swap travel to their saved heights.</p>
<p><b>Re-home:</b> Align XYZ with A1 at the original tip height, then confirm or set A1. The mesh is kept; setting A1 cancels any unfinished calibration.</p>
<p><b>Recovery:</b> After reboot, confirm nothing moved or return above A1 and confirm there. After interrupted motion, return to A1 and confirm again.</p>
<p><b>Stopping:</b> STOP / Esc cancels motion and disables motors; use the machine’s emergency stop for safety. Losing connection does not stop a move. Idle motors switch off after 60 s without this page.</p></details>
</aside>
</main><div id="message" role="status" aria-live="polite"></div>
<script>
const $=id=>document.getElementById(id);const PPM=100,PITCH=254,COLS=34,ROWS=26; // Boards run A1 to Z34.
let cutSettingsLoaded=false;
let state=null,pending=false,online=false,xyStep={holes:1},zStep=100,hideTimer,lastUptime=null,worst=0,worstSince=0;
const meshNames=['A1','A17','A34','M1','M17','M34','Z1','Z17','Z34'],meshColumns=[1,17,34],meshRows=[0,12,25];
let meshPoint=1;const meshButtons=[];
const client=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
const rowName=i=>(i>=26?rowName(Math.floor(i/26)-1):'')+String.fromCharCode(65+i%26);
const holeName=(col,row)=>col>=1&&col<=COLS&&row>=0&&row<ROWS?rowName(row)+col:null;
const mm=p=>(p/PPM).toFixed(p%PPM?p%10?2:1:0)+' mm';
const stepText=st=>st.holes?st.holes+(st.holes===1?' hole':' holes'):mm(st.pulses);
// The XY offset of Z34 from A1 in raw steps: measured when set, else nominal.
const span=()=>state?.spanSet?state.span:[(COLS-1)*PITCH,-(ROWS-1)*PITCH];
// Raw steps from A1 to a hole: columns run along +X, rows along -Y, each
// axis interpolated between A1 and Z34. Same rounding as the controller.
function meshSample(col,row){const c=col<=17?0:1,r=row<=12?0:1,u=(col-meshColumns[c])/(meshColumns[c+1]-meshColumns[c]),v=(row-meshRows[r])/(meshRows[r+1]-meshRows[r]),p=state.mesh;return[0,1,2].map(a=>(p[r*3+c][a]*(1-u)+p[r*3+c+1][a]*u)*(1-v)+(p[(r+1)*3+c][a]*(1-u)+p[(r+1)*3+c+1][a]*u)*v);}
function meshLocate(x,y){let col=1+x/PITCH,row=-y/PITCH;for(let i=0;i<16;i++){const p=meshSample(col,row),pc=meshSample(col+.001,row),pr=meshSample(col,row+.001),dx=x-p[0],dy=y-p[1];if(Math.abs(dx)+Math.abs(dy)<.001)return[col,row];const a=(pc[0]-p[0])/.001,b=(pr[0]-p[0])/.001,c=(pc[1]-p[1])/.001,d=(pr[1]-p[1])/.001,det=a*d-b*c;if(Math.abs(det)<1)break;col+=(dx*d-b*dy)/det;row+=(a*dy-dx*c)/det;}return[1+x/PITCH,-y/PITCH];}
function bedHeight(p){if(!state?.meshSet)return 0;let[c,r]=meshLocate(p[0],p[1]);const hc=Math.round(c),hr=Math.round(r),h=hole(hc,hr);if(h[0]===p[0]&&h[1]===p[1]){c=hc;r=hr;}return Math.round(meshSample(Math.max(1,Math.min(34,c)),Math.max(0,Math.min(25,r)))[2]);}
function hole(col,row){if(state?.meshSet)return meshSample(col,row).slice(0,2).map(Math.round);const[sx,sy]=span();return[Math.round(sx*(col-1)/(COLS-1)),Math.round(sy*row/(ROWS-1))];}
function grid(p){const[sx,sy]=span(),indices=state?.meshSet?meshLocate(p[0],p[1]):[p[0]*(COLS-1)/sx+1,p[1]*(ROWS-1)/sy];const col=Math.round(indices[0]),row=Math.round(indices[1]),h=hole(col,row),rx=p[0]-h[0],ry=h[1]-p[1];return{col,row,name:holeName(col,row),rx,ry,on:!rx&&!ry};}
function place(g){if(!g.name)return'Outside A1–Z34';if(g.on)return'On grid';const parts=[];if(g.rx)parts.push(mm(Math.abs(g.rx))+(g.rx>0?' left':' right'));if(g.ry)parts.push(mm(Math.abs(g.ry))+(g.ry>0?' forward':' back'));return parts.join(', ')+' of '+g.name;}
function parseHole(t){const m=/^\s*([A-Za-z]{1,2})\s*(\d{1,3})\s*$/.exec(t||'');if(!m)return null;let row=0;for(const ch of m[1].toUpperCase())row=row*26+ch.charCodeAt(0)-64;const col=+m[2];return holeName(col,row-1)?{col,row:row-1}:null;}
const arrows=[];
function jog(axis,sign,glyph,dir){const b=document.createElement('button');b.className='jog';b.disabled=true;const i=document.createElement('i');i.textContent=glyph;const t=document.createElement('span');b.append(i);b.append(t);b.onclick=()=>act('jog',axis==='Z'?{axis,pulses:sign*zStep}:xyStep.holes?{axis,holes:sign*xyStep.holes}:{axis,pulses:sign*xyStep.pulses});arrows.push({b,t,axis,sign,dir});return b;}
function hub(title,sub){const d=document.createElement('div');d.className='hub';const b=document.createElement('b');b.id=title;b.textContent='—';const s=document.createElement('span');s.textContent=sub;d.append(b);d.append(s);return d;}
const xy={1:['Y',1,'↑','Back'],3:['X',1,'←','Left'],5:['X',-1,'→','Right'],7:['Y',-1,'↓','Forward']};
for(let i=0;i<9;i++)$('xy').append(i===4?hub('hub','drill'):xy[i]?jog(...xy[i]):document.createElement('div'));
$('z').append(jog('Z',1,'▲','Up'));$('z').append(hub('zhub','height'));$('z').append(jog('Z',-1,'▼','Down'));
for(const i of [2,1,0,5,4,3,8,7,6]){const b=document.createElement('button');b.onclick=()=>{meshPoint=i;render();};b.title='Select '+meshNames[i];$('meshGrid').append(b);meshButtons[i]=b;}
document.addEventListener('change',e=>{if(e.target.name==='xy')xyStep=/h$/.test(e.target.value)?{holes:parseInt(e.target.value)}:{pulses:+e.target.value};if(e.target.name==='z')zStep=+e.target.value;render();});
function render(){const s=state,blocked=!online||pending||!s||s.busy||!s.commissioned;document.querySelectorAll('[data-op],.jog').forEach(b=>b.disabled=blocked);$('go').disabled=true;$('cut').disabled=true;$('saveCut').disabled=true;$('cutAll').disabled=true;$('cancelCutAll').disabled=true;$('cutList').disabled=blocked;$('cutDepth').disabled=blocked;$('cutRpm').disabled=blocked;$('cutFeed').disabled=blocked;$('cutAccel').disabled=blocked;
const st=$('status');if(!online){st.textContent='Disconnected';st.dataset.tone='bad';}if(!s)return;
if(online){st.textContent=s.batch?.returning?'Returning to A1':s.batch?.active?'Cut list '+(s.batch.completed+1)+'/'+s.batch.total:s.cutPhase?'Cutting':s.busy?'Moving':s.armed?'Motors on':'Motors off · '+(s.disableReason||'Stopped');st.dataset.tone=s.busy?'busy':s.armed?'ok':'off';}
const g=s.known?grid(s.position):null,z=Math.round(s.position[2]-bedHeight(s.position));
$('here').textContent=g?g.name||'Off board':'—';$('hereNote').textContent=g?place(g):'Position unknown';$('hereNote').className=g&&g.name&&!g.on?'off':'';
$('height').textContent=s.known?(z<0?'−':'+')+mm(Math.abs(z)):'—';$('heightNote').textContent=s.known?(z<0?'below':'above')+(s.meshSet?' bed':' A1'):'Position unknown';
$('hub').textContent=g?(g.on?'':'≈')+(g.name||'—'):'—';$('zhub').textContent=s.known?(z<0?'−':'+')+(Math.abs(z)/PPM).toFixed(1):'—';
const n=xyStep.holes||0;
arrows.forEach(a=>{const step=a.axis==='Z'?{pulses:zStep}:xyStep;let t=a.dir+' '+stepText(step);if(a.axis!=='Z'&&g&&g.on&&n){const col=g.col+(a.axis==='X'?a.sign*n:0),row=g.row-(a.axis==='Y'?a.sign*n:0);t=holeName(col,row)||'Off board';}a.t.textContent=t;a.b.title=a.dir+' '+stepText(step)+(t.includes(' ')?'':' to '+t);});
$('refBadge').textContent=!s.homeSet?'A1 not set':s.known?'Position known':'Position unknown';$('refBadge').dataset.tone=s.known?'ok':'warn';
$('referenceNote').textContent=!s.commissioned?'Motor mapping changed. Restore it before use.':s.known?'Re-home at A1 at the same tip height. Calibration is kept.':s.homeSet?'Confirm position, or use mm jogs to align XYZ at saved A1.':'Align with A1 at the top-right stops, then set A1.';
$('confirm').hidden=s.known||!s.homeSet||!s.recoverable;$('reference').hidden=s.known||!s.homeSet;$('refActions').hidden=$('confirm').hidden&&$('reference').hidden;
const why=!online||!s.commissioned?'':s.webArmed?'Controlled here.':s.armed?'Controlled elsewhere. Press STOP, then Motors on.':'Enable motors to move.';
$('gate').hidden=!why;$('gateText').textContent=why;$('arm').hidden=s.armed;$('arm').disabled=blocked||s.armed;$('disarm').hidden=!s.webArmed;
arrows.forEach(a=>a.b.disabled=blocked||!s.webArmed||!!(s.meshSet&&!s.known&&a.axis!=='Z'&&xyStep.holes));
const travel=blocked||!s.known||!s.homeSet||!s.webArmed;
$('cut').disabled=travel||!!s.calibrating||!cutOptions();
$('cutAll').disabled=$('cut').disabled||!$('cutList').value.trim();
const batch=s.batch;
$('cancelCutAll').hidden=!batch?.active;$('cancelCutAll').disabled=!online||pending||!s.webArmed||!batch?.active||!!batch.cancelRequested||!!batch.returning;
$('cancelCutAll').textContent=batch?.cancelRequested?'Cancel requested':'Cancel Cut All';
$('batchHint').textContent=batch?.returning?(batch.cancelRequested?'Cancelled · returning to A1':'Cuts complete · returning to A1'):batch?.active&&batch.cancelRequested?(s.cutPhase?'Finishing current cut':'Finishing travel')+' · then returning to A1':batch?.active?(s.cutPhase?'Cutting ':'Going to ')+batch.hole+' · '+(batch.completed+1)+' of '+batch.total:batch?.returned?(batch.cancelRequested?'Cancelled after '+batch.completed+' of '+batch.total+' cuts':'Completed '+batch.total+' cuts')+' · returned to A1.':batch?.total?'Stopped after '+batch.completed+' of '+batch.total+' cuts.':'Enter up to 884 coordinates, A1–Z34.';
$('saveCut').disabled=blocked||(s.armed&&!s.webArmed)||!cutOptions();
$('cutHint').textContent=s.cutPhase?['','Cutting · spinning and lowering','Cutting · two turns at full depth','Cutting · spinning and returning','Cutting · stopping the drill'][s.cutPhase]:s.calibrating?'Finish calibration before cutting.':'Position the bit before cutting. Runs on the controller; STOP cancels.';
$('go').disabled=travel;$('go-home').disabled=travel;$('go-span').disabled=travel;$('go-replace').disabled=travel||!s.replaceSet;$('replace').disabled=blocked||!s.known||!s.homeSet;$('span').disabled=blocked||!s.known||!s.homeSet;
$('span').disabled=$('span').disabled||!!s.meshSet||!!s.calibrating;
$('meshInfo').textContent=s.calibrating?((s.draftMask||0).toString(2).split('1').length-1)+'/9 measured · '+(s.meshSet?'Saved mesh stays active.':'Apply when complete.'):s.meshSet?'3×3 mesh active · retained when A1 changes.':'Touch A1 surface, then start.';
$('meshEditor').hidden=!s.calibrating;$('mesh-clear').hidden=!s.meshSet;
$('mesh-start').textContent=s.calibrating?'Restart at A1':'Start at A1';
$('mesh-go').textContent='Go to '+meshNames[meshPoint];$('mesh-save').textContent='Save '+meshNames[meshPoint];
$('mesh-go').disabled=travel||!s.calibrating;$('mesh-save').disabled=blocked||!s.known||!s.calibrating||meshPoint===0;
$('mesh-apply').disabled=blocked||!s.known||!s.calibrating||s.draftMask!==511;
meshButtons.forEach((b,i)=>{b.textContent=((s.draftMask||0)&(1<<i)?'✓ ':'')+meshNames[i];b.setAttribute('aria-pressed',String(i===meshPoint));});
$('goHint').textContent=s.meshSet?'Lift → travel → follow bed height.':parseHole($('hole').value)?'Lift 1 mm → '+$('hole').value.toUpperCase()+' → lower 1 mm.':'Lift 1 mm → travel straight → lower 1 mm.';
$('a1Info').textContent=s.homeSet?'Top-right hole · corner stops':'Not set · align with A1, then set here.';
const pitch=(p,n)=>(Math.abs(p)/n/PPM).toFixed(3)+' mm';
$('spanInfo').textContent=s.meshSet?'Position from 3×3 mesh':s.spanSet?'Pitch: '+pitch(s.span[0],COLS-1)+' across · '+pitch(s.span[1],ROWS-1)+' forward':'Default pitch: 2.54 mm. Go to Z34, fine-align, then set here.';
const r=s.replaceSet?grid(s.replace):null,rz=s.replace[2];
$('swapInfo').textContent=r?'Park: '+(r.on&&r.name?r.name:mm(s.replace[0])+' left, '+mm(-s.replace[1])+' forward of A1')+', '+mm(Math.abs(rz))+(rz<0?' below':' above')+' A1.':'Not set · raise drill, move board clear, then set here.';
$('savedHint').textContent=!s.homeSet?'':!s.known?'Confirm position to save or travel.':!s.webArmed?'Enable motors to travel.':s.meshSet?'Travel lifts over the mesh. Fine mm jogs stay manual.':'Travel clearance: A1 / swap = higher endpoint · Z34 = +1 mm.';
}
function say(text,error){const m=$('message');m.textContent=text;m.className='show'+(error?' err':'');clearTimeout(hideTimer);if(!error)hideTimer=setTimeout(()=>{m.className='';},3500);}
async function post(op,extra={}){const response=await fetch('/api/action',{method:'POST',headers:{'X-XYZ-Control':'1','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({op,client,...extra}),signal:AbortSignal.timeout(1200)});const text=await response.text();if(!response.ok)throw Error(text);return text;}
async function act(op,extra={}){if(pending&&op!=='stop')return;if(op==='home'&&state?.homeSet&&!confirm((state.known?'Move A1 to the drill’s current position?':'Replace A1 and clear the saved swap position? To keep A1, use “Drill is above A1”.')+(state.calibrating?' This cancels the unfinished calibration.':'')))return;if(op==='span'&&state?.spanSet&&!confirm('Set Z34 at the current position?'))return;if(op==='mesh-start'&&!confirm('Tip touching the A1 surface? This sets A1 here and starts a new calibration. The saved mesh stays active until Apply.'))return;if(op==='mesh-clear'&&!confirm('Clear the mesh and use the saved Z34 pitch (or default pitch)?'))return;pending=true;render();try{say(await post(op,extra));}catch(e){say(failure(e),true);}finally{pending=false;await refresh();}}
function link(ms){const now=Date.now();if(now-worstSince>60000){worst=0;worstSince=now;}worst=Math.max(worst,ms);const l=$('link');l.textContent='link '+Math.round(ms)+' ms · worst '+(worst>=1000?(worst/1000).toFixed(1)+' s':Math.round(worst)+' ms');l.className='link'+(worst>=1000?' slow':'');}
function failure(e){return e.name==='TimeoutError'||/abort/i.test(e.message)?'No reply from the controller within 1.2 s. The motors are unaffected; the request may still have run.':e.message;}
async function refresh(){const t0=Date.now();try{state=JSON.parse(await post('poll'));online=true;if(!cutSettingsLoaded&&state.cutSettings){$('cutDepth').value=String(state.cutSettings.depth);$('cutRpm').value=String(state.cutSettings.rpm);$('cutFeed').value=String(state.cutSettings.feed);$('cutAccel').value=String(state.cutSettings.accel);cutSettingsLoaded=true;}link(Date.now()-t0);if(lastUptime!==null&&state.uptime<lastUptime)say('Controller restarted: uptime fell from '+lastUptime+' s to '+state.uptime+' s. Check power, then run CRASH INFO over USB.',true);lastUptime=state.uptime;}catch(e){online=false;link(Date.now()-t0);}render();}
function cutOptions(){const depth=Number($('cutDepth').value),rpm=Number($('cutRpm').value),feed=Number($('cutFeed').value),accel=Number($('cutAccel').value);return Number.isFinite(depth)&&depth>=0.1&&depth<=10&&Math.abs(depth*10-Math.round(depth*10))<0.000001&&Number.isInteger(rpm)&&rpm>=1&&rpm<=240&&Number.isFinite(feed)&&feed>=0.1&&feed<=20&&Math.abs(feed*10-Math.round(feed*10))<0.000001&&Number.isInteger(accel)&&accel>=15&&accel<=750?{depth,rpm,feed,accel}:null;}
function cut(){const options=cutOptions();if(!options){say('Use depth 0.1–10 mm, speed 1–240 RPM, acceleration 15–750 RPM/s, and plunge/retract 0.1–20 mm/s.',true);return;}return act('cut',options);}
$('saveCut').onclick=()=>{const options=cutOptions();if(options)return act('cut-settings',options);};
$('cut').onclick=cut;$('cutDepth').oninput=()=>render();$('cutRpm').oninput=()=>render();$('cutFeed').oninput=()=>render();$('cutAccel').oninput=()=>render();
function cutAll(){const options=cutOptions();if(!options){say('Enter valid cut settings first.',true);return;}const text=$('cutList').value;if(text.length>8192){say('Use at most 8192 characters.',true);return;}const entries=text.split(',');if(entries.length>884){say('Use at most 884 coordinates.',true);return;}const holes=[];for(let i=0;i<entries.length;i++){const token=entries[i].trim();if(!/^[A-Za-z][0-9]{1,2}$/.test(token)||!parseHole(token)){say('Invalid coordinate '+(i+1)+': '+(token||'(empty)')+'. Use A1–Z34.',true);return;}const h=parseHole(token);holes.push(rowName(h.row)+h.col);}return act('cut-all',{...options,holes:holes.join(',')});}
$('cancelCutAll').onclick=()=>act('cancel-cut-all');$('cutAll').onclick=cutAll;$('cutList').oninput=()=>render();
function goHole(){const h=parseHole($('hole').value);if(!h){say('Enter A1–Z34 (e.g. D12).',true);return;}return act('goto',{hole:rowName(h.row)+h.col});}
$('go').onclick=goHole;$('go-span').onclick=()=>act('goto',{hole:'Z34'});$('hole').onkeydown=e=>{if(e.key==='Enter'&&!$('go').disabled)goHole();};
$('hole').oninput=()=>render();
$('mesh-go').onclick=()=>act('mesh-go',{point:meshPoint});$('mesh-save').onclick=()=>act('mesh-save',{point:meshPoint});
$('stop').onclick=()=>act('stop');document.querySelectorAll('[data-op]').forEach(b=>b.onclick=()=>act(b.dataset.op));
document.addEventListener('keydown',e=>{if(e.code==='Escape'){e.preventDefault();act('stop');}});
// One request marks the owning page present and returns status. Retry even
// after a failed request; observers never count as the controlling page.
async function poll(){if(!document.hidden&&!pending)await refresh();setTimeout(poll,300);}
render();poll();
</script></html>)HTML";
