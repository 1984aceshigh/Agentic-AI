Phase 2-6 integration tests.

Contents:
- tests/integration/test_phase2_runtime_flow.py

Intent:
- Verify the end-to-end Phase 2 runtime flow across context management,
  execution records, executor dispatch, human gate handling, and rerun preparation.

Assumptions:
- Phase 1 models already exist under agent_platform.models.execution.
- Phase 2-1 through 2-5 code has already been merged into the project.
