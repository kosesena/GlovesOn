# Voice connection diagnostic — 2026-09-09

## Resolved application path — production verification

Production deployment `dpl_DujJtEFNeGdkzxvycczEKkY5teai` is READY at
https://gloveson.vercel.app. Browser sessions now send inline configuration with
function tools, avoiding the failing stored-agent lookup. The provider's internal
visibility discrepancy remains unexplained; it no longer blocks the browser flow.
A separate playback defect was corrected: `reply.audio` carries PCM in `data`,
whereas the browser previously read `audio`. Suspended microphone AudioContexts
are explicitly resumed for Safari.

A synthetic spoken stock question was sent through the production voice session:
recognized speech “How many pieces of material 4711 are in stock?”, `get_stock`
HTTP 200, stock 271, matching spoken reply and nonempty audio response. The session
ended successfully, its revoked tool capability returned 401, and inventory was
unchanged. This verifies the live provider and tool flow; it does not claim a test
of the user's physical microphone or Safari audio device.

The tool bridge preserves existing ERP validation and confirmation, requires a
separate expiring capability and active scope, and never exposes the shared tool
secret. Browser results wait for `reply.done`; interrupted late results are discarded.
Validation: full suite 71 passed and 10 subtests passed on the dedicated test database;
32 focused checks and 9 browser lifecycle checks passed. Full-suite execution
preceded the final audio-field correction, which has a focused browser regression
check and the successful live verification above.

See `voice-inline-verification.json` for the sanitized end-to-end result. The sections
below are historical measurements and are superseded by this resolution.

## Earlier measurements: runtime equality and origin-dependent visibility

At approximately 20:59–21:02 Türkiye time, the existing authenticated `/health`
endpoint confirmed that the running production AssemblyAI key matches the local
`.env` key. The tool secret also matches. Only equality booleans were printed;
neither secret nor its fingerprint was printed. The local key also matches the
fingerprint supplied by the user. There is no inherited shell key overriding it.

A protected diagnostic mode was deployed to production:
`dpl_DLRZT25Fvss9scf1ijVsTgCzyRMi`,
`https://gloveson-fo6tdnycg-sena-koses-projects.vercel.app`.
`GET /api/voice-token?diagnostic=true` requires `X-Tool-Secret` before touching
the session budget or the provider. It uses the ordinary template with deliberately
invalid tool credentials and routing scope. No ERP tools were invoked. Standard
requests retain their previous behavior. Raw provider bodies are not logged:
only allowlisted metadata, response shape, identifiers and equality flags are returned.

Controlled comparison (matching request payload digests):

| Check | Observed result |
|---|---|
| Production runtime key versus local file | Match |
| Production POST agent | 201 |
| Production immediately GETs that same agent | 200 |
| Local client GETs production-created agent | 404 |
| Local POST identical diagnostic payload | 201 |
| Local GETs its own new agent | 200 |
| Both temporary agents cleaned up | Confirmed |

This disproves the claim that the production-created agent was never retrievable.
It demonstrates origin-dependent visibility, not its internal cause. Provider
partitioning/routing is a hypothesis; a wrong configured key is no longer supported.
The `tools` echo differs on both sides, which is not evidence of a mismatched
submitted payload: the provider documents masking/write-only headers and may
return normalized tool defaults.

Four additional local controls covered raw/Bearer authorization and minimal/full
templates. Each returned 201; same-client and fresh-client GETs returned 200 with
either authorization form. All four agents were deleted (204). No response set a
cookie. Thus these local controls do not support auth-prefix or connection-reuse
explanations. They do not establish the provider's server-side routing behavior.

A final, tool-free local agent returned GET 200 and WebSocket `session.ready`;
the session was ended and the agent deleted. This was a silent connection check,
not a human microphone or ERP end-to-end test. Production voice success has not
been established. The new diagnostic code is deployed; the earlier UI changes
remain separate local changes.

See `voice-provider-evidence.json` for sanitized request IDs and response metadata,
No external message
has been sent. Diagnostic tests cover authorization, invalid tool credentials,
agent tracking and redaction. Local check suite: 28 passed.

## Earlier follow-up: explicit user authorization and key replacement

The user instructed replacing Vercel's ASSEMBLYAI_API_KEY with the working value
from the local .env, redeploying, and probing again. Updated the existing project
variable with Vercel's PATCH API (HTTP 200); sensitive type and production/preview
targets were retained. No key value was printed, and no other variable was changed.

Redeployed the original production deployment, not a diagnostic preview:
`dpl_Ax547H6GLQscMS6W5ZTrNr9YMXkh`, URL
`https://gloveson-m3fjrjb4w-sena-koses-projects.vercel.app`. Vercel confirmed Ready
and the `gloveson.vercel.app` alias points to it.

Post-deployment probe still fails: token endpoint 200, agent lookup with local key
404, WebSocket session.error agent_not_found. Cleanup returned HTTP 200 with
closed:true and cleanup_pending:false. No ERP calls or writes. Thus replacing the
configured key did not resolve the observed failure; do not label a different
account as the proven root cause. The runtime credential equality has not been
independently measured. Provider-side record visibility remains unexplained.

Local UI error visibility changes are still undeployed and uncommitted.
The historical approval rejections below are retained as an audit trail; the user
has since explicitly authorized the key replacement and production connection probe.

## Reproduced failure

The user sees `session.error: agent_not_found` after Start talking in Safari.
The same error was reproduced using a Python WebSocket client, so this failure
occurs before microphone capture and is not specific to Safari.

Production alias `gloveson.vercel.app` points to deployment
`dpl_E9KaEghsg6NJN5hnezLYRPXrpUq8` at commit `20d9c80`. The long URL in the
user screenshot is this same deployment, not an older preview.

## Evidence

- Production `/api/voice-token` returns 200 with a scoped token and a fresh agent ID.
- Its token successfully opens a session with an agent created using the local
  AssemblyAI credential. A locally minted token cannot open the production-created agent.
- Local agent creation works with both raw and Bearer authorization, with tokens
  issued before or after agent creation. The project template also connects using
  deliberately invalid tool credentials and no tool calls.
- Production-created agents return 404 when retrieved using the local credential,
  including after 12 seconds. This alone does not prove the keys are identical.
- A temporary Vercel preview with Bearer authorization and an invalid diagnostic
  TOOL_SHARED_SECRET still reproduces the failure. Do not merge that header change
  as a fix.
- A diagnostic preview can retrieve its own newly created agent server-side (200),
  while the client WebSocket still receives agent_not_found. Account/project scope
  or provider-side visibility needs further investigation; neither is proven yet.
- The Vercel API does not return the value of its sensitive AssemblyAI variable.
  An empty returned value is redaction, not evidence of an empty configured key.
- All diagnostic sessions were closed and temporary agents cleaned up. No tool
  calls or ERP writes were made. No shared database reset was performed.

## Local UI fix

`web/index.html` now tears down failed provider sessions, opens the transcript,
and retains Connection error instead of returning to Ready to listen. Playback
initialization errors also re-enable the button and expose the message.

Validation: 24 Python checks passed; the actual browser session functions passed
5 mocked lifecycle checks, including provider error and audio initialization failure.
These UI changes are local and have not been deployed or committed.

## Approval boundary

Automatic approval review rejected a full-template diagnostic using the real tool
secret, then rejected calling a preview endpoint that would send that secret to
AssemblyAI. Safe follow-up previews used an invalid diagnostic secret instead.
A proposed runtime equality check against the local AssemblyAI key was also
rejected because it would embed a credential-derived fingerprint in preview code.
That command did not run. Do not bypass these rejections. User authorization is
needed for the credential comparison and real-credential verification steps.

## Temporary diagnostic deployments

- Bearer-only preview: `gloveson-c4ahdx2x3-sena-koses-projects.vercel.app`
- Invalid-secret preview: `gloveson-jn91aoabk-sena-koses-projects.vercel.app`
- Invalid-secret preview plus server lookup:
  `gloveson-bu6txi63u-sena-koses-projects.vercel.app`

Do not promote these diagnostic deployments to production. They are not the fix.
These previews did not change production at that point in the investigation.
Subsequent key replacement and the protected diagnostic deployment are recorded above.
