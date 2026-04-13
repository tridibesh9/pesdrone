# Simulation and Hardware-Loop Tests

## Run tests
```bash
cd pi-companion
pip install -e .[dev]
cd ..
pytest tools-sim-test
```

## Suites
- `sitl/`: mission safety behavior tests
- `sitl/test_multi_patch_planner.py`: multi-patch clustering, route, and spray timing tests
- `sitl/test_image_patch_trial.py`: one-image detection-to-cluster route visualization tests
- `hil/`: protocol fault and parser tests

## Utility
- `create_sample_trial_image.py`: generates a synthetic field image for quick trial demos
