"""Run everything and write outputs/: tables, figures, the Markdown report and the Excel reconciliation pack."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config as K  # noqa: E402
from . import facilities as F  # noqa: E402
from . import pipeline as PL  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eba800"]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
NEUTRAL = "#9a9893"
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
                     "axes.titleweight": "bold", "axes.titlelocation": "left", "lines.linewidth": 2})
CLOSE, OPEN = K.REPORTING_DATES[-1], K.REPORTING_DATES[3]


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def _waterfall(ax, labels, values, kinds, fmt="{:,.0f}"):
    run = 0.0
    for i, (v, k) in enumerate(zip(values, kinds)):
        if k == "total":
            ax.bar(i, v, color=NEUTRAL, width=0.62, edgecolor=SURFACE, linewidth=2)
            run, top = v, v
        else:
            ax.bar(i, v, bottom=run, color=C[0] if v >= 0 else C[1], width=0.62, edgecolor=SURFACE, linewidth=2)
            top = max(run, run + v)
            run += v
        ax.text(i, top + max(abs(np.array(values))) * 0.015, fmt.format(v) if k == "total" else f"{v:+,.0f}",
                ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(labels)), labels, fontsize=8.5)
    ax.grid(axis="x", visible=False)
    peak = max(np.cumsum([v if k == "step" else 0 for v, k in zip(values, kinds)]).max() + values[0], max(values))
    ax.set_ylim(0, peak * 1.12)


# ------------------------------------------------------------------ figures
def figures(out, S, B, A, cov, mov, eff, cal, sens, idx):
    fd = out / "figures"
    fd.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 4.6))
    short = ["Local\nprovisions", "Healthy\nnames", "Sensitive", "Pre-\ndoubtful", "Doubtful", "Compromised", "IFRS 9\nECL"]
    _waterfall(ax, short, B.mad_m.tolist(), B.kind.tolist())
    ax.set_title(f"From local provisions to IFRS 9 ECL, {CLOSE} (MAD million)")
    ax.set_ylabel("MAD million")
    _save(fig, fd / "fig1_bridge.png")

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, s in zip(axes, (1, 2, 3)):
        d = cov[cov.stage == s]
        ax.plot(d.month, d.coverage_pct, color=C[s - 1], marker="o", ms=4)
        ax.set_title(f"Stage {s} coverage (ECL / EAD)")
        ax.set_ylim(0, d.coverage_pct.max() * 1.3)
        ax.yaxis.set_major_formatter(lambda v, _, s=s: f"{v:.1f}%" if s == 1 else f"{v:.0f}%")
        ax.tick_params(axis="x", rotation=45, labelsize=8)
    _save(fig, fd / "fig2_coverage_by_stage.png")

    fig, ax = plt.subplots(figsize=(10, 4.6))
    lab = {"Opening allowance": "Opening\n" + OPEN, "Transfer to Stage 1": "To S1", "Transfer to Stage 2": "To S2",
           "Transfer to Stage 3": "To S3", "Remeasurement after stage transfer": "Remeasured\nafter transfer",
           "Change in exposure": "Exposure", "Change in risk parameters and time in default": "Risk\nparameters",
           "Write-offs": "Write-offs", "Change in forward-looking scenarios": "Scenarios", "New exposures": "New",
           "Repaid or left the bank": "Repaid", "Closing allowance": "Closing\n" + CLOSE}
    rows = [r for r in mov.index if not r.startswith("Transfer")]          # transfers net to zero in total
    _waterfall(ax, [lab[r] for r in rows], mov.loc[rows, "Total"].tolist(),
               ["total" if r in ("Opening allowance", "Closing allowance") else "step" for r in rows])
    ax.set_title("Loss allowance movement, all stages (MAD million)")
    _save(fig, fd / "fig3_allowance_movement.png")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(eff.months_before_default, eff.in_stage_2_pct, color=C[0], marker="o", ms=4)
    ax.plot(eff.months_before_default, eff.local_sensitive_pct, color=C[1], marker="o", ms=4)
    ax.text(12.3, eff.in_stage_2_pct.iloc[-1], "IFRS 9 Stage 2", color=INK, va="center", ha="right", fontsize=9)
    ax.text(12.3, eff.local_sensitive_pct.iloc[-1], "Local 'sensitive'", color=INK, va="center", ha="right", fontsize=9)
    ax.set_xlim(0.5, 15.5)
    ax.invert_xaxis()
    ax.set_xlabel("Months before default")
    ax.set_ylabel("% of 2025 defaults already flagged")
    ax.set_ylim(0, 100)
    ax.set_title("How early do the two frameworks see 2025's defaults?")
    _save(fig, fd / "fig4_stage2_effectiveness.png")

    fig, ax = plt.subplots(figsize=(8, 4.4))
    c = cal[cal.names >= 20]
    x = c.index.to_numpy()
    ax.vlines(x, c.ci_low * 100, c.ci_high * 100, color=GRID, linewidth=6)
    ax.scatter(x, c.observed * 100, color=INK2, s=40, zorder=3, label="Observed 2025 default rate (90% interval)")
    ax.plot(x, c.pd_pit * 100, color=C[0], marker="o", ms=5, label="Predicted 12-month PD (PIT, weighted)")
    ax.plot(x, c.pd_ttc * 100, color=C[2], marker="o", ms=5, label="Through-the-cycle PD")
    ax.set_yscale("log")
    ax.set_xlabel("Internal grade at December 2024")
    ax.set_ylabel("% (log scale)")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.set_title("PD backtest: December 2024 predictions vs 2025 defaults")
    _save(fig, fd / "fig5_pd_backtest.png")

    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    s = sens.iloc[1:].sort_values("change_pct")
    ax.barh(s.scenario, s.change_pct, color=[C[0] if v >= 0 else C[1] for v in s.change_pct], height=0.6,
            edgecolor=SURFACE, linewidth=2)
    for y, v in enumerate(s.change_pct):
        ax.text(v + (0.4 if v >= 0 else -0.4), y, f"{v:+.1f}%", va="center", ha="left" if v >= 0 else "right", fontsize=8.5)
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.set_xlim(s.change_pct.min() - 5, s.change_pct.max() + 5)
    ax.set_xlabel(f"Change in total ECL vs reported, {CLOSE}")
    ax.grid(axis="y", visible=False)
    ax.set_title("What moves the allowance")
    _save(fig, fd / "fig6_sensitivities.png")

    fig, ax = plt.subplots(figsize=(8, 3.8))
    for i, col in enumerate(idx.columns):
        ax.plot(idx.index, idx[col], color=C[i], marker="o", ms=3)
        ax.text(len(idx) - 0.6, idx[col].iloc[-1], col, color=INK, va="center", fontsize=9)
    ax.set_xticks(range(0, len(idx), 4), idx.index[::4])
    ax.set_xlim(-0.5, len(idx) + 4)
    ax.set_ylabel("Index, 2020Q4 = 100")
    ax.set_title("Collateral values follow the official IPAI property price index")
    _save(fig, fd / "fig7_collateral_index.png")


# ------------------------------------------------------------------ Excel reconciliation pack
def excel_pack(path, S, mov, sens, cal, eff):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    F_ = "Arial"
    h = Font(name=F_, bold=True, color="FFFFFF")
    hfill = PatternFill("solid", fgColor="2A3B4C")
    blue = Font(name=F_, color="0000FF")
    green = Font(name=F_, color="008000")
    norm = Font(name=F_)
    bold = Font(name=F_, bold=True)
    title = Font(name=F_, bold=True, size=13)
    thin = Border(top=Side(style="thin", color="999999"))
    mad = '#,##0.0;(#,##0.0);"-"'
    pct = '0.0%;(0.0%);"-"'

    def header(ws, row, cols):
        for j, c in enumerate(cols, 1):
            cell = ws.cell(row, j, c)
            cell.font, cell.fill = h, hfill
            cell.alignment = Alignment(wrap_text=True, vertical="center")

    def widths(ws, w):
        for j, x in enumerate(w, 1):
            ws.column_dimensions[get_column_letter(j)].width = x

    # --- README
    ws = wb.active
    ws.title = "README"
    lines = [("IFRS 9 vs local provisioning: reconciliation pack", title),
             (f"Reporting date {CLOSE}. Synthetic Moroccan corporate portfolio; amounts in MAD million.", norm),
             ("", norm),
             ("Blue cells are inputs you can change (local provisioning rates, eligible collateral share).", blue),
             ("Green cells link to another sheet. Black cells are formulas.", norm),
             ("IFRS 9 ECL, EAD and stages come from the Python engine (src/ifrs9) and are pasted as values.", norm),
             ("Local provisions are recomputed in this workbook from the inputs on 'Assumptions'.", norm),
             ("", norm),
             ("Sheets", bold),
             ("Assumptions: local rates and collateral eligibility (inputs)", norm),
             ("Counterparties: one row per name, local provision formulas, IFRS 9 values", norm),
             ("Stage x Bucket: exposure, ECL and local provisions by IFRS 9 stage and local bucket", norm),
             ("Bridge: from local provisions to IFRS 9 ECL, bucket by bucket", norm),
             ("Movement FY2025: IFRS 7.35H-style roll-forward of the allowance by stage", norm),
             ("Sensitivities, PD Backtest, Stage 2 Timing: validation tables", norm)]
    for i, (t, f) in enumerate(lines, 1):
        ws.cell(i, 1, t).font = f
    widths(ws, [110])

    # --- Assumptions
    A = wb.create_sheet("Assumptions")
    A["A1"] = "Local provisioning parameters (individual accounts)"
    A["A1"].font = title
    header(A, 3, ["Local bucket", "Minimum provision rate", "Rule (simplified)"])
    rule = {"Healthy": "No specific provision", "Sensitive": "Watch list; revised circular, from 2027",
            "Pre-doubtful": "90-179 days past due", "Doubtful": "180-359 days past due",
            "Compromised": "360+ days past due"}
    for i, b in enumerate(K.LOCAL_BUCKETS, 4):
        A.cell(i, 1, b).font = norm
        c = A.cell(i, 2, K.LOCAL_RATES[b])
        c.font, c.number_format = blue, pct
        A.cell(i, 3, rule[b]).font = norm
    A["A10"], A["B10"] = "Eligible share of current collateral value", K.LOCAL_COLLATERAL_ELIGIBLE
    A["A10"].font, A["B10"].font, A["B10"].number_format = norm, blue, pct
    A["B10"].comment = Comment("Assumption: share of the current (IPAI-indexed) mortgage value deducted "
                               "from the provision base. See docs/LOCAL_RULES.md.", "ifrs9")
    A["A12"] = ("Source: public descriptions of Bank Al-Maghrib circular 19/G and its revision "
                "(see docs/LOCAL_RULES.md). Check the circular itself before any real use.")
    A["A12"].font = Font(name=F_, italic=True, color="52514E")
    widths(A, [44, 22, 44])

    # --- Counterparties
    D = wb.create_sheet("Counterparties")
    cols = ["Counterparty", "Segment", "Grade", "Days past due", "IFRS 9 stage", "Local bucket",
            "On-balance outstanding", "Collateral value", "Public guarantee cover", "Provision base",
            "Local rate", "Local provision", "EAD", "IFRS 9 ECL", "ECL - local"]
    header(D, 1, cols)
    S = S.sort_values(["stage", "local_bucket", "counterparty_id"]).reset_index(drop=True)
    n = len(S)
    for i, r in enumerate(S.itertuples(), 2):
        vals = [r.counterparty_id, r.segment, str(r.internal_rating), int(r.days_past_due), int(r.stage), r.local_bucket,
                round(r.on_balance, 4), round(r.collateral_value, 4), r.public_guarantee_cover]
        for j, v in enumerate(vals, 1):
            D.cell(i, j, v).font = norm
        D.cell(i, 10, f"=MAX(G{i}-Assumptions!$B$10*H{i},0)*(1-I{i})")
        D.cell(i, 11, f"=INDEX(Assumptions!$B$4:$B$8,MATCH(F{i},Assumptions!$A$4:$A$8,0))").font = green
        D.cell(i, 12, f"=J{i}*K{i}")
        D.cell(i, 13, round(r.ead, 4)).font = norm
        D.cell(i, 14, round(r.ecl, 4)).font = norm
        D.cell(i, 15, f"=N{i}-L{i}")
        for j in (7, 8, 10, 12, 13, 14, 15):
            D.cell(i, j).number_format = mad
        D.cell(i, 9).number_format = D.cell(i, 11).number_format = pct
    last = n + 1
    D.cell(1, 14).comment = Comment("Computed by the Python engine (src/ifrs9/ecl.py), pasted as values.", "ifrs9")
    D.freeze_panes = "B2"
    D.auto_filter.ref = f"A1:O{last}"
    widths(D, [13, 18, 7, 9, 8, 13, 13, 12, 11, 12, 9, 12, 12, 12, 12])
    rng = lambda col: f"Counterparties!${col}$2:${col}${last}"  # noqa: E731

    # --- Stage x Bucket
    X = wb.create_sheet("Stage x Bucket")
    X["A1"] = f"Stage x local bucket, {CLOSE} (MAD million)"
    X["A1"].font = title
    blocks = [("EAD", "M"), ("IFRS 9 ECL", "N"), ("Local provision", "L")]
    row = 3
    for name, col in blocks:
        X.cell(row, 1, name).font = bold
        header(X, row + 1, ["Local bucket", "Stage 1", "Stage 2", "Stage 3", "Total"])
        for i, b in enumerate(K.LOCAL_BUCKETS):
            rr = row + 2 + i
            X.cell(rr, 1, b).font = norm
            for s in (1, 2, 3):
                c = X.cell(rr, 1 + s, f'=SUMIFS({rng(col)},{rng("F")},$A{rr},{rng("E")},{s})')
                c.number_format = mad
            X.cell(rr, 5, f"=SUM(B{rr}:D{rr})").number_format = mad
        tr = row + 2 + len(K.LOCAL_BUCKETS)
        X.cell(tr, 1, "Total").font = bold
        for j in range(2, 6):
            c = X.cell(tr, j, f"=SUM({get_column_letter(j)}{row + 2}:{get_column_letter(j)}{tr - 1})")
            c.number_format, c.font, c.border = mad, bold, thin
        row = tr + 3
    widths(X, [18, 14, 14, 14, 14])

    # --- Bridge
    Bs = wb.create_sheet("Bridge")
    Bs["A1"] = f"Bridge from local provisions to IFRS 9 ECL, {CLOSE} (MAD million)"
    Bs["A1"].font = title
    header(Bs, 3, ["Step", "Local provision", "IFRS 9 ECL", "Difference", "Main driver"])
    driver = {"Healthy": "IFRS 9 books 12-month ECL from day one, and lifetime ECL once risk rises (Stage 2)",
              "Sensitive": "Lifetime expected loss vs a flat 10% minimum",
              "Pre-doubtful": "Expected loss given default vs a flat 20%",
              "Doubtful": "Expected loss given default vs a flat 50%",
              "Compromised": "Collateral recoveries count under IFRS 9; locally the minimum is 100% of the base"}
    for i, b in enumerate(K.LOCAL_BUCKETS, 4):
        Bs.cell(i, 1, b).font = norm
        Bs.cell(i, 2, f'=SUMIFS({rng("L")},{rng("F")},A{i})').number_format = mad
        Bs.cell(i, 3, f'=SUMIFS({rng("N")},{rng("F")},A{i})').number_format = mad
        Bs.cell(i, 4, f"=C{i}-B{i}").number_format = mad
        Bs.cell(i, 5, driver[b]).font = norm
    t = 4 + len(K.LOCAL_BUCKETS)
    Bs.cell(t, 1, "Total").font = bold
    for j in (2, 3, 4):
        c = Bs.cell(t, j, f"=SUM({get_column_letter(j)}4:{get_column_letter(j)}{t - 1})")
        c.number_format, c.font, c.border = mad, bold, thin
    Bs.cell(t + 2, 1, "IFRS 9 ECL / local provisions").font = norm
    c = Bs.cell(t + 2, 3, f"=IFERROR(C{t}/B{t},0)")
    c.number_format = "0.00x"
    widths(Bs, [16, 16, 14, 14, 90])

    # --- Movement
    Mv = wb.create_sheet("Movement FY2025")
    Mv["A1"] = f"Loss allowance roll-forward {OPEN} to {CLOSE} (MAD million), IFRS 7.35H style"
    Mv["A1"].font = title
    header(Mv, 3, ["", "Stage 1", "Stage 2", "Stage 3", "Total"])
    for i, (lbl, r) in enumerate(mov.iterrows(), 4):
        Mv.cell(i, 1, lbl).font = bold if "allowance" in lbl else norm
        for j, s in enumerate(["Stage 1", "Stage 2", "Stage 3"], 2):
            if lbl == "Closing allowance":
                c = Mv.cell(i, j, f"=SUM({get_column_letter(j)}4:{get_column_letter(j)}{i - 1})")
                c.font, c.border = bold, thin
            else:
                c = Mv.cell(i, j, round(float(r[s]), 4))
                c.font = norm
            c.number_format = mad
        Mv.cell(i, 5, f"=SUM(B{i}:D{i})").number_format = mad
    ci = 4 + len(mov) - 1
    Mv.cell(ci + 2, 1, "Check: closing = reported ECL").font = norm
    c = Mv.cell(ci + 2, 5, f"=ROUND(E{ci}-Bridge!C{t},3)")
    c.number_format = '0.000;(0.000);"OK"'
    widths(Mv, [48, 14, 14, 14, 14])

    # --- Sensitivities
    Se = wb.create_sheet("Sensitivities")
    Se["A1"] = f"ECL sensitivities, {CLOSE} (MAD million)"
    Se["A1"].font = title
    header(Se, 3, ["Run", "Total ECL", "Change", "Change %"])
    for i, r in enumerate(sens.itertuples(), 4):
        Se.cell(i, 1, r.scenario).font = norm
        Se.cell(i, 2, round(r.ecl_mad_m, 4)).number_format = mad
        Se.cell(i, 3, f"=B{i}-$B$4").number_format = mad
        Se.cell(i, 4, f"=IFERROR(C{i}/$B$4,0)").number_format = pct
    widths(Se, [44, 14, 14, 12])

    # --- PD backtest
    Pb = wb.create_sheet("PD Backtest")
    Pb["A1"] = "12-month PD at December 2024 vs defaults observed in 2025 (performing names)"
    Pb["A1"].font = title
    header(Pb, 3, ["Grade", "Names", "Predicted PD (PIT)", "TTC PD", "Defaults", "Observed rate",
                   "90% interval low", "90% interval high", "Within interval"])
    for i, (g, r) in enumerate(cal.iterrows(), 4):
        vals = [int(g), int(r.names), r.pd_pit, r.pd_ttc, int(r.defaults)]
        for j, v in enumerate(vals, 1):
            Pb.cell(i, j, v).font = norm
        Pb.cell(i, 6, f"=IFERROR(E{i}/B{i},0)")
        Pb.cell(i, 7, float(r.ci_low)).font = norm
        Pb.cell(i, 8, float(r.ci_high)).font = norm
        Pb.cell(i, 9, f'=IF(AND(C{i}>=G{i},C{i}<=H{i}),"Yes","No")')
        for j in (3, 4, 6, 7, 8):
            Pb.cell(i, j).number_format = "0.00%"
    widths(Pb, [8, 9, 16, 10, 10, 13, 14, 14, 13])

    # --- Stage 2 timing
    Ef = wb.create_sheet("Stage 2 Timing")
    Ef["A1"] = "Share of 2025 defaults already flagged k months before default"
    Ef["A1"].font = title
    header(Ef, 3, ["Months before default", "Defaults", "In IFRS 9 Stage 2", "Locally 'sensitive'"])
    for i, r in enumerate(eff.itertuples(), 4):
        Ef.cell(i, 1, int(r.months_before_default)).font = norm
        Ef.cell(i, 2, int(r.defaults_observed)).font = norm
        Ef.cell(i, 3, r.in_stage_2_pct / 100).number_format = pct
        Ef.cell(i, 4, r.local_sensitive_pct / 100).number_format = pct
    widths(Ef, [22, 10, 18, 18])

    for w in wb.worksheets:
        w.sheet_view.showGridLines = False
    wb.save(path)


# ------------------------------------------------------------------ Markdown report
def _md(df, fmt="{:,.1f}"):
    d = df.copy()
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join([""] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in d.iterrows():
        lines.append("| " + " | ".join([str(i)] + [fmt.format(v) if isinstance(v, (int, float, np.floating)) else str(v)
                                                     for v in r]) + " |")
    return "\n".join(lines)


def write_report(out, S, B, cov, mov, eff, cal, bys, sens, cyc, legacy_local, eng):
    tot_ecl, tot_loc = S.ecl.sum(), S.local_provision.sum()
    c = cov[cov.month == CLOSE].set_index("stage")
    e6 = eff.set_index("months_before_default")
    sb = PL.stage_bucket(S, "ead")
    txt = f"""# IFRS 9 provisioning and reconciliation with local rules

Synthetic Moroccan corporate portfolio, reporting date **{CLOSE}**. Amounts in MAD million.
Generated by `python scripts/run_all.py`; every number below is recomputed on each run.

## Headline

| | MAD million |
|---|---|
| Exposure at default (EAD) | {S.ead.sum():,.0f} |
| IFRS 9 expected credit loss (consolidated) | {tot_ecl:,.1f} |
| Local provisions, revised rules with the sensitive class (individual accounts) | {tot_loc:,.1f} |
| Local provisions, legacy rules (no sensitive class) | {legacy_local:,.1f} |
| IFRS 9 / local | {tot_ecl / tot_loc:.2f}x |

## Staging and coverage

| Stage | Names | EAD | Share of EAD | ECL | Coverage |
|---|---|---|---|---|---|
""" + "\n".join(f"| Stage {s} | {int(c.at[s, 'names'])} | {c.at[s, 'ead']:,.0f} | {c.at[s, 'ead_share_pct']:.1f}% | "
                f"{c.at[s, 'ecl']:,.1f} | {c.at[s, 'coverage_pct']:.2f}% |" for s in (1, 2, 3)) + f"""

## Stage x local bucket (EAD)

{_md(sb, "{:,.0f}")}

## Bridge: local provisions to IFRS 9 ECL

{_md(B.set_index("item")[["mad_m"]].rename(columns={"mad_m": "MAD million"}), "{:+,.1f}")}

Healthy names carry no local provision but {B.mad_m.iloc[1]:,.0f} of IFRS 9 ECL. On defaulted loans the two
frameworks disagree in both directions: flat 20% and 50% minimums sit below the expected loss of recent
defaults, while the 100% minimum on compromised loans sits above it, because IFRS 9 counts collateral
recoveries.

## Allowance movement {OPEN} to {CLOSE}

{_md(mov)}

Transfers move the opening allowance between stages and net to zero. This synthetic book has no new or
repaid names, so those lines are omitted.

## Validation

**PD backtest** (December 2024 predictions, 2025 defaults, performing names):

{_md(cal[["names", "pd_pit", "pd_ttc", "defaults", "observed", "ci_low", "ci_high"]], "{:.4f}")}

By stage: Stage 1 predicted {bys.at[1, 'pd_pit']:.2%} vs observed {bys.at[1, 'observed']:.2%};
Stage 2 predicted {bys.at[2, 'pd_pit']:.2%} vs observed {bys.at[2, 'observed']:.2%}.

**Stage 2 timing**: of the {int(e6.at[6, 'defaults_observed'])} counterparties that defaulted in 2025,
{e6.at[6, 'in_stage_2_pct']:.0f}% were already in Stage 2 six months before default
({e6.at[6, 'local_sensitive_pct']:.0f}% classified sensitive locally), and {e6.at[3, 'in_stage_2_pct']:.0f}% three months before.

**Credit cycle implied by observed default rates** (0 = average year):

{_md(cyc.set_index("year"), "{:.3f}")}

## Sensitivities

{_md(sens.set_index("scenario"), "{:,.1f}")}

## Model facts

- One-year migration matrix estimated on {int(eng.counts.to_numpy().sum()):,} grade-years (2021-2023 cohorts).
- PD smoothing: logit(PD) = {eng.logit[0]:.2f} + {eng.logit[1]:.3f} x grade, so one notch multiplies PD by {np.exp(eng.logit[1]):.2f}.
- Scenario weights {CLOSE[:4]}: """ + ", ".join(f"{k} {v['weight']:.0%}" for k, v in K.SCENARIOS[int(CLOSE[:4])].items()) + """.
"""
    (out / "ifrs9_report.md").write_text(txt)


# ------------------------------------------------------------------ run
def run(out=None, seed=42):
    out = Path(out or ROOT / "outputs")
    out.mkdir(parents=True, exist_ok=True)
    eng = PL.Engine(seed)
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    for name, df in eng.D.items():
        df.to_csv(data / (f"{name}.csv.gz" if len(df) > 50000 else f"{name}.csv"), index=False)
    eng.terms.to_csv(data / "facility_terms.csv", index=False)

    A = eng.all_dates()
    S = A[A.month == CLOSE].copy()
    B = PL.bridge(S)
    cov = PL.coverage_by_stage(A)
    mov = PL.movement(eng, OPEN, CLOSE)
    cal, bys = PL.pd_backtest(eng, OPEN)
    eff = PL.stage2_effectiveness(eng, CLOSE[:4])
    sens = PL.sensitivities(eng, CLOSE)
    cyc = PL.implied_cycle(eng)
    legacy_local = eng.snapshot(CLOSE, sensitive_regime=False).local_provision.sum()

    A.to_csv(out / "ecl_by_counterparty_all_dates.csv.gz", index=False)
    for name, df in {"stage_x_bucket_ead": PL.stage_bucket(S, "ead"), "stage_x_bucket_ecl": PL.stage_bucket(S, "ecl"),
                     "stage_x_bucket_local": PL.stage_bucket(S, "local_provision"), "bridge": B, "movement": mov,
                     "coverage_by_stage": cov, "pd_backtest": cal, "stage2_timing": eff, "sensitivities": sens,
                     "implied_credit_cycle": cyc,
                     "pd_by_grade": eng.pd12.to_frame(),
                     "migration_matrix": pd.DataFrame(eng.M, index=[*map(str, range(1, 10)), "D"],
                                                      columns=[*map(str, range(1, 10)), "D"])}.items():
        df.to_csv(out / f"{name}.csv", index=name not in ("bridge", "coverage_by_stage", "stage2_timing",
                                                          "sensitivities", "implied_credit_cycle"))
    figures(out, S, B, A, cov, mov, eff, cal, sens, F.property_index())
    excel_pack(out / f"reconciliation_pack_{CLOSE}.xlsx", S, mov, sens, cal, eff)
    write_report(out, S, B, cov, mov, eff, cal, bys, sens, cyc, legacy_local, eng)
    return {"S": S, "B": B, "mov": mov, "sens": sens, "cal": cal, "eff": eff, "legacy_local": legacy_local}
