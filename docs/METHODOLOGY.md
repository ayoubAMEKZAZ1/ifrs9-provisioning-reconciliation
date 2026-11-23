# Methodology

Every parameter named below lives in `src/ifrs9/config.py`. All values are illustrative choices for a
synthetic book, not a bank's calibrated model.

## 1. Portfolio

The counterparty panel is the same synthetic book as in `credit-early-warning-system`:
- 3,000 Moroccan corporates, observed monthly from 2021 to 2025, in four segments (SME, mid-corporate, large corporate, property developer).
- Annual ratings on a 1-9 scale, days past due and defaults.

`facilities.py` adds the terms that provisioning needs:

| Item | How it is built |
|---|---|
| Products | Each counterparty's limit is split into a term loan, an overdraft line and signature commitments (`PRODUCT_MIX`). Developers are almost all term debt. |
| Drawn amounts | Term loan balance, plus the overdraft at the panel's utilisation. |
| EAD | Drawn + 60% CCF on the undrawn overdraft + 50% CCF on signature commitments. In default, only drawn amounts count. |
| Maturity | Term loans mature between mid-2026 and 2031 (developers by 2028) and amortise straight-line. Overdrafts are given a 3-year behavioural life and signature lines 1.5 years (IFRS 9 B5.5.40). |
| Collateral | All developers and part of SMEs and mid-corporates have a mortgage, valued at an LTV of 55-90% at origination. |
| Collateral indexation | Values are indexed quarterly to the **official IPAI price index** (Bank Al-Maghrib / ANCFCC), the same public series used in `morocco-real-estate-credit-signals`. Commercial property uses the commercial index; developers use the average of the land and residential indices. |
| Public guarantee | 30% of SMEs carry a public guarantee covering 60% of the residual loss, of the kind offered by the national guarantee scheme. |

## 2. Probability of default

- **Development window.** The PD model uses only 2021-2023 data; the reporting dates are 2024-2025. So the 2025 backtest is out of time.
- **Migration matrix.** One-year transitions are counted from monthly cohorts: grade now → grade in 12 months, or D if the name defaults within the year. Names that leave the book are dropped. The default column is smoothed with a binomial logistic fit, logit(PD) = a + b × grade, which keeps PDs monotone where grades 1-2 have few observations. Non-default transitions get a light prior on the diagonal.
- **Lifetime PD.** Cumulative PD after *k* years comes from the k-th power of the matrix, with D absorbing. The conditional yearly hazard is h_k = (cum_k − cum_{k−1}) / (1 − cum_{k−1}).
- **Forward-looking adjustment.** For years 1-3, each scenario gives a credit-cycle index Z. The point-in-time hazard is Φ((Φ⁻¹(h) − √ρ·Z) / √(1 − ρ)), with ρ = 0.12. From year 4, the hazard reverts to its through-the-cycle value.
- **Scenarios.** Three scenarios (base, upside, downside), reweighted every year. They also carry a property-price path that moves collateral values. In a bank, Z would come from a satellite model on GDP, sector output and rates. The report shows the Z implied by each year's observed default rate as a sanity check.

## 3. Loss given default

Recoveries come from three parts:
- **Collateral:** min(EAD, collateral × (1 − 35% haircut)), discounted at the EIR over 3.5 years, since judicial recovery in Morocco is slow.
- **Unsecured remainder:** recovers 1 − 65%.
- **Public guarantee:** where present, the guaranteed share of that remainder recovers 95%.

LGD = 1 − PV(recoveries) / EAD, with a 5% floor. For defaulted names, LGD rises 20% per year spent in default, because the longer a file stays open, the less it recovers.

## 4. Staging (significant increase in credit risk)

Staging is at counterparty level, so all of a name's facilities share its stage.

| Stage | Rule |
|---|---|
| 3 | In default (90+ days past due) |
| 2 | Any of the triggers below, then held in Stage 2 for 3 months after the last trigger (probation) |
| 1 | Everything else |

The Stage 2 triggers are:
- **Relative PD test:** the 12-month TTC PD of the current grade is at least 3× the origination PD, which is two notches. Grades 1-3 are exempt as low credit risk (IFRS 9 5.5.10).
- **Absolute PD threshold:** grade 7 or worse. This is a practical backstop many banks use. It is a policy choice, and the sensitivities show what removing it does.
- **Days-past-due backstop:** more than 30 days past due (IFRS 9 5.5.11).
- **Watch list:** grade 8-9.

## 5. Expected credit loss

ECL = Σ over scenarios s of weight_s × Σ over years k and products p of marginal PD_s,k × LGD_s,k × EAD_p,k × (1 + EIR)^−(k − 0.5)

- **Stage 1:** year 1 only, so the 12-month ECL. A facility with less than a year left is cut at its maturity.
- **Stage 2:** every year up to each product's remaining life.
- **Stage 3:** LGD in default × drawn EAD.

## 6. Local classification and the reconciliation

`local_rules.py` classifies every counterparty in one of five buckets, then computes the local provision. docs/LOCAL_RULES.md gives the sources.

| Output | What it shows |
|---|---|
| Stage × bucket matrix | Exposure, ECL and local provisions in each cell |
| Bridge | Local provisions → IFRS 9 ECL. Each step is the difference (ECL − local provision) within one local bucket |
| Allowance movement | IFRS 7.35H-style roll-forward by stage (see below) |

The allowance movement is built as follows:
- **Transfers** move the opening allowance of names that changed stage.
- **Remeasurement** is split into three parts: after a stage transfer, from changes in exposure (opening coverage × change in EAD), and from risk parameters and time in default.
- **Scenario effect** is the closing ECL under the closing scenarios minus the closing ECL under the opening scenarios.
- **Write-offs** release the opening allowance of names written off during the year.

## 7. Validation

- **PD backtest.** December 2024 predictions are compared with 2025 defaults, by grade, with Jeffreys 90% intervals.
- **Stage 2 timing.** For every 2025 default, the table records whether the name was already in Stage 2, or classified sensitive locally, 1 to 12 months before.
- **Sensitivities.** The run is repeated with each scenario at 100%, property values −15%, LGD +10 points, the SICR threshold at 1 and 3 notches, no absolute threshold and no probation.

## What this is not

- **Not a calibrated model of any bank.** The data is synthetic. The value is in the mechanics, the reconciliation logic and the controls.
- **No new or repaid names.** The synthetic book has neither, so those lines of the movement table are empty and omitted.
- **No modification gains and losses, POCI assets or individual (expert) Stage 3 assessments.**
