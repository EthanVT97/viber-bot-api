# Viber Bot API

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Postgres](https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)

A production-ready FastAPI backend for Viber chatbots with features for customer management, payment processing, and chat logging.

## Features

- 💬 Real-time chat processing with Redis pub/sub
- 💳 Payment recording and validation
- 👥 Customer profile management
- 📊 Admin dashboard with analytics
- 🚀 High-performance async architecture
- 🔒 Multiple security layers (IP whitelisting, API keys)
- 📈 Built-in monitoring (Sentry, Prometheus)

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL 13+
- Redis 6+
- Docker (optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/EthanVT97/viber-bot-api.git
cd viber-bot-api

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Install dependencies
pip install -r requirements.txt
```

### Running with Docker

```bash
docker-compose up -d --build
```

## Configuration

Environment variables (`.env` file):

```ini
# Core
ENVIRONMENT=development
DEBUG=true

# Database
DATABASE_URL=postgres://user:password@localhost:5432/viberbot
DATABASE_POOL_MIN=2
DATABASE_POOL_MAX=10

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
CUSTOMER_API_KEY=your_customer_key
BILLING_API_KEY=your_billing_key
CHATLOG_API_KEY=your_chatlog_key
ADMIN_SECRET=your_admin_secret
WHITELISTED_IP=127.0.0.1

# Monitoring
SENTRY_DSN=https://your-sentry-dsn
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/customers` | POST | Create customer profile |
| `/payments` | POST | Record payment |
| `/chat-logs` | POST | Log chat message |
| `/admin` | GET | Admin dashboard |
| `/health` | GET | Service health check |
| `/docs` | GET | API documentation (dev only) |

## Deployment

### Production Setup

```bash
# Using Gunicorn with Uvicorn workers
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Kubernetes (example)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: viber-bot-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: ethanvt97/viber-bot-api:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: viber-bot-secrets
```

## Development

```bash
# Run with hot reload
uvicorn app.main:app --reload

# Run tests
pytest tests/

# Generate migration
alembic revision --autogenerate -m "description"
```

## Project Structure

```
viber-bot-api/
├── app/                  # Application code
│   ├── core/             # Core utilities
│   ├── models/           # Database models
│   ├── routes/           # API endpoints
│   ├── services/         # Business logic
│   └── main.py           # App entry point
├── tests/                # Test cases
├── alembic/              # Database migrations
├── requirements.txt      # Dependencies
├── Dockerfile            # Production container
└── docker-compose.yml    # Dev environment
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Contact

EthanVT - botservice@ygnb2b.com

Project Link: [https://github.com/EthanVT97/viber-bot-api](https://github.com/EthanVT97/viber-bot-api)
```
