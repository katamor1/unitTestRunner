import { SettingsAction, SettingsFieldId, SettingsViewModel } from '../config/settingsViewModel';

export function renderSettings(settings: SettingsViewModel): string {
  const readyLabel = settings.ready ? '設定確認は完了しています。' : '未設定の必須項目があります。';
  const openAttribute = settings.ready && settings.warnings.length === 0 ? '' : ' open';
  return `<details class="settings"${openAttribute}>
  <summary class="settings-summary">
    <h2>設定</h2>
    <span class="settings-toggle settings-collapsed-label">設定を表示</span>
    <span class="settings-toggle settings-expanded-label">設定を隠す</span>
  </summary>
  <p class="settings-ready">${escapeHtml(readyLabel)}</p>
  ${settings.fields.map(renderSettingField).join('')}
</details>`;
}

function renderSettingField(field: SettingsViewModel['fields'][number]): string {
  const value = field.effectiveValue || '未設定';
  const configured = field.configuredValue && field.configuredValue !== field.effectiveValue ? `<div class="setting-value">設定値: ${escapeHtml(field.configuredValue)}</div>` : '';
  const messages = field.messages.map((message) => `<div class="setting-message">${escapeHtml(message)}</div>`).join('');
  return `<section class="setting-field ${field.state}">
  <div class="setting-title">
    <h3>${escapeHtml(field.label)}</h3>
    <span class="setting-status">${escapeHtml(field.statusLabel)}</span>
  </div>
  <p>${escapeHtml(field.description)}</p>
  <div class="setting-value">${escapeHtml(value)}</div>
  ${configured}
  ${messages}
  <div class="actions">${field.actions.map((action) => renderSettingAction(field.id, action)).join('')}</div>
</section>`;
}

function renderSettingAction(fieldId: SettingsFieldId, action: SettingsAction): string {
  const classes = action.primary ? 'primary' : '';
  return `<button class="${classes}" data-setting-kind="${escapeAttribute(action.kind)}" data-field-id="${escapeAttribute(fieldId)}">${escapeHtml(action.label)}</button>`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttribute(value: string): string {
  return escapeHtml(value);
}
