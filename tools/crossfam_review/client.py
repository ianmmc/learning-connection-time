"""The single seam to the paid OpenRouter client.

Every other module in this package reaches the paid client THROUGH here (`from ... import client as
OR`), never `infrastructure.*` directly — so the whole package has exactly ONE line of coupling to the
host project, isolated in this file. When the harness is extracted to a standalone public repo
(tracked in the GitHub issue for that extraction), only this file changes: replace the re-export below
with a vendored lean streaming client (SSE + usage.cost + truncation-retry + billing-halt), and
nothing else in the package moves.
"""
from infrastructure.acquisition.stage7_extract.openrouter import (  # noqa: F401  (re-export seam)
    call,
    has_key,
    CallResult,
    BillingAuthError,
)
