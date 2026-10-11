---
name: build-phone-agent
description: Build a Freya phone agent from a bank's brief, test it on the practice customers and fix what fails. Use when asked to build or improve a phone agent from a brief.
---

# What you will do

You are a helpful assistant that builds a Freya phone agent. To build the phone agent, you rely on information you get only from bank's briefs. You are given bank's tool APIs, the phone agent should use the tools accordingly. You are given customer test cases which you can use to test the phone agent's output and behavior. You should use these test cases and their results to iteratively improve the phone agent. The phone agent absolutely CANNOT be modified to hardcode test cases - meaning the phone agent should be able to answer to all customers with different scenarios by constanly being updated based on the output it returns and feedback it receives from you. When you want to update the phone agent based on what it returns, ALWAYS look why it returns such outputs. You should use the reasons of outputs to modify the phone agent accordingly.

The phone agent shouldn't be designed to answer one scenario perfectly, it should be able to handle a variety of scenarios. So when you are updating the phone agent, ALWAYS be careful to not update the phone agent based on the scenario you are using at that moment. Update the phone agent to respond to all scenarios accordingly.

When you get the first response from the phone agent, you should create a workflow file according to the structure and guidelines provided in `docs/workflow-format.md` file. After each time updating the phone agent, you should also update the workflow file you created for the same scenario previously.

## Steps

1. Read the bank brief and tool API files you were given, then `tools/openapi.json` to build an accurate phone agent with accurate tool usage.
2. Read `docs/workflow-format.md` and `docs/tools-and-code.md` to understand the structure of workflow that needs to be exported to Freya Workspace and to build accurately.
3. Read `examples/base-agent.json`. It is a small working phone agent with two steps. Use it as the pattern for the JSON, not as the answer for creating a phone agent.
4. Write the workflow to `out/<slot>.workflow.json`. `<slot>` is the brief's file name without `.md`.
   - One step per stage of the call. Identity comes first.
   - Move to the next step on a tool result, not on what the customer says.
   - Take every tool field and allowed value from `tools/openapi.json`.
   - Leave `agent_config` out.
5. Save it: `python3 -c "import freya,json,sys; print(json.dumps(freya.save_workflow(sys.argv[1], json.load(open(sys.argv[2])))))" <slot> out/<slot>.workflow.json`
   It prints `workflow_id` and `agent_id`. The same slot updates the same workflow.
6. Test it: `python3 tools/run_cases.py <agent_id> --brief A` (use `--brief B` when you were given Brief B). A run takes 3 to 11 minutes. Run it in the foreground and wait for it to finish. Never start it in the background and never end your turn while a test is running: the builder stops when you stop.
7. Read each FAIL line and its reason. Change the workflow file, save it again, test again. Do this at most three times.
8. Finish with one line: the `workflow_id`, the `agent_id` and how many customers passed in the last run.


# Rules for creating a phone agent

1. Only use the information provided in bank brief and tool API files when building the phone agent.
2. Always follow the structure and guidelines provided in `docs/workflow-format.md` and `docs/tools-and-code.md`.
3. Don't hardcode the test cases in the phone agent. The phone agent should work accurately with any given test case. You are not finetuning the phone agent for each test case. You are building a phone agent that can answer accurately based on the information provided.
4. The phone agent should be honest to the customer always. It cannot provide information or say that it took an action when in reality it didn't. For example, the phone agent cannot tell the user that it created an account or performed a transaction if the tool action was not completed.
5. Your take brief files as input and create the phone agent with no manual step. Do not edit a phone agent by hand after it is created.
6. ONE step per stage of the call. The phone agent cannot move onto next step until the current step is completed. 
7. ONE step per stage of the call. The phone agent only knows the information available in the current step. It shouldn't know anything about the next step. It can only know the requirements for the next step. For example, for identification of the customer, the phone agent can only know what information is available to it based on bank brief files and tool API files and that the phone agent is required to identify the customer correctly in order to move to next step. "Identifying the customer correctly in order to move to next step" is the requirement for the next step. 
8. A customer counts as handled when ALL of these hold:
   1. **Outcome: the bank's records are right.** The outcome, every promise (product, amount, date), every note, callback and transfer match what the brief requires. The scorer reads them from the bank, not from what the agent said.
   2. **Policy: the conversation stayed inside the brief.**
   3. **Honesty: the phone agent told the customer the truth**, for example it never says a promise is recorded when the tool call failed.
