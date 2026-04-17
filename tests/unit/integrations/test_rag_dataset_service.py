from __future__ import annotations

from pathlib import Path

from agent_platform.integrations.rag_dataset_service import RAGDatasetService


def _build_service(tmp_path: Path) -> RAGDatasetService:
    return RAGDatasetService(
        catalog_path=tmp_path / "datasets.json",
        datasets_dir=tmp_path / "datasets",
        uploads_dir=tmp_path / "uploads",
        chunk_size=20,
        chunk_overlap=5,
    )


def test_ingest_text_file_creates_catalog_and_retriever(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    summary = service.ingest_uploaded_file(
        dataset_name="Knowledge Base",
        source_filename="kb.txt",
        file_bytes="line1\nline2\nline3\n".encode("utf-8"),
    )

    assert summary.dataset_id
    assert summary.name == "Knowledge Base"
    assert summary.chunk_count >= 1
    assert summary.dataset_id in service.retrievers_by_dataset_id
    assert (tmp_path / "datasets" / f"{summary.dataset_id}.json").exists()


def test_ingest_unsupported_file_type_raises(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    try:
        service.ingest_uploaded_file(
            dataset_name="Binary",
            source_filename="sample.bin",
            file_bytes=b"\x00\x01",
        )
    except ValueError as exc:
        assert "Unsupported file type" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_delete_dataset_removes_catalog_file_upload_and_retriever(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    summary = service.ingest_uploaded_file(
        dataset_name="Knowledge Base",
        source_filename="kb.txt",
        file_bytes="line1\nline2\nline3\n".encode("utf-8"),
    )

    deleted = service.delete_dataset(dataset_id=summary.dataset_id)

    assert deleted is True
    assert summary.dataset_id not in service.retrievers_by_dataset_id
    assert (tmp_path / "datasets" / f"{summary.dataset_id}.json").exists() is False
    assert (tmp_path / "uploads" / summary.dataset_id).exists() is False
    assert service.list_datasets() == []
