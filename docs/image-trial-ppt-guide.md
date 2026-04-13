# One-Image Trial Guide (PPT Ready)

## Goal
Run a single image through the current detection model and produce visual outputs that clearly show:
- detected stressed points,
- clustered patches,
- fixed-wing-friendly route sequence.

## Command
From repository root:

- `& ".\\.venv\\Scripts\\python.exe" -m pip install -e ".\\pi-companion[dev]"`
- `& ".\\.venv\\Scripts\\python.exe" -m pi_companion.image_patch_trial --image "C:/path/to/your-image.jpg"`

Optional tuning example:

- `& ".\\.venv\\Scripts\\python.exe" -m pi_companion.image_patch_trial --image "C:/path/to/your-image.jpg" --cluster-radius-px 85 --speed-mps 13.5 --system-delay-s 0.45`

If you want text labels near every detection point:

- `... --show-detection-labels`

## Output Files
Default output directory: `.runtime/image-trial`

- `<image>_patch_overlay.png`
- `<image>_stress_mask.png`
- `<image>_trial_report.json`

## What To Show In PPT
1. Original image and patch overlay side by side.
2. Stress mask image to explain what the detector is picking.
3. Trial report summary:
   - number of detections,
   - number of clusters,
   - route order,
   - lead distance.

## Practical Talking Points
- Fixed-wing does not chase each point; it follows route legs across clusters.
- Spray is triggered using lead distance (`speed x delay`) not only target coincidence.
- If route heading is misaligned or timing window is not met, command stays HOLD.

## Notes
- If zero detections appear, auto-tune runs several threshold combinations automatically.
- For field use, calibrate `ground-sample-m-per-px` and timing values with real hardware.
