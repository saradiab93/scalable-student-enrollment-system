# Student Enrollment & Reporting Microservice

A Django-based microservice for high-volume student enrollment ingestion and optimized government reporting. Built with Clean Architecture, SOLID principles, and async background processing via Celery.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  API Layer  │────▶│ Service Layer│────▶│  Repository     │
│  (DRF Views)│     │ (Business    │     │  (Django ORM)   │
│             │     │  Logic)      │     │                 │
└─────────────┘     └──────────────┘     └─────────────────┘
       │                    │                      │
       │                    │                      ▼
       ▼                    ▼               ┌──────────────┐
  JSON / CSV           DTOs / Domain         │ PostgreSQL   │
  Ingestion            Validation           │ + Aggregates │
       │                                        └──────────────┘
       ▼
┌─────────────┐
│ Celery      │
│ Worker      │
│ (Redis)     │
└─────────────┘
```

### Layer Separation (Lightweight DDD)

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Domain** | `app/domain/` | Enums, domain exceptions |
| **Application** | `app/application/` | DTOs, service layer, repository interfaces |
| **Infrastructure** | `app/infrastructure/` | Django models, repository implementations |
| **Interfaces** | `app/interfaces/api/` | REST API views, serializers, URLs |

### Key Design Decisions

1. **Decoupled Ingestion**: The API accepts enrollments, persists them immediately with `PENDING` status, and returns `202 Accepted`. Celery workers process records asynchronously — the web thread never blocks on validation or aggregation.

2. **Audit Trail**: Every enrollment record carries a lifecycle status (`pending` → `processed` / `failed`) with timestamps and error messages for failed records.

3. **Pre-Aggregated Reporting**: Instead of scanning 10M+ rows at query time, an `EnrollmentAggregate` table stores counts per `(region, grade)`. The reporting endpoint reads from this small table (typically hundreds of rows), returning in under 500ms.

4. **Atomic Aggregate Updates**: Count increments use `select_for_update()` + `F()` expressions inside a transaction to prevent race conditions during concurrent processing.

5. **Duplicate Protection**: A partial unique constraint on `student_id` (only for `processed` status) plus application-level checks prevent duplicate enrollments, even under concurrent load.

6. **Dependency Injection**: A simple `Container` class (`app/dependencies.py`) wires repositories into services. Tests can inject mocks or alternate implementations without touching views.

## Quick Start

### Prerequisites

- Docker and Docker Compose

### Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

The API will be available at `http://localhost:8000`.

### Run Locally (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Start PostgreSQL and Redis separately, then:
python manage.py migrate
python manage.py runserver

# In a separate terminal:
celery -A config worker --loglevel=info
```

## API Endpoints

### Ingest Enrollments (JSON)

```bash
curl -X POST http://localhost:8000/api/enrollments/ \
  -H "Content-Type: application/json" \
  -d '{
    "enrollments": [
      {"student_id": "STU001", "region": "North", "grade": 5, "name": "Sara"},
      {"student_id": "STU002", "region": "South", "grade": 7, "name": "Omar"}
    ]
  }'
```

Response (`202 Accepted`):

```json
{
  "accepted": 2,
  "enrollment_ids": ["uuid-1", "uuid-2"],
  "message": "Enrollments queued for background processing"
}
```

### Ingest Enrollments (CSV)

```bash
curl -X POST http://localhost:8000/api/enrollments/ \
  -F "file=@enrollments.csv"
```

CSV format: `student_id,region,grade,name`

### Get Enrollment Status

```bash
curl http://localhost:8000/api/enrollments/<enrollment_id>/
```

### Enrollment Report

```bash
# All regions and grades
curl http://localhost:8000/api/reports/enrollments/

# Filter by region
curl "http://localhost:8000/api/reports/enrollments/?region=North"

# Filter by grade
curl "http://localhost:8000/api/reports/enrollments/?grade=5"

# Combined filter
curl "http://localhost:8000/api/reports/enrollments/?region=North&grade=5"
```

## Running Tests

```bash
python manage.py test app.tests
```

Tests include:
- JSON and CSV ingestion flows
- Successful processing and aggregate updates
- Invalid data handling (failed status)
- Duplicate student detection
- **Failed background task recovery** — simulates a worker crash and verifies the enrollment is marked `failed`
- **Concurrent duplicate race condition** — two threads process the same `student_id` simultaneously; only one succeeds
- Reporting query performance (bounded to 1 query regardless of aggregate row count)

## Scaling to 100 Million Records (Production)

In a real-world governmental production environment, the following strategies would extend this architecture:

### Data Tier
- **Partition enrollment records** by `region` or `academic_year` using PostgreSQL table partitioning. Queries and maintenance operate on smaller partitions.
- **Read replicas** for the reporting API; writes go to primary, reads from replicas fed by the aggregate table.
- **Archive cold data** (previous academic years) to object storage (S3) or a data warehouse (BigQuery/Redshift) while keeping current-year aggregates hot.

### Ingestion Tier
- **Horizontal Celery workers** behind Redis Cluster or RabbitMQ with priority queues (urgent vs. bulk).
- **Batch ingestion endpoint** that groups records into Celery chunks (e.g., 500 per task) to reduce broker overhead at 100k+ req/s.
- **Idempotency keys** on `student_id` at the API gateway to reject duplicates before they hit the database.

### Reporting Tier
- **Materialized views** refreshed on a schedule (e.g., every 5 minutes) for dashboards that tolerate slight staleness.
- **CQRS pattern**: the aggregate table is the read model; enrollment processing events update it via the write path (already implemented here).
- **CDN / API caching** for popular report queries (e.g., national totals by grade) with short TTL.

### Infrastructure
- **Kubernetes** with auto-scaling web and worker pods based on queue depth and CPU.
- **Connection pooling** (PgBouncer) to handle thousands of concurrent worker connections.
- **Observability**: structured logging, Prometheus metrics (queue depth, processing latency, error rate), and distributed tracing (OpenTelemetry).

### Reliability
- **Dead-letter queues** for permanently failed tasks with alerting.
- **Circuit breakers** on database connections during failover.
- **Multi-region deployment** with async replication for disaster recovery.


docker compose exec web python manage.py createsuperuser
docker compose exec db psql -U enrollment -d enrollment_db
\dt
SELECT * FROM app_enrollmentrecord;

## Project Structure

```
student_enrollment/
├── app/
│   ├── domain/              # Enums, exceptions
│   ├── application/         # DTOs, services, repository interfaces
│   ├── infrastructure/      # Django models, repository implementations
│   ├── interfaces/api/      # REST views, serializers, URLs
│   ├── tasks.py             # Celery tasks
│   ├── dependencies.py      # DI container
│   └── tests/
├── config/                  # Django settings, Celery, URLs
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```
