# CHAT-AH Scenario Uniqueness Analysis

**Analysis Date**: April 21, 2026  
**Total Files**: 20 scenarios (004 & 006 not found; 18 valid files)  
**Analysis Scope**: Precondition types, complexity, prompt intent, and persona usage

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Scenarios Analyzed** | 18 |
| **Unique Precondition Types** | 8 |
| **Precondition Complexity Range** | 1-6 kubectl/helm operations |
| **Distinct Prompt Intents** | 7 |
| **Personas Used** | 1 (chat all) |
| **Exact Duplicates** | 4 clusters (8 scenarios) |
| **Near-Duplicates** | 3 clusters (5 scenarios) |
| **Functionally Redundant** | 3 scenarios |
| **Unique/High-Value Scenarios** | 5 scenarios |
| **Consolidation Opportunity** | ~11 scenarios (61%) |

---

## Detailed File Analysis Matrix

| File | Precondition Type | Complexity | Prompt Intent | Focus Area | Status | Cluster |
|------|-------------------|-----------|---------------|-----------|--------|---------|
| **CHAT-AH-001.0** | Fresh namespace (media-microservices) | 1 | Resource info retrieval / workload inventory | Read-only | DUPLICATE | A1 |
| **CHAT-AH-002.0** | Fresh namespace (media-microservices) | 1 | Resource info retrieval / metrics collection | Read-only | DUPLICATE | A1 |
| **CHAT-AH-003.0** | Fresh namespace + optional release (finance) | 2 | Release verification + eventing | Read-only + publish | UNIQUE | - |
| **CHAT-AH-005.0** | Fresh namespace + MCP assumption (media-microservices) | 1 | Deployment readiness + cross-validation | Read-only + MCP | NEAR-DUP | A2 |
| **CHAT-AH-007.0** | Fresh namespace (victoria-metrics) | 1 | Release inspection | Read-only | DUPLICATE | B1 |
| **CHAT-AH-008.0** | Fresh namespace with workload check (media-microservices) | 2 | Resource snapshot + analysis | Read-only | NEAR-DUP | A1 |
| **CHAT-AH-009.0** | Fresh namespace with workload check (media-microservices) | 2 | Deployment verification + eventing | Read-only + publish | NEAR-DUP | C1 |
| **CHAT-AH-010.0** | Fresh namespace with workload check (finance) | 2 | Workload + resource overview | Read-only | FUNCTIONAL-RED | D1 |
| **CHAT-AH-011.0** | Fresh namespace (infra) | 1 | Release inspection | Read-only | DUPLICATE | B1 |
| **CHAT-AH-012.0** | Fresh namespace with workload check (search) | 2 | Right-size + publish event | Write + publish | UNIQUE | - |
| **CHAT-AH-013.0** | Fresh namespace with pods (finance) | 2 | Resource definition inspection | Read-only | FUNCTIONAL-RED | D1 |
| **CHAT-AH-014.0** | Fresh namespace (infra) | 1 | Config + event inspection | Read-only | DUPLICATE | B1 |
| **CHAT-AH-015.0** | Fresh namespace with pods (media-microservices) | 2 | Health snapshot + logs | Read-only | UNIQUE | - |
| **CHAT-AH-016.0** | Fresh namespace with deployment (search) | 2 | Replica scaling | Write | UNIQUE | - |
| **CHAT-AH-017.0** | Simulated quota incident (ResourceQuota + Deploy) | 4 | Quota violation recovery + right-size | Write + incident | DUPLICATE | E1 |
| **CHAT-AH-018.0** | Simulated policy friction (Quota + LimitRange + Deploy) | 5 | Policy friction recovery + adjustment | Write + incident | DUPLICATE | F1 |
| **CHAT-AH-019.0** | Helm release conflict state | 3 | Helm recovery | Write + incident | UNIQUE | - |
| **CHAT-AH-020.0** | Simulated quota incident (ResourceQuota + Deploy) | 4 | Quota violation recovery + right-size | Write + incident | DUPLICATE | E1 |
| **CHAT-AH-021.0** | Simulated policy friction (Quota + LimitRange + Deploy) | 5 | Policy friction recovery + reduction | Write + incident | DUPLICATE | F1 |
| **CHAT-AH-022.0** | Noisy namespace (multi-deployment + quota) | 6 | Noise filtering + anomaly detection | Write + incident | UNIQUE | - |

---

## Precondition Type Classification

### **Type 1: Fresh Namespace Only** (Complexity: 1)
- **Files**: 001, 002, 007, 011, 014
- **Setup**: `kubectl get ns <ns> || kubectl create ns <ns>`
- **Characteristic**: No objects created, just namespace existence
- **Count**: 5 scenarios

### **Type 2: Fresh Namespace + Workload Verification** (Complexity: 2)
- **Files**: 008, 009, 010, 012, 013, 015, 016
- **Setup**: Namespace creation + workload count check via `kubectl get deploy|pods`
- **Characteristic**: Assumes workloads exist but doesn't create them
- **Count**: 7 scenarios

### **Type 3: Fresh Namespace + MCP Assumption** (Complexity: 1-2)
- **Files**: 005
- **Setup**: Namespace creation + MCP server availability assumption
- **Characteristic**: Depends on external MCP server
- **Count**: 1 scenario

### **Type 4: Fresh Namespace + Release Optional** (Complexity: 2)
- **Files**: 003
- **Setup**: Namespace creation + helm list check (no release creation)
- **Characteristic**: Mixed read-only + action (kafka publish)
- **Count**: 1 scenario

### **Type 5: Simulated Quota Incident** (Complexity: 4)
- **Files**: 017, 020
- **Setup**: Namespace creation + ResourceQuota + Deployment with requests/limits
- **Objects**: 3+ (NS, quota, deployment)
- **Characteristic**: Tests high-complexity incident scenario w/ resource constraints
- **Count**: 2 scenarios (EXACT DUPLICATES)

### **Type 6: Simulated Policy Friction** (Complexity: 5)
- **Files**: 018, 021
- **Setup**: Namespace + ResourceQuota + LimitRange + Deployment(s)
- **Objects**: 4+ (NS, quota, limitrange, deployment)
- **Characteristic**: Tests policy-induced failure recovery
- **Count**: 2 scenarios (EXACT DUPLICATES)

### **Type 7: Helm Release Conflict** (Complexity: 3)
- **Files**: 019
- **Setup**: Namespace + helm install + history check
- **Objects**: 2 (NS, release)
- **Characteristic**: Tests Helm state recovery
- **Count**: 1 scenario

### **Type 8: Noisy Multi-Deployment Quota** (Complexity: 6)
- **Files**: 022
- **Setup**: Namespace + ResourceQuota + 2 deployments (signal + noise)
- **Objects**: 5+ (NS, quota, 2 deployments)
- **Characteristic**: Tests signal extraction under noise
- **Count**: 1 scenario (UNIQUE COMPLEXITY)

---

## Duplicate Clusters

### **CLUSTER A1: Namespace-Scoped Resource Inventory** (EXACT DUPLICATES)
- **Files**: CHAT-AH-001.0, CHAT-AH-002.0, CHAT-AH-008.0
- **Precondition**: Fresh `media-microservices` namespace
- **Complexity**: 1-2 operations
- **Prompt Intent**: Workload/resource inventory and metrics collection
- **Key Difference**: 
  - 001 ([[001.0.yaml#L2-L4]](CHAT-AH-001.0.yaml#L2-L4)): "compact workload inventory"
  - 002 ([[002.0.yaml#L2-L5]](CHAT-AH-002.0.yaml#L2-L5)): "5-minute CPU usage snapshot" + "top 3 consumers"
  - 008 ([[008.0.yaml#L2-L6]](CHAT-AH-008.0.yaml#L2-L6)): "5-minute resource snapshot" + "exclude complex queries"
- **Semantic Redundancy**: 002 and 008 are semantically near-identical (same timeframe, resource scope)
- **Recommendation**: **CONSOLIDATE 002 + 008 into 001** (keep 001 as it's simpler baseline)

### **CLUSTER A2: Media-Microservices with MCP** (NEAR-DUPLICATE)
- **Files**: CHAT-AH-005.0
- **Precondition**: Fresh `media-microservices` + MCP server assumption
- **Complexity**: 1-2 operations (incl. MCP dependency)
- **Prompt Intent**: Deployment readiness check + cross-validation
- **Distinguishing Feature**: Uses kubernetes-mcp-server (external tool dependency)
- **Recommendation**: **KEEP** if MCP integration is strategic; otherwise **MERGE with 001** as variant

### **CLUSTER B1: Helm Release Inspection** (NEAR-DUPLICATES)
- **Files**: CHAT-AH-007.0, CHAT-AH-011.0, CHAT-AH-014.0
- **Precondition**: Fresh namespace (victoria-metrics, infra, infra)
- **Complexity**: 1 operation per file
- **Prompt Intent**: Helm release status + resource configuration
- **Key Variation**:
  - 007 ([[007.0.yaml#L2-L5]](CHAT-AH-007.0.yaml#L2-L5)): "Helm release state for victoria-metrics"
  - 011 ([[011.0.yaml#L2-L5]](CHAT-AH-011.0.yaml#L2-L5)): "Helm release status in namespace infra"
  - 014 ([[014.0.yaml#L2-L5]](CHAT-AH-014.0.yaml#L2-L5)): "Config + events (not just Helm)"
- **Semantic Issue**: 007 & 011 are testing identical capability on different namespaces
- **Recommendation**: **CONSOLIDATE 007 + 011 into parametrized scenario**; **KEEP 014** as config+event variant

### **CLUSTER C1: Deployment Verification + Eventing** (NEAR-DUPLICATES)
- **Files**: CHAT-AH-003.0, CHAT-AH-009.0
- **Precondition**: Fresh namespace + optional/existing objects
- **Complexity**: 2 operations
- **Prompt Intent**: Verify deployment/release → publish Kafka event
- **Key Variation**:
  - 003 ([[003.0.yaml#L2-L5]](CHAT-AH-003.0.yaml#L2-L5)): "verify release finance" + "helm tests" + Kafka publish
  - 009 ([[009.0.yaml#L2-L6]](CHAT-AH-009.0.yaml#L2-L6)): "verify bounded deployment update" + Kafka publish
- **Semantic Difference**: 003 is release-focused; 009 is deployment-focused
- **Recommendation**: **KEEP BOTH** as distinct (release vs. deployment verification patterns)

### **CLUSTER D1: Namespace Workload Analysis** (FUNCTIONAL REDUNDANCY)
- **Files**: CHAT-AH-010.0, CHAT-AH-013.0
- **Precondition**: Fresh `finance` namespace with workloads
- **Complexity**: 2 operations each
- **Prompt Intent**: Workload + resource introspection
- **Key Difference**:
  - 010 ([[010.0.yaml#L2-L6]](CHAT-AH-010.0.yaml#L2-L6)): "compact workload and resource overview" + "requested CPU/memory"
  - 013 ([[013.0.yaml#L2-L6]](CHAT-AH-013.0.yaml#L2-L6)): "inspect resource definitions" + "pod count" + "mismatch analysis"
- **Functional Overlap**: Both inspect finance namespace resources with near-identical outcome
- **Recommendation**: **CONSOLIDATE into single parametrized scenario**  

### **CLUSTER E1: Quota Pressure Incident** (EXACT DUPLICATES)
- **Files**: CHAT-AH-017.0, CHAT-AH-020.0
- **Precondition**: Simulated quota incident (ResourceQuota 300m CPU / 384Mi mem + 2 deployments)
- **Complexity**: 4 operations (create NS, apply quota, apply deployment)
- **Precondition Details**:
  - **017** ([[017.0.yaml#L5-L40]](CHAT-AH-017.0.yaml#L5-L40)): Quota 300m/384Mi, Deploy 2 replicas @150m CPU/128Mi mem
  - **020** ([[020.0.yaml#L5-L44]](CHAT-AH-020.0.yaml#L5-L44)): Quota 300m/384Mi, Deploy 2 replicas @200m CPU/192Mi mem
- **Difference**: Resource request size differ slightly (150m → 200m CPU, 128Mi → 192Mi mem)
- **Prompt Intent**: Both = "recover from quota pressure" + "right-size workload"
- **Analysis**: Same scenario with minor resource variation
- **Recommendation**: **REMOVE 020, KEEP 017** as canonical quota-pressure incident

### **CLUSTER F1: Policy Friction Incident** (EXACT DUPLICATES)
- **Files**: CHAT-AH-018.0, CHAT-AH-021.0
- **Precondition**: Simulated policy friction (ResourceQuota 250m/256Mi + LimitRange + 1-2 deployments)
- **Complexity**: 5 operations (NS, quota, limitrange, deployment)
- **Precondition Details**:
  - **018** ([[018.0.yaml#L5-L50]](CHAT-AH-018.0.yaml#L5-L50)): 1 deployment `incident-worker` (no explicit resources, relies on LimitRange defaults)
  - **021** ([[021.0.yaml#L5-L50]](CHAT-AH-021.0.yaml#L5-L50)): 1 deployment `incident-worker` (2 replicas initially, same defaults)
- **Prompt Difference**:
  - 018 ([[018.0.yaml#L52-L56]](CHAT-AH-018.0.yaml#L52-L56)): "recover from namespace policy change" + "adjust workload"
  - 021 ([[021.0.yaml#L52-L56]](CHAT-AH-021.0.yaml#L52-L56)): "recover from namespace policy friction" + "reduce footprint"
- **Semantic Equivalence**: Both test LimitRange-induced rollout friction with identical setup
- **Recommendation**: **REMOVE 021, KEEP 018** as canonical policy-friction incident

---

## High-Value Unique Scenarios

### **1. CHAT-AH-003.0: Release Verification + Event Publishing**
- **Precondition Complexity**: 2 (namespace + optional release)
- **Unique Aspect**: Tests release state verification combined with **Kafka eventing** (pub/sub integration)
- **Value**: Validates multi-step workflow (verify → act → publish)
- **Line Reference**: [[003.0.yaml#L2-L5]](CHAT-AH-003.0.yaml#L2-L5)
- **Status**: KEEP - No equivalent scenario

### **2. CHAT-AH-012.0: Right-Sizing + Event Publishing**
- **Precondition Complexity**: 2 (search namespace with workloads)
- **Unique Aspect**: Tests **bounded resource mutation** followed by event publishing
- **Value**: Validates write/optimization capability with eventing
- **Line Reference**: [[012.0.yaml#L2-L8]](CHAT-AH-012.0.yaml#L2-L8)
- **Status**: KEEP - Only scenario testing right-size + publish pattern

### **3. CHAT-AH-015.0: Health Snapshot with Log Analysis**
- **Precondition Complexity**: 2 (media-microservices with pods)
- **Unique Aspect**: Combines **pod resource usage** (top) + **log extraction** for diagnostics
- **Value**: Tests multi-source diagnostic capability (metrics + logs)
- **Line Reference**: [[015.0.yaml#L2-L7]](CHAT-AH-015.0.yaml#L2-L7)
- **Status**: KEEP - Unique diagnostic pattern (resource + logs)

### **4. CHAT-AH-016.0: Replica Scaling Only**
- **Precondition Complexity**: 2 (search namespace with deployment)
- **Unique Aspect**: Tests **horizontal scaling** (replica adjustment) in isolation
- **Value**: Validates single-dimension scaling without resource changes
- **Line Reference**: [[016.0.yaml#L2-L5]](CHAT-AH-016.0.yaml#L2-L5)
- **Status**: KEEP - Distinct from 012 (which includes resource + replica changes)

### **5. CHAT-AH-019.0: Helm Release Conflict Recovery**
- **Precondition Complexity**: 3 (namespace + helm install + conflict state)
- **Unique Aspect**: Tests **Helm state recovery** from conflict/stale release
- **Value**: Validates release remediation without namespace deletion
- **Line Reference**: [[019.0.yaml#L5-L15]](CHAT-AH-019.0.yaml#L5-L15)
- **Status**: KEEP - Only Helm recovery scenario

### **6. CHAT-AH-022.0: Noise Filtering in Incident Resolution**
- **Precondition Complexity**: 6 (multi-deployment + quota with signal/noise)
- **Unique Aspect**: Tests **signal extraction** with intentional noise (2 deployments, one distractor)
- **Value**: Validates ability to identify root cause under ambiguity
- **Line Reference**: [[022.0.yaml#L5-L70]](CHAT-AH-022.0.yaml#L5-L70)
- **Status**: KEEP - Only noise-filtering scenario (highest complexity)

---

## Consolidation Recommendations

### **TIER 1: Remove (Exact Duplicates - 6 files)**
- **CHAT-AH-002.0** → merge into CHAT-AH-001.0 (same precondition, same intent, simpler variant exists)
- **CHAT-AH-008.0** → merge into CHAT-AH-001.0 (redundant CPU snapshot, same namespace)
- **CHAT-AH-020.0** → delete, keep CHAT-AH-017.0 (identical quota incident, minor resource variation)
- **CHAT-AH-021.0** → delete, keep CHAT-AH-018.0 (identical policy friction, same setup)
- **CHAT-AH-007.0** → parametrize with CHAT-AH-011.0 (same Helm inspection, different namespaces)
- **CHAT-AH-014.0** → variant of B1 cluster (but unique enough: config + events vs. release only) - REVIEW

### **TIER 2: Consider Merging (Functional Redundancy - 2 files)**
- **CHAT-AH-010.0** + **CHAT-AH-013.0** → single parametrized finance-namespace scenario
  - Both: finance namespace, workload inspection, resource definitions
  - Difference: 010 seeks overview; 013 seeks mismatch analysis
  - Recommendation: Keep as variants of same test (parametrize on analysis goal)

### **TIER 3: Review (Near-Duplicates - 3 files)**
- **CHAT-AH-005.0**: Depends on MCP server
  - Decision: Keep if MCP integration is strategic priority; otherwise merge with 001
- **CHAT-AH-009.0** vs. **CHAT-AH-003.0**: Release vs. deployment verification
  - Decision: Keep both (different resource types)

### **TIER 4: Keep (Unique/High-Value - 6 files)**
- CHAT-AH-003.0 ✓
- CHAT-AH-012.0 ✓
- CHAT-AH-015.0 ✓
- CHAT-AH-016.0 ✓
- CHAT-AH-019.0 ✓
- CHAT-AH-022.0 ✓

---

## Consolidated Test Suite Recommendation

### **Proposed Final Set: 12 Scenarios** (from 18, -33% reduction)

| File | Precondition | Intent | Rationale | Priority |
|------|-------------|--------|-----------|----------|
| CHAT-AH-001.0 | media-microservices | Workload inventory | Baseline read | **KEEP** |
| CHAT-AH-003.0 | finance + release | Verify + publish | Multi-step workflow | **KEEP** |
| CHAT-AH-005.0* | media-microservices + MCP | Readiness check | MCP integration | **REVIEW** |
| CHAT-AH-009.0 | media-microservices | Deploy verification | Deployment pattern | **KEEP** |
| CHAT-AH-010+013.0* | finance | Workload analysis | Parametrized variant | **CONSOLIDATE** |
| CHAT-AH-011.0 | infra | Helm inspection | Config pattern | **KEEP** |
| CHAT-AH-012.0 | search | Right-size + publish | Optimization + eventing | **KEEP** |
| CHAT-AH-015.0 | media-microservices | Health + logs | Diagnostic pattern | **KEEP** |
| CHAT-AH-016.0 | search | Replica scaling | Single-dimension scaling | **KEEP** |
| CHAT-AH-017.0 | incident-resolution | Quota recovery | High-complexity incident | **KEEP** |
| CHAT-AH-018.0 | incident-resolution | Policy recovery | Policy friction incident | **KEEP** |
| CHAT-AH-019.0 | incident-resolution | Helm recovery | Release recovery | **KEEP** |
| CHAT-AH-022.0 | incident-resolution | Noise filtering | Signal extraction | **KEEP** |

**Removed**: 002, 007, 008, 014, 020, 021 (6 scenarios)  
**Consolidate**: 010+013 (1 consolidated scenario)  
**Review**: 005 (1 decision-pending)

---

## Matrix: Precondition Complexity vs. Prompt Intent

| Precondition Complexity | Resource Info | Config Inspection | Helm Management | Scaling | Right-Sizing | Incident Resolution | Eventing |
|------------------------|----------------|------------------|-----------------|---------|--------------|-------------------|---------| 
| **1 (simple NS)** | 001,002 | 014* | 007,011 | - | - | - | - |
| **2 (NS + workloads)** | 008,010,013 | - | - | 016 | 012 | - | 009 |  
| **3 (NS + release)** | - | - | - | - | - | - | 003,019* |
| **4 (NS + quota)** | - | - | - | - | - | 017,020 | - |
| **5 (NS + policy)** | - | - | - | - | - | 018,021 | - |
| **6 (multi)** | - | - | - | - | - | 022 | - |

*Scenarios merging cell categories

---

## Key Insights

1. **Namespace scope over-represented**: 5 scenarios test simple namespace creation with no state
2. **Media-microservices overused**: 5 scenarios (001, 002, 005, 008, 009, 015) use same namespace
3. **Finance namespace redundant**: 3 scenarios (003, 010, 013) overlap significantly
4. **Incident scenarios well-differentiated**: 017, 018, 019, 022 each test unique failure modes
5. **Eventing under-tested**: Only 3, 009, 012 explicitly test Kafka publishing
6. **All scenarios use "chat" persona**: No deployer, ops, or other personas in ad-hoc suite

---

## Appendix: Evidence Citations

### Exact Duplicate Files (with line ranges)

**CLUSTER E1 - Quota Incidents:**
- [017.0 precondition](CHAT-AH-017.0.yaml#L5-L40): ResourceQuota 300m/384Mi, 2 replicas @150m/128Mi
- [020.0 precondition](CHAT-AH-020.0.yaml#L5-L44): ResourceQuota 300m/384Mi, 2 replicas @200m/192Mi
- [017.0 prompt](CHAT-AH-017.0.yaml#L2-L5): "recover resource-pressure incident"
- [020.0 prompt](CHAT-AH-020.0.yaml#L2-L5): "recover quota-pressure incident"

**CLUSTER F1 - Policy Incidents:**
- [018.0 precondition](CHAT-AH-018.0.yaml#L5-L50): ResourceQuota 250m/256Mi + LimitRange + deployment
- [021.0 precondition](CHAT-AH-021.0.yaml#L5-L50): ResourceQuota 250m/256Mi + LimitRange + deployment
- [018.0 prompt](CHAT-AH-018.0.yaml#L2-L5): "recover from policy change"
- [021.0 prompt](CHAT-AH-021.0.yaml#L2-L5): "recover from policy friction"

---

## Files Analyzed

✓ CHAT-AH-001.0, 002.0, 003.0, 005.0, 007.0, 008.0, 009.0, 010.0  
✓ CHAT-AH-011.0, 012.0, 013.0, 014.0, 015.0, 016.0, 017.0, 018.0  
✓ CHAT-AH-019.0, 020.0, 021.0, 022.0  
✗ CHAT-AH-004.0, 006.0 (not found)
