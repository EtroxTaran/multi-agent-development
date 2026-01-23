#!/usr/bin/env python3
import json
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    command = (data.get("command") or "").strip()
    lower = command.lower()

    deny_patterns = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev/zero of=/dev/",
        "dd if=/dev/random of=/dev/",
        "shutdown",
        "reboot",
    ]

    ask_patterns = [
        "git push --force",
        "git push -f",
        "sudo ",
        "curl | sh",
        "wget | sh",
    ]

    for pattern in deny_patterns:
        if pattern in lower:
            print(
                json.dumps(
                    {
                        "permission": "deny",
                        "user_message": "Blocked dangerous command by safety hook.",
                        "agent_message": f"Blocked: {command}",
                    }
                )
            )
            return 0

    for pattern in ask_patterns:
        if pattern in lower:
            print(
                json.dumps(
                    {
                        "permission": "ask",
                        "user_message": "High-risk command detected. Confirm to proceed.",
                        "agent_message": f"High-risk command requires approval: {command}",
                    }
                )
            )
            return 0

    print(json.dumps({"permission": "allow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
