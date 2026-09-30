# lablab submission — form fields

Final copy, 30 September 2026.

## Project title

GlovesOn — voice goods receipts into SAP

## Short description

A warehouse voice agent: a worker with both hands full posts goods receipts by
speaking, hears every one read back, and nothing is written without a clear yes.

## Long description

**The problem.** A receiving clerk has gloves on and an unplanned pallet in front
of her. Recording it means stopping, walking to a terminal and typing. GlovesOn
lets her do it by talking.

**The workflow.** She names the material and the quantity. GlovesOn looks up the
description, unit and bin itself, reads the receipt back (quantity, unit,
material description, bin) and posts it only after an explicit "yes". A wrong
receipt is corrected with a reversal document; both documents stay. The same
receipt twice is refused by a duplicate guard in the gateway.

**Built on AssemblyAI.** The Voice Agent API carries speech, conversation and
voice. Tool calls return to the browser and pass through a scoped capability to
our gateway, which speaks SAP's released OData APIs with the CSRF handshake a
real S/4HANA requires. The write tool does not exist until a draft has been read
back.

**Honest limits.** Reads have been verified against SAP's S/4HANA Cloud sandbox;
writes go to a mock S/4HANA that follows SAP's contract, and nothing has been
posted to a real SAP system. The posting is made by a service user, not the
individual worker. Calls, emails and notes are demo records. Noise robustness is
not benchmarked. Every claim, the file it lives in and the test that holds it:
`docs/JUDGE-GUIDE.md`.

## Technology tags

AssemblyAI · Voice Agent API · SAP S/4HANA · OData · FastAPI · Python ·
Postgres · Vercel

## Links

- Application: https://gloveson.space
- Video: https://youtu.be/5B2fo5k0wPQ (4:25, 1080p; also `submission/GlovesOn-film.mp4`)
- Repository: https://github.com/kosesena/GlovesOn
- Slides: `submission/GlovesOn-deck-cinematic.pdf` (cream edition `GlovesOn-deck.pdf`)
- Cover: `submission/cover-16x9.jpg`
