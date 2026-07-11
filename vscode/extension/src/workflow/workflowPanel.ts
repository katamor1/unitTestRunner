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
  private terminologyView?: vscode.WebviewView;

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.terminologyView = webviewView;
    super.resolveWebviewView(webviewView);
  }

  refresh(): void {
    super.refresh();
    if (this.terminologyView) {
      this.terminologyView.webview.html = applyWorkflowViewTerminology(this.terminologyView.webview.html);
    }
  }
}

export function renderWorkflowHtml(
  ...args: Parameters<typeof renderBaseWorkflowHtml>
): ReturnType<typeof renderBaseWorkflowHtml> {
  return applyWorkflowViewTerminology(renderBaseWorkflowHtml(...args));
}

function applyWorkflowViewTerminology(html: string): string {
  const previousLabel = '\u5f93\u6765';
  return html.split(previousLabel).join('詳細');
}
