// @ts-nocheck
import type { CliDiagnostic, CliProducedArtifact } from '../cli/cliEnvelope';
import type { ExecutionBlockerActionCode, HandledBlockedRunDetails } from './contracts';

export interface VerifiedBlockedRun {
  workspace: string;
  runId: string;
  count: number;
  primaryAction: ExecutionBlockerActionCode;
  primaryActionLabel: string;
  reportJson?: string;
  reportMarkdown?: string;
  reportSha256?: string;
  primarySourcePath?: string;
  publicationDiagnostics: CliDiagnostic[];
  updatedAt: string;
}

import * as crypto from 'crypto';
import * as fs from 'fs';
import { isPathInside, pathDialect, resolveReportedPath } from '../platform/pathDialect';
const ACTION_CODES = new Set([
    'open_test_input_editor',
    'open_build_probe_report',
    'generate_harness',
    'run_build_probe',
    'choose_or_build_executable',
    'open_execution_log',
    'open_execution_report',
]);
const SHA256 = /^[0-9a-f]{64}$/;
export function verifyBlockedRunArtifacts(
  workspace: string,
  details: HandledBlockedRunDetails,
  producedArtifacts: CliProducedArtifact[],
): VerifiedBlockedRun {
    const normalizedWorkspace = pathDialect(workspace).resolve(workspace);
    const diagnostics = [...details.publicationDiagnostics];
    const base = {
        workspace: normalizedWorkspace,
        runId: details.runId,
        count: details.count,
        primaryAction: details.primaryAction,
        primaryActionLabel: details.primaryActionLabel,
        updatedAt: new Date().toISOString(),
    };
    const pairs = candidatePairs(details, diagnostics);
    for (const pair of pairs) {
        try {
            const verified = verifyImmediatePair(normalizedWorkspace, details, pair, producedArtifacts);
            return {
                ...base,
                reportJson: verified.jsonPath,
                reportMarkdown: verified.markdownPath,
                reportSha256: verified.jsonSha256,
                primarySourcePath: optionalExistingContractPath(normalizedWorkspace, verified.blocker.primarySourceArtifact),
                publicationDiagnostics: deduplicateDiagnostics(diagnostics),
            };
        }
        catch (error) {
            diagnostics.push(verificationDiagnostic(`${pair.label}: ${errorMessage(error)}`));
        }
    }
    diagnostics.push(verificationDiagnostic('No complete blocker report pair could be verified.'));
    return {
        ...base,
        primarySourcePath: verifiedExecutionReportPath(normalizedWorkspace, details.runId, producedArtifacts),
        publicationDiagnostics: deduplicateDiagnostics(diagnostics),
    };
}
export function restoreLatestBlockedRun(workspace: string): VerifiedBlockedRun | undefined {
    const normalizedWorkspace = pathDialect(workspace).resolve(workspace);
    try {
        const pointerPath = resolveContainedContractPath(normalizedWorkspace, 'reports/latest_run.json');
        const pointer = parseEnvelope(readJsonRecord(pointerPath, 'latest-run pointer'), 'latest_run_pointer', 'latest-run pointer');
        const data = record(pointer.data, 'latest-run data');
        const runId = nonEmptyString(data.run_id, 'latest-run run_id');
        const updatedAt = nonEmptyString(data.updated_at, 'latest-run updated_at');
        const pointerSubject = parseSubject(pointer.subject);
        const executionReference = artifactReference(data.execution_report, 'test_execution_report', 'latest-run execution_report');
        const blockerReference = blockerReferenceValue(data.blocker_report);
        if (executionReference.path !== `runs/${runId}/test_execution_report.json`
            || blockerReference.path !== `runs/${runId}/test_execution_blockers.json`
            || blockerReference.markdownPath !== `runs/${runId}/test_execution_blockers.md`) {
            return undefined;
        }
        const executionPath = resolveContainedContractPath(normalizedWorkspace, executionReference.path);
        if (sha256(executionPath) !== executionReference.sha256) {
            return undefined;
        }
        const executionRoot = parseEnvelope(readJsonRecord(executionPath, 'execution report'), 'test_execution_report', 'execution report');
        const executionData = record(executionRoot.data, 'execution data');
        const executionFunction = record(executionData.function, 'execution function');
        if (executionFunction.status !== 'blocked') {
            return undefined;
        }
        const executionSubject = parseSubject(executionRoot.subject);
        const blockerPath = resolveContainedContractPath(normalizedWorkspace, blockerReference.path);
        const blockerHash = sha256(blockerPath);
        if (blockerHash !== blockerReference.sha256) {
            return undefined;
        }
        const blocker = parseBlockerArtifact(blockerPath);
        if (blocker.runId !== runId
            || blocker.executionReportPath !== executionReference.path
            || blocker.executionReportSha256 !== executionReference.sha256
            || !sameSubject(pointerSubject, executionSubject)
            || !sameSubject(pointerSubject, blocker.subject)) {
            return undefined;
        }
        const markdownPath = resolveContainedContractPath(normalizedWorkspace, blockerReference.markdownPath);
        const dialect = pathDialect(blockerPath);
        if (dialect.dirname(blockerPath) !== dialect.dirname(markdownPath)) {
            return undefined;
        }
        return {
            workspace: normalizedWorkspace,
            runId,
            count: blocker.count,
            primaryAction: blocker.primaryAction,
            primaryActionLabel: blocker.primaryActionLabel,
            reportJson: blockerPath,
            reportMarkdown: markdownPath,
            reportSha256: blockerHash,
            primarySourcePath: optionalExistingContractPath(normalizedWorkspace, blocker.primarySourceArtifact),
            publicationDiagnostics: [],
            updatedAt,
        };
    }
    catch {
        return undefined;
    }
}
function candidatePairs(details, diagnostics) {
    const pairs = [];
    addCandidate(pairs, diagnostics, 'latest', details.latestJson, details.latestMarkdown);
    addCandidate(pairs, diagnostics, 'history', details.runJson, details.runMarkdown);
    return pairs;
}
function addCandidate(pairs, diagnostics, label, jsonPath, markdownPath) {
    if (jsonPath === undefined && markdownPath === undefined) {
        return;
    }
    if (jsonPath === undefined || markdownPath === undefined) {
        diagnostics.push(verificationDiagnostic(`${label}: blocker report pair is incomplete.`));
        return;
    }
    pairs.push({ label, jsonPath, markdownPath });
}
function verifyImmediatePair(workspace, details, pair, producedArtifacts) {
    const jsonArtifact = exactProducedArtifact(producedArtifacts, pair.jsonPath, 'test_execution_blocker_report');
    const markdownArtifact = exactProducedArtifact(producedArtifacts, pair.markdownPath, 'test_execution_blocker_report_markdown');
    const jsonPath = resolveContainedContractPath(workspace, pair.jsonPath);
    const markdownPath = resolveContainedContractPath(workspace, pair.markdownPath);
    const jsonHash = sha256(jsonPath);
    if (jsonHash !== jsonArtifact.sha256) {
        throw new Error(`Blocker JSON hash mismatch: ${pair.jsonPath}`);
    }
    if (sha256(markdownPath) !== markdownArtifact.sha256) {
        throw new Error(`Blocker Markdown hash mismatch: ${pair.markdownPath}`);
    }
    const blocker = parseBlockerArtifact(jsonPath);
    if (blocker.runId !== details.runId
        || blocker.count !== details.count
        || blocker.primaryAction !== details.primaryAction
        || blocker.primaryActionLabel !== details.primaryActionLabel) {
        throw new Error('Blocker report does not match the CLI blocked result.');
    }
    const executionPath = resolveContainedContractPath(workspace, blocker.executionReportPath);
    if (sha256(executionPath) !== blocker.executionReportSha256) {
        throw new Error('Blocker execution-report reference hash mismatch.');
    }
    const executionRoot = parseEnvelope(readJsonRecord(executionPath, 'execution report'), 'test_execution_report', 'execution report');
    const executionData = record(executionRoot.data, 'execution data');
    const executionFunction = record(executionData.function, 'execution function');
    if (executionFunction.status !== 'blocked'
        || !sameSubject(parseSubject(executionRoot.subject), blocker.subject)) {
        throw new Error('Blocker report references a non-blocked or different execution report.');
    }
    return { jsonPath, markdownPath, jsonSha256: jsonHash, blocker };
}
function verifiedExecutionReportPath(workspace, runId, producedArtifacts) {
    const relative = `runs/${runId}/test_execution_report.json`;
    try {
        const artifact = exactProducedArtifact(producedArtifacts, relative, 'test_execution_report');
        const absolute = resolveContainedContractPath(workspace, relative);
        if (sha256(absolute) !== artifact.sha256) {
            return undefined;
        }
        const root = parseEnvelope(readJsonRecord(absolute, 'execution report'), 'test_execution_report', 'execution report');
        const data = record(root.data, 'execution data');
        const fn = record(data.function, 'execution function');
        return fn.status === 'blocked' ? absolute : undefined;
    }
    catch {
        return undefined;
    }
}
function exactProducedArtifact(artifacts, pathValue, kind) {
    const matches = artifacts.filter((item) => (item.path === pathValue && item.artifactKind === kind));
    if (matches.length !== 1) {
        throw new Error(`Expected one produced blocker artifact: ${pathValue}`);
    }
    return matches[0];
}
function parseBlockerArtifact(pathValue) {
    const root = parseEnvelope(readJsonRecord(pathValue, 'blocker report'), 'test_execution_blocker_report', 'blocker report');
    const data = record(root.data, 'blocker report data');
    if (data.execution_status !== 'blocked') {
        throw new Error('Blocker report is not for a blocked execution.');
    }
    const blockers = array(data.blockers, 'blocker report blockers');
    const count = positiveInteger(data.blocker_count, 'blocker_count');
    if (blockers.length !== count) {
        throw new Error('Blocker report count does not match its blocker array.');
    }
    const primary = record(data.primary_action, 'blocker primary_action');
    const primaryAction = actionCode(primary.code);
    const primaryActionLabel = nonEmptyString(primary.label, 'primary_action.label');
    const affectedCount = positiveInteger(primary.affected_count, 'primary_action.affected_count');
    let primaryMatches = 0;
    let primarySourceArtifact;
    blockers.forEach((raw, index) => {
        const blocker = record(raw, `blockers[${index}]`);
        const expectedId = `BLK-${String(index + 1).padStart(3, '0')}`;
        if (blocker.blocker_id !== expectedId) {
            throw new Error(`Unexpected blocker ID at index ${index}.`);
        }
        const sourceArtifact = contractPath(blocker.source_artifact, `blockers[${index}].source_artifact`);
        const recommended = record(blocker.recommended_action, `blockers[${index}].recommended_action`);
        const recommendedCode = actionCode(recommended.code);
        const recommendedLabel = nonEmptyString(recommended.label, `blockers[${index}].recommended_action.label`);
        if (recommendedCode === primaryAction) {
            if (recommendedLabel !== primaryActionLabel) {
                throw new Error('Primary action label does not match its blockers.');
            }
            primaryMatches += 1;
            primarySourceArtifact ?? (primarySourceArtifact = sourceArtifact);
        }
    });
    if (primaryMatches !== affectedCount) {
        throw new Error('Primary action affected_count does not match the blockers.');
    }
    const execution = artifactReference(data.execution_report, 'test_execution_report', 'blocker execution_report');
    return {
        runId: nonEmptyString(data.run_id, 'blocker run_id'),
        count,
        primaryAction,
        primaryActionLabel,
        executionReportPath: execution.path,
        executionReportSha256: execution.sha256,
        primarySourceArtifact,
        subject: parseSubject(root.subject),
    };
}
function parseEnvelope(root, expectedKind, name) {
    const requiredKeys = [
        'artifact_kind',
        'schema_version',
        'producer',
        'subject',
        'data',
        'extensions',
    ];
    const allowed = new Set(requiredKeys);
    if (root.artifact_kind !== expectedKind
        || root.schema_version !== '1.0.0'
        || requiredKeys.some((key) => !Object.prototype.hasOwnProperty.call(root, key))
        || Object.keys(root).some((key) => !allowed.has(key))) {
        throw new Error(`Unsupported ${name} contract.`);
    }
    record(root.producer, `${name} producer`);
    parseSubject(root.subject);
    record(root.data, `${name} data`);
    record(root.extensions, `${name} extensions`);
    return root;
}
function artifactReference(value, expectedKind, name) {
    const reference = record(value, name);
    if (reference.artifact_kind !== expectedKind) {
        throw new Error(`${name} has an invalid artifact kind.`);
    }
    return {
        path: contractPath(reference.path, `${name}.path`),
        sha256: hashValue(reference.sha256, `${name}.sha256`),
    };
}
function blockerReferenceValue(value) {
    const reference = record(value, 'latest-run blocker_report');
    if (reference.artifact_kind !== 'test_execution_blocker_report') {
        throw new Error('Latest blocker reference has an invalid artifact kind.');
    }
    return {
        path: contractPath(reference.path, 'latest-run blocker_report.path'),
        markdownPath: contractPath(reference.markdown_path, 'latest-run blocker_report.markdown_path'),
        sha256: hashValue(reference.sha256, 'latest-run blocker_report.sha256'),
    };
}
function parseSubject(value) {
    const subject = record(value, 'artifact subject');
    return {
        functionId: nonEmptyString(subject.function_id, 'subject.function_id'),
        sourcePath: contractPath(subject.source_path, 'subject.source_path'),
        sourceSha256: hashValue(subject.source_sha256, 'subject.source_sha256'),
    };
}
function sameSubject(left, right) {
    return left.functionId === right.functionId
        && left.sourcePath === right.sourcePath
        && left.sourceSha256 === right.sourceSha256;
}
function resolveContainedContractPath(workspace, relative) {
    contractPath(relative, 'blocker path');
    const absolute = resolveReportedPath(relative, workspace);
    if (!isPathInside(absolute, workspace)) {
        throw new Error(`Blocker report path escapes workspace: ${relative}`);
    }
    assertRegularFileWithoutLinks(workspace, absolute);
    const realWorkspace = fs.realpathSync.native(workspace);
    const realPath = fs.realpathSync.native(absolute);
    if (!isPathInside(realPath, realWorkspace)) {
        throw new Error(`Blocker report path resolves outside workspace: ${relative}`);
    }
    return absolute;
}
function assertRegularFileWithoutLinks(workspace, absolute) {
    const dialect = pathDialect(workspace);
    const root = dialect.resolve(workspace);
    const target = dialect.resolve(absolute);
    const relative = dialect.relative(root, target);
    let current = root;
    for (const part of relative.split(dialect.sep).filter(Boolean)) {
        current = dialect.join(current, part);
        const stat = fs.lstatSync(current);
        if (stat.isSymbolicLink()) {
            throw new Error(`Blocker report path contains a symlink or junction: ${current}`);
        }
    }
    if (!fs.statSync(target).isFile()) {
        throw new Error(`Blocker report path is not a regular file: ${target}`);
    }
}
function optionalExistingContractPath(workspace, relative) {
    if (relative === undefined) {
        return undefined;
    }
    try {
        return resolveContainedContractPath(workspace, relative);
    }
    catch {
        return undefined;
    }
}
function sha256(pathValue) {
    return crypto.createHash('sha256').update(fs.readFileSync(pathValue)).digest('hex');
}
function readJsonRecord(pathValue, name) {
    const raw = JSON.parse(fs.readFileSync(pathValue, 'utf8'));
    return record(raw, name);
}
function record(value, name) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`${name} must be an object.`);
    }
    return value;
}
function array(value, name) {
    if (!Array.isArray(value)) {
        throw new Error(`${name} must be an array.`);
    }
    return value;
}
function nonEmptyString(value, name) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`${name} must be a non-empty string.`);
    }
    return value;
}
function positiveInteger(value, name) {
    if (typeof value !== 'number' || !Number.isInteger(value) || value < 1) {
        throw new Error(`${name} must be a positive integer.`);
    }
    return value;
}
function hashValue(value, name) {
    if (typeof value !== 'string' || !SHA256.test(value)) {
        throw new Error(`${name} must be a SHA-256 value.`);
    }
    return value;
}
function contractPath(value, name) {
    if (typeof value !== 'string'
        || value.length === 0
        || value.includes('\\')
        || value.startsWith('/')
        || /^[A-Za-z]:/.test(value)
        || value.split('/').some((part) => part.length === 0 || part === '.' || part === '..')) {
        throw new Error(`${name} is not a normalized contract path.`);
    }
    return value;
}
function actionCode(value) {
    if (typeof value !== 'string' || !ACTION_CODES.has(value)) {
        throw new Error('Blocker action code is unsupported.');
    }
    return value;
}
function verificationDiagnostic(message) {
    return {
        code: 'blocker_report_verification_failed',
        severity: 'warning',
        message,
    };
}
function deduplicateDiagnostics(values) {
    const seen = new Set();
    return values.filter((item) => {
        const key = `${item.code}\0${item.severity}\0${item.message}`;
        if (seen.has(key)) {
            return false;
        }
        seen.add(key);
        return true;
    });
}
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
