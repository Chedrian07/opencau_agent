#!/usr/bin/env python3
import subprocess
import sys


def main() -> int:
    text = sys.stdin.read()
    subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)
    subprocess.run(["xdotool", "key", "ctrl+v"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
