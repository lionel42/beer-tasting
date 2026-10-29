"""Beer tasting app. Run with:  streamlit run app.py"""

import random
import sqlite3
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db
import fun
import stats

st.set_page_config(page_title="Beer Tasting", page_icon="🍺", layout="wide")

# Chart colours (validated categorical slots 1-2, diverging red <-> gray <-> blue)
BLUE, ORANGE, RED, GRAY = "#2a78d6", "#eb6834", "#e34948", "#898781"
DIVERGING = [[0, RED], [0.5, "#f0efec"], [1, BLUE]]
BEER_COLUMNS = ["position", "name", "brewery", "style", "abv", "ibu", "price"]


# --- helpers ----------------------------------------------------------------

def is_blind() -> bool:
    return db.get_setting("blind", "0") == "1"


def beer_labels(beers: pd.DataFrame) -> pd.Series:
    """Display label per beer id; hides names in blind mode. Always unique."""
    blind = is_blind()
    labels = [
        f"#{int(p)}" if blind else f"#{int(p)} {n}"
        for p, n in zip(beers["position"], beers["name"])
    ]
    seen: dict[str, int] = {}
    for i, lab in enumerate(labels):
        seen[lab] = seen.get(lab, 0) + 1
        if seen[lab] > 1:
            labels[i] = f"{lab} ({seen[lab]})"
    return pd.Series(labels, index=beers["id"].values)


def score_matrix() -> tuple[pd.DataFrame, pd.DataFrame]:
    """M (beer label x participant name) and the beers table with a label column."""
    beers, people, r = db.beers(), db.participants(), db.ratings()
    beers["label"] = beer_labels(beers).values
    M = (
        r.pivot(index="beer_id", columns="participant", values="score")
        .reindex(index=beers["id"], columns=people["name"])
    )
    M.index = beers["label"].values
    M.index.name, M.columns.name = "beer", "participant"
    return M, beers


def clean(v):
    """Turn editor values (NaN, '', numpy types) into plain Python / None."""
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == "":
        return None
    return v.item() if hasattr(v, "item") else v


def apply_table_edits(state: dict, ids: list[int], columns: list[str], insert, update, delete):
    """Apply st.data_editor edit state (edited/added/deleted rows) to the database."""
    for row in state.get("deleted_rows", []):
        delete(ids[row])
    for row, changes in state.get("edited_rows", {}).items():
        if int(row) in state.get("deleted_rows", []):
            continue
        update(ids[int(row)], {c: clean(v) for c, v in changes.items() if c in columns})
    for new in state.get("added_rows", []):
        values = {c: clean(v) for c, v in new.items() if c in columns}
        if values.get("name"):
            insert(values)


def heatmap(C: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=C.values, x=list(C.columns), y=list(C.index),
        zmin=-1, zmax=1, colorscale=DIVERGING, xgap=2, ygap=2,
        hovertemplate="%{y} × %{x}<br>r = %{z:.2f}<extra></extra>",
        colorbar=dict(title="r", thickness=12),
    ))
    fig.update_layout(title=title, height=max(350, 28 * len(C) + 120),
                      yaxis=dict(autorange="reversed"), margin=dict(t=50, l=10, r=10, b=10))
    return fig


# --- sidebar ----------------------------------------------------------------

st.sidebar.title("🍺 Beer Tasting")
page = st.sidebar.radio("Page", ["Setup", "Scoring", "Stats"], label_visibility="collapsed")

blind = st.sidebar.toggle(
    "Blind mode", value=is_blind(),
    help="Hide beer names on the Scoring and Stats pages (shows #1, #2, ...).",
)
if blind != is_blind():
    db.set_setting("blind", "1" if blind else "0")
    st.rerun()

funny = st.sidebar.toggle("Fun animations", value=db.get_setting("fun", "1") == "1",
                         help="A silly reaction every time a score is entered.")
if funny != (db.get_setting("fun", "1") == "1"):
    db.set_setting("fun", "1" if funny else "0")

st.sidebar.download_button(
    "⬇️ Backup (CSV)", db.export_long().to_csv(index=False),
    file_name="beer_tasting.csv", mime="text/csv", width="stretch",
)
st.sidebar.caption(f"Data is saved automatically to `{db.DB_PATH.name}`.")


# --- Setup ------------------------------------------------------------------

def page_setup():
    st.header("Setup")
    st.caption("Add rows at the bottom of each table, edit cells in place, select rows "
               "and press the bin icon to delete. Then press **Save**.")
    if is_blind():
        st.info("Blind mode is on: this page still shows the real beer names, keep it hidden 🙈")

    version = st.session_state.setdefault("setup_version", 0)
    left, right = st.columns([1, 3])

    with left:
        st.subheader("Participants")
        people = db.participants()
        st.data_editor(
            people[["name"]], key=f"people_{version}", num_rows="dynamic", height=35 * (len(people) + 3) + 3,
            hide_index=True, width="stretch",
            column_config={"name": st.column_config.TextColumn("Name", required=True)},
        )

    with right:
        st.subheader("Beers")
        beers = db.beers()
        st.data_editor(
            beers[BEER_COLUMNS], key=f"beers_{version}", num_rows="dynamic", height=35 * (len(beers) + 3) + 3,
            hide_index=True, width="stretch",
            column_config={
                "position": st.column_config.NumberColumn(
                    "Order", min_value=1, step=1, help="Tasting order (blank = last)"),
                "name": st.column_config.TextColumn("Name", required=True),
                "brewery": st.column_config.TextColumn("Brewery"),
                "style": st.column_config.TextColumn("Style", help="e.g. IPA, Stout, Lager"),
                "abv": st.column_config.NumberColumn("ABV %", min_value=0.0, max_value=70.0,
                                                     step=0.1),
                "ibu": st.column_config.NumberColumn("IBU", min_value=0, step=1),
                "price": st.column_config.NumberColumn("Price", min_value=0.0, step=0.05,
                                                       format="%.2f"),
            },
        )

    if st.button("💾 Save", type="primary"):
        try:
            apply_table_edits(
                st.session_state[f"people_{version}"], people["id"].tolist(), ["name"],
                insert=lambda v: db.add_participant(v["name"].strip()),
                update=lambda i, v: v.get("name") and db.rename_participant(i, v["name"].strip()),
                delete=db.delete_participant,
            )
            apply_table_edits(
                st.session_state[f"beers_{version}"], beers["id"].tolist(), BEER_COLUMNS,
                insert=lambda v: db.add_beer(**v),
                update=lambda i, v: db.update_beer(i, **v),
                delete=db.delete_beer,
            )
        except sqlite3.IntegrityError as e:
            st.error(f"Could not save: {e} (participant names must be unique).")
        else:
            st.session_state.setup_version += 1   # fresh editors showing the saved data
            st.rerun()

    with st.expander("Testing & reset"):
        st.write("Try the app before the big night with random data, then reset.")
        c1, c2 = st.columns(2)
        if c1.button("Load demo data", disabled=not (people.empty and beers.empty)):
            load_demo()
            st.session_state.setup_version += 1
            st.rerun()
        sure = c2.checkbox("I really want to delete everything")
        if c2.button("Reset all data", disabled=not sure):
            db.DB_PATH.unlink(missing_ok=True)
            st.session_state.setup_version += 1
            st.rerun()


def load_demo():
    styles = {
        "Lager": (4.8, 20), "Pils": (5.0, 35), "IPA": (6.5, 60), "NEIPA": (6.8, 40),
        "Stout": (8.0, 45), "Sour": (4.5, 8), "Weizen": (5.3, 12), "Tripel": (8.5, 30),
    }
    profiles = {s: np.random.normal(0, 1.5, 10) for s in styles}   # latent taste per style
    names = ["Alex", "Sam", "Robin", "Kim", "Jo", "Charlie", "Noa", "Luca", "Mika", "Andrea"]
    for n in names:
        db.add_participant(n)
    for i in range(14):
        style = random.choice(list(styles))
        abv, ibu = styles[style]
        db.add_beer(name=f"Demo {style} {i + 1}", brewery="Demo Brewing", style=style,
                    abv=round(abv + random.uniform(-0.5, 0.5), 1), ibu=ibu,
                    price=round(random.uniform(2, 9), 2))
    people, beers = db.participants(), db.beers()
    bias = np.random.normal(0, 0.8, len(people))
    for _, b in beers.iterrows():
        for j, p in enumerate(people["id"]):
            s = 6 + bias[j] + profiles[b["style"]][j] + np.random.normal(0, 0.7)
            db.set_rating(int(p), int(b["id"]), round(float(np.clip(s, 1, 10)), 1))


# --- Scoring ----------------------------------------------------------------

def page_scoring():
    st.header("Scoring")
    beers, people, r = db.beers(), db.participants(), db.ratings()
    if beers.empty or people.empty:
        st.info("Add participants and beers on the **Setup** page first.")
        return

    labels = beer_labels(beers)
    grid = (
        r.pivot(index="beer_id", columns="participant_id", values="score")
        .reindex(index=beers["id"], columns=people["id"])
    )
    grid.columns = people["name"].values
    rated = grid.notna().sum(axis=1).astype(str) + f"/{len(people)}"
    # Scores are edited as text so both "7.5" and "7,5" work (number cells mangle commas)
    grid = grid.map(lambda v: "" if pd.isna(v) else f"{v:g}")
    grid.insert(0, "Beer", labels.values)
    grid["Rated"] = rated
    grid = grid.reset_index(drop=True)

    beer_ids, pid_by_name = beers["id"].tolist(), dict(zip(people["name"], people["id"]))
    stored = r.set_index(["participant_id", "beer_id"])["score"].to_dict()
    # Key changes whenever beers/participants change, so stale edits never leak onto other
    # rows, and after a rejected entry, so the grid reloads from the database
    resets = st.session_state.setdefault("score_resets", 0)
    key = f"scores_{hash((tuple(beer_ids), tuple(people['id'])))}_{resets}"

    def save_scores():
        for row, changes in st.session_state[key]["edited_rows"].items():
            for name, value in changes.items():
                if name not in pid_by_name:
                    continue
                text = (clean(value) or "").strip().replace(",", ".")
                try:
                    score = None if text == "" else float(text)
                    if score is not None and not 1 <= score <= 10:
                        raise ValueError
                except ValueError:
                    st.session_state.score_error = (
                        f"“{value}” for {name} is not a score between 1 and 10, not saved.")
                    st.session_state.score_resets += 1
                    continue
                pid, bid = pid_by_name[name], beer_ids[int(row)]
                score = None if score is None else round(score, 2)
                # The editor re-sends all earlier edits too; only react to the new one
                if score is not None and score != stored.get((pid, bid)):
                    st.session_state.fun_reaction = (name, labels[bid], score)
                db.set_rating(pid, bid, score)

    st.caption("Click a cell, type a score from 1 to 10 (decimals with . or , ), press Enter. "
               "Every change is saved immediately. Clear a cell to remove a score.")
    if error := st.session_state.pop("score_error", None):
        st.error(error)
    st.data_editor(
        grid, key=key, on_change=save_scores, hide_index=True, width="stretch",
        height=min(38 * (len(grid) + 1) + 3, 800), num_rows="fixed",
        disabled=["Beer", "Rated"],
        column_config={
            "Beer": st.column_config.TextColumn("Beer", pinned=True),
            "Rated": st.column_config.TextColumn("Rated", width="small"),
            **{
                name: st.column_config.TextColumn(name, max_chars=5,
                                                  validate=r"^\s*([1-9]([.,]\d*)?|10([.,]0*)?)?\s*$")
                for name in people["name"]
            },
        },
    )
    total = len(beers) * len(people)
    st.progress(len(r) / total, text=f"{len(r)} of {total} scores entered")

    if (reaction := st.session_state.pop("fun_reaction", None)) and funny:
        st.session_state.fun_count = st.session_state.get("fun_count", 0) + 1
        fun.announce(*reaction)
        st.session_state.fun_html = (fun.animation(reaction[2], st.session_state.fun_count),
                                     time.time())
    # Streamlit reruns again right after an edit; keep rendering the same animation for a
    # few seconds so that second run doesn't cut it off
    if funny and (shown := st.session_state.get("fun_html")) and time.time() - shown[1] < 3:
        st.html(shown[0])


# --- Stats ------------------------------------------------------------------

def page_stats():
    st.header("Stats")
    M, beers = score_matrix()
    M = M.dropna(how="all").dropna(axis=1, how="all")
    if M.shape[0] < 3 or M.shape[1] < 2:
        st.info("Need at least 3 rated beers and 2 participants with scores. "
                "Tip: try **Load demo data** on the Setup page.")
        return
    meta = beers.set_index("label").loc[M.index]
    summary = stats.beer_summary(M)

    # Headline numbers
    w, n_w, m_w = stats.kendalls_w(M)
    c = st.columns(4)
    c[0].metric("Scores", int(M.count().sum()))
    c[1].metric("Favourite", summary.index[0], f"{summary['mean'].iloc[0]:.2f} avg",
                delta_color="off", delta_arrow="off")
    contro = summary["std"].idxmax()
    c[2].metric("Most controversial", contro, f"σ = {summary.loc[contro, 'std']:.2f}",
                delta_color="off", delta_arrow="off")
    c[3].metric("Group agreement (Kendall's W)", "–" if np.isnan(w) else f"{w:.2f}",
                f"{n_w} beers rated by all", delta_color="off", delta_arrow="off",
                help="0 = everyone ranks the beers differently, 1 = identical rankings.")

    tabs = st.tabs(["🏆 Ranking", "🧑‍🤝‍🧑 People", "🧬 Taste clusters", "🗺️ Preference map",
                    "📈 Does it matter?"])

    # Ranking -----------------------------------------------------------------
    with tabs[0]:
        corrected = st.toggle(
            "Correct for harsh / generous raters (z-scores)",
            help="Each person's scores are standardised to mean 0, std 1 before averaging.",
        )
        col, label = ("mean_z", "Mean z-score") if corrected else ("mean", "Mean score")
        s = summary.sort_values(col)
        fig = go.Figure(go.Bar(
            x=s[col], y=s.index, orientation="h", marker_color=BLUE,
            error_x=None if corrected else dict(type="data", array=s["ci95"], color=GRAY,
                                                thickness=1.5),
            customdata=np.stack([s["mean"], s["std"], s["n"]], axis=1),
            hovertemplate="<b>%{y}</b><br>mean %{customdata[0]:.2f}"
                          "<br>σ %{customdata[1]:.2f}<br>n %{customdata[2]}<extra></extra>",
        ))
        fig.update_layout(title=f"{label} per beer" + ("" if corrected else " (±95% CI)"),
                          height=max(350, 30 * len(s) + 100), xaxis_title=label,
                          margin=dict(t=50, l=10, r=10, b=10))
        st.plotly_chart(fig, width="stretch")

        # Every individual score, so you can see the spread behind the mean
        long = M.reset_index().melt(id_vars="beer", value_name="score").dropna()
        order = summary.index[::-1]
        fig = go.Figure(go.Scatter(
            x=long["score"], y=long["beer"], mode="markers", text=long["participant"],
            marker=dict(size=10, color=BLUE, opacity=0.7, line=dict(width=1, color="white")),
            hovertemplate="<b>%{text}</b> gave %{y}: %{x}<extra></extra>",
        ))
        fig.update_layout(title="All individual scores", xaxis=dict(range=[0.5, 10.5]),
                          yaxis=dict(categoryorder="array", categoryarray=list(order)),
                          height=max(350, 30 * len(order) + 100),
                          margin=dict(t=50, l=10, r=10, b=10))
        st.plotly_chart(fig, width="stretch")

        st.dataframe(
            summary.join(meta[["style", "abv", "price"]]).round(2),
            width="stretch",
        )

    # People ------------------------------------------------------------------
    with tabs[1]:
        ps = stats.person_summary(M)
        g = ps["generosity"].sort_values()
        fig = go.Figure(go.Bar(
            x=g.values, y=g.index, orientation="h",
            marker_color=[BLUE if v >= 0 else RED for v in g.values],
            hovertemplate="<b>%{y}</b><br>%{x:+.2f} points vs. group<extra></extra>",
        ))
        fig.update_layout(title="Generosity: average points above (+) or below (–) the group",
                          height=max(300, 30 * len(g) + 100),
                          margin=dict(t=50, l=10, r=10, b=10))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(ps.round(2), width="stretch")
        st.caption("**agreement** = Spearman correlation between the person and the "
                   "average of everyone else.")

        C = stats.person_correlation(M)
        order = stats.cluster_order(C)
        st.plotly_chart(heatmap(C.loc[order, order], "Taste similarity between people "
                                "(Spearman r)"), width="stretch")
        p = stats.pairs(C)
        if not p.empty:
            a, b = st.columns(2)
            a.subheader("👯 Taste twins")
            a.dataframe(p.head(3).round(2), hide_index=True, width="stretch")
            b.subheader("⚔️ Taste opposites")
            b.dataframe(p.tail(3).iloc[::-1].round(2), hide_index=True,
                        width="stretch")

        st.subheader("🔥 Hot takes")
        st.caption("Each person's biggest disagreement with the group (bias-corrected).")
        st.dataframe(stats.hot_takes(M).round(2), hide_index=True, width="stretch")

    # Taste clusters ----------------------------------------------------------
    with tabs[2]:
        st.write("Beers are grouped by **how people reacted to them**, not by their label: "
                 "two beers end up together when the same people liked them.")
        max_k = min(8, len(M) - 1)
        # A slider needs min < max; with only 3 rated beers, 2 clusters is the only option
        k = st.slider("Number of clusters", 2, max_k, min(4, max_k)) if max_k > 2 else 2
        clusters, leaf_order = stats.beer_clusters(M, k)
        C = stats.beer_correlation(M)
        st.plotly_chart(heatmap(C.loc[leaf_order, leaf_order],
                                "Beer similarity across tasters (r of z-scores)"),
                        width="stretch")

        table = pd.DataFrame({
            "cluster": clusters, "style": meta["style"], "mean": summary["mean"],
        }).loc[leaf_order]
        cols = st.columns(min(k, 4))
        for i, (cl, members) in enumerate(table.groupby("cluster", sort=False)):
            with cols[i % len(cols)]:
                st.markdown(f"**Cluster {cl}** · avg {members['mean'].mean():.2f}")
                for beer, row in members.iterrows():
                    style = "" if is_blind() or pd.isna(row["style"]) else f" · _{row['style']}_"
                    st.markdown(f"- {beer}{style}")
        if not is_blind() and meta["style"].notna().any():
            st.subheader("Clusters vs. official styles")
            st.dataframe(pd.crosstab(table["style"], table["cluster"]),
                         width="stretch")

    # Preference map ----------------------------------------------------------
    with tabs[3]:
        beers_xy, people_xy, var = stats.preference_map(M)
        st.write("**Internal preference map** (PCA). Beers close together were liked by "
                 "the same people. Each arrow is a person pointing towards what they like; "
                 "people with arrows in the same direction share tastes.")
        scale = np.abs(beers_xy.values).max() / max(np.abs(people_xy.values).max(), 1e-9) * 0.9
        fig = go.Figure()
        for name, (x, y) in people_xy.iterrows():
            fig.add_annotation(x=x * scale, y=y * scale, ax=0, ay=0, xref="x", yref="y",
                               axref="x", ayref="y", showarrow=True, arrowhead=2,
                               arrowwidth=2, arrowcolor=ORANGE, opacity=0.8)
        fig.add_trace(go.Scatter(
            x=people_xy["PC1"] * scale * 1.08, y=people_xy["PC2"] * scale * 1.08,
            mode="text", text=people_xy.index, textfont=dict(color=ORANGE), name="People",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=beers_xy["PC1"], y=beers_xy["PC2"], mode="markers+text", name="Beers",
            text=beers_xy.index, textposition="top center",
            marker=dict(size=11, color=BLUE, line=dict(width=2, color="white")),
            customdata=np.stack([summary.loc[beers_xy.index, "mean"],
                                 clusters.loc[beers_xy.index]], axis=1),
            hovertemplate="<b>%{text}</b><br>mean %{customdata[0]:.2f}"
                          "<br>cluster %{customdata[1]}<extra></extra>",
        ))
        fig.update_layout(
            height=650, xaxis_title=f"PC1 ({var[0]:.0%} of variance)",
            yaxis_title=f"PC2 ({var[1]:.0%} of variance)",
            yaxis=dict(scaleanchor="x", scaleratio=1, zeroline=True),
            xaxis=dict(zeroline=True), margin=dict(t=30, l=10, r=10, b=10),
        )
        st.plotly_chart(fig, width="stretch")

    # Does it matter? ---------------------------------------------------------
    with tabs[4]:
        options = {"Price": "price", "ABV %": "abv", "IBU (bitterness)": "ibu",
                   "Tasting order (palate fatigue?)": "position"}
        options = {k: v for k, v in options.items() if meta[v].notna().sum() >= 3}
        if not options:
            st.info("Fill in price / ABV / IBU on the Setup page to unlock this.")
        else:
            choice = st.radio("Does the score depend on…", list(options), horizontal=True)
            x, y = meta[options[choice]].astype(float), summary.loc[meta.index, "mean"]
            fig = go.Figure(go.Scatter(
                x=x, y=y, mode="markers", text=meta.index, name="Beers",
                marker=dict(size=11, color=BLUE, line=dict(width=2, color="white")),
                hovertemplate="<b>%{text}</b><br>%{x}: %{y:.2f}<extra></extra>",
            ))
            t = stats.trend(x, y)
            if t:
                xs = np.linspace(x.min(), x.max(), 2)
                fig.add_trace(go.Scatter(x=xs, y=t["intercept"] + t["slope"] * xs,
                                         mode="lines", line=dict(color=GRAY, width=2,
                                                                 dash="dash"),
                                         name="Trend", hoverinfo="skip"))
                st.markdown(
                    f"Spearman ρ = **{t['rho']:.2f}** (p = {t['p']:.2f}, n = {t['n']}). "
                    + ("Probably just noise 🤷" if t["p"] > 0.05 else "That looks real! 🎉")
                )
            fig.update_layout(xaxis_title=choice, yaxis_title="Mean score", showlegend=False,
                              height=450, margin=dict(t=30, l=10, r=10, b=10))
            st.plotly_chart(fig, width="stretch")


{"Setup": page_setup, "Scoring": page_scoring, "Stats": page_stats}[page]()
