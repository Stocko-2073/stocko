# phone_girl: open questions

What we don't know yet, and how to find out. The simulator is described in
[sim/README.md](sim/README.md) and the radio link in
[protocol/PROTOCOL.md](protocol/PROTOCOL.md).

## On the RTX 5080

1. **How fast is it, and how many worlds fit in 16 GB?** Measured with
   `phone-girl-bench` (Walk, random actions). "Before" is 2026-10-28; "after"
   is 2026-10-29, with the fixes in item 2.

   | Worlds | Steps/s before | Steps/s after | ms/step after | Memory |
   | --- | --- | --- | --- | --- |
   | 1,024 | 34k | 66k | 15.6 | 0.9 GB |
   | 4,096 | 123k | 207k | 19.8 | 1.4 GB |
   | 8,192 | 196k | 298k | 27.5 | 2.4 GB |
   | 16,384 | 257k | 361k | 45.4 | 4.2 GB |
   | 32,768 | 282k | 394k | 83.2 | 8.0 GB |

   Use 16k worlds: past that, throughput barely grows. Memory is never the
   limit.
2. **Python's kernel-launch overhead.** `phone-girl-bench --profile` splits a
   control step into its parts. For each part it gives CPU time, time alone
   (with the GPU drained around it) and kernel launches. The first profile
   found three costs:
   - Body randomization launched about 2,000 kernels per step, because
     `dr.pseudo_inertia` is fully general. It is now in closed form.
   - MuJoCo Warp's `set_const` launched 565 more, over every world, on every
     step that reset an episode. It now replays from a CUDA graph, recomputes
     only the subtree masses at a reset, and runs in full every 10 steps.
   - Friction randomization resolved geom names by regex on every call.

   Result on 2026-10-29: 16k worlds went from 257k to 348k steps/s, and 1k
   worlds from 34k to 60k.

   Then the fall check moved from 16 contact sensors, one per body and
   updated every physics step, to one read of the contact list per control
   step (`tasks.env.body_on_floor`). With the same resets, 8k worlds went from
   30.2 to 28.2 ms a step (+7%). 1k worlds gained only 1%.

   What's left:
   - The physics alone takes 27 ms of a 47 ms step at 16k worlds. That makes
     about 600k steps/s the ceiling.
   - The servo step, servo telemetry and IMU are now compiled with
     `torch.compile` on CUDA; they launched about 1,300 kernels a step
     between them. A test checks the compiled code against the uncompiled
     code. On Stand it measured:

     | Worlds | Eager | Compiled | Gain |
     | --- | --- | --- | --- |
     | 1,024 | 17.5 ms | 13.7 ms | +28% |
     | 4,096 | 20.8 ms | 19.2 ms | +9% |
     | 8,192 | 28.0 ms | 25.7 ms | +9% |

     Compiling takes about 9 s per run. Inductor needs `Python.h`, so the
     project uses uv's managed Python. Also compiling mjlab's actuator write
     path and the foot sensor would add 4% at 1k–4k worlds and nothing at 8k,
     and would mean patching mjlab, so it is left as is.

   Walk with all of the above: 71k steps/s at 1k worlds, 324k at 8k, 393k at
   16k and 423k at 32k.

   Still open: after the physics, mjlab's managers spend about 6 ms launching
   small kernels while the GPU waits.
3. **CPU–GPU waits.** `phone-girl-bench --sync-debug` finds five per control
   step, all in mjlab:
   - the reset and command-resample checks (`nonzero()`), which are expected;
   - the push event's timer (`event_manager.py:282`);
   - `velocity.upright` indexing bodies with a Python list (`rewards.py:94`);
   - the velocity command copying `dt` to the GPU every step
     (`velocity_command.py:116`).

   Our own versions of `upright` and the command would remove the last two.
   Each wait also stops the CPU queuing work ahead of the GPU, which makes
   item 2 worse.
4. **Solver budget: keep Newton 15 and line search 30.** At 16k worlds the
   worlds average 3.1 Newton iterations and almost never reach the cap. The
   graph stops once every world has converged, so the cap costs nothing.
   Lower caps made the physics slower, not faster: every world at a cap
   prints a warning from the GPU. At 6 iterations or fewer, the worst
   velocity errors also passed the XL330's 0.024 rad/s resolution. Rows peak
   at 93 of 160 and contacts average 2.3 per world, so `njmax` and `nconmax`
   have room.
5. **Do the tasks learn?** Queued on cradle on 2026-10-29, one run after
   another (`logs/overnight.sh`):
   - `PhoneGirl-Stand-Ideal`, 8k worlds, 3,000 iterations;
   - `PhoneGirl-Stand`, 8k worlds, 10,000 iterations;
   - `PhoneGirl-Walk`, 8k worlds, 15,000 iterations;
   - `PhoneGirl-Stand`, 16k worlds, 6,000 iterations, to compare with 8k.

   Each takes about 0.75 s an iteration at 8k worlds. If standing stalls:
   - Is balancing on the stilt tips feasible at all with these servos? Compare
     with `PhoneGirl-Stand-Ideal`: no randomization, no latency, no stalls.
     If only the ideal robot stands, find which of the link, the battery or
     the unknowns makes the difference.
   - Shrink the action scale (0.4 rad) or the initial action noise (std 0.5).
   - The reward weights are first guesses.
6. **How much latency can a policy take?** Train with a 30 ms interval and with
   more stalls (`LinkCfg`). This sets what we must demand of the BLE link.
7. **Boxes or convex hulls for collision?** Each printed part collides as one
   box around it. The servos and the phone are their exact boxes, and each
   stilt is a box, a capsule and the 2.5 mm tip sphere. Boxes are fast on the
   GPU but loose on tapered and rounded parts:
   - **Stilts.** At home the stilt boxes are 1.1 mm apart, while the parts are
     4.6 mm apart. The reset's ±0.03 rad joint noise makes the boxes overlap
     in 43% of resets, by up to 8.7 mm, so the legs get kicked apart. Even the
     parts' convex hulls overlap in 12% of resets, so cut the leg joints'
     noise to about ±0.01 rad whatever shapes we use.
   - **Hands.** In the CAD's `collision_test_pose` the hands just touch the
     phone, but their boxes sink 4 mm into the phone's box.
   - **Hip roll.** At home it stops at 9–11° each way. Outward the leg hits
     the arm hanging beside it, and inward the stilts hit each other. Check
     whether the real robot rolls further.

   Try convex hulls of the printed parts' meshes, capped at 32–64 vertices.
   Keep the servo and phone boxes and the tip spheres. Compare throughput and
   contact counts with the boxes in `phone-girl-bench`. If hulls cost too much,
   fit a few boxes along each tapered part instead. Item 23 covers parts that
   one hull fits badly.

## On the robot

Each answer replaces a guess or narrows a randomized span.

8. **Joint travel.** The limits in `mjcf.TRAVEL_DEG` are placeholders. Find the
   real stops, then set the same values as the MCU's soft limits. The CAD's
   `collision_test_pose` is outside them for all eight leg joints: its knee is
   167° from home, and the sim allows ±110°.
9. **Electronics mass.** Weigh the board and wiring, about 20 g estimated. Then
   run `phone-girl-export --electronics-g …` and `phone-girl-build`.
10. **Do BAM's XL330 parameters fit our servos on 2S?** Record step responses
    with the capture opcode and refit with `bam.fit`. BAM's XL330 defaults to
    7.5 V, so its identification probably ran there.
11. **Backlash.** It isn't modelled. Measure it; if it's more than about 1°,
    add it.
12. **Present Current.** What does it read under load in each direction? The
    XL330 measures it at the power input, and its sign is undocumented.
13. **Battery.** Measure the pack plus wiring resistance with a load step, and
    the idle current.
14. **Phone IMU.** Find CoreMotion's noise, bias and latency (`systemUptime −
    timestamp`), and where the IMU sits in the phone.
15. **Stilt-tip friction** on the floors we'll use.
16. **Above 7.0 V.** Confirm that the XL330's input-voltage error bit is only a
    flag on these servos. A full pack exceeds the servo's Max Voltage Limit.

## Link firmware and phone app (not written yet)

17. **Firmware.**
    - Does iOS grant a 15 ms connection interval and keep it?
    - Does phase-locking to command arrivals hold?
    - Does a Fast Sync Read of 17 servos fit in about 1.2 ms at 3 Mbps?
    - Fit `LinkCfg` to the measured `command_latency` and stall rate.
18. **App.** How long does the policy take to run on the phone? It should be
    well under 1 ms of the 15 ms tick.

## Later

19. **Vision.** Which task needs the cameras? They are modelled but unused;
    plan teacher–student distillation from the blind policies.
20. **One policy for many skills.** Distill Stand and Walk into one student
    with rsl_rl's `Distillation` once both work.
21. **Upstream reports.**
    - mjlab: a reset writes zero targets into actuator delay buffers, which
      `Xl330Actuator.reset` works around.
    - mjlab: the web viewer's velocity joystick crashes on a command range of
      zero, which `tasks.env.ZeroTwist` works around.
    - BAM: its GPU M6 quadratic term drops the CPU model's sign check.
22. **mjlab pin.** Move off the pinned main commit once a release includes it.
23. **Convex decomposition, if self-collisions need it.** Kneeling needs the
    pocket on the back of each leg. Today a limb's parts never collide with each
    other, so the pocket can't jam against its own thigh. It matters if we turn
    on collisions within a limb, or if another limb, the trunk or the floor has
    to fit into it. A box fills the pocket, and so would a single hull.
    Splitting the leg mesh into several hulls keeps the pocket. To research:
    - [CoACD](https://github.com/SarahWeiii/CoACD), the tool MuJoCo's docs
      point to. [obj2mjcf](https://github.com/kevinzakka/obj2mjcf) uses it to
      make MuJoCo collision meshes.
    - [CuACD](https://arxiv.org/abs/2609.28731) (September 2026), a GPU method
      from CoACD's group, reported over 10× faster. No code link found yet.
    - [VisACD](https://arxiv.org/abs/2604.04244) (Eurographics 2026), another
      GPU method.
    - [CGAL's approximate convex decomposition](https://www.cgal.org/2026/05/11/approx_convex_decomposition/),
      in CGAL 6.2.
    - V-HACD, the older standard.

    Every extra hull adds collision pairs on the GPU, so split only the parts
    that need it.
