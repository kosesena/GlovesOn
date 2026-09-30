# The user, by the numbers

GlovesOn is built for one person: the receiving clerk at a distribution centre, on the dock,
with a pallet in front of her that was not on today's plan. She is not invented and she is not
someone we interviewed; she is described here from published numbers, each with its source, so
that every sentence about her can be checked. Where we measured something ourselves, the
recording is named.

## Who she is

- **She is one of 844,120 people in the United States alone.** That is the May 2023 count for
  "Shipping, Receiving, and Inventory Clerks" (SOC 43-5071), median wage $19.12 an hour,
  $39,780 a year. Warehousing and storage is the largest single employer of the occupation.
  Source: [BLS OEWS, May 2023](https://www.bls.gov/oes/2023/may/oes435071.htm).
- **Her hands are the bottleneck, not her head.** Receiving is manual by definition — the goods
  arrive on a pallet and someone has to open, count and put them away — and the recording of
  that work is still a screen or a sheet of paper for a large share of sites: in Modern Materials
  Handling's 2025 Warehouse/DC Operations Survey (101 respondents), about 40 % still use
  paper-based picking methods, down from 56 % in 2023; voice and pick-to-light grew.
  Source: [MMH, 2025 Warehouse/DC Operations Survey](https://www.mmh.com/article/2025_warehouse_dc_operations_survey_tech_investment_marches_on).
- **The clock she is measured on is dock-to-stock**: the hours from a truck arriving to the goods
  being put away *and recorded in the system*. WERC's 2025 DC Measures puts best-in-class under
  3.5 hours; the older WERC tiers had the median around 6 hours. The recording step is inside
  that clock — a receipt that waits for a terminal is inventory that does not exist yet.
  Sources: [WERC DC Measures 2025, via MMH](https://www.mmh.com/article/wercs_2026_dc_measures_report_delivers_benchmarks),
  [APQC definition](https://www.apqc.org/resources/benchmarking/open-standards-benchmarking/measures/dock-stock-cycle-time-hours-supplier).

## What GlovesOn measures for her

- **8 seconds** from her spoken "Yes, confirm" to the material document number being read back
  to her, on the live app against the mock S/4HANA. Measured on 24 September 2026 from a screen
  recording of one session (`Ekran Kaydı 2026-09-24 14.12.35.mov`, kept outside the repo): the
  yes at 32.5 s, the document number at 40.6 s. The reversal in the same session took 7.6 s, the
  refusal of a repeated reversal 6.0 s, the cancellation 5.0 s. One session, one network, one
  speaker: a measurement, not a benchmark.
- **Two documents after a mistake, never one.** A wrong receipt is corrected by a reversal
  document; both stay. That is not our design choice, it is how SAP's material ledger works,
  and the mock follows it (`gateway/sap_mock.py`).
- **Zero writes without the yes.** The write tools do not exist in the agent's configuration
  until a draft has been read back; a cancelled draft, a hesitation or a repeated request
  leaves nothing in the ledger. Tests: `tests/` (see `docs/JUDGE-GUIDE.md` for the map).

## What this does not claim

No ROI figure: session cost and time saved per receipt are not measured over a shift, only
per interaction. No claim that she wants voice — the surveys above measure adoption, not
preference. No named site: the numbers are national and industry-wide, and the demo tenant is
a mock.
