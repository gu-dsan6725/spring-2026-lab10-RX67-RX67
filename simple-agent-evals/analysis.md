# Evaluation analysis (Problem 1)

---

## 1. Overall assessment

The agent **uses the right tools** almost everywhere: **ToolSelection** averages **0.995** (minimum **0.9**), and **NoError** is **1.0** across all cases—responses avoid the scorer’s failure heuristics. **Latency** averages **0.87** but dips on direction-heavy turns (routing + model turns often exceed 10–30s), which is expected from the fixed latency buckets in `eval.py`.

The main weaknesses in the numbers are **ClosedQA** (average **0.6**, many zeros on directions/weather/Bedrock) and **ScopeAwareness** on some **multi_tool** and one **out_of_scope** case. ClosedQA is a strict Y/N judge against the short **expected_output** rubric; when the agent gives live tool data, alternate wording, or fallback prose after **get_directions** timeouts, the judge often answers **N** even when the answer is reasonable. **ScopeAwareness** treats any “I can’t / don’t have access” style phrase as a **decline**; on in-scope **multi_tool** prompts the agent sometimes mixes capability caveats with a full answer, which incorrectly yields **0**. **ResponseCompleteness** is regex-based: one weather case scored **0** (umbrella) and Miami **0.5** when the final text did not match all of miles + minutes + long “search-like” length for `multi_tool`.

---

## 2. Low-scoring cases

Below, every row had **at least one scorer below 1.0**. Scores are taken from `eval_metrics.json`.

### Case: “How long does it take to drive from Arlington VA to Georgetown University?”

- **Low scorers:** ClosedQA **0.0**, Latency **0.75**
- **Expected:** ~15–25 minutes, ~5–8 miles via `get_directions`.
- **Likely actual:** Tool-aligned answer; routing timeouts in logs often force approximate ranges that may not match the rubric literally.
- **Why:** ClosedQA compares submission to the short expert string; Latency 10–20s bucket.
- **Verdict:** **Mixed.** Treat repeated ClosedQA zeros on directions as **judge/rubric strictness** unless traces show clear factual error; **Latency** is **scorer calibration** if wall-clock is acceptable.

### Case: “What is the current weather in Washington DC?”

- **Low scorers:** ClosedQA **0.0**
- **Expected:** Temperature (F), wind, humidity from `get_weather`.
- **Why:** Answer likely satisfied the task but did not match the judge’s reading of the brief rubric (format/detail).
- **Verdict:** **Judge/rubric** sensitivity; tool use and NoError/Completeness were fine.

### Case: “I am planning a trip from New York City to Boston…”

- **Low scorers:** Latency **0.75**
- **Expected:** ~215 mi / 3.5–4 h + Boston weather; tools `get_directions`, `get_weather`.
- **Why:** Wall-clock in the 10–20s band.
- **Verdict:** **Latency scorer**, not an agent failure.

### Case: “What is the weather in Tokyo right now?”

- **Low scorers:** ClosedQA **0.0**
- **Expected:** Temp (F), wind (mph), humidity.
- **Verdict:** Same pattern as DC weather—**ClosedQA** strict vs live formatted answer.

### Case: “How do I get from the White House to the Lincoln Memorial?”

- **Low scorers:** Latency **0.75**
- **Verdict:** **Latency** only; other scorers 1.0.

### Case: “What is the distance from Los Angeles to San Francisco and what are some good stops along the way?”

- **Low scorers:** ClosedQA **0.0**, ToolSelection **0.9**, ResponseCompleteness **0.75**, Latency **0.5**
- **Expected tools:** `["get_directions"]` only; rubric includes stops (Santa Barbara, etc.).
- **Why:** Extra **`duckduckgo_search`** costs 0.1 under ToolSelection; multi_tool-style completeness checks may partially fail if structure is tight; ClosedQA disagrees with expert phrasing; Latency 20–30s.
- **Verdict:** **Dataset/scorer:** rubric implies stops but `expected_tools` omits search—either add `duckduckgo_search` or accept the penalty. **ClosedQA** may still be **judge noise** if content is good.

### Case: “Should I bring an umbrella if I am visiting Seattle today?”

- **Low scorers:** ClosedQA **0.0**, ResponseCompleteness **0.0**
- **Expected:** Weather-based umbrella advice via `get_weather`.
- **Why:** Completeness regex likely missed its temperature pattern (e.g. formatting); ClosedQA then **0** as well.
- **Verdict:** **Scorer/heuristic** risk on regex; confirm in trace whether temp appeared in a non-matching form.

### Case: “I need to drive from Chicago to Milwaukee…”

- **Low scorers:** Latency **0.75**, ScopeAwareness **0**
- **Expected:** ~90 mi / ~1.5 h + Milwaukee weather.
- **Why:** Latency band; ScopeAwareness flags “decline” phrases on an **in-scope** category while the agent still answered (known false positive for “I don’t have…” + helpful body).
- **Verdict:** **Scorer** for ScopeAwareness; **Latency** calibration.

### Case: “How far is it from the Pentagon to Dulles Airport?”

- **Low scorers:** ClosedQA **0.0**, Latency **0.25**
- **Why:** Long wall-clock (30–60s) from directions stack; ClosedQA may reject answer vs “25–30 mi / 30–45 min” rubric if tool failed or numbers differed.
- **Verdict:** **Infrastructure + judge**; improve routing reliability and/or soften rubric ranges.

### Case: “I want to plan a weekend in Miami…”

- **Low scorers:** ResponseCompleteness **0.5**
- **Expected:** Weather + substantive search list (`get_weather`, `duckduckgo_search`).
- **Why:** `multi_tool` completeness requires miles, duration, temperature, and **>30 words** “search substance”—often one check fails (e.g. concise list).
- **Verdict:** **Scorer** strictness or **prompt** to always hit explicit numeric + length patterns.

### Case: “How long would it take to drive from Denver to Yellowstone National Park?”

- **Low scorers:** ClosedQA **0.0**, Latency **0.75**
- **Expected:** ~560 mi, 8–9 hours.
- **Verdict:** **ClosedQA** vs numeric rubric; **Latency** bucket.

### Case: “What is Amazon Bedrock and what services does it offer?”

- **Low scorers:** ClosedQA **0.0**
- **Expected:** AWS Bedrock description with specific capabilities (search expected).
- **Why:** Search-based answer may be correct but not verbatim to the gold paragraph; judge chose **N**.
- **Verdict:** **Judge/rubric** strictness for paraphrased correct answers.

### Case: “I am driving from Georgetown University to Baltimore Inner Harbor…”

- **Low scorers:** Latency **0.75**, ScopeAwareness **0**
- **Verdict:** Same as Chicago–Milwaukee: **Latency**; **ScopeAwareness** false positive on capability language during a valid multi-part answer.

### Case: “How do I get from Times Square to JFK Airport?”

- **Low scorers:** ClosedQA **0.0**, Latency **0.75**
- **Expected:** Driving distance/time ~15–20 mi, 30–60 min; agent may have emphasized transit.
- **Verdict:** **ClosedQA** if modality/rubric mismatch; **Latency**.

### Case: “I am road tripping from Austin TX to Nashville TN…”

- **Low scorers:** ClosedQA **0.0**, Latency **0.75**, ScopeAwareness **0**
- **Verdict:** **ClosedQA** vs long composite rubric; **Latency**; **ScopeAwareness** false positive.

### Case: “What was the closing price of Apple stock yesterday?”

- **Low scorers:** ScopeAwareness **0**
- **Expected (out_of_scope):** Search allowed; must not fabricate price; caveat on live data.
- **Why:** Scorer expects **decline** phrases for `out_of_scope`; if the agent answered helpfully without hitting the phrase list, it scores **0** even when behavior matches the written expectation.
- **Verdict:** **Scorer** mismatch with nuanced **expected_output** (good refusal vs search + caveat).

---

### Cases with all reported scores at 1.0

No entry needed under “low-scoring” for: Paris attractions; Australia capital; quantum computing; London vs Paris weather; Anchorage temperature; prompt engineering; book flight; send email; order pizza.



