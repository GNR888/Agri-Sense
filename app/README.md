# Agri-Sense — Farmer Dashboard

Interactive map dashboard for crop recommendations in Vietnam.

## Stack

- **Next.js 16** (App Router, TypeScript, Tailwind)
- **react-leaflet** — interactive map of Vietnam
- **TanStack Query** — data fetching and server-state management

## Running locally

```bash
# Install dependencies
npm install

# Start the dev server (port 3000)
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The dashboard expects the FastAPI backend running at `http://localhost:8000`. To point at a different backend:

```bash
NEXT_PUBLIC_API_URL=http://my-api-host:8000 npm run dev
```

## Usage

1. Click any point on the map of Vietnam, or click a province marker, to select a location.
2. Choose a planting season from the panel on the right.
3. Click **Get Recommendations** to fetch the top-3 crop suggestions with yield and revenue estimates.
