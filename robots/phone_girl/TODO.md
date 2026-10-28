# phone_girl: open questions

What we don't know yet, and how to find out. The simulator is described in
[sim/README.md](sim/README.md) and the radio link in
[protocol/PROTOCOL.md](protocol/PROTOCOL.md).

## On the RTX 5080

1. **How fast is it, and how many worlds fit in 16 GB?**
   Run `uv run phone-girl-bench` (1k–8k worlds). Use the largest world count
   before throughput stops scaling or memory runs out.
2. **Does Python's kernel-launch overhead matter?** The servo, battery, IMU and
   link models run as a few dozen small torch kernels per physics step, between
   MuJoCo Warp's graph launches. Profile one step (`nsys`, or time it with and
   without the actuator). If the overhead is a large share, try two fixes:
   `torch.compile` on `Xl330Actuator.compute`, or move it into a Warp kernel
   captured with the physics.
3. **Are there CPU–GPU waits besides mjlab's reset check?**
   `uv run phone-girl-bench --sync-debug` lists each one.
4. **Is the solver budget right?** Newton 15, line search 30, `njmax` 160 and
   `nconmax` 24 were sized on the CPU. Check the bench's `newton`, `rows` and
   `contacts` maxima, then try fewer iterations.
5. **Do the tasks learn?** Train `PhoneGirl-Stand`, then `PhoneGirl-Walk`. The
   CPU run only proved that the training loop works. If standing stalls:
   - Is balancing on the stilt tips feasible at all with these servos and about
     17 ms of latency? Try with `Randomization.scale = 0` and no link delay.
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
