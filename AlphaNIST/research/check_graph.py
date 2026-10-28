"""Offline integrity checks for the paper archive and explanatory graph."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import json,hashlib,re,subprocess
R=Path(__file__).resolve().parent.parent
G=json.loads((R/'concept-graph.json').read_text());S=json.loads((R/'sources/catalog.json').read_text())
N={n['id']:n for n in G['nodes']};assert len(N)==len(G['nodes'])
seen=set();active=set()
def visit(i):
 assert i in N,i
 assert i not in active,'cycle '+i
 if i in seen:return
 active.add(i)
 for d in N[i]['dependencies']:visit(d)
 active.remove(i);seen.add(i)
visit(G['root']);assert seen==set(N)
expected={(n['id'],d) for n in N.values() for d in n['dependencies']}
assert expected=={(e['from'],e['to']) for e in G['edges']}
assert len(expected)==len(G['edges'])
for n in N.values():
 assert n['definition'] and n['evidence']
 assert n['status'] in G['status_definitions']
 for e in n['evidence']:assert e['source'] in S and e['locator'],e
 if n['status']=='undocumented':assert n.get('needed_to_resolve'),n['id']
for s in S.values():assert (R/s['path']).is_file(),s['path']
print(f"PASS: {len(N)} unique reachable concepts, {len(expected)} acyclic links, all evidence and closure requirements present.")
pdfs=pages=0
for f in ('papers.json','support.json'):
 for s in json.loads((R/'sources'/f).read_text()):
  if s['status']!='downloaded':continue
  p=R/s['path'];data=p.read_bytes()
  assert hashlib.sha256(data).hexdigest()==s['sha256'],s['id']+' hash'
  assert len(data)==s['bytes'],s['id']+' size'
  if p.suffix=='.pdf':
   assert data.startswith(b'%PDF-')
   info=subprocess.run(['pdfinfo',str(p)],check=True,capture_output=True,text=True).stdout
   count=int(re.search(r'^Pages:\s+(\d+)',info,re.M)[1]);assert count>0
   pages+=count;pdfs+=1
   assert (R/s['text']).stat().st_size>100,s['id']+' extracted text'
print(f"PASS: archive hashes and sizes match; {pdfs} PDFs readable ({pages} pages); extracted text present.")
links=0
def checklink(url,source):
 global links
 u=urlsplit(url)
 if u.scheme or u.netloc:return
 target=(source.parent/unquote(u.path)) if u.path else source
 assert target.exists(),f'{source.name}: missing {url}'
 if u.fragment and target.name=='CONCEPTS.md':assert unquote(u.fragment) in N,url
 links+=1
for p in R.glob('*.md'):
 for url in re.findall(r'\]\(([^\n)]+)\)',p.read_text()):checklink(url,p)
class Links(HTMLParser):
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag in ('a','script','link'):
   url=attrs.get('href') or attrs.get('src')
   if url:checklink(url,R/'concept-graph.html')
h=(R/'concept-graph.html').read_text();Links().feed(h)
assert '__GRAPH_DATA__' not in h and '__SOURCE_DATA__' not in h
assert not re.search(r'<script[^>]+src=',h)
assert json.loads(re.search(r'<script type="application/json" id="graph-data">(.*?)</script>',h,re.S)[1])==G
assert json.loads(re.search(r'<script type="application/json" id="source-data">(.*?)</script>',h,re.S)[1])==S
print(f"PASS: {links} local document links/anchors checked; embedded explorer data matches graph and catalog; no external scripts.")
