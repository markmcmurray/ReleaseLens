# pmwatch — Curated PEP Corpus

**Purpose.** Eval harness corpus and demo material for pmwatch, a multi-agent pipeline reconciling packaging PEPs against implementations across PyPI Warehouse, pip, and uv.

**Scope.** Packaging-domain PEPs only (index protocols, distribution formats, metadata, dependency resolution, build backends, attestations). All entries have an observable interaction surface (server-side, client-side, or wire protocol) and findable implementation commits across the three target sites.

**Hero PEP.** PEP 658. Considered PEP 691 and PEP 740 as challengers; 658 retained because the server-ahead-of-client gap is sharpest, the verifiable claim (hash equivalence between `.metadata` and wheel-extracted `METADATA`) is clean, and the performance narrative is well-known.

---

## The List

### 1. PEP 440 — Version Identification and Dependency Specification (2014)

- **Surface.** Client-side parsing across all three sites; foundational.
- **Why interesting.** Implementation *drift* rather than temporal gap. `packaging.specifiers` is canonical, but Warehouse, pip, and uv each diverge on edge cases (pre-release handling, local versions, normalization). Generates "claims that look identical but diverge in practice" material.
- **Commit-finding confidence.** High.

### 2. PEP 503 — Simple Repository API (2015)

- **Surface.** Wire protocol all three sites speak.
- **Why interesting.** Baseline against which all later index-protocol gaps are measured. Limited temporal-gap drama on its own — it codified existing practice — but indispensable as foundation. Candidate for ejection if the corpus needs trimming further.
- **Commit-finding confidence.** High, but mostly historical.

### 3. PEP 625 — Filename of a Source Distribution (2019)

- **Surface.** Warehouse-side enforcement, build-backend production, client parsing.
- **Why interesting.** Server enforcement only switched on recently — Warehouse began rejecting non-conforming sdist filenames years after acceptance. Strong "PEP 2019, enforced 2024" gap story.
- **Commit-finding confidence.** High on Warehouse, medium on pip/uv.

### 4. PEP 643 — Metadata for Source Distributions / Core Metadata 2.2 (2020)

- **Surface.** Backends produce static metadata in sdists; Warehouse parses on upload; pip/uv read for resolution.
- **Why interesting.** Classic partial-implementation story — a meaningful fraction of sdists in the wild still don't ship static metadata. Useful for "what fraction of sdists actually comply" telemetry.
- **Commit-finding confidence.** Medium; surface is diffuse.

### 5. PEP 658 — Serve Distribution Metadata in the Simple Repository API (2021) — **HERO**

- **Surface.** Index-protocol; all three sites.
- **Why interesting.** Canonical server-ahead-of-client gap. Warehouse shipped `.metadata` exposure in 2022; pip didn't use it by default for several months; uv supported it from inception. Underlies a well-known performance claim. Verifiable claim is clean: hash the served `.metadata` and compare against `METADATA` extracted from the wheel.
- **Commit-finding confidence.** Very high — Warehouse PR, pip PR, and uv references all easily findable.

### 6. PEP 691 — JSON-based Simple API for Package Indexes (2022)

- **Surface.** Pure wire-protocol; content negotiation between server and client (observable in `Accept` headers).
- **Why interesting.** Relatively fast adoption across all three sites. Functions as "this is what fast adoption looks like" contrast against the slower-moving 658 and 740. Was a serious hero candidate; lost out because the gap is smaller and the headline performance story doesn't attach as cleanly.
- **Commit-finding confidence.** Very high.

### 7. PEP 700 — Additional Fields for the Simple API for Package Indexes (2023)

- **Surface.** Extends 691; adds `size`, `upload-time`, `yanked` fields. Warehouse exposes; clients selectively consume.
- **Why interesting.** pip and uv use different subsets of the new fields. Good "partial implementation, by choice" material distinct from 658-style "partial because not yet caught up."
- **Commit-finding confidence.** High on Warehouse, medium on clients.

### 8. PEP 708 — Extending the Repository API to Mitigate Dependency Confusion Attacks (2023)

- **Surface.** Server marks tracks/alternate-locations; clients enforce.
- **Why interesting.** Security-protocol gap. Server-side mechanism specified; client-side enforcement uneven. Strong "claim only holds when both sides cooperate" material — relevant to the supply-chain framing.
- **Commit-finding confidence.** Medium.

### 9. PEP 740 — Index Support for Digital Attestations (2023)

- **Surface.** Warehouse stores and exposes provenance; clients verify.
- **Why interesting.** Freshest server-ahead-of-client gap in the ecosystem. Warehouse + sigstore pipeline shipped; client verification is patchy. Generates "what fraction of recent uploads have currently-unverified attestations" telemetry — lands well for the Cloudsmith side of the story. Was a hero challenger; held back because the verifiable claim is harder to demo concisely.
- **Commit-finding confidence.** High on Warehouse, lower on clients.

### 10. PEP 639 — Improving License Clarity with Better Package Metadata (2024)

- **Surface.** SPDX expressions in core metadata; producers (build backends), display (Warehouse), consumers (pip, uv) all touch.
- **Why interesting.** Drafted ~2019, accepted late 2024 — half-decade lag on the *spec itself* before anyone could implement, with the implementation tail still rolling. Distinct gap shape from server-ahead PEPs: this one was stuck in committee, not in code.
- **Commit-finding confidence.** Medium on Warehouse and pip; lower on uv.

---

## Coverage Summary

| Profile | PEPs |
|---|---|
| Hero | 658 |
| Headline server-ahead-of-client gaps | 658, 740, 625 |
| Foundational baselines | 440, 503 |
| Fast-adoption contrast | 691 |
| Partial-implementation stories | 643, 700, 708, 639 |

**Temporal range.** 2014–2024.
**Surface mix.** Wire-protocol heavy (503, 658, 691, 700, 708, 740), two metadata-format PEPs (643, 639), one version-spec PEP (440), one filename-format PEP (625).
**Three-site participation.** All ten genuinely involve Warehouse, pip, and uv.

---

## Considered and Rejected

- **PEP 660 (Editable installs for pyproject.toml based builds, 2021).** Warehouse isn't a meaningful participant — accepts wheel uploads but editable installs are local-only. Fails the three-site requirement.
- **PEP 770 (SBOM in package metadata, 2024).** Almost no implementation yet; likely evidence-poor for commit archaeology in early 2026. Strong thematic fit; revisit when implementations land.

## Trim and Swap Notes

- **First eject if culling to 8.** PEP 503 (foundational but story-poor) or PEP 643 (thematically overlaps 625).
- **First swap-in when revisiting.** PEP 770, once SBOM-related commits exist in the three target repos.
