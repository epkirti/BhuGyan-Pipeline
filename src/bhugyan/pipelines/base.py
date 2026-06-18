"""Base class for all pipelines."""
from __future__ import annotations

import abc

import asyncpg

from ..config import settings
from ..observability import PipelineRun


class Pipeline(abc.ABC):
    #: short id (p1..p5) and human label
    id: str = ""
    label: str = ""

    def __init__(self, conn: asyncpg.Connection, **opts):
        self.conn = conn
        self.opts = opts

    def new_run(self, meta: dict | None = None) -> PipelineRun:
        return PipelineRun(f"{self.id.upper()}: {self.label}",
                           meta=meta or {}, log_dir=settings.run_log_dir)

    @abc.abstractmethod
    async def run(self) -> dict:
        """Execute the pipeline end to end; return a summary dict."""
        raise NotImplementedError
