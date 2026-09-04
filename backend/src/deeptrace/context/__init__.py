"""Direct source-context formatting and embedding filtering."""

from deeptrace.context.compression import ContextCompressor, format_document_context
from deeptrace.context.embeddings import CompressionRuntime

__all__ = [
    "CompressionRuntime",
    "ContextCompressor",
    "format_document_context",
]
