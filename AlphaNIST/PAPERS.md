# Downloaded papers and primary evidence

40 PDF papers plus the NIST full-article HTML, project/documentation snapshots, the shared conversation, and pinned predecessor code. Local files are the research snapshot retrieved 14 October 2026. See the manifests for SHA-256 hashes; versioned arXiv links are recorded when the PDF identifies its revision.

Review depth: AlphaNIST and the operational OmniReset/SGS branches received method-and-appendix review. Other sources were read for the passages needed by the linked concepts; this index does not claim a cover-to-cover review of every paper.

## Recommended reading order

1. AlphaNIST IV–VI: identify what the root paper actually specifies.
2. OmniReset 3.1–3.3 and Appendix A: reset coverage and predecessor choices.
3. SGS 3.2, Appendices A/B/C: allocation, defaults and transfer differences.
4. Follow the concept links below for learning, geometry, contact, control, and comparisons.

## AlphaNIST — AlphaNIST: Emergent Assembly Skills from Binary Task Rewards

[Local source](papers/AlphaNIST-2610.13354v1.pdf) · [Original](https://arxiv.org/pdf/2610.13354v1) · [Extracted text](text/AlphaNIST.txt)

Root paper: read method, figures, results, limitations and references.

**PDF revision:** 2610.13354v1.

**Concept trail:** [AlphaNIST](CONCEPTS.md#alphanist) (III–VI); [Task and mathematical problem](CONCEPTS.md#task) (III-A; IV-C; V-D); [Which states can training start from](CONCEPTS.md#resets) (IV-B); [Which available states get practiced](CONCEPTS.md#sampling) (Eq. 4; Algorithm 1); [What behavior the objective favors](CONCEPTS.md#reward) (IV-C, Eqs. 5–6); [How experience changes the policy](CONCEPTS.md#learning) (Algorithm 1; IV-E); [What the policy observes and computes](CONCEPTS.md#network) (Fig. 3; IV-D); [How a sampled action moves the robot](CONCEPTS.md#control) (IV-D); [What generates transitions](CONCEPTS.md#physics) (II-A; IV-D; VI); [What the reported evidence establishes](CONCEPTS.md#evaluation) (V–VI); [Related methods and conversation trails](CONCEPTS.md#context) (II); [NIST Assembly Task Board 1](CONCEPTS.md#nist) (I, Fig. 2); [Insertion, meshing, threading and clearance](CONCEPTS.md#assembly_geometry) (I); [Markov decision process](CONCEPTS.md#mdp) (III-A, Eqs. 1–2); [Simulator state versus configuration](CONCEPTS.md#state) (IV-B); [Policy action](CONCEPTS.md#action) (IV-D); [Probability, expectation and empirical frequency](CONCEPTS.md#probability) (III-A; IV-B); [Discounted finite-horizon return](CONCEPTS.md#return) (Eq. 2); [Partial observation and history](CONCEPTS.md#pomdp) (III-A, Fig. 3); [Rigid pose and coordinate frames](CONCEPTS.md#pose) (IV-C); [Translation and orientation error](CONCEPTS.md#rotation_distance) (IV-C); [Goal configuration and assembly coordinate](CONCEPTS.md#goal) (IV-C); [Shared learning across assembly pairs](CONCEPTS.md#multi_task) (III-A; IV-B; V-A); [Several pairs in one episode](CONCEPTS.md#multi_pair) (IV-C; V-D; Table I); [Cached states versus replayed trajectories](CONCEPTS.md#reset_cache) (Algorithm 1); [Assembly-indexed reset bank](CONCEPTS.md#reset_bank) (Eq. 3, IV-B); [Initial-state distribution is an inductive bias](CONCEPTS.md#reset_prior) (IV-B); [AlphaNIST sampling equation](CONCEPTS.md#alpha_sampler) (Eq. 4; Algorithm 1); [Rolling empirical success](CONCEPTS.md#success_history) (IV-B); [Bernoulli variance and learning heuristic](CONCEPTS.md#bernoulli) (Eq. 4); [Normalized categorical sampling](CONCEPTS.md#categorical) (Eq. 4); [Beta-shaped kernel is not a Bayesian posterior](CONCEPTS.md#beta) (Eq. 4); [Softmax temperature changes the kernel](CONCEPTS.md#temperature) (Eq. 4); [Published AlphaNIST and SGS formulas differ](CONCEPTS.md#sampler_difference) (Eq. 4); [Task frequency induced by reset weights](CONCEPTS.md#task_balance) (Eqs. 3–4; Algorithm 1); [Training distribution moves with the policy](CONCEPTS.md#adaptive_objective) (III-A; IV-B; V); [Terminal full-assembly reward](CONCEPTS.md#success) (Eq. 5; IV-C); [Dense action, speed and torque cost](CONCEPTS.md#control_cost) (Eq. 6); [Squared Euclidean norm](CONCEPTS.md#norm) (Eq. 6); [Torque penalty is not measured energy](CONCEPTS.md#energy) (Eq. 6); [Progress shaping and policy invariance](CONCEPTS.md#shaping) (Eq. 7); [The tested dense reward is one choice](CONCEPTS.md#dense_ablation) (V, Eq. 7); [Discount and the incentive to finish early](CONCEPTS.md#discount) (Eq. 2); [Success, timeout and unsafe termination](CONCEPTS.md#termination) (IV-C; V); [Actor, critic and advantage](CONCEPTS.md#value) (Fig. 3); [Proximal Policy Optimization](CONCEPTS.md#ppo) (IV-E); [Fresh rollouts and bounded data reuse](CONCEPTS.md#on_policy) (Algorithm 1); [Exploration entropy](CONCEPTS.md#entropy) (Fig. 3); [Synchronous distributed PPO](CONCEPTS.md#distributed) (IV-E); [Parallelism changes the optimization batch](CONCEPTS.md#batch_scale) (IV-E; V); [Geometry conditioning through point clouds](CONCEPTS.md#point_cloud) (III-A; IV-D; VI); [Point-cloud encoder specification](CONCEPTS.md#encoder) (Fig. 3); [Robot measurements and previous action](CONCEPTS.md#proprioception) (Fig. 3); [SimBa-style residual architecture](CONCEPTS.md#simba) (Fig. 3); [Running observation normalization](CONCEPTS.md#running_norm) (Fig. 3); [Residual connection](CONCEPTS.md#residual) (Fig. 3); [Swish activation](CONCEPTS.md#swish) (Fig. 3); [ELU activation](CONCEPTS.md#elu) (Fig. 3); [Gaussian action distribution](CONCEPTS.md#gaussian) (Fig. 3); [Panda embodiment](CONCEPTS.md#robot) (IV-D, Fig. 3); [Relative joint-position targets](CONCEPTS.md#joint_targets) (IV-D); [Joint impedance and implicit actuation](CONCEPTS.md#impedance) (IV-D); [Joint-speed and torque limits](CONCEPTS.md#limits) (IV-C–D); [System identification and drivetrain effects](CONCEPTS.md#system_id) (IV-D); [Driven and coupled finger](CONCEPTS.md#gripper) (IV-D); [Isaac Lab environment framework](CONCEPTS.md#isaaclab) (IV-D); [Factory contact simulation](CONCEPTS.md#factory) (II-A); [Physics step versus policy step](CONCEPTS.md#timestep) (IV-D); [Training success versus evaluation success](CONCEPTS.md#metrics) (V-A–B, Figs. 5–7); [Start distribution defines the test](CONCEPTS.md#reset_evaluation) (V; Fig. 7); [Reported sampling and scale ablation](CONCEPTS.md#scale) (V-B); [Interaction budget and GPU-hours](CONCEPTS.md#compute) (V-A); [One-to-ten pair results](CONCEPTS.md#multi_pair_result) (Table I; V-D; VI); [Observed dexterity and planning-like behavior](CONCEPTS.md#emergence) (V-C–D, Figs. 8–9); [What an ablation identifies](CONCEPTS.md#ablation) (IV-B; V); [Alternative assembly pipelines](CONCEPTS.md#related_assembly) (II-C); [Multi-task optimization alternatives](CONCEPTS.md#multitask_alternatives) (II-B); [PCGrad gradient projection](CONCEPTS.md#pcgrad) (II-B); [PopArt target normalization](CONCEPTS.md#popart) (II-B); [Predecessor sim-to-real pipeline](CONCEPTS.md#transfer) (VI); [Asymmetric actor-critic](CONCEPTS.md#asymmetric) (Fig. 3); [AlphaGo Zero is motivation, not the algorithm](CONCEPTS.md#alphago) (I; II-C); [Audit of the shared conversation](CONCEPTS.md#conversation) (IV-B–C); [Operational-space control](CONCEPTS.md#osc) (IV-D); [Exact AlphaNIST reset-bank contents](CONCEPTS.md#gap_bank) (IV-B); [Exact adaptation from OmniReset and SGS](CONCEPTS.md#gap_adaptation) (IV-B); [Sampler numerical and bookkeeping settings](CONCEPTS.md#gap_sampler) (IV-B, Algorithm 1); [Global formula versus GPU-local banks](CONCEPTS.md#gap_distributed_sampler) (IV-B and IV-E); [Exact success distance and symmetry handling](CONCEPTS.md#gap_metric) (IV-C, Eq. 5); [Control-cost coefficient and units](CONCEPTS.md#gap_cost) (Eq. 6; Fig. 3; IV-D); [Reward timing and termination masks](CONCEPTS.md#gap_reward_timing) (IV-C; V); [Full PPO and optimization configuration](CONCEPTS.md#gap_ppo) (IV-E); [Point-cloud construction and encoder aggregation](CONCEPTS.md#gap_encoder) (Fig. 3; IV-D); [Proprioception packing and history](CONCEPTS.md#gap_observation) (Fig. 3; III-A; IV-D); [Gaussian exploration and action processing](CONCEPTS.md#gap_noise) (Fig. 3; IV-D; V); [Exact neural layer settings](CONCEPTS.md#gap_network_details) (Fig. 3); [Controller gains and identified robot model](CONCEPTS.md#gap_controller) (IV-D); [Physics versions, assets and numerical settings](CONCEPTS.md#gap_simulator) (II-A; IV-D; VI); [Multi-pair observation and reset construction](CONCEPTS.md#gap_multi_pair) (IV-C; V-D; Table I); [Evaluation independence and uncertainty](CONCEPTS.md#gap_eval) (V; Figs. 5–7; Table I); [Why transfer and planning-like behavior emerge](CONCEPTS.md#gap_causality) (V-A and V-C–D); [AlphaNIST hardware and unseen-condition performance](CONCEPTS.md#gap_hardware) (VI); [Full compute accounting](CONCEPTS.md#gap_compute) (IV-E; V-A); [Cross-paper reward-coefficient discrepancy](CONCEPTS.md#gap_reward_comparison) (V, Eq. 7).

## OmniReset — Emergent Dexterity via Diverse Resets and Large-Scale Reinforcement Learning

[Local source](papers/OmniReset-2603.15789.pdf) · [Original](https://arxiv.org/pdf/2603.15789v3) · [Extracted text](text/OmniReset.txt)

Reset-generation dependency: method and appendices, including grasp generation, transfer, control and reward configuration.

**PDF revision:** 2603.15789v3.

**Concept trail:** [OmniReset reset generation](CONCEPTS.md#omnireset) (§§3.1–3.2); [Human-supplied reset priors](CONCEPTS.md#reset_inputs) (§3.1 Requirements 1–3); [Reaching resets](CONCEPTS.md#reaching) (§3.2); [Near-object resets](CONCEPTS.md#near_object) (§3.2); [Stable-grasp resets](CONCEPTS.md#stable_grasp) (§3.2); [Near-goal and partial-assembly resets](CONCEPTS.md#near_goal) (§3.2); [Offline partial-assembly generation](CONCEPTS.md#partial_assembly) (§3.2); [Grasp pose generation](CONCEPTS.md#grasp_sampling) (§3.2); [Reset physical feasibility](CONCEPTS.md#validation) (§3.2 Practical Implementation); [Cached states versus replayed trajectories](CONCEPTS.md#reset_cache) (§3.2); [Uniformity over states versus reset families](CONCEPTS.md#omni_sampling) (§3.2 Practical Implementation); [Initial-state distribution is an inductive bias](CONCEPTS.md#reset_prior) (§§3.1–3.2); [Coverage is finite and approximate](CONCEPTS.md#reset_support) (§3.2); [Reverse curriculum generation](CONCEPTS.md#reverse_curriculum) (§2); [Dense action, speed and torque cost](CONCEPTS.md#control_cost) (Appendix A.1); [The tested dense reward is one choice](CONCEPTS.md#dense_ablation) (Appendix A.1); [How skills can connect across reset states](CONCEPTS.md#credit) (§§3.2–3.3); [System identification and drivetrain effects](CONCEPTS.md#system_id) (Appendix A.3.2); [Friction model and combine rule](CONCEPTS.md#friction) (Appendix A.3.4); [Predecessor sim-to-real pipeline](CONCEPTS.md#transfer) (§5; Appendix A.3); [Asymmetric actor-critic](CONCEPTS.md#asymmetric) (§3.3, Appendix A.3.9); [Generalized state-dependent exploration](CONCEPTS.md#gsde) (§3.3); [Teacher-to-student policy distillation](CONCEPTS.md#distillation) (Appendix A.3.11); [DAgger data aggregation](CONCEPTS.md#dagger) (Appendix A.3.11); [ResNet visual encoder](CONCEPTS.md#resnet_student) (Appendix A.3.11); [Domain randomization](CONCEPTS.md#randomization) (Appendix A.3.7); [Curricula in predecessor transfer experiments](CONCEPTS.md#transfer_curriculum) (Appendix A.3.9); [Friction, distillation and seed-selection caveats](CONCEPTS.md#transfer_limits) (Appendix A.3.10–11); [Audit of the shared conversation](CONCEPTS.md#conversation) (§3.2); [PACE calibration pipeline](CONCEPTS.md#pace) (Appendix A.3.2); [Operational-space control](CONCEPTS.md#osc) (Appendix A.3.5–6); [Exact AlphaNIST reset-bank contents](CONCEPTS.md#gap_bank) (§3.2); [Exact adaptation from OmniReset and SGS](CONCEPTS.md#gap_adaptation) (§3.2); [Cross-paper reward-coefficient discrepancy](CONCEPTS.md#gap_reward_comparison) (Appendix A.1).

## SGS — A Balanced Data Diet: Addressing the Exploration Bottleneck in Mega-Scale RL for Robot Control

[Local source](papers/SGS-2610.12465.pdf) · [Original](https://arxiv.org/pdf/2610.12465v1) · [Extracted text](text/SGS.txt)

Adaptive-sampling dependency: equations, manipulation resets, defaults, evaluation and transfer appendices.

**PDF revision:** 2610.12465v1.

**Concept trail:** [Simulator state versus configuration](CONCEPTS.md#state) (§3.1); [Probability, expectation and empirical frequency](CONCEPTS.md#probability) (§3.2); [Ideal threaded assembly path](CONCEPTS.md#helix) (Appendix A.2); [Reaching resets](CONCEPTS.md#reaching) (Appendix A.2); [Near-object resets](CONCEPTS.md#near_object) (Appendix A.2); [Near-goal and partial-assembly resets](CONCEPTS.md#near_goal) (Appendix A.2); [Inverse kinematics](CONCEPTS.md#ik) (Appendix A.2); [Coverage is finite and approximate](CONCEPTS.md#reset_support) (Appendix B.3); [Rolling empirical success](CONCEPTS.md#success_history) (§3.2; Appendix B.2); [Normalized categorical sampling](CONCEPTS.md#categorical) (Eq. 2); [Beta-shaped kernel is not a Bayesian posterior](CONCEPTS.md#beta) (§3.2); [General SGS sampler](CONCEPTS.md#sgs) (§3.2, Eqs. 1–2; Appendix B.2); [Softmax temperature changes the kernel](CONCEPTS.md#temperature) (Eqs. 1–2; Appendix B.2); [Published AlphaNIST and SGS formulas differ](CONCEPTS.md#sampler_difference) (§3.2; Appendix B.2); [Sampling for Learnability lineage](CONCEPTS.md#sfl) (§2); [Prioritized Level Replay](CONCEPTS.md#plr) (§2); [Torque penalty is not measured energy](CONCEPTS.md#energy) (Appendix A.3.1, mechanical power); [Friction model and combine rule](CONCEPTS.md#friction) (Appendix C.2); [Physics step versus policy step](CONCEPTS.md#timestep) (Appendix A.2); [What an ablation identifies](CONCEPTS.md#ablation) (Appendix B.3); [Predecessor sim-to-real pipeline](CONCEPTS.md#transfer) (Appendix C); [Domain randomization](CONCEPTS.md#randomization) (Appendix C.2); [Curricula in predecessor transfer experiments](CONCEPTS.md#transfer_curriculum) (Appendix B.4); [Friction, distillation and seed-selection caveats](CONCEPTS.md#transfer_limits) (Appendix C.2–3); [Exact adaptation from OmniReset and SGS](CONCEPTS.md#gap_adaptation) (Appendices A.2 and B.4); [Sampler numerical and bookkeeping settings](CONCEPTS.md#gap_sampler) (§3.2, Appendix B.2).

## PPO — Proximal Policy Optimization Algorithms

[Local source](papers/PPO-1707.06347.pdf) · [Original](https://arxiv.org/pdf/1707.06347v2) · [Extracted text](text/PPO.txt)

Clipped surrogate, actor/critic optimization, entropy, and training procedure.

**PDF revision:** 1707.06347v2.

**Concept trail:** [How experience changes the policy](CONCEPTS.md#learning) (§§2–5); [Success, timeout and unsafe termination](CONCEPTS.md#termination) (§5); [Likelihood-ratio policy gradient](CONCEPTS.md#policy_gradient) (§2.1); [Proximal Policy Optimization](CONCEPTS.md#ppo) (§3 Eq. 7); [Action-probability ratio](CONCEPTS.md#importance) (§§2–3); [Fresh rollouts and bounded data reuse](CONCEPTS.md#on_policy) (§5, Algorithm 1); [Generalized Advantage Estimation](CONCEPTS.md#gae) (§5); [TRPO and conservative policy iteration](CONCEPTS.md#trpo) (§2.2); [Exploration entropy](CONCEPTS.md#entropy) (Eq. 9); [Minibatches, gradients and Adam](CONCEPTS.md#optimization) (§5); [Gaussian action distribution](CONCEPTS.md#gaussian) (§6); [Full PPO and optimization configuration](CONCEPTS.md#gap_ppo) (§§3–6).

## GAE — High-Dimensional Continuous Control Using Generalized Advantage Estimation

[Local source](papers/GAE-1506.02438.pdf) · [Original](https://arxiv.org/pdf/1506.02438v6) · [Extracted text](text/GAE.txt)

Advantage estimation, temporal-difference residuals and bias/variance.

**PDF revision:** 1506.02438v6.

**Concept trail:** [Discounted finite-horizon return](CONCEPTS.md#return) (§2); [Discount and the incentive to finish early](CONCEPTS.md#discount) (§2); [Actor, critic and advantage](CONCEPTS.md#value) (§2); [Bootstrapping and Bellman recursion](CONCEPTS.md#bellman) (§§2–3); [Likelihood-ratio policy gradient](CONCEPTS.md#policy_gradient) (§2); [Generalized Advantage Estimation](CONCEPTS.md#gae) (§3); [How skills can connect across reset states](CONCEPTS.md#credit) (§3).

## TRPO — Trust Region Policy Optimization

[Local source](papers/TRPO-1502.05477.pdf) · [Original](https://arxiv.org/pdf/1502.05477v5) · [Extracted text](text/TRPO.txt)

Trust-region/KL lineage of PPO; does not confer its guarantees on AlphaNIST.

**PDF revision:** 1502.05477v5.

**Concept trail:** [TRPO and conservative policy iteration](CONCEPTS.md#trpo) (§§3–4); [Kullback–Leibler divergence](CONCEPTS.md#kl) (§3).

## SimBa — SimBa: Simplicity Bias for Scaling Up Parameters in Deep Reinforcement Learning

[Local source](papers/SimBa-2410.09754.pdf) · [Original](https://arxiv.org/pdf/2410.09754v2) · [Extracted text](text/SimBa.txt)

Running normalization and residual MLP; distinguish original ReLU from AlphaNIST Swish.

**PDF revision:** 2410.09754v2.

**Concept trail:** [SimBa-style residual architecture](CONCEPTS.md#simba) (§4, Eqs. 3–7); [Running observation normalization](CONCEPTS.md#running_norm) (§4 Eqs. 3–4); [Layer normalization](CONCEPTS.md#layer_norm) (§4); [Residual connection](CONCEPTS.md#residual) (Eq. 6); [Exact neural layer settings](CONCEPTS.md#gap_network_details) (§4).

## ResNet — Deep Residual Learning for Image Recognition

[Local source](papers/ResNet-1512.03385.pdf) · [Original](https://arxiv.org/pdf/1512.03385v1) · [Extracted text](text/ResNet.txt)

Read for the concepts and source locations below.

**PDF revision:** 1512.03385v1.

**Concept trail:** [Residual connection](CONCEPTS.md#residual) (§3.2); [ResNet visual encoder](CONCEPTS.md#resnet_student) (§3).

## LayerNorm — Layer Normalization

[Local source](papers/LayerNorm-1607.06450.pdf) · [Original](https://arxiv.org/pdf/1607.06450v1) · [Extracted text](text/LayerNorm.txt)

Read for the concepts and source locations below.

**PDF revision:** 1607.06450v1.

**Concept trail:** [Layer normalization](CONCEPTS.md#layer_norm) (§3).

## Swish — Searching for Activation Functions

[Local source](papers/Swish-1710.05941.pdf) · [Original](https://arxiv.org/pdf/1710.05941v2) · [Extracted text](text/Swish.txt)

Read for the concepts and source locations below.

**PDF revision:** 1710.05941v2.

**Concept trail:** [Swish activation](CONCEPTS.md#swish) (§3).

## ELU — Fast and Accurate Deep Network Learning by Exponential Linear Units (ELUs)

[Local source](papers/ELU-1511.07289.pdf) · [Original](https://arxiv.org/pdf/1511.07289v5) · [Extracted text](text/ELU.txt)

Read for the concepts and source locations below.

**PDF revision:** 1511.07289v5.

**Concept trail:** [ELU activation](CONCEPTS.md#elu) (§2).

## Adam — Adam: A Method for Stochastic Optimization

[Local source](papers/Adam-1412.6980.pdf) · [Original](https://arxiv.org/pdf/1412.6980v9) · [Extracted text](text/Adam.txt)

Read for the concepts and source locations below.

**PDF revision:** 1412.6980v9.

**Concept trail:** [Minibatches, gradients and Adam](CONCEPTS.md#optimization) (Algorithm 1).

## Factory — Factory: Fast Contact for Robotic Assembly

[Local source](papers/Factory-2205.03532.pdf) · [Original](https://arxiv.org/pdf/2205.03532v1) · [Extracted text](text/Factory.txt)

SDF contacts, contact reduction and solver; geometry and threading.

**PDF revision:** 2205.03532v1.

**Concept trail:** [What generates transitions](CONCEPTS.md#physics) (III); [Insertion, meshing, threading and clearance](CONCEPTS.md#assembly_geometry) (II-A4, Fig. 2); [Ideal threaded assembly path](CONCEPTS.md#helix) (Fig. 2); [Factory contact simulation](CONCEPTS.md#factory) (§III); [Rigid-body dynamics](CONCEPTS.md#rigid_body) (II-A); [Nonpenetration and contact constraints](CONCEPTS.md#contact) (II-A; III); [Signed distance field](CONCEPTS.md#sdf) (II-A1; III-A); [Contact patch reduction](CONCEPTS.md#contact_reduction) (III-B–C); [Iterative contact solver](CONCEPTS.md#solver) (II-A3; III-B); [Physics versions, assets and numerical settings](CONCEPTS.md#gap_simulator) (III).

## IndustReal — IndustReal: Transferring Contact-Rich Assembly Tasks from Simulation to Reality

[Local source](papers/IndustReal-2305.17110.pdf) · [Original](https://arxiv.org/pdf/2305.17110v1) · [Extracted text](text/IndustReal.txt)

Reset/curriculum lineage, SDF alignment rewards, sim-to-real action integration.

**PDF revision:** 2305.17110v1.

**Concept trail:** [Translation and orientation error](CONCEPTS.md#rotation_distance) (§IV-F); [Offline partial-assembly generation](CONCEPTS.md#partial_assembly) (§IV-G); [Signed distance field](CONCEPTS.md#sdf) (IV-E–F); [IndustReal](CONCEPTS.md#industreal) (§IV-E–G; §V; Appendix on PLAI).

## ORBIT — Orbit: A Unified Simulation Framework for Interactive Robot Learning Environments

[Local source](papers/ORBIT-2301.04195.pdf) · [Original](https://arxiv.org/pdf/2301.04195v2) · [Extracted text](text/ORBIT.txt)

OmniReset grasp-sampler citation; inspected framework description does not supply the exact grasp recipe. Public UWLab code supplies additional detail.

**PDF revision:** 2301.04195v2.

**Concept trail:** [Grasp pose generation](CONCEPTS.md#grasp_sampling) (Fig. 8 and agent interfaces).

## IsaacLab — Isaac Lab: A GPU-Accelerated Simulation Framework for Multi-Modal Robot Learning

[Local source](papers/IsaacLab-2511.04831.pdf) · [Original](https://arxiv.org/pdf/2511.04831v1) · [Extracted text](text/IsaacLab.txt)

Read for the concepts and source locations below.

**PDF revision:** 2511.04831v1.

**Concept trail:** [Joint impedance and implicit actuation](CONCEPTS.md#impedance) (actuator modeling); [Isaac Lab environment framework](CONCEPTS.md#isaaclab) (framework overview and environment abstractions); [GPU-native parallel simulation lineage](CONCEPTS.md#isaacgym) (Introduction).

## IsaacGym — Isaac Gym: High Performance GPU-Based Physics Simulation For Robot Learning

[Local source](papers/IsaacGym-2108.10470.pdf) · [Original](https://arxiv.org/pdf/2108.10470v2) · [Extracted text](text/IsaacGym.txt)

Read for the concepts and source locations below.

**PDF revision:** 2108.10470v2.

**Concept trail:** [GPU-native parallel simulation lineage](CONCEPTS.md#isaacgym) (§3).

## gSDE — Smooth Exploration for Robotic Reinforcement Learning

[Local source](papers/gSDE-2005.05719.pdf) · [Original](https://arxiv.org/pdf/2005.05719v2) · [Extracted text](text/gSDE.txt)

Read for the concepts and source locations below.

**PDF revision:** 2005.05719v2.

**Concept trail:** [Generalized state-dependent exploration](CONCEPTS.md#gsde) (§§2.2–3).

## AsymmetricActorCritic — Asymmetric Actor Critic for Image-Based Robot Learning

[Local source](papers/AsymmetricActorCritic-1710.06542.pdf) · [Original](https://arxiv.org/pdf/1710.06542v1) · [Extracted text](text/AsymmetricActorCritic.txt)

Read for the concepts and source locations below.

**PDF revision:** 1710.06542v1.

**Concept trail:** [Partial observation and history](CONCEPTS.md#pomdp) (III); [Asymmetric actor-critic](CONCEPTS.md#asymmetric) (III).

## DextrAH-RGB — DextrAH-RGB: Visuomotor Policies to Grasp Anything with Dexterous Hands

[Local source](papers/DextrAH-RGB-2412.01791.pdf) · [Original](https://arxiv.org/pdf/2412.01791v2) · [Extracted text](text/DextrAH-RGB.txt)

Read for the concepts and source locations below.

**PDF revision:** 2412.01791v2.

**Concept trail:** [Kullback–Leibler divergence](CONCEPTS.md#kl) (§III-C); [Teacher-to-student policy distillation](CONCEPTS.md#distillation) (§III-C); [Behavior cloning and state-distribution shift](CONCEPTS.md#imitation) (§III-C); [DAgger data aggregation](CONCEPTS.md#dagger) (§III-C).

## ReverseCurriculum — Reverse Curriculum Generation for Reinforcement Learning

[Local source](papers/ReverseCurriculum-1707.05300.pdf) · [Original](https://arxiv.org/pdf/1707.05300v3) · [Extracted text](text/ReverseCurriculum.txt)

Read for the concepts and source locations below.

**PDF revision:** 1707.05300v3.

**Concept trail:** [Reverse curriculum generation](CONCEPTS.md#reverse_curriculum) (§4, Algorithm 1).

## AutoMate — AutoMate: Specialist and Generalist Assembly Policies over Diverse Geometries

[Local source](papers/AutoMate-2407.08028.pdf) · [Original](https://arxiv.org/pdf/2407.08028v2) · [Extracted text](text/AutoMate.txt)

Read for the concepts and source locations below.

**PDF revision:** 2407.08028v2.

**Concept trail:** [AutoMate assembly by disassembly](CONCEPTS.md#automate) (§§IV–VI); [Behavior cloning and state-distribution shift](CONCEPTS.md#imitation) (generalist learning).

## Refinery — Refinery: Active Fine-Tuning and Deployment-Time Optimization for Contact-Rich Policies

[Local source](papers/Refinery-2510.11019.pdf) · [Original](https://arxiv.org/pdf/2510.11019v1) · [Extracted text](text/Refinery.txt)

Read for the concepts and source locations below.

**PDF revision:** 2510.11019v1.

**Concept trail:** [Refinery active initialization](CONCEPTS.md#refinery) (Method, Fig. 1); [Bayesian optimization and acquisition functions](CONCEPTS.md#bayesopt) (§IV-A, Algorithm 1); [Gaussian-process surrogate](CONCEPTS.md#gaussian_process) (§IV-A); [Gaussian mixture model](CONCEPTS.md#gmm) (§IV-B, Algorithm 2).

## ARCH — ARCH: Hierarchical Hybrid Learning for Long-Horizon Contact-Rich Robotic Assembly

[Local source](papers/ARCH-2409.16451.pdf) · [Original](https://arxiv.org/pdf/2409.16451v2) · [Extracted text](text/ARCH.txt)

Read for the concepts and source locations below.

**PDF revision:** 2409.16451v2.

**Concept trail:** [ARCH explicit hierarchical assembly](CONCEPTS.md#arch) (Abstract; Method).

## PCGrad — Gradient Surgery for Multi-Task Learning

[Local source](papers/PCGrad-2001.06782.pdf) · [Original](https://arxiv.org/pdf/2001.06782v4) · [Extracted text](text/PCGrad.txt)

Read for the concepts and source locations below.

**PDF revision:** 2001.06782v4.

**Concept trail:** [PCGrad gradient projection](CONCEPTS.md#pcgrad) (§3, Algorithm 1).

## PopArtMultitask — Multi-Task Deep Reinforcement Learning with PopArt

[Local source](papers/PopArtMultitask-1809.04474.pdf) · [Original](https://arxiv.org/pdf/1809.04474v1) · [Extracted text](text/PopArtMultitask.txt)

Read for the concepts and source locations below.

**PDF revision:** 1809.04474v1.

**Concept trail:** [Term weighting versus numerical normalization](CONCEPTS.md#reward_scaling) (§2); [PopArt target normalization](CONCEPTS.md#popart) (§2).

## DeepMindSoccer — Learning Agile Soccer Skills for a Bipedal Robot with Deep Reinforcement Learning

[Local source](papers/DeepMindSoccer-2304.13653.pdf) · [Original](https://arxiv.org/pdf/2304.13653v2) · [Extracted text](text/DeepMindSoccer.txt)

Corrected conversation analogy; Methods and reward Table S3.

**PDF revision:** 2304.13653v2.

**Concept trail:** [Term weighting versus numerical normalization](CONCEPTS.md#reward_scaling) (Methods; Table S3); [DeepMind soccer and reward weights](CONCEPTS.md#soccer) (Methods; Supplementary Table S3).

## PACE — Towards Bridging the Gap: Systematic Sim-to-Real Transfer for Diverse Legged Robots

[Local source](papers/PACE-2509.06342.pdf) · [Original](https://arxiv.org/pdf/2509.06342v2) · [Extracted text](text/PACE.txt)

OmniReset explicitly cites this identification procedure; current downloaded revision discusses identifiability and joint-trajectory fitting.

**PDF revision:** 2509.06342v2.

This is the current expanded journal revision, not necessarily the revision available when OmniReset ran its experiments.

**Concept trail:** [PACE calibration pipeline](CONCEPTS.md#pace) (§2, Eqs. 3–7); [Covariance matrix adaptation evolution strategy](CONCEPTS.md#cmaes) (Eq. 4); [Parameter identifiability](CONCEPTS.md#identifiability) (§2, Eqs. 6–7).

## CMAES — The CMA Evolution Strategy: A Tutorial

[Local source](papers/CMAES-1604.00772.pdf) · [Original](https://arxiv.org/pdf/1604.00772v2) · [Extracted text](text/CMAES.txt)

Derivative-free covariance-adapting search used in predecessor system identification.

**PDF revision:** 1604.00772v2.

**Concept trail:** [Covariance matrix adaptation evolution strategy](CONCEPTS.md#cmaes) (§§1–3).

## ProCuRL — Proximal Curriculum for Reinforcement Learning Agents

[Local source](papers/ProCuRL-2304.12877.pdf) · [Original](https://arxiv.org/pdf/2304.12877v1) · [Extracted text](text/ProCuRL.txt)

Followed SFL learnability claim to restricted theoretical settings and optimal-success assumption.

**PDF revision:** 2304.12877v1.

**Concept trail:** [ProCuRL and the limits of learnability theory](CONCEPTS.md#procurl) (§§3.1–3.2).

## DAgger — A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning

[Local source](papers/DAgger-1011.0686.pdf) · [Original](https://arxiv.org/pdf/1011.0686v3) · [Extracted text](text/DAgger.txt)

Read for the concepts and source locations below.

**PDF revision:** 1011.0686v3.

**Concept trail:** [DAgger data aggregation](CONCEPTS.md#dagger) (§3, Algorithm 3.1).

## DomainRandomization — Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World

[Local source](papers/DomainRandomization-1703.06907.pdf) · [Original](https://arxiv.org/pdf/1703.06907v1) · [Extracted text](text/DomainRandomization.txt)

Read for the concepts and source locations below.

**PDF revision:** 1703.06907v1.

**Concept trail:** [Domain randomization](CONCEPTS.md#randomization) (§3).

## SFL — No Regrets: Investigating and Improving Regret Approximations for Curriculum Discovery

[Local source](papers/SFL-2408.15099.pdf) · [Original](https://arxiv.org/pdf/2408.15099v3) · [Extracted text](text/SFL.txt)

Read for the concepts and source locations below.

**PDF revision:** 2408.15099v3.

**Concept trail:** [Bernoulli variance and learning heuristic](CONCEPTS.md#bernoulli) (§4); [Sampling for Learnability lineage](CONCEPTS.md#sfl) (§4, Algorithm 1); [ProCuRL and the limits of learnability theory](CONCEPTS.md#procurl) (§4).

## PLR — Prioritized Level Replay

[Local source](papers/PLR-2010.03934.pdf) · [Original](https://arxiv.org/pdf/2010.03934v4) · [Extracted text](text/PLR.txt)

Read for the concepts and source locations below.

**PDF revision:** 2010.03934v4.

**Concept trail:** [Prioritized Level Replay](CONCEPTS.md#plr) (§3, Algorithms 1–2).

## UnitaryScalarization — In Defense of the Unitary Scalarization for Deep Multi-Task Learning

[Local source](papers/UnitaryScalarization-2201.04122.pdf) · [Original](https://arxiv.org/pdf/2201.04122v4) · [Extracted text](text/UnitaryScalarization.txt)

Read for the concepts and source locations below.

**PDF revision:** 2201.04122v4.

**Concept trail:** [Ordinary scalarized multi-task training](CONCEPTS.md#unitary) (Abstract; experimental conclusions).

## AlphaGoZero — Mastering the Game of Go without Human Knowledge

[Local source](papers/AlphaGoZero.pdf) · [Original](https://discovery.ucl.ac.uk/id/eprint/10045895/1/agz_unformatted_nature.pdf) · [Extracted text](text/AlphaGoZero.txt)

Read for the concepts and source locations below.

**Concept trail:** [AlphaGo Zero is motivation, not the algorithm](CONCEPTS.md#alphago) (self-play learning); [Monte Carlo tree search](CONCEPTS.md#mcts) (Methods: Search algorithm); [Self-play learning](CONCEPTS.md#selfplay) (Methods: Self-play reinforcement learning).

## PopArt — Learning Values across Many Orders of Magnitude

[Local source](papers/PopArt.pdf) · [Original](https://papers.neurips.cc/paper_files/paper/2016/file/5227b6aaf294f5f027273aebf16015f2-Paper.pdf) · [Extracted text](text/PopArt.txt)

Read for the concepts and source locations below.

**Concept trail:** [PopArt target normalization](CONCEPTS.md#popart) (§2).

## RewardShaping — Policy Invariance under Reward Transformations: Theory and Application to Reward Shaping

[Local source](papers/RewardShaping.pdf) · [Original](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf) · [Extracted text](text/RewardShaping.txt)

Potential-based policy-invariance theorem; contrast with arbitrary distance/effort shaping. OCR text checked against rendered page.

**Concept trail:** [Term weighting versus numerical normalization](CONCEPTS.md#reward_scaling) (§§2–3); [Progress shaping and policy invariance](CONCEPTS.md#shaping) (Theorem 1); [Why shaping boundary conditions matter](CONCEPTS.md#potential_terminal) (Theorem 1 and proof).

## ConservativePolicyIteration — Approximately Optimal Approximate Reinforcement Learning

[Local source](papers/ConservativePolicyIteration.pdf) · [Original](https://homes.cs.washington.edu/~sham/papers/rl/aoarl.pdf) · [Extracted text](text/ConservativePolicyIteration.txt)

Policy-improvement and restart-distribution lineage. OCR used because original embedded text is garbled.

**Concept trail:** [Markov decision process](CONCEPTS.md#mdp) (§2); [Bootstrapping and Bellman recursion](CONCEPTS.md#bellman) (§2); [TRPO and conservative policy iteration](CONCEPTS.md#trpo) (§§3–4).

## OperationalSpaceControl — A Unified Approach for Motion and Force Control of Robot Manipulators: The Operational Space Formulation

[Local source](papers/OperationalSpaceControl.pdf) · [Original](https://khatib.stanford.edu/publications/pdfs/Khatib_1987_RA.pdf) · [Extracted text](text/OperationalSpaceControl.txt)

Read for the concepts and source locations below.

**Concept trail:** [Rigid-body dynamics](CONCEPTS.md#rigid_body) (dynamic modeling); [Operational-space control](CONCEPTS.md#osc) (operational-space formulation); [Kinematic Jacobian and wrench mapping](CONCEPTS.md#jacobian) (kinematics and dynamic formulation).

## AlphaNIST-project — AlphaNIST project page

[Local source](sources/AlphaNIST-project.html) · [Original](https://alpha-nist.github.io/)

Supporting provenance/documentation snapshot.

## SGS-project — SGS project page

[Local source](sources/SGS-project.html) · [Original](https://sgs-rl.github.io/)

Supporting provenance/documentation snapshot.

## PhysX-GPU — PhysX GPU simulation documentation

[Local source](sources/PhysX-GPU.html) · [Original](https://nvidia-omniverse.github.io/PhysX/physx/5.4.1/docs/GPURigidBodies.html)

Supporting provenance/documentation snapshot.

## UWLab-commit — UWLab pinned commit metadata

[Local source](sources/UWLab-commit.json) · [Original](https://api.github.com/repos/UW-Lab/UWLab/commits/main)

Supporting provenance/documentation snapshot.

## libfranka-control — libfranka Robot control API

[Local source](sources/libfranka-control.html) · [Original](https://frankarobotics.github.io/libfranka/0.15.0/classfranka_1_1Robot.html)

Read for the concepts and source locations below.

**Concept trail:** [Joint impedance and implicit actuation](CONCEPTS.md#impedance) (setJointImpedance documentation); [Controller gains and identified robot model](CONCEPTS.md#gap_controller) (setJointImpedance).

## NIST-article — Benchmarking Protocols for Evaluating Small Parts Robotic Assembly Systems

[Local source](sources/NIST-article.html) · [Original](https://pmc.ncbi.nlm.nih.gov/articles/PMC7537423/)

Original benchmark/task-board definitions and protocol. Archived full article HTML; PDF retrieval failed.

**Concept trail:** [NIST Assembly Task Board 1](CONCEPTS.md#nist) (Task Board Design; Performance Metrics).

## Other archived evidence

[Shared conversation](sources/shared-conversation.json) ([original](https://chatgpt.com/share/6acf821c-d6f4-83e9-bf97-c5bad96593d9)); [raw HTML](sources/shared-conversation.html). The transcript is a question trail, not scientific authority.

[UWLab code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst), pinned to commit `2b40afb9693d46bc1b1a91c7ba95e03c04daa60d` (2026-09-28). [Original pinned repository](https://github.com/UW-Lab/UWLab/tree/2b40afb9693d46bc1b1a91c7ba95e03c04daa60d); [downloaded ZIP](sources/UWLab-main.zip). This snapshot is not established as the exact experimental code revision.

## Retrieval limitations

The Sutton–Barto textbook download failed TLS verification and was not used as evidence. The NIST PDF endpoints returned access/challenge errors; its full article HTML is archived and cited instead. Failures remain recorded in [support.json](sources/support.json).

[Paper manifest](sources/papers.json) · [Supporting-source manifest](sources/support.json) · [Research audit](RESEARCH-AUDIT.md)
