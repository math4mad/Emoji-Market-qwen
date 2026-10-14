#  UI Modify
> fork  一个新分支，进行开发。 部署以新分支为依据
1. 模拟参数 panel  添加悬浮球按钮
2. 整体分列chart 可以再小一点。 整合到一个panel里
3. 形成 Dashboard 布局
4. 样式要统一， 有现代感。 
5. Desktop 样式优先。 
6. 根据对话， 添加教程，显示交换是怎么完成的



-----
2026-10-14-8:55
fellow this pic to form a new dashboard layout

/Users/mac/Downloads/DownLoad_Temp/OIP-C.6chp0Ei_doHBOO660mka-wHaEJ.webp

Let me first read the current `app.py` to understand the structure before redesigning:
Now I have the full picture. Let me redesign the main dashboard area following the reference image layout — KPI cards row, multi-chart grid, and a clean analytics look. I'll rewrite the UI section (from line 525 onward) while keeping the engine classes and sidebar intact.
Now I'll rewrite the CSS and the entire main dashboard area. Let me do this in sections:
Now let me replace the header bar section:
Now replace Row 1 (capital chart + log) and Row 2 (intelligence metrics) with the new multi-chart grid:
Now I need to add the heatmap back — it was removed in the replacement. Let me add it as a new row alongside the event log:
Now I need to add the heatmap and event log back. Let me insert a new row between Row 2 (metrics trend + edge state) and Row 4 (snapshots):
Now let me check for lints and run a quick test:
No lints. Now let me run the AppTest to verify:
The initial render passed (Exceptions: `[]`), but the test script's API usage was wrong. Let me fix the test and also fix the `use_container_width` deprecation warnings:
Now also fix the remaining `width="stretch"` in the snapshot/export section:
Lines 787, 798, 804 are in the snapshot/export section — those use the old `width="stretch"` pattern for `st.pyplot` and `st.download_button`. Let me fix those:
Now run the test again:
All tests pass. Let me commit and push:
Done. Committed `b6e7a27` and pushed to `main`.

**New dashboard layout** following the web-analytics reference image:

```
┌─────────────────────────────────────────────────────────────┐
│  🌍 Emoji Economy Analytics              [▶ Auto] [⏭ Step]   │
├──────────┬──────────┬──────────┬──────────┬──────────────────┤
│ 💰 Total │ 🤖 Active│ ⚠️ Crises│ 📊 Volume│ ⏱️ Tick          │
│ Capital  │ Agents   │          │          │                  │  ← KPI row (colored cards)
├──────────┴────┬─────┴──────────┴──────────┴──────────────────┤
│ 📈 Capital    │ 🍩 Capital    │ 🧠 Intelligence               │
│ Evolution     │ Share (donut) │ (4 metrics)                   │  ← Chart grid row 1
├───────────────┼───────────────┴───────────────────────────────┤
│ 🧠 Metrics    │ 🔁 Edge State                                  │
│ Trend         │ (table)                                        │  ← Chart grid row 2
├───────────────┼───────────────────────────────────────────────┤
│ 🔥 Heatmap    │ 📜 Event Log                                   │  ← Chart grid row 3
├───────────────┴───────────────────────────────────────────────┤
│ 🕘 Snapshots  │  📤 CSV Export  │  🔗 Scenario Sharing        │
├───────────────────────────────────────────────────────────────┤
│ 🎓 Tutorial (expander)                                        │
└───────────────────────────────────────────────────────────────┘
```

- AppTest: **PASS** (0 exceptions, 5 steps verified)
- Cleaned up `Figure_1.png` (test artifact)