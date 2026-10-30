# phone_girl: experiments

Training experiments, oldest first: what we asked, what ran and what it
showed. They ran on cradle's RTX 5080 at 8,192 worlds, with the code committed
alongside each entry. Scripts written for a single experiment (task variants,
the evaluation, diagnostics) are not kept; the entries say what they did.

How we run them, since the evening of 2026-10-29 (the first entry predates
this):

- One run per question.
- Policies are trained and judged on the robot as a whole: the randomized
  robot over its default link, with the phone IMU model. No ideal robot, perfect
  sensors or reduced models.
- The hardware is fixed. Whether to change it is the owner's call, not an
  experiment's conclusion.

A policy is evaluated over 4,096 robots for 19 s each (21.5 robot-hours), in
its task's play setup, which has no shoves, unless the entry says otherwise.

The first two entries ran over BLE at a 15 ms tick. Since then the default link
is USB-C NCM at a 10 ms tick (`sim/src/phone_girl/link.py`).

## Standing on planted tips with the waist and hips (2026-10-29)

**Question.** Can phone_girl stand with both stilt tips planted, balancing
with only the waist and the hips' roll and pitch? The knees, thigh yaws and
arms hold the default pose.

**Setup.**

- `PhoneGirl-Stand` gives those five joints 0.4 rad of target per unit of
  action and the other twelve none.
  - Rewards: staying up, an upright torso, the CoM over the line between the
    tips, the default pose and stillness.
  - Penalties: 2 per tip off the floor, plus slip, action rate, copper loss,
    joint limits, and 20 for a fall.
- Shoves on the torso: up to 0.25 N along each axis, for 50–150 ms, every
  1–3 s. A forward one moves the whole robot at up to 4.9 cm/s.
- `PhoneGirl-Stand-Ideal` is the same task, shoves included, on the nominal
  robot over a perfect link. The phone IMU model stays on:
  - 5–25 ms latency, noise and biases;
  - two tilt errors fixed for each episode, up to 1° from sensor fusion and up
    to 2° from the phone sitting askew in its pocket.
- A variant of Stand-Ideal has a perfect IMU: no latency, noise, biases or
  tilt errors.

**Training**, 1,500 iterations (18 minutes) unless stopped early:

| Run | Robot | IMU | Mean episode at the end |
| --- | --- | --- | --- |
| stand2_ideal | ideal | modelled | 100 steps (1.5 s), flat after 6 minutes |
| stand2_ideal_quiet | ideal | modelled | 75 steps; stopped after 444 iterations |
| stand2_ideal_perfect_imu | ideal | perfect | 249 steps (3.7 s), still rising |
| stand2 | randomized, over the link | modelled | stopped after 180 iterations, once stand2_ideal had failed |

The quiet run explored with a noise of 0.1 instead of 0.5 and no entropy
bonus.

**Evaluation**, on the ideal robot:

| Policy | IMU | Shoves | Falls per robot-hour |
| --- | --- | --- | --- |
| stand2_ideal | modelled | none | 2,350: one every 1.5 s |
| stand2_ideal_perfect_imu | perfect | none | 106: one every 34 s |
| stand2_ideal_perfect_imu | perfect | as in training | 918: one every 3.9 s |
| stand2_ideal_perfect_imu | modelled | none | 3,440: one a second |

Nearly every fall was forward or backward. The exception was the perfect-IMU
policy on the modelled IMU, where 7% of falls were sideways.

With a perfect IMU the policy balances the way we asked:

- its tips stay down, lifting about 7 times a minute, mostly for a single
  15 ms step;
- its torso tilts 6° on average;
- its joints move as below (RMS from the default pose, and RMS speed).

| Policy | Waist | Hip pitch | Hip roll | Knees | Arms |
| --- | --- | --- | --- | --- | --- |
| stand2_ideal_perfect_imu | 4.2°, 26°/s | 8.9°, 53°/s | 1.5°, 3°/s | 1.0°, 7°/s | 0.3° |
| stand2_ideal | 9.6°, 81°/s | 3.3°, 23°/s | 0.5°, 5°/s | 0.8°, 6°/s | 0.3° |

The knees and arms move only as far as their servos give under load.

**What it showed.**

- The waist and hips can balance the robot on planted tips, but only with a
  perfect IMU. Even then, the policy fell about every half minute without
  being shoved, and every 4 s with training's shoves. It was still improving
  when training stopped.
- With the phone IMU model, it never learned. The perfect IMU removes
  latency, noise and biases as well as the tilt errors, so which of them
  matters is not yet known. The tilt errors are the likeliest:
  - each degree of tilt error misplaces the CoM by 4.8 mm at its height;
  - two tips side by side give no margin in pitch to absorb that.
- A one-off side-view check, a linear-quadratic regulator, gives a rough limit
  for shoves. It had perfect state, rigid legs and rigid arms. It recovered
  from forward shoves of only about 2 cm/s, at the default servo gain or four
  times it, and with up to 30 ms of latency. Training shoves reach 4.9 cm/s.

**Open.**

- How well can the phone's tilt be known on the robot? (TODO item 14.)
- Would memory help? The actor sees 45 ms of history, too short to notice a
  constant tilt error.

## Adding shoulder flexion and the knees (2026-10-29)

**Question.** With the tips still planted, does Stand learn if it may also
move shoulder flexion (shoulder pitch) and the knees?

**Setup.** Stand as in the entry above, but driving nine joints instead of
five: the waist, hip roll, hip pitch, shoulder pitch and the knees. The thigh
yaws, shoulder yaws, elbows and wrists hold the default pose. The rewards and
shoves are unchanged. The task variant was scratch code and is not kept.

**Runs.**

| Run | Robot | Iterations | Mean episode at the end |
| --- | --- | --- | --- |
| stand3_ideal | ideal, with the phone IMU model | 1,500 | 107 steps (1.6 s), against stand2_ideal's 100 |
| stand3 | the robot as a whole | 3,000 (38 minutes) | 67 steps (1.0 s), flat from the start |

stand3_ideal ran before the rules at the top of this file. A perfect-IMU run
was stopped after 576 iterations, when the rules were adopted.

**Evaluation.**

| Policy | Robot | Falls per robot-hour |
| --- | --- | --- |
| stand3_ideal | ideal, with the phone IMU model | 2,240: one every 1.6 s |
| stand3 | the robot as a whole | 3,460: one every 1.0 s |

Shoves made no difference to stand3, because it falls before the first one
arrives: 74,372 falls with them, 74,411 without. Every fall was forward or
backward. The tips stayed down 95% of the time; most lifts lasted a single
15 ms step.

Joint use, as RMS from the default pose and RMS speed:

| Policy | Waist | Hip pitch | Hip roll | Shoulder pitch | Knees |
| --- | --- | --- | --- | --- | --- |
| stand3_ideal | 9.4°, 74°/s | 5.4°, 37°/s | 0.4°, 2°/s | 10.3°, 69°/s | 2.8°, 9°/s |
| stand3 | 12.5°, 92°/s | 4.8°, 34°/s | 0.6°, 3°/s | 8.9°, 49°/s | 2.6°, 10°/s |

**What it showed.**

- The policies use the new joints: shoulder pitch moves about as much as the
  waist. Even so, standing on planted tips doesn't learn on the robot as a
  whole. The robot falls about once a second, from the start of training to
  the end.
- It doesn't bend the knees. It commands them to the end of their travel, 10°
  past straight, where the simulator's joint limit stops them hard: they sat
  within 0.5° of it 80% of the time. The robot has no mechanical stops, only
  its servos and self-collisions, so the policy leans on support the robot
  doesn't have.
- The overnight Stand of TODO item 5 fell under 0.5 times per robot-hour on
  the whole robot. It could use every joint and lift its tips, which it tapped
  about 8 times a second. Its shoves were velocity kicks rather than forces.

**Open.**

- Would memory help? The actor still sees only 45 ms of history: too short to
  notice a constant tilt error from how the robot drifts.
- How well can the phone's tilt be known on the robot? (TODO item 14.)
- The simulator's joint limits act as hard stops, which the robot lacks
  (TODO item 8).

## Adding shoulder flexion and the knees, over USB (2026-10-30)

**Question.** Does the faster link change the outcome of the entry above?

**Setup.** stand3 again with only the link changed: the same task variant,
8,192 worlds, 3,000 iterations and seed. Settings set in seconds keep their
meaning at either tick (`sim/README.md`, Timing), so both runs simulate the
same time.

| | stand3: BLE | stand3_usb: USB-C NCM |
| --- | --- | --- |
| Tick | 15 ms | 10 ms |
| Servo read to goals | 16–22 ms | 2.5–9.5 ms |
| Late commands | 3%, one tick late | none |
| Stalls | 0.05 a second, 50–250 ms each | none |
| Actor history, 45 ms | 3 steps | 5 steps |

USB's timings are design targets, not measurements. The phone IMU model is the
same over both links: its samples reach the policy 5–25 ms late, so over USB
the IMU is the robot's slowest input.

**Runs.**

| Run | Link | Iterations | Mean episode at the end |
| --- | --- | --- | --- |
| stand3 | BLE | 3,000 (38 minutes) | 67 steps (1.0 s), flat from the start |
| stand3_usb | USB | 3,000 (49 minutes) | 103 steps (1.0 s), flat from the start |

Over both links the mean episode reached 1.0 s within 25 iterations, peaked
near 1.15 s within 350 and settled back to 1.0 s.

**Evaluation**, each policy over its own link:

| Policy | Link | Falls per robot-hour | With training's shoves |
| --- | --- | --- | --- |
| stand3 | BLE | 3,460: one every 1.0 s | 3,460 |
| stand3_usb | USB | 3,490: one every 1.0 s | 3,490 |

Evaluated again with today's code over BLE, stand3 fell 74,490 times against
74,411 in the entry above, and its other measures didn't change: nothing but
the link separates the two runs. Every fall was forward or backward, and the
tips stayed down 95% of the time, over both links.

Joint use, as RMS from the default pose and RMS speed:

| Policy | Waist | Hip pitch | Hip roll | Shoulder pitch | Knees |
| --- | --- | --- | --- | --- | --- |
| stand3 | 12.5°, 92°/s | 4.8°, 34°/s | 0.6°, 3°/s | 8.9°, 49°/s | 2.6°, 10°/s |
| stand3_usb | 13.8°, 93°/s | 6.4°, 30°/s | 0.5°, 3°/s | 6.0°, 35°/s | 2.4°, 9°/s |

Both policies command the knees to the end of their travel nearly all the
time: the targets' 5th to 95th percentiles sit at the stop. The knees sat within
0.5° of it 57–65% of the time over USB, against 80–84% over BLE.

Tips lift on 2.4% of a foot's control steps over USB and 2.5% over BLE. With
1.5 times the steps per second, the evaluation counts about 1.5 times as many
lifts a second over USB, so its per-second counts and stance lengths can't be
compared between ticks. A one-off check found that most lifts aren't balancing:

- about half come in the last 0.1 s before a fall;
- a fifth to a quarter are the step that resets a robot, which the evaluation
  counts as a lift: the respawned robot's tips are down in under half of
  those samples;
- away from falls and resets, a foot lifts on under 1% of control steps.

**What it showed.**

- The faster link changes nothing here. Over USB as over BLE, standing on
  planted tips with the waist, hips, shoulder pitch and knees doesn't learn on
  the robot as a whole. The robot falls about once a second, from the start of
  training to the end, shoved or not.
- That fits stand3_ideal, which had no link delay or randomization and still
  fell every 1.6 s. Down to USB's design targets, the link isn't what stops
  this task. In the first entry, the ideal robot learned to balance on planted
  tips only with a perfect IMU.
- The policy still leans on the knee stops the robot doesn't have.
- The same training takes 49 minutes over USB instead of 38.

**Open.**

- How well can the phone's tilt be known on the robot, and how late does
  CoreMotion deliver? (TODO item 14.)
- Would memory help? The actor still sees 45 ms of history, now 5 steps.
- How much latency can a policy take (TODO item 6)? This task can't say, since
  it fails over either link. Walk can.
- The simulator's joint limits act as hard stops, which the robot lacks
  (TODO item 8).
