"""Enrich existing download manifests and generate the annotated paper index. No network."""
from pathlib import Path
import json,re
R=Path(__file__).resolve().parent.parent
titles={
'AlphaNIST':'AlphaNIST: Emergent Assembly Skills from Binary Task Rewards',
'OmniReset':'Emergent Dexterity via Diverse Resets and Large-Scale Reinforcement Learning',
'SGS':'A Balanced Data Diet: Addressing the Exploration Bottleneck in Mega-Scale RL for Robot Control',
'PPO':'Proximal Policy Optimization Algorithms',
'GAE':'High-Dimensional Continuous Control Using Generalized Advantage Estimation',
'TRPO':'Trust Region Policy Optimization',
'SimBa':'SimBa: Simplicity Bias for Scaling Up Parameters in Deep Reinforcement Learning',
'ResNet':'Deep Residual Learning for Image Recognition','LayerNorm':'Layer Normalization',
'Swish':'Searching for Activation Functions','ELU':'Fast and Accurate Deep Network Learning by Exponential Linear Units (ELUs)',
'Adam':'Adam: A Method for Stochastic Optimization',
'Factory':'Factory: Fast Contact for Robotic Assembly',
'IndustReal':'IndustReal: Transferring Contact-Rich Assembly Tasks from Simulation to Reality',
'ORBIT':'Orbit: A Unified Simulation Framework for Interactive Robot Learning Environments',
'IsaacLab':'Isaac Lab: A GPU-Accelerated Simulation Framework for Multi-Modal Robot Learning',
'IsaacGym':'Isaac Gym: High Performance GPU-Based Physics Simulation For Robot Learning',
'gSDE':'Smooth Exploration for Robotic Reinforcement Learning',
'AsymmetricActorCritic':'Asymmetric Actor Critic for Image-Based Robot Learning',
'DextrAH-RGB':'DextrAH-RGB: Visuomotor Policies to Grasp Anything with Dexterous Hands',
'ReverseCurriculum':'Reverse Curriculum Generation for Reinforcement Learning',
'AutoMate':'AutoMate: Specialist and Generalist Assembly Policies over Diverse Geometries',
'Refinery':'Refinery: Active Fine-Tuning and Deployment-Time Optimization for Contact-Rich Policies',
'ARCH':'ARCH: Hierarchical Hybrid Learning for Long-Horizon Contact-Rich Robotic Assembly',
'PCGrad':'Gradient Surgery for Multi-Task Learning',
'PopArtMultitask':'Multi-Task Deep Reinforcement Learning with PopArt',
'DeepMindSoccer':'Learning Agile Soccer Skills for a Bipedal Robot with Deep Reinforcement Learning',
'PACE':'Towards Bridging the Gap: Systematic Sim-to-Real Transfer for Diverse Legged Robots',
'CMAES':'The CMA Evolution Strategy: A Tutorial',
'ProCuRL':'Proximal Curriculum for Reinforcement Learning Agents',
'DAgger':'A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning',
'DomainRandomization':'Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World',
'SFL':'No Regrets: Investigating and Improving Regret Approximations for Curriculum Discovery',
'PLR':'Prioritized Level Replay','UnitaryScalarization':'In Defense of the Unitary Scalarization for Deep Multi-Task Learning',
'AlphaGoZero':'Mastering the Game of Go without Human Knowledge',
'PopArt':'Learning Values across Many Orders of Magnitude',
'RewardShaping':'Policy Invariance under Reward Transformations: Theory and Application to Reward Shaping',
'ConservativePolicyIteration':'Approximately Optimal Approximate Reinforcement Learning',
'OperationalSpaceControl':'A Unified Approach for Motion and Force Control of Robot Manipulators: The Operational Space Formulation',
'NIST-article':'Benchmarking Protocols for Evaluating Small Parts Robotic Assembly Systems',
'AlphaNIST-project':'AlphaNIST project page','SGS-project':'SGS project page',
'PhysX-GPU':'PhysX GPU simulation documentation','libfranka-control':'libfranka Robot control API',
'UWLab-commit':'UWLab pinned commit metadata',
}
reasons={
'AlphaNIST':'Root paper: read method, figures, results, limitations and references.',
'OmniReset':'Reset-generation dependency: method and appendices, including grasp generation, transfer, control and reward configuration.',
'SGS':'Adaptive-sampling dependency: equations, manipulation resets, defaults, evaluation and transfer appendices.',
'PPO':'Clipped surrogate, actor/critic optimization, entropy, and training procedure.',
'GAE':'Advantage estimation, temporal-difference residuals and bias/variance.',
'TRPO':'Trust-region/KL lineage of PPO; does not confer its guarantees on AlphaNIST.',
'SimBa':'Running normalization and residual MLP; distinguish original ReLU from AlphaNIST Swish.',
'Factory':'SDF contacts, contact reduction and solver; geometry and threading.',
'IndustReal':'Reset/curriculum lineage, SDF alignment rewards, sim-to-real action integration.',
'ORBIT':'OmniReset grasp-sampler citation; inspected framework description does not supply the exact grasp recipe. Public UWLab code supplies additional detail.',
'DeepMindSoccer':'Corrected conversation analogy; Methods and reward Table S3.',
'PACE':'OmniReset explicitly cites this identification procedure; current downloaded revision discusses identifiability and joint-trajectory fitting.',
'ProCuRL':'Followed SFL learnability claim to restricted theoretical settings and optimal-success assumption.',
'CMAES':'Derivative-free covariance-adapting search used in predecessor system identification.',
'RewardShaping':'Potential-based policy-invariance theorem; contrast with arbitrary distance/effort shaping. OCR text checked against rendered page.',
'ConservativePolicyIteration':'Policy-improvement and restart-distribution lineage. OCR used because original embedded text is garbled.',
'NIST-article':'Original benchmark/task-board definitions and protocol. Archived full article HTML; PDF retrieval failed.',
}
allrows=[]
for f in ('papers.json','support.json'):
 p=R/'sources'/f; rows=json.loads(p.read_text())
 for x in rows:
  if x['status']!='downloaded':continue
  x['title']=titles.get(x['id'],x['id']);x.setdefault('retrieved','2026-10-14')
  txt=R/'text'/f"{x['id']}.txt"
  if txt.exists() and x['path'].endswith('.pdf'):
   x['text']=str(txt.relative_to(R));content=txt.read_text()
   versions=re.findall(r'arXiv:\s*(\d{4}\.\d{4,5}v\d+)',content)
   if versions:
    x['pdf_version']=versions[0];x['version_url']='https://arxiv.org/pdf/'+versions[0]
   if x['id'] in ('RewardShaping','ConservativePolicyIteration','OperationalSpaceControl'):x['text_method']='Tesseract OCR; equations should be checked in original PDF'
  if x['id']=='PACE':x['version_note']='This is the current expanded journal revision, not necessarily the revision available when OmniReset ran its experiments.'
 p.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');allrows.extend(rows)
G=json.loads((R/'concept-graph.json').read_text())
out=['# Downloaded papers and primary evidence','','40 PDF papers plus the NIST full-article HTML, project/documentation snapshots, the shared conversation, and pinned predecessor code. Local files are the research snapshot retrieved 14 October 2026. See the manifests for SHA-256 hashes; versioned arXiv links are recorded when the PDF identifies its revision.','',
'Review depth: AlphaNIST and the operational OmniReset/SGS branches received method-and-appendix review. Other sources were read for the passages needed by the linked concepts; this index does not claim a cover-to-cover review of every paper.','',
'## Recommended reading order','','1. AlphaNIST IV–VI: identify what the root paper actually specifies.','2. OmniReset 3.1–3.3 and Appendix A: reset coverage and predecessor choices.','3. SGS 3.2, Appendices A/B/C: allocation, defaults and transfer differences.','4. Follow the concept links below for learning, geometry, contact, control, and comparisons.','']
for x in allrows:
 if x['status']!='downloaded':continue
 links=[f"[Local source]({x['path']})",f"[Original]({x.get('version_url',x['url'])})"]
 if x.get('text'):links.append(f"[Extracted text]({x['text']})")
 evidence=[]
 for n in G['nodes']:
  rr=[r['locator'] for r in n['evidence'] if r['source']==x['id']]
  if rr:evidence.append(f"[{n['title']}](CONCEPTS.md#{n['id']}) ({'; '.join(rr)})")
 out += [f"## {x['id']} — {x['title']}",'',' · '.join(links),'']
 out += [reasons.get(x['id'], 'Read for the concepts and source locations below.' if evidence else 'Supporting provenance/documentation snapshot.'),'']
 if x.get('pdf_version'):out += ['**PDF revision:** '+x['pdf_version']+'.','']
 if x.get('version_note'):out += [x['version_note'],'']
 if evidence:out += ['**Concept trail:** '+'; '.join(evidence)+'.','']
out += ['## Other archived evidence','', '[Shared conversation](sources/shared-conversation.json) ([original](https://chatgpt.com/share/6acf821c-d6f4-83e9-bf97-c5bad96593d9)); [raw HTML](sources/shared-conversation.html). The transcript is a question trail, not scientific authority.','',
'[UWLab code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst), pinned to commit `2b40afb9693d46bc1b1a91c7ba95e03c04daa60d` (2026-09-28). [Original pinned repository](https://github.com/UW-Lab/UWLab/tree/2b40afb9693d46bc1b1a91c7ba95e03c04daa60d); [downloaded ZIP](sources/UWLab-main.zip). This snapshot is not established as the exact experimental code revision.','',
'## Retrieval limitations','', 'The Sutton–Barto textbook download failed TLS verification and was not used as evidence. The NIST PDF endpoints returned access/challenge errors; its full article HTML is archived and cited instead. Failures remain recorded in [support.json](sources/support.json).','',
'[Paper manifest](sources/papers.json) · [Supporting-source manifest](sources/support.json) · [Research audit](RESEARCH-AUDIT.md)','']
(R/'PAPERS.md').write_text('\n'.join(out))
