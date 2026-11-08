"""Candidate customer adapter; no network, visual renderer or second parser."""

from typing import Any

from gpt_rag_ui.services.native_presentation import text_projection


def render_text(native_result: Any, *, owner_admitted: bool) -> str:
    """Project a completed native result AFTER the channel's existing owner gate.

    The boolean is an explicit caller precondition, not authentication. Never
    take it from a browser/request parameter. Send the returned string through
    the channel's existing safe text sink; never evaluate it as HTML or code.
    """
    if not owner_admitted:
        raise PermissionError("Existing native-result owner admission is required")
    return text_projection(native_result)
