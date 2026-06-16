"""Request/response schemas for recording directory operation APIs."""

from pydantic import BaseModel, Field


class RenameRequest(BaseModel):
    """Request body for PUT /api/recordings/rename."""

    old_name: str = Field(..., description="Name of the recording folder to rename")
    new_name: str = Field(..., description="New folder name")


class DeleteRequest(BaseModel):
    """Request body for DELETE /api/recordings."""

    folders: list[str] = Field(..., description="Names of recording folders to delete")


class UpdateMetaRequest(BaseModel):
    """Request body for PATCH /api/recordings/{name}.

    Partial update — only the specified fields are written. Fields left as
    None are not modified.
    """

    task_name: str | None = Field(default=None, description="Task name")
    tags: list[str] | None = Field(default=None, description="List of tags")


class FileEntry(BaseModel):
    """Metadata for a single recording folder.

    Represents one subdirectory (= recording folder) under `output_dir`. By
    design a recording folder holds a flat set of files with no nested
    hierarchy, so the API does not expose the child file list — it returns
    only the flags and total size needed by the UI.
    """

    name: str = Field(..., description="Recording folder name")
    path: str = Field(..., description="Path relative to output_dir")
    size: int = Field(..., description="Total size of files in the folder (bytes)")
    modified_at: float = Field(..., description="mtime of the folder itself (UNIX seconds)")
    topic_count: int | None
    recording_start_ns: int | None
    duration_ns: int | None
    message_count: int | None
    has_quality_report: bool = Field(..., description="Whether quality_report.json exists")
    validation_overall_status: str | None = Field(
        ...,
        description=(
            "Overall validation status from validation_result.json "
            "(pass / warn / fail / error). null when no validation report exists."
        ),
    )
    upload_status: str | None = Field(
        ...,
        description=(
            "Latest upload status from upload_state.json "
            "(idle / uploading / uploaded / failed). null when no upload state exists."
        ),
    )
    task_name: str | None
    recording_config_name: str | None
    tags: list[str]


class FilesResponse(BaseModel):
    """Response for GET /api/recordings."""

    output_dir: str
    entries: list[FileEntry]


class TaskNamesResponse(BaseModel):
    """Response for GET /api/recordings/task-names.

    Returns task_name values collected from existing recordings, ordered
    by most recently used. Used to power autocomplete on the frontend's
    recording-start form.
    """

    task_names: list[str] = Field(..., description="Deduped list of task_name values (most recent first)")


class RenameResponse(BaseModel):
    """Response for PUT /api/recordings/rename."""

    name: str


class DeleteResponse(BaseModel):
    """Response for DELETE /api/recordings."""

    deleted: list[str]


class UpdateMetaResponse(BaseModel):
    """Response for PATCH /api/recordings/{name}."""

    task_name: str | None
    recording_config_name: str | None
    tags: list[str]
