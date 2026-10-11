"""Generic structural checks; business policy still requires source review and call tests."""
import argparse
import json
import pathlib
from urllib.parse import urlparse


def audit(workflow, mock_url=None):
    errors, warnings = [], []
    nodes = workflow.get("nodes", {})
    global_nodes = workflow.get("global_nodes", {})
    if not isinstance(nodes, dict) or not nodes:
        return {"errors": ["nodes must be a nonempty object"], "warnings": []}
    if not isinstance(global_nodes, dict):
        return {"errors": ["global_nodes must be an object"], "warnings": []}
    all_nodes = {**nodes, **global_nodes}
    if workflow.get("initial_node") not in nodes:
        errors.append("initial_node does not identify a regular node")
    if "agent_config" in workflow:
        errors.append("Generated workflow must omit agent_config; preserve the event model")
    for name, node in all_nodes.items():
        if node.get("node_type") == "end_call" and node.get("terminal", {}).get("function", {}).get("handler") != "__function__:end_call":
            errors.append(f"{name}: end_call node lacks an executable end_call terminal")
        if node.get("node_type") == "end_call":
            if node.get("transitions"):
                errors.append(f"{name}: end_call must not have outgoing transitions")
            props = node.get("terminal", {}).get("function", {}).get("parameters", {}).get("properties", {})
            if props.get("interruptible", {}).get("default") and not props.get("trigger_pattern_both", {}).get("default"):
                errors.append(f"{name}: interruptible hang-up without farewell patterns can repeat goodbye indefinitely")
        if node.get("max_node_turns") is not None and not node.get("max_turn_transition"):
            errors.append(f"{name}: max_node_turns without max_turn_transition does not bound retries")
        if node.get("node_type") in ("api_request", "code"):
            if not node.get("passthrough") or not node.get("passthrough_default_transition"):
                errors.append(f"{name}: action node needs passthrough and a fallback target to avoid waiting for another user turn")
        if node.get("tools") and node.get("node_type") != "conversation":
            errors.append(f"{name}: tools on a non-conversation node are stripped by Freya")
        if node.get("pre_actions") and node.get("node_type") == "conversation":
            errors.append(f"{name}: pre_actions on a conversation node are stripped by Freya")
        targets = [t.get("target_node") for t in node.get("transitions", [])]
        targets += [node.get("max_turn_transition"), node.get("passthrough_default_transition")]
        for target in filter(None, targets):
            if target not in all_nodes:
                errors.append(f"{name}: transition target does not exist: {target}")
        if node.get("node_type") == "conversation" and not node.get("transitions") and not node.get("tools"):
            warnings.append(f"{name}: no transitions or lifecycle tools; verify this node can finish")
    counts = {"steps": len(nodes), "global_steps": len(global_nodes), "tools": 0, "api_calls": 0}
    terminal_handlers = set()
    def visit(value, path="workflow"):
        if isinstance(value, dict):
            if value.get("handler") in ("__function__:end_call", "__function__:transfer_call"):
                terminal_handlers.add(value["handler"])
            if value.get("type") == "function" and isinstance(value.get("function"), dict):
                counts["tools"] += 1
            if value.get("handler") == "__function__:api_call":
                counts["api_calls"] += 1
                properties = value.get("parameters", {}).get("properties", {})
                url = properties.get("url", {}).get("default", "")
                method = properties.get("method", {}).get("default", "")
                if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    errors.append(f"{path}: API tool needs an explicit HTTP method default")
                misplaced = set(properties) - {"url", "method", "headers", "body", "connect_retries", "timeout"}
                if misplaced:
                    errors.append(f"{path}: bank request fields must be under body.properties, not transport parameters: {sorted(misplaced)}")
                if not url:
                    errors.append(f"{path}: API tool has no default URL")
                elif mock_url and "{{" not in url:
                    expected, actual = urlparse(mock_url), urlparse(url)
                    if (expected.scheme, expected.netloc) != (actual.scheme, actual.netloc):
                        errors.append(f"{path}: API tool points outside the supplied mock: {url}")
                elif "{{" in url:
                    warnings.append(f"{path}: dynamic URL needs runtime verification")
            for key, item in value.items():
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, f"{path}[{i}]")
    visit(workflow)
    # A terminal elsewhere in the document does not make a trapped branch finish.
    edges = {name: {t.get("target_node") for t in node.get("transitions", [])}
             | {node.get("max_turn_transition"), node.get("passthrough_default_transition")}
             for name, node in all_nodes.items()}
    ends = {name for name, node in all_nodes.items()
            if node.get("node_type") in ("end_call", "transfer_call", "exit", "invoke_agent")
            or any(tool.get("function", {}).get("handler") in ("__function__:end_call", "__function__:transfer_call")
                   for tool in node.get("tools", []))}
    can_finish = set(ends)
    while True:
        predecessors = {name for name, targets in edges.items() if targets & can_finish}
        if predecessors <= can_finish:
            break
        can_finish.update(predecessors)
    for name in all_nodes.keys() - can_finish:
        errors.append(f"{name}: no explicit path to executable call termination; a goodbye prompt is insufficient")
    if not terminal_handlers and not any(node.get("node_type") in ("transfer_call", "exit", "invoke_agent") for node in all_nodes.values()):
        errors.append("Workflow has no executable end/transfer/exit path; farewell text alone does not end a call")
    return {"errors": errors, "warnings": warnings, **counts,
            "limits": "Does not prove business-policy compliance, runtime code behavior or hidden-test success"}


def retains(expected, actual):
    """Allow server-added defaults, but never lost or changed submitted fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and retains(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(retains(a, b) for a, b in zip(expected, actual))
    return expected == actual


def compare_deployment(expected, actual):
    """Check that Freya retained the graph and tool bindings used by the builder."""
    errors = []
    if actual.get("initial_node") != expected.get("initial_node"):
        errors.append("Platform changed initial_node")
    for field in ("tools", "system_prompt", "context_variables"):
        if field in expected and not retains(expected[field], actual.get(field)):
            errors.append(f"Platform changed workflow.{field}")
    for group in ("nodes", "global_nodes"):
        for name, node in expected.get(group, {}).items():
            saved = actual.get(group, {}).get(name)
            if not saved:
                errors.append(f"Platform did not retain node {name}")
                continue
            if saved.get("node_type") != node.get("node_type"):
                errors.append(f"Platform changed node type for {name}")
            for field in ("terminal", "passthrough", "passthrough_default_transition", "max_node_turns", "max_turn_transition", "response_mapping", "extraction_schema", "on_enter", "task_message", "loop_prompt", "routing_prompt"):
                if field in node and not retains(node[field], saved.get(field)):
                    errors.append(f"Platform changed {name}.{field}")
            for transition in node.get("transitions", []):
                if not any(t.get("target_node") == transition.get("target_node") and retains(transition.get("condition"), t.get("condition"))
                           for t in saved.get("transitions", [])):
                    errors.append(f"Platform did not retain a transition from {name}")
            for field in ("tools", "pre_actions"):
                for tool in node.get(field, []):
                    fn = tool.get("function", {})
                    candidates = [item.get("function", {}) for item in saved.get(field, [])]
                    matching = next((item for item in candidates if item.get("name") == fn.get("name") and item.get("handler") == fn.get("handler")), None)
                    if matching is None:
                        errors.append(f"Platform did not retain {name}.{field}.{fn.get('name')}")
                    else:
                        props = fn.get("parameters", {}).get("properties", {})
                        actual_props = matching.get("parameters", {}).get("properties", {})
                        for key in ("url", "method", "body"):
                            if key in props and not retains(props[key], actual_props.get(key)):
                                errors.append(f"Platform changed {key} schema for {name}.{fn.get('name')}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow", type=pathlib.Path)
    parser.add_argument("--mock-url")
    args = parser.parse_args()
    data = json.loads(args.workflow.read_text(encoding="utf-8"))
    result = audit(data.get("workflow", data), args.mock_url)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))
