# IRGS publication versions

The coordinated edition is **3.4.9 Pre-Alpha** (metadata channel: development).
The previous release version is **3.3.3**, as directed by the user. Earlier
3.4.0 commits and validation
records are development history and retain their actual tested identities.

## Pre-Alpha and Alpha classification

All 3.x.x editions are Pre-Alpha, including earlier development identities.
The requested functional Alpha target is now 5.0.0, not a version-only promotion.
TARGET_5_0.md carries forward the original A4 functional criteria; no intervening
4.0 publication is required.
[The shared Alpha plan](ALPHA_4_0_PLAN.md) and
[acceptance register](ALPHA_4_0_ACCEPTANCE.json) define the mandatory gates.
Publish the requested Alpha only after the coordinator qualifies the exact all-three set.
This instruction-only component update leaves VERSION.json at the coordinated edition.

Every push to unified `KingSav3ge/WorldWard/main` increases the coordinated version,
including guide-only or QA-only publications. The next edition is 3.5 (canonical metadata: 3.5.0). Only a substantial
milestone satisfying the functional Alpha gates may be assessed as the requested
5.0.0 Alpha candidate; record its evidence and limits.
Keep all four repository VERSION.json editions aligned for a coordinated release.
Independent Core compatibility, schemas, content and fixture versions retain
their own meanings. Never relabel historical tests as new execution.

Component development may continue on its own main at the current edition.
Only the coordinator assembles a compatible exact Engine/App/Catalog source set,
qualifies it and publishes unified main. Automatic QA retains reports outside
source until included in that versioned coordinator publication. It does not
push reports independently or advance versions on behalf of a product review.

## Current source and build retention

Unified main contains one canonical current installation. Do not keep obsolete
extracted installations or superseded generated release ZIPs in the source tree.
Replace the current distributable after the next edition passes qualification;
older generated packages need not be retained. Git history, original supplied
archives/citations, adopted canon and accurately dated qualification records are
source provenance, not duplicate installations. Preserve saves, credentials and
personal configuration. Core compatibility directory `IRGS_3_3` remains current.
