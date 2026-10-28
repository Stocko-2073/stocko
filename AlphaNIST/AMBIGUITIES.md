# AlphaNIST unresolved evidence boundaries

These are the remaining questions after tracing the papers, appendices and public predecessor code. No item is labeled proprietary: publication or code absence alone does not establish proprietary ownership. Empirical limitations require experiments, not merely another definition.

## 1. Exact AlphaNIST reset-bank contents

M, per-task/per-family counts, generation seeds, pose/velocity distributions, saved fields, rejection thresholds and the bank files are absent. A descriptive family list cannot reconstruct the distribution.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2

**Closure requirement:** Publish the bank or deterministic generator, assets, configurations and seed list.

## 2. Exact adaptation from OmniReset and SGS

The paper does not say which grasp generator, near-goal force/path method, workspace bounds, family mixing, gravity curriculum or randomization settings were carried over. Predecessors disagree on several of these choices.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [SGS](papers/SGS-2610.12465.pdf) Appendices A.2 and B.4

**Closure requirement:** Release AlphaNIST reset and environment configs; distinguish inherited from changed components.

## 3. Sampler numerical and bookkeeping settings

AlphaNIST leaves L and εq numerical values unspecified and does not explain short histories, repeated concurrent entry outcomes, update ordering, or any hidden temperature/flooring. SGS defaults do not exactly reproduce AlphaNIST Eq. 4.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B, Algorithm 1; [SGS](papers/SGS-2610.12465.pdf) §3.2, Appendix B.2

**Closure requirement:** Release the sampler implementation and a tiny deterministic sampling test.

## 4. Global formula versus GPU-local banks

Eq. 4 normalizes over the entire bank, but IV-E says each GPU samples a local bank from local rolling estimates. Bank replication/sharding, cross-rank statistics and task balance are not specified. These choices can change the effective global distribution.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B and IV-E

**Closure requirement:** Publish rank-local bank mapping, update synchronization and normalization behavior.

## 5. Exact success distance and symmetry handling

d_asm is called a distance between relative poses and compared with 0.001 m, but its formula, keypoints, angle-to-length conversion, rotational symmetries and task-dependent equivalences are missing. For threads, depth, turn count and orientation acceptance cannot be reconstructed.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C, Eq. 5

**Closure requirement:** Publish the success predicate, goal transforms, units, symmetry groups and per-part examples.

## 6. Control-cost coefficient and units

The value of c, per-term normalization, action scaling, arm/finger inclusion, torque source and clamp rules are not reported. Mixing action, rad/s and Nm squared without this information leaves the numerical objective underdetermined.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 6; Fig. 3; IV-D

**Closure requirement:** Release the reward code/config and logged term magnitudes before and after scaling.

## 7. Reward timing and termination masks

Eq. 5 uses sₜ₊₁ while Eq. 6 lists t-indexed commands/speeds/torques. Per-physics-step versus policy-step aggregation, dt scaling, simultaneous-success precedence, reset masks and timeout bootstrap handling are unspecified.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; V

**Closure requirement:** Publish the environment step order, reward manager behavior and terminal/bootstrap flags.

## 8. Full PPO and optimization configuration

Numerical discount γ, GAE λ (or alternate estimator), clip ratio, value/entropy weights, optimizer parameters, learning-rate schedule, gradient clipping, reward/advantage normalization, initialization and timeout handling are absent. Standard PPO is a family of implementations.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E; [PPO](papers/PPO-1707.06347.pdf) §§3–6

**Closure requirement:** Release complete trainer config, library versions and checkpoint metadata.

## 9. Point-cloud construction and encoder aggregation

n_pts, sampling method, coordinate frame, visibility/occlusion, segmentation, noise, ordering/pooling and per-part allocation are unspecified. The two-layer figure does not uniquely define a permutation-invariant point encoder.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; IV-D

**Closure requirement:** Publish observation generation and encoder forward pass, with tensor-shape examples.

## 10. Proprioception packing and history

Listed feature counts sum to 30 while Fig. 3 says 150. Five-frame stacking is plausible but unconfirmed. Pose/twist frames, joint coordinate meanings, history timing, normalization updates and distributed statistics are not fully specified.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; III-A; IV-D

**Closure requirement:** Publish observation schema and normalization/history implementation.

## 11. Gaussian exploration and action processing

Covariance parameterization, initialization, variance sharing, temporal correlation, squashing/clipping and gripper mapping are missing. Gaussian output alone does not establish independent diagonal noise or gSDE. Evaluation is explicitly stochastic, but its exact distribution and postprocessing are not specified.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; IV-D; V

**Closure requirement:** Publish action-distribution and postprocessing code for training and stochastic evaluation.

## 12. Exact neural layer settings

ELU alpha, Swish beta, normalization epsilon/affine settings, parameter initialization and whether all encoder parameters are separate for actor/critic are not exhaustively enumerated. Figure 3 says separate parameters but does not provide executable architecture.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; [SimBa](papers/SimBa-2410.09754.pdf) §4

**Closure requirement:** Publish network constructors and serialized model architecture.

## 13. Controller gains and identified robot model

Exact stiffness/damping profiles, armature, joint friction, gripper mechanics, action scales, saturation, torque measurement and libfranka version are not given. Manufacturer docs establish interfaces, not the experiment’s chosen parameter vector.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D; [libfranka-control](sources/libfranka-control.html) setJointImpedance

**Closure requirement:** Publish robot asset/config, identified parameters, controller settings and identification data.

## 14. Physics versions, assets and numerical settings

AlphaNIST does not enumerate simulator/library commits, collision asset checksums, SDF resolution, contact offsets, friction/restitution, timestep/decimation, solver iteration count or all randomizations. PhysX/Newton background citations do not uniquely identify the experiment’s backend/configuration.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-A; IV-D; VI; [Factory](papers/Factory-2205.03532.pdf) III

**Closure requirement:** Release environment lockfile, asset manifests and full physics configuration.

## 15. Multi-pair observation and reset construction

The rule for sampling active task subsets, maintaining fixed point counts, representing inactive/completed parts, combining partial-assembly starts, collision-valid multi-part resets, and evaluation trial counts is not fully described. Table I alone does not establish full-from-table ten-part success.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; V-D; Table I

**Closure requirement:** Publish active-set sampling, scene/observation generation, reset banks and per-family evaluation.

## 16. Evaluation independence and uncertainty

Scaling evaluation defines a frozen mixed bank, but its separation from training banks, per-family sizes and seed-generation details are not stated. Fig. 7 uses five evaluation seeds, which must not be re-labeled five independent training runs. Table I lacks comparable uncertainty/trial details.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V; Figs. 5–7; Table I

**Closure requirement:** Publish train/test bank overlap checks, per-training-seed checkpoints, evaluation seeds and raw outcomes.

## 17. Why transfer and planning-like behavior emerge

The paper proposes an explanation for sparse-objective transfer but does not isolate the causal representation/skill mechanism or prove planning optimality. This is an open empirical explanation, not evidence of proprietary technology.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V-A and V-C–D

**Closure requirement:** Requires targeted ablations/representation tests or additional published evidence; existing descriptions cannot settle it.

## 18. AlphaNIST hardware and unseen-condition performance

No AlphaNIST hardware transfer result or full twenty-active-pair result is reported. Predecessor hardware success cannot fill this gap. Robustness to real perception, latency and contact mismatch remains unestablished.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) VI

**Closure requirement:** Requires new evaluations with sensor-derived observations and specified physical/held-out conditions.

## 19. Full compute accounting

GPU model, training-vs-reset-generation cost accounting, preprocessing overhead and wall-clock breakdown are not sufficiently specified to turn GPU-hours into reproducible runtime/cost estimates. Matching iterations also changes total interactions with environment count.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E; V-A

**Closure requirement:** Publish hardware, timing logs, preprocessing costs and interaction totals.

## 20. Cross-paper reward-coefficient discrepancy

AlphaNIST says its .01 reach/alignment coefficients match OmniReset. OmniReset v3 Appendix A.1 and inspected UWLab main list .1 reach/distance-related weights. Terms may also differ in scaling. The exact experimental correspondence remains unresolved.

**Checked:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V, Eq. 7; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.1; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) rl_state_cfg.py, reward config

**Closure requirement:** Publish version-specific ablation configs and clarify whether effective weights or term scales differ.
