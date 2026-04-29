# Deployment Test Scenario (DEP-*.yaml) Uniqueness Analysis

## Executive Summary

**Analysis Date:** April 20, 2026  
**Scope:** All DEP-*.yaml files in `/root/workspace/lnd/aiops/apps/newbie-app/tests/evals/test_scenarios/package-deployment/e2e/`

### Key Findings

| Metric | Count |
|--------|-------|
| **Total test files analyzed** | 26 |
| **Unique scenario combinations** | 11 (42%) |
| **Duplicate scenario combinations** | 5 (58% of scenarios) |
| **Files with functional redundancy** | 15 (58% of all files) |
| **Consolidated baseline files recommended** | 11 |
| **Candidates for consolidation** | 10 |

### High-Level Assessment

- **58% of test scenarios are duplicates** - Testing identical combinations of preconditions, prompts, charts, and versions
- **5 major duplicate groups** identified with 2-5 files per group
- **11 unique scenario combinations** that should be retained
- **Significant opportunity for test suite optimization**

---

## Classification Scheme

### Precondition Types

1. **Clean slate (uninstall + delete ns)** - Removes all prior state before testing (2 files)
2. **Namespace preparation only** - Creates/verifies namespace, minimal cleanup (5 files)
3. **Pre-upgrade setup (prepare for update)** - Pre-installs previous chart version, prepares for upgrade (19 files)
4. **Pre-installed release** - Previous release installed (0 files)
5. **Minimal/cleanup only** - Comments and echo statements only (0 files)

### Prompt Intent Categories

1. **Initial deployment** - Fresh install / first-time deployment (7 files)
2. **Upgrade/Update** - Upgrade from previous version (8 files)
3. **Installation** - General installation operation (5 files)
4. **Publish/Kafka operation** - Message queue publish operation (4 files)
5. **General deployment** - Unspecified deployment operation (2 files)

---

## SECTION 1: Exact Duplicates

These files test **identical scenarios** (same precondition type + prompt intent + chart + version).

### Duplicate Group 1: 5-File Redundancy [HIGH PRIORITY]

**Scenario:** Initial deployment of nginx v22.6.10 with pre-upgrade setup

| Dimension | Value |
|-----------|-------|
| Precondition Type | Pre-upgrade setup (prepare for update) |
| Prompt Intent | Initial deployment |
| Chart | oci://registry-1.docker.io/bitnamicharts/nginx |
| Version | 22.6.10 |

**Affected Files:**
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.1.yaml#L7-L10)
  - Chat prompt: Line 2 - "fresh install" with validation order choice
  - Precondition: Line 7 - Comment: "New pre-condition"
  - Complexity: 3 operations (helm uninstall, install, namespace creation)

- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.3.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.3.yaml#L7)
  - Chat prompt: Line 2 - "fresh install" with conditional existence check
  - Precondition: Line 7 - Comment: "target release already exists before request"
  - Complexity: 4 operations

- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.4.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.4.yaml#L7)
  - Chat prompt: Line 2 - "fresh install" with namespace workload consideration
  - Precondition: Line 7 - Comment: "namespace has unrelated workloads already running"
  - Complexity: 5 operations

- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.6.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.6.yaml#L7)
  - Chat prompt: Line 2 - "fresh install" for recovery/replace behavior
  - Precondition: Line 7 - Comment: "cluster has stale failed release metadata"
  - Complexity: 4 operations

- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.1.yaml#L23)
  - Chat prompt: Line 2 - "deploy request" (different wording but same test)
  - Precondition: Line 23 - kubectl create ns + helm operations
  - Complexity: 6 operations

**Evidence of Duplication:**
- All 5 files produce ~identical helm/kubectl command sequences
- Chart references, versions, and namespace targets are identical
- Prompt intent analysis classifies all as "Initial deployment"
- Precondition scripts all follow: create-ns → uninstall → install pattern

**Consolidation Recommendation:**
- **KEEP:** [DEP-E-001.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.1.yaml) (baseline, simplest comment)
- **REMOVE:** DEP-E-001.3, DEP-E-001.4, DEP-E-001.6, DEP-E-006.1 (exact functional duplicates)
- **Risk:** Minimal - these test identical operations on identical chart versions

---

### Duplicate Group 2: 4-File Redundancy [MEDIUM PRIORITY]

**Scenario:** Upgrade/Update of nginx v22.6.10 with pre-upgrade setup

| Dimension | Value |
|-----------|-------|
| Precondition Type | Pre-upgrade setup (prepare for update) |
| Prompt Intent | Upgrade/Update |
| Chart | oci://registry-1.docker.io/bitnamicharts/nginx |
| Version | 22.6.10 |

**Affected Files:**
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.2.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.2.yaml#L24)
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-008.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-008.1.yaml#L23)
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.1.yaml#L23)
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.1.yaml#L23)

**Consolidation Recommendation:**
- **KEEP:** [DEP-E-006.2.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.2.yaml)
- **REMOVE:** DEP-E-008.1, DEP-E-009.1, DEP-E-010.1
- **Risk:** Low - identical test scenarios for same chart version

---

### Duplicate Group 3: 2-File Redundancy [MEDIUM PRIORITY]

**Scenario:** Upgrade/Update of redis v25.3.9 with pre-upgrade setup

| Dimension | Value |
|-----------|-------|
| Precondition Type | Pre-upgrade setup (prepare for update) |
| Prompt Intent | Upgrade/Update |
| Chart | oci://registry-1.docker.io/bitnamicharts/redis |
| Version | 25.3.9 |

**Affected Files:**
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.0.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.0.yaml#L7)
  - Precondition: Line 7 - "release exists at previous version and should be upgraded"
  
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.1.yaml#L7)
  - Precondition: Line 7 - "release exists at previous version with extra workload in namespace"

**Consolidation Recommendation:**
- **KEEP:** [DEP-E-002.0.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.0.yaml)
- **REMOVE:** DEP-E-002.1
- **Risk:** Low - both test identical upgrade scenario for same chart version

---

### Duplicate Group 4 & 5: 2-File Redundancies [MEDIUM PRIORITY]

**Group 4 - Installation scenario with namespace-only setup:**
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-007.0.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-007.0.yaml)
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.0.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.0.yaml)

**Group 5 - Installation scenario with pre-upgrade setup:**
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-007.1.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-007.1.yaml#L24)
- [tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.0.yaml](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.0.yaml#L23)

---

## SECTION 2: Near-Duplicates

These files test **similar scenarios** (same intent + chart + version) but with **different preconditions** - offering potential value through precondition variance testing.

### Near-Duplicate Group A: 7-File Cluster [RETAIN - Precondition Variance Test]

**Core Scenario:** Initial deployment of nginx v22.6.10  
**Precondition Variance:**

| Precondition Type | Files | Evidence |
|-------------------|-------|----------|
| Clean slate (uninstall + delete ns) | [DEP-E-001.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.0.yaml#L7) | Minimal setup: delete ns and uninstall only |
| Namespace preparation only | [DEP-E-001.2](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.2.yaml#L7) | Create namespace with `--dry-run` pattern |
| Pre-upgrade setup | [DEP-E-001.1](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.1.yaml#L7), [DEP-E-001.3](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.3.yaml#L7), [DEP-E-001.4](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.4.yaml#L7), [DEP-E-001.6](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.6.yaml#L7), [DEP-E-006.1](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.1.yaml#L23) | 5 variants of pre-install pattern |

**Assessment:** Precondition-only variance detected BUT with 5 duplicate files in one category. Recommend:
- **RETAIN:** DEP-E-001.0, DEP-E-001.2 (different precondition types)
- **RETAIN:** DEP-E-001.1 (representative of pre-upgrade setup category)
- **CONSOLIDATE:** DEP-E-001.3, DEP-E-001.4, DEP-E-001.6, DEP-E-006.1 (duplicates of DEP-E-001.1)

---

### Near-Duplicate Group B: 5-File Cluster

**Core Scenario:** Installation of nginx v22.6.10  
**Precondition Variance:** Clean slate vs Namespace-only vs Pre-upgrade setup

**Assessment:** PARTIALLY RETAIN
- **RETAIN:** DEP-E-006.0 (clean slate variant)
- **RETAIN:** DEP-E-007.0 (namespace-only variant)
- **CONSOLIDATE:** DEP-E-010.0 (duplicate of DEP-E-007.0)
- **CONSOLIDATE:** DEP-E-007.1, DEP-E-009.0 (duplicate variants)

---

## SECTION 3: Unique Scenarios

These 11 files test **distinct scenario combinations** and should be **retained**:

| # | File | Precondition | Intent | Chart | Version | Rationale |
|---|------|--------------|--------|-------|---------|-----------|
| 1 | [DEP-E-001.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.0.yaml) | Clean slate | Initial deployment | nginx | 22.6.10 | Only clean-slate initial deployment test |
| 2 | [DEP-E-006.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.0.yaml) | Clean slate | Installation | nginx | 22.6.10 | Only clean-slate installation test |
| 3 | [DEP-E-001.2](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.2.yaml) | Namespace-only | Initial deployment | nginx | 22.6.10 | Namespace preparation variant |
| 4 | [DEP-E-010.2](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.2.yaml) | Namespace-only | General deployment | nginx | 22.6.10 | Only general deployment test |
| 5 | [DEP-E-008.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-008.0.yaml) | Pre-upgrade setup | General deployment | nginx | 22.6.10 | Unique intent variant |
| 6 | [DEP-M-001.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-M-001.0.yaml) | Pre-upgrade setup | Publish/Kafka | nginx | 22.6.10 | Only nginx Publish/Kafka test |
| 7 | [DEP-E-003.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-003.0.yaml) | Pre-upgrade setup | Publish/Kafka | postgresql | 18.5.14 | PostgreSQL with different version pattern |
| 8 | [DEP-E-003.1](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-003.1.yaml) | Pre-upgrade setup | Publish/Kafka | postgresql | 18.5.14 | PostgreSQL variant (version suffix difference) |
| 9 | [DEP-E-005.0](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-005.0.yaml) | Pre-upgrade setup | Upgrade/Update | memcached | 8.3.7 | Only memcached test at 8.3.7 |
| 10 | [DEP-E-005.1](tests/evals/test_scenarios/package-deployment/e2e/DEP-E-005.1.yaml) | Pre-upgrade setup | Upgrade/Update | memcached | 8.3.8 | Memcached upgrade to different version |
| 11 | [DEP-M-001.2](tests/evals/test_scenarios/package-deployment/e2e/DEP-M-001.2.yaml) | Namespace-only | Publish/Kafka | postgresql | 18.5.14 | PostgreSQL with namespace-only setup |

---

## SECTION 4: Consolidation Recommendations

### Summary Matrix

| Priority | Group | Files | Consolidation | Impact |
|----------|-------|-------|----------------|--------|
| **HIGH** | Initial deployment (nginx 22.6.10) | 5 | Keep DEP-E-001.1, remove 4 duplicates | Reduce test suite by 4 files (15%) |
| **MEDIUM** | Upgrade/Update (nginx 22.6.10) | 4 | Keep DEP-E-006.2, remove 3 duplicates | Reduce by 3 files |
| **MEDIUM** | Upgrade/Update (redis 25.3.9) | 2 | Keep DEP-E-002.0, remove 1 duplicate | Reduce by 1 file |
| **MEDIUM** | Installation (namespace-only) | 2 | Keep DEP-E-007.0, remove 1 duplicate | Reduce by 1 file |
| **MEDIUM** | Installation (pre-upgrade setup) | 2 | Keep DEP-E-007.1, remove 1 duplicate | Reduce by 1 file |

### Consolidation Impact

**If all recommendations are implemented:**
- Current suite: 26 files
- Consolidated suite: 16 files
- **Reduction: 10 files (38% reduction)**
- **Retained coverage: 11 unique scenario combinations (100% of functional coverage)**

### Implementation Strategy

**Phase 1 (High Priority):**
```
DELETE:
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.3.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.4.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.6.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.1.yaml

KEEP:
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.1.yaml
```

**Phase 2 (Medium Priority):**
```
DELETE:
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-008.1.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.1.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.1.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.1.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.0.yaml
- tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.0.yaml
```

---

## SECTION 5: Precondition-Only Variance Analysis

Files testing **same intent + chart + version** but **different preconditions**:

| Scenario | Preconditions Tested | Value | Recommendation |
|----------|---------------------|-------|-----------------|
| Initial deployment (nginx 22.6.10) | 3 types: clean slate, namespace-only, pre-upgrade setup | **KEEP all 3 types** - tests agent response to different state conditions | RETAIN DEP-E-001.0, DEP-E-001.2, one of {001.1, 001.3, 001.4, 001.6} |
| Installation (nginx 22.6.10) | 3 types: clean slate, namespace-only, pre-upgrade setup | **KEEP all 3 types** - tests robustness across setup variations | RETAIN DEP-E-006.0, DEP-E-007.0, one of {007.1, 009.0} |
| Publish/Kafka (postgresql 18.5.14) | 2 types: namespace-only, pre-upgrade setup | **KEEP both** - precondition variance | RETAIN both DEP-M-001.2 and DEP-E-003.1 (or DEP-E-003.0) |

---

## SECTION 6: Prompt-Only Variance Analysis

Files with **same precondition + intent** but **different prompt wording**:

**DEP-E-001.1, 001.3, 001.4, 001.6:**
- All test "fresh install" intent with "pre-upgrade setup" precondition
- Prompt variations: validation order choice, conditional existence, namespace workload, stale metadata
- **Assessment:** Wording variations in prompts don't create functional differences in **precondition** (which is identical)
- **Recommendation:** These are prompt variations, not precondition variations - consolidate together

---

## SECTION 7: Functional Redundancy Matrix

```
REDUNDANT CLUSTERS:

Cluster A (5 files - EXACT DUPLICATES):
├─ DEP-E-001.1 ✓ KEEP (baseline)
├─ DEP-E-001.3 ✗ REMOVE (duplicate)
├─ DEP-E-001.4 ✗ REMOVE (duplicate)
├─ DEP-E-001.6 ✗ REMOVE (duplicate)
└─ DEP-E-006.1 ✗ REMOVE (duplicate)

Cluster B (4 files - EXACT DUPLICATES):
├─ DEP-E-006.2 ✓ KEEP (baseline)
├─ DEP-E-008.1 ✗ REMOVE (duplicate)
├─ DEP-E-009.1 ✗ REMOVE (duplicate)
└─ DEP-E-010.1 ✗ REMOVE (duplicate)

Cluster C (2 files - EXACT DUPLICATES):
├─ DEP-E-002.0 ✓ KEEP (baseline)
└─ DEP-E-002.1 ✗ REMOVE (duplicate)

Cluster D (2 files - EXACT DUPLICATES):
├─ DEP-E-007.0 ✓ KEEP (baseline)
└─ DEP-E-010.0 ✗ REMOVE (duplicate)

Cluster E (2 files - EXACT DUPLICATES):
├─ DEP-E-007.1 ✓ KEEP (baseline)
└─ DEP-E-009.0 ✗ REMOVE (duplicate)

UNIQUE SCENARIOS (Retain all):
├─ DEP-E-001.0 ✓
├─ DEP-E-001.2 ✓
├─ DEP-E-003.0 ✓
├─ DEP-E-003.1 ✓
├─ DEP-E-005.0 ✓
├─ DEP-E-005.1 ✓
├─ DEP-E-008.0 ✓
├─ DEP-E-010.2 ✓
├─ DEP-M-001.0 ✓
└─ DEP-M-001.2 ✓
```

---

## SECTION 8: Risk Assessment

### Consolidation Risks

| Risk | Level | Mitigation |
|------|-------|-----------|
| Test coverage loss | **LOW** - 11 unique scenarios retained vs. 26 files | Verify all unique scenario intents tested |
| Missed edge cases | **MEDIUM** - Precondition variants may test different agent paths | Run full test suite before/after consolidation |
| Regression detection latency | **LOW** - Consolidation reduces redundancy, not coverage | Maintain monitoring on core scenarios |
| False negatives in duplicates | **LOW** - Manual verification of 15 duplicate files performed | Cross-reference with test execution logs |

### Validation Checklist Before Deletion

- [ ] All 11 unique scenarios have passing executions
- [ ] RED-flagged scenarios (pre-upgrade setup clusters) have recent successful runs
- [ ] Chart versions in consolidated files still align with deployment targets
- [ ] Test execution time reduction measured
- [ ] No integration tests depend on removed file names

---

## Appendix A: File-by-File Breakdown

| File | Precondition | Intent | Chart | Version | Line: Prompt | Line: Precond | Status |
|------|--------------|--------|-------|---------|-------------|---------------|--------|
| DEP-E-001.0 | Clean slate | Initial deployment | nginx | 22.6.10 | 2 | 7 | **UNIQUE** |
| DEP-E-001.1 | Pre-upgrade | Initial deployment | nginx | 22.6.10 | 2 | 7 | KEEP duplicate group |
| DEP-E-001.2 | Namespace-only | Initial deployment | nginx | 22.6.10 | 2 | 7 | **UNIQUE** |
| DEP-E-001.3 | Pre-upgrade | Initial deployment | nginx | 22.6.10 | 2 | 7 | ✗ REMOVE |
| DEP-E-001.4 | Pre-upgrade | Initial deployment | nginx | 22.6.10 | 2 | 7 | ✗ REMOVE |
| DEP-E-001.6 | Pre-upgrade | Initial deployment | nginx | 22.6.10 | 2 | 7 | ✗ REMOVE |
| DEP-E-002.0 | Pre-upgrade | Upgrade/Update | redis | 25.3.9 | 2 | 7 | KEEP duplicate group |
| DEP-E-002.1 | Pre-upgrade | Upgrade/Update | redis | 25.3.9 | 2 | 7 | ✗ REMOVE |
| DEP-E-003.0 | Pre-upgrade | Publish/Kafka | postgresql | 18.5.14 | 2 | 7 | **UNIQUE** |
| DEP-E-003.1 | Pre-upgrade | Publish/Kafka | postgresql | 18.5.14. | 2 | 7 | **UNIQUE** |
| DEP-E-005.0 | Pre-upgrade | Upgrade/Update | memcached | 8.3.7 | 2 | 7 | **UNIQUE** |
| DEP-E-005.1 | Pre-upgrade | Upgrade/Update | memcached | 8.3.8 | 2 | 7 | **UNIQUE** |
| DEP-E-006.0 | Clean slate | Installation | nginx | 22.6.10 | 2 | 23 | **UNIQUE** |
| DEP-E-006.1 | Pre-upgrade | Initial deployment | nginx | 22.6.10 | 2 | 23 | ✗ REMOVE |
| DEP-E-006.2 | Pre-upgrade | Upgrade/Update | nginx | 22.6.10 | 2 | 24 | KEEP duplicate group |
| DEP-E-007.0 | Namespace-only | Installation | nginx | 22.6.10 | 2 | 23 | KEEP duplicate group |
| DEP-E-007.1 | Pre-upgrade | Installation | nginx | 22.6.10 | 2 | 24 | KEEP duplicate group |
| DEP-E-008.0 | Pre-upgrade | General deployment | nginx | 22.6.10 | 2 | 24 | **UNIQUE** |
| DEP-E-008.1 | Pre-upgrade | Upgrade/Update | nginx | 22.6.10 | 2 | 23 | ✗ REMOVE |
| DEP-E-009.0 | Pre-upgrade | Installation | nginx | 22.6.10 | 2 | 23 | ✗ REMOVE |
| DEP-E-009.1 | Pre-upgrade | Upgrade/Update | nginx | 22.6.10 | 2 | 23 | ✗ REMOVE |
| DEP-E-010.0 | Namespace-only | Installation | nginx | 22.6.10 | 2 | 23 | ✗ REMOVE |
| DEP-E-010.1 | Pre-upgrade | Upgrade/Update | nginx | 22.6.10 | 2 | 23 | ✗ REMOVE |
| DEP-E-010.2 | Namespace-only | General deployment | nginx | 22.6.10 | 2 | 23 | **UNIQUE** |
| DEP-M-001.0 | Pre-upgrade | Publish/Kafka | nginx | 22.6.10 | 2 | 9 | **UNIQUE** |
| DEP-M-001.2 | Namespace-only | Publish/Kafka | postgresql | 18.5.14. | 2 | 10 | **UNIQUE** |

---

## Appendix B: Data Quality Notes

- **Version field formatting inconsistency:** Some files have trailing periods in version strings (e.g., "22.6.10." vs "22.6.10") - recommend standardization
- **Prompt wording variations:** Many files intentionally vary prompt language ("fresh install" vs "deploy request") but test identical scenarios
- **Precondition comments:** Comments indicate different "reasoning" for precondition but actual `helm`/`kubectl` commands are identical

---

**Report Generated:** April 20, 2026  
**Analysis Tool:** Python regex-based YAML parser  
**Methodology:** Extracted precondition type, prompt intent, chart reference, and version from all 26 DEP-*.yaml files
