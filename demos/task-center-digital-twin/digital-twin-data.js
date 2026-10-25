window.XUANJUN_TWIN_DATA = {
  "anomalies": [],
  "boards": [
    {
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "acceptance-delivery",
      "health": "STABLE",
      "task_count": 1
    },
    {
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "customer",
      "health": "NO_DATA",
      "task_count": 0
    },
    {
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "finance",
      "health": "NO_DATA",
      "task_count": 0
    },
    {
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "maintenance",
      "health": "NO_DATA",
      "task_count": 0
    },
    {
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "operations",
      "health": "NO_DATA",
      "task_count": 0
    },
    {
      "active_count": 1,
      "blocked_count": 0,
      "board_id": "research-development",
      "health": "ACTIVE",
      "task_count": 2
    },
    {
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "shared-ecosystem",
      "health": "NO_DATA",
      "task_count": 0
    }
  ],
  "mode": "TEST_ONLY",
  "production_status": "NOT_IMPLEMENTED",
  "schema": 2,
  "tasks": [
    {
      "attempt_id": "demo-a-attempt",
      "authority_state": "VALID",
      "blocker": null,
      "board_id": "research-development",
      "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "checkpoints": [
        {
          "attempt_id": "demo-a-prior",
          "checkpoint_id": "demo-a-checkpoint",
          "created_at": 1792914219.1551578,
          "effects_state": "RECONCILED",
          "resources_json": "[\"fake:shared\"]"
        }
      ],
      "dependencies": [
        {
          "event_attempt_id": "demo-b-attempt",
          "event_id": "terminal-demo-b-attempt",
          "producer_task_id": "demo-b",
          "required_evidence_ref": "evid-demo-b",
          "required_version": "b-v1",
          "state": "RECEIVED"
        }
      ],
      "epoch": 1,
      "input_version": "input-v1",
      "module_id": "xuanjun.scheduler.kernel",
      "next_action": "RESUME_ADMISSION_REQUIRED",
      "node_id": "node-demo-a",
      "output_version": "a-v1",
      "preemptible": true,
      "priority": 100,
      "project_id": "demo-project",
      "resources": [
        "fake:shared"
      ],
      "responsible_party": "test-executor",
      "state": "STARTED",
      "task_id": "demo-a",
      "task_responsible_party": "test-executor"
    },
    {
      "attempt_id": "demo-b-attempt",
      "authority_state": "REVOKED",
      "blocker": null,
      "board_id": "acceptance-delivery",
      "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "checkpoints": [
        {
          "attempt_id": "demo-b-attempt",
          "checkpoint_id": "terminal-checkpoint-demo-b-attempt",
          "created_at": 1792914219.174842,
          "effects_state": "RECONCILED",
          "resources_json": "[\"fake:demo-b\"]"
        }
      ],
      "dependencies": [],
      "epoch": 1,
      "input_version": "input-v1",
      "module_id": "xuanjun.scheduler.kernel",
      "next_action": "DEPENDENCIES_RECHECK",
      "node_id": "node-demo-b",
      "output_version": "b-v1",
      "preemptible": true,
      "priority": 50,
      "project_id": "demo-project",
      "resources": [
        "fake:demo-b"
      ],
      "responsible_party": "test-executor",
      "state": "SUCCESS",
      "task_id": "demo-b",
      "task_responsible_party": "test-executor"
    },
    {
      "attempt_id": "UNKNOWN",
      "authority_state": "NONE",
      "blocker": null,
      "board_id": "research-development",
      "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "checkpoints": [
        {
          "attempt_id": "demo-c-attempt",
          "checkpoint_id": "demo-c-checkpoint",
          "created_at": 1792914219.2738826,
          "effects_state": "RECONCILED",
          "resources_json": "[\"fake:shared\"]"
        }
      ],
      "dependencies": [],
      "epoch": null,
      "input_version": "input-v1",
      "module_id": "xuanjun.scheduler.kernel",
      "next_action": "RESUME_FROM_CHECKPOINT",
      "node_id": "node-demo-c",
      "output_version": "c-v1",
      "preemptible": false,
      "priority": 10,
      "project_id": "demo-project",
      "resources": [
        "fake:shared"
      ],
      "responsible_party": "test-executor",
      "state": "READY",
      "task_id": "demo-c",
      "task_responsible_party": "test-executor"
    }
  ],
  "tenant_id": "tenant-a",
  "timeline": [
    {
      "attempt_id": "demo-c-attempt",
      "event_id": "received-demo-c-attempt",
      "evidence_kind": "PHASE_EXECUTION",
      "evidence_ref": "test-received-demo-c-attempt",
      "kind": "RECEIVED",
      "observed_at": 1792914219.1604135,
      "task_id": "demo-c"
    },
    {
      "attempt_id": "demo-c-attempt",
      "event_id": "started-demo-c-attempt",
      "evidence_kind": "PHASE_EXECUTION",
      "evidence_ref": "test-started-demo-c-attempt",
      "kind": "STARTED",
      "observed_at": 1792914219.1604135,
      "task_id": "demo-c"
    },
    {
      "attempt_id": "demo-b-attempt",
      "event_id": "received-demo-b-attempt",
      "evidence_kind": "PHASE_EXECUTION",
      "evidence_ref": "test-received-demo-b-attempt",
      "kind": "RECEIVED",
      "observed_at": 1792914219.1680598,
      "task_id": "demo-b"
    },
    {
      "attempt_id": "demo-b-attempt",
      "event_id": "started-demo-b-attempt",
      "evidence_kind": "PHASE_EXECUTION",
      "evidence_ref": "test-started-demo-b-attempt",
      "kind": "STARTED",
      "observed_at": 1792914219.1680598,
      "task_id": "demo-b"
    },
    {
      "attempt_id": "demo-b-attempt",
      "event_id": "demo-b-progress",
      "evidence_kind": "TEST_RUN",
      "evidence_ref": "demo-test-run",
      "kind": "PROGRESS",
      "observed_at": 1792914219.1724398,
      "task_id": "demo-b"
    },
    {
      "attempt_id": "demo-b-attempt",
      "event_id": "terminal-demo-b-attempt",
      "evidence_kind": "TEST_RUN",
      "evidence_ref": "test-terminal-demo-b-attempt",
      "kind": "TERMINAL",
      "observed_at": 1792914219.174842,
      "task_id": "demo-b"
    },
    {
      "attempt_id": "demo-a-attempt",
      "event_id": "received-demo-a-attempt",
      "evidence_kind": "PHASE_EXECUTION",
      "evidence_ref": "test-received-demo-a-attempt",
      "kind": "RECEIVED",
      "observed_at": 1792914219.3061314,
      "task_id": "demo-a"
    },
    {
      "attempt_id": "demo-a-attempt",
      "event_id": "started-demo-a-attempt",
      "evidence_kind": "PHASE_EXECUTION",
      "evidence_ref": "test-started-demo-a-attempt",
      "kind": "STARTED",
      "observed_at": 1792914219.3061314,
      "task_id": "demo-a"
    }
  ]
};
