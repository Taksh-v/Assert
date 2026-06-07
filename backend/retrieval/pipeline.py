"""Retrieval pipeline skeleton: stage interface + pipeline executor.

This module defines a minimal Stage contract and a `RetrievalPipeline` that
executes registered stages in order. Stages receive and return a context dict
allowing incremental composition without changing existing orchestrators.
"""
from typing import Callable, Dict, Any, List, Awaitable
import asyncio


class Stage:
    """A pipeline stage is an async callable that accepts and returns a context dict."""

    def __init__(self, name: str, fn: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]):
        self.name = name
        self.fn = fn

    async def run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await self.fn(ctx)


class RetrievalPipeline:
    def __init__(self):
        self.stages: List[Stage] = []

    def add_stage(self, stage: Stage) -> None:
        self.stages.append(stage)

    async def run(self, initial_ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = dict(initial_ctx)
        for stage in self.stages:
            ctx = await stage.run(ctx)
        return ctx
