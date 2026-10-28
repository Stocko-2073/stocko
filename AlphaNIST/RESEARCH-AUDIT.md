# Research scope and audit trail

Snapshot date: 14 October 2026. Root: AlphaNIST v1, arXiv:2610.13354v1. The task is to resolve its operational concepts and the supplied conversation’s questions, including dependencies delegated to other papers.

## Closure rule

A concept is closed for this graph when its meaning and role can be explained from primary evidence without an unnamed operational dependency. A branch stops at (1) a self-contained definition, (2) an already resolved shared concept, or (3) a missing detail with a named source search and a concrete requirement for resolution. Source disagreement is retained rather than averaged away. Experimental/causal questions that need new measurements are distinguished in their text from missing implementation values.

This is a finite explanatory graph, not proof that the literature contains no further ambiguity. A paper describing a predecessor is evidence for that predecessor; adoption by AlphaNIST requires separate evidence. Likewise, a public repository snapshot is not automatically the version used for a reported experiment.

## Recursive trails followed

| Starting question | Followed trail | Outcome |
|---|---|---|
| What makes diverse resets work? | AlphaNIST → OmniReset → reset inputs, four state families, grasp/near-goal sampling, feasibility checks and cached states | Explains coverage; AlphaNIST’s exact adaptation/bank remains absent |
| Where is the grasp recipe? | OmniReset’s ORBIT citation → ORBIT paper → public UWLab grasp sampler, configuration and author documentation | ORBIT does not supply the detailed recipe; current code exposes antipodal sampling, standoff/orientation search and physical validation |
| How are near-goal states made? | OmniReset → IndustReal lineage → UWLab partial-assembly sampler; compare SGS Appendix A.2 | Physical perturbation of completed assemblies differs from SGS’s parameterized assembly-path offsets; AlphaNIST adaptation unresolved |
| What changes the sampling distribution? | AlphaNIST Eq. 4 → SGS equations/defaults → SFL → ProCuRL; compare prioritized level replay and reverse curricula | Explicit formulas; temperature discrepancy; restricted assumptions behind theoretical learnability claims |
| What does sparse reward mean? | AlphaNIST success and costs → reward transformations/potential shaping → OmniReset reward table/config → DeepMind soccer Table S3 | Sparse positive reward versus dense penalties; missing c; coefficient comparison left unresolved |
| How does RL propagate competence? | PPO → GAE, Bellman/value targets → TRPO → conservative policy iteration → KL/entropy/optimization | Mathematical definitions supplied; no transfer of theoretical guarantees to arbitrary neural PPO |
| What is the architecture? | AlphaNIST Fig. 3 → SimBa → ResNet, running/layer normalization, activation papers → Adam | Published blocks defined; observation packing, point aggregation and several implementation values remain open |
| What controls contact? | AlphaNIST Panda interface → Isaac Lab/Gym and Factory → SDF, reduced contacts, iterative solvers, friction and timestep | Framework/physics concepts resolved; exact experiment configuration absent |
| What does “hardware matched” require? | OmniReset system identification → PACE → CMA-ES and identifiability; operational-space controller → Jacobian/wrench mapping | Predecessor procedure explained without attributing it wholesale to AlphaNIST |
| What would sim-to-real add? | OmniReset/SGS transfer → asymmetric actor–critic, gSDE, DextrAH-RGB → distillation, KL, DAgger, domain randomization | Separate predecessor transfer pipeline; AlphaNIST hardware result remains unestablished |
| Are there alternative assembly/multi-task methods? | AutoMate, Refinery, ARCH; PCGrad, PopArt and unitary scalarization | Comparison branches clearly separated from adopted mechanisms; Refinery’s Bayesian optimization/GMM expanded |
| What did the conversation imply? | Archived chat → corrected bipedal soccer paper; AlphaGo Zero motivation → self-play/tree search | Reward analogy verified; no unsupported claim that AlphaNIST performs MCTS or adversarial self-play |

## AlphaNIST reference disposition

This table accounts for all 29 root-paper references. “Context only” means it is cited as background rather than a mechanism needed to explain the reported AlphaNIST pipeline; those bibliographies were not recursively expanded. This distinction prevents representing an entire related-work field as an implemented dependency.

| Ref. | Source | Disposition |
|---|---|---|
| 1 | NIST assembly benchmarking protocols | Full article HTML archived; task/protocol concepts followed |
| 2 | Factory | PDF archived; contact physics followed |
| 3 | Assembly sequencing for arbitrary motions | Context only: classical assembly planning |
| 4 | Benchmarking off-the-shelf assembly solutions | Context only: prior benchmark performance |
| 5 | Compliance-enabled contact formations | Context only: alternative assembly engineering |
| 6 | Robust multi-modal policies with demonstrations | Context only: demonstration-based prior work |
| 7 | A Balanced Data Diet / SGS | PDF archived; sampling and reset details followed |
| 8 | AlphaGo (2016) | Context only; the explicit sparse/self-play motivation is examined through ref. 9 |
| 9 | AlphaGo Zero (2017) | PDF archived; self-play and tree-search concepts defined |
| 10 | OmniReset | PDF and public code archived; main reset dependency followed |
| 11 | Isaac Lab | PDF archived; simulation framework followed |
| 12 | mjlab | Context only: alternative simulator framework, not established AlphaNIST backend |
| 13 | Learning dexterous in-hand manipulation | Context only: sim-to-real precedent; domain-randomization concept followed separately |
| 14 | General in-hand object rotation with vision/touch | Context only: sensorimotor precedent |
| 15 | DextrAH-RGB | PDF archived; predecessor distillation branch followed |
| 16 | Dextreme | Context only: dexterous sim-to-real precedent |
| 17 | PhysX GPU documentation | Documentation snapshot archived; no assumed experiment version |
| 18 | Newton | Context only: engine example; citation does not establish AlphaNIST used it |
| 19 | Gradient surgery / PCGrad | PDF archived; comparison concept followed |
| 20 | AutoMate | PDF archived; assembly-by-disassembly/imitation distinction followed |
| 21 | Multi-task PopArt | PDF archived; followed to original PopArt normalization paper |
| 22 | Unitary scalarization | PDF archived; simple shared optimization comparison |
| 23 | Industrial insertion with visual inputs/natural rewards | Context only: earlier natural-reward assembly |
| 24 | Reverse curriculum generation | PDF archived; contrasted with static reset coverage/adaptive sampling |
| 25 | Refinery | PDF archived; initial-state optimization and its statistical concepts followed |
| 26 | ARCH | PDF archived; explicit hierarchical planning comparison |
| 27 | ResNet | PDF archived; residual connections followed |
| 28 | SimBa | PDF archived; architecture and normalizations followed |
| 29 | IndustReal | PDF archived; reset/reward/control lineage followed |

## Provenance and version limits

The paper corpus contains 40 validated PDF downloads, plus a full-article HTML copy of the NIST benchmark paper. The [index](PAPERS.md) links all downloaded sources and their concept uses. ArXiv revisions found inside PDF text are recorded separately from the requested download URL. SHA-256 hashes identify the exact downloaded bytes. Some citations in old papers point to earlier versions than the current downloaded revision; those should not be assumed identical. In particular, the archived PACE paper is an expanded journal revision.

The AlphaNIST and SGS project pages were checked and archived; their inspected snapshots announce forthcoming code. No released AlphaNIST implementation was located through those project links. This is a bounded search result, not a claim that no private or unindexed copy exists.

The UWLab ZIP’s commit comment matches the saved GitHub commit metadata: `2b40afb9693d46bc1b1a91c7ba95e03c04daa60d`, dated 2026-09-28. Selected grasp/reset/configuration/documentation files are extracted under [sources/code/UWLab-main](sources/code/UWLab-main). The complete ZIP is retained. Relevant paths include `events.py`, `reset_states_cfg.py`, `partial_assemblies_cfg.py`, `rl_state_cfg.py`, and the OmniReset `new_task.rst`/`rl_training.rst` documentation. Exact paths can be found with `rg --files sources/code`.

The shared conversation is preserved as both raw HTML and parsed messages. It includes the initial incorrect soccer-paper suggestion and the user’s correction. Chat claims were checked against the underlying papers; they do not count as primary evidence for implementation details.

PDF text extraction is an aid, not the source of record. RewardShaping and ConservativePolicyIteration needed OCR because their embedded text was garbled; the scanned OperationalSpaceControl paper also needed OCR. Equations and critical layout ambiguities were checked against rendered pages where needed, including AlphaNIST Figure 3, the reward-shaping theorem, and the operational-space kinematics/dynamics formulation. The graph does not claim that every page of every supporting PDF was visually inspected.

## Completion and verification boundaries

The graph has 165 unique nodes, 311 links, and 20 explicit evidence boundaries. All nodes are reachable from the root. Shared concepts create a directed acyclic graph; the Markdown tree uses cross-references to avoid repeating entire subtrees. All graph citations resolve to an archived source, and every undocumented node states what would close it. These structural properties are checked automatically.

The explorer is self-contained and has no remote scripts or runtime fetches. Local JavaScript checks exercise startup, all concepts, source listings, ambiguity views, search, node selection and expand/collapse. Browser visual inspection was blocked by tool security and approval policy: serving the project was rejected because the directory contains the shared conversation; local-file browser URLs were also rejected. No server was started and no workaround was used. The verification record therefore does not claim a browser rendering/accessibility audit.

No policies were trained, simulator experiments reproduced, or hardware results independently validated. No source was labeled proprietary merely because a detail was missing. The unresolved list is an evidence-based stopping boundary for this research pass, not proof of universal completeness.
