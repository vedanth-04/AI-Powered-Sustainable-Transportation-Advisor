# Transit MLOps dashboard (React)

Single-page React app for the Phase 3 MLOps pipeline. It reads everything from the Python API in
`dashboard/server.py`, which in turn reads the pipeline artifacts (`outputs/phase3`, Phase 2 evidence,
`docs/`). Charts are hand-built SVG components (`src/components/charts.jsx`), so the only runtime
dependencies are React and React DOM.

```powershell
npm install        # once, needs Node.js 18+
npm run build      # writes dist/, served by `python -m dashboard.server` at http://127.0.0.1:8050
npm run dev        # optional live reload on http://localhost:5173 (API proxied to :8050)
```

| Path | Contents |
|---|---|
| `src/App.jsx` | Layout, navigation (`#overview`, `#drift`, …), theme toggle, data loading |
| `src/pages/` | Overview, Pipeline, Data, Experiments, Drift monitor, Model registry, Deployment, Governance |
| `src/components/` | UI primitives and SVG charts with hover tooltips |
| `src/lib/` | Formatting, scales and a small escaped Markdown renderer for the docs viewer |
