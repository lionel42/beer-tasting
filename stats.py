"""Pure statistics on the score matrix M: rows = beers, columns = participants, NaN = not rated.

Nothing here touches the database or Streamlit, so it can be reused in a notebook.
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, leaves_list, linkage
from scipy.spatial.distance import squareform
from scipy.stats import rankdata, spearmanr
from sklearn.decomposition import PCA


def zscore(M: pd.DataFrame) -> pd.DataFrame:
    """Standardise each participant (column): removes harsh/generous rater bias.

    A participant who gave every beer the same score has std 0 -> all z = 0.
    """
    std = M.std(ddof=0).replace(0, np.nan)
    return ((M - M.mean()) / std).fillna(0).where(M.notna())


def beer_summary(M: pd.DataFrame) -> pd.DataFrame:
    Z = zscore(M)
    out = pd.DataFrame({
        "mean": M.mean(axis=1),
        "median": M.median(axis=1),
        "std": M.std(axis=1),          # the "controversy index"
        "min": M.min(axis=1),
        "max": M.max(axis=1),
        "n": M.count(axis=1),
        "mean_z": Z.mean(axis=1),      # rank after removing rater bias
    })
    # 95% CI of the mean (normal approximation, good enough for a beer night)
    out["ci95"] = 1.96 * out["std"] / np.sqrt(out["n"])
    return out.sort_values("mean", ascending=False)


def person_summary(M: pd.DataFrame) -> pd.DataFrame:
    group_mean = M.mean(axis=1)
    return pd.DataFrame({
        "mean": M.mean(),
        "std": M.std(),
        "min": M.min(),
        "max": M.max(),
        "n": M.count(),
        # positive = more generous than the group on the same beers
        "generosity": M.sub(group_mean, axis=0).mean(),
        # how well the person agrees with the rest of the group
        "agreement": pd.Series(
            {p: _corr(M[p], M.drop(columns=p).mean(axis=1)) for p in M.columns}
        ),
    }).sort_values("mean", ascending=False)


def _corr(a: pd.Series, b: pd.Series, min_periods: int = 3) -> float:
    ok = a.notna() & b.notna()
    if ok.sum() < min_periods or a[ok].nunique() < 2 or b[ok].nunique() < 2:
        return np.nan
    return spearmanr(a[ok], b[ok]).statistic


def person_correlation(M: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlation between participants over the beers both rated."""
    return M.corr(method="spearman", min_periods=3)


def beer_correlation(M: pd.DataFrame) -> pd.DataFrame:
    """Correlation between beers across participants (on bias-free z-scores)."""
    return zscore(M).T.corr(method="pearson", min_periods=3)


def pairs(C: pd.DataFrame) -> pd.DataFrame:
    """Upper triangle of a correlation matrix as a sorted list of pairs."""
    iu = np.triu_indices(len(C), k=1)
    out = pd.DataFrame({
        "a": C.index[iu[0]],
        "b": C.columns[iu[1]],
        "r": C.values[iu],
    }).dropna()
    return out.sort_values("r", ascending=False).reset_index(drop=True)


def _filled_z(M: pd.DataFrame) -> pd.DataFrame:
    """z-scores with missing ratings imputed as 0 (= that person's average)."""
    return zscore(M).fillna(0)


def beer_clusters(M: pd.DataFrame, k: int) -> tuple[pd.Series, list[str]]:
    """Ward clustering of beers by the taste profile of the group.

    Returns cluster labels per beer and the dendrogram leaf order.
    """
    X = _filled_z(M)
    L = linkage(X.values, method="ward")
    labels = pd.Series(fcluster(L, t=k, criterion="maxclust"), index=X.index, name="cluster")
    order = [X.index[i] for i in leaves_list(L)]
    return labels, order


def cluster_order(C: pd.DataFrame) -> list:
    """Order rows/columns of a correlation matrix so similar items sit together."""
    if len(C) < 3:
        return list(C.index)
    D = (1 - C.fillna(0)).clip(lower=0).to_numpy(copy=True)
    np.fill_diagonal(D, 0)
    L = linkage(squareform(D, checks=False), method="average")
    return [C.index[i] for i in leaves_list(L)]


def preference_map(M: pd.DataFrame):
    """Internal preference mapping (MDPREF): PCA of the beers x participants z-matrix.

    Beers become points in a 2-D 'taste space'; each participant becomes an arrow
    pointing to the beers they like. Returns (beer_coords, person_loadings, explained).
    """
    # PCA centres each participant column (already ~0 after z-scoring), so beers keep
    # their overall-liking offset and well-liked beers land where most arrows point.
    X = _filled_z(M)
    pca = PCA(n_components=2)
    scores = pca.fit_transform(X.values)
    beers = pd.DataFrame(scores, index=X.index, columns=["PC1", "PC2"])
    loadings = pd.DataFrame(pca.components_.T, index=X.columns, columns=["PC1", "PC2"])
    return beers, loadings, pca.explained_variance_ratio_


def kendalls_w(M: pd.DataFrame) -> tuple[float, int, int]:
    """Kendall's coefficient of concordance on beers rated by everyone.

    0 = no agreement, 1 = everyone ranks the beers identically.
    Returns (W, n_beers_used, n_raters).
    """
    C = M.dropna()
    n, m = C.shape
    if n < 2 or m < 2:
        return np.nan, n, m
    R = np.column_stack([rankdata(C[c]) for c in C.columns])
    S = ((R.sum(axis=1) - m * (n + 1) / 2) ** 2).sum()
    return 12 * S / (m**2 * (n**3 - n)), n, m


def hot_takes(M: pd.DataFrame, top: int = 1) -> pd.DataFrame:
    """For each participant, the beer where they deviate most from the group (in z)."""
    Z = zscore(M)
    dev = Z.sub(Z.mean(axis=1), axis=0)
    rows = []
    for p in M.columns:
        d = dev[p].dropna()
        for beer in d.abs().sort_values(ascending=False).index[:top]:
            rows.append({
                "participant": p,
                "beer": beer,
                "their score": M.loc[beer, p],
                "group mean": M.loc[beer].mean(),
                "direction": "loves it" if d[beer] > 0 else "hates it",
            })
    return pd.DataFrame(rows)


def trend(x: pd.Series, y: pd.Series) -> dict | None:
    """Least-squares line + Spearman rho for a metadata-vs-score scatter."""
    ok = x.notna() & y.notna()
    if ok.sum() < 3 or x[ok].nunique() < 2:
        return None
    slope, intercept = np.polyfit(x[ok], y[ok], 1)
    res = spearmanr(x[ok], y[ok])
    return {"slope": slope, "intercept": intercept, "rho": res.statistic, "p": res.pvalue,
            "n": int(ok.sum())}
