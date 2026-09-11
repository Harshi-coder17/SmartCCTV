# SmartCCTV - SIH26187
## Software-Defined Border Video Intelligence Platform

**AI-Based Intelligent Video Analytics for Border Surveillance**
*Smart India Hackathon 2026 - Ministry of Home Affairs*

---

## Overview

SmartCCTV is a production-grade, edge-first intelligence layer that upgrades existing CCTV infrastructure into an actionable, evidence-backed security platform. It does not replace cameras - it makes them intelligent.

**Core Capabilities:**
- Real-time person and vehicle detection and tracking
- Cross-camera Re-Identification (ReID) without requiring face visibility
- Virtual fence and tripwire crossing detection with direction enforcement
- Loitering, abandoned object, and crowd anomaly detection
- Explainable risk scoring (not a black box)
- Evidence packages with SHA-256 integrity chain
- Secure RBAC-based command dashboard with real-time WebSocket alerts
- Camera health monitoring and tamper detection
- Offline-resilient edge-first architecture

---

## Architecture

```
[CCTV / Video Files / RTSP Streams]
          |
    [Stream Manager]   <-- multi-camera asyncio workers
          |
    [Perception Engine]
      YOLOv8 + ByteTrack  --> Detection + Tracking
      OSNet + FAISS       --> Cross-camera ReID
      Face Engine         --> Face detection (Haar) / Recognition (InsightFace optional)
      ANPR Engine         --> License plate OCR
      Pose Engine         --> Behavioral signal extraction
          |
    [Event Intelligence]
      Zone Engine         --> Zone intrusion, tripwire crossing, direction violation
      Loitering Monitor   --> Dwell-time state machines
      Abandoned Object    --> Person-object separation tracking
      Crowd Engine        --> Group spacing, density analysis
      Risk Engine         --> Step 29 weighted scoring formula
          |
    [Correlation Engine]
      Topology Graph      --> Camera adjacency, travel-time feasibility
      Event Matcher       --> Cross-camera event fusion, movement timeline
      Entry-point Check   --> Origin verification (camera-health-aware)
          |
    [FastAPI Backend]
      REST API + WebSocket --> Alerts, events, evidence, admin
      JWT RS256 Auth       --> httpOnly cookies, refresh tokens, revocation
      RBAC                 --> operator / supervisor / admin / auditor roles
      AES-256 Evidence     --> Encrypted clip storage
      SHA-256 Ledger       --> Append-only integrity chain (Hyperledger-ready interface)
      Audit Log            --> Every action logged, structured
          |
    [React Dashboard]
      Real-time AlertFeed  --> WebSocket, sorted by risk score
      Camera Grid          --> Live MJPEG tiles with health status
      GIS Map              --> Leaflet zones, camera pins, event markers
      Evidence Panel       --> Pre/post clips, hash verification, risk breakdown
      Track Timeline       --> Cross-camera movement visualization
      Admin Panel          --> Zone config, tripwires, personnel enrollment
      Audit Log Viewer     --> Tamper-evident action history
```

---

## Quick Start (Development)

### Prerequisites
- Python 3.11+
- Node.js 20+
- pip and npm

### 1. Clone and Setup Environment

```bash
cd SmartCCTV
cp .env.example .env
# Edit .env if needed (defaults work for demo)
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database and Seed Demo Data

```bash
python scripts/setup_db.py
# Note the admin password printed - save it securely
```

### 4. Start the Backend

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The backend will:
- Auto-create RSA key pair for JWT signing
- Initialize SQLite database
- Load demo cameras from data/cameras.json
- Start processing video.mp4 and video2.mp4
- Serve API at http://localhost:8000
- API docs at http://localhost:8000/docs

### 5. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at: http://localhost:5173

Login with: username `admin`, password from step 3.

---

## Production Deployment (Docker Compose)

```bash
# Set required secrets in .env
cp .env.example .env
# Edit: POSTGRES_PASSWORD, and optionally FACE_BACKEND=insightface

docker compose up -d

# First time: initialize DB
docker compose exec backend python scripts/setup_db.py

# Dashboard at http://localhost:3000
# API at http://localhost:8000
```

---

## Feature Details

### Object Detection and Tracking
- **Model:** YOLOv8n (upgradeable to YOLOv8m/l/x for higher accuracy)
- **Tracker:** ByteTrack (handles occlusion better than DeepSORT)
- **Classes:** person, car, motorcycle, bus, truck
- **GPU:** Auto-detects NVIDIA CUDA (RTX 5060 supported), falls back to CPU

### Cross-Camera Re-Identification
- **Model:** OSNet (torchreid) - whole-body appearance embedding (no face required)
- **Index:** FAISS with top-2 retrieval and margin check
- **Safety:** Ambiguous matches create provisional identities - never auto-merged
- **Gate:** Only compares cameras that are topologically adjacent and travel-time feasible

### Face Capabilities
- **Default (Haar):** OpenCV Haar cascade - face detection only, no embedding
- **Optional (InsightFace):** RetinaFace detection + ArcFace 512-d embeddings
  - Enable by setting FACE_BACKEND=insightface in .env
  - Requires insightface and onnxruntime (included in requirements.txt)
  - Adds watchlist matching and authorized personnel recognition
  - Liveness detection via MediaPipe Face Mesh (anti-spoofing)

### Risk Scoring (Explainable)
Transparent weighted formula - no black box:
```
identity_score = zone_violation*30 + no_traceable_origin*25 + route_anomaly*15 + off_hours*10
context_multiplier = zone_sensitivity_factor * time_factor
behavior_contribution = behavior_signals * context_multiplier
  (capped at 5 if no identity flag fired)
risk_score = identity_score + behavior_contribution
```
All weights configurable in data/risk_weights.json - no restart required.

### Evidence Integrity
- Every evidence file: AES-256-GCM encrypted at rest
- SHA-256 hash computed and stored in append-only ledger
- Chain-hash: each ledger entry includes hash of previous entry
- Operator can verify integrity with one click in dashboard
- Interface-compatible with Hyperledger Fabric (set HASH_LEDGER_BACKEND=hyperledger when network is available)

### Security
- JWT RS256 (asymmetric) - 60-minute access tokens + 7-day refresh
- httpOnly cookies (XSS-resistant)
- Access token revocation list (immediate revoke on compromise)
- RBAC: operator / supervisor / admin / auditor
- AES-256-GCM evidence encryption
- Structured audit log (every action logged with actor, role, IP, timestamp)
- CORS restricted to configured origins

---

## Camera Zone Editor

Draw zone polygons and tripwires interactively:

```bash
python scripts/zone_editor.py --camera CAM-01 --video video.mp4
```

Controls:
- Left click: add polygon point
- Right click: close zone polygon
- `z`: zone mode | `t`: tripwire mode
- `1-5`: set sensitivity level
- `s`: save | `h`: help | ESC: exit

---

## Adding a New Camera

1. Run the zone editor to define zones for the new camera
2. Either: add camera via Admin Panel in dashboard
   Or: add to data/cameras.json and re-run setup_db.py
3. Backend stream manager will auto-detect and start processing

For RTSP cameras: set `rtsp_url` to the full RTSP URL (e.g., `rtsp://admin:pass@192.168.1.100/stream`)

---

## Project Structure

```
SmartCCTV/
├── backend/              Python FastAPI backend
│   ├── main.py           Application entry point
│   ├── config.py         All configuration (Pydantic Settings)
│   ├── database.py       SQLAlchemy async DB setup
│   ├── models/           ORM models (Camera, Event, Alert, etc.)
│   ├── api/              REST routes (auth, cameras, events, alerts, admin)
│   ├── core/             Pipeline workers
│   │   ├── stream_manager.py    Multi-camera orchestrator
│   │   ├── camera_health.py     Tamper and health monitoring
│   │   ├── perception/          Detection, ReID, Face, ANPR, Pose
│   │   ├── events/              Zone, Loitering, Risk scoring
│   │   └── correlation/         Cross-camera topology and matching
│   ├── security/         JWT, AES-256, SHA-256 ledger, RBAC
│   └── utils/            Evidence builder, audit logger, model registry
├── frontend/             React TypeScript dashboard
├── scripts/              setup_db.py, zone_editor.py
├── data/                 cameras.json, zones.json, risk_weights.json
├── evidence/             Encrypted evidence storage
├── models_cache/         Downloaded model weights
├── logs/                 Audit log and hash ledger
├── docker-compose.yml    Production deployment
├── Dockerfile            Backend container
└── .env.example          Configuration template
```

---

## Evaluation Metrics

| Metric | Measurement |
|--------|-------------|
| Detection precision/recall | Annotated clips per scenario |
| Track continuity | Identity switches on labeled sequences |
| Event precision | Scenario scripts + reviewed alert log |
| Alert latency | Timestamp each pipeline stage (median + P95) |
| Evidence completeness | Automated integrity checklist |
| False alert rate | Controlled clips, count invalid alerts per camera-hour |

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| SIH Demonstrator | In Progress | Integrated platform with recorded feeds |
| Technical Hardening | Planned | Containerized, threat-model controls, test automation |
| Controlled Pilot | Planned | Site survey, camera capability register, policy workshops |
| Field Trial | Future | Limited-camera deployment with operators in the loop |
| Operational Scale | Future | Multi-sector under owning-agency governance |

---

## Known Limitations

- No AI model can infer hostile intent from appearance alone. The system reports observable events and configurable risk factors.
- Cross-camera ReID can produce false associations under similar clothing or changing light - topology gates and operator review are essential controls.
- Visible-light night video is limited by sensor physics. Enhancement may assist review but cannot create detail absent from the original signal.
- ANPR quality depends on camera angle, resolution, and motion blur - confidence is always reported, not asserted.
- Prototype performance on test footage is not evidence of field readiness. Field claims require controlled trials.

---

## Security Notice

This system processes biometric and sensitive security data. Before any operational deployment:
- Complete a security assessment
- Obtain appropriate data governance approvals
- Ensure all storage is physically located under the operating agency's control
- Review and comply with applicable data protection regulations (DPDP Act)
- All biometric modules (face recognition, ANPR watchlist) require explicit policy authorization

---

*SIH26187 - Smart India Hackathon - Ministry of Home Affairs*
*Conceptual design for technology demonstrator. Operational deployment requires agency validation, security accreditation, and lawful-use approvals.*
