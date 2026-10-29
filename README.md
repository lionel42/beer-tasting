# 🍺 Beer Tasting

A small Streamlit app to score beers (1–10, decimals with `.` or `,`) and nerd out on the results.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

## Pages

- **Setup**: participants and beers (order, style, ABV, IBU, price). Press *Save*.
  *Testing & reset* loads random demo data so you can try the stats beforehand.
- **Scoring**: beers × participants grid, saved to `tasting.db` on every edit.
- **Stats**: ranking (raw or bias-corrected), generosity, taste twins/opposites,
  hot takes, taste clusters vs. official styles, PCA preference map,
  and price/ABV/IBU/tasting-order vs. score.

**Blind mode** (sidebar) shows beers as `#1, #2, …` on Scoring and Stats until you switch it off.
**Backup (CSV)** in the sidebar downloads all scores in long format.

## Files

- `db.py`: SQLite schema and queries (ratings stored in long format)
- `stats.py`: pure functions on the beer × participant matrix, reusable in a notebook
- `app.py`: the Streamlit UI
