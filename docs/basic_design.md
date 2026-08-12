# unitTestRunner v0.1 基本設計

active roadmapは [v0.1 redesign roadmap](v01-redesign-roadmap.md) です。本書は製品構造だけを説明し、独立したtask authorityではありません。

## 目的

VC6/C90既存Cプロジェクトの指定関数について、レビュー可能なdossierとTestSpecを作り、対応可能なsubsetだけ外部workspaceでbuild/runします。本番source treeは変更しません。

## 構成

1. Python CLI core
   - DSW/DSP、path、encoding、C sourceの代表subsetを解析
   - public artifactを生成・strict validate
   - review/build/run/reanalysis/suite gateを実行
2. external workspace
   - canonical JSONと人間向けview
   - C90/CP932/CRLF harness/build files
   - ordinary run directories
3. VS Code thin adapter
   - active resourceからtarget/settingsを解決
   - formal CLIをspawn
   - strict envelopeとartifact SHAを検証
   - 普通のreview/workflow/suite UIを提供

## Public contract

public artifactは `function_dossier`、`test_spec`、`review_record`、`build_probe_report`、`test_run_report`、`reanalysis_report`、`suite_manifest`、`suite_run_report` の8種類です。

各JSONはschema 1.0.0の4-field envelopeです。subjectはsource相対path、source SHA-256、function、project、full configurationです。Markdown、CSV、logはviewです。

CLI JSON envelopeは `command`、`outcome`、`message`、`artifacts`、`diagnostics` の5 fieldです。

## 一方向workflow

project discovery → source mapping → analysis → dossier/TestSpec → review → harness → build → explicit run の順です。

- file existenceやsaveだけでは完了しない
- current TestSpec SHAに対するapprovalだけが有効
- TestSpec変更後はreview/build/run stateを解除
- planとbuild-probeは未承認でも可
- 実runは未解決0、build成功、current approval必須
- unsupported dependency/value/oracleはreview-requiredで停止

## VC6/C90境界

- project、full configuration、source membershipが一意な場合だけ自動選択
- 0件/複数件は候補付きblocked、artifactを書かない
- project base → full configuration → source ADD/SUBTRACTでbuild context導出
- CP932、Shift-JIS、UTF-8 BOM、Windows/UNC pathを通常入力として扱う
- outputはsource root外、containment逸脱を拒否

## review/reanalysis/suite

review_recordはordinary artifact reviewです。reanalysisはcandidateとreportを作り、canonical TestSpecを自動変更しません。suiteはportable relative path、revision guard、source/TestSpec/harnessの3 SHA stale check、明示selectorだけを扱います。

## 非目標

完全C frontend、全関数自動harness、immutable proof、recursive authority、runtime review IPC、host/supply-chain provenance、hostile same-user filesystem対策、自動regression graph、高度analyticsはv0.1外です。
