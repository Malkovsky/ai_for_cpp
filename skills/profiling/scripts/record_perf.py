#!/usr/bin/env python3
"""Record a native workload and export perf text; HTML is a separate opt-in."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile


SCRIPT_FIELDS = "comm,pid,time,period,event,ip,sym,symoff,dso"


def run_capture(command, env, log, timeout):
    """Stop the complete workload process group on interruption or timeout."""
    with subprocess.Popen(
        command, env=env, stdout=log, stderr=log, start_new_session=True
    ) as process:
        try:
            returncode = process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        if returncode:
            raise subprocess.CalledProcessError(returncode, command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--perf-bin", default="perf")
    parser.add_argument("--cpu", type=int, default=0)
    parser.add_argument("--event", default="cycles:u")
    parser.add_argument("--frequency", type=int, default=999)
    parser.add_argument("--call-graph", default="dwarf,4096")
    parser.add_argument(
        "--control-prefix", help="Workload's PREFIX_CTL/PREFIX_ACK variables"
    )
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply the workload after --")
    if args.frequency <= 0 or args.timeout <= 0:
        parser.error("Frequency and timeout must be positive")
    if args.cpu < 0:
        parser.error("CPU must be non-negative")
    if args.control_prefix and not re.fullmatch(
        r"[A-Za-z_][A-Za-z_0-9]*", args.control_prefix
    ):
        parser.error("Invalid environment-variable prefix")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "perf.data").exists():
        parser.error("Output already contains perf.data; use a fresh directory")
    executable = shutil.which(command[0])
    if executable is None:
        parser.error(f"Workload executable not found: {command[0]}")
    binary = Path(executable).resolve()
    metadata = {
        "command": command,
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "cpu": args.cpu,
        "event": args.event,
        "frequency_hz": args.frequency,
        "call_graph": args.call_graph,
        "scope": "workload-controlled FIFO; verify phase/query counts"
        if args.control_prefix
        else "whole command, including setup",
    }
    env = dict(os.environ)
    # /tmp rather than the output directory: some mounted filesystems lack FIFOs.
    with tempfile.TemporaryDirectory(prefix="perf-control-") as temporary:
        record = [
            args.perf_bin,
            "record",
            "-e",
            args.event,
            "-F",
            str(args.frequency),
            "--call-graph",
            args.call_graph,
            "-o",
            str(out / "perf.data"),
        ]
        if args.control_prefix:
            ctl, ack = Path(temporary) / "ctl", Path(temporary) / "ack"
            os.mkfifo(ctl)
            os.mkfifo(ack)
            env[args.control_prefix + "_CTL"] = str(ctl)
            env[args.control_prefix + "_ACK"] = str(ack)
            record += ["-D", "-1", f"--control=fifo:{ctl},{ack}"]
        record += ["--", "taskset", "-c", str(args.cpu), *command]
        metadata["record_command"] = record
        (out / "capture.json").write_text(json.dumps(metadata, indent=2) + "\n")
        with (out / "record.log").open("w") as log:
            run_capture(record, env, log, args.timeout)
    commands = {
        "perf.script": [
            args.perf_bin,
            "script",
            "-i",
            str(out / "perf.data"),
            "--ns",
            "--inline",
            "-F",
            SCRIPT_FIELDS,
        ],
        "report.txt": [
            args.perf_bin,
            "report",
            "-i",
            str(out / "perf.data"),
            "--stdio",
            "--no-children",
        ],
    }
    for filename, command_line in commands.items():
        with (out / filename).open("w") as stream:
            subprocess.run(
                command_line, stdout=stream, check=True, timeout=args.timeout
            )
    report = (out / "report.txt").read_text()
    lost = re.search(r"Total Lost Samples:\s*(\d+)", report)
    metadata["lost_samples"] = int(lost[1]) if lost else None
    metadata["export_commands"] = commands
    (out / "capture.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Capture and text reports: {out}")
    if metadata["lost_samples"]:
        print(f"Warning: {metadata['lost_samples']} lost samples")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"perf capture failed: {error}; inspect record.log") from error
