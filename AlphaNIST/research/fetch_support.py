import pathlib,urllib.request,hashlib,json,subprocess,concurrent.futures
R=pathlib.Path(__file__).resolve().parent.parent
items=[
('SuttonBarto','https://www.incompleteideas.net/book/RLbook2020.pdf','pdf'),
('AlphaGoZero','https://discovery.ucl.ac.uk/id/eprint/10045895/1/agz_unformatted_nature.pdf','pdf'),
('PopArt','https://papers.neurips.cc/paper_files/paper/2016/file/5227b6aaf294f5f027273aebf16015f2-Paper.pdf','pdf'),
('NIST','https://europepmc.org/articles/PMC7537423?pdf=render','pdf'),
('RewardShaping','https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf','pdf'),
('ConservativePolicyIteration','https://homes.cs.washington.edu/~sham/papers/rl/aoarl.pdf','pdf'),
('OperationalSpaceControl','https://khatib.stanford.edu/publications/pdfs/Khatib_1987_RA.pdf','pdf'),
('AlphaNIST-project','https://alpha-nist.github.io/','html'),
('SGS-project','https://sgs-rl.github.io/','html'),
('PhysX-GPU','https://nvidia-omniverse.github.io/PhysX/physx/5.4.1/docs/GPURigidBodies.html','html'),
('UWLab-commit','https://api.github.com/repos/UW-Lab/UWLab/commits/main','json'),
('libfranka-control','https://frankarobotics.github.io/libfranka/0.15.0/classfranka_1_1Robot.html','html'),
('NIST-article','https://pmc.ncbi.nlm.nih.gov/articles/PMC7537423/','html')]
def go(it):
 name,url,ext=it;p=R/('papers' if ext=='pdf' else 'sources')/(name+'.'+ext)
 o=dict(id=name,url=url,path=str(p.relative_to(R)))
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=90) as r:b=r.read()
  if ext=='pdf' and not b.startswith(b'%PDF'):raise ValueError('Not a PDF')
  p.write_bytes(b);o.update(status='downloaded',bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if ext=='pdf':subprocess.run(['pdftotext','-layout',str(p),str(R/'text'/(name+'.txt'))],check=True,capture_output=True)
 except Exception as e:o.update(status='failed',error=str(e))
 print(name,o['status'],o.get('error',''),flush=True);return o
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as p: rows=list(p.map(go,items))
(R/'sources'/'support.json').write_text(json.dumps(rows,indent=2)+'\n')
