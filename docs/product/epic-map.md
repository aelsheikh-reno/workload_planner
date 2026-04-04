# Epic Map

## Approved 7-epic model

### EPIC-01 — Plan Intake and Normalization
Purpose: Import source-plan structure and normalize it into the internal planning model.  
Boundary: Intake, validation, and normalization only; not source authoring.

### EPIC-02 — Capacity and Availability Modeling
Purpose: Model productive capacity, calendars, exceptions, and resource availability rules.  
Boundary: Capacity truth for planning only; not HR-system replacement.

### EPIC-03 — Scheduling and Allocation Engine
Purpose: Generate a capacity-aware draft execution schedule from imported work and dependencies.  
Boundary: Draft scheduling and allocation only; not approval or activation.

### EPIC-04 — Planning Visibility and Diagnostics
Purpose: Present planning outputs so managers can inspect workload, drift, and planning state.  
Boundary: Visibility and diagnostics only; not rule ownership from planning, warnings, recommendations, or approval.

### EPIC-05 — Planning Risk, Warnings, and Trust Controls
Purpose: Evaluate plan quality and planning reliability and produce warnings/trust outputs.  
Boundary: Assessment and interpretation only; not scheduling, approval, or remediation ownership.

### EPIC-06 — Rebalancing Recommendations
Purpose: Generate deterministic candidate mitigation actions and rank them.  
Boundary: Recommendation generation/ranking only; not direct plan mutation.

### EPIC-07 — Draft Review, Approval, and Plan Activation
Purpose: Compare draft to approved state, support safe acceptance, and explicitly activate approved outcomes.  
Boundary: Review, acceptance, blocking, activation, and approved-plan governance only.
