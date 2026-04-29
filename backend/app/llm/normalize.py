from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.actions import Action

DUPLICATE_COMPACT_TYPES = frozenset({"click", "double_click", "right_click", "move", "type", "keypress"})


def _coerce_scalar(value: Any) -> Any:
    """Map vendor-specific coordinate forms (UI-TARS box, Qwen point list,
    fractional values, etc.) into a single integer when possible."""
    if value is None:
        return None
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        return int(round(value)) if -1e9 < value < 1e9 else value
    if isinstance(value, (list, tuple)):
        nums = [_coerce_scalar(v) for v in value if v is not None]
        if not nums:
            return value
        if len(nums) == 1:
            return nums[0]
        if len(nums) == 2:
            return int(round(sum(nums) / 2))
        if len(nums) == 4:
            # bbox [x1, y1, x2, y2] — caller picks x or y, return mid of axis
            return int(round((nums[0] + nums[2]) / 2))
        return int(round(sum(nums) / len(nums)))
    if isinstance(value, dict):
        for key in ("x", "y", "value"):
            if key in value:
                return _coerce_scalar(value[key])
    return value


def _bbox_to_point(bbox: Any) -> tuple[int, int] | None:
    if not isinstance(bbox, (list, tuple)) or not bbox:
        return None
    nums: list[float] = []
    for item in bbox:
        if isinstance(item, (int, float)):
            nums.append(float(item))
    if len(nums) == 2:
        return int(round(nums[0])), int(round(nums[1]))
    if len(nums) == 4:
        return int(round((nums[0] + nums[2]) / 2)), int(round((nums[1] + nums[3]) / 2))
    return None


def _scale_fractional(value: Any, axis: int) -> Any:
    if isinstance(value, float) and 0.0 <= value <= 1.0:
        return int(round(value * axis))
    if isinstance(value, int) and 0 <= value <= 1:
        return value * axis
    return value


def _maybe_extract_point(raw: dict[str, Any]) -> tuple[int, int] | None:
    if "x" in raw and "y" not in raw and isinstance(raw["x"], (list, tuple)) and len(raw["x"]) >= 2:
        try:
            return int(round(float(raw["x"][0]))), int(round(float(raw["x"][1])))
        except (TypeError, ValueError):
            pass
    if "y" in raw and "x" not in raw and isinstance(raw["y"], (list, tuple)) and len(raw["y"]) >= 2:
        try:
            return int(round(float(raw["y"][0]))), int(round(float(raw["y"][1])))
        except (TypeError, ValueError):
            pass
    for key in ("box", "bbox", "start_box", "rect"):
        point = _bbox_to_point(raw.get(key))
        if point is not None:
            return point
    for key in ("point", "pos", "position", "coordinate", "coordinates", "loc"):
        candidate = raw.get(key)
        if isinstance(candidate, dict):
            x = candidate.get("x")
            y = candidate.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return int(round(float(x))), int(round(float(y)))
        elif isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
            try:
                return int(round(float(candidate[0]))), int(round(float(candidate[1])))
            except (TypeError, ValueError):
                continue
    return None


def normalize_action(raw: dict[str, Any], *, display_width: int | None = None, display_height: int | None = None) -> Action:
    cleaned: dict[str, Any] = {}
    for key in (
        "type",
        "x",
        "y",
        "button",
        "text",
        "keys",
        "path",
        "scroll_x",
        "scroll_y",
        "duration_ms",
    ):
        if key in raw and raw[key] is not None:
            cleaned[key] = raw[key]

    point = _maybe_extract_point(raw)
    if point is not None:
        if (
            "x" not in cleaned
            or "y" not in cleaned
            or isinstance(cleaned.get("x"), (list, tuple))
            or isinstance(cleaned.get("y"), (list, tuple))
        ):
            cleaned["x"] = point[0]
            cleaned["y"] = point[1]
        else:
            cleaned.setdefault("x", point[0])
            cleaned.setdefault("y", point[1])

    for axis_key, axis_size in (("x", display_width), ("y", display_height)):
        if axis_key not in cleaned:
            continue
        value = cleaned[axis_key]
        # Lists/tuples → midpoint or single
        if isinstance(value, (list, tuple)):
            value = _coerce_scalar(value)
        # Fractional 0..1 → scale to display when known
        if axis_size and isinstance(value, float) and 0.0 <= value <= 1.0:
            value = int(round(value * (axis_size - 1)))
        elif isinstance(value, float):
            value = int(round(value))
        cleaned[axis_key] = value

    if cleaned.get("type") == "scroll" and "scroll_y" not in cleaned and "scroll_x" not in cleaned:
        cleaned["scroll_y"] = 1
    if cleaned.get("type") == "wait" and "duration_ms" not in cleaned:
        cleaned["duration_ms"] = 500
    if isinstance(cleaned.get("button"), str):
        cleaned["button"] = cleaned["button"].lower()
    if isinstance(cleaned.get("keys"), str):
        cleaned["keys"] = [cleaned["keys"]]
    return Action(**cleaned)


def _is_left_click(action: Action) -> bool:
    return action.type == "click" and (action.button is None or action.button == "left")


def _same_point(left: Action, right: Action) -> bool:
    return left.x == right.x and left.y == right.y


def _compact_duplicate_clicks(actions: list[Action]) -> list[Action]:
    compacted: list[Action] = []
    index = 0
    while index < len(actions):
        current = actions[index]
        next_action = actions[index + 1] if index + 1 < len(actions) else None
        if (
            next_action is not None
            and _is_left_click(current)
            and _is_left_click(next_action)
            and _same_point(current, next_action)
        ):
            compacted.append(Action(type="double_click", x=current.x, y=current.y))
            index += 2
            continue
        if (
            next_action is not None
            and current.type in DUPLICATE_COMPACT_TYPES
            and current.type == next_action.type
            and current.model_dump(exclude_none=True) == next_action.model_dump(exclude_none=True)
        ):
            compacted.append(current)
            index += 2
            continue
        compacted.append(current)
        index += 1
    return compacted


def _normalize_panel_launcher_clicks(
    actions: list[Action],
    *,
    display_width: int | None,
    display_height: int | None,
) -> list[Action]:
    if not display_width or not display_height:
        return actions
    panel_top = max(0, display_height - 90)
    center = display_width // 2
    normalized: list[Action] = []
    for action in actions:
        if (
            action.type == "double_click"
            and action.x is not None
            and action.y is not None
            and panel_top <= action.y <= display_height - 1
            and center - 250 <= action.x <= center + 250
        ):
            normalized.append(Action(type="click", x=action.x, y=action.y, button=action.button))
        else:
            normalized.append(action)
    return normalized


def _is_return_keypress(action: Action) -> bool:
    return action.type == "keypress" and action.keys is not None and "Return" in action.keys


def _append_return_after_url_type(actions: list[Action]) -> list[Action]:
    normalized: list[Action] = []
    for index, action in enumerate(actions):
        normalized.append(action)
        next_action = actions[index + 1] if index + 1 < len(actions) else None
        if (
            action.type == "type"
            and isinstance(action.text, str)
            and action.text.startswith(("http://", "https://"))
            and not (next_action is not None and _is_return_keypress(next_action))
        ):
            normalized.append(Action(type="keypress", keys=["Return"]))
    return normalized


def normalize_actions(
    raws: list[dict[str, Any]],
    *,
    display_width: int | None = None,
    display_height: int | None = None,
) -> list[Action]:
    actions: list[Action] = []
    for raw in raws:
        try:
            actions.append(
                normalize_action(raw, display_width=display_width, display_height=display_height)
            )
        except ValidationError as exc:
            raise ValueError(f"invalid computer action {raw}: {exc}") from exc
    compacted = _compact_duplicate_clicks(actions)
    panel_normalized = _normalize_panel_launcher_clicks(
        compacted,
        display_width=display_width,
        display_height=display_height,
    )
    return _append_return_after_url_type(panel_normalized)
