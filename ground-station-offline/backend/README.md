# Ground Station Offline Backend

Local backend for telemetry ingestion, spray event storage, and operator commands.

## Run
```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
```

## Endpoints
- `GET /health`
- `POST /telemetry`
- `POST /spray-event`
- `POST /command/emergency-spray-disable`
