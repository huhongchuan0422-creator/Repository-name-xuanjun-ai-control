window.XUANJUN_TWIN_DATA = {
  "anomalies": [
    {
      "anomaly_id": "dependency:delivery-node",
      "board_id": "acceptance-delivery",
      "depends_on": [
        "qa-node"
      ],
      "evidence_ref": [
        "qa-report-demo"
      ],
      "impact": "TASK_START_BLOCKED",
      "missing": "DEPENDENCY_WAIT",
      "next_action": "WAIT_DEPENDENCIES",
      "node_id": "delivery",
      "project_id": "project-demo",
      "responsible_party": "developer",
      "task_id": "delivery-node"
    }
  ],
  "boards": [
    {
      "active_count": 0,
      "blocked_count": 1,
      "board_id": "acceptance-delivery",
      "health": "BLOCKED",
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
      "active_count": 0,
      "blocked_count": 0,
      "board_id": "research-development",
      "health": "STABLE",
      "task_count": 1
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
      "attempt_id": "UNKNOWN",
      "authority_state": "NONE",
      "blocker": "DEPENDENCY_WAIT",
      "board_id": "acceptance-delivery",
      "checkpoint_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "checkpoints": [],
      "dependencies": [
        {
          "event_id": null,
          "producer_task_id": "qa-node",
          "required_evidence_ref": "qa-report-demo",
          "required_version": "accepted-v1",
          "state": "WAITING"
        }
      ],
      "epoch": null,
      "input_version": "accepted-v1",
      "module_id": "xuanjun.scheduler.kernel",
      "next_action": "WAIT_DEPENDENCIES",
      "node_id": "delivery",
      "output_version": "delivery-v1",
      "preemptible": true,
      "priority": 100,
      "project_id": "project-demo",
      "resources": [
        "fake:delivery/demo"
      ],
      "responsible_party": "developer",
      "state": "READY",
      "task_id": "delivery-node"
    },
    {
      "attempt_id": "UNKNOWN",
      "authority_state": "NONE",
      "blocker": null,
      "board_id": "research-development",
      "checkpoint_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "checkpoints": [],
      "dependencies": [],
      "epoch": null,
      "input_version": "candidate-v1",
      "module_id": "xuanjun.scheduler.kernel",
      "next_action": "CLAIM_TEST_ONLY_EXECUTOR",
      "node_id": "qa-acceptance",
      "output_version": "accepted-v1",
      "preemptible": true,
      "priority": 50,
      "project_id": "project-demo",
      "resources": [
        "fake:qa/demo"
      ],
      "responsible_party": "qa",
      "state": "READY",
      "task_id": "qa-node"
    }
  ],
  "tenant_id": "tenant-demo",
  "timeline": []
};
