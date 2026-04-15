# Agentic AI プロジェクト利用マニュアル

このドキュメントは、本リポジトリ（`agenticai`）の**ローカル実行方法**と、Web UI / API の基本的な使い方をまとめたものです。  
対象は「まず動かして全体像を確認したい」利用者です。

---

## 1. 前提環境

- Python: **3.12**（`Pipfile` の `python_version = "3.12"`）
- OS: macOS / Linux / Windows（Python が動けば可）

依存パッケージ例（抜粋）:

- flask
- pydantic
- pyyaml
- networkx
- langgraph
- openai

---

## 2. セットアップ

### 方法A: pipenv を使う（推奨）

```bash
pipenv install
pipenv shell
```

### 方法B: pip を使う

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. アプリ起動

トップディレクトリ（このファイルがある場所）で以下を実行します。

```bash
PYTHONPATH=src python src/run_ui.py
```

起動後、ブラウザで以下にアクセス:

- `http://127.0.0.1:5000/workflows`
- `http://127.0.0.1:5000/workflow-definitions`

`run_ui.py` はサンプルのワークフロー状態をメモリ上に作成し、Flask UI を起動します。

> 現在の `run_ui.py` は、`create_app(...)` に対して Fake サービスではなく、
> `HumanGateService` / `WorkflowExecutionService` / `RerunService` 系の実サービスを注入します。
> さらに、`data/workflow_definitions/active/` 配下の定義を読み込んでグラフを構築します
> （定義がない場合のみ `sample_workflow` をフォールバック利用）。

### OpenAI 接続（本番相当設定）

LLM ノードで OpenAI を使う場合は、`config/runtime.yaml` で設定できます。

```yaml
llm:
  provider: openai   # openai / dummy
  openai_model: gpt-4o-mini
  openai_api_key: ""
```

- `provider: openai` なら OpenAI を既定利用
- `provider: dummy` ならダミーを既定利用
- `openai_api_key` は空にして、環境変数で上書きしてもOK

環境変数は `runtime.yaml` より優先されます。必要なら起動前に以下を設定してください。

```bash
export OPENAI_API_KEY="<your_api_key>"
export OPENAI_MODEL="gpt-4o-mini"
export AGENT_PLATFORM_LLM_PROVIDER="openai"
PYTHONPATH=src python src/run_ui.py
```

- `AGENT_PLATFORM_LLM_PROVIDER`
  - `openai`: OpenAI アダプタを既定利用
  - `dummy`（既定値）: ダミー応答アダプタを既定利用
- ノード個別に `config.provider: openai` を指定した場合は、そのノードは OpenAI を優先します。

---

## 4. 主要画面（Web UI）

### 4.1 ワークフロー一覧

- `GET /workflows`
- 各 workflow のサマリーを表示

### 4.2 ノード一覧

- `GET /workflows/<workflow_id>/executions/<execution_id>/nodes`
- `?status=FAILED` のようにステータス絞り込み可能

### 4.3 ノード詳細

- `GET /workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>`
- ログ、入出力プレビュー、状態を確認

### 4.4 グラフ表示

- `GET /workflows/<workflow_id>/graph`
- Mermaid 形式でワークフロー構造を表示

### 4.5 定義エディタ

- `GET /workflow-definitions`
- `GET /workflow-definitions/new`
- `GET /workflow-definitions/<workflow_id>/edit`

ワークフロー YAML の新規作成、編集、バリデーション、複製、アーカイブ操作が可能です。

---

## 5. 主要 API

## 5.1 実行状態参照 API

- `GET /api/workflows`
- `GET /api/workflows/<workflow_id>/executions/<execution_id>/nodes`

## 5.2 実行操作 API（Actions）

- `POST /actions/workflows/<workflow_id>/run`
  - body 例: `{"global_inputs": {...}}`
- `POST /actions/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/approve`
- `POST /actions/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/reject`
- `POST /actions/workflows/<workflow_id>/executions/<execution_id>/rerun`
  - body 例: `{"from_node_id": "step3"}`

## 5.3 ワークフロー定義 API

- `GET /api/workflow-definitions`
- `GET /api/workflow-definitions/<workflow_id>`
- `POST /api/workflow-definitions/validate`

---

## 6. ワークフロー定義ファイル配置

定義ファイルは以下ディレクトリで管理されます。

- 有効: `data/workflow_definitions/active/`
- アーカイブ: `data/workflow_definitions/archived/`

`FileWorkflowDefinitionRepository` がこの2ディレクトリを読み書きします。

---

## 7. GUI実行ユースケース（2ノードの簡単な流れ）

ここでは、**2ノード構成（生成 → 人手確認）**のイメージで、GUI上でタスクを実行・確認する流れを説明します。

- ノード1: `llm_generate`（下書き作成）
- ノード2: `human_gate`（承認/差し戻し）

### 7.1 画面遷移と実行の流れ

1. ブラウザで `http://127.0.0.1:5000/workflows` を開き、対象ワークフローを選択します。  
2. 一覧画面から実行（Run）を行うと、新しい `execution_id` が発行されます。  
3. ノード一覧（`/workflows/<workflow_id>/executions/<execution_id>/nodes`）へ移動し、状態を確認します。
   - `llm_generate` が `SUCCEEDED`
   - `human_gate` が `WAITING_HUMAN`
4. `human_gate` ノード詳細画面を開き、ログや出力内容を確認します。
5. 必要に応じて以下を実行します。
   - **Approve**: 承認して後続へ進める
   - **Reject**: 差し戻し（必要なら fallback ノード指定）

### 7.2 何を確認すればよいか

- ノード一覧でステータスが期待どおり遷移しているか
- ノード詳細で `input/output/log` が業務上妥当か
- 承認/差し戻し操作のあと、一覧と詳細の表示が更新されるか

この一連の操作を通して、GUIでの「実行 → 確認 → 人手判断」の基本ループを確認できます。

---

## 8. よく使う操作例

### 8.1 ワークフローを実行する（HTTP）

```bash
curl -X POST http://127.0.0.1:5000/actions/workflows/sample_workflow/run \
  -H "Content-Type: application/json" \
  -d '{"global_inputs":{"topic":"release note"}}'
```

### 8.2 失敗ノードから再実行する

```bash
curl -X POST http://127.0.0.1:5000/actions/workflows/sample_workflow/executions/<execution_id>/rerun \
  -H "Content-Type: application/json" \
  -d '{"from_node_id":"step3"}'
```

### 8.3 定義 YAML を検証する

```bash
curl -X POST http://127.0.0.1:5000/api/workflow-definitions/validate \
  -H "Content-Type: application/json" \
  -d '{"yaml_text":"workflow_id: sample\nworkflow_name: Sample\nnodes: []\nedges: []"}'
```

---

## 9. テスト実行

```bash
PYTHONPATH=src pytest -q
```

統合テスト例:

- `tests/integration/test_phase4_flask_ui_flow.py`

---

## 10. 補足

- `src/run_ui.py` は Fake サービスではなく、実サービス（Human Gate / Rerun / Execution）を `create_app(...)` に注入する構成です。
- OpenAI を使う場合は、`OPENAI_API_KEY` と `AGENT_PLATFORM_LLM_PROVIDER=openai` を設定してください。
