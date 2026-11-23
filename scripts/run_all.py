"""Generate the portfolio, run the IFRS 9 engine and the local-rules reconciliation, write outputs/."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ifrs9.report import run  # noqa: E402

if __name__ == "__main__":
    t = time.time()
    r = run()
    S = r["S"]
    print(f"IFRS 9 ECL {S.ecl.sum():,.1f} | local provisions {S.local_provision.sum():,.1f} "
          f"(legacy rules {r['legacy_local']:,.1f}) | MAD million | {time.time() - t:.0f}s")
    print("Wrote outputs/ifrs9_report.md, outputs/reconciliation_pack_*.xlsx and outputs/figures/")
