from . import build_workspace_generator as _build_workspace_generator
from .link_library_build_compat import apply_link_library_build_compat
from .log_parser import parse_build_log
from .workspace_compat_fixes import apply_build_probe_compat_fixes

apply_build_probe_compat_fixes()
apply_link_library_build_compat()

generate_build_workspace = _build_workspace_generator.generate_build_workspace

__all__ = ["generate_build_workspace", "parse_build_log"]
