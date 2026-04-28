# ReleaseLens Report

**Run:** 849b3b36-1912-4fc4-aa76-3ae7cd57ead3
**PEPs:** PEP-658
**Target:** devpi-public/stub-package

## Executive summary

| Metric | Value |
|---|---|
| PEPs analysed | 1 |
| Features extracted | 4 |
| Verifications | 20 |
| Impact findings | 80 |

## Per-PEP matrix

### PEP-658 — Accepted


| Feature | warehouse | pip | uv | Consensus | First seen | PEP→impl gap |
|---|---|---|---|---|---|---|
| [pep-658.backward-compatibility](#pep-658-backward-compatibility) | [x] [found (0.90)](https://github.com/pypi/warehouse/commit/a11df5630ded0efff9806f62b5ea0b5966b69437) | [x] [23.3 (0.90)](https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1) | [x] [found (0.90)](https://github.com/astral-sh/uv/commit/6c316319134b82f582ff27abdb3d482ebdf2e06c) | implemented_everywhere | pip @ 23.3 | 0d |
| [pep-658.metadata-anchor-tag](#pep-658-metadata-anchor-tag) | [x] [found (0.95)](warehouse:warehouse/packaging/utils.py:102) | [x] [found (0.90)](https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1) | [ ] not found (0.50) | partial | pip | 0d |
| [pep-658.metadata-file-serving](#pep-658-metadata-file-serving) | [x] [found (0.90)](https://github.com/pypi/warehouse/commit/a11df5630ded0efff9806f62b5ea0b5966b69437) | [x] [found (0.90)](https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1) | [ ] not found (0.50) | partial | pip | 0d |
| [pep-658.metadata-hash-attribute](#pep-658-metadata-hash-attribute) | [x] [found (0.90)](https://github.com/pypi/warehouse/commit/a11df5630ded0efff9806f62b5ea0b5966b69437) | [x] [found (0.90)](https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1) | [x] [found (0.90)](https://github.com/astral-sh/uv/commit/6c316319134b82f582ff27abdb3d482ebdf2e06c) | implemented_everywhere | pip | 0d |


## Per feature

#### pep-658.backward-compatibility

Tools revert to downloading distributions if the `data-dist-info-metadata` attribute is absent.

**Spec claims:**
- (behavioural) If an anchor tag lacks the `data-dist-info-metadata` attribute, tools are expected to revert to downloading the distribution to inspect the metadata.
- (behavioural) Older tools not supporting the `data-dist-info-metadata` attribute are expected to ignore the attribute and maintain their current behaviour.


**Evidence:**

<details><summary>warehouse — found (conf 0.90, changelog)</summary>

Source: https://github.com/pypi/warehouse/commit/a11df5630ded0efff9806f62b5ea0b5966b69437, https://github.com/pypi/warehouse/commit/38ba926d2083de4d650340040ec247bb0a2c92bc

> Implement PEP 658 (#13649)
> 
> * add database model for storing calculated hashes of wheel METADATA files
> 
> * implement a helper for extracting METADATA file contents from wheels
> 
> * Store the digest of metadata file if exists, push to object storage
> 
> * don't store md5
> 
> * expose data-dist-info-metadata on simple api
> 
> * fail if unable to extract metadata file from wheels
> 
> * ensure metadata and pgp files are archived along with the actual distribution file
> 
> also resolves https://github.co

Notes: Commit explicitly references implementing PEP 658, but no version tag provided. Strong evidence of implementation.

</details>

<details><summary>pip — found 23.3 (conf 0.90, changelog)</summary>

Source: https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1, https://github.com/pypa/pip/commit/c12139de9b51da9947d3b36b4f0e2e0c8f467663, https://github.com/pypa/pip/commit/48152bb2e147f11a350b9b7c90057b15b6ba70ea, https://github.com/pypa/pip/commit/1d4674c38950fe01d138a57524799473a2341bb7, https://github.com/pypa/pip/commit/003c7ac56b4da80235d4a147fbcef84b6fbc8248

> Use data-dist-info-metadata (PEP 658) to decouple resolution from downloading (#11111)
> 
> Co-authored-by: Tzu-ping Chung <uranusjr@gmail.com>

Notes: Commit bad03ef explicitly mentions PEP 658 implementation for using data-dist-info-metadata attribute, likely first introduction.

</details>

<details><summary>uv — found (conf 0.90, changelog)</summary>

Source: https://github.com/astral-sh/uv/commit/6c316319134b82f582ff27abdb3d482ebdf2e06c, https://github.com/astral-sh/uv/commit/4e48d759c47f5d566285e4d2a7ab0411ab844c6c, https://github.com/astral-sh/uv/commit/b061db094d72ebd4fb6e52a1c80cea4f140a3b42, https://github.com/astral-sh/uv/commit/c80d5c6ffbe705a8b337f7e9df5c459f1c3b2860, https://github.com/astral-sh/uv/commit/fee344db6fec72d7d5aa9eef03a7d76cb48d4c37

> Fetch from `data-dist-info-metadata` when available (#37)
> 
> As specified in https://peps.python.org/pep-0658/#specification.

Notes: Commit #37 explicitly references PEP 658 and implements fetching from data-dist-info-metadata, but release version not specified.

</details>

**Verification:** earliest tool pip, temporal gap 0d — STUB
**Impact (devpi-public/stub-package):** effort S, confidence 0.50
- Current: not_present
- Delta: STUB delta


#### pep-658.metadata-anchor-tag

Adds a `data-dist-info-metadata` attribute to anchor tags in simple repository APIs to indicate the presence of a separately fetchable `METADATA` file.

**Spec claims:**
- (structural) Anchor tags pointing to a distribution MAY have a `data-dist-info-metadata` attribute.
- (metadata) The presence of the `data-dist-info-metadata` attribute indicates the distribution MUST contain a Core Metadata file.


**Evidence:**

<details><summary>warehouse — found (conf 0.95, static)</summary>

Source: warehouse:warehouse/packaging/utils.py:102, warehouse:tests/unit/api/test_simple.py:293, warehouse:tests/unit/api/test_simple.py:346, warehouse:tests/unit/api/test_simple.py:436, warehouse:tests/unit/api/test_simple.py:642

>                 "data-dist-info-metadata": (

Notes: Direct use of 'data-dist-info-metadata' in code (utils.py) suggests implementation. Tests also reference the attribute.

</details>

<details><summary>pip — found (conf 0.90, changelog)</summary>

Source: https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1, https://github.com/pypa/pip/commit/c12139de9b51da9947d3b36b4f0e2e0c8f467663, https://github.com/pypa/pip/commit/48152bb2e147f11a350b9b7c90057b15b6ba70ea, https://github.com/pypa/pip/commit/1d4674c38950fe01d138a57524799473a2341bb7, https://github.com/pypa/pip/commit/003c7ac56b4da80235d4a147fbcef84b6fbc8248

> Use data-dist-info-metadata (PEP 658) to decouple resolution from downloading (#11111)
> 
> Co-authored-by: Tzu-ping Chung <uranusjr@gmail.com>

Notes: Commit explicitly uses data-dist-info-metadata attribute for PEP 658, but release version not stated.

</details>

<details><summary>uv — not found (conf 0.50, changelog)</summary>

Source: https://github.com/astral-sh/uv/commit/4e48d759c47f5d566285e4d2a7ab0411ab844c6c, https://github.com/astral-sh/uv/commit/b061db094d72ebd4fb6e52a1c80cea4f140a3b42, https://github.com/astral-sh/uv/commit/c80d5c6ffbe705a8b337f7e9df5c459f1c3b2860

> Add zstandard support for wheels (#15645)
> 
> ## Summary
> 
> This PR allows pyx to send down hashes for zstandard-compressed
> tarballs. If the hash is present, then the file is assumed to be present
> at `${wheel_url}.tar.zst`, similar in design to PEP 658
> `${wheel_metadata}.metadata` files. The intent here is that the index
> must include the wheel (to support all clients and support
> random-access), but can optionally include a zstandard-compressed
> version alongside it.

Notes: Commit 4e48d75 references PEP 658 design but does not confirm implementation of metadata anchor tags. No explicit version attribution.

</details>

**Verification:** earliest tool pip, temporal gap 0d — STUB
**Impact (devpi-public/stub-package):** effort S, confidence 0.50
- Current: not_present
- Delta: STUB delta


#### pep-658.metadata-file-serving

Repositories must serve the Core Metadata file with a `.metadata` suffix appended to the distribution filename.

**Spec claims:**
- (protocol) If the `data-dist-info-metadata` attribute is present, the repository MUST serve the Core Metadata file with a `.metadata` suffix.
- (protocol) The Core Metadata file must be served at a URL derived from the distribution's filename with `.metadata` appended.


**Evidence:**

<details><summary>warehouse — found (conf 0.90, changelog)</summary>

Source: https://github.com/pypi/warehouse/commit/a11df5630ded0efff9806f62b5ea0b5966b69437, https://github.com/pypi/warehouse/commit/38ba926d2083de4d650340040ec247bb0a2c92bc

> Implement PEP 658 (#13649)
> 
> * add database model for storing calculated hashes of wheel METADATA files
> 
> * implement a helper for extracting METADATA file contents from wheels
> 
> * Store the digest of metadata file if exists, push to object storage
> 
> * don't store md5
> 
> * expose data-dist-info-metadata on simple api
> 
> * fail if unable to extract metadata file from wheels
> 
> * ensure metadata and pgp files are archived along with the actual distribution file
> 
> also resolves https://github.co

Notes: Commit explicitly references implementing PEP 658, but no release version tagged.

</details>

<details><summary>pip — found (conf 0.90, changelog)</summary>

Source: https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1, https://github.com/pypa/pip/commit/c12139de9b51da9947d3b36b4f0e2e0c8f467663, https://github.com/pypa/pip/commit/48152bb2e147f11a350b9b7c90057b15b6ba70ea, https://github.com/pypa/pip/commit/1d4674c38950fe01d138a57524799473a2341bb7, https://github.com/pypa/pip/commit/003c7ac56b4da80235d4a147fbcef84b6fbc8248

> Use data-dist-info-metadata (PEP 658) to decouple resolution from downloading (#11111)
> 
> Co-authored-by: Tzu-ping Chung <uranusjr@gmail.com>

Notes: Commit bad03ef explicitly mentions using data-dist-info-metadata (PEP 658), indicating feature implementation. No release notes explicitly attribute to a version.

</details>

<details><summary>uv — not found (conf 0.50, changelog)</summary>

Source: https://github.com/astral-sh/uv/commit/4e48d759c47f5d566285e4d2a7ab0411ab844c6c, https://github.com/astral-sh/uv/commit/b061db094d72ebd4fb6e52a1c80cea4f140a3b42, https://github.com/astral-sh/uv/commit/c80d5c6ffbe705a8b337f7e9df5c459f1c3b2860

> Add zstandard support for wheels (#15645)
> 
> ## Summary
> 
> This PR allows pyx to send down hashes for zstandard-compressed
> tarballs. If the hash is present, then the file is assumed to be present
> at `${wheel_url}.tar.zst`, similar in design to PEP 658
> `${wheel_metadata}.metadata` files. The intent here is that the index
> must include the wheel (to support all clients and support
> random-access), but can optionally include a zstandard-compressed
> version alongside it.

Notes: Commit 0 references PEP 658 design but does not attribute a release. No explicit version tied to the feature.

</details>

**Verification:** earliest tool pip, temporal gap 0d — STUB
**Impact (devpi-public/stub-package):** effort S, confidence 0.50
- Current: not_present
- Delta: STUB delta


#### pep-658.metadata-hash-attribute

The `data-dist-info-metadata` attribute may include a hash of the Core Metadata file for client-side verification.

**Spec claims:**
- (structural) The repository SHOULD provide the hash of the Core Metadata file in the `data-dist-info-metadata` attribute using the syntax `<hashname>=<hashvalue>`.
- (structural) The repository MAY use `true` as the attribute's value if a hash is unavailable.


**Evidence:**

<details><summary>warehouse — found (conf 0.90, changelog)</summary>

Source: https://github.com/pypi/warehouse/commit/a11df5630ded0efff9806f62b5ea0b5966b69437, https://github.com/pypi/warehouse/commit/38ba926d2083de4d650340040ec247bb0a2c92bc

> Implement PEP 658 (#13649)
> 
> * add database model for storing calculated hashes of wheel METADATA files
> 
> * implement a helper for extracting METADATA file contents from wheels
> 
> * Store the digest of metadata file if exists, push to object storage
> 
> * don't store md5
> 
> * expose data-dist-info-metadata on simple api
> 
> * fail if unable to extract metadata file from wheels
> 
> * ensure metadata and pgp files are archived along with the actual distribution file
> 
> also resolves https://github.co

Notes: Commit explicitly implements PEP 658 with storage of metadata hashes, but no release version tagged.

</details>

<details><summary>pip — found (conf 0.90, changelog)</summary>

Source: https://github.com/pypa/pip/commit/bad03ef931d9b3ff4f9e75f35f9c41f45839e2a1, https://github.com/pypa/pip/commit/c12139de9b51da9947d3b36b4f0e2e0c8f467663, https://github.com/pypa/pip/commit/48152bb2e147f11a350b9b7c90057b15b6ba70ea, https://github.com/pypa/pip/commit/1d4674c38950fe01d138a57524799473a2341bb7

> Use data-dist-info-metadata (PEP 658) to decouple resolution from downloading (#11111)
> 
> Co-authored-by: Tzu-ping Chung <uranusjr@gmail.com>

Notes: Commit #3 explicitly mentions using PEP 658 for data-dist-info-metadata, indicating implementation. No release tag given.

</details>

<details><summary>uv — found (conf 0.90, changelog)</summary>

Source: https://github.com/astral-sh/uv/commit/6c316319134b82f582ff27abdb3d482ebdf2e06c, https://github.com/astral-sh/uv/commit/4e48d759c47f5d566285e4d2a7ab0411ab844c6c, https://github.com/astral-sh/uv/commit/b061db094d72ebd4fb6e52a1c80cea4f140a3b42, https://github.com/astral-sh/uv/commit/c80d5c6ffbe705a8b337f7e9df5c459f1c3b2860, https://github.com/astral-sh/uv/commit/fee344db6fec72d7d5aa9eef03a7d76cb48d4c37

> Fetch from `data-dist-info-metadata` when available (#37)
> 
> As specified in https://peps.python.org/pep-0658/#specification.

Notes: Commit #37 explicitly references PEP 658 and implements fetching from data-dist-info-metadata per its specification, but does not specify a version.

</details>

**Verification:** earliest tool pip, temporal gap 0d — STUB
**Impact (devpi-public/stub-package):** effort S, confidence 0.50
- Current: not_present
- Delta: STUB delta


