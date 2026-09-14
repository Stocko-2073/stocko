// Run the shipped page script against a small DOM/fetch double.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const html = fs.readFileSync('xyza/web_page.h', 'utf8');
assert(html.includes('<option value="1000" selected>1000 pulses ≈ 10 mm</option>'));
const elements = [];
function element(tag = 'div') {
  const e = {tag, children: [], dataset: {}, disabled: false, hidden: false,
    textContent: '', value: '10', className: '',
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; }};
  elements.push(e); return e;
}
const ids = {};
for (const match of html.matchAll(/id="([^"]+)"(?: data-op="([^"]+)")?/g)) {
  ids[match[1]] = element();
  if (match[2]) ids[match[1]].dataset.op = match[2];
}
const document = {hidden: false, getElementById: id => ids[id],
  createElement: element, addEventListener() {},
  querySelectorAll(selector) {
    return elements.filter(e => (selector.includes('[data-op]') && e.dataset.op) ||
      (selector.includes('.jog') && e.className === 'jog'));
  }};
const requests = [];
let failNextPoll=false;
let responseState = {armed:false,webArmed:false,busy:false,known:false,homeSet:false,
  replaceSet:false,recoverable:false,commissioned:true,position:[0,0,0],replace:[0,0,0]};
const context = vm.createContext({document,crypto:webcrypto,Uint8Array,URLSearchParams,
  AbortSignal,confirm:()=>true,setTimeout:()=>{},fetch:async (url, options) => {
    requests.push({url,options});
    if(options.body?.get('op')==='poll'&&failNextPoll){failNextPoll=false;throw Error('Temporary delay');}
    return {ok:true,text:async()=>options.body?.get('op')==='poll'?JSON.stringify(responseState):'OK',json:async()=>responseState};
  }});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
(async () => {
  await vm.runInContext('refresh()', context);
  assert.equal(ids.arm.disabled,false);
  assert.equal(ids.replace.disabled,true);
  assert.equal(ids['go-home'].disabled,true);
  await vm.runInContext("act('arm')", context);
  const request = requests.find(r => r.options.body?.get('op') === 'arm');
  assert.equal(request.options.headers['X-XYZ-Control'],'1');
  assert.equal(request.options.body.get('client').length,32);
  responseState = {...responseState,armed:true,webArmed:true,known:true,homeSet:true,
    replaceSet:true,position:[10,20,30],replace:[100,200,300]};
  await vm.runInContext('refresh()',context);
  assert.equal(ids['go-home'].disabled,false);
  assert.equal(ids.replace.disabled,false);
  assert.equal(ids.coords.children[2].textContent,'Z 30');
  // Poll must retry after a network failure, even with online=false.
  failNextPoll=true;
  await vm.runInContext('poll()',context);
  assert.equal(ids.status.textContent,'Disconnected — controls unavailable');
  await vm.runInContext('poll()',context);
  assert.equal(ids.status.textContent,'Motors enabled');
  responseState.busy=true;
  await vm.runInContext('refresh()',context);
  assert.equal(ids.home.disabled,true);
  assert.equal(ids.stop.disabled,false);
  await vm.runInContext("act('stop')",context);
  assert(requests.some(r=>r.options.body?.get('op')==='stop'));
  vm.runInContext('online=false;render()',context);
  assert.equal(ids['go-home'].disabled,true);
  assert.equal(ids.status.textContent,'Disconnected — controls unavailable');
  console.log('Web page state and request tests passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
