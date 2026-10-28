"""Download a declared primary-source corpus; save hashes and extracted PDF text."""
import concurrent.futures, hashlib, json, pathlib, subprocess, urllib.request, datetime
ROOT=pathlib.Path(__file__).resolve().parent.parent
PAPERS=[
('AlphaNIST','2610.13354v1','core'),('OmniReset','2603.15789v3','core'),('SGS','2610.12465','core'),
('PPO','1707.06347','foundation'),('GAE','1506.02438','foundation'),('TRPO','1502.05477','foundation'),
('SimBa','2410.09754','core'),('ResNet','1512.03385','foundation'),('LayerNorm','1607.06450','foundation'),('Swish','1710.05941','foundation'),('ELU','1511.07289','foundation'),('Adam','1412.6980','foundation'),
('Factory','2205.03532','physics'),('IndustReal','2305.17110','reset-and-transfer'),('ORBIT','2301.04195','reset-and-simulation'),('IsaacLab','2511.04831','simulation'),('IsaacGym','2108.10470','simulation'),
('gSDE','2005.05719','omnireset-only'),('AsymmetricActorCritic','1710.06542','omnireset-only'),('DextrAH-RGB','2412.01791','transfer-only'),
('ReverseCurriculum','1707.05300','related-reset'),('AutoMate','2407.08028','related-assembly'),('Refinery','2510.11019','related-assembly'),('ARCH','2409.16451','related-assembly'),
('PCGrad','2001.06782','related-multitask'),('PopArtMultitask','1809.04474','related-multitask'),('DeepMindSoccer','2304.13653','conversation-analogy')]
EXTRA=[('PACE','2509.06342','system-identification-lineage'),('CMAES','1604.00772','system-identification-foundation'),('ProCuRL','2304.12877','sampling-lineage'),('DAgger','1011.0686','distillation-foundation'),('DomainRandomization','1703.06907','transfer-foundation'),('SFL','2408.15099','sampling-lineage'),('PLR','2010.03934','sampling-comparison'),('UnitaryScalarization','2201.04122','related-multitask')]
def fetch(row):
 name,aid,role=row
 file=ROOT/'papers'/f'{name}-{aid}.pdf'; url=f'https://arxiv.org/pdf/{aid}'
 existing=list((ROOT/'papers').glob(f'{name}-*.pdf'))
 if not file.exists() and existing and name in ('OmniReset','SGS'): file=existing[0]
 result=dict(id=name,arxiv=aid,url=url,role=role,path=str(file.relative_to(ROOT)),retrieved=datetime.date.today().isoformat())
 try:
  if not file.exists():
   req=urllib.request.Request(url,headers={'User-Agent':'research-source-archive/1.0'})
   with urllib.request.urlopen(req,timeout=90) as r: data=r.read()
   if not data.startswith(b'%PDF-'):raise ValueError('Response is not PDF')
   file.write_bytes(data)
  data=file.read_bytes()
  result.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
  out=ROOT/'text'/f'{name}.txt'
  subprocess.run(['pdftotext','-layout',str(file),str(out)],check=True,capture_output=True)
  result['text']=str(out.relative_to(ROOT));result['status']='downloaded'
 except Exception as e:result.update(status='failed',error=str(e))
 print(name,result['status'],flush=True)
 return result
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(fetch,PAPERS+EXTRA))
 (ROOT/'sources'/'papers.json').write_text(json.dumps(rows,indent=2)+'\n')
