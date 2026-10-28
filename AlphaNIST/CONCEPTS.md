# AlphaNIST concept definitions

Operational concepts required to explain the reported AlphaNIST method; predecessor mechanisms, relevant comparisons and foundational definitions. Not a transitive crawl of every cited paper in all of robotics.

Statuses describe evidence, not certainty of successful reproduction. Undocumented leaves name what would resolve them.

<a id="alphanist"></a>
## AlphaNIST

**documented · core**

A simulated assembly learning system combining heterogeneous tasks, a cached reset distribution adapted from OmniReset, adaptive success-based sampling, a shared geometry-conditioned actor and critic, a terminal assembly objective plus control penalties, and synchronous PPO. Each branch below separates its published mechanism from missing implementation particulars.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III–VI

**Follow:** [Task and mathematical problem](#task), [Which states can training start from](#resets), [Which available states get practiced](#sampling), [What behavior the objective favors](#reward), [How experience changes the policy](#learning), [What the policy observes and computes](#network), [How a sampled action moves the robot](#control), [What generates transitions](#physics), [What the reported evidence establishes](#evaluation), [Related methods and conversation trails](#context)

<a id="task"></a>
## Task and mathematical problem

**documented · core**

One policy is trained across twenty assembly-pair tasks; multiple-pair experiments train separate policies for each active-pair count. The simulator state, policy observation, objective, and reset distribution are different objects.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A; IV-C; V-D

**Follow:** [NIST Assembly Task Board 1](#nist), [Markov decision process](#mdp), [Partial observation and history](#pomdp), [Goal configuration and assembly coordinate](#goal), [Shared learning across assembly pairs](#multi_task), [Several pairs in one episode](#multi_pair)

<a id="resets"></a>
## Which states can training start from

**documented · core**

A bank stores assembly identity and simulator state. Reset coverage creates opportunities to learn contacts, grasps, transport, and completion without supplying the actions connecting those states. Sampling cannot create missing bank entries.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B

**Follow:** [OmniReset reset generation](#omnireset), [Assembly-indexed reset bank](#reset_bank), [Initial-state distribution is an inductive bias](#reset_prior), [Coverage is finite and approximate](#reset_support), [Exact AlphaNIST reset-bank contents](#gap_bank), [Exact adaptation from OmniReset and SGS](#gap_adaptation)

<a id="sampling"></a>
## Which available states get practiced

**documented · core**

Each cached assembly–reset entry has a rolling success estimate. AlphaNIST weights intermediate success rates most highly and retains a positive floor for every entry. This changes the episode-start distribution over tasks as well as states.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4; Algorithm 1

**Follow:** [AlphaNIST sampling equation](#alpha_sampler), [Rolling empirical success](#success_history), [Normalized categorical sampling](#categorical), [Beta-shaped kernel is not a Bayesian posterior](#beta), [General SGS sampler](#sgs), [Task frequency induced by reset weights](#task_balance), [Training distribution moves with the policy](#adaptive_objective), [Sampler numerical and bookkeeping settings](#gap_sampler), [Global formula versus GPU-local banks](#gap_distributed_sampler)

<a id="reward"></a>
## What behavior the objective favors

**documented · core**

The positive task reward is sparse and binary; the complete reward includes dense control penalties. The success predicate and penalty scaling are essential to interpreting or reproducing the objective.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C, Eqs. 5–6

**Follow:** [Terminal full-assembly reward](#success), [Dense action, speed and torque cost](#control_cost), [Term weighting versus numerical normalization](#reward_scaling), [Progress shaping and policy invariance](#shaping), [Discount and the incentive to finish early](#discount), [Success, timeout and unsafe termination](#termination), [Exact success distance and symmetry handling](#gap_metric), [Control-cost coefficient and units](#gap_cost), [Reward timing and termination masks](#gap_reward_timing)

<a id="learning"></a>
## How experience changes the policy

**documented · core**

PPO uses freshly collected policy rollouts to update an actor and value estimator. Value learning and function approximation can connect competence across nearby reset states, but do not guarantee a path between them.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Algorithm 1; IV-E; [PPO](papers/PPO-1707.06347.pdf) §§2–5

**Follow:** [Likelihood-ratio policy gradient](#policy_gradient), [Proximal Policy Optimization](#ppo), [Actor, critic and advantage](#value), [Bootstrapping and Bellman recursion](#bellman), [Generalized Advantage Estimation](#gae), [Minibatches, gradients and Adam](#optimization), [Synchronous distributed PPO](#distributed), [How skills can connect across reset states](#credit), [Full PPO and optimization configuration](#gap_ppo)

<a id="network"></a>
## What the policy observes and computes

**documented · core**

Separate actor and critic parameters use the same illustrated architecture: point-cloud embedding concatenated with normalized proprioception/action input, followed by two SimBa-style residual blocks. The actor outputs eight action coordinates; the critic a scalar value.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; IV-D

**Follow:** [Geometry conditioning through point clouds](#point_cloud), [Robot measurements and previous action](#proprioception), [SimBa-style residual architecture](#simba), [Gaussian action distribution](#gaussian), [Point-cloud construction and encoder aggregation](#gap_encoder), [Proprioception packing and history](#gap_observation), [Gaussian exploration and action processing](#gap_noise)

<a id="control"></a>
## How a sampled action moves the robot

**documented · core**

At 25 Hz, seven relative joint-position commands and a gripper command feed a hardware-matched simulated Panda. A low-level implicit impedance controller determines motion and contact response.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D

**Follow:** [Panda embodiment](#robot), [Relative joint-position targets](#joint_targets), [Joint impedance and implicit actuation](#impedance), [Joint-speed and torque limits](#limits), [System identification and drivetrain effects](#system_id), [Driven and coupled finger](#gripper), [Controller gains and identified robot model](#gap_controller)

<a id="physics"></a>
## What generates transitions

**documented · core**

Isaac Lab hosts GPU-parallel physics environments. Contact representation, friction, integration, and solver settings determine the dynamics that RL optimizes against; hardware limits alone do not establish simulator fidelity.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-A; IV-D; VI; [Factory](papers/Factory-2205.03532.pdf) III

**Follow:** [Isaac Lab environment framework](#isaaclab), [GPU-native parallel simulation lineage](#isaacgym), [Factory contact simulation](#factory), [Rigid-body dynamics](#rigid_body), [Signed distance field](#sdf), [Friction model and combine rule](#friction), [Iterative contact solver](#solver), [Physics step versus policy step](#timestep), [Physics versions, assets and numerical settings](#gap_simulator)

<a id="evaluation"></a>
## What the reported evidence establishes

**documented · core**

Results are task- and distribution-specific measurements in simulation. They establish strong performance within the tested setup, not unseen-geometry generalization, hardware reliability, or complete twenty-part sequences.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V–VI

**Follow:** [Training success versus evaluation success](#metrics), [Start distribution defines the test](#reset_evaluation), [Reported sampling and scale ablation](#scale), [Interaction budget and GPU-hours](#compute), [One-to-ten pair results](#multi_pair_result), [Observed dexterity and planning-like behavior](#emergence), [What an ablation identifies](#ablation), [Evaluation independence and uncertainty](#gap_eval), [Why transfer and planning-like behavior emerge](#gap_causality), [AlphaNIST hardware and unseen-condition performance](#gap_hardware)

<a id="context"></a>
## Related methods and conversation trails

**documented · comparison**

These branches explain comparisons and borrowed concepts. They are not an assertion that every referenced method is implemented inside AlphaNIST.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II

**Follow:** [Alternative assembly pipelines](#related_assembly), [Multi-task optimization alternatives](#multitask_alternatives), [Predecessor sim-to-real pipeline](#transfer), [AlphaGo Zero is motivation, not the algorithm](#alphago), [DeepMind soccer and reward weights](#soccer), [Audit of the shared conversation](#conversation)

<a id="nist"></a>
## NIST Assembly Task Board 1

**documented · core**

The benchmark includes nuts and bolts, gears and shafts, rods/pegs and holes, and electrical connectors. AlphaNIST uses twenty movable-part/mating-geometry pairs. Physical NIST benchmarking also measures completion time, reliability, and test conditions; a simulated mixed-reset success rate is a different protocol.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) I, Fig. 2; [NIST-article](sources/NIST-article.html) Task Board Design; Performance Metrics

**Follow:** [Insertion, meshing, threading and clearance](#assembly_geometry)

<a id="assembly_geometry"></a>
## Insertion, meshing, threading and clearance

**documented · foundation**

Insertion fits one body into a receptacle; gear meshing additionally aligns teeth; threading couples axial advancement with rotation. Clearance is the geometric gap permitting motion. Realistic rigid-body threading still has six-dimensional relative motion and can tilt, jam or cross-thread; it is not necessarily constrained to an ideal helix.

**Evidence:** [Factory](papers/Factory-2205.03532.pdf) II-A4, Fig. 2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) I

**Follow:** [Rigid pose and coordinate frames](#pose), [Nonpenetration and contact constraints](#contact), [Ideal threaded assembly path](#helix)

<a id="mdp"></a>
## Markov decision process

**documented · foundation**

The model contains states S, actions A, transition law p(s′|s,a), reward r, discount γ, horizon T and initial distribution ρ. Markov means the current state contains the information needed for next-state probabilities. In a finite-horizon problem the remaining time can be treated as part of state.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A, Eqs. 1–2; [ConservativePolicyIteration](papers/ConservativePolicyIteration.pdf) §2

**Follow:** [Simulator state versus configuration](#state), [Policy action](#action), [Probability, expectation and empirical frequency](#probability), [Discounted finite-horizon return](#return)

<a id="state"></a>
## Simulator state versus configuration

**documented · foundation**

A simulator state includes positions, orientations and velocities, robot joint state, and relevant physical or task variables. A pose alone is not the full dynamic state. A reset configuration specifies the state and context restored at episode start.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; [SGS](papers/SGS-2610.12465.pdf) §3.1

**Follow:** [Rigid pose and coordinate frames](#pose)

<a id="action"></a>
## Policy action

**documented · foundation**

An action is the control-interface command, not necessarily a physical torque. Here the eight-dimensional policy output describes seven arm-position increments and one gripper command; controller dynamics turn these into motion.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D

<a id="probability"></a>
## Probability, expectation and empirical frequency

**documented · foundation**

A probability lies in [0,1]. Expectation averages outcomes under a stated distribution. For Boolean outcomes y₁,…,yₙ, empirical success is Σy/n and estimates, but is not identical to, the current policy’s true success probability.

**Evidence:** [SGS](papers/SGS-2610.12465.pdf) §3.2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A; IV-B

<a id="return"></a>
## Discounted finite-horizon return

**documented · foundation**

Gₜ = Σₖ γᵏ rₜ₊ₖ until termination/horizon; the objective averages this return across starting states, transitions and sampled actions. With control costs, the objective is not just probability of successful assembly.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 2; [GAE](papers/GAE-1506.02438.pdf) §2

**Follow:** [Discount and the incentive to finish early](#discount)

<a id="pomdp"></a>
## Partial observation and history

**documented · foundation**

The policy sees oₜ rather than the entire simulator state. Different hidden states may produce the same observation, so a memoryless policy need not be optimal. Stacked observations may reduce this aliasing without guaranteeing full observability. AlphaNIST states partial observations but leaves temporal packing unclear.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A, Fig. 3; [AsymmetricActorCritic](papers/AsymmetricActorCritic-1710.06542.pdf) III

**Follow:** [Proprioception packing and history](#gap_observation)

<a id="pose"></a>
## Rigid pose and coordinate frames

**documented · foundation**

A rigid pose is translation x∈R³ and rotation R∈SO(3), represented by a homogeneous transform T=[R x;0 1]. Object pose in the mating frame is T_mating⁻¹T_object. Quaternions represent rotation, with q and −q representing the same orientation; ordering conventions must be explicit.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) docs/source/publications/omnireset/new_task.rst, Steps 1 and 4

**Follow:** [Translation and orientation error](#rotation_distance)

<a id="rotation_distance"></a>
## Translation and orientation error

**documented · foundation**

Translation error has length units; an angular error can be computed from the relative rotation, for example acos(clamp((tr(R_goalᵀR)−1)/2,−1,1)). This is a generic definition, not AlphaNIST’s unpublished metric. Combining angle and length requires a convention or a geometry-based distance.

**Evidence:** [IndustReal](papers/IndustReal-2305.17110.pdf) §IV-F; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C

**Follow:** [Exact success distance and symmetry handling](#gap_metric)

<a id="helix"></a>
## Ideal threaded assembly path

**documented · foundation**

For pitch h, ideal axial displacement and rotation obey z−z₀=hθ/(2π). A path generator can use this relation to propose near-goal poses; the physical simulation still solves contact and permits off-path states. AlphaNIST does not publish its per-part path functions.

**Evidence:** [SGS](papers/SGS-2610.12465.pdf) Appendix A.2; [Factory](papers/Factory-2205.03532.pdf) Fig. 2

**Follow:** [Exact adaptation from OmniReset and SGS](#gap_adaptation)

<a id="goal"></a>
## Goal configuration and assembly coordinate

**documented · core**

For task e, Φₑ(α), α∈[0,1], parameterizes an assembly-relative configuration, with Φₑ(1) fully assembled. This supplies privileged geometric goal knowledge; it is neither a demonstrated action sequence nor the policy’s discrete task input.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C

**Follow:** [Rigid pose and coordinate frames](#pose), [Exact success distance and symmetry handling](#gap_metric), [Exact adaptation from OmniReset and SGS](#gap_adaptation)

<a id="multi_task"></a>
## Shared learning across assembly pairs

**documented · core**

The same actor and value model serve different geometries. Task identity chooses simulator assets in the bank, while the actor receives geometry instead of an explicit task label. Shared parameters permit transfer, but the paper does not prove which representation or skill causes the observed gains.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A; IV-B; V-A

**Follow:** [Task frequency induced by reset weights](#task_balance), [Why transfer and planning-like behavior emerge](#gap_causality)

<a id="multi_pair"></a>
## Several pairs in one episode

**documented · core**

Success requires every active pair to be assembled simultaneously. The agent may switch between unfinished pairs, with no prescribed order and no positive reward for completing an individual pair. A separate policy is trained for each active-pair count from one to ten.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; V-D; Table I

**Follow:** [Multi-pair observation and reset construction](#gap_multi_pair)

<a id="omnireset"></a>
## OmniReset reset generation

**documented · predecessor**

OmniReset requests a target object, a sampler of goal states, and a workspace. It precomputes grasp poses and feasible offsets near the goal, generates four families of robot–object states, rejects invalid candidates, and caches accepted states for fast resets. AlphaNIST explicitly adapts the approach rather than specifying an identical implementation.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §§3.1–3.2

**Follow:** [Human-supplied reset priors](#reset_inputs), [Reaching resets](#reaching), [Near-object resets](#near_object), [Stable-grasp resets](#stable_grasp), [Near-goal and partial-assembly resets](#near_goal), [Reset physical feasibility](#validation), [Cached states versus replayed trajectories](#reset_cache), [Uniformity over states versus reset families](#omni_sampling)

<a id="reset_inputs"></a>
## Human-supplied reset priors

**documented · predecessor**

Object selection, goal transforms, workspace limits and robot/asset geometry constrain the distribution before learning. In current UWLab, metadata includes assembled offsets and success tolerances. No demonstrations does not mean absence of engineered information.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.1 Requirements 1–3; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) docs/source/publications/omnireset/new_task.rst, Steps 1–5

**Follow:** [Goal configuration and assembly coordinate](#goal), [Rigid pose and coordinate frames](#pose)

<a id="reaching"></a>
## Reaching resets

**documented · predecessor**

OmniReset places the object at varied tabletop poses and the gripper around the workspace. SGS’s later Reaching strategy instead initially aligns the end effector with a grasp frame and randomizes aperture, allowing the object to fall. Identical family names do not establish identical distributions.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [SGS](papers/SGS-2610.12465.pdf) Appendix A.2

**Follow:** [Inverse kinematics](#ik)

<a id="near_object"></a>
## Near-object resets

**documented · predecessor**

The object rests on the table and the end effector starts near a precomputed grasp pose with perturbations and open/closed gripper states. This exposes contact initiation, including nonprehensile interaction. This is one of OmniReset’s four families; SGS reports three families.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [SGS](papers/SGS-2610.12465.pdf) Appendix A.2

**Follow:** [Grasp pose generation](#grasp_sampling)

<a id="stable_grasp"></a>
## Stable-grasp resets

**documented · predecessor**

OmniReset places the object in air and the gripper at a feasible grasp pose. This exposes transport without requiring pickup first. A cached pose is only as physically credible as its grasp-validation and friction models.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2

**Follow:** [Grasp pose generation](#grasp_sampling), [Reset physical feasibility](#validation), [Friction model and combine rule](#friction)

<a id="near_goal"></a>
## Near-goal and partial-assembly resets

**documented · predecessor**

OmniReset begins at a known goal, applies small random forces, and collects feasible offsets; the gripper is then placed in contact nearby. SGS instead explicitly describes task-dependent assembly-path profiles. Neither description establishes the exact construction used for every AlphaNIST pair.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [SGS](papers/SGS-2610.12465.pdf) Appendix A.2; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) partial_assemblies_cfg.py, PartialAssembliesEventCfg

**Follow:** [Offline partial-assembly generation](#partial_assembly), [Goal configuration and assembly coordinate](#goal), [Grasp pose generation](#grasp_sampling), [Exact adaptation from OmniReset and SGS](#gap_adaptation)

<a id="partial_assembly"></a>
## Offline partial-assembly generation

**documented · predecessor**

Current UWLab starts from assembled offsets, sets both bodies’ friction to zero, applies random force and torque components in [−0.005,0.005], and logs feasible relative poses. This is a public generator for useful states, not evidence that AlphaNIST used these numbers. The cited IndustReal paper explains sampling curricula but does not by itself specify this exact force-displacement recipe.

**Evidence:** [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) partial_assemblies_cfg.py, lines 83–142; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [IndustReal](papers/IndustReal-2305.17110.pdf) §IV-G

**Follow:** [IndustReal](#industreal), [Reset physical feasibility](#validation)

<a id="grasp_sampling"></a>
## Grasp pose generation

**documented · predecessor**

OmniReset reports 1,000 feasible grasps and cites ORBIT. The current UWLab implementation samples object surface points, favors high/upward-facing surfaces, casts inward rays to opposing points within gripper aperture, then samples orientation and standoff. Closing and perturbing the grasp plus collision checks validate candidates. ORBIT alone does not provide this full recipe.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [ORBIT](papers/ORBIT-2301.04195.pdf) Fig. 8 and agent interfaces; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) events.py::_sample_antipodal_grasps; grasp_sampling_cfg.py

**Follow:** [Opposing-contact grasp candidates](#antipodal), [Reset physical feasibility](#validation), [Inverse kinematics](#ik), [Limits of the public grasp sampler](#grasp_limits)

<a id="antipodal"></a>
## Opposing-contact grasp candidates

**documented · foundation**

Opposing surface contacts suggest a parallel-jaw grasp. A true frictional force-closure claim additionally depends on normals and friction cones. UWLab’s ray/opposing-point heuristic and simulator tests should not be described as an exhaustive mathematical force-closure proof.

**Evidence:** [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) events.py::_sample_antipodal_grasps; grasp_sampling_cfg.py

**Follow:** [Friction model and combine rule](#friction)

<a id="ik"></a>
## Inverse kinematics

**documented · foundation**

Forward kinematics maps joint angles to a gripper pose. Inverse kinematics seeks joint angles realizing a desired pose, subject to reachability and joint limits. Multiple solutions or no solution may exist; feasibility and collision rejection matter when converting grasp poses to arm resets.

**Evidence:** [SGS](papers/SGS-2610.12465.pdf) Appendix A.2; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) reset_states_cfg.py; events.py::reset_end_effector_from_grasp_dataset

**Follow:** [Rigid pose and coordinate frames](#pose), [Reset physical feasibility](#validation)

<a id="grasp_limits"></a>
## Limits of the public grasp sampler

**documented · predecessor**

UWLab documents failures for adversarial/unusual shapes and possible task-specific tuning of sampling and minimum collision distance at millimeter precision. Its current release also documents some Isaac Lab 3 training regressions. These are implementation limitations, not unpublished proprietary concepts.

**Evidence:** [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) docs/source/publications/omnireset/new_task.rst, Known Limitations; rl_training.rst, known regressions

<a id="validation"></a>
## Reset physical feasibility

**documented · predecessor**

Reject candidates with unacceptable collisions, let the simulator settle, and check grasp/object stability. Contact is allowed and necessary; invalid interpenetration is different from intended contact. Approximate collision checks can still miss problematic configurations.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2 Practical Implementation; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) collision_analyzer.py; grasp_sampling_cfg.py

**Follow:** [Nonpenetration and contact constraints](#contact), [Signed distance field](#sdf)

<a id="reset_cache"></a>
## Cached states versus replayed trajectories

**documented · foundation**

A reset cache stores states to initialize new simulator rollouts. It does not provide a recorded action trajectory or replay old state-action transitions into PPO. Caching validated states reduces reset-time cost and avoids repeated online feasibility work.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Algorithm 1

**Follow:** [Fresh rollouts and bounded data reuse](#on_policy)

<a id="omni_sampling"></a>
## Uniformity over states versus reset families

**documented · predecessor**

Uniform sampling over a union of finite datasets weights each family in proportion to its number of entries. Current UWLab first selects a family using configured probabilities, then samples a state uniformly within it. Equal family probability equals uniform-over-all-entries only for equal dataset sizes.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2 Practical Implementation; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) events.py::MultiResetManager

**Follow:** [Normalized categorical sampling](#categorical)

<a id="reset_bank"></a>
## Assembly-indexed reset bank

**documented · core**

D_reset={(eᵢ,s̄ᵢ)} stores the part/mating-geometry identity with robot, board and object state. Sampling an entry jointly changes task and starting condition. Bank multiplicities therefore affect the training prior even before adaptive weighting.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 3, IV-B

**Follow:** [Cached states versus replayed trajectories](#reset_cache), [Task frequency induced by reset weights](#task_balance), [Exact AlphaNIST reset-bank contents](#gap_bank)

<a id="reset_prior"></a>
## Initial-state distribution is an inductive bias

**derived · inference**

Providing near-success and grasped starts makes useful experience much more likely than unstructured starts. The human knowledge lies in the support and weighting of initial states, as well as geometry and goals. This does not tell the policy the connecting actions.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §§3.1–3.2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B

**Follow:** [Coverage is finite and approximate](#reset_support), [How skills can connect across reset states](#credit)

<a id="reset_support"></a>
## Coverage is finite and approximate

**derived · inference**

A finite bank is not all valid states. If a useful start is absent, SGS cannot select it; rollouts may still reach states outside the bank. Coverage and learned generalization determine whether competence transfers to a desired deployment start distribution.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [SGS](papers/SGS-2610.12465.pdf) Appendix B.3

**Follow:** [Start distribution defines the test](#reset_evaluation)

<a id="alpha_sampler"></a>
## AlphaNIST sampling equation

**documented · core**

qᵢ=[εq+√(p̂ᵢ(1−p̂ᵢ))]/Σⱼ[εq+√(p̂ⱼ(1−p̂ⱼ))]. The kernel is symmetric and maximized at 0.5; without the floor, p̂=0 and p̂=1 have zero weight. All p̂ᵢ initialize to zero in Algorithm 1, so a common positive floor initially produces a uniform bank distribution.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4; Algorithm 1

**Follow:** [Bernoulli variance and learning heuristic](#bernoulli), [Beta-shaped kernel is not a Bayesian posterior](#beta), [Normalized categorical sampling](#categorical), [Rolling empirical success](#success_history), [Sampler numerical and bookkeeping settings](#gap_sampler)

<a id="success_history"></a>
## Rolling empirical success

**documented · core**

AlphaNIST uses the latest L Boolean outcomes per entry. It is a moving history from changing policies, not an exact success probability or calibrated posterior. Window length trades noise against staleness; rarely visited entries can have stale estimates. SGS reports H=100, which is not a published AlphaNIST L.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; [SGS](papers/SGS-2610.12465.pdf) §3.2; Appendix B.2

**Follow:** [Probability, expectation and empirical frequency](#probability), [Sampler numerical and bookkeeping settings](#gap_sampler)

<a id="bernoulli"></a>
## Bernoulli variance and learning heuristic

**documented · foundation**

For success Y∈{0,1} with probability p, Var(Y)=p(1−p); its standard deviation is √(p(1−p)). Both peak at p=0.5. This measures variability of success, not guaranteed expected policy improvement: irreducibly stochastic tasks can also have p near one half.

**Evidence:** [SFL](papers/SFL-2408.15099.pdf) §4; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4

**Follow:** [Probability, expectation and empirical frequency](#probability)

<a id="categorical"></a>
## Normalized categorical sampling

**documented · foundation**

For nonnegative weights wᵢ with positive sum, choose entry i with probability wᵢ/Σwⱼ. The normalizer couples entries: adding or duplicating a bank entry changes probabilities. This is sampling a discrete index, not sampling a continuous success rate.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4; [SGS](papers/SGS-2610.12465.pdf) Eq. 2

**Follow:** [Probability, expectation and empirical frequency](#probability)

<a id="beta"></a>
## Beta-shaped kernel is not a Bayesian posterior

**documented · foundation**

The Beta(a,b) density is proportional to p^(a−1)(1−p)^(b−1) on [0,1]. AlphaNIST’s unfloored kernel has a=b=1.5. It evaluates that shape at observed success rates to weight discrete entries; it does not draw p from a fitted posterior, and is not Thompson sampling.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4; [SGS](papers/SGS-2610.12465.pdf) §3.2

**Follow:** [Normalized categorical sampling](#categorical), [Bernoulli variance and learning heuristic](#bernoulli)

<a id="sgs"></a>
## General SGS sampler

**documented · predecessor**

SGS uses wᵢ=(pᵢ+ε)^(κt)(1−pᵢ+ε)^(κ(1−t)), logit log(wᵢ+ε), then softmax with temperature T. Appendix B.2 additionally floors w and T. Manipulation defaults are t=.5, κ=1, ε=10⁻⁴, T=2, H=100 and N=32,768 configurations.

**Evidence:** [SGS](papers/SGS-2610.12465.pdf) §3.2, Eqs. 1–2; Appendix B.2

**Follow:** [Softmax temperature changes the kernel](#temperature), [Published AlphaNIST and SGS formulas differ](#sampler_difference), [Sampling for Learnability lineage](#sfl), [Reverse curriculum generation](#reverse_curriculum), [Prioritized Level Replay](#plr)

<a id="temperature"></a>
## Softmax temperature changes the kernel

**derived · foundation**

softmax(log(w+ε)/T) is proportional to (w+ε)^(1/T). Larger T flattens differences. Ignoring epsilon, t=.5 and κ=1 yield [p(1−p)]^(1/(2T)); SGS’s T=2 therefore gives a fourth-root shape, not AlphaNIST’s square-root equation.

**Evidence:** [SGS](papers/SGS-2610.12465.pdf) Eqs. 1–2; Appendix B.2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4

**Follow:** [Beta-shaped kernel is not a Bayesian posterior](#beta)

<a id="sampler_difference"></a>
## Published AlphaNIST and SGS formulas differ

**derived · inference**

The two papers share the success-frontier principle, but their printed effective weights differ in epsilon placement, temperature, and flooring. Treat AlphaNIST Eq. 4 as its declared rule. Whether the unreleased code implements it exactly cannot be resolved from SGS defaults.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 4; [SGS](papers/SGS-2610.12465.pdf) §3.2; Appendix B.2

**Follow:** [Sampler numerical and bookkeeping settings](#gap_sampler)

<a id="sfl"></a>
## Sampling for Learnability lineage

**documented · comparison**

SFL scores levels using p(1−p), evaluates a pool of levels and retains high-scoring ones. SGS explicitly acknowledges the same moderate-success principle, while using rolling histories and a smooth beta-shaped sampler over a fixed configuration set. Neither success variability nor regret is identical to actual future learning gain.

**Evidence:** [SFL](papers/SFL-2408.15099.pdf) §4, Algorithm 1; [SGS](papers/SGS-2610.12465.pdf) §2

**Follow:** [Bernoulli variance and learning heuristic](#bernoulli), [Prioritized Level Replay](#plr), [ProCuRL and the limits of learnability theory](#procurl)

<a id="plr"></a>
## Prioritized Level Replay

**documented · comparison**

PLR preferentially revisits levels using learning-potential scores such as value-prediction error and a staleness component. It replays environment levels, not necessarily old transitions. SGS instead directly weights empirical success. These methods can disagree when value error and success variability differ.

**Evidence:** [PLR](papers/PLR-2010.03934.pdf) §3, Algorithms 1–2; [SGS](papers/SGS-2610.12465.pdf) §2

**Follow:** [Actor, critic and advantage](#value)

<a id="reverse_curriculum"></a>
## Reverse curriculum generation

**documented · comparison**

Florensa et al. start near a supplied goal, generate nearby starts with random actions, and expand using starts with intermediate success. OmniReset instead proposes broad fixed reset coverage; SGS adapts sampling weights over a fixed pool. These are distinct mechanisms despite similar intuition.

**Evidence:** [ReverseCurriculum](papers/ReverseCurriculum-1707.05300.pdf) §4, Algorithm 1; [OmniReset](papers/OmniReset-2603.15789.pdf) §2

**Follow:** [Goal configuration and assembly coordinate](#goal), [Bernoulli variance and learning heuristic](#bernoulli)

<a id="task_balance"></a>
## Task frequency induced by reset weights

**derived · inference**

P(e)=Σᵢ:eᵢ=e qᵢ. Thus adaptive reset sampling also reweights assembly tasks. Equal numbers of states per task do not ensure equal task sampling once their success rates differ. Equal episode allocation also need not mean equal transition allocation when episode lengths vary.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eqs. 3–4; Algorithm 1

**Follow:** [Normalized categorical sampling](#categorical)

<a id="adaptive_objective"></a>
## Training distribution moves with the policy

**derived · inference**

ρ is introduced as an initial distribution, while Algorithm 1 updates it from recent policy outcomes. PPO is therefore optimized on a changing mixture. The paper does not describe importance correction back to a fixed uniform task objective; evaluation explicitly uses a different, frozen distribution.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A; IV-B; V

**Follow:** [Fresh rollouts and bounded data reuse](#on_policy), [Start distribution defines the test](#reset_evaluation)

<a id="success"></a>
## Terminal full-assembly reward

**documented · core**

For a single pair, success is 1[d_asmᵉ(sₜ₊₁)<0.001 m]; it is issued once and terminates the episode. Multi-pair success requires all active assemblies at once. The threshold is explicit; the complete distance computation and symmetry handling are not.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 5; IV-C

**Follow:** [Goal configuration and assembly coordinate](#goal), [Exact success distance and symmetry handling](#gap_metric)

<a id="control_cost"></a>
## Dense action, speed and torque cost

**documented · core**

rₜ=rₜ^succ−c(‖aₜ‖²+‖q̇ₜ‖²+‖τₜ‖²), with fixed c≥0 across tasks. It discourages effort without directly rewarding assembly progress. Unlike OmniReset’s formula, the printed AlphaNIST equation has a torque penalty but no action-difference penalty.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 6; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.1

**Follow:** [Squared Euclidean norm](#norm), [Torque penalty is not measured energy](#energy), [Term weighting versus numerical normalization](#reward_scaling), [Control-cost coefficient and units](#gap_cost)

<a id="norm"></a>
## Squared Euclidean norm

**documented · foundation**

For vector x, ‖x‖₂²=Σⱼxⱼ². Components with twice the magnitude contribute four times the penalty. The result depends on units, preprocessing and which coordinates are included; equal coefficients alone do not imply equal physical influence.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 6

<a id="energy"></a>
## Torque penalty is not measured energy

**documented · foundation**

Mechanical power is τᵀq̇ and mechanical work integrates power over time. Squared torque is an effort-related surrogate. Neither squared action nor squared torque alone is a measurement of electrical energy consumption.

**Evidence:** [SGS](papers/SGS-2610.12465.pdf) Appendix A.3.1, mechanical power; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 6

<a id="reward_scaling"></a>
## Term weighting versus numerical normalization

**documented · foundation**

Changing relative reward weights changes the optimization objective. Rescaling a whole fixed objective by a positive constant preserves mathematical rankings, but can change neural optimization unless optimizer and auxiliary terms scale compatibly. Observation normalization, advantage normalization and PopArt target normalization are different operations.

**Evidence:** [RewardShaping](papers/RewardShaping.pdf) §§2–3; [PopArtMultitask](papers/PopArtMultitask-1809.04474.pdf) §2; [DeepMindSoccer](papers/DeepMindSoccer-2304.13653.pdf) Methods; Table S3

**Follow:** [Squared Euclidean norm](#norm), [PopArt target normalization](#popart), [Control-cost coefficient and units](#gap_cost)

<a id="shaping"></a>
## Progress shaping and policy invariance

**documented · foundation**

A distance-to-goal bonus can favor partial behavior or alter optimal policies. Potential shaping F(s,s′)=γΨ(s′)−Ψ(s) preserves policy rankings under the theorem’s assumptions and appropriate terminal potentials, because its discounted sum telescopes. AlphaNIST’s tested reach/alignment bonuses are not stated to have this form.

**Evidence:** [RewardShaping](papers/RewardShaping.pdf) Theorem 1; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 7

**Follow:** [Why shaping boundary conditions matter](#potential_terminal), [The tested dense reward is one choice](#dense_ablation)

<a id="potential_terminal"></a>
## Why shaping boundary conditions matter

**derived · foundation**

Σₜγᵗ[γΨ(sₜ₊₁)−Ψ(sₜ)]=−Ψ(s₀)+γᴴΨ(s_H). If the final potential depends on the terminal outcome, a finite-horizon return can change ranking. Setting appropriate terminal potential or including time in the potential is necessary; arbitrary distance bonuses do not automatically qualify.

**Evidence:** [RewardShaping](papers/RewardShaping.pdf) Theorem 1 and proof

**Follow:** [Discount and the incentive to finish early](#discount)

<a id="dense_ablation"></a>
## The tested dense reward is one choice

**documented · core**

AlphaNIST adds reach and orientation-alignment rewards with c₂=c₃=.01 and observes worse joint training than its sparse-task objective. This does not prove all dense shaping is inferior. Its claim that these coefficients match OmniReset conflicts with OmniReset v3 Appendix A.1, which lists .1 for reach and distance.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V, Eq. 7; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.1

**Follow:** [Cross-paper reward-coefficient discrepancy](#gap_reward_comparison)

<a id="discount"></a>
## Discount and the incentive to finish early

**documented · foundation**

For 0<γ<1, a success reward received sooner has larger discounted value. With γ=1 and zero control cost, equally successful trajectories need not favor earlier completion. Cost accumulation can favor shorter/lower-effort paths, but there is no general shortest-path guarantee. AlphaNIST’s numerical γ is unpublished.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 2; [GAE](papers/GAE-1506.02438.pdf) §2

**Follow:** [Full PPO and optimization configuration](#gap_ppo)

<a id="termination"></a>
## Success, timeout and unsafe termination

**documented · core**

Episodes stop at success, horizon, or arm velocity/torque violation. The text requires success without simultaneous safety failure. Correct value targets distinguish terminal outcomes from rollout cuts and any bootstrapable time limits; exact masks and precedence are not published.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; V; [PPO](papers/PPO-1707.06347.pdf) §5

**Follow:** [Reward timing and termination masks](#gap_reward_timing), [Joint-speed and torque limits](#limits)

<a id="value"></a>
## Actor, critic and advantage

**documented · foundation**

The actor defines πθ(a|o). The critic estimates expected future return Vϕ(o); Q(s,a) conditions on a chosen action. Advantage A=Q−V compares that action with average behavior. With costs and discount, V is not simply assembly success probability.

**Evidence:** [GAE](papers/GAE-1506.02438.pdf) §2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Discounted finite-horizon return](#return)

<a id="bellman"></a>
## Bootstrapping and Bellman recursion

**documented · foundation**

Vπ(s)=E[r+γVπ(s′)] with the future term removed at a true terminal state. Learning a useful value near completion can influence estimates farther away through sampled transitions. A neural approximation can generalize across states, but approximation error can also propagate.

**Evidence:** [GAE](papers/GAE-1506.02438.pdf) §§2–3; [ConservativePolicyIteration](papers/ConservativePolicyIteration.pdf) §2

**Follow:** [Actor, critic and advantage](#value), [Success, timeout and unsafe termination](#termination)

<a id="policy_gradient"></a>
## Likelihood-ratio policy gradient

**documented · foundation**

Policy-gradient updates weight ∇θ log πθ(aₜ|oₜ) by estimated advantage. Positive advantage favors the sampled action and negative advantage disfavors it. The environment need not be differentiable; sampled rewards and transitions train the networks.

**Evidence:** [PPO](papers/PPO-1707.06347.pdf) §2.1; [GAE](papers/GAE-1506.02438.pdf) §2

**Follow:** [Actor, critic and advantage](#value), [Gaussian action distribution](#gaussian), [Minibatches, gradients and Adam](#optimization)

<a id="ppo"></a>
## Proximal Policy Optimization

**documented · core**

The clipped objective averages min(ratio·Â, clip(ratio,1−ε,1+ε)·Â), with ratio=πθ(a|o)/πold(a|o). Clipping limits incentives for some large probability changes; it is not a hard guarantee on every policy change. AlphaNIST names standard PPO but omits many settings.

**Evidence:** [PPO](papers/PPO-1707.06347.pdf) §3 Eq. 7; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E

**Follow:** [Fresh rollouts and bounded data reuse](#on_policy), [Action-probability ratio](#importance), [Generalized Advantage Estimation](#gae), [TRPO and conservative policy iteration](#trpo), [Exploration entropy](#entropy), [Full PPO and optimization configuration](#gap_ppo)

<a id="importance"></a>
## Action-probability ratio

**documented · foundation**

The new/old probability ratio compares policies on actions sampled by the old policy. This action correction is distinct from correcting a changed reset distribution. PPO’s clipped surrogate is not an exact unbiased importance estimator after clipping.

**Evidence:** [PPO](papers/PPO-1707.06347.pdf) §§2–3

**Follow:** [Probability, expectation and empirical frequency](#probability)

<a id="on_policy"></a>
## Fresh rollouts and bounded data reuse

**documented · foundation**

PPO collects trajectories with a current policy, then performs several optimization passes on that batch. It is called on-policy despite this short reuse window; it does not ordinarily maintain an unrestricted old-transition replay buffer as off-policy algorithms do.

**Evidence:** [PPO](papers/PPO-1707.06347.pdf) §5, Algorithm 1; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Algorithm 1

<a id="gae"></a>
## Generalized Advantage Estimation

**documented · foundation**

Using TD residual δₜ=rₜ+γV(sₜ₊₁)−V(sₜ), GAE computes Âₜ=Σₗ(γλ)ˡδₜ₊ₗ with termination masks and truncation handling. λ trades bias and variance. PPO’s source gives this estimator; AlphaNIST does not explicitly publish its advantage-estimator configuration.

**Evidence:** [GAE](papers/GAE-1506.02438.pdf) §3; [PPO](papers/PPO-1707.06347.pdf) §5

**Follow:** [Bootstrapping and Bellman recursion](#bellman), [Full PPO and optimization configuration](#gap_ppo)

<a id="trpo"></a>
## TRPO and conservative policy iteration

**documented · lineage**

TRPO seeks policy improvement with a constrained average KL change; PPO replaces the expensive constrained update with simpler surrogate objectives. Conservative policy iteration supplies earlier improvement and restart-distribution analysis. Their guarantees do not automatically prove convergence of AlphaNIST’s neural PPO setup.

**Evidence:** [TRPO](papers/TRPO-1502.05477.pdf) §§3–4; [PPO](papers/PPO-1707.06347.pdf) §2.2; [ConservativePolicyIteration](papers/ConservativePolicyIteration.pdf) §§3–4

**Follow:** [Kullback–Leibler divergence](#kl)

<a id="entropy"></a>
## Exploration entropy

**documented · foundation**

Entropy measures distributional spread: H(π)=−E log π(a|o). An entropy bonus can discourage premature collapse of a stochastic policy. AlphaNIST’s Gaussian output does not establish the entropy coefficient, variance schedule or use of gSDE.

**Evidence:** [PPO](papers/PPO-1707.06347.pdf) Eq. 9; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Gaussian action distribution](#gaussian), [Gaussian exploration and action processing](#gap_noise), [Full PPO and optimization configuration](#gap_ppo)

<a id="optimization"></a>
## Minibatches, gradients and Adam

**documented · foundation**

Backpropagation differentiates a neural loss; minibatch optimization averages sample gradients. Adam tracks first and second gradient moments, bias-corrects them and scales updates. Adam is documented in the PPO lineage and public predecessor config, but AlphaNIST’s exact optimizer settings are not disclosed.

**Evidence:** [Adam](papers/Adam-1412.6980.pdf) Algorithm 1; [PPO](papers/PPO-1707.06347.pdf) §5; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) agents/rsl_rl_cfg.py

**Follow:** [Full PPO and optimization configuration](#gap_ppo)

<a id="distributed"></a>
## Synchronous distributed PPO

**documented · core**

AlphaNIST averages actor and critic gradients across GPUs before each optimizer step. It reports 4K environments/GPU in multi-GPU runs, 32 rollout steps/environment, five epochs and four minibatches. Model architecture and settings are said to stay fixed as environment count scales.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E

**Follow:** [Parallelism changes the optimization batch](#batch_scale), [Global formula versus GPU-local banks](#gap_distributed_sampler)

<a id="batch_scale"></a>
## Parallelism changes the optimization batch

**derived · inference**

With N environments and 32 steps, each iteration collects 32N transitions. Holding iterations fixed while increasing N increases data, batch size and compute together. Four minibatches mean larger minibatches at larger N. This does not isolate a pure hardware-parallelism effect.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E; V

**Follow:** [Interaction budget and GPU-hours](#compute)

<a id="credit"></a>
## How skills can connect across reset states

**derived · inference**

Near-goal success supplies useful value/advantage targets; experience beginning farther away can learn actions that reach high-value states. Shared function approximation can transfer across reset neighborhoods and tasks. No stored graph, stage label, or demonstrated connecting motion is required; connectivity and successful learning are not guaranteed.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §§3.2–3.3; [GAE](papers/GAE-1506.02438.pdf) §3

**Follow:** [Bootstrapping and Bellman recursion](#bellman), [Coverage is finite and approximate](#reset_support)

<a id="point_cloud"></a>
## Geometry conditioning through point clouds

**documented · core**

The actor observes surface points for the movable part, mating geometry and robot, rather than a discrete task token. This makes task-relevant geometry available. It does not establish camera-based perception, occlusion handling, or generalization to unseen shapes; the paper’s results use simulation.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) III-A; IV-D; VI

**Follow:** [Point-cloud encoder specification](#encoder), [Point-cloud construction and encoder aggregation](#gap_encoder), [Proprioception packing and history](#gap_observation)

<a id="encoder"></a>
## Point-cloud encoder specification

**documented · core**

Figure 3 shows a two-layer ELU encoder with widths 256 and 128 from 3×n_pts input. It does not state n_pts, point sampling, coordinate frame, aggregation/pooling, segmentation, or how point order is treated. Calling it PointNet would add an unverified architectural claim.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [ELU activation](#elu), [Point-cloud construction and encoder aggregation](#gap_encoder)

<a id="proprioception"></a>
## Robot measurements and previous action

**documented · core**

Figure 3 lists pose 7, twist 6, joints 9, action 8, but labels the input as 150 dimensional. The listed quantities sum to 30; five stacked frames would explain 150, but the paper does not explicitly confirm that packing, frame convention or history spacing.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Rigid pose and coordinate frames](#pose), [Proprioception packing and history](#gap_observation)

<a id="simba"></a>
## SimBa-style residual architecture

**documented · core**

SimBa normalizes observations with running statistics, uses pre-layer-normalized residual MLP blocks, and layer-normalizes the final representation. AlphaNIST illustrates two blocks of width 256 with 1024-wide expansions, using Swish, whereas original SimBa describes ReLU. Preserve that distinction.

**Evidence:** [SimBa](papers/SimBa-2410.09754.pdf) §4, Eqs. 3–7; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Running observation normalization](#running_norm), [Layer normalization](#layer_norm), [Residual connection](#residual), [Swish activation](#swish)

<a id="running_norm"></a>
## Running observation normalization

**documented · foundation**

Track per-feature mean μ and variance σ² across samples, then use (x−μ)/√(σ²+ε). This changes input scale; it is not reward normalization. AlphaNIST shows RN on the 150-dimensional input branch, but does not publish statistics synchronization or update/freeze rules.

**Evidence:** [SimBa](papers/SimBa-2410.09754.pdf) §4 Eqs. 3–4; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Proprioception packing and history](#gap_observation)

<a id="layer_norm"></a>
## Layer normalization

**documented · foundation**

Normalize a sample’s hidden features using their mean and variance, optionally with learned affine scale and shift. Unlike batch normalization, the statistics are within that sample’s layer rather than across examples. This stabilizes representation magnitude; it does not normalize physical reward units.

**Evidence:** [LayerNorm](papers/LayerNorm-1607.06450.pdf) §3; [SimBa](papers/SimBa-2410.09754.pdf) §4

<a id="residual"></a>
## Residual connection

**documented · foundation**

A block computes x+F(x), preserving an identity path while learning a correction. AlphaNIST’s two blocks use layer normalization, linear expansion, nonlinear activation and linear contraction. Residual structure can aid optimization without guaranteeing a simpler or more general policy.

**Evidence:** [ResNet](papers/ResNet-1512.03385.pdf) §3.2; [SimBa](papers/SimBa-2410.09754.pdf) Eq. 6; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

<a id="swish"></a>
## Swish activation

**documented · foundation**

Swish is f(x)=x·sigmoid(βx); β=1 is often called SiLU. AlphaNIST labels its activation Swish, but does not specify β. Original SimBa uses ReLU, so the architecture is an adaptation.

**Evidence:** [Swish](papers/Swish-1710.05941.pdf) §3; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Exact neural layer settings](#gap_network_details)

<a id="elu"></a>
## ELU activation

**documented · foundation**

ELU(x)=x for x>0 and α(exp(x)−1) otherwise. It provides a smooth negative branch. AlphaNIST labels its point encoder ELU without publishing the α setting or precise point aggregation.

**Evidence:** [ELU](papers/ELU-1511.07289.pdf) §2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Exact neural layer settings](#gap_network_details)

<a id="gaussian"></a>
## Gaussian action distribution

**documented · core**

The actor samples actions from a Gaussian distribution described by a mean and covariance (often diagonal in robotics). AlphaNIST confirms a Gaussian eight-dimensional output but not its variance parameterization, clipping/squashing, initial scale, or joint/gripper postprocessing.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; [PPO](papers/PPO-1707.06347.pdf) §6

**Follow:** [Gaussian exploration and action processing](#gap_noise)

<a id="kl"></a>
## Kullback–Leibler divergence

**documented · foundation**

D_KL(P‖Q)=E_P[log(P/Q)] quantifies a directional distribution mismatch. It is nonnegative but generally asymmetric. It appears in trust-region constraints and distribution distillation; the direction and normalization matter.

**Evidence:** [TRPO](papers/TRPO-1502.05477.pdf) §3; [DextrAH-RGB](papers/DextrAH-RGB-2412.01791.pdf) §III-C

<a id="robot"></a>
## Panda embodiment

**documented · core**

A seven-DoF arm plus a parallel-jaw gripper is simulated. Nine joint coordinates can include seven arm joints and two finger coordinates, while the policy controls only one gripper coordinate. Exact observation interpretation still requires the unpublished packing.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D, Fig. 3

**Follow:** [Driven and coupled finger](#gripper)

<a id="joint_targets"></a>
## Relative joint-position targets

**documented · core**

q_target=q_current+Δq at each 25 Hz policy step. This differs from accumulating increments on the previous target and from commanding Cartesian displacement. Action scaling and clipping determine the numerical Δq; they are not published.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D

**Follow:** [Joint impedance and implicit actuation](#impedance), [Controller gains and identified robot model](#gap_controller)

<a id="impedance"></a>
## Joint impedance and implicit actuation

**documented · foundation**

A schematic controller uses torque Kp(q_target−q)−Kd q̇ plus any compensation terms. Stiffness trades tracking against compliant contact; damping suppresses velocity. An implicit simulator drive solves effects within its integration/constraint step, so it is not automatically identical to a real actuator or an explicit PD calculation.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D; [libfranka-control](sources/libfranka-control.html) setJointImpedance documentation; [IsaacLab](papers/IsaacLab-2511.04831.pdf) actuator modeling

**Follow:** [System identification and drivetrain effects](#system_id), [Physics step versus policy step](#timestep), [Controller gains and identified robot model](#gap_controller)

<a id="limits"></a>
## Joint-speed and torque limits

**documented · core**

AlphaNIST specifies 2.175 rad/s for arm joints 1–4, 2.61 rad/s for 5–7, and 87 Nm / 12 Nm torque limits respectively. Exceeding limits ends the episode. Whether action/actuator clipping is additionally used, and how simultaneous success is handled, remains an implementation question.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C–D

**Follow:** [Controller gains and identified robot model](#gap_controller), [Reward timing and termination masks](#gap_reward_timing)

<a id="system_id"></a>
## System identification and drivetrain effects

**documented · foundation**

System identification fits model parameters from real measurements. Armature adds effective inertia; friction resists motion; latency delays commands. AlphaNIST says parameters are identified and hardware matched but does not publish the complete parameter vector, fitting dataset or validation residuals.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.2

**Follow:** [Controller gains and identified robot model](#gap_controller), [PACE calibration pipeline](#pace)

<a id="gripper"></a>
## Driven and coupled finger

**documented · core**

One finger is driven and one mechanically coupled passive finger follows. Finger kinematics, contact pad friction and gripper command mapping affect what grasps are physically stable. The robot’s two finger coordinates do not imply two independent policy actions.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D

**Follow:** [Friction model and combine rule](#friction), [Controller gains and identified robot model](#gap_controller)

<a id="isaaclab"></a>
## Isaac Lab environment framework

**documented · core**

Isaac Lab integrates assets, scene simulation, sensors, actions, observations, rewards, resets, randomization and learning interfaces. It is the reported AlphaNIST framework; a framework citation does not identify every version or default actually used in the experiment.

**Evidence:** [IsaacLab](papers/IsaacLab-2511.04831.pdf) framework overview and environment abstractions; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D

**Follow:** [GPU-native parallel simulation lineage](#isaacgym), [Physics versions, assets and numerical settings](#gap_simulator)

<a id="isaacgym"></a>
## GPU-native parallel simulation lineage

**documented · lineage**

Isaac Gym keeps simulation state and learning tensors on the GPU to reduce CPU transfer overhead and run many environments in parallel. Isaac Lab is its successor framework. Parallel environments provide experience throughput, not independent physical hardware evidence.

**Evidence:** [IsaacGym](papers/IsaacGym-2108.10470.pdf) §3; [IsaacLab](papers/IsaacLab-2511.04831.pdf) Introduction

**Follow:** [Synchronous distributed PPO](#distributed)

<a id="factory"></a>
## Factory contact simulation

**documented · lineage**

Factory combines signed distance fields for collision geometry, reduced contact patches and a Gauss–Seidel solver to make detailed assembly simulation tractable. AlphaNIST cites this simulation lineage; its exact contact asset and solver configuration remain unreported.

**Evidence:** [Factory](papers/Factory-2205.03532.pdf) §III; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-A

**Follow:** [Signed distance field](#sdf), [Contact patch reduction](#contact_reduction), [Iterative contact solver](#solver)

<a id="rigid_body"></a>
## Rigid-body dynamics

**documented · foundation**

A schematic robot equation is M(q)q̈+C(q,q̇)+g(q)+f(q̇)=τ+J(q)ᵀf_contact. M is inertia, C velocity-dependent terms, g gravity, f friction, J the contact Jacobian. A rigid approximation omits deformation and requires contact constraints and numerical integration.

**Evidence:** [OperationalSpaceControl](papers/OperationalSpaceControl.pdf) dynamic modeling; [Factory](papers/Factory-2205.03532.pdf) II-A

**Follow:** [Nonpenetration and contact constraints](#contact), [Friction model and combine rule](#friction), [Iterative contact solver](#solver), [Kinematic Jacobian and wrench mapping](#jacobian)

<a id="contact"></a>
## Nonpenetration and contact constraints

**documented · foundation**

Contact modeling prevents excessive overlap and determines forces/impulses when bodies meet. In an ideal complementarity view, nonnegative normal force acts at zero gap, while positive gap has no normal force. Finite time steps and tolerances make the numerical model approximate.

**Evidence:** [Factory](papers/Factory-2205.03532.pdf) II-A; III

**Follow:** [Signed distance field](#sdf), [Iterative contact solver](#solver)

<a id="sdf"></a>
## Signed distance field

**documented · foundation**

An SDF maps a point to signed distance from a surface; its sign convention distinguishes inside from outside and its gradient supplies a local normal. A voxel grid approximates it. Resolution and sampling affect small-feature accuracy, so a mesh image alone does not establish collision fidelity.

**Evidence:** [Factory](papers/Factory-2205.03532.pdf) II-A1; III-A; [IndustReal](papers/IndustReal-2305.17110.pdf) IV-E–F

<a id="contact_reduction"></a>
## Contact patch reduction

**documented · foundation**

Many nearby contacts with similar normals can be grouped and reduced while trying to preserve their combined wrench. Fewer constraints reduce memory and solver cost. The procedure is an approximation whose settings can affect force and torque predictions.

**Evidence:** [Factory](papers/Factory-2205.03532.pdf) III-B–C

<a id="friction"></a>
## Friction model and combine rule

**documented · foundation**

Coulomb friction bounds tangential force by μ times normal force. Material coefficients and combine modes determine the effective contact μ. SGS reports that OmniReset’s pad μ=100 encouraged implausible grasps and uses μ=2; AlphaNIST does not publish its pad friction, so neither value can be imported.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.4; [SGS](papers/SGS-2610.12465.pdf) Appendix C.2

**Follow:** [Physics versions, assets and numerical settings](#gap_simulator)

<a id="solver"></a>
## Iterative contact solver

**documented · foundation**

Gauss–Seidel updates constraints sequentially using latest estimates; Jacobi uses previous-iteration values and parallelizes more easily. Contact reduction can make Gauss–Seidel competitive at scale. Iteration count, tolerances and substeps affect stability and penetration.

**Evidence:** [Factory](papers/Factory-2205.03532.pdf) II-A3; III-B

**Follow:** [Physics step versus policy step](#timestep), [Physics versions, assets and numerical settings](#gap_simulator)

<a id="timestep"></a>
## Physics step versus policy step

**documented · foundation**

A policy step can hold one action across several physics steps (decimation). AlphaNIST gives 25 Hz policy control, not its full physics timing. SGS gives 200 Hz physics and eight steps per Franka action; those are SGS settings, not confirmed AlphaNIST values.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D; [SGS](papers/SGS-2610.12465.pdf) Appendix A.2

**Follow:** [Physics versions, assets and numerical settings](#gap_simulator)

<a id="metrics"></a>
## Training success versus evaluation success

**documented · core**

The 98.2% number is shared-policy training success at 64K environments. The 97.4% versus 84.3% sampler comparison is frozen-bank evaluation at 256K. These measure different experiments and should not be mixed into one headline hardware accuracy claim.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V-A–B, Figs. 5–7

**Follow:** [Start distribution defines the test](#reset_evaluation)

<a id="reset_evaluation"></a>
## Start distribution defines the test

**documented · core**

Scaling evaluation uses stochastic actions, a common frozen mixed-reset bank, uniform sampling within each task, 32 trials/task/seed and five evaluation seeds. Success rates cover all reset configurations. A partially assembled start is easier than a full pickup-to-insertion trial; the mixed result does not state a table-only success rate.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V; Fig. 7

**Follow:** [Evaluation independence and uncertainty](#gap_eval)

<a id="scale"></a>
## Reported sampling and scale ablation

**documented · core**

At 256K environments sparse-task success is 97.4% with beta sampling and 84.3% with uniform sampling; dense-reward counterparts are 77.4% and 34.3%. These support a gain in the tested setup, while data volume and batch size also grow with scale.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V-B

**Follow:** [Parallelism changes the optimization batch](#batch_scale), [What an ablation identifies](#ablation)

<a id="compute"></a>
## Interaction budget and GPU-hours

**documented · core**

The shared policy uses 410 GPU-hours versus 16.1K aggregate GPU-hours for twenty sparse-reward specialists, approximately 39.3×. Comparisons match per-run interaction budgets, not aggregate data for all specialists. GPU-hours are device-hours, not wall-clock hours or a hardware-independent efficiency measure.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V-A

**Follow:** [Full compute accounting](#gap_compute)

<a id="multi_pair_result"></a>
## One-to-ten pair results

**documented · core**

Table I reports 99,97,95,93,92,90,89,87,86,84 percent for one through ten active pairs, with policies trained and evaluated at the same count and 15 seconds allowed per pair. Twenty simultaneous active pairs remain future work.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Table I; V-D; VI

**Follow:** [Several pairs in one episode](#multi_pair), [Multi-pair observation and reset construction](#gap_multi_pair)

<a id="emergence"></a>
## Observed dexterity and planning-like behavior

**documented · core**

Figures and videos show regrasping, geometry-assisted reorientation, nut tapping/threading and switching between partially completed tasks. This supports the observation of coordinated behavior. It does not identify an internal symbolic planner, prove optimal planning, or show general performance on arbitrary assemblies.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V-C–D, Figs. 8–9

**Follow:** [Why transfer and planning-like behavior emerge](#gap_causality)

<a id="ablation"></a>
## What an ablation identifies

**documented · foundation**

Changing one component while holding others fixed estimates its effect in that tested setup. Results do not establish necessity in all settings. AlphaNIST’s beta-versus-uniform comparison uses the same bank, so it tests allocation conditional on coverage, not whether broad reset coverage itself is necessary.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; V; [SGS](papers/SGS-2610.12465.pdf) Appendix B.3

**Follow:** [The tested dense reward is one choice](#dense_ablation)

<a id="related_assembly"></a>
## Alternative assembly pipelines

**documented · comparison**

Prior work supplies useful contrasts: Factory uses subpolicies; IndustReal adds simulator/reward/curriculum and control techniques; AutoMate uses assembly-by-disassembly and imitation; Refinery improves specialist initialization; ARCH uses an explicit hierarchy. None should be silently inserted into AlphaNIST.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-C

**Follow:** [IndustReal](#industreal), [AutoMate assembly by disassembly](#automate), [Refinery active initialization](#refinery), [ARCH explicit hierarchical assembly](#arch)

<a id="industreal"></a>
## IndustReal

**documented · comparison**

IndustReal addresses interpenetration artifacts in training, uses an SDF-based dense alignment reward, samples starts with a curriculum, and applies a policy-level action integrator for transfer. Its sampling-based curriculum retains easier starts while expanding difficulty. This is explanatory reset/control lineage, not AlphaNIST’s reward.

**Evidence:** [IndustReal](papers/IndustReal-2305.17110.pdf) §IV-E–G; §V; Appendix on PLAI

**Follow:** [Signed distance field](#sdf), [Progress shaping and policy invariance](#shaping)

<a id="automate"></a>
## AutoMate assembly by disassembly

**documented · comparison**

AutoMate generates disassembly trajectories, reverses them into assembly paths, trains specialist RL policies with an imitation objective, and distills/fine-tunes a generalist. These are trajectory-guided policies; OmniReset’s unordered reset states do not supply the same action/path supervision.

**Evidence:** [AutoMate](papers/AutoMate-2407.08028.pdf) §§IV–VI

**Follow:** [Behavior cloning and state-distribution shift](#imitation)

<a id="refinery"></a>
## Refinery active initialization

**documented · comparison**

Refinery uses Bayesian-optimization-guided initial-state selection to fine-tune pretrained assembly specialists, then models favorable deployment initializations using a Gaussian mixture. It requires a pretrained-policy pipeline and does not establish AlphaNIST’s sampler or reset geometry.

**Evidence:** [Refinery](papers/Refinery-2510.11019.pdf) Method, Fig. 1

**Follow:** [Bayesian optimization and acquisition functions](#bayesopt), [Gaussian mixture model](#gmm)

<a id="arch"></a>
## ARCH explicit hierarchical assembly

**documented · comparison**

ARCH uses a high-level learned planner to select and parameterize lower-level skills combining RL and model-based control. AlphaNIST’s multi-pair policy is described without this explicit hierarchy. Its planning-like behavior should not be confused with ARCH’s architecture.

**Evidence:** [ARCH](papers/ARCH-2409.16451.pdf) Abstract; Method

<a id="multitask_alternatives"></a>
## Multi-task optimization alternatives

**documented · comparison**

Task sharing can introduce conflicting gradients or unequal target scales. PCGrad and PopArt address those issues explicitly. AlphaNIST reports standard shared PPO without task-specific value heads or gradient projection; this does not prove those issues never occur.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-B

**Follow:** [PCGrad gradient projection](#pcgrad), [PopArt target normalization](#popart), [Ordinary scalarized multi-task training](#unitary)

<a id="pcgrad"></a>
## PCGrad gradient projection

**documented · comparison**

For conflicting gradients gᵢ·gⱼ<0, project gᵢ away from gⱼ via gᵢ←gᵢ−(gᵢ·gⱼ/‖gⱼ‖²)gⱼ. This explicitly modifies multi-task updates. AlphaNIST states that it does not use gradient projection.

**Evidence:** [PCGrad](papers/PCGrad-2001.06782.pdf) §3, Algorithm 1; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-B

<a id="popart"></a>
## PopArt target normalization

**documented · comparison**

PopArt maintains target mean/scale and adjusts the output layer when those statistics change so unnormalized predictions are preserved. For f=σ(Wh+b)+μ, use W′=σW/σ′ and b′=(σb+μ−μ′)/σ′. Multi-task PopArt uses task-specific statistics/heads; this is distinct from changing physical reward terms.

**Evidence:** [PopArt](papers/PopArt.pdf) §2; [PopArtMultitask](papers/PopArtMultitask-1809.04474.pdf) §2; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-B

<a id="unitary"></a>
## Ordinary scalarized multi-task training

**documented · comparison**

Kurin et al. show that summing task losses with standard regularization/stabilization can match specialized optimizers on tested benchmarks. This supports considering simple baselines; it does not guarantee that AlphaNIST’s task mixture is balanced or optimal.

**Evidence:** [UnitaryScalarization](papers/UnitaryScalarization-2201.04122.pdf) Abstract; experimental conclusions

<a id="transfer"></a>
## Predecessor sim-to-real pipeline

**documented · predecessor**

OmniReset and SGS train simulator experts and distill perception-based students, with system identification and randomization for transfer. AlphaNIST reports simulation only and leaves sensor-derived deployment to future work. Predecessor hardware results are not AlphaNIST hardware validation.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) §5; Appendix A.3; [SGS](papers/SGS-2610.12465.pdf) Appendix C; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) VI

**Follow:** [Asymmetric actor-critic](#asymmetric), [Generalized state-dependent exploration](#gsde), [Teacher-to-student policy distillation](#distillation), [Domain randomization](#randomization), [Curricula in predecessor transfer experiments](#transfer_curriculum), [Friction, distillation and seed-selection caveats](#transfer_limits), [Operational-space control](#osc)

<a id="asymmetric"></a>
## Asymmetric actor-critic

**documented · predecessor**

The critic can use privileged simulator information unavailable to the deployed actor. OmniReset uses this separation. AlphaNIST illustrates actor and critic with the same inputs and separate parameters; inheriting OmniReset’s privileged critic or five-frame actor setting would be unsupported.

**Evidence:** [AsymmetricActorCritic](papers/AsymmetricActorCritic-1710.06542.pdf) III; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.3, Appendix A.3.9; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3

**Follow:** [Partial observation and history](#pomdp)

<a id="gsde"></a>
## Generalized state-dependent exploration

**documented · predecessor**

gSDE samples a noise matrix periodically and multiplies it by policy features: a=μ(s)+W_noise z(s). Holding the matrix between resampling steps creates correlated exploration; state-dependent variance alone does not. OmniReset says it uses gSDE; AlphaNIST does not establish that choice.

**Evidence:** [gSDE](papers/gSDE-2005.05719.pdf) §§2.2–3; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.3

**Follow:** [Gaussian action distribution](#gaussian)

<a id="distillation"></a>
## Teacher-to-student policy distillation

**documented · predecessor**

A privileged expert labels actions/distributions for a student observing images. OmniReset describes 80K trajectories, an ImageNet-pretrained ResNet-18 encoder, a 4-layer 512-unit MLP, KL action matching and auxiliary object-pose reconstruction. It cites DextrAH-RGB, whose own student learning uses online DAgger; these collection procedures differ.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.11; [DextrAH-RGB](papers/DextrAH-RGB-2412.01791.pdf) §III-C

**Follow:** [Kullback–Leibler divergence](#kl), [Behavior cloning and state-distribution shift](#imitation), [ResNet visual encoder](#resnet_student), [DAgger data aggregation](#dagger)

<a id="imitation"></a>
## Behavior cloning and state-distribution shift

**documented · foundation**

Behavior cloning fits expert actions on collected observations. If errors push the learner into unfamiliar states, errors can compound. This is a different supervision source from PPO learning only from environment rewards; distillation after RL does not mean the original RL used human demonstrations.

**Evidence:** [DextrAH-RGB](papers/DextrAH-RGB-2412.01791.pdf) §III-C; [AutoMate](papers/AutoMate-2407.08028.pdf) generalist learning

**Follow:** [DAgger data aggregation](#dagger)

<a id="dagger"></a>
## DAgger data aggregation

**documented · foundation**

Roll out the learner, ask the expert for actions at states the learner visits, add those labels to the dataset, and retrain. This targets the learner-induced observation distribution. DextrAH-RGB uses an online variant; OmniReset discusses image-based DAgger as future work.

**Evidence:** [DAgger](papers/DAgger-1011.0686.pdf) §3, Algorithm 3.1; [DextrAH-RGB](papers/DextrAH-RGB-2412.01791.pdf) §III-C; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.11

<a id="resnet_student"></a>
## ResNet visual encoder

**documented · foundation**

Residual image networks learn convolutional features with skip connections. OmniReset’s student uses pretrained ResNet-18 features and end-to-end fine-tuning; this is separate from AlphaNIST’s surface-point encoder and residual MLP.

**Evidence:** [ResNet](papers/ResNet-1512.03385.pdf) §3; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.11

**Follow:** [Residual connection](#residual)

<a id="randomization"></a>
## Domain randomization

**documented · foundation**

Randomize simulator dynamics and/or visual factors to expose a policy or student to a distribution of conditions. It aims to reduce sensitivity to mismatch but cannot guarantee coverage of real-world physics or perception. AlphaNIST’s full randomization distribution is not reported.

**Evidence:** [DomainRandomization](papers/DomainRandomization-1703.06907.pdf) §3; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.7; [SGS](papers/SGS-2610.12465.pdf) Appendix C.2

**Follow:** [Physics versions, assets and numerical settings](#gap_simulator)

<a id="transfer_curriculum"></a>
## Curricula in predecessor transfer experiments

**documented · predecessor**

OmniReset A.3.9 transitions from simplified dynamics to system-identified dynamics after training. SGS B.4 says its main manipulation experiments use a success-triggered gravity curriculum and reports a one-seed no-curriculum ablation. These facts limit blanket claims that the entire predecessor pipelines have no curricula; they do not prove AlphaNIST used one.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.9; [SGS](papers/SGS-2610.12465.pdf) Appendix B.4

**Follow:** [Exact adaptation from OmniReset and SGS](#gap_adaptation)

<a id="transfer_limits"></a>
## Friction, distillation and seed-selection caveats

**documented · predecessor**

OmniReset selects seeds by action-noise robustness and reports a gap between state experts and vision students. SGS identifies unrealistic high-friction grasps and modifies pad friction. These reveal concrete sources of simulation-to-hardware mismatch, but not AlphaNIST’s unreported configuration.

**Evidence:** [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.10–11; [SGS](papers/SGS-2610.12465.pdf) Appendix C.2–3

**Follow:** [Friction model and combine rule](#friction), [AlphaNIST hardware and unseen-condition performance](#gap_hardware)

<a id="alphago"></a>
## AlphaGo Zero is motivation, not the algorithm

**documented · comparison**

AlphaGo Zero combines self-play, a policy/value network and Monte Carlo tree search to create training targets from game outcomes. AlphaNIST invokes sparse-objective inspiration but describes PPO in a continuous robot environment, with no reported tree search or adversarial self-play.

**Evidence:** [AlphaGoZero](papers/AlphaGoZero.pdf) self-play learning; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) I; II-C

**Follow:** [Proximal Policy Optimization](#ppo), [Monte Carlo tree search](#mcts)

<a id="soccer"></a>
## DeepMind soccer and reward weights

**documented · conversation**

The user’s intended paper is Learning Agile Soccer Skills for a Bipedal Robot with Deep Reinforcement Learning, not the wheeled-robot paper initially suggested in the chat. Its Table S3 gives per-stage weights, e.g. scoring 1000, velocity-to-ball .05, forward velocity .1, knee-torque penalty .01 for the full 1v1 agent. These demonstrate relative scaling but do not supply AlphaNIST c.

**Evidence:** [DeepMindSoccer](papers/DeepMindSoccer-2304.13653.pdf) Methods; Supplementary Table S3

**Follow:** [Term weighting versus numerical normalization](#reward_scaling)

<a id="conversation"></a>
## Audit of the shared conversation

**documented · conversation**

The chat correctly separates reset generation from success-based selection and notes missing reward scaling. Its near-goal story describes OmniReset, with an explicit caveat about AlphaNIST adaptation. Treat the chat as a trail of questions, not primary evidence; the archived transcript preserves the user’s soccer-paper correction.

**Evidence:** [Conversation](sources/shared-conversation.json) user/assistant messages; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B–C; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2

**Follow:** [DeepMind soccer and reward weights](#soccer), [Published AlphaNIST and SGS formulas differ](#sampler_difference), [Initial-state distribution is an inductive bias](#reset_prior)

<a id="procurl"></a>
## ProCuRL and the limits of learnability theory

**documented · lineage**

ProCuRL selects starting states by PoS_current × (PoS_optimal − PoS_current). If optimal success is one, this becomes p(1−p). Its justifications consider restricted settings including independent tasks and simple learners. They do not prove that middle-success resets maximize improvement for a shared neural robot policy.

**Evidence:** [ProCuRL](papers/ProCuRL-2304.12877.pdf) §§3.1–3.2; [SFL](papers/SFL-2408.15099.pdf) §4

**Follow:** [Bernoulli variance and learning heuristic](#bernoulli)

<a id="pace"></a>
## PACE calibration pipeline

**documented · predecessor**

OmniReset explicitly follows PACE for actuator identification. PACE replays measured joint-target trajectories in many simulated environments and minimizes mean squared simulated-versus-real joint-position error. It fits effective joint dynamics with evolutionary search. Its discussion of identifiability explains why a fitted parameter vector need not uniquely reveal microscopic actuator physics. This does not establish that AlphaNIST used the same fitting procedure.

**Evidence:** [PACE](papers/PACE-2509.06342.pdf) §2, Eqs. 3–7; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.2

**Follow:** [Covariance matrix adaptation evolution strategy](#cmaes), [Parameter identifiability](#identifiability)

<a id="cmaes"></a>
## Covariance matrix adaptation evolution strategy

**documented · foundation**

CMA-ES samples candidate parameter vectors from a multivariate Gaussian, ranks their objective values, and updates its mean, step size and covariance using successful search directions. It requires objective evaluations rather than derivatives through the simulator. Its search covariance is unrelated to an RL policy’s action covariance.

**Evidence:** [CMAES](papers/CMAES-1604.00772.pdf) §§1–3; [PACE](papers/PACE-2509.06342.pdf) Eq. 4

<a id="identifiability"></a>
## Parameter identifiability

**documented · foundation**

A parameter is identifiable from a measurement protocol only when different values produce distinguishable observations under that protocol. PACE gives an example: co-scaling inertia, damping and PD gains can preserve joint trajectories. Accurate trajectory fitting alone therefore does not establish a unique physical model or contact accuracy.

**Evidence:** [PACE](papers/PACE-2509.06342.pdf) §2, Eqs. 6–7

**Follow:** [Controller gains and identified robot model](#gap_controller)

<a id="bayesopt"></a>
## Bayesian optimization and acquisition functions

**documented · foundation**

Fit a probabilistic surrogate to measured objective values, then choose a new evaluation using an acquisition score balancing predicted value and uncertainty. Refinery uses Gaussian-process estimates and studies upper confidence bound, probability of improvement and expected improvement. These propose initialization conditions for policy fine-tuning; they are not SGS’s per-entry success weights.

**Evidence:** [Refinery](papers/Refinery-2510.11019.pdf) §IV-A, Algorithm 1

**Follow:** [Gaussian-process surrogate](#gaussian_process)

<a id="gaussian_process"></a>
## Gaussian-process surrogate

**documented · foundation**

A Gaussian process defines a joint Gaussian distribution over function values at any finite collection of inputs. A covariance kernel specifies their prior relationship; conditioning on observations yields a predictive mean and uncertainty. Refinery uses these to model success across initializations.

**Evidence:** [Refinery](papers/Refinery-2510.11019.pdf) §IV-A

<a id="gmm"></a>
## Gaussian mixture model

**documented · foundation**

A mixture density is a weighted sum of Gaussian component densities with nonnegative weights summing to one. Refinery fits it to successful plug initializations, samples candidate initializations, and chooses a high-density candidate at deployment. Mixture density is not itself a calibrated probability of policy success.

**Evidence:** [Refinery](papers/Refinery-2510.11019.pdf) §IV-B, Algorithm 2

<a id="osc"></a>
## Operational-space control

**documented · predecessor**

Operational-space control expresses desired motion and forces in task coordinates such as end-effector pose, and uses robot dynamics to map them to joint torques. OmniReset’s UR7e transfer controller uses Cartesian targets. AlphaNIST instead reports relative joint-position commands; copying the predecessor’s Cartesian action scale would change its interface.

**Evidence:** [OperationalSpaceControl](papers/OperationalSpaceControl.pdf) operational-space formulation; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.3.5–6; [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D

**Follow:** [Kinematic Jacobian and wrench mapping](#jacobian)

<a id="jacobian"></a>
## Kinematic Jacobian and wrench mapping

**documented · foundation**

The Jacobian J(q) maps joint velocity to local end-effector or contact velocity: v=J(q)q̇. By virtual work, a task-space wrench F maps to generalized joint force JᵀF. Near singular configurations some Cartesian motions become difficult or impossible to produce with bounded joint motion.

**Evidence:** [OperationalSpaceControl](papers/OperationalSpaceControl.pdf) kinematics and dynamic formulation

**Follow:** [Rigid pose and coordinate frames](#pose)

<a id="mcts"></a>
## Monte Carlo tree search

**documented · comparison**

AlphaGo Zero searches a tree of possible moves, guided by network move priors and value estimates. Simulations select branches using visit/value statistics, expand and evaluate leaves, and back up values. Root visit counts define improved move-selection targets. No corresponding tree-search module is reported for AlphaNIST.

**Evidence:** [AlphaGoZero](papers/AlphaGoZero.pdf) Methods: Search algorithm

**Follow:** [Self-play learning](#selfplay)

<a id="selfplay"></a>
## Self-play learning

**documented · comparison**

In AlphaGo Zero the current system plays both sides of the game. Search-generated move distributions and final game outcomes train the policy/value network, which then guides future search. A robot learning against passive assembly geometry is not this adversarial training loop.

**Evidence:** [AlphaGoZero](papers/AlphaGoZero.pdf) Methods: Self-play reinforcement learning

<a id="gap_bank"></a>
## Exact AlphaNIST reset-bank contents

**undocumented · boundary**

M, per-task/per-family counts, generation seeds, pose/velocity distributions, saved fields, rejection thresholds and the bank files are absent. A descriptive family list cannot reconstruct the distribution.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2

**Needed to resolve:** Publish the bank or deterministic generator, assets, configurations and seed list.

<a id="gap_adaptation"></a>
## Exact adaptation from OmniReset and SGS

**undocumented · boundary**

The paper does not say which grasp generator, near-goal force/path method, workspace bounds, family mixing, gravity curriculum or randomization settings were carried over. Predecessors disagree on several of these choices.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B; [OmniReset](papers/OmniReset-2603.15789.pdf) §3.2; [SGS](papers/SGS-2610.12465.pdf) Appendices A.2 and B.4

**Needed to resolve:** Release AlphaNIST reset and environment configs; distinguish inherited from changed components.

<a id="gap_sampler"></a>
## Sampler numerical and bookkeeping settings

**undocumented · boundary**

AlphaNIST leaves L and εq numerical values unspecified and does not explain short histories, repeated concurrent entry outcomes, update ordering, or any hidden temperature/flooring. SGS defaults do not exactly reproduce AlphaNIST Eq. 4.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B, Algorithm 1; [SGS](papers/SGS-2610.12465.pdf) §3.2, Appendix B.2

**Needed to resolve:** Release the sampler implementation and a tiny deterministic sampling test.

<a id="gap_distributed_sampler"></a>
## Global formula versus GPU-local banks

**undocumented · boundary**

Eq. 4 normalizes over the entire bank, but IV-E says each GPU samples a local bank from local rolling estimates. Bank replication/sharding, cross-rank statistics and task balance are not specified. These choices can change the effective global distribution.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-B and IV-E

**Needed to resolve:** Publish rank-local bank mapping, update synchronization and normalization behavior.

<a id="gap_metric"></a>
## Exact success distance and symmetry handling

**undocumented · boundary**

d_asm is called a distance between relative poses and compared with 0.001 m, but its formula, keypoints, angle-to-length conversion, rotational symmetries and task-dependent equivalences are missing. For threads, depth, turn count and orientation acceptance cannot be reconstructed.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C, Eq. 5

**Needed to resolve:** Publish the success predicate, goal transforms, units, symmetry groups and per-part examples.

<a id="gap_cost"></a>
## Control-cost coefficient and units

**undocumented · boundary**

The value of c, per-term normalization, action scaling, arm/finger inclusion, torque source and clamp rules are not reported. Mixing action, rad/s and Nm squared without this information leaves the numerical objective underdetermined.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Eq. 6; Fig. 3; IV-D

**Needed to resolve:** Release the reward code/config and logged term magnitudes before and after scaling.

<a id="gap_reward_timing"></a>
## Reward timing and termination masks

**undocumented · boundary**

Eq. 5 uses sₜ₊₁ while Eq. 6 lists t-indexed commands/speeds/torques. Per-physics-step versus policy-step aggregation, dt scaling, simultaneous-success precedence, reset masks and timeout bootstrap handling are unspecified.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; V

**Needed to resolve:** Publish the environment step order, reward manager behavior and terminal/bootstrap flags.

<a id="gap_ppo"></a>
## Full PPO and optimization configuration

**undocumented · boundary**

Numerical discount γ, GAE λ (or alternate estimator), clip ratio, value/entropy weights, optimizer parameters, learning-rate schedule, gradient clipping, reward/advantage normalization, initialization and timeout handling are absent. Standard PPO is a family of implementations.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E; [PPO](papers/PPO-1707.06347.pdf) §§3–6

**Needed to resolve:** Release complete trainer config, library versions and checkpoint metadata.

<a id="gap_encoder"></a>
## Point-cloud construction and encoder aggregation

**undocumented · boundary**

n_pts, sampling method, coordinate frame, visibility/occlusion, segmentation, noise, ordering/pooling and per-part allocation are unspecified. The two-layer figure does not uniquely define a permutation-invariant point encoder.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; IV-D

**Needed to resolve:** Publish observation generation and encoder forward pass, with tensor-shape examples.

<a id="gap_observation"></a>
## Proprioception packing and history

**undocumented · boundary**

Listed feature counts sum to 30 while Fig. 3 says 150. Five-frame stacking is plausible but unconfirmed. Pose/twist frames, joint coordinate meanings, history timing, normalization updates and distributed statistics are not fully specified.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; III-A; IV-D

**Needed to resolve:** Publish observation schema and normalization/history implementation.

<a id="gap_noise"></a>
## Gaussian exploration and action processing

**undocumented · boundary**

Covariance parameterization, initialization, variance sharing, temporal correlation, squashing/clipping and gripper mapping are missing. Gaussian output alone does not establish independent diagonal noise or gSDE. Evaluation is explicitly stochastic, but its exact distribution and postprocessing are not specified.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; IV-D; V

**Needed to resolve:** Publish action-distribution and postprocessing code for training and stochastic evaluation.

<a id="gap_network_details"></a>
## Exact neural layer settings

**undocumented · boundary**

ELU alpha, Swish beta, normalization epsilon/affine settings, parameter initialization and whether all encoder parameters are separate for actor/critic are not exhaustively enumerated. Figure 3 says separate parameters but does not provide executable architecture.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) Fig. 3; [SimBa](papers/SimBa-2410.09754.pdf) §4

**Needed to resolve:** Publish network constructors and serialized model architecture.

<a id="gap_controller"></a>
## Controller gains and identified robot model

**undocumented · boundary**

Exact stiffness/damping profiles, armature, joint friction, gripper mechanics, action scales, saturation, torque measurement and libfranka version are not given. Manufacturer docs establish interfaces, not the experiment’s chosen parameter vector.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-D; [libfranka-control](sources/libfranka-control.html) setJointImpedance

**Needed to resolve:** Publish robot asset/config, identified parameters, controller settings and identification data.

<a id="gap_simulator"></a>
## Physics versions, assets and numerical settings

**undocumented · boundary**

AlphaNIST does not enumerate simulator/library commits, collision asset checksums, SDF resolution, contact offsets, friction/restitution, timestep/decimation, solver iteration count or all randomizations. PhysX/Newton background citations do not uniquely identify the experiment’s backend/configuration.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) II-A; IV-D; VI; [Factory](papers/Factory-2205.03532.pdf) III

**Needed to resolve:** Release environment lockfile, asset manifests and full physics configuration.

<a id="gap_multi_pair"></a>
## Multi-pair observation and reset construction

**undocumented · boundary**

The rule for sampling active task subsets, maintaining fixed point counts, representing inactive/completed parts, combining partial-assembly starts, collision-valid multi-part resets, and evaluation trial counts is not fully described. Table I alone does not establish full-from-table ten-part success.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-C; V-D; Table I

**Needed to resolve:** Publish active-set sampling, scene/observation generation, reset banks and per-family evaluation.

<a id="gap_eval"></a>
## Evaluation independence and uncertainty

**undocumented · boundary**

Scaling evaluation defines a frozen mixed bank, but its separation from training banks, per-family sizes and seed-generation details are not stated. Fig. 7 uses five evaluation seeds, which must not be re-labeled five independent training runs. Table I lacks comparable uncertainty/trial details.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V; Figs. 5–7; Table I

**Needed to resolve:** Publish train/test bank overlap checks, per-training-seed checkpoints, evaluation seeds and raw outcomes.

<a id="gap_causality"></a>
## Why transfer and planning-like behavior emerge

**undocumented · boundary**

The paper proposes an explanation for sparse-objective transfer but does not isolate the causal representation/skill mechanism or prove planning optimality. This is an open empirical explanation, not evidence of proprietary technology.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V-A and V-C–D

**Needed to resolve:** Requires targeted ablations/representation tests or additional published evidence; existing descriptions cannot settle it.

<a id="gap_hardware"></a>
## AlphaNIST hardware and unseen-condition performance

**undocumented · boundary**

No AlphaNIST hardware transfer result or full twenty-active-pair result is reported. Predecessor hardware success cannot fill this gap. Robustness to real perception, latency and contact mismatch remains unestablished.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) VI

**Needed to resolve:** Requires new evaluations with sensor-derived observations and specified physical/held-out conditions.

<a id="gap_compute"></a>
## Full compute accounting

**undocumented · boundary**

GPU model, training-vs-reset-generation cost accounting, preprocessing overhead and wall-clock breakdown are not sufficiently specified to turn GPU-hours into reproducible runtime/cost estimates. Matching iterations also changes total interactions with environment count.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) IV-E; V-A

**Needed to resolve:** Publish hardware, timing logs, preprocessing costs and interaction totals.

<a id="gap_reward_comparison"></a>
## Cross-paper reward-coefficient discrepancy

**undocumented · boundary**

AlphaNIST says its .01 reach/alignment coefficients match OmniReset. OmniReset v3 Appendix A.1 and inspected UWLab main list .1 reach/distance-related weights. Terms may also differ in scaling. The exact experimental correspondence remains unresolved.

**Evidence:** [AlphaNIST](papers/AlphaNIST-2610.13354v1.pdf) V, Eq. 7; [OmniReset](papers/OmniReset-2603.15789.pdf) Appendix A.1; [UWLab-code](sources/code/UWLab-main/docs/source/publications/omnireset/index.rst) rl_state_cfg.py, reward config

**Needed to resolve:** Publish version-specific ablation configs and clarify whether effective weights or term scales differ.
