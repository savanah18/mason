# CHAT-AH Consolidation Action Plan

**Status**: Ready for Implementation  
**Estimated Portfolio Reduction**: 6 files removed (33%) → 12 core + 1 parametric = 13 tests

---

## Quick Reference: Dispose Decisions

### **REMOVE - Exact Duplicates (DELETE)**

#### 1. CHAT-AH-002.0 → Absorbed into CHAT-AH-001.0
- **Reason**: Identical precondition (media-microservices fresh NS), identical intent (resource snapshot)
- **Decision**: Delete 002, keep 001 as unified baseline
- **Loss**: None (identical test value)
- **File Path**: [CHAT-AH-002.0.yaml](CHAT-AH-002.0.yaml#L1-L50)

#### 2. CHAT-AH-008.0 → Absorbed into CHAT-AH-001.0  
- **Reason**: Same precondition (media-microservices + workload check), semantically identical to 002
- **Decision**: Delete 008, keep 001
- **Loss**: None (triple-redundancy)
- **File Path**: [CHAT-AH-008.0.yaml](CHAT-AH-008.0.yaml#L1-L50)

#### 3. CHAT-AH-020.0 → Absorbed into CHAT-AH-017.0
- **Reason**: Identical incident precondition (quota pressure + same quota limits)
- **Precondition Match**: Both create ResourceQuota 300m/384Mi + 2-replica deployment
- **Resource Variation**: Only difference is request size (150m→200m CPU); same failure mode
- **Decision**: Delete 020, keep 017 as canonical quota incident
- **Loss**: None (tests same incident recovery)
- **File Path**: [CHAT-AH-020.0.yaml](CHAT-AH-020.0.yaml#L1-L50)

#### 4. CHAT-AH-021.0 → Absorbed into CHAT-AH-018.0
- **Reason**: Identical precondition (policy friction: quota + limitrange on 1 deployment)
- **Setup Equivalence**: Both use ResourceQuota 250m/256Mi + LimitRange defaults + incident-worker deployment
- **Prompt Redundancy**: Identical request (recover from policy friction + adjust workload)
- **Decision**: Delete 021, keep 018 as canonical policy incident
- **Loss**: None (identical incident pattern)
- **File Path**: [CHAT-AH-021.0.yaml](CHAT-AH-021.0.yaml#L1-L50)

#### 5. CHAT-AH-007.0 → Parametrized with CHAT-AH-011.0
- **Reason**: Both test Helm release inspection; only variable is namespace (victoria-metrics vs. infra)
- **Duplicate Pattern**: Same prompt intent, setup, and execution; different namespace target
- **Decision**: Keep 011, parametrize 007 as namespace variant (or delete if namespace variation not valuable)
- **Recommendation**: If testing cross-namespace behavior is valuable, parametrize; otherwise delete
- **File Path**: [CHAT-AH-007.0.yaml](CHAT-AH-007.0.yaml#L1-L50)

---

### **REVIEW - Decision Pending (Conditional)**

#### CHAT-AH-005.0: MCP Server Dependency Check
- **Rationale**: Tests media-microservices with Kubernetes MCP Server integration
- **Uniqueness**: Only scenario using external MCP server
- **Decision Matrix**:
  | Decision | Action | Reason |
  |----------|--------|--------|
  | MCP is strategic | KEEP | Validates MCP integration path |
  | MCP is exploratory | MERGE with 001 | Use 001 as simpler variant |
  | MCP unsupported | DELETE | Remove external dependency |
- **File Path**: [CHAT-AH-005.0.yaml](CHAT-AH-005.0.yaml#L1-L50)

#### CHAT-AH-014.0: Config + Event Inspection
- **Rationale**: Blends configuration inspection with event history (unique combination)
- **Relationship to B1**: Not purely Helm-focused like 007/011
- **Analysis**: Combines `kubernetes-configuration_view` + `kubernetes-events_list` (multi-tool test)
- **Decision**:
  | If Testing | Action |
  |-----------|--------|
  | Config+event diagnostics is valuable | KEEP |
  | Seen as "noise" in Helm suite | REVIEW with 007/011 |
- **Recommendation**: KEEP (unique diagnostic pattern) or DELETE if in B1 consolidation scope
- **File Path**: [CHAT-AH-014.0.yaml](CHAT-AH-014.0.yaml#L1-L50)

---

### **CONSOLIDATE - Functional Redundancy (Parametrize)**

#### CHAT-AH-010.0 + CHAT-AH-013.0 → Single Finance-Namespace Scenario
- **Common Precondition**: finance namespace with workloads
- **Intent Overlap**: Both inspect workload + resource settings
- **Key Difference**: 010 seeks overview; 013 seeks mismatch detection
- **Consolidation Strategy**:
  ```
  Proposed Parametric Test:
  
  ID: CHAT-AH-010+013 (Finance Workload Analysis)
  
  Variants:
    - Variant A: Workload summary (from 010)
    - Variant B: Mismatch analysis (from 013)
  
  Shared Precondition:
    kubectl get ns finance || kubectl create ns finance
    kubectl get pods -n finance --no-headers
  
  Shared Infrastructure:
    - Target namespace: finance
    - Check: existing workloads present
  ```
- **Action**: Create parametric test, retire originals or keep as reference
- **File Paths**: 
  - [CHAT-AH-010.0.yaml](CHAT-AH-010.0.yaml#L1-L50)
  - [CHAT-AH-013.0.yaml](CHAT-AH-013.0.yaml#L1-L50)

---

### **KEEP - Unique/High-Value Scenarios (NO CHANGES)**

#### ✓ CHAT-AH-001.0 (Absorbs 002, 008)
- **Baseline workload inventory** - serves as reference read-only test
- **No changes** (consolidation target for 002/008)

#### ✓ CHAT-AH-003.0 (UNIQUE → Release + Eventing)
- **Only scenario combining release verification + Kafka event publishing**
- **Multi-step workflow pattern** (verify → publish)
- **No consolidation candidates**

#### ✓ CHAT-AH-009.0 (Deployment Verification with Eventing)
- **Distinct from 003**: deployment-focused vs. release-focused
- **Tests deployment readiness + kafka publish**
- **Keep as separate pattern**

#### ✓ CHAT-AH-012.0 (Right-Sizing + Event)
- **Only scenario combining resource optimization + eventing**
- **Unique: mutation + publish pattern**
- **High value: tests write capability + integration**

#### ✓ CHAT-AH-015.0 (Health Snapshot with Logs)
- **Only scenario combining pod metrics + log extraction**
- **Unique diagnostic pattern: resource usage + error signals**
- **No equivalent**

#### ✓ CHAT-AH-016.0 (Replica Scaling Only)
- **Tests horizontal scaling in isolation**
- **Distinct from 012 (which includes resource changes)**
- **Single-dimension pattern validation**

#### ✓ CHAT-AH-017.0 (Quota Incident - Consolidation Target)
- **Absorbs 020 (identical incident)**
- **Canonical quota-pressure recovery test**
- **High complexity: 4 setupoperations**

#### ✓ CHAT-AH-018.0 (Policy Friction - Consolidation Target)
- **Absorbs 021 (identical incident)**
- **Canonical policy-friction recovery test**
- **Highest pre-incident complexity: 5 operations**

#### ✓ CHAT-AH-019.0 (Helm Release Recovery)
- **Only scenario testing Helm conflict resolution**
- **Unique: release-conflict recovery pattern**
- **No equivalent**

#### ✓ CHAT-AH-022.0 (Noise Filtering)
- **Maximum complexity scenario: 6+ operations**
- **Only scenario with intentional noise (signal/noise separation)**
- **Unique: anomaly detection under ambiguity**

---

## Implementation Timeline

### **Phase 1: Immediate Removal (Week 1)**
- Delete: CHAT-AH-002.0, CHAT-AH-008.0, CHAT-AH-020.0, CHAT-AH-021.0
- Update: Test suite references and CI/CD configurations
- Verify: No test suite depends on deleted versions

### **Phase 2: Conditional Reviews (Week 2)**
- Decide on CHAT-AH-005.0 (MCP dependency)
  - **Action**: Confirm MCP integration priority with team
  - **Outcome**: KEEP or DELETE
  
- Decide on CHAT-AH-014.0 (Config + Events)
  - **Action**: Assess value of config+event diagnostics
  - **Outcome**: KEEP or DELETE/PARAMETRIZE

- Decide on CHAT-AH-007.0 (Helm parametrize)
  - **Action**: Determine namespace-variance testing value
  - **Outcome**: PARAMETRIZE or DELETE

### **Phase 3: Consolidation Parametrization (Week 2-3)**
- Create: CHAT-AH-010+013-Finance-Workload-Analysis (parametric)
  - Consolidate finance namespace tests
  - Create variants for overview vs. mismatch analysis

- Parametrize: CHAT-AH-007.0+011.0 (if applicable)
  - Create namespace-scoped Helm inspection test
  - Reduce from 2 scenarios to 1 parametric

### **Phase 4: Documentation & Migration (Week 3)**
- Update: Test suite documentation
- Migrate: All test references to new consolidated names
- Archive: Deleted file versions in git history
- Verify: All CI/CD pipelines still operational

---

## Portfolio Summary: Before & After

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| Total Scenarios | 18 | 12 + 1 consolidated | 33% |
| Exact Duplicate Tests | 8 | 0 | 100% |
| Near-Duplicate Tests | 5+ | ~2 (parametric) | ~60% |
| Unique Tests | 5 | 12 | +140% representation |
| Average Precondition Complexity | 2.2 | 2.8 | Tests more complex scenarios |
| Eventing Coverage | 3/18 (17%) | 3/13 (23%) | Increased |
| Incident Recovery Coverage | 4/18 (22%) | 4/13 (31%) | Stronger |

---

## Risk Assessment

### **Low Risk**
- Removing 002, 008 (exact copies of 001)
- Removing 020, 021 (exact incident duplicates)
- Parametrizing 007, 011 (namespace variance)
- Consolidating 010, 013 (finance overlap)

### **Medium Risk**
- Deciding on 005 (MCP dependency) - affects integration strategy
- Deciding on 014 (config+events) - affects diagnostic coverage

### **Mitigation**
- Before removing, run combined scenario (all 18) on current system
- Document removal rationale for future reference
- Maintain git commit history showing consolidations
- Example: Use git tags for "final-ad-hoc-18.yaml" before consolidation

---

## Files to Delete

```bash
# Phase 1 - Immediate removal
rm CHAT-AH-002.0.yaml
rm CHAT-AH-008.0.yaml
rm CHAT-AH-020.0.yaml
rm CHAT-AH-021.0.yaml

# Phase 2 - Conditional (team decision)
# rm CHAT-AH-005.0.yaml  # If MCP unsupported
# rm CHAT-AH-007.0.yaml  # If parametrized or namespace variance not valued
# rm CHAT-AH-014.0.yaml  # If config+event diagnostics not prioritized
```

---

## Files to Create/Modify

### **New Parametric Tests**
```yaml
# Example: CHAT-AH-010+013-finance-workload-analysis.yaml
# Consolidates 010.0 (overview) + 013.0 (mismatch)
# Variants: variant-overview, variant-mismatch-analysis
```

### **Updated References**
- Test suite documentation
- CI/CD pipelines (if hardcoded scenario paths)
- Evaluation scripts (if filename-dependent)

---

## Expected Outcomes

✓ **Eliminate redundancy**: 33% fewer duplicate tests  
✓ **Increase signal**: More unique scenarios per test run  
✓ **Maintain coverage**: All capability areas still tested  
✓ **Improve maintainability**: Fewer files to update  
✓ **Highlight high-value tests**: Incident resolution patterns better represented  

---

## Sign-Off Checklist

- [ ] Team reviews consolidation recommendations
- [ ] MCP dependency decision made for 005.0
- [ ] Config+event value assessed for 014.0
- [ ] Namespace variance importance confirmed for 007.0
- [ ] Git backup created before deletion
- [ ] Phase 1 deletions executed
- [ ] Phase 2 conditional decisions finalized
- [ ] Phase 3 parametric tests created
- [ ] Phase 4 documentation updated
- [ ] Test suite re-run with consolidated portfolio
