# Explicit workflows

Open **Workspace → Workflows**. Expand **New workflow**, edit the graph, choose
**Validate**, review it, then **Start reviewed workflow**. Editing invalidates the
previous validation. Start retries reuse the request ID to prevent duplicate runs.
The dialog lists each node, its child session, deliverables and available actions.

The same operations are available from the CLI:

```bash
siling workflow validate workflow.json
siling workflow start workflow.json --request-id change-123
siling workflow list
```

Copy [the example graph](../examples/workflow.json) and replace its prompts and
absolute paths. Prepare a separate directory/worktree for every agent; nested or
shared paths are rejected, including paths reserved by unfinished workflows.
For a Git project, create worktrees from the same reviewed base:

```bash
git worktree add -b change-implement ../worktrees/implement HEAD
git worktree add -b change-test ../worktrees/test HEAD
git worktree add -b change-review ../worktrees/review HEAD
```

Use absolute paths in the JSON. A Claude workspace must also have its usual trust
accepted. SiLing reuses the existing `delegate` implementation and agent settings;
this workflow layer does not provide a filesystem sandbox. Remote-node dispatch
is not supported by this first explicit-graph runner.

`depends_on` names predecessors. IDs must be unique; unknown dependencies and
cycles fail validation. Optional `inputs` are objects with `session_id` and
`artifact_id`. Inputs are revalidated before dispatch. Direct predecessors'
outputs are included automatically. Worktree files are not copied between nodes:
produce an explicit patch, and tell the test/review nodes how to consume it.

Each child must register and report its results explicitly:

```bash
siling link-file /absolute/path/test-report.md --purpose deliverable \
  --description "Test command, outcome and evidence"
# link-file prints the artifact ID. Inside a child, ORCH_RUN_ID is used automatically.
siling workflow report WORKFLOW_ID test --artifact artifact-ID
# Failure, with no success claim:
siling workflow report WORKFLOW_ID test --failed --reason "Required checks failed"
```

Only accessible deliverables attributed to the current execution qualify. A stale
report from an earlier attempt, an inherited reference, an unverified URL, or a
missing file cannot complete a node. This validates the report's provenance and
availability; it does not independently prove every claim written by an agent.
The review and approval nodes provide the human review point.

- **Approve** records the decision and releases explicit successors. It does not
  merge, publish, or deploy anything itself.
- **Cancel node** stops only that node's verified owned child using normal graceful
  stop, then blocks downstream nodes. If stop fails, the pane remains available
  for inspection; cancellation is not reported as successful.
- **Retry node** preserves completed predecessors and prior attempt history. End
  the previous child before retrying. Completed nodes are not rerun implicitly.
- **Reconcile execution** checks a known ended child or recovers an uncertain start
  from its exact workflow/node/attempt receipt. No receipt or an ambiguous match
  requires inspection; SiLing does not guess and start a duplicate.
- **Continue ready nodes** advances pending nodes after a restart or after global
  capacity becomes available. Loading the page, reconnecting and listing workflows
  never replay commands or launch agents.

The runner permits 1–16 nodes, 1–4 concurrent nodes per workflow, and at most four
starting/running workflow nodes globally. It retains up to 100 workflow records;
there is no automatic history deletion. Native sessions survive a Dashboard
restart. A terminal ending without an explicit validated result is not success.

The runner uses a fixed, reviewed graph; it does not ask a model to plan a DAG or
recursively create subagents. Prompts instruct workers to stay within their node.
Ordinary agents still retain the tools and permissions of their existing CLI.
