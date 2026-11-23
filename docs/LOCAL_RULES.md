# Local classification rules: what is implemented and where it comes from

Moroccan banks publish consolidated accounts under IFRS 9 and individual (statutory) accounts under
Bank Al-Maghrib's rules on classifying and provisioning loans (circular 19/G of 2002, amended, and its
revision). This repository applies a **simplified reading of public descriptions** of those rules. It is
not a legal summary: check the circular itself before any real use.

## Implemented

| Bucket | Trigger used here | Minimum provision |
|---|---|---|
| Compromised | 360+ days past due | 100% of the provision base |
| Doubtful | 180-359 days past due | 50% |
| Pre-doubtful | 90-179 days past due | 20% |
| Sensitive | Performing, but grade 8-9, or 30+ days past due, or an exposure of MAD 20m+ at grade 7 | 10% (revised circular) |
| Healthy | Everything else | none |

The classification and the provision base work as follows:
- **Contagion:** classification is by counterparty, so all of a name's claims share the worst bucket.
- **Provision base:** on-balance outstanding, minus 50% of the current (IPAI-indexed) mortgage value, minus the public-guarantee share. Both the 50% and the guarantee treatment are assumptions (`LOCAL_COLLATERAL_ELIGIBLE` in config.py).
- **Left out:** reserved interest and off-balance commitments.
- **Legacy rules:** `LOCAL_SENSITIVE_REGIME = False` reproduces them, with no sensitive class. The report gives both totals.

## Public sources used

- **Overdue-loan categories and minimum provisions.** The three categories (pre-doubtful, doubtful, compromised) and the 20% / 50% / 100% minimums are described in the financial press. The usual day thresholds are 90, 180 and 360 days.
  - La Vie Éco, on circular 19/G and its 2004 amendment: https://www.lavieeco.com/?p=8750
  - La Vie Éco, on the 90 / 180 / 360-day thresholds: https://www.lavieeco.com/?p=44144
  - Finances News: https://www.fnh.ma/article/actualite-financiere-maroc/banques-toujours-pas-d-accord-a-l-horizon-entre-bam-et-la-dgi-sur-la-fiscalite-des-provisions
- **Sensitive class (revised circular).** La Vie Éco (12 September 2026) reports the revised circular applies from 2027, with sensitive loans provisioned at a minimum of 10%: https://www.lavieeco.com/?p=459602
- **Purpose of the reform.** It widens the default definition and adds an intermediate "sensitive" risk class:
  - Le360, on the two-step timetable: https://fr.le360.ma/economie/banques-classification-des-creances-la-nouvelle-reforme-se-fera-en-deux-etapes-194900/
  - EcoActu, interview with Bank Al-Maghrib's director of banking supervision: https://ecoactu.ma/?p=18228
- **The MAD 20m threshold for sensitive exposures** is from earlier descriptions of the draft rules: https://fnh.ma/article/bourse-finances/reglementation-prudentielle-le-repit-pour-les-banques-ne-sera-que-passager
- **Two frameworks, two sets of accounts.** IFRS 9 in consolidated accounts and circular 19/G in individual accounts: https://fnh.ma/article/bourse-finances/reglementation-prudentielle-les-banques-a-l-epreuve-de-nouvelles-contraintes

## Why the two frameworks give different numbers

| | IFRS 9 | Local rules |
|---|---|---|
| Performing loans | 12-month ECL from day one; lifetime ECL after a significant increase in risk | No specific provision; 10% once a name is sensitive (from 2027) |
| Defaulted loans | Expected loss given default: collateral recoveries count, discounted | Flat minimums by age of arrears: 20%, 50%, 100% |
| Forward-looking | Probability-weighted macro scenarios | None |
| Unit | Facility (here: counterparty) | Counterparty (contagion) |

The bridge in the report shows each of these effects in MAD.
