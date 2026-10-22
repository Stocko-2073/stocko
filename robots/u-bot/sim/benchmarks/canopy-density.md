# Representative lawn canopy density experiment

An opt-in 5 cm canopy uses **20,000 shoots/m²**, with low/high cases of 4,000 and 36,000. This is a representative scenario, not a measured population average for residential lawns.

## Evidence and assumptions

[Badra et al. (2006), *Canadian Journal of Plant Science*, 86:1107–1118](https://doi.org/10.4141/P05-242) reports a commercial Kentucky bluegrass sod survey spanning 4,000–36,000 tillers/m² (p. 1113), and a medium-density threshold of 12,000 tillers/m². Its own field trial maintained grass at 50 mm, with 38 mm clipping harvests. These are different datasets: the survey does not establish the mean density of a 5 cm home lawn. [Author-hosted full text](https://www.researchgate.net/publication/259475628_Effect_of_leaf_nitrogen_concentration_versus_CND_nutritional_balance_on_shoot_density_and_foliage_colour_of_an_established_Kentucky_bluegrass_Poa_pratensis_L_turf).

20,000 is our chosen midpoint of the reported survey range. A shoot/tiller carries multiple leaves; it is not a blade. **Three blades per shoot** is an explicit modeling assumption, giving 60,000 blades/m² at the reference density. Species, maintenance, moisture, leaf width, and blade stiffness still need local measurements.

## Model

`GrassCanopy(shoot_density=20000, blades_per_shoot=3)` enables this experiment. `shoot_density=None` preserves the original sparse illustration (about 178 blades/m²) and density-independent drag. Defaults remain unchanged.

For explicit densities, the existing passive force magnitude is multiplied by `shoot_density × blades_per_shoot / 60000`. Resistance is 30 N/m of effective wheel width **at the reference blade density**. This is an assumed linear bulk law, not a stiffness value inferred from the density research. The sparse prototype has the same reference drag by construction; the video therefore isolates visual coverage, while the low/high runs exercise the force scaling. Zero density produces no canopy drag or blades.

Roots occupy a deterministic jittered grid across the 6 × 6 m field. Grid rounding produces 20,022.25 shoots/m² at the reference setting (0.11% above target). Each shoot renders three distinct 1 mm diameter blade proxies of 5 cm root-to-tip length, with differing lean. This is not botanical leaf geometry. Only shoots within a 0.7 m display radius are drawn, nearest first, subject to scene capacity. Physical canopy density covers the whole grass field regardless of camera or geometry budget. The showcase uses reduced capsule tessellation and disables shadows/reflections to limit rendering cost. It reserves 100,000 geometries so the entire local disk fits; ordinary viewers with smaller budgets show a smaller disk.

Blade bending/recovery remains illustrative and cannot affect trajectories. Only displayed shoots are brushed; newly displayed areas do not reconstruct past wheel tracks. Soil collision, grip and rolling friction are unchanged. No stem elasticity, entanglement, vertical support, or permanent flattening is modeled.

## Results

16/16 five-waypoint routes completed; no solver warnings in navigation or passive coasting. Seed 0, both wheel models, 1/2 ms physics. Coasting follows two seconds of powered travel and three seconds with motor servos disabled. Entry speeds differ, so distances are system responses rather than isolated material coefficients.

| Shoots/m² | Wheels | dt (ms) | Route (s) | Coast entry (m/s) | Coast path (mm) | Simulation / wall time |
|---|---|---:|---:|---:|---:|---:|
| Prototype | smooth | 1 | 22.88 | 0.252 | 58.0 | 4.38× |
| Prototype | smooth | 2 | 22.96 | 0.248 | 56.2 | 8.03× |
| Prototype | lugs | 1 | 23.72 | 0.241 | 41.3 | 4.64× |
| Prototype | lugs | 2 | 23.88 | 0.242 | 38.9 | 8.55× |
| 4000 | smooth | 1 | 20.16 | 0.282 | 78.9 | 4.49× |
| 4000 | smooth | 2 | 20.22 | 0.281 | 78.1 | 8.35× |
| 4000 | lugs | 1 | 20.78 | 0.274 | 58.4 | 4.64× |
| 4000 | lugs | 2 | 20.78 | 0.272 | 57.2 | 8.55× |
| 20000 | smooth | 1 | 22.88 | 0.252 | 58.0 | 4.52× |
| 20000 | smooth | 2 | 22.96 | 0.248 | 56.2 | 8.28× |
| 20000 | lugs | 1 | 23.72 | 0.241 | 41.3 | 4.61× |
| 20000 | lugs | 2 | 23.88 | 0.242 | 38.9 | 8.54× |
| 36000 | smooth | 1 | 25.54 | 0.227 | 40.9 | 4.46× |
| 36000 | smooth | 2 | 25.70 | 0.227 | 41.2 | 8.16× |
| 36000 | lugs | 1 | 26.46 | 0.221 | 35.9 | 4.31× |
| 36000 | lugs | 2 | 26.58 | 0.220 | 34.7 | 8.02× |

Across matched wheel/density cases, changing from 1 ms to 2 ms changes route time by at most 0.16 s. This checks timestep sensitivity on one route and seed; it does not establish numerical convergence. Tests cover density scaling, passivity, zero density, spatial shoot counts, geometry budgets, fixed blade length, recovery/reset, and identical trajectories with/without rendering. Timing is a single navigation rollout, includes metrics, excludes rendering, and was collected alongside other checks. It is an indicative local measurement, not a controlled performance benchmark. Density adds no collision objects or physics degrees of freedom.

[Raw results](canopy-density.json) include each waypoint arrival, tracking/slip metrics, coasting results, warnings and timing. This controller did not issue exact zero commands on these routes, so command-to-stop fields are null; use the passive-coasting runs for the stopping comparison, and the video for explicit braking/reversal commands.

## Reproduce

From `sim/`:

```sh
.venv/bin/python -m ubot_sim.canopy_density_experiment
.venv/bin/python -m ubot_sim.canopy_showcase --density
.venv/bin/python -m pytest -q
```

[Watch the 14-second comparison](../videos/canopy-density-showcase.mp4). Both sides receive the same drive/brake/reverse commands and have equal estimated reference drag. The dense circular patch is the display radius, not a physical boundary. The JSON sidecar records canopy settings, realized density, displayed shoot count, render wall time and motion samples. Playback runs at real time; offline rendering took 174 s for the 14 s, 1280 × 720, 25 fps video on this machine. The dense disk contains 30,827 displayed shoots / 92,481 blades. Both panels have zero solver warnings and exactly matching sampled speeds, as expected at the reference drag. The final full suite passed all 151 tests.
