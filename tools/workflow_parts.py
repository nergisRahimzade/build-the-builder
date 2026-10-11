"""Freya schema constructors. Policy, paths, values and branch choices come from input sources.

Import these from a builder-generated Python script, then json.dump the graph.
These helpers do not infer business rules, attach services automatically, or alter exports.
"""
from copy import deepcopy


def api_tool(name, url, method, body=None, mapping=None, description="", timeout_ms=30000):
    """body is a JSON Schema object from the contract, with runtime/default bindings."""
    if not url.startswith(("https://", "http://")) or method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise ValueError("Provide the actual source URL and HTTP method")
    if body is not None and (not isinstance(body, dict) or body.get("type") != "object"):
        raise ValueError("body must be an object schema, not a payload string")
    properties = {
        "url": {"type": "string", "default": url},
        "method": {"type": "string", "default": method},
        "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
    }
    if body is not None:
        properties["body"] = deepcopy(body)
    tool = {"type": "function", "config": {"timeoutMs": timeout_ms}, "function": {
        "name": name, "handler": "__function__:api_call", "description": description,
        "parameters": {"type": "object", "properties": properties}}}
    if mapping:
        tool["response_mapping"] = deepcopy(mapping)
    return tool


def end_node(name, message=""):
    """A real hang-up, independent of any bank record/close API."""
    properties = {"message_mode": {"type": "string", "default": "custom" if message else "none"}}
    if message:
        properties["spoken_message"] = {"type": "string", "default": message}
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"},
            "disable_inactivity_monitor": True, "transitions": [], "terminal": {
                "type": "function", "function": {"name": name, "handler": "__function__:end_call",
                "parameters": {"type": "object", "properties": properties}}}}


def action_node(name, tool, transitions, fallback):
    """Run an action on entry; caller supplies response-dependent routes and fallback."""
    action = deepcopy(tool)
    mapping = action.pop("response_mapping", None)
    if not fallback:
        raise ValueError("Action nodes need a fallback branch derived from the source")
    routes = deepcopy(transitions)
    if not routes or routes[-1].get("condition", {}).get("operator") != "always":
        routes.append({"target_node": fallback, "description": "Fallback after action result", "condition": {"operator": "always"}})
    node = {"name": name, "node_type": "api_request", "on_enter": {"type": "silent"},
            "passthrough": True, "passthrough_default_transition": fallback,
            "pre_actions": [action], "transitions": routes}
    if mapping:
        node["response_mapping"] = mapping
    return node
