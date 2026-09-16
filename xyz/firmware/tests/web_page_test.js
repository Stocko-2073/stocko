// Run the shipped page script against a small DOM/fetch double.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const html = fs.readFileSync('xyza/web_page.h', 'utf8');
assert(html.includes('<input type="radio" name="xy" value="1h" checked>1 hole'));
assert(html.includes('<input type="radio" name="z" value="100" checked>1 mm'));
assert(!/\)HTML"/.test(html.match(/R"HTML\(([\s\S]*)\)HTML";/)[1]));
const elements = [];
function element(tag = 'div') {
  const e = {tag, children: [], dataset: {}, disabled: false, hidden: false,
    textContent: '', value: '10', className: '', title: '',
    setAttribute(name,value) { this[name]=value; },
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; }};
  elements.push(e); return e;
}
const ids = {};
for (const match of html.matchAll(/id="([^"]+)"(?: data-op="([^"]+)")?/g)) {
  ids[match[1]] = element();
  if (match[2]) ids[match[1]].dataset.op = match[2];
}
const document = {hidden: false, getElementById: id => ids[id] || elements.find(e => e.id === id),
  createElement: element, addEventListener() {},
  querySelectorAll(selector) {
    return elements.filter(e => (selector.includes('[data-op]') && e.dataset.op) ||
      (selector.includes('.jog') && e.className === 'jog'));
  }};
const requests = [];
let failNextPoll=false;
let responseState = {armed:false,webArmed:false,busy:false,known:false,homeSet:false,
  replaceSet:false,spanSet:false,recoverable:false,commissioned:true,position:[0,0,0],replace:[0,0,0],span:[0,0],uptime:500};
const context = vm.createContext({document,crypto:webcrypto,Uint8Array,URLSearchParams,
  AbortSignal,confirm:()=>true,setTimeout:()=>{},clearTimeout:()=>{},fetch:async (url, options) => {
    requests.push({url,options});
    if(options.body?.get('op')==='poll'&&failNextPoll){failNextPoll=false;throw Error('Temporary delay');}
    return {ok:true,text:async()=>options.body?.get('op')==='poll'?JSON.stringify(responseState):'OK',json:async()=>responseState};
  }});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
(async () => {
  await vm.runInContext('refresh()', context);
  assert.equal(ids.arm.disabled,false);
  assert.equal(ids.gate.hidden,false);
  assert.equal(ids.disarm.hidden,true);
  assert.equal(ids.here.textContent,'—');
  assert.equal(ids.refBadge.textContent,'A1 not set');
  assert.equal(ids.go.disabled,true);
  assert.equal(ids.replace.disabled,true);
  assert.equal(ids.span.disabled,true);
  assert.equal(ids['go-home'].disabled,true);
  assert.equal(ids['go-span'].disabled,true);
  await vm.runInContext("act('arm')", context);
  const request = requests.find(r => r.options.body?.get('op') === 'arm');
  assert.equal(request.options.headers['X-XYZ-Control'],'1');
  assert.equal(request.options.body.get('client').length,32);
  responseState = {...responseState,armed:true,webArmed:true,known:true,homeSet:true,
    replaceSet:true,position:[1524,-508,250],replace:[2540,-3810,800]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids['go-home'].disabled,false);
  assert.equal(ids['go-span'].disabled,false);
  assert.equal(ids.replace.disabled,false);
  assert.equal(ids.span.disabled,false);
  assert(ids.spanInfo.textContent.startsWith('Default pitch: 2.54 mm.'));
  // Raw +X counts columns leftward; raw -Y counts rows forward from A.
  assert.equal(ids.here.textContent,'C7');
  assert.equal(ids.hereNote.textContent,'On grid');
  assert.equal(ids.height.textContent,'+2.5 mm');
  assert.equal(document.getElementById('hub').textContent,'C7');
  const labels=vm.runInContext("arrows.map(a=>a.t.textContent)",context);
  assert.equal(JSON.stringify(labels),JSON.stringify(['B7','C8','C6','D7','Up 1 mm','Down 1 mm']));
  assert.equal(ids.swapInfo.textContent,'Park: P11, 8 mm above A1.');
  assert.equal(ids.gate.hidden,false); // Owning page: offers to turn the motors off.
  assert.equal(ids.arm.hidden,true);
  assert.equal(ids.disarm.hidden,false);
  assert.equal(ids.disarm.dataset.op,'stop');
  assert.equal(ids.status.dataset.tone,'ok');
  assert.equal(ids.status.textContent,'Motors on');
  assert.equal(ids.go.disabled,false);
  // Off-grid and fine steps fall back to direction words.
  responseState={...responseState,position:[1554,-498,-30]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.here.textContent,'C7');
  assert.equal(ids.hereNote.textContent,'0.3 mm left, 0.1 mm back of C7');
  assert.equal(ids.height.textContent,'−0.3 mm');
  assert.equal(vm.runInContext("arrows[1].t.textContent",context),'Left 1 hole');
  vm.runInContext("xyStep={pulses:10};render()",context);
  assert.equal(vm.runInContext("arrows[1].t.textContent",context),'Left 0.1 mm');
  vm.runInContext("xyStep={holes:1}",context);
  responseState={...responseState,position:[1524,-508,250]};
  await vm.runInContext('refresh()',context);
  // With Z34 saved, the grid interpolates between the corners, with the
  // controller's rounding, and the measured pitch is shown.
  responseState={...responseState,spanSet:true,span:[8462,-6410],position:[2821,-3077,0]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.here.textContent,'M12');
  assert.equal(ids.hereNote.textContent,'On grid');
  assert.equal(ids.spanInfo.textContent,'Pitch: 2.564 mm across · 2.564 mm forward');
  assert.equal(JSON.stringify(vm.runInContext("arrows.map(a=>a.t.textContent)",context)),JSON.stringify(['L12','M13','M11','N12','Up 1 mm','Down 1 mm']));
  assert.equal(JSON.stringify(vm.runInContext("hole(34,25)",context)),'[8462,-6410]');
  assert.equal(JSON.stringify(vm.runInContext("hole(1,0)",context)),'[0,0]');
  responseState={...responseState,position:[2831,-3077,0]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.hereNote.textContent,'0.1 mm left of M12');
  assert.equal(vm.runInContext("arrows[1].t.textContent",context),'Left 1 hole');
  responseState={...responseState,position:[8462,-6410,0]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.here.textContent,'Z34');
  ids['go-span'].onclick();
  await new Promise(r=>setImmediate(r));
  assert.equal(requests.findLast(r=>r.options.body?.get('op')==='goto').options.body.get('hole'),'Z34');
  responseState={...responseState,spanSet:false,span:[0,0],position:[1524,-508,250]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.here.textContent,'C7');
  // Go to hole: letters are rows, numbers are columns; A1 is the origin.
  assert.equal(JSON.stringify(vm.runInContext("parseHole('d12')",context)),'{"col":12,"row":3}');
  assert.equal(JSON.stringify(vm.runInContext("parseHole('z34')",context)),'{"col":34,"row":25}');
  assert.equal(vm.runInContext("parseHole('AA1')",context),null); // Beyond row Z.
  assert.equal(vm.runInContext("parseHole('A35')",context),null); // Beyond column 34.
  assert.equal(vm.runInContext("parseHole('A0')",context),null);
  assert.equal(vm.runInContext("parseHole('12D')",context),null);
  assert.equal(vm.runInContext("holeName(35,0)",context),null);
  assert.equal(vm.runInContext("rowName(27)",context),'AB');
  ids.hole.value='d12';
  await vm.runInContext('goHole()',context);
  const goto=requests.findLast(r=>r.options.body?.get('op')==='goto');
  assert.equal(goto.options.body.get('hole'),'D12');
  assert.equal(goto.options.body.has('x'),false);
  // Poll must retry after a network failure, even with online=false.
  failNextPoll=true;
  await vm.runInContext('poll()',context);
  assert.equal(ids.status.textContent,'Disconnected');
  await vm.runInContext('poll()',context);
  assert.equal(ids.status.textContent,'Motors on');
  responseState.busy=true;
  await vm.runInContext('refresh()',context);
  assert.equal(ids.home.disabled,true);
  assert.equal(ids.stop.disabled,false);
  assert.equal(ids.status.textContent,'Moving');
  assert.equal(ids.status.dataset.tone,'busy');
  // A page that does not own control is told why the pad is disabled.
  responseState={...responseState,busy:false,webArmed:false};
  await vm.runInContext('refresh()',context);
  assert(ids.gateText.textContent.includes('Press STOP'));
  assert.equal(ids.arm.hidden,true);
  assert(vm.runInContext("document.querySelectorAll('.jog').every(b=>b.disabled)",context));
  responseState={...responseState,busy:true,webArmed:true};
  await vm.runInContext('refresh()',context);
  await vm.runInContext("act('stop')",context);
  assert(requests.some(r=>r.options.body?.get('op')==='stop'));
  responseState.busy=false;
  await vm.runInContext('refresh()',context);
  // Forward (toward row B) is raw -Y; left (next column) is raw +X. Whole
  // holes are sent as hole counts so the controller applies the local pitch.
  vm.runInContext("xyStep={holes:1};document.querySelectorAll('.jog')[3].onclick()",context);
  await new Promise(r=>setImmediate(r));
  let jog=requests.findLast(r=>r.options.body?.get('op')==='jog');
  assert.equal(jog.options.body.get('axis'),'Y');
  assert.equal(jog.options.body.get('holes'),'-1');
  assert.equal(jog.options.body.has('pulses'),false);
  vm.runInContext("xyStep={holes:3};document.querySelectorAll('.jog')[1].onclick()",context);
  await new Promise(r=>setImmediate(r));
  jog=requests.findLast(r=>r.options.body?.get('op')==='jog');
  assert.equal(jog.options.body.get('axis'),'X');
  assert.equal(jog.options.body.get('holes'),'3');
  vm.runInContext("xyStep={pulses:100};document.querySelectorAll('.jog')[1].onclick()",context);
  await new Promise(r=>setImmediate(r));
  jog=requests.findLast(r=>r.options.body?.get('op')==='jog');
  assert.equal(jog.options.body.get('pulses'),'100');
  assert.equal(jog.options.body.has('holes'),false);
  vm.runInContext("document.querySelectorAll('.jog')[5].onclick()",context);
  await new Promise(r=>setImmediate(r));
  jog=requests.findLast(r=>r.options.body?.get('op')==='jog');
  assert.equal(jog.options.body.get('axis'),'Z');
  assert.equal(jog.options.body.get('pulses'),'-100');
  // A controller restart shows as uptime going backwards.
  assert(ids.link.textContent.startsWith('link '));
  responseState={...responseState,uptime:3};
  await vm.runInContext('refresh()',context);
  assert(ids.message.textContent.startsWith('Controller restarted: uptime fell from 500 s to 3 s'));
  assert.equal(ids.message.className,'show err');
  // Full XYZ mesh: readout, destinations and height use the same bilinear
  // map as firmware, including the unequal 16/17 and 12/13 intervals.
  const mesh=[];
  for(let r=0;r<3;r++)for(let c=0;c<3;c++)mesh.push([
    ([1,17,34][c]-1)*254+r*c*2+(r===1?20:0),
    -[0,12,25][r]*254+c*15,r*40+c*15+(r===1&&c===1?100:0)]);
  responseState={...responseState,known:true,homeSet:true,armed:true,webArmed:true,busy:false,
    meshSet:true,mesh,calibrating:false,draftMask:0,position:[...mesh[4]]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.here.textContent,'M17');
  assert.equal(ids.hereNote.textContent,'On grid');
  assert.equal(ids.height.textContent,'+0 mm');
  assert.equal(ids.heightNote.textContent,'above bed');
  assert.equal(ids.span.disabled,true);
  assert.equal(ids.meshEditor.hidden,true);
  assert.equal(ids['mesh-clear'].hidden,false);
  assert.equal(ids['mesh-apply'].disabled,true);
  assert.equal(JSON.stringify(vm.runInContext('meshSample(9,6)',context)),'[2042.5,-1516.5,52.5]');
  assert.equal(JSON.stringify(vm.runInContext('hole(9,6)',context)),'[2043,-1516]');
  for(let r=0;r<26;r++)for(let c=1;c<=34;c++){
    const g=vm.runInContext(`grid(hole(${c},${r}))`,context);
    assert.equal(g.col,c);assert.equal(g.row+0,r);assert.equal(g.on,true);
    assert.equal(vm.runInContext(`bedHeight(hole(${c},${r}))`,context),
      vm.runInContext(`Math.round(meshSample(${c},${r})[2])`,context));
  }
  responseState={...responseState,calibrating:true,draftMask:1};
  await vm.runInContext('refresh()',context);
  assert.equal(ids.meshEditor.hidden,false);
  assert.equal(ids['mesh-go'].disabled,false);
  assert.equal(ids['mesh-save'].disabled,false);
  assert.equal(ids['mesh-apply'].disabled,true);
  assert(ids.meshInfo.textContent.startsWith('1/9 measured'));
  assert.equal(vm.runInContext('meshButtons[0].textContent',context),'✓ A1');
  vm.runInContext('meshButtons[4].onclick()',context);
  assert.equal(ids['mesh-save'].textContent,'Save M17');
  assert.equal(vm.runInContext("meshButtons[4]['aria-pressed']",context),'true');
  ids['mesh-save'].onclick();await new Promise(r=>setImmediate(r));
  assert.equal(requests.findLast(r=>r.options.body?.get('op')==='mesh-save').options.body.get('point'),'4');
  ids['mesh-go'].onclick();await new Promise(r=>setImmediate(r));
  assert.equal(requests.findLast(r=>r.options.body?.get('op')==='mesh-go').options.body.get('point'),'4');
  vm.runInContext('meshButtons[0].onclick()',context);
  assert.equal(ids['mesh-save'].disabled,true); // A1 is captured by Start, never edited alone.
  responseState={...responseState,draftMask:511};
  await vm.runInContext('refresh()',context);
  assert.equal(ids['mesh-apply'].disabled,false);
  vm.runInContext('xyStep={holes:1}',context);
  responseState={...responseState,known:false};
  await vm.runInContext('refresh()',context);
  assert.equal(ids['mesh-go'].disabled,true);
  assert.equal(ids['mesh-save'].disabled,true);
  assert.equal(ids['mesh-apply'].disabled,true);
  assert.equal(ids['mesh-start'].disabled,false); // Can establish A1 after physical movement.
  assert(vm.runInContext("arrows.filter(a=>a.axis!=='Z').every(a=>a.b.disabled)",context));
  vm.runInContext('xyStep={pulses:10};render()',context);
  assert(vm.runInContext('arrows.every(a=>!a.b.disabled)',context)); // Manual re-home still possible.
  vm.runInContext('online=false;render()',context);
  assert.equal(ids['go-home'].disabled,true);
  assert.equal(ids.status.textContent,'Disconnected');
  console.log('Web page state and request tests passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
