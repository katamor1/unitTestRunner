# Unit Test Runner Phase 3 VS Code Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the VS Code adapter workspace-safe, cancellable, semantically accurate, and easy to operate for long-running legacy VC6 test workflows.

**Architecture:** Keep the Phase 0 single activation entry, route every command through one extension-wide execution coordinator, and persist a complete target/run identity in workspace state. Derive workflow progress from validated Phase 1 contracts and explicit review decisions. Present the existing detailed steps through three task-focused surfaces: Setup, Function Test, and Suite.

**Tech Stack:** TypeScript 5.4, VS Code 1.85 Extension API, Node.js child processes, Phase 1 CLI v1 envelope, Webview CSP/theme variables, `@vscode/test-electron`.

## Global Constraints

- The VS Code extension remains a thin adapter; C analysis and artifact semantics stay in Python.
- No executable command may use a path stored only in `globalState`.
- File existence controls whether a report can be opened, never whether a workflow step is complete.
- User cancellation and timeout use the already-implemented process-tree termination path.
- Product source changes are never auto-saved.
- All destructive/long-running commands display operation, function, project/configuration, output workspace, and suite count before execution.
- Webview state updates must preserve focus, expansion state, and current selection.

---

### Task 1: Persist a complete workspace-scoped target context

**Files:**

- Create: `vscode/extension/src/workflow/targetContext.ts`
- Create: `vscode/extension/src/workflow/targetContextStore.ts`
- Modify: `vscode/extension/src/extension.ts`
- Modify: `vscode/extension/src/config/settings.ts`
- Modify: `vscode/extension/src/functionTarget/regexFunctionResolver.ts`
- Create: `vscode/extension/src/test/targetContext.test.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`

**Interfaces:**

```typescript
export interface TargetContext {
  logicalTargetId: string;
  workspaceFolderUri: string;
  sourceUri: string;
  sourceRelativePath: string;
  functionId: string;
  functionName: string;
  project: string;
  configuration: string;
  outputWorkspace: string;
  revision: TargetRevision;
  latestRunId?: string;
}

export interface TargetRevision {
  sourceSha256: string;
  buildContextSha256?: string;
  testSpecRevision?: number;
  testSpecSha256?: string;
}

export interface TargetContextStore {
  read(logicalTargetId: string): TargetContext | undefined;
  write(value: TargetContext): Thenable<void>;
  active(): TargetContext | undefined;
  migrateLegacyOnce(): Thenable<void>;
}
```

- [ ] **Step 1: Write cross-workspace and same-name tests**

Open two workspace folders with the same static function name. Assert different context IDs/output paths and prove Workspace B cannot resolve Workspace A's latest output.

- [ ] **Step 2: Resolve the workspace folder from the active document**

Use `vscode.workspace.getWorkspaceFolder(document.uri)`, not the first folder. Hard-fail if the document is outside all configured roots.

- [ ] **Step 3: Build a stable target identity**

Derive immutable logical identity from workspace-folder URI, relative source, function semantic ID, project, and configuration. Store source/build/spec hashes in `revision`, not in the logical ID, so changes mark one target stale instead of creating an unrelated target. Do not use `outputRoot/functionName` alone.

- [ ] **Step 4: Move executable state to `workspaceState`**

Read legacy global keys once for migration and then clear/ignore them for command execution. Clipboard history may remain global; workspace/run paths may not.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension && npm run compile && node --test --test-name-pattern="target context|workspace" dist/test/*.test.js
git add vscode/extension/src
git commit -m "feat: scope function test context to the active workspace"
```

---

### Task 2: Add one extension-wide execution coordinator

**Files:**

- Create: `vscode/extension/src/execution/executionCoordinator.ts`
- Create: `vscode/extension/src/execution/executionEvents.ts`
- Modify: `vscode/extension/src/cli/cliRunner.ts`
- Modify: `vscode/extension/src/extension.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `vscode/extension/src/suite/suitePanel.ts`
- Modify: `vscode/extension/src/suite/suiteDashboard.ts`
- Modify: `vscode/extension/src/test/processTree.test.ts`
- Create: `vscode/extension/src/test/executionCoordinator.test.ts`

**Interfaces:**

```typescript
export interface ExecutionRequest {
  targetKey: string;
  operation: string;
  invocation: CliInvocation;
  confirm: boolean;
}

export interface ExecutionProgressEvent {
  executionId: string;
  phase: 'queued' | 'running' | 'cancelling' | 'completed';
  elapsedMs: number;
  message: string;
}

export interface ExecutionCoordinator {
  run(request: ExecutionRequest): Promise<ValidatedCliResult>;
  cancel(executionId: string): Promise<void>;
  active(targetKey?: string): readonly ActiveExecution[];
  onDidChange(listener: (event: ExecutionProgressEvent) => void): vscode.Disposable;
}

export interface CliRunOptions {
  signal?: AbortSignal;
  onStdout?: (chunk: string) => void;
  onStderr?: (chunk: string) => void;
}
```

- [ ] **Step 1: Write concurrency tests**

Start from Workflow, Command Palette, and Suite simultaneously. Assert only one process per target key; the others receive a visible busy result rather than starting.

- [ ] **Step 2: Write user-cancel process-tree tests**

Spawn a parent/child/grandchild fixture, cancel through `AbortSignal`, and assert every PID exits. Distinguish `cancelled` from `timed_out`.

- [ ] **Step 3: Stream output and progress**

Forward stdout/stderr chunks immediately to one output channel. Wrap execution in cancellable `vscode.window.withProgress`, showing function, phase, and elapsed time.

- [ ] **Step 4: Route every execution entry through the coordinator**

Quick, detailed workflow, command palette, build/test, and all suite commands use the same instance. Local `runningLabel` becomes presentation only.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension && npm run compile && node --test --test-name-pattern="process tree|execution coordinator" dist/test/*.test.js
git add vscode/extension/src
git commit -m "feat: coordinate and cancel all extension executions"
```

---

### Task 3: Add an asynchronous project/toolchain preflight

**Files:**

- Create: `vscode/extension/src/preflight/preflightService.ts`
- Create: `vscode/extension/src/preflight/preflightModels.ts`
- Modify: `vscode/extension/src/config/validation.ts`
- Modify: `vscode/extension/src/config/settingsViewModel.ts`
- Modify: `vscode/extension/src/workflow/settingsPanelRenderer.ts`
- Modify: `vscode/extension/src/extension.ts`
- Create: `vscode/extension/src/test/preflightService.test.ts`
- Modify: `vscode/extension/src/test/settingsPersistence.test.ts`

**Interfaces:**

```typescript
export type PreflightSeverity = 'ok' | 'warning' | 'blocked';

export interface PreflightCheck {
  code: string;
  severity: PreflightSeverity;
  message: string;
  action?: 'selectSourceRoot' | 'selectDsw' | 'selectOutput' | 'selectCli' | 'openLog';
}

export interface PreflightService {
  run(settings: AdapterSettings, activeDocument?: vscode.TextDocument): Promise<readonly PreflightCheck[]>;
}
```

- [ ] **Step 1: Add failing checks for unsafe/missing inputs**

Cover missing/non-file DSW, source outside root, dirty document, unwritable output, output inside source, missing CLI, CLI version failure, invalid timeout, and ambiguous project/configuration. Resolve and compare real paths using Windows case-insensitive semantics; reject junction/symlink aliases that place output at or under source root.

- [ ] **Step 2: Discover DSW and project/configuration candidates**

Use the CLI discovery commands and show explicit choices. Do not silently select the first project for multiple membership.

- [ ] **Step 3: Hard-block unsafe output roots**

`outputRoot` or Quick output under product source changes validation from warning to blocked unless a future explicitly audited override is designed. Remove unused `quickAllowExecution` and `quickReusePreviousWorkspace` settings if they still have no behavior.

- [ ] **Step 4: Handle dirty documents before analysis**

Offer Save, Use current disk revision, or Cancel. “Use current disk revision” records the disk hash in `TargetRevision`, labels the result as disk-based, and leaves the editor dirty; a later save changes the hash and makes generated artifacts stale. Never analyze editor memory while passing old disk bytes to Python without disclosure.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension && npm run compile && node --test --test-name-pattern="preflight|settings" dist/test/*.test.js
git add vscode/extension/src vscode/extension/package.json
git commit -m "feat: validate VC6 workspace and toolchain before execution"
```

---

### Task 4: Derive workflow progress from semantic artifact state

**Files:**

- Create: `vscode/extension/src/workflow/artifactStatus.ts`
- Modify: `vscode/extension/src/workflow/workflowState.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `vscode/extension/src/cli/cliEnvelope.ts`
- Modify: `vscode/extension/src/cli/cliResultParser.ts`
- Modify: `vscode/extension/src/reports/reportPathResolver.ts`
- Modify: `vscode/extension/src/test/workflowPanel.test.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`

**Interfaces:**

```typescript
export type ArtifactState = 'absent' | 'fresh' | 'stale' | 'invalid';
export type ReviewState = 'not_reviewed' | 'changes_requested' | 'approved' | 'stale';
export type ExecutionLifecycle = 'idle' | 'queued' | 'running' | 'finished';
export type RunOutcome = 'planned' | 'passed' | 'failed' | 'blocked' | 'inconclusive' | 'cancelled' | 'timed_out' | 'error';

export interface WorkflowCheckpoint {
  artifact: ArtifactState;
  review: ReviewState;
  lifecycle: ExecutionLifecycle;
  outcome: RunOutcome;
  reasons: readonly string[];
}
```

- [ ] **Step 1: Replace file-existence completion tests**

Create cases where a failed, not-run, stale, schema-invalid, or unapproved report file exists. None may advance the corresponding checkpoint.

- [ ] **Step 2: Remove save-driven approval**

Delete `completeAwaitingSaveIfMatches()` from approval flow and stop using text-document save events to mark review complete.

- [ ] **Step 3: Derive checkpoint state from validated contracts**

Use produced artifact hash/status, `review_decisions.json`, build outcome, execution verdict, and evidence integrity. Use `existsSync` only before opening a path.

- [ ] **Step 4: Compress the default user journey**

Show five standard stages: Setup -> Design review -> Build -> Execute -> Approve. Keep the detailed internal steps available under Detailed mode without changing semantic state.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension && npm run compile && node --test --test-name-pattern="workflow|artifact state|review" dist/test/*.test.js
git add vscode/extension/src
git commit -m "feat: derive workflow progress from validated outcomes"
```

---

### Task 5: Add canonical test-spec and review-decision UI

**Files:**

- Create: `vscode/extension/src/testSpec/testSpecPanel.ts`
- Create: `vscode/extension/src/testSpec/testSpecViewModel.ts`
- Create: `vscode/extension/src/review/reviewDecisionPanel.ts`
- Create: `vscode/extension/src/review/reviewViewModel.ts`
- Modify: `vscode/extension/src/cli/commandBuilder.ts`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `vscode/extension/package.json`
- Create: `vscode/extension/src/test/testSpecPanel.test.ts`
- Create: `vscode/extension/src/test/reviewDecisionPanel.test.ts`

**Interfaces:**

```typescript
export interface TestSpecCaseEdit {
  specId: string;
  expectedRevision: number;
  caseId: string;
  inputs: readonly TypedValueEdit[];
  state: readonly TypedValueEdit[];
  dependencies: readonly DependencyOverrideEdit[];
  oracles: readonly OracleEdit[];
}

export interface ReviewDecisionEdit {
  reviewId: string;
  expectedRevision: number;
  resolution: 'approved' | 'changes_requested' | 'waived' | 'open';
  reviewer: string;
  rationale: string;
}
```

- [ ] **Step 1: Render typed inputs and unresolved items without editing exports**

The panel reads `test_spec.json` through the CLI, groups cases by coverage, and clearly labels unresolved/blocking fields. CSV/Markdown actions are “Export/Open view”.

- [ ] **Step 2: Save through version-checked CLI commands**

No direct unvalidated JSON writes from the Webview. Send `expectedRevision`; display a conflict diff when another change won.

- [ ] **Step 3: Record explicit review decisions**

Require reviewer and rationale for waiver/changes requested. Show artifact revision/hash and stale decisions.

- [ ] **Step 4: Add dependency-policy editing in the same case context**

Expose per-call configured/resolved mode and evidence from the already-merged dependency-policy contract. Do not duplicate policy inference in TypeScript.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension && npm run compile && node --test --test-name-pattern="test spec|review decision" dist/test/*.test.js
git add vscode/extension/src vscode/extension/package.json
git commit -m "feat: edit canonical test specs and reviews in VS Code"
```

---

### Task 6: Complete accessibility, focus retention, and Extension Host E2E

**Files:**

- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts`
- Modify: `vscode/extension/src/suite/suitePanel.ts`
- Modify: `vscode/extension/src/suite/suiteDashboard.ts`
- Modify: `vscode/extension/src/test/extensionHost/index.ts`
- Create: `vscode/extension/src/test/accessibilityMarkup.test.ts`
- Create: `vscode/extension/src/test/workflowExtensionHost.test.ts`

**Interfaces:** Webview controls expose accessible names/state and restore a stable focus key after model refresh.

- [ ] **Step 1: Add markup tests**

Require checkbox labels/`aria-label`, `aria-pressed` on mode toggles, disabled reasons, status text in addition to color, and a focus key for interactive elements.

- [ ] **Step 2: Preserve focus and expansion state**

Prefer targeted state messages over replacing all HTML. When replacement is necessary, capture and restore focus/scroll/expanded sections.

- [ ] **Step 3: Add keyboard-only Extension Host flow**

Exercise Setup -> Quick design -> open test spec -> record review -> build confirmation -> cancel. Assert no command throws and state survives panel reopen.

- [ ] **Step 4: Add activation and multi-root E2E**

Activate the packaged entry, verify all contributed commands, run with two workspace folders, and assert active-document folder selection.

- [ ] **Step 5: Run and commit**

```bash
cd vscode/extension
npm test
npm run test:extension-host
git add vscode/extension/src
git commit -m "test: verify accessible and workspace-safe extension workflows"
```

---

## Phase 3 Completion Check

- [ ] One activation entry and one registration per command remain true.
- [ ] No executable path is sourced only from global state.
- [ ] Multi-root targets follow the active document.
- [ ] Preflight blocks dirty/source-outside-root/unsafe-output/ambiguous-context errors.
- [ ] All command surfaces share one coordinator and one output stream.
- [ ] User cancel and timeout leave no descendant process.
- [ ] Workflow completion uses semantic contracts, not file existence or save events.
- [ ] Test spec and review edits use revision-checked CLI operations.
- [ ] Focus, expansion state, labels, and keyboard operation pass Extension Host QA.
