import copy
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import freya
from tools.audit_workflow import audit, compare_deployment
from tools.workflow_parts import api_tool, action_node, end_node


def workflow():
    return {"initial_node": "ask", "nodes": {
        "ask": {"node_type": "conversation", "max_node_turns": 4,
                "max_turn_transition": "end", "transitions": [{"target_node": "end"}]},
        "end": {"node_type": "end_call", "transitions": [], "terminal": {
            "type": "function", "function": {"name": "finished", "handler": "__function__:end_call",
            "parameters": {"properties": {"message_mode": {"default": "none"}}}}}}}}


class WorkflowGuardTests(unittest.TestCase):
    def test_generated_action_and_terminal_use_distinct_handlers(self):
        tool = api_tool("record", "https://mock.example/record", "POST", {"type": "object", "properties": {"id": {"type": "string", "default": "{{caller}}"}}})
        data = {"initial_node": "record", "nodes": {"record": action_node("record", tool, [], "end"), "end": end_node("end", "Goodbye")}}
        self.assertEqual(audit(data)["errors"], [])
        self.assertEqual(data["nodes"]["end"]["terminal"]["function"]["handler"], "__function__:end_call")
        self.assertEqual(tool["function"]["parameters"]["properties"]["body"]["properties"]["id"]["default"], "{{caller}}")

    def test_api_mapping_moves_to_action_node(self):
        mapping = [{"response_path": "data.ok", "variable_name": "completed"}]
        tool = api_tool("record", "https://mock.example/record", "POST", mapping=mapping)
        node = action_node("record", tool, [], "failed")
        self.assertEqual(node["response_mapping"], mapping)
        self.assertNotIn("response_mapping", node["pre_actions"][0])
        self.assertIn("response_mapping", tool)

    def test_disconnected_terminal_does_not_hide_loop(self):
        data = workflow()
        data["nodes"]["ask"] = {"node_type": "conversation", "transitions": [{"target_node": "ask"}]}
        self.assertTrue(any("no explicit path" in error for error in audit(data)["errors"]))

    def test_ineffective_cap_is_rejected(self):
        data = workflow()
        del data["nodes"]["ask"]["max_turn_transition"]
        self.assertTrue(any("does not bound retries" in error for error in audit(data)["errors"]))

    def test_silent_action_must_advance(self):
        data = workflow()
        data["nodes"]["ask"]["node_type"] = "api_request"
        self.assertTrue(any("action node needs" in error for error in audit(data)["errors"]))

    def test_valid_graph_and_removed_platform_terminal(self):
        data = workflow()
        self.assertEqual(audit(data)["errors"], [])
        remote = copy.deepcopy(data)
        del remote["nodes"]["end"]["terminal"]
        self.assertIn("Platform changed end.terminal", compare_deployment(data, remote))

    def test_server_added_defaults_are_not_lost_behavior(self):
        data = workflow()
        remote = copy.deepcopy(data)
        remote["nodes"]["end"]["terminal"]["function"]["description"] = ""
        self.assertEqual(compare_deployment(data, remote), [])

    def test_missing_identification_node_blocks_save_before_network(self):
        data = workflow()
        data["nodes"]["ask"]["transitions"] = [{"target_node": "identity_check"}]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"FREYA_ENFORCE_AUDIT": "1"}), patch.object(freya, "api") as api:
            with self.assertRaisesRegex(ValueError, "identity_check"):
                freya.save_workflow("synthetic", data, str(pathlib.Path(temp) / "state.json"))
            api.assert_not_called()
