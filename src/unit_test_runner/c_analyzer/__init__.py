from __future__ import annotations

from .link_provider_warning_compat import apply_link_provider_warning_compat

apply_link_provider_warning_compat()

from .legacy import analyze_function, list_functions, mask_comments_and_strings

__all__ = ["analyze_function", "list_functions", "mask_comments_and_strings"]
