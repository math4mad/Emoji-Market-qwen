# UI Iteration Snapshots

This folder records screenshots of the Emoji Economy dashboard at each UI iteration.

## Naming convention

```
NN-description.png          (viewport: 1440x900)
NN-description-full.png     (full page capture)
```

- `NN` — sequence number (01, 02, 03, …)
- `description` — short label for the layout/iteration

## How to capture

```bash
# Start the app
streamlit run app.py --server.port 8501 --server.headless true &

# Viewport screenshot
npx playwright screenshot --browser chromium \
  --viewport-size 1440,900 --wait-for-timeout 3000 \
  http://localhost:8501 ui-snapshots/NN-description.png

# Full-page screenshot
npx playwright screenshot --browser chromium \
  --viewport-size 1440,900 --wait-for-timeout 3000 --full-page \
  http://localhost:8501 ui-snapshots/NN-description-full.png
```

## History

| # | File | Description |
|---|------|-------------|
| 01 | `01-concave-layout-v1.png` | Concave-style: dark status bar + mid row (Capital/Edge/Intelligence) + lower row (Heatmap/Log) + bottom action strip |
| 02 | `02-compact-heatmap-log.png` | Compact heatmap (3.2x2.8) and slim event log (8 lines, h=250) — heatmap narrower, log taller |
