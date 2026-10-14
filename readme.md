# Emoji Market 🌍

A political-economy simulator built with Streamlit, evolved from a [design dialogue with an AI agent](https://chat.qwen.ai/s/81387775-267a-4b3a-bb81-d6ac43c4daf3?fev=0.3.16).

## Live Demo

https://emoji-market.streamlit.app

## Features

- **AI Arbitrage Agents** — Two bots (Alpha & Beta) search for profitable exchange cycles using Dijkstra's algorithm on a weighted directed graph
- **Crisis Simulation** — Random market shocks halve exchange rates; watch agents adapt and recover
- **Market Recovery** — Rates gradually regress toward baseline after disruption
- **System Intelligence Dashboard** — Four neuroscience-inspired metrics (Integration, Cognitive Load, Learning Rate, Representation Efficiency)
- **Exchange Rate Heatmap** — Visualize rates, cumulative volume, or deviation from baseline
- **Agent Strategy Configuration** — Per-agent target commodity, capital, risk preference, and trade volume
- **Backtest Snapshots** — Save, compare, and delete simulation runs for parameter sweep analysis
- **Policy Sandbox** — Central bank interventions: inject/drain capital, trading tax, targeted edge repair
- **Preset Scenarios** — One-click load: Highland Crisis, AI War, Stable Equilibrium
- **CSV Export** — Download capital history and intelligence metrics as CSV
- **Scenario Sharing** — Generate URL-encoded parameter strings to share configurations

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web Framework | Streamlit |
| Graph Algorithms | NetworkX |
| Visualization | Matplotlib |
| Data Handling | NumPy, Pandas |

## Project Structure

```
app.py              # Main Streamlit application
first-step.py       # Prototype: direct commodity exchange
add-searching-path.py  # Prototype: Dijkstra pathfinding
compete-vis.py      # Prototype: competitive agents + visualization
repro_beta.py       # Reproduction script for Beta-Bot stuck bug
external/           # Design dialogue notes and suggestions
```

## License

MIT — see [LICENSE](LICENSE).
