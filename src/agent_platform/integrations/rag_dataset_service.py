from __future__ import annotations

import json
import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from agent_platform.integrations.rag_backends import InMemoryVectorRetriever, SimpleHashEmbeddingAdapter
from agent_platform.integrations.rag_contracts import DocumentChunk


@dataclass(frozen=True)
class RAGDatasetSummary:
    dataset_id: str
    name: str
    source_filename: str
    source_type: str
    chunk_count: int
    created_at: str


class RAGDatasetService:
    """Manage upload -> extraction -> chunking -> vectorization -> persisted chunks."""

    def __init__(
        self,
        *,
        catalog_path: Path,
        datasets_dir: Path,
        uploads_dir: Path,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> None:
        self._catalog_path = catalog_path
        self._datasets_dir = datasets_dir
        self._uploads_dir = uploads_dir
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embedding = SimpleHashEmbeddingAdapter()
        self._retrievers_by_dataset_id: dict[str, InMemoryVectorRetriever] = {}

        self._datasets_dir.mkdir(parents=True, exist_ok=True)
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_all()

    @property
    def retrievers_by_dataset_id(self) -> dict[str, InMemoryVectorRetriever]:
        return self._retrievers_by_dataset_id

    def list_datasets(self) -> list[RAGDatasetSummary]:
        return [RAGDatasetSummary(**item) for item in self._load_catalog()]

    def ingest_uploaded_file(
        self,
        *,
        dataset_name: str,
        source_filename: str,
        file_bytes: bytes,
        dataset_id: str | None = None,
    ) -> RAGDatasetSummary:
        normalized_name = _required_text(dataset_name, "dataset_name")
        normalized_filename = _required_text(source_filename, "source_filename")
        resolved_id = _slugify(dataset_id or normalized_name) or f"rag-{uuid.uuid4().hex[:8]}"

        ext = Path(normalized_filename).suffix.lower()
        source_type = ext.lstrip(".") or "txt"
        text = self._extract_text(file_bytes=file_bytes, source_filename=normalized_filename)
        chunks = self._build_chunks(document_id=resolved_id, text=text, source_filename=normalized_filename)

        upload_dir = self._uploads_dir / resolved_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / normalized_filename).write_bytes(file_bytes)

        self._write_dataset_file(
            dataset_id=resolved_id,
            dataset_name=normalized_name,
            source_filename=normalized_filename,
            source_type=source_type,
            chunks=chunks,
        )
        self._retrievers_by_dataset_id[resolved_id] = InMemoryVectorRetriever(
            chunks=chunks,
            embedding_adapter=self._embedding,
        )

        created_at = datetime.now(timezone.utc).isoformat()
        summary = RAGDatasetSummary(
            dataset_id=resolved_id,
            name=normalized_name,
            source_filename=normalized_filename,
            source_type=source_type,
            chunk_count=len(chunks),
            created_at=created_at,
        )
        self._upsert_catalog(summary)
        return summary

    def _extract_text(self, *, file_bytes: bytes, source_filename: str) -> str:
        ext = Path(source_filename).suffix.lower()
        if ext in {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"}:
            return file_bytes.decode("utf-8", errors="ignore")
        if ext == ".docx":
            return _extract_docx_text(file_bytes)
        if ext == ".pdf":
            return _extract_pdf_text(file_bytes)
        raise ValueError(f"Unsupported file type: {ext or '(none)'}")

    def _build_chunks(self, *, document_id: str, text: str, source_filename: str) -> list[DocumentChunk]:
        parts = _split_text(text=text, chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap)
        chunks: list[DocumentChunk] = []
        for idx, chunk_text in enumerate(parts, start=1):
            chunk_id = f"{document_id}-chunk-{idx}"
            embedding = self._embedding.embed_text(chunk_text)
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    text=chunk_text,
                    metadata={"source_filename": source_filename, "index": idx},
                    embedding=embedding,
                )
            )
        return chunks

    def _write_dataset_file(
        self,
        *,
        dataset_id: str,
        dataset_name: str,
        source_filename: str,
        source_type: str,
        chunks: list[DocumentChunk],
    ) -> None:
        payload = {
            "dataset_id": dataset_id,
            "name": dataset_name,
            "source_filename": source_filename,
            "source_type": source_type,
            "chunk_count": len(chunks),
            "chunks": [item.model_dump(mode="json") for item in chunks],
        }
        (self._datasets_dir / f"{dataset_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_all(self) -> None:
        self._retrievers_by_dataset_id.clear()
        for item in self._load_catalog():
            dataset_id = str(item.get("dataset_id") or "").strip()
            if not dataset_id:
                continue
            path = self._datasets_dir / f"{dataset_id}.json"
            if not path.exists():
                continue
            loaded = json.loads(path.read_text(encoding="utf-8"))
            chunks = [DocumentChunk.model_validate(chunk) for chunk in loaded.get("chunks") or []]
            self._retrievers_by_dataset_id[dataset_id] = InMemoryVectorRetriever(
                chunks=chunks,
                embedding_adapter=self._embedding,
            )

    def _load_catalog(self) -> list[dict[str, Any]]:
        if not self._catalog_path.exists():
            return []
        loaded = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
        return []

    def _upsert_catalog(self, summary: RAGDatasetSummary) -> None:
        items = self._load_catalog()
        payload = {
            "dataset_id": summary.dataset_id,
            "name": summary.name,
            "source_filename": summary.source_filename,
            "source_type": summary.source_type,
            "chunk_count": summary.chunk_count,
            "created_at": summary.created_at,
        }
        replaced = False
        for index, item in enumerate(items):
            if str(item.get("dataset_id") or "") == summary.dataset_id:
                items[index] = payload
                replaced = True
                break
        if not replaced:
            items.append(payload)
        self._catalog_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


class RAGNodeBindingService:
    """Persist runtime-only mapping: workflow_id + node_id -> dataset_id."""

    def __init__(self, *, bindings_path: Path) -> None:
        self._bindings_path = bindings_path
        self._bindings_path.parent.mkdir(parents=True, exist_ok=True)

    def get_dataset_id(self, *, workflow_id: str, node_id: str) -> str | None:
        all_bindings = self._load()
        workflow_bindings = all_bindings.get(workflow_id)
        if not isinstance(workflow_bindings, dict):
            return None
        value = workflow_bindings.get(node_id)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    def set_dataset_id(self, *, workflow_id: str, node_id: str, dataset_id: str | None) -> None:
        all_bindings = self._load()
        workflow_bindings = all_bindings.setdefault(workflow_id, {})
        if not isinstance(workflow_bindings, dict):
            workflow_bindings = {}
            all_bindings[workflow_id] = workflow_bindings

        if dataset_id is None or not str(dataset_id).strip():
            workflow_bindings.pop(node_id, None)
        else:
            workflow_bindings[node_id] = str(dataset_id).strip()

        if not workflow_bindings:
            all_bindings.pop(workflow_id, None)
        self._save(all_bindings)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._bindings_path.exists():
            return {}
        loaded = json.loads(self._bindings_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for workflow_id, payload in loaded.items():
            if not isinstance(workflow_id, str) or not isinstance(payload, dict):
                continue
            result[workflow_id] = {
                str(node_id): str(dataset_id)
                for node_id, dataset_id in payload.items()
                if isinstance(node_id, str) and isinstance(dataset_id, str)
            }
        return result

    def _save(self, payload: dict[str, dict[str, str]]) -> None:
        self._bindings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value).strip().lower())
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered


def _split_text(*, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        return []

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore

        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return [item for item in splitter.split_text(normalized) if item.strip()]
    except Exception:
        pass

    chunks: list[str] = []
    step = max(chunk_size - max(chunk_overlap, 0), 1)
    for start in range(0, len(normalized), step):
        part = normalized[start : start + chunk_size].strip()
        if part:
            chunks.append(part)
        if start + chunk_size >= len(normalized):
            break
    return chunks


def _extract_docx_text(file_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_bytes)
    paragraphs: list[str] = []
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for paragraph in root.iter(f"{namespace}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:  # pragma: no cover - depends on optional lib
        raise ValueError("PDF extraction requires pypdf package") from exc
