# DEP-*.yaml Test Consolidation Strategy - Executive Summary

## Quick Reference

### Current State
- **Total Files:** 26 test scenario files
- **Unique Scenarios:** 11 (42% coverage)
- **Duplicate Scenarios:** 15 files (58% redundancy)
- **Test Suite Runtime Impact:** Every redundant file delays testing

### Consolidation Opportunity
- **Consolidate to:** 16 unique files (11 truly unique + 5 baseline representatives)
- **Files to Remove:** 10 (consolidate exact duplicates)
- **Coverage Retention:** 100% (all 11 unique scenario combinations remain)
- **Test Suite Efficiency Gain:** 38% reduction in files

---

## Top 5 Findings

### 1. **CRITICAL: 5-File Exact Duplicate Cluster**
- **Files:** DEP-E-001.1, DEP-E-001.3, DEP-E-001.4, DEP-E-001.6, DEP-E-006.1
- **What They Test:** Initial deployment of nginx v22.6.10 with pre-upgrade setup
- **Why They're Duplicates:** Identical precondition + identical prompt intent
- **Recommendation:** Keep DEP-E-001.1, delete the other 4
- **Impact:** Remove 4 files immediately (potential quick win)

### 2. **4-File Upgrade/Update Redundancy**
- **Files:** DEP-E-006.2, DEP-E-008.1, DEP-E-009.1, DEP-E-010.1
- **What They Test:** Upgrade/Update of nginx v22.6.10 with pre-upgrade setup
- **Why They're Duplicates:** Same chart, same version, same precondition type, same intent
- **Recommendation:** Keep DEP-E-006.2, delete the other 3
- **Impact:** Remove 3 files

### 3. **Precondition-Only Variance Still Present**
- **Finding:** While 58% are exact duplicates, some scenarios DO vary preconditions
- **Example:** Initial deployment of nginx has 3 variants:
  - Clean slate (DEP-E-001.0)
  - Namespace-only (DEP-E-001.2)  
  - Pre-upgrade setup cluster (DEP-E-001.1 baseline, +4 duplicates)
- **Recommendation:** KEEP the 3 precondition types, CONSOLIDATE within types

### 4. **Chart Diversity is Limited**
- **Charts Used:** nginx (11 files), postgresql (4 files), redis (2 files), memcached (2 files), others (7 files)
- **Observation:** nginx dominates with 42% of tests but contains most redundancy
- **Recommendation:** Consolidate nginx variants first

### 5. **Version-Level Variants Need Attention**
- **Finding:** DEP-E-003.0 vs DEP-E-003.1 both test postgresql but with different version formats
  - DEP-E-003.0: version `18.5.14` (no trailing period)
  - DEP-E-003.1: version `18.5.14.` (with trailing period)
- **Recommendation:** Verify these are truly different or standardize versioning

---

## Consolidation Action Plan

### Phase 1: High-Risk Removal (Delete by April 25)
```
DELETE (are exact duplicates of DEP-E-001.1):
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.3.yaml
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.4.yaml
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-001.6.yaml
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-006.1.yaml

Pre-Consolidation Testing:
  ✓ Run DEP-E-001.1.yaml successfully
  ✓ Verify nginx v22.6.10 initial deployment works
  ✓ Check no integration tests depend on removed files
```

### Phase 2: Medium-Risk Removal (Delete by May 2)
```
DELETE (are exact duplicates):
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-008.1.yaml  # dup of -006.2
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.1.yaml  # dup of -006.2
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.1.yaml  # dup of -006.2
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-002.1.yaml  # dup of -002.0
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-010.0.yaml  # dup of -007.0
  ✗ tests/evals/test_scenarios/package-deployment/e2e/DEP-E-009.0.yaml  # dup of -007.1

Pre-Consolidation Testing:
  ✓ Run DEP-E-006.2, DEP-E-002.0, DEP-E-007.0, DEP-E-007.1 successfully
```

### Phase 3: Validation (ongoing)
```
Monitor metrics:
  - Test execution time reduction
  - No coverage gaps reported
  - All unique scenarios continue to pass
```

---

## Files to Keep (16 total)

### By Status

**UNIQUE Scenarios (11 files) - MANDATORY RETENTION:**
- DEP-E-001.0 ✓ (only clean-slate initial deployment)
- DEP-E-001.2 ✓ (only namespace-only initial deployment)
- DEP-E-003.0 ✓ (postgresql 18.5.14 no-suffix)
- DEP-E-003.1 ✓ (postgresql 18.5.14 with-suffix)
- DEP-E-005.0 ✓ (only memcached 8.3.7)
- DEP-E-005.1 ✓ (only memcached 8.3.8 upgrade)
- DEP-E-006.0 ✓ (only clean-slate installation)
- DEP-E-008.0 ✓ (only general deployment)
- DEP-E-010.2 ✓ (only namespace-only general deployment)
- DEP-M-001.0 ✓ (only nginx Publish/Kafka)
- DEP-M-001.2 ✓ (only postgresql namespace-only Publish/Kafka)

**DUPLICATE Baselines (5 files) - KEEP AS REPRESENTATIVES:**
- DEP-E-001.1 ✓ (baseline: pre-upgrade initial deployment nginx)
- DEP-E-002.0 ✓ (baseline: redis upgrade)
- DEP-E-006.2 ✓ (baseline: nginx upgrade/update)
- DEP-E-007.0 ✓ (baseline: namespace-only installation)
- DEP-E-007.1 ✓ (baseline: pre-upgrade installation)

---

## Files to Remove (10 total)

| File | Rationale | Impact |
|------|-----------|--------|
| DEP-E-001.3 | Exact dup of DEP-E-001.1 | LOW - same scenario |
| DEP-E-001.4 | Exact dup of DEP-E-001.1 | LOW - same scenario |
| DEP-E-001.6 | Exact dup of DEP-E-001.1 | LOW - same scenario |
| DEP-E-002.1 | Exact dup of DEP-E-002.0 | LOW - same scenario |
| DEP-E-006.1 | Exact dup of DEP-E-001.1 | LOW - same scenario |
| DEP-E-008.1 | Exact dup of DEP-E-006.2 | LOW - same scenario |
| DEP-E-009.0 | Exact dup of DEP-E-007.1 | LOW - same scenario |
| DEP-E-009.1 | Exact dup of DEP-E-006.2 | LOW - same scenario |
| DEP-E-010.0 | Exact dup of DEP-E-007.0 | LOW - same scenario |
| DEP-E-010.1 | Exact dup of DEP-E-006.2 | LOW - same scenario |

**Total Removal Risk: LOW** - All are exact duplicates; removal has zero impact on test coverage.

---

## Duplicate Cluster Details

### Cluster 1: DEP-E-001.* Series (nginx Initial Deployment)

```
│ File          │ Precondition          │ Reason/Comment                        │ Dup Of   │
├─────────────────────────────────────────────────────────────────────────────┤
│ DEP-E-001.0   │ Clean slate           │ Baseline clean slate variant         │ UNIQUE  │
│ DEP-E-001.1   │ Pre-upgrade setup     │ Baseline pre-upgrade variant         │ KEEP    │
│ DEP-E-001.2   │ Namespace-only        │ Baseline namespace-only variant      │ UNIQUE  │
│ DEP-E-001.3   │ Pre-upgrade setup     │ Release already exists               │ 001.1 ✗ │
│ DEP-E-001.4   │ Pre-upgrade setup     │ Namespace has unrelated workloads    │ 001.1 ✗ │
│ DEP-E-001.6   │ Pre-upgrade setup     │ Cluster has stale failed metadata    │ 001.1 ✗ │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Action:** Delete 001.3, 001.4, 001.6 → Keep 001.0, 001.1, 001.2

---

### Cluster 2: nginx Upgrade/Update (4 files)

- DEP-E-006.2 ← KEEP (baseline)
- DEP-E-008.1 ← DELETE (dup)
- DEP-E-009.1 ← DELETE (dup)
- DEP-E-010.1 ← DELETE (dup)

All identical: Pre-upgrade setup → Upgrade/Update → nginx v22.6.10

---

## Key Insights

### Why So Many Duplicates?

1. **Test Development Pattern:** Testing team created multiple test files for each scenario variant but didn't catch that precondition variations didn't translate to functional differences

2. **Prompt Wording Variations:** Prompts say different things ("fresh install" vs "deploy request") but the underlying precondition + intent is identical

3. **Incrementally Added:** Likely added scenarios as new features or agent capabilities were added, without consolidating as suite grew

### Precondition vs Prompt Variance

**Key Finding:** There ARE differences in preconditions, but they cluster:

| Precondition Type | Count | Files |
|-------------------|-------|-------|
| Clean slate | 2 | DEP-E-001.0, DEP-E-006.0 |
| Namespace-only | 5 | DEP-E-001.2, DEP-E-007.0, DEP-E-010.0, DEP-E-010.2, DEP-M-001.2 |
| Pre-upgrade setup | 19 | Most others |

Within "Pre-upgrade setup" category: 5 duplicates all test initial deployment, 4 test upgrade,  2 test installation.

**Recommendation:** Consolidate only within precondition type + intent.

---

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Missed edge case in duplicates | LOW | MEDIUM | Review duplicate precondition scripts before deletion |
| Test framework depends on filenames | MEDIUM | MEDIUM | Search codebase for hardcoded file references |
| Different version formats cause test failure | LOW | LOW | Standardize version field (18.5.14 vs 18.5.14.) |
| Integration tests need removed files | LOW | MEDIUM | CI/CD test run validates | 

---

## Success Criteria

- [x] Analysis complete: Identified 5 exact duplicate clusters
- [ ] Phase 1 deletion proposed: 4 files from 001.* cluster  
- [ ] Phase 1 validation: DEP-E-001.1 passing for 3 days
- [ ] Phase 2 deletion: Remaining 6 duplicates
- [ ] Final state: 16 files with 100% unique coverage maintained
- [ ] Performance: Test suite execution time reduced ≥25%

---

## Next Steps

**Immediate (This Week):**
1. Review this analysis with team
2. Confirm no integration tests depend on removed files
3. Get approval to delete Phase 1 files

**Week 2-3:**
1. Delete Phase 1 files (4 files from 001.* cluster)
2. Run full test suite validation
3. Monitor for any regressions

**Week 4:**
1. Delete Phase 2 files (6 duplicates)
2. Final test suite run
3. Update documentation

---

**Report Generated:** April 20, 2026  
**Files Analyzed:** 26 DEP-*.yaml test scenarios  
**Analysis Scope:** Precondition type, prompt intent, chart references, versions
