# SmartMineGuard
**Digital Intelligence for Safer & Transparent Mineral Transportation**

SmartMineGuard is a software-only mining intelligence and enforcement platform designed to help government mining authorities identify suspicious mineral transportation and possible illegal mining activity. It functions as an intelligence layer over existing permit and transport systems.

## Core Capabilities
- **Live GIS Command Center**: Real-time PostGIS-backed map tracking.
- **Explainable Detection Engine**: Rule-based detection for Route Deviation, Weight Fraud, GPS Blackout, and Pass Recycling.
- **Risk Scoring**: 0-100 normalized risk score generated per trip.
- **Digital Chain of Custody**: Links Permits → Trucks → GPS → Weighbridges → Investigations.
- **Officer PWA**: Mobile-first QR and manual permit verification with offline capabilities.

## Architecture & Tech Stack
- **Frontend**: Next.js 14, React, Tailwind CSS, Leaflet, Recharts.
- **Backend**: Node.js, Express, TypeScript, WebSockets.
- **Database**: PostgreSQL 15 + PostGIS 3.3.
- **Infrastructure**: Docker & Docker Compose.

## Installation & Running (Demo Mode)

1. Clone the repository.
2. Copy environment variables: `cp .env.example .env`
3. Start the infrastructure (Database, Backend, Frontend):
   ```bash
   docker-compose up -d --build
