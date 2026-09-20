"""
A2 — soil-surface fitting machinery.

Everything here is scene-agnostic geometry. No constant in this file encodes a
belief about how gardens are arranged; the two numbers the pipeline needs
(the RANSAC inlier threshold and the spline smoothing) are *passed in* by the
caller, which reads the first off A1's measured local-planarity curve
(category (a)) and derives the second by cross-validation on the inliers
(category (c)).

Contents
--------
`ransac_plane`      3-point RANSAC plane, orientation fixed by geometry alone.
`local_plane_residuals` / `noise_floor`
                    A1's local-planarity estimator, re-used verbatim so the
                    curve can be extended to the window size A2 actually fits
                    over instead of being read off the end of A1's table.
`PSpline2D`         Penalised tensor-product cubic B-spline over image
                    coordinates, with a second-difference roughness penalty,
                    IRLS robust weights, and block cross-validation for the
                    smoothing parameter.
`variogram_range`   Empirical residual autocorrelation length — used to size
                    the CV blocks so cross-validation is not fooled by
                    spatially correlated residuals.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.interpolate import BSpline
from scipy.sparse.linalg import splu


# ---------------------------------------------------------------- RANSAC plane


@dataclass
class PlaneFit:
    normal: np.ndarray  # unit, pointing toward the camera origin
    offset: float  # plane is {p : n.p = offset}
    inliers: np.ndarray  # bool mask over the input points
    threshold: float
    n_iters: int

    def signed_distance(self, pts: np.ndarray) -> np.ndarray:
        """Positive = on the camera side of the plane (i.e. above the ground)."""
        return pts @ self.normal - self.offset


def _orient_toward_camera(normal: np.ndarray, point_on_plane: np.ndarray) -> np.ndarray:
    """Point the normal at the camera origin.

    Purely geometric: the camera is at the origin and sees this surface, so the
    surface's outward normal has a positive component toward the origin. This
    is what makes "above the soil" mean "on the camera side", with no appeal to
    gravity, to a known camera height, or to where plants happen to be.
    """
    if normal @ (-point_on_plane) < 0:
        normal = -normal
    return normal


def ransac_plane(
    pts: np.ndarray,
    threshold: float,
    iters: int = 4000,
    seed: int = 20260901,
) -> PlaneFit:
    """Plain 3-point RANSAC, then a least-squares refit on the inliers.

    `threshold` is an orthogonal distance in the units of `pts` (rdu) and is the
    only quantity here that decides anything; `iters` is a compute budget and
    `seed` is reproducibility.
    """
    rng = np.random.default_rng(seed)
    n = pts.shape[0]
    best_mask = np.zeros(n, bool)
    best_count = -1
    idxs = rng.integers(0, n, size=(iters, 3))
    for tri in idxs:
        p0, p1, p2 = pts[tri]
        nrm = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(nrm)
        if norm < 1e-12:
            continue
        nrm = nrm / norm
        d = float(nrm @ p0)
        mask = np.abs(pts @ nrm - d) < threshold
        c = int(mask.sum())
        if c > best_count:
            best_count, best_mask = c, mask
    inl = pts[best_mask]
    centre = inl.mean(0)
    _, _, vt = np.linalg.svd(inl - centre, full_matrices=False)
    nrm = _orient_toward_camera(vt[-1], centre)
    d = float(nrm @ centre)
    mask = np.abs(pts @ nrm - d) < threshold
    return PlaneFit(nrm, d, mask, float(threshold), int(iters))


# ------------------------------------------------- A1's local-planarity curve


def local_plane_residuals(
    xyz_raster: np.ndarray, win: int, stride: int | None = None
) -> np.ndarray:
    """RMS orthogonal residual of a least-squares plane fit in each win x win
    window of a 3-D point raster. Identical to A1's `measure_quantisation.py`
    implementation, so the numbers are directly comparable."""
    if stride is None:
        stride = win
    h, w, _ = xyz_raster.shape
    out = []
    for r0 in range(0, h - win + 1, stride):
        for c0 in range(0, w - win + 1, stride):
            blk = xyz_raster[r0 : r0 + win, c0 : c0 + win].reshape(-1, 3)
            if not np.isfinite(blk).all():
                continue
            s = np.linalg.svd(blk - blk.mean(0), compute_uv=False)
            out.append(s[-1] / np.sqrt(blk.shape[0]))
    return np.asarray(out)


def noise_floor(resid: np.ndarray) -> dict:
    """A1's reading of that distribution: the 10th percentile is the flattest
    windows in the scene — flat enough to be a surface, common enough not to be
    a lucky window."""
    q = {f"p{p:02d}": float(np.percentile(resid, p)) for p in (1, 5, 10, 25, 50, 90)}
    return {"n_windows": int(resid.size), **q, "recommended_sigma_rdu": q["p10"]}


# ------------------------------------------------------------- 2-D P-spline


def _bspline_design(x: np.ndarray, knots: np.ndarray, degree: int = 3) -> sp.csr_matrix:
    return BSpline.design_matrix(np.clip(x, knots[degree], knots[-degree - 1]), knots, degree)


def _open_uniform_knots(lo: float, hi: float, n_seg: int, degree: int = 3) -> np.ndarray:
    inner = np.linspace(lo, hi, n_seg + 1)
    return np.concatenate([np.full(degree, lo), inner, np.full(degree, hi)])


def _diff_penalty(n: int, order: int = 2) -> sp.csr_matrix:
    D = sp.eye(n, format="csc")
    for _ in range(order):
        D = D[1:] - D[:-1]
    return (D.T @ D).tocsr()


class PSpline2D:
    """Penalised tensor-product cubic B-spline surface z ~= f(u, v).

    A second-order difference penalty on the coefficient grid controls
    smoothness through a single scalar `lam`. Two properties matter here:

    * the penalty, not the knot spacing, sets the effective resolution, so the
      basis size is an upper bound rather than a tuned constant (checked by
      refitting at a second basis size);
    * where there are no observations at all — under a closed canopy — the
      penalty alone decides the surface, which is exactly the "interpolated,
      not observed" case the coverage map has to flag.
    """

    def __init__(
        self,
        u_range: tuple[float, float],
        v_range: tuple[float, float],
        n_seg_u: int = 24,
        n_seg_v: int = 32,
        degree: int = 3,
    ):
        self.degree = degree
        self.tu = _open_uniform_knots(*u_range, n_seg_u, degree)
        self.tv = _open_uniform_knots(*v_range, n_seg_v, degree)
        self.nu = n_seg_u + degree
        self.nv = n_seg_v + degree
        self.Pu = _diff_penalty(self.nu)
        self.Pv = _diff_penalty(self.nv)
        self.coef: np.ndarray | None = None

    # -- basis ------------------------------------------------------------
    def design(self, u: np.ndarray, v: np.ndarray) -> sp.csr_matrix:
        Bu = _bspline_design(np.asarray(u, float), self.tu, self.degree)
        Bv = _bspline_design(np.asarray(v, float), self.tv, self.degree)
        return _row_kron(Bv, Bu)  # coefficient layout is (v, u), row-major

    @property
    def penalty(self) -> sp.csr_matrix:
        return sp.kron(self.Pv, sp.eye(self.nu)) + sp.kron(sp.eye(self.nv), self.Pu)

    # -- fitting ----------------------------------------------------------
    def fit(
        self,
        u: np.ndarray,
        v: np.ndarray,
        z: np.ndarray,
        lam: float,
        w: np.ndarray | None = None,
        B: sp.csr_matrix | None = None,
    ) -> "PSpline2D":
        B = self.design(u, v) if B is None else B
        w = np.ones_like(z) if w is None else w
        W = sp.diags(w)
        A = (B.T @ W @ B).tocsc() + lam * self.penalty.tocsc()
        # tiny ridge so unvisited coefficients (fully occluded corners) stay
        # finite rather than singular; 1e-9 is a numerical guard, not a model
        # choice, and is orders of magnitude below any lam the CV selects.
        A = A + 1e-9 * sp.eye(A.shape[0], format="csc")
        rhs = B.T @ (w * z)
        self.coef = splu(A).solve(rhs)
        return self

    def fit_robust(
        self,
        u: np.ndarray,
        v: np.ndarray,
        z: np.ndarray,
        lam: float,
        n_iter: int = 6,
        tukey_c: float = 4.685,
        w0: np.ndarray | None = None,
    ) -> tuple["PSpline2D", np.ndarray, float]:
        """IRLS with Tukey's bisquare. Returns (self, final weights, scale).

        `tukey_c = 4.685` is the standard 95 %-efficiency constant of the
        bisquare estimator, not a tuned value; the scale it multiplies is the
        MAD of the residuals, measured each iteration.
        """
        B = self.design(u, v)
        w = np.ones_like(z) if w0 is None else w0.copy()
        scale = np.nan
        for _ in range(n_iter):
            self.fit(u, v, z, lam, w=w, B=B)
            r = z - B @ self.coef
            scale = 1.4826 * np.median(np.abs(r - np.median(r)))
            if scale <= 0:
                break
            t = r / (tukey_c * scale)
            w = np.where(np.abs(t) < 1, (1 - t**2) ** 2, 0.0)
        return self, w, float(scale)

    # -- evaluation --------------------------------------------------------
    def eval_grid(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Evaluate on the outer product grid: returns (len(v), len(u))."""
        Bu = _bspline_design(np.asarray(u, float), self.tu, self.degree)
        Bv = _bspline_design(np.asarray(v, float), self.tv, self.degree)
        C = self.coef.reshape(self.nv, self.nu)
        return np.asarray(Bv @ (C @ Bu.T.toarray()))

    def eval_points(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        return self.design(u, v) @ self.coef


def _row_kron(A: sp.csr_matrix, Bm: sp.csr_matrix) -> sp.csr_matrix:
    """Row-wise Kronecker (Khatri-Rao) product of two CSR matrices with the
    same number of rows. Row i of the result is kron(A[i], B[i])."""
    A = A.tocsr()
    Bm = Bm.tocsr()
    n = A.shape[0]
    a_cnt = np.diff(A.indptr)
    b_cnt = np.diff(Bm.indptr)

    if a_cnt.size and a_cnt.min() == a_cnt.max() and b_cnt.min() == b_cnt.max():
        # Fast path: a B-spline design matrix has exactly degree+1 nonzeros per
        # row, so the whole product is one reshape-and-broadcast.
        na, nb = int(a_cnt[0]), int(b_cnt[0])
        ad = A.data.reshape(n, na)
        ai = A.indices.reshape(n, na).astype(np.int64)
        bd = Bm.data.reshape(n, nb)
        bi = Bm.indices.reshape(n, nb).astype(np.int64)
        data = (ad[:, :, None] * bd[:, None, :]).reshape(-1)
        indices = (ai[:, :, None] * Bm.shape[1] + bi[:, None, :]).reshape(-1)
        indptr = np.arange(n + 1, dtype=np.int64) * (na * nb)
        return sp.csr_matrix(
            (data, indices, indptr), shape=(n, A.shape[1] * Bm.shape[1])
        )

    per_row = a_cnt * b_cnt
    indptr = np.concatenate([[0], np.cumsum(per_row)])
    data = np.empty(indptr[-1], A.dtype)
    indices = np.empty(indptr[-1], np.int64)
    for i in range(n):
        ai = slice(A.indptr[i], A.indptr[i + 1])
        bi = slice(Bm.indptr[i], Bm.indptr[i + 1])
        d = np.outer(A.data[ai], Bm.data[bi]).ravel()
        idx = (A.indices[ai][:, None] * Bm.shape[1] + Bm.indices[bi][None, :]).ravel()
        s = slice(indptr[i], indptr[i + 1])
        data[s] = d
        indices[s] = idx
    return sp.csr_matrix(
        (data, indices, indptr), shape=(n, A.shape[1] * Bm.shape[1])
    )


# --------------------------------------------------- residual autocorrelation


def variogram_range(
    resid_img: np.ndarray, mask_img: np.ndarray, lags: np.ndarray
) -> dict:
    """Empirical semivariogram of a residual raster, and the lag at which it
    first reaches 95 % of its sill.

    Computed by shifting the raster along eight directions, so every pair at a
    given lag is used rather than a random subsample. The range is the distance
    beyond which two residuals are effectively independent — i.e. the minimum
    size of a cross-validation block that is not just predicting a point from
    its own neighbours' shared noise.
    """
    r = np.where(mask_img, resid_img, np.nan)
    dirs = [(1, 0), (0, 1), (1, 1), (1, -1), (2, 1), (1, 2), (2, -1), (1, -2)]
    dirs = [(dy / np.hypot(dy, dx), dx / np.hypot(dy, dx)) for dy, dx in dirs]
    gamma, counts, centres = [], [], []
    for lag in lags:
        acc, n = 0.0, 0
        for uy, ux in dirs:
            dy, dx = int(round(uy * lag)), int(round(ux * lag))
            if dy == 0 and dx == 0:
                continue
            a = r[max(dy, 0): r.shape[0] + min(dy, 0), max(dx, 0): r.shape[1] + min(dx, 0)]
            b = r[max(-dy, 0): r.shape[0] + min(-dy, 0), max(-dx, 0): r.shape[1] + min(-dx, 0)]
            d = (a - b) ** 2
            ok = np.isfinite(d)
            acc += float(d[ok].sum())
            n += int(ok.sum())
        if n < 500:
            continue
        centres.append(float(lag))
        gamma.append(0.5 * acc / n)
        counts.append(n)
    gamma = np.asarray(gamma)
    centres_a = np.asarray(centres)
    sill = float(np.nanmax(gamma))
    reached = np.where(gamma >= 0.95 * sill)[0]
    rng_lag = float(centres_a[reached[0]]) if len(reached) else float(centres_a[-1])

    # Practical range from an exponential model gamma = n + s(1 - exp(-d/a)),
    # fitted over short lags only. A real surface's variogram keeps creeping up
    # at long lags because of large-scale shape, so "95 % of the maximum" finds
    # the image size, not the decorrelation length; the short-lag fit does not.
    # Fit over short lags only. 60 px is where the empirical curve on this
    # scene has clearly plateaued (see fig_diagnostics, top right) and is a
    # display-scale choice, not a threshold: the range it yields feeds only the
    # *reported* block-CV comparison, never the lambda that is actually used.
    fit = centres_a <= 60
    practical = float("nan")
    try:
        from scipy.optimize import curve_fit

        def model(d, n, s, a):
            return n + s * (1 - np.exp(-d / a))

        p, _ = curve_fit(
            model, centres_a[fit], gamma[fit],
            p0=[gamma[fit][0], sill, 10.0],
            bounds=([0, 0, 0.5], [np.inf, np.inf, 200.0]), maxfev=20000,
        )
        practical = float(3.0 * p[2])  # 95 % of the sill for an exponential
        params = {"nugget": float(p[0]), "partial_sill": float(p[1]), "a_px": float(p[2])}
    except Exception as exc:  # pragma: no cover - diagnostics only
        params = {"error": repr(exc)}

    return {
        "lag_centres_px": centres,
        "semivariance": gamma.tolist(),
        "n_pairs_per_lag": counts,
        "sill": sill,
        "range_px_at_95pct_sill": rng_lag,
        "exponential_model": params,
        "practical_range_px": practical,
    }


def disk_fold_masks(
    shape: tuple[int, int],
    radii: list[float],
    k: int = 5,
    coverage: float = 0.2,
    seed: int = 13,
) -> list[np.ndarray]:
    """`k` hold-out masks, each a scatter of disks covering ~`coverage` of the
    image, with radii drawn from `radii`.

    Disks, not squares or scattered points, because the prediction task the
    surface actually faces is a *canopy hole*: a compact region with no ground
    observation anywhere inside it. Cross-validating on scattered points would
    score a task the surface never has to do — every held-out point would have a
    neighbour a pixel away — and would therefore select a far rougher surface
    than the one that survives the holes this scene really contains.
    """
    h, w = shape
    rng = np.random.default_rng(seed)
    masks = []
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(k):
        m = np.zeros((h, w), bool)
        while m.mean() < coverage:
            r = float(rng.choice(radii))
            cy = rng.uniform(0, h)
            cx = rng.uniform(0, w)
            m |= (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
        masks.append(m)
    return masks


def block_cv_folds(
    u: np.ndarray, v: np.ndarray, block_px: float, k: int = 5, seed: int = 11
) -> np.ndarray:
    """Assign each point to one of k folds by the spatial block it falls in.
    Blocks, not points: residuals are spatially correlated, and point-wise CV
    would choose an undersmoothed surface by predicting each point from its own
    neighbours' shared noise."""
    bu = np.floor(u / block_px).astype(np.int64)
    bv = np.floor(v / block_px).astype(np.int64)
    nbu = bu.max() + 1
    bid = bv * nbu + bu
    rng = np.random.default_rng(seed)
    uniq = np.unique(bid)
    assign = rng.integers(0, k, size=uniq.size)
    lut = np.zeros(uniq.max() + 1, np.int64)
    lut[uniq] = assign
    return lut[bid]
