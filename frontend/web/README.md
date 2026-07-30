# Aureum Studio — Web Dashboard

Aureum Studio is the web interface for the Aureum self-proving semantic kernel.
It lets you author strategies with Claude, edit YAML in Monaco, run backtests,
and inspect Aureum Backtest Certificates in real time.

## Stack

- Vite + React + TypeScript
- Tailwind CSS
- Monaco Editor (YAML)
- Recharts (NAV curve)
- React Router

## Local development

1. Start the Aureum API server:

   ```bash
   cd bindings/python
   pip install -e ".[web]"
   export ANTHROPIC_API_KEY=...
   uvicorn aureum.server:app --reload --port 8000
   ```

2. In a second terminal, start the frontend dev server:

   ```bash
   cd frontend/web
   npm install
   npm run dev
   ```

3. Open http://localhost:5173

The Vite dev server proxies `/api` to the backend at `http://127.0.0.1:8000`.
For production, set `VITE_API_URL` to the public backend URL.

## Build

```bash
npm run build
```

Static output is written to `frontend/web/dist`.
