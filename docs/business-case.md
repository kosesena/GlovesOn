# Business case

Feeds the lablab "long description", the Business Value slide and the video
narration. Every number below carries a bias tag and its source is listed at
the end; nothing here may cite a figure that is not there. Tags: **[V]** vendor
marketing · **[I]** independent or first-hand · **[R]** paid analyst report. Costs come from `docs/assemblyai-notlari.md` §1 and follow the rule
in `docs/nfr.md` §5: no ROI claim until session length per receipt is measured.

---

## The user

A receiving clerk on a warehouse floor that runs SAP. Gloves on, both hands
under a box that just came off a truck. Every delivery they accept has to end
up in SAP as a material document — until it does, the company does not know it
owns the goods: purchasing chases a delivery that already arrived, production
plans without parts that are sitting on the dock, sales promises dates from
wrong stock.

Today that record costs a walk. Put the box down, pull the gloves off, find
the shared terminal, log in, open the transaction, type material, quantity,
plant, storage location, bin — post. For every delivery. The terminal is the
single most expensive piece of furniture on the floor, priced not in hardware
but in interrupted work.

## What GlovesOn does about it

The worker says one sentence: *"Forty M8 bolts arrived."* The agent looks up
the material itself — bin, unit, description — and reads the whole posting
back aloud: *"Forty pieces of hex bolt M8x40 into bin A-03-02 — confirm?"*
On an unmistakable yes, a real goods receipt is posted through SAP's released
OData API. Stock updates in the moment. A wrong receipt is corrected by voice
too — with a reversal document, never a deletion, so both records stay and
the audit trail ties each document back to the sentence the worker confirmed.

Hands never leave the box. The screen is gone from the loop.

## Why this does not already exist

Voice in warehouses is decades old and very good at what it does. Honeywell
Voice guides roughly a million workers **[I]**; Lydia is SAP-certified with
speaker-independent recognition **[V]**. But every incumbent voice-guides
*planned* work: the WMS issues a task, the worker answers fixed prompts. The
unplanned pallet on the dock — the thing that actually interrupts a floor —
has no voice path. None of them lets a worker *initiate* a document by
describing it.

SAP itself is the proof the gap is real: Joule already posts and reverses
goods movements *by chat* in EWM, and SAP announced real-time voice for Joule
(LiveKit partnership) with GA planned H2 2026 — in its top cloud tiers first
**[V]**. The market leader is walking toward this product.
GlovesOn demonstrates it working today, on a browser and a consumer headset.

## The numbers

- Voice-directed warehousing is an established budget line: analyst estimates
  of the market range from **$4.8B to $6.5B today, growing 14–17% a year**
  **[R]** (cited as a range: the estimates disagree).
- The incumbent cost norm is **~$5,000 per user** in hardware and software
  (integrator budgeting figure **[I-ish]**), with ROI typically accepted at
  10–15 users and up.
- GlovesOn's marginal hardware cost per seat is zero — a browser and a
  headset. The variable cost is voice time: **$0.075 per connected minute**
  (provider list price). *Illustration, not a measurement:* if a receipt
  conversation averaged 45 seconds, the voice cost per posting would be about
  five and a half cents. Session length per receipt is unmeasured; per
  `nfr.md` §5 no ROI figure is quoted until it is.

## Positioning in one sentence

Incumbents voice-execute the work the WMS planned; SAP's assistant is growing
voice in its priciest cloud editions; **GlovesOn is the unplanned moment —
a pallet arrives, both hands are full, and the record has to exist now —
handled with a write discipline the ERP itself is only beginning to grow:
spoken read-back of the material description, an explicit yes, a duplicate
guard, reversal instead of deletion, and an audit trail from document back to
sentence.**

## Honest limits

Stated because the judges will find them anyway (`clean-core.md`, `nfr.md`):
noise robustness is untested and nothing is enabled yet; the posting is not
made as the individual worker (principal propagation is the missing Clean
Core piece); the demo serves one session at a time by design; Turkish is
understood on input but the agent cannot yet answer in Turkish.

## Sources

- Honeywell Voice (Vocollect), scale and SAP integration: <https://thirdfin.io/voice-picking/honeywell-vocollect/> ·
  <https://automation.honeywell.com/content/dam/honeywell-edam/sps/ppr/en-us/public/software/common/documents/sps-ppr-honeywell-voicedirect-erp-for-sap-brochure-en-us-ltr.pdf>
- Lydia 9 Voice Browser, SAP-certified: <https://www.logisticsbusiness.com/it-in-logistics/lydia-9-voice-browser-certified-sap/> ·
  <https://epg.com/logistics-software/lydia-voice/>
- Joule, transactional EWM actions by chat: <https://community.sap.com/t5/supply-chain-management-q-a/ai-in-warehousing-what-you-need-to-start-with-joule/qaq-p/14345541>;
  real-time voice with LiveKit: <https://livekit.com/blog/livekit-partners-with-sap-to-deliver-intelligent-voice-for-joule>
- Market size: <https://www.gminsights.com/industry-analysis/voice-directed-warehousing-solution-market> ·
  <https://market.us/report/global-voice-directed-warehousing-solutions-market/> ·
  <https://www.mordorintelligence.com/industry-reports/voice-picking-solution-market>
- Incumbent cost per user: <https://www.fcbco.com/blog/bid/156266/voice-technology-in-the-warehouse> ·
  <https://www.capturetech.com/en/techniques/pick-by-voice/the-profit-and-investment-in-voice-picking/>
