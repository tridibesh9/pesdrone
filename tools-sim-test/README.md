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
- `hil/`: protocol fault and parser tests
