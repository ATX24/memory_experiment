// OpenAI-compatible chat turn served by the authenticated Claude Code CLI via
// BAML's claude_code.ClaudeCodeClient. The Python host (server.py) owns the
// socket; this function owns one model turn:
//   OpenAI request JSON  ->  ClaudeCodeClient.invoke  ->  OpenAI response JSON
// Tool calls are not executed here: they are returned to the caller as
// `tool_calls`, exactly like a hosted chat-completions endpoint.

function chat_turn(req_json: string, model: string, timeout_ms: int) -> string {
  let req = baml.json.parse(req_json);
  let messages = baml.json.path_or<json[]>(req, ".messages", []);
  let tool_defs = baml.json.path_or<json[]>(req, ".tools", []);

  // ---- system prompt ----
  let system_parts: string[] = [];
  for (let m in messages) {
    if (baml.json.path_or<string>(m, ".role", "") == "system") {
      system_parts.push(baml.json.path_or<string>(m, ".content", ""));
    };
  }
  let system_text = system_parts.join("\n\n");
  let render = (of: ai.OutputFormat) -> ai.Prompt { ai.internal.assemble_prompt([system_text], []) };

  // ---- journal: user / assistant(+tool_calls) / tool messages ----
  let events: ai.events.Event[] = [];
  for (let m in messages) {
    let role = baml.json.path_or<string>(m, ".role", "");
    if (role == "user") {
      events.push(ai.events.UserMessage.new(baml.json.path_or<string>(m, ".content", "")));
    } else if (role == "assistant") {
      let blocks: ai.content.ModelBlock[] = [];
      let text = baml.json.path_or<string?>(m, ".content", null);
      if let t: string = text {
        if (t.length() > 0) { blocks.push(ai.content.Text { text: t }); };
      };
      for (let c in baml.json.path_or<json[]>(m, ".tool_calls", [])) {
        let raw_args = baml.json.path_or<string>(c, ".function.arguments", "{}");
        let parsed = baml.json.from_string<map<string, unknown>>(raw_args) catch_all (e) {
          _ => { let empty: map<string, unknown> = {}; empty },
        };
        blocks.push(ai.content.ToolUse {
          id: baml.json.path_or<string>(c, ".id", "call"),
          name: baml.json.path_or<string>(c, ".function.name", ""),
          args: parsed,
        });
      }
      events.push(ai.events.AssistantMessage { content: blocks, client_id: "claude-code" });
    } else if (role == "tool") {
      events.push(ai.events.ToolCompleted.new(
        baml.json.path_or<string>(m, ".tool_call_id", ""),
        baml.json.path_or<string>(m, ".content", ""),
      ));
    };
  }
  let journal = ai.Journal { log: events };

  // ---- toolbox from OpenAI function definitions (handlers never run here) ----
  let tools: ai.tools.Tool[] = [];
  for (let t in tool_defs) {
    let schema = baml.json.from_json<map<string, unknown>>(
      baml.json.path_or<json>(t, ".function.parameters", {"type": "object"}),
    );
    tools.push(ai.tools.raw_tool(
      baml.json.path_or<string>(t, ".function.name", ""),
      baml.json.path_or<string>(t, ".function.description", ""),
      schema,
      (a: map<string, unknown>) -> string { "" },
    ));
  }
  let toolbox = ai.tools.Toolbox.new(tools);

  let cc = claude_code.ClaudeCodeClient.new(model = model, timeout_ms = timeout_ms);
  let turn = cc.invoke(ai.ModelTurnInput {
    prompt: render,
    journal: journal,
    toolbox: toolbox,
    output_type: reflect.Type.of<string>(),
  });

  // ---- OpenAI response ----
  let tool_calls: json[] = [];
  let text_out: string[] = [];
  for (let b in turn.content) {
    match (b) {
      let t: ai.content.Text => {
        // the final outcome arrives JSON-encoded (output_type is string)
        let unq = baml.json.from_string<string>(t.text) catch_all (e) { _ => t.text };
        text_out.push(unq);
      },
      let c: ai.content.ToolUse => {
        tool_calls.push({
          "id": c.id,
          "type": "function",
          "function": { "name": c.name, "arguments": baml.json.stringify(baml.json.to_json(c.args)) },
        });
      },
      _ => { null },
    };
  }
  let finish = if (tool_calls.length() > 0) { "tool_calls" } else { "stop" };
  let message: map<string, json> = { "role": "assistant", "content": text_out.join("\n") };
  if (tool_calls.length() > 0) { let _ = message.set("tool_calls", tool_calls); };
  let usage: map<string, json> = {
    "prompt_tokens": turn.usage?.input_tokens ?? 0,
    "completion_tokens": turn.usage?.output_tokens ?? 0,
    "total_tokens": (turn.usage?.input_tokens ?? 0) + (turn.usage?.output_tokens ?? 0),
    "prompt_tokens_details": { "cached_tokens": turn.usage?.cached_input_tokens ?? 0 },
  };
  let resp: map<string, json> = {
    "object": "chat.completion",
    "model": model,
    "choices": [{ "index": 0, "message": baml.json.to_json(message), "finish_reason": finish }],
    "usage": baml.json.to_json(usage),
  };
  baml.json.stringify(baml.json.to_json(resp))
}
