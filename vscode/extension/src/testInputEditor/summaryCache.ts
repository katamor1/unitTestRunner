import { TestInputFormClient } from './cliClient';
import { TestInputApplyResult, TestInputFormModel } from './contracts';
import { TestInputSummaryState } from '../workflow/workflowState';

export async function loadTestInputSummaryState(
  client: TestInputFormClient,
  workspace: string,
): Promise<TestInputSummaryState> {
  try {
    const model = await client.load(workspace, true);
    return readyTestInputSummaryState(workspace, model);
  } catch (error) {
    return {
      status: 'error',
      workspace,
      message: error instanceof Error ? error.message : String(error),
      updatedAt: new Date().toISOString(),
    };
  }
}

export function readyTestInputSummaryState(
  workspace: string,
  model: TestInputFormModel,
): TestInputSummaryState {
  return {
    status: 'ready',
    workspace,
    revision: model.revision,
    specSha256: model.specSha256,
    summary: model.summary,
    updatedAt: new Date().toISOString(),
  };
}


export function readyTestInputSummaryStateFromApply(
  workspace: string,
  result: TestInputApplyResult,
): TestInputSummaryState {
  return {
    status: 'ready',
    workspace,
    revision: result.revision,
    specSha256: result.specSha256,
    summary: result.summary,
    updatedAt: new Date().toISOString(),
  };
}
