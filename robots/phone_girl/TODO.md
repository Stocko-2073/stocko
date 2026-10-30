# phone_girl: open questions

What we don't know yet, and how to find out. The simulator is described in
[sim/README.md](sim/README.md), the link to the MCU (USB-C NCM by default, or
BLE) in [protocol/PROTOCOL.md](protocol/PROTOCOL.md), and training experiments in
[EXPERIMENTS.md](EXPERIMENTS.md).

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

   Past 16k worlds, throughput barely grows, and memory is never the limit.
   For training, though, 8k worlds learn as fast per hour as 16k (item 5).

   The table above was measured over BLE at a 15 ms tick. Over USB the tick is
   10 ms, so a control step is 4 physics steps instead of 6. Measured the same
   day, 2026-10-29, after the stilt hulls (item 7):

   | Worlds | USB, 10 ms | BLE, 15 ms | Simulated time per second, USB vs BLE |
   | --- | --- | --- | --- |
   | 1,024 | 77k steps/s, 13.3 ms | 61k, 16.7 ms | −17% |
   | 4,096 | 251k, 16.3 ms | 195k, 21.0 ms | −14% |
   | 8,192 | 375k, 21.8 ms | 289k, 28.4 ms | −13% |
   | 16,384 | 475k, 34.5 ms | 361k, 45.4 ms | −12% |

   Each control step costs about the same overhead, so 1.5× as many steps cost
   12–17% of simulated time. In training at 8k worlds, an iteration still
   simulates 0.36 s per robot but takes 0.99 s instead of 0.75 s. The batch is
   1.5× larger and the actor's history longer, so learning takes 0.20 s instead
   of 0.13 s. A 3,000-iteration run takes about 50 minutes instead of 38.
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
5. **Do the tasks learn? Yes.** Trained on cradle overnight on 2026-10-29,
   one run after another (`logs/overnight.sh` there). Falls are counted over
   4,096 robots for 19 s each (21.5 robot-hours) with full randomization and
   link lag. Everything in this item ran over BLE at a 15 ms tick, before USB
   became the default link:

   | Task | Worlds | Full episodes after | Return within 3% after | Falls per robot-hour |
   | --- | --- | --- | --- | --- |
   | Stand-Ideal | 8k | 2 min | 10 min | 0 on its own task |
   | Stand | 8k | 8 min | 45 min | under 0.5; 1.6 with pushes |
   | Stand | 16k | 8 min | 45 min | under 0.5; 2.1 with pushes |
   | Walk | 8k | 18 min | 90 min | about 4 |

   "Full episodes" is when the mean episode first reaches 97% of its final
   length; the return is compared with the run's final return.

   - The randomization is needed: the ideal policy falls about once a second
     on the randomized robot with link lag.
   - 8k worlds learned as fast per hour as 16k (one run each): a 16k
     iteration takes 1.7× as long for twice the samples. Train at 8k, for 45
     to 90 minutes a run.
   - Stand never stands still, even on the ideal robot. It taps at about 8
     steps a second, with 60 ms swings and both tips down 46% of the time. On
     two point feet that may be the only way to balance. Check it on the
     robot: impacts, backlash (item 11) and servo wear are not well modelled.
   - Walk steps about 5.5 times a second, with 150 ms swings. It turns at 97%
     of the commanded rate and moves at 85–87% of the commanded speed. On a
     zero command it keeps stepping in place.
   - Neither slides. A tip moves 1.5–2.5 mm over a stance, as much on
     slippery floors as on grippy ones. But until 2026-10-29 `foot_slip`
     paired each foot's speed with the other foot's contact (the contact
     sensor lists the right foot first), so these runs were penalized for
     fast swings instead of slip. Retrain both before tuning further.
   - Stand with planted tips, moving only the waist and hips (since
     2026-10-29), is much harder. With the phone IMU model the ideal robot
     didn't learn it and falls every 1.5 s. With a perfect IMU it learned the
     intended balance but still fell about every 34 s. Also driving shoulder
     pitch and the knees didn't help: on the robot as a whole it falls about
     once a second. See [EXPERIMENTS.md](EXPERIMENTS.md).
6. **How much latency can a policy take?** Train with longer turnarounds, late
   commands and stalls (`LinkCfg`). This sets what we must demand of the link,
   and how much USB gains over BLE.
7. **Boxes or convex hulls for collision?** Each printed part collides as one
   box around it, except the top of each stilt. The servos and the phone are
   their exact boxes, and each stilt is a hull, a capsule and the 2.5 mm tip
   sphere. Boxes are fast on the GPU but loose on tapered and rounded parts:
   - **Stilts.** Their top boxes were 1.1 mm apart at home, where the parts
     are 4.6 mm apart, so hip roll stopped at 0.5° inward. Since 2026-10-29
     the tops are their convex hulls (80 vertices), 4.6 mm apart, and the
     reset's joint noise is ±0.01 rad, so they never start overlapping. The
     hulls cost 15%: Walk at 8k worlds went from 324k to 276k steps a second.
     Fewer hull vertices, or a few boxes along the taper, might win it back.
   - **Hands.** In the CAD's `collision_test_pose` the hands just touch the
     phone, but their boxes sink 4 mm into the phone's box.
   - **Hip roll** stops at about 2° inward, on the other stilt, and 5.5°
     outward, where the hip-pitch servo meets the hand hanging beside it.
     That is the printed parts' clearance too (6.4 mm at home), not the
     boxes'. Hands held further out would free it.

   Hulls for the other printed parts, capped at 32–64 vertices, would fix the
   hands; compare their cost in `phone-girl-bench` as for the stilts. Item 23
   covers parts that one hull fits badly.

## On the robot

Each answer replaces a guess or narrows a randomized span.

8. **Joint travel.** The robot has no mechanical stops: a joint turns until
   parts collide. `mjcf.TRAVEL_DEG` sets the soft limits the MCU clamps goals
   to. They are placeholders, except the knees': 10° past straight, 3° beyond
   the default pose, and 167° the other way to the CAD's
   `collision_test_pose`. That pose is still outside the other leg joints'
   travel. The simulator also enforces these limits as hard stops, which the
   robot lacks, and a Stand policy pressed its knees against them
   (EXPERIMENTS.md).
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
    timestamp`), and where the IMU sits in the phone. Measure how well the
    phone's tilt in its pocket can be calibrated: standing on planted tips
    learned only with a perfect IMU (item 5).
15. **Stilt-tip friction** on the floors we'll use.
16. **Above 7.0 V.** Confirm that the XL330's input-voltage error bit is only a
    flag on these servos. A full pack exceeds the servo's Max Voltage Limit.

## Link firmware and phone app (not written yet)

17. **Firmware.**
    - Over USB-C NCM, the default:
      - Does the iPhone bring up the ESP32-S3's NCM interface and take the
        MCU's DHCP lease?
      - What are the UDP round trip and its jitter? Fit `LinkCfg.turnaround_s`,
        and the late and stall terms if there are any. Today's are placeholders.
      - Power: the phone, as USB host, sources VBUS. The MCU runs from the pack
        and mustn't back-feed it.
    - Over BLE, if we use it:
      - Does iOS grant a 15 ms connection interval and keep it?
      - Does phase-locking to command arrivals hold?
      - Fit `ble_link()` to the measured `command_latency` and stall rate.
    - Does a Fast Sync Read of 17 servos fit in about 1.2 ms at 3 Mbps?
18. **App.** How long does the policy take to run on the phone? It should be
    well under 1 ms of the 10 ms tick.

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
