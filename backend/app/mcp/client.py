"""MCP client: discovery, schema validation, and bounded tool calls (Phase 5.11)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.mcp.schemas import (
    CreatePurchaseRequestInput,
    CreatePurchaseRequestOutput,
    GetPolicyEvidenceInput,
    GetPolicyEvidenceOutput,
    GetPurchaseRequestStatusInput,
    GetPurchaseRequestStatusOutput,
    GetSupplierQuotationInput,
    GetSupplierQuotationOutput,
    SearchSuppliersInput,
    SearchSuppliersOutput,
)

logger = logging.getLogger(__name__)

TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "search_suppliers": SearchSuppliersInput,
    "get_supplier_quotation": GetSupplierQuotationInput,
    "get_policy_evidence": GetPolicyEvidenceInput,
    "create_purchase_request": CreatePurchaseRequestInput,
    "get_purchase_request_status": GetPurchaseRequestStatusInput,
}

TOOL_OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "search_suppliers": SearchSuppliersOutput,
    "get_supplier_quotation": GetSupplierQuotationOutput,
    "get_policy_evidence": GetPolicyEvidenceOutput,
    "create_purchase_request": CreatePurchaseRequestOutput,
    "get_purchase_request_status": GetPurchaseRequestStatusOutput,
}

READ_ONLY_TOOLS = frozenset(
    {
        "search_suppliers",
        "get_supplier_quotation",
        "get_policy_evidence",
        "get_purchase_request_status",
    }
)


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    name: str
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    latency_ms: float = 0.0


class MCPClientError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class MCPClient:
    """Spawns the MCP server over stdio, caches discovery, enforces timeouts."""

    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        timeout_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command or os.getenv("MCP_SERVER_COMMAND", "python")
        default_args = os.getenv("MCP_SERVER_ARGS", "")
        if args is not None:
            self.args = list(args)
        elif default_args:
            self.args = json.loads(default_args)
        else:
            self.args = ["-m", "app.mcp.server"]
        self.timeout_s = timeout_s or float(os.getenv("MCP_TOOL_TIMEOUT_S", "10"))
        self.env = env
        self._tools: dict[str, ToolInfo] = {}
        self._session_cm = None
        self._session = None
        self._stdio_cm = None

    async def connect(self) -> None:
        if self._session is not None:
            return
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env={**os.environ, **(self.env or {})},
        )
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        await self.refresh_tools()

    async def refresh_tools(self) -> list[ToolInfo]:
        if self._session is None:
            await self.connect()
        assert self._session is not None
        result = await asyncio.wait_for(
            self._session.list_tools(), timeout=self.timeout_s
        )
        self._tools = {
            tool.name: ToolInfo(
                name=tool.name,
                description=tool.description or "",
                input_schema=dict(tool.inputSchema or {}),
            )
            for tool in result.tools
        }
        return list(self._tools.values())

    async def list_tools(self) -> list[ToolInfo]:
        if not self._tools:
            return await self.refresh_tools()
        return list(self._tools.values())

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        model = TOOL_INPUT_MODELS.get(name)
        if model is None:
            raise MCPClientError("unknown_tool", f"unknown tool {name}")
        try:
            return model.model_validate(arguments)
        except ValidationError as exc:
            raise MCPClientError(
                "invalid_arguments", f"invalid arguments for {name}: {exc}"
            ) from exc

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, timeout_s: float | None = None
    ) -> ToolResult:
        started = time.perf_counter()
        if not self._tools:
            try:
                await self.refresh_tools()
            except Exception as exc:
                return ToolResult(
                    ok=False,
                    name=name,
                    error_code="server_unavailable",
                    error_message=exc.__class__.__name__,
                    retryable=name in READ_ONLY_TOOLS,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
        if name not in self._tools:
            return ToolResult(
                ok=False,
                name=name,
                error_code="unknown_tool",
                error_message=f"tool {name} not advertised",
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        try:
            parsed = self.validate_arguments(name, arguments)
        except MCPClientError as exc:
            return ToolResult(
                ok=False,
                name=name,
                error_code=exc.code,
                error_message=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        if self._session is None:
            try:
                await self.connect()
            except Exception as exc:
                return ToolResult(
                    ok=False,
                    name=name,
                    error_code="server_unavailable",
                    error_message=exc.__class__.__name__,
                    retryable=name in READ_ONLY_TOOLS,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )

        deadline = timeout_s or self.timeout_s
        try:
            assert self._session is not None
            raw = await asyncio.wait_for(
                self._session.call_tool(
                    name, parsed.model_dump(mode="json", exclude_none=True)
                ),
                timeout=deadline,
            )
        except TimeoutError:
            return ToolResult(
                ok=False,
                name=name,
                error_code="timeout",
                error_message=f"tool call exceeded {deadline}s",
                retryable=name in READ_ONLY_TOOLS,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            # Drop the broken session so the next call reconnects.
            await self.close()
            return ToolResult(
                ok=False,
                name=name,
                error_code="server_error",
                error_message=exc.__class__.__name__,
                retryable=name in READ_ONLY_TOOLS,
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        latency = (time.perf_counter() - started) * 1000
        if getattr(raw, "isError", False) or getattr(raw, "is_error", False):
            text = ""
            content = getattr(raw, "content", None) or []
            if content:
                text = getattr(content[0], "text", "") or ""
            code = "tool_error"
            retryable = False
            if text:
                try:
                    payload = json.loads(text)
                    code = payload.get("code", code)
                    retryable = bool(payload.get("retryable", False))
                except (json.JSONDecodeError, TypeError):
                    pass
            logger.warning(
                "mcp tool failed",
                extra={"tool": name, "error_code": code, "latency_ms": latency},
            )
            return ToolResult(
                ok=False,
                name=name,
                error_code=code,
                error_message=text or "tool execution failed",
                retryable=retryable,
                latency_ms=latency,
            )

        data: dict[str, Any] = {}
        structured = getattr(raw, "structured_content", None) or getattr(
            raw, "structuredContent", None
        )
        if isinstance(structured, dict):
            data = structured
            if "result" in data and isinstance(data["result"], dict):
                data = data["result"]
        else:
            content = getattr(raw, "content", None) or []
            if content:
                text = getattr(content[0], "text", "") or ""
                try:
                    parsed_json = json.loads(text)
                    if isinstance(parsed_json, dict):
                        data = parsed_json
                except json.JSONDecodeError:
                    data = {"raw": text}

        out_model = TOOL_OUTPUT_MODELS.get(name)
        if out_model is not None and data:
            try:
                validated = out_model.model_validate(data)
                data = validated.model_dump()
            except ValidationError:
                # Untrusted output: keep raw but flag as unvalidated shape.
                data = {**data, "_unvalidated": True}

        logger.info(
            "mcp tool ok",
            extra={"tool": name, "latency_ms": latency, "ok": True},
        )
        return ToolResult(ok=True, name=name, data=data, latency_ms=latency)

    async def close(self) -> None:
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_cm = None
            self._session = None
        if self._stdio_cm is not None:
            try:
                await self._stdio_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._stdio_cm = None
        self._tools = {}

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
