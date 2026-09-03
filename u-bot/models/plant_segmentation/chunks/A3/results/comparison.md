| approach | squash_leaf | squash_petiole | grass | broadleaf_weed | straw | fruit | other | **mean IoU** | grass→squash | compute |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ZeroPlantSeg (recorded baseline, charitable mapping) | 0.6760 | 0.0000 | 0.0000 | 0.4903 | 0.6076 | 0.0000 | 0.0000 | **0.2534** | 53.0 % | ~8 min/image (SAM ViT-H + OVSeg CLIP per mask + GroundingDINO per mask + DBSCAN), MPS |
| 1. shape prior over SAM regions (depth-4 tree, blocked CV) | 0.6502 | 0.1444 | 0.4152 | 0.0000 | 0.5113 | 0.0000 | 0.0000 | **0.2459** ±0.0180 | 22.5 % | SAM ViT-H 776 s + features 1.5 s + fit <1 s |
| 2. shape prior + A2 height_above_soil | 0.6609 | 0.1707 | 0.4397 | 0.0629 | 0.6577 | 0.0001 | 0.0000 | **0.2846** ±0.0336 | 34.5 % | as above + A2 products (already on disk; A2 itself is ~10 min) |
| 3. frozen DINOv2 patch features + logistic probe, 42 patches | 0.7634 | 0.3598 | 0.4084 | 0.3327 | 0.7292 | 0.8170 | 0.4656 | **0.5537** ±0.0197 | 25.3 % | DINOv2-base features 4.7 s (70 tiles, MPS) + fit 0.01 s + predict 0.03 s; no SAM |
| 4. open-vocabulary: SigLIP 2 so400m over SAM regions (crop_fill, descriptive, 12-template ensemble) | 0.7027 | 0.1940 | 0.1025 | 0.1830 | 0.5846 | 0.9362 | 0.0809 | **0.3977** | 84.9 % | SAM ViT-H 776 s + crops ~6 s + SigLIP2-so400m encode 103 s, MPS |
