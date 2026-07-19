import { pathDialect } from '../platform/pathDialect';
import { TestInputSummaryState, WorkflowState } from '../workflow/workflowState';

export function currentTestInputWorkspace(state: WorkflowState): string | undefined {
  return state.outputWorkspace || state.reports?.workspace;
}

export function applyTestInputSummaryForWorkspace(
  state: WorkflowState,
  requestedWorkspace: string,
  summary: TestInputSummaryState,
): WorkflowState {
  const current = currentTestInputWorkspace(state);
  if (
    !current
    || !sameWorkspace(current, requestedWorkspace)
    || !sameWorkspace(summary.workspace, requestedWorkspace)
  ) {
    return state;
  }
  return {
    ...state,
    testInputSummary: summary,
    updatedAt: new Date().toISOString(),
  };
}

export function clearTestInputSummaryForWorkspace(
  state: WorkflowState,
  requestedWorkspace: string,
): WorkflowState {
  const current = currentTestInputWorkspace(state);
  if (!current || !sameWorkspace(current, requestedWorkspace)) {
    return state;
  }
  if (!state.testInputSummary) {
    return state;
  }
  const { testInputSummary: _removed, ...remaining } = state;
  return {
    ...remaining,
    updatedAt: new Date().toISOString(),
  };
}

export function sameTestInputWorkspace(left: string, right: string): boolean {
  return sameWorkspace(left, right);
}

function sameWorkspace(left: string, right: string): boolean {
  const leftDialect = pathDialect(left);
  const rightDialect = pathDialect(right);
  if (leftDialect !== rightDialect) {
    return false;
  }
  const leftValue = leftDialect.resolve(left);
  const rightValue = rightDialect.resolve(right);
  if (leftDialect.sep === '\\') {
    return leftValue.toLowerCase() === rightValue.toLowerCase();
  }
  return leftValue === rightValue;
}
