# Agentic AI USER MANUAL（全面改訂版）

本書は、現時点の実装（実行UI / 定義編集UI / 実行サービス / RAG連携 / API群）を前提に、
**「このリポジトリをローカルで運用するための実務手順」**をまとめた最新版です。

---

## 1. このプロジェクトでできること

本プロジェクトは、YAMLで定義したワークフローを以下の一連で扱えます。

1. 定義を作成・編集・検証（Graph Editor / YAML）
2. 実行（Run）
3. 実行結果を一覧・詳細で確認
4. Human Gate ノードで承認 / 差し戻し
5. 途中ノードから再実行（rerun）
6. RAGデータセットをアップロードし、ノードに紐付け

---

## 2. 前提環境

- Python **3.12**
- macOS / Linux / Windows（Python実行可能であれば可）

主要依存（抜粋）:

- Flask
- Pydantic
- PyYAML
- NetworkX
- LangGraph
- OpenAI SDK

---

## 3. セットアップ

### 3.1 pipenv（推奨）

```bash
pipenv install
pipenv shell
```

### 3.2 venv + pip

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. 起動

```bash
PYTHONPATH=src python src/run_ui.py
```

主な入口:

- `http://127.0.0.1:5000/workflows`
- `http://127.0.0.1:5000/executions`
- `http://127.0.0.1:5000/workflow-definitions`
- `http://127.0.0.1:5000/rag-datasets`

### 4.1 起動時に内部で行われること

- `data/workflow_definitions/active/` のYAMLを読み込み、検証通過したものを GraphModel 化
- 読み込み対象がない場合のみフォールバックの `sample_workflow` を使用
- 実サービスをDIしてFlask起動
  - `WorkflowExecutionService`
  - `HumanGateService`
  - `ExecutionRecordsManager`
  - `ExecutionContextManager`
  - `RAGDatasetService`
  - `RAGNodeBindingService`

---

## 5. LLMランタイム設定（runtime.yaml + 環境変数）

`config/runtime.yaml`:

```yaml
llm:
  provider: openai
  openai_model: gpt-4o-mini
  openai_api_key: ""

assessment:
  same_output_max_evaluations: 3
```

### 5.1 優先順位

環境変数 > `runtime.yaml` > デフォルト

- `AGENT_PLATFORM_LLM_PROVIDER`（`openai` / `dummy`）
- `OPENAI_MODEL`
- `OPENAI_API_KEY`
- `AGENT_PLATFORM_ASSESSMENT_SAME_OUTPUT_MAX_EVALUATIONS`

### 5.2 例

```bash
export AGENT_PLATFORM_LLM_PROVIDER=openai
export OPENAI_MODEL=gpt-4o-mini
export OPENAI_API_KEY=<your_key>
PYTHONPATH=src python src/run_ui.py
```

---

## 6. Web UI ガイド

## 6.1 実行系UI

- `/workflows` : ワークフロー一覧、Runボタン、Graph/Nodesへの導線
- `/executions` : 実行履歴一覧（workflow_id フィルタ、削除）
- `/executions/<execution_id>` : 実行詳細（ノード結果の表）
- `/workflows/<workflow_id>/executions/<execution_id>/nodes` : ノード一覧（statusフィルタ）
- `/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>` : ノード詳細
  - 入出力プレビュー
  - ログ
  - Adapter情報
  - Memory/RAGパネル
  - Event history
- `/workflows/<workflow_id>/graph` : Mermaidグラフ表示 + Run導線

## 6.2 定義編集UI

- `/workflow-definitions` : 定義一覧（archive/clone/delete）
- `/workflow-definitions/new` : 新規作成
- `/workflow-definitions/<workflow_id>/graph-editor` : Graph Editor
- `/rag-datasets` : RAGデータセット管理

Graph Editor の主要機能:

- ノード追加 / 更新 / 削除
- エッジ追加 / 置換 / 削除
- LLM task 切替（`generate` / `assessment` / `extract`）
- assessment options と routes の編集
- extract fields / output format の編集
- YAML生編集 + Validate + Save
- workflow metadata（workflow_id/workflow_name）更新

---

## 7. 実行時ノードタイプ（現行ランタイム）

`WorkflowExecutionService` のデフォルトレジストリで実行対象となるノードタイプ:

- `llm`
- `human_gate`
- `api`
- `mcp`

> 注意:
> `memory_read` / `memory_write` 等の実装ファイルは存在しますが、
> 現行のデフォルト実行レジストリには登録されていません。

---

## 8. LLMノード仕様（現行）

`llm` ノードは `config.task` により挙動が切り替わります。

- `generate` : 生成
- `assessment` : 判定（`assessment_options`, `assessment_routes` を使用可）
- `extract` : 抽出（`extract_fields`, `extract_output_format` を使用可）

### 8.1 assessment の補足

- 応答テキストから option を推定し `selected_option` を出力
- `assessment_routes` があれば `next_node` を決定
- 同一入力での評価ループ抑止として `same_output_max_evaluations` 制限を適用

### 8.2 extract の補足

- `extract_fields` を使って構造化抽出
- 出力フォーマット: `json` / `yaml` / `markdown` / `plain_text`

### 8.3 RAG / Memory（LLM内連携）

- `config.rag.profile` に紐づく retriever から hit を取得
- ノード詳細画面で rag hits を可視化
- `memory.read` / `memory.write` 設定キーは実装されていますが、
  現行の `run_ui.py` 既定構成では MemoryStore 未注入のため、そのままでは利用できません

---

## 9. Human Gate 運用

Human Gate ノード到達時:

- ノードステータス `WAITING_HUMAN`
- ワークフローステータスも待機系へ

操作API:

- Approve: 後続へ進行
- Reject: `fallback_node_id` 付き差し戻し可（または定義側 `on_reject`）

---

## 10. RAGデータセット運用

`/rag-datasets` で:

- ファイルアップロード（抽出→分割→インデックス）
- データセット一覧確認
- 削除

保持先:

- カタログ: `data/rag/datasets.json`
- 実体: `data/rag/datasets/`
- アップロード原本: `data/rag/uploads/`
- ノード紐付け: `data/rag/node_bindings.json`

Graph Editor でノードに `rag_dataset` を指定すると、実行時に `config.rag.profile` へ反映されます。

---

## 11. 主要HTTPエンドポイント

## 11.1 参照API（`/api`）

- `GET /api/workflows`
- `GET /api/workflows/<workflow_id>/executions/<execution_id>/nodes`
- `GET /api/executions`
- `GET /api/executions/<execution_id>`

定義API:

- `GET /api/workflow-definitions`
- `GET /api/workflow-definitions/<workflow_id>`
- `POST /api/workflow-definitions/validate`
- `GET /api/workflow-definitions/<workflow_id>/graph-editor-state`

## 11.2 実行操作（`/actions`）

- `POST /actions/workflows/<workflow_id>/run`
- `POST /actions/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/approve`
- `POST /actions/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/reject`
- `POST /actions/workflows/<workflow_id>/executions/<execution_id>/rerun`
- `POST /actions/executions/<execution_id>/delete`

## 11.3 定義操作（`/actions/workflow-definitions`）

- validate / create / save / clone / archive / delete
- update metadata
- add/update/delete node
- add/delete edge
- rag dataset upload/delete

---

## 12. よく使うコマンド例

### 12.1 実行開始

```bash
curl -X POST http://127.0.0.1:5000/actions/workflows/sample_workflow/run \
  -H "Content-Type: application/json" \
  -d '{"global_inputs":{"topic":"release note"}}'
```

### 12.2 ノードから再実行

```bash
curl -X POST http://127.0.0.1:5000/actions/workflows/sample_workflow/executions/<execution_id>/rerun \
  -H "Content-Type: application/json" \
  -d '{"from_node_id":"step3"}'
```

### 12.3 定義バリデーション

```bash
curl -X POST http://127.0.0.1:5000/api/workflow-definitions/validate \
  -H "Content-Type: application/json" \
  -d '{"yaml_text":"workflow_id: sample\nworkflow_name: Sample\nnodes: []\nedges: []"}'
```

---

## 13. データ配置

- 実行記録: `data/runtime/execution_records.json`
- ワークフロー定義（有効）: `data/workflow_definitions/active/`
- ワークフロー定義（アーカイブ）: `data/workflow_definitions/archived/`
- RAG関連: `data/rag/`

---

## 14. テスト

```bash
PYTHONPATH=src pytest -q
```

代表テスト:

- `tests/integration/test_phase2_runtime_flow.py`
- `tests/integration/test_phase4_flask_ui_flow.py`

---

## 15. 現状の制約・注意点

- 実行はサーバープロセス内で同期的に進む実装（外部ジョブキューではない）
- 実行可能ノードタイプはデフォルトでは `llm/human_gate/api/mcp`
- 定義に含めた全機能が常に実行レジストリへ自動登録されるわけではない
- memory機能を有効活用するには、MemoryStore を実行サービスへ注入する拡張が別途必要
- OpenAI利用時はAPIキー未設定だと実行時に失敗する可能性がある

---

## 16. クイックスタート（最短手順）

1. `PYTHONPATH=src python src/run_ui.py`
2. `/workflow-definitions` で定義を確認 or 新規作成
3. `/workflows` で Run
4. `/workflows/<workflow_id>/executions/<execution_id>/nodes` で進行確認
5. `WAITING_HUMAN` ノードがあれば approve/reject 実施
6. 必要なら `/executions` で履歴を監査
