# Noise test — measuring recognition under a warehouse floor

`voice_focus: far-field` is set in `agent/agent.json`, but a config change is a
claim, not a measurement. This is the harness that turns it into one. Until it
is run, the honest statement is the one in `docs/nfr.md`: **enabled, unmeasured.**

The thing being measured is not "does it feel better" — it is whether the agent
recognizes SAP material numbers and quantities correctly while a warehouse is
loud around the speaker. A wrong material number is the failure that matters:
it is the one the read-back exists to catch, and the one that would post a
document against the wrong part.

---

## What you need

- Chrome, the live demo, a headset mic (the real deployment target — not a
  studio mic, that would measure the wrong thing).
- A noise source playing warehouse audio through a separate speaker, not
  through the headset: forklift, pallet-truck, PA. A phone playing a
  "warehouse ambience" loop at a measured distance works.
- A phone SPL meter app to set the noise level. Test at three levels:
  **quiet (~45 dB), moderate (~65 dB), loud (~80 dB)**. 80 dB is a real
  receiving floor; incumbent voice systems are tuned for 85 dB.

## The script — 20 utterances, fixed

Say each one once, at a normal working voice, without leaning into the mic.
They cover the recognition targets that actually matter: four-digit material
numbers (both digit-by-digit and paired), quantities as number words, and bin
codes. Use the demo's real materials so the keyterms apply.

```
 1  "Post a goods receipt, twenty pieces of four seven one one."
 2  "Post a goods receipt, forty pieces of forty-seven eleven."
 3  "How many of material four seven one two do we have?"
 4  "Fifteen pieces of five one zero zero."
 5  "A hundred and twenty pieces of four seven one three."
 6  "Where are the ball bearings stored?"
 7  "Post a goods receipt, thirty five pieces of five one zero one."
 8  "Two hundred pieces of six two zero zero."
 9  "Material four seven one one, stock check."
10  "Post a goods receipt, five pieces of seven three zero zero."
11–20  repeat 1–10 with the noise source at the next level up.
```

## What to record, per utterance

A spreadsheet, one row per utterance × level. Columns:

| level | said | transcript | material ok? | quantity ok? | posted correctly? | notes |

- **material ok** and **quantity ok** are the numbers that count. A wrong
  digit is a fail even if the sentence was otherwise perfect.
- **posted correctly** is the end-to-end truth: did the right document get the
  right line, or did the read-back catch a mishear before you confirmed?
- Note every mishear verbatim — "four seven one one" heard as "four seven one
  none" tells you more than a pass/fail bit.

## The number that goes in the report

Per level: **material-number accuracy = correct materials / 10.** That single
figure, at each of the three levels, is what `nfr.md` and the deck may cite.
Nothing else — not a feeling, not "works great in noise."

## After measuring — the knobs, in order

Only turn one at a time, and re-run the script after each, or you learn nothing:

1. `voice_focus_threshold` up from 0.85 toward 1.0 — more aggressive
   suppression. Watch for the cost: too high starts eating quiet speech.
2. `input.transcription_mode: max_accuracy` (default `balanced`) — the notes
   already flag this as the first thing to try for material numbers; it costs
   latency.
3. Only if both fail at 80 dB: revisit whether far-field was the right mode, or
   whether the headset itself is the limit.

## What this test cannot fix

If accuracy collapses at 80 dB and stays there, that is not a bug to hide — it
is the incumbents' known strength showing: ruggedized incumbents beat a browser-and-headset
on extreme-noise robustness, and the honest positioning already concedes it.
The read-back is the backstop by design: even a mishear does not post, because
nothing posts without the spoken yes.
