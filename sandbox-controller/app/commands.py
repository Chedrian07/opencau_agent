from app.schemas import CommandRequest

SCREENSHOT_PATH = "/tmp/opencau-smoke.png"
LATEST_SCREENSHOT_PATH = "/tmp/opencau-action.png"
READ_SCREENSHOT_COMMAND = ["/bin/cat", SCREENSHOT_PATH]
READ_LATEST_SCREENSHOT_COMMAND = ["/bin/cat", LATEST_SCREENSHOT_PATH]
AGENT_ACTION_BIN = "/usr/local/bin/agent_action.py"

ALLOWED_COMMANDS: dict[str, list[str]] = {
    "healthcheck": ["/usr/local/bin/healthcheck.sh"],
    "screenshot": ["/usr/local/bin/screenshot.sh", SCREENSHOT_PATH],
    "xdotool_click_type": ["/usr/local/bin/xdotool-smoke.sh"],
}


def command_for(request: CommandRequest) -> list[str]:
    return ALLOWED_COMMANDS[request.operation]


def agent_action_command(action_json: str) -> list[str]:
    return [AGENT_ACTION_BIN, action_json]
