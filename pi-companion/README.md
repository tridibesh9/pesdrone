# Pi Companion

Mission orchestration, safety supervision, perception pipeline, and hardware interfaces for Raspberry Pi 5.

## Run demo
```bash
pip install -e .[dev]
pi-companion-demo
pi-companion-multi-patch-demo
pi-companion-image-trial --image C:/path/to/field-image.jpg
```

## One-Image Trial Outputs
The image trial command generates PPT-ready files in `.runtime/image-trial` by default:
- `<image>_patch_overlay.png`: original image with detection points, patch clusters, and route arrows
- `<image>_stress_mask.png`: binary stressed-vegetation mask used for patch finding
- `<image>_trial_report.json`: counts, coordinates, and route order

## Main modules
- `pi_companion.safety_supervisor`
- `pi_companion.mission_orchestrator`
- `pi_companion.perception`
- `pi_companion.io`
- `pi_companion.telemetry`
- `pi_companion.planning`
- `pi_companion.image_patch_trial`
