# Surface route evaluation

48/48 routes completed; 0 solver warnings. All current presets use the same baseline controller, routes and seeds.

Each row aggregates seeds for one route, wheel model and timestep. Time is the mean of successful runs only; errors and slip include all runs. Stop travel averages completed waypoint stops with a recorded zero command.

| Surface | Route | Wheels | dt (ms) | Complete | Time (s) | Tracking RMS (mm) | Slip RMS (mm/s) | Stop travel (mm) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| concrete | five_waypoints | lugs | 1 | 3/3 | 18.69 | 24.97 | 10.50 | 4.81 |
| concrete | five_waypoints | lugs | 2 | 3/3 | 18.73 | 24.94 | 12.62 | 4.89 |
| concrete | five_waypoints | smooth | 1 | 3/3 | 18.68 | 25.92 | 12.60 | 5.77 |
| concrete | five_waypoints | smooth | 2 | 3/3 | 18.68 | 25.99 | 14.34 | 5.57 |
| concrete | out_and_back | lugs | 1 | 3/3 | 13.93 | 22.66 | 9.51 | 5.16 |
| concrete | out_and_back | lugs | 2 | 3/3 | 13.95 | 22.22 | 10.04 | 5.09 |
| concrete | out_and_back | smooth | 1 | 3/3 | 13.90 | 21.51 | 10.93 | 5.75 |
| concrete | out_and_back | smooth | 2 | 3/3 | 13.90 | 21.57 | 11.99 | 5.64 |
| rough_concrete | five_waypoints | lugs | 1 | 3/3 | 18.67 | 24.57 | 10.57 | 4.67 |
| rough_concrete | five_waypoints | lugs | 2 | 3/3 | 18.51 | 25.46 | 11.77 | 4.12 |
| rough_concrete | five_waypoints | smooth | 1 | 3/3 | 19.09 | 25.36 | 11.02 | 3.77 |
| rough_concrete | five_waypoints | smooth | 2 | 3/3 | 18.49 | 26.17 | 11.05 | 3.32 |
| rough_concrete | out_and_back | lugs | 1 | 3/3 | 14.07 | 23.53 | 5.88 | 5.91 |
| rough_concrete | out_and_back | lugs | 2 | 3/3 | 14.21 | 24.01 | 5.84 | 6.00 |
| rough_concrete | out_and_back | smooth | 1 | 3/3 | 14.17 | 24.76 | 9.58 | 5.58 |
| rough_concrete | out_and_back | smooth | 2 | 3/3 | 14.25 | 23.83 | 10.04 | 5.30 |

## Method and limits

- **Sampling**: 50 Hz after physics/forward; 45 s episode limit; fixed layout, no domain randomization; reset excluded.
- **Completion**: Stop at every waypoint using the existing 12 cm / 0.08 m/s / 0.2 rad/s, 15-control-step arrival test.
- **Travel time**: Simulated elapsed time through the final arrival, including turns and required stop dwell; failures have null completion time.
- **Tracking**: RMS and maximum XY distance to the active finite nominal route segment, sampled uniformly in time; not distance to the goal.
- **Slip**: Tangential speed at loaded drive-wheel contact points against static terrain, from point Jacobians and qvel. Normal force must exceed 1e-6 N. RMS/P95 pool unweighted contacts across 50 Hz samples; no-contact steps are omitted and counted separately. Includes longitudinal and lateral scrubbing, not a slip ratio or a force-weighted measure.
- **Stopping**: For each waypoint: first zero wheel-speed target to arrival, entry speed, XY travel during that interval, final goal error and speed. Includes any remaining success dwell and later controller correction; not a passive coast test or guaranteed monotonic deceleration.
- **Aggregation**: Table values average per-run RMS metrics across seeds, and completed stop travel across stops; raw values remain in JSON.

The raw JSON includes every run, stop, seed, contact sample count, solver warning count, software versions, and source hashes. These estimated presets are not calibrated material measurements. This evaluates the existing baseline controller; it does not establish hardware accuracy or timestep convergence.
