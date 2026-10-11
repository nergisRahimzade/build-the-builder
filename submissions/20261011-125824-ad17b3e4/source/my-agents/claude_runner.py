"""Anthropic backend for the same builder tools and completion gates."""
import dataclasses
import json
from types import SimpleNamespace

from anthropic import AsyncAnthropic
from agents.tool_context import ToolContext


@dataclasses.dataclass
class Event:
    type: str
    data: object = None
    item: object = None
    text: str = ""


def messages_for_claude(items):
    messages = []
    for item in items:
        content = item["content"]
        if isinstance(content, list):
            converted = []
            for block in content:
                kind = block.get("type")
                if kind == "input_text":
                    converted.append({"type": "text", "text": block["text"]})
                elif kind in ("input_file", "input_image"):
                    header, data = (block.get("file_data") or block["image_url"]).split(",", 1)
                    converted.append({"type": "document" if kind == "input_file" else "image",
                        "source": {"type": "base64", "media_type": header.split(":", 1)[1].split(";")[0], "data": data}})
                else:
                    converted.append(block)
            content = converted
        messages.append({"role": item["role"], "content": content})
    return messages


class ClaudeResult:
    def __init__(self, agent, input, max_turns):
        self.agent, self.messages, self.max_turns = agent, messages_for_claude(input), max_turns
        self.context_wrapper = SimpleNamespace(usage=SimpleNamespace(requests=0, total_tokens=0))

    def to_input_list(self):
        return self.messages.copy()

    async def stream_events(self):
        client = AsyncAnthropic()
        tools = {tool.name: tool for tool in self.agent.tools}
        try:
            for _ in range(self.max_turns):
                async with client.messages.stream(model=self.agent.model, max_tokens=20000,
                    system=self.agent.instructions, messages=self.messages,
                    tools=[{"name": tool.name, "description": tool.description, "input_schema": tool.params_json_schema} for tool in tools.values()],
                    tool_choice={"type": "any"}) as stream:
                    response = await stream.get_final_message()
                self.context_wrapper.usage.requests += 1
                self.context_wrapper.usage.total_tokens += response.usage.input_tokens + response.usage.output_tokens
                yield Event("raw_response_event", data=SimpleNamespace(type="response.created", response=response))
                yield Event("provider_response", data=response.model_dump())
                self.messages.append({"role": "assistant", "content": [block.model_dump() for block in response.content]})
                results, finishing = [], False
                for block in response.content:
                    if block.type == "text":
                        yield Event("builder_text", text=block.text)
                    elif block.type == "tool_use":
                        arguments = json.dumps(block.input)
                        raw = SimpleNamespace(call_id=block.id, name=block.name, arguments=arguments)
                        yield Event("run_item_stream_event", item=SimpleNamespace(type="tool_call_item", raw_item=raw))
                        context = ToolContext(context=None, tool_name=block.name, tool_call_id=block.id, tool_arguments=arguments)
                        output = await tools[block.name].on_invoke_tool(context, arguments)
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                        yield Event("run_item_stream_event", item=SimpleNamespace(type="tool_call_output_item", raw_item={"call_id": block.id}, output=output))
                        finishing = finishing or block.name == "FinishBuild"
                if results:
                    self.messages.append({"role": "user", "content": results})
                if finishing:
                    return
            raise RuntimeError("Claude builder exceeded its turn limit")
        finally:
            await client.close()
