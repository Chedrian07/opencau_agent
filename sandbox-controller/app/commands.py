from app.schemas import CommandRequest

SCREENSHOT_PATH = "/tmp/opencau-smoke.png"
READ_SCREENSHOT_COMMAND = ["/bin/cat", SCREENSHOT_PATH]

ALLOWED_COMMANDS: dict[str, list[str]] = {
    "healthcheck": ["/usr/local/bin/healthcheck.sh"],
    "screenshot": ["/usr/local/bin/screenshot.sh", SCREENSHOT_PATH],
    "xdotool_click_type": ["/usr/local/bin/xdotool-smoke.sh"],
}


def command_for(request: CommandRequest) -> list[str]:
    return ALLOWED_COMMANDS[request.operation]
