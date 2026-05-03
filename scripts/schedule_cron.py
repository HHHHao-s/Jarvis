"""Manage crontab entries for Jarvis scheduled tasks."""

import subprocess
import sys
import argparse
import tempfile
import os
from datetime import datetime

JARVIS_MARKER = "# jarvis-scheduled"


def get_crontab() -> list[str]:
    result = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().split("\n")


def set_crontab(lines: list[str]) -> None:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".cron") as f:
        f.write("\n".join(lines) + "\n")
        tmp_path = f.name
    try:
        subprocess.run(["crontab", tmp_path], check=True)
    finally:
        os.unlink(tmp_path)


def cmd_add(args):
    """Add a new scheduled task."""
    schedule = args.schedule
    command = args.command
    label = args.label or f"jarvis-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    lines = get_crontab()
    # Remove empty trailing lines
    while lines and lines[-1] == "":
        lines.pop()

    entry = f"{schedule} cd {os.getcwd()} && {command}  {JARVIS_MARKER}:{label}"
    lines.append(entry)
    lines.append("")
    set_crontab(lines)
    print(f"Task '{label}' added: {schedule} -> {command}")


def cmd_list(_args):
    """List all Jarvis-managed crontab entries."""
    lines = get_crontab()
    found = False
    for line in lines:
        if JARVIS_MARKER in line:
            found = True
            schedule, rest = line.split(" cd ", 1)
            cmd_part, label_part = rest.rsplit(JARVIS_MARKER + ":", 1)
            print(f"  [{label_part}] {schedule.strip()}")
            print(f"    command: {cmd_part.strip()}")
            print()
    if not found:
        print("No Jarvis scheduled tasks found.")


def cmd_remove(args):
    """Remove a scheduled task by label."""
    label = args.label
    lines = get_crontab()
    new_lines = []
    removed = False
    for line in lines:
        if f"{JARVIS_MARKER}:{label}" in line:
            removed = True
            continue
        new_lines.append(line)
    if removed:
        set_crontab(new_lines)
        print(f"Task '{label}' removed.")
    else:
        print(f"Task '{label}' not found.")


def cmd_show(_args):
    """Show the raw crontab and a next-run estimate."""
    lines = get_crontab()
    if not lines:
        print("Crontab is empty.")
        return
    for line in lines:
        print(line)


def main():
    parser = argparse.ArgumentParser(description="Manage Jarvis crontab entries")
    sub = parser.add_subparsers(dest="action")

    p_add = sub.add_parser("add", help="Add a scheduled task")
    p_add.add_argument(
        "--schedule", "-s", default="0 9 * * *",
        help="Cron schedule expression (default: '0 9 * * *' — daily at 9am)"
    )
    p_add.add_argument(
        "--command", "-c", required=True,
        help="Command to run (from project root)"
    )
    p_add.add_argument(
        "--label", "-l",
        help="Label for this task (auto-generated if omitted)"
    )
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List Jarvis scheduled tasks")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="Remove a scheduled task")
    p_remove.add_argument("label", help="Label of the task to remove")
    p_remove.set_defaults(func=cmd_remove)

    p_show = sub.add_parser("show", help="Show raw crontab")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    if args.action is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
