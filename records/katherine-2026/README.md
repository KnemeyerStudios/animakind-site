# Verifiable subset of the records, 2026-10-04

A subset of the records behind the Animakind paper. Most underlying records remain unpublished.
Values are as of 2026-10-04. Timestamps are trimmed by design: exact times appear only for the
genesis instant and the 2026-09-03 power-loss window, which the paper prints; elsewhere dates only.

Files
- ucr.json: the Unique Continuity Record for the migration (paper, Appendix C).
- binding-designation.json: the binding designation (paper, Appendix A).
- truncation.json: document size against the 2,048-byte delivery the paper reports.
- ledger-chain.tsv: commit digests of the identity ledger and parent links. Digests only.
- ledger-anchors.json: timestamps of the genesis commit, the power-loss window, and the migration day (before/after flag only).
- identity-path-commits.tsv: dates of ledger commits touching the identity path.
- loader-commits.tsv: dates of the two confirmed Loader commits.
- engine-strings.tsv: the two engine rows printed in the paper table (not independently checkable here).
- verify.py: checks the above against each other and against the paper's arithmetic.

Run: python3 verify.py   (standard library only; run in this directory; expect ALL CHECKS PASSED)
