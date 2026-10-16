"""Account for both isolated processes, not just the worker's own RSS/cgroup."""
from pathlib import Path
import subprocess

from gate_common import require
from korea.shadow_acceptance import sample_resources, _bounded_cgroup_path, _read_integer


def process_start_time(proc):
    fields = (Path(proc) / "stat").read_text().rsplit(") ", 1)[1].split()
    require(len(fields) >= 20, "C_BROKER_PROC_STAT")
    return int(fields[19])


def memory_identity(proc, cgroup_root):
    entries = [line.split(":", 2) for line in (Path(proc) / "cgroup").read_text().splitlines() if line]
    unified = [row[2] for row in entries if row[:2] == ["0", ""]]
    if len(unified) == 1:
        return "v2", Path(_bounded_cgroup_path(str(cgroup_root), unified[0]))
    memory = [row[2] for row in entries if len(row) == 3 and "memory" in row[1].split(",")]
    require(len(memory) == 1, "C_BROKER_MEMORY_CONTROLLER")
    return "v1", Path(_bounded_cgroup_path(str(cgroup_root), memory[0], "memory"))


class CombinedResourceSampler:
    def __init__(self, broker_pid, proc_root="/proc", cgroup_root="/sys/fs/cgroup", worker_sampler=None, peer_uid=986):
        require(type(broker_pid) is int and broker_pid > 0, "C_BROKER_PID")
        self.proc = Path(proc_root) / str(broker_pid)
        self.proc_root, self.cgroup_root = Path(proc_root), Path(cgroup_root)
        require(peer_uid in (0,986),'C_RESOURCE_PEER_ROLE');self.peer_uid=peer_uid
        self.start = process_start_time(self.proc)
        self.version, self.memory = memory_identity(self.proc, self.cgroup_root)
        worker_version, worker_memory = memory_identity(self.proc_root / "self", self.cgroup_root)
        require(worker_version == self.version and worker_memory != self.memory,
                "C_SEPARATE_PROCESS_CGROUPS_REQUIRED")
        self.worker_sampler = worker_sampler or (lambda: sample_resources(str(self.proc_root), str(self.cgroup_root)))

    def __call__(self):
        require(process_start_time(self.proc) == self.start, "C_BROKER_PID_REUSED")
        require(memory_identity(self.proc, self.cgroup_root) == (self.version, self.memory),
                "C_BROKER_CGROUP_CHANGED")
        status = {}
        for line in (self.proc / "status").read_text().splitlines():
            if ":" in line:
                name, value = line.split(":", 1); status[name] = value.split()
        require(status.get("Uid") == [str(self.peer_uid)] * 4 and "VmRSS" in status, "C_BROKER_UID_OR_RSS")
        if self.version == "v1":
            peak = _read_integer(self.memory / "memory.max_usage_in_bytes")
            oom = _read_integer(self.memory / "memory.failcnt")
            values = dict(line.split() for line in (self.memory / "memory.oom_control").read_text().splitlines())
            require("under_oom" in values, "C_BROKER_OOM_UNAVAILABLE")
            oom += int(values["under_oom"])
        else:
            peak = _read_integer(self.memory / "memory.peak")
            values = dict(line.split() for line in (self.memory / "memory.events").read_text().splitlines())
            require("oom" in values and "oom_kill" in values, "C_BROKER_OOM_UNAVAILABLE")
            oom = int(values["oom"]) + int(values["oom_kill"])
        worker = dict(self.worker_sampler())
        require(worker["cgroup_version"] == self.version and worker["cgroup_evidence_complete"] is True and
                min(peak, oom) >= 0, "C_COMBINED_RESOURCE_EVIDENCE")
        worker["rss_mib"] += int(status["VmRSS"][0]) / 1024.0
        worker["cgroup_memory_peak_mib"] += peak / 1048576.0
        worker["cgroup_oom"] += oom
        require(process_start_time(self.proc) == self.start, "C_BROKER_PID_REUSED")
        return worker


def live_sampler():
    result = subprocess.run(["/usr/bin/systemctl", "show", "xuanjun-binance-phase-c-broker.service",
                             "-p", "MainPID", "-p", "ActiveState", "-p", "SubState", "-p", "User"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5, check=True)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines())
    require(values["ActiveState"] == "active" and values["SubState"] == "running" and
            values["User"] == "xuanjun_binance", "C_BROKER_NOT_ACTIVE")
    broker=CombinedResourceSampler(int(values["MainPID"]))
    result=subprocess.run(['/usr/bin/systemctl','show','xuanjun-binance-phase-c-controller.service',
        '-p','MainPID','-p','ActiveState','-p','SubState','-p','User'],stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,text=True,timeout=5,check=True)
    values=dict(line.split('=',1) for line in result.stdout.splitlines())
    require(values['ActiveState']=='active' and values['SubState']=='running' and values['User']=='root',
            'C_SUPERVISOR_NOT_ACTIVE')
    return CombinedResourceSampler(int(values['MainPID']),worker_sampler=broker,peer_uid=0)
