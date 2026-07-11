import * as vscode from 'vscode';

import {
  WorkflowPanelProvider as BaseWorkflowPanelProvider,
  renderWorkflowHtml as renderBaseWorkflowHtml,
} from './workflowPanelBase';

export {
  SIMPLE_SECONDARY_ACTIONS,
  SIMPLE_WORKFLOW_ACTIONS,
  resolveWorkflowReports,
} from './workflowPanelBase';

export class WorkflowPanelProvider extends BaseWorkflowPanelProvider {
  refresh(): void {
    super.refresh();
    const view = (this as unknown as { view?: vscode.WebviewView }).view;
    if (view) {
      view.webview.html = applyWorkflowViewTerminology(view.webview.html);
    }
  }
}

export function renderWorkflowHtml(
  ...args: Parameters<typeof renderBaseWorkflowHtml>
): ReturnType<typeof renderBaseWorkflowHtml> {
  return applyWorkflowViewTerminology(renderBaseWorkflowHtml(...args));
}

function applyWorkflowViewTerminology(html: string): string {
  return html
    .replace('>従来</button>', '>詳細</button>')
    .replace('正式レビューや証跡確認の全工程を見る場合は従来表示に切り替えます。', '正式レビューや証跡確認の全工程を見る場合は詳細表示に切り替えます。')
    .replace('>従来パネルを表示</button>', '>詳細パネルを表示</button>');
}
