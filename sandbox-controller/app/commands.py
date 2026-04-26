from app.schemas import CommandRequest

ALLOWED_COMMANDS: dict[str, list[str]] = {
    "healthcheck": ["/usr/local/bin/healthcheck.sh"],
    "screenshot": ["/usr/local/bin/screenshot.sh", "/tmp/opencau-smoke.png"],
    "xdotool_click_type": ["/usr/local/bin/xdotool-smoke.sh"],
}


def command_for(request: CommandRequest) -> list[str]:
    return ALLOWED_COMMANDS[request.operation]
