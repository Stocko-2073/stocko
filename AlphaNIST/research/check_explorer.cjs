// Offline JavaScript behavior checks with a minimal DOM stub. This is not a browser render test.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'concept-graph.html'),'utf8');
const script=[...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
const elements={};
function element(id){return elements[id]??=( {innerHTML:'',textContent:'',hidden:false,events:{},addEventListener(k,f){this.events[k]=f},setAttribute(k,v){this[k]=v}})}
for(const [,attrs,content] of script){const id=/id="([^"]+)"/.exec(attrs);if(id)element(id[1]).textContent=content}
const modes=['tree','all','gaps','sources'].map(mode=>({...element('mode-'+mode),dataset:{mode}}));
const listeners={};
const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>modes,addEventListener(k,f){listeners[k]=f}},location:{hash:''},history:{replaceState(_a,_b,h){context.location.hash=h}},window:{addEventListener(){}},console});
const js=script.filter(x=>!x[1].includes('application/json')).map(x=>x[2]).join('\n');
new vm.Script(js).runInContext(context);
const run=s=>vm.runInContext(s,context);
const G=JSON.parse(element('graph-data').textContent),S=JSON.parse(element('source-data').textContent);
assert.match(element('detail').innerHTML,/AlphaNIST/);
assert.match(element('stats').innerHTML,new RegExp(String(G.nodes.length)));
for(const n of G.nodes){run(`choose(${JSON.stringify(n.id)})`);assert.ok(element('detail').innerHTML.includes(n.id));assert.equal(context.location.hash,'#'+n.id)}
run('mode="all";term="";renderNav()');assert.equal(element('count').textContent,G.nodes.length+' entries');
run('mode="gaps";renderNav()');assert.equal(element('count').textContent,G.nodes.filter(n=>n.status==='undocumented').length+' entries');
run('choose("gap_metric")');assert.match(element('detail').innerHTML,/What would resolve this/);
element('search').events.input({target:{value:'  covariance  '}});assert.ok(parseInt(element('count').textContent)>0);
element('search').events.input({target:{value:'does-not-exist-123456'}});assert.equal(element('count').textContent,'0 entries');
run('mode="sources";term="";renderNav()');assert.equal(element('count').textContent,Object.keys(S).length+' sources');
for(const s of Object.values(S))assert.ok(element('tree').innerHTML.includes(s.path));
run('mode="tree";term="";renderNav()');element('expand').onclick();
for(const n of G.nodes)assert.ok(element('tree').innerHTML.includes(`data-select="${n.id}"`),n.id);
assert.match(element('tree').innerHTML,/shared/);
element('collapse').onclick();assert.equal(element('count').textContent,(1+G.nodes.find(n=>n.id===G.root).dependencies.length)+' entries');
assert.equal(run('esc("<script>\\\"&\\\'")'),'&lt;script&gt;&quot;&amp;&#39;');
console.log(`PASS: JavaScript parses and starts; all ${G.nodes.length} node selections, view counts, search, sources, expand/collapse and escaping checked.`);
console.log('LIMIT: minimal DOM checks only; no browser visual, CSS layout, accessibility or PDF-link navigation test.');
