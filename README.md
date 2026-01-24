# BLOASIS

**AI-Powered Multi-Asset Trading Platform**

BLOASIS is an intelligent trading platform that combines Large Language Models (LLMs) and Reinforcement Learning for automated trading decisions across multiple asset classes.

## 🎯 Mission

- **Risk Management**: User-specific risk profiles (Conservative/Moderate/Aggressive)
- **Strategy Optimization**: LLM strategy generation → Quantitative parameter fitting → RL validation
- **Multi-Asset Trading**: Diversified trading across different asset classes
- **Event-Driven Response**: Real-time market regime detection for critical events (FOMC, CPI, etc.)

## 🏗️ Architecture

BLOASIS is built on a microservices architecture (MSA) with the following core services:

- **Market Regime Service**: Event-based market condition classification
- **AI Analysis Service**: Strategy generation using FinGPT + Claude
- **Classification Service**: 3-Tier asset selection (Sector → Thematic → Factor)
- **Backtesting Service**: Multi-strategy backtesting with VectorBT + FinRL
- **Risk Management Service**: Risk assessment and position management
- **Executor Service**: Real-time order execution

## 🛠️ Tech Stack

### Backend
- **Language**: Python 3.11+ (FastAPI)
- **AI/ML**:
  - FinGPT (financial domain specialization)
  - Claude Sonnet 4 (complex reasoning)
  - LangGraph (multi-agent orchestration)
- **Backtesting**: VectorBT (technical strategies), FinRL (reinforcement learning)
- **API Gateway**: Kong OSS (gRPC-to-REST transcoding)

### Infrastructure
- **Communication**: gRPC (internal MSA), REST (external clients)
- **Message Broker**: Redpanda (Kafka API compatible)
- **Database**: PostgreSQL, TimescaleDB (time-series)
- **Cache**: Redis
- **Service Discovery**: Consul
- **Container**: Docker, DevContainer

### Frontend
- **Language**: TypeScript (React/Next.js)
- **Communication**: REST API, WebSocket

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- VSCode with DevContainer extension (recommended)
- Python 3.11+

### DevContainer Setup (Recommended)

```bash
# Open project in VSCode
code /path/to/bloasis

# Command Palette (Cmd+Shift+P)
> Dev Containers: Reopen in Container
```

DevContainer automatically sets up:
- Python 3.11, uv package manager
- Redpanda, PostgreSQL, TimescaleDB, Redis
- Kong Gateway, Consul

### Manual Setup

```bash
# 1. Clone repository
git clone https://github.com/yourusername/bloasis.git
cd bloasis

# 2. Create Python virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies (TBD)
# pip install -r requirements.txt

# 4. Start infrastructure (TBD)
# docker-compose up -d
```

## 📁 Project Structure

```
bloasis/
├── services/                # Microservices
│   ├── market-regime/
│   ├── ai-analysis/
│   ├── classification/
│   ├── backtesting/
│   ├── risk-management/
│   └── executor/
├── frontend/                # React dashboard
├── infra/                   # Infrastructure config (Docker, Kong, Consul)
├── shared/                  # Shared libraries
│   ├── proto/               # gRPC .proto definitions
│   ├── models/              # Common data models
│   └── utils/               # Utilities
├── tests/                   # Integration tests
├── .devcontainer/           # DevContainer configuration
├── .gitignore
├── LICENSE                  # Apache 2.0
└── README.md
```

## 🧪 Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# E2E tests
pytest tests/e2e/
```

## 🤝 Contributing

BLOASIS is an open-source project. Contributions are welcome!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is provided for educational and research purposes only. The developers are not responsible for any losses incurred from actual trading. Trade at your own risk.

## 📧 Contact

For inquiries, please contact us through GitHub Issues.

---

**Current Status**: Phase 1 in preparation (Architecture complete, implementation pending)
