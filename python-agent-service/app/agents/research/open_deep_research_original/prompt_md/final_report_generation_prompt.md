{output_language_instructions}
Based on all the research conducted, create a comprehensive, well-structured answer to the overall research brief:

### Research brief

{research_brief}

For more context, here is all of the messages so far. Focus on the research brief above, but consider these messages as well for more context.

### Messages

{messages}

CRITICAL: Make sure the answer is written in the same language as the human messages!
For example, if the user's messages are in English, then MAKE SURE you write your response in English. If the user's messages are in Chinese, then MAKE SURE you write your entire response in Chinese.
This is critical. The user will only understand the answer if it is written in the same language as their input message.

Today's date is {date}.

### Findings

{findings}

Please create a detailed answer to the overall research brief that:
1. Is well-organized with proper headings (# for title, ## for sections, ### for subsections)
2. Includes specific facts and insights from the research
3. References relevant sources using [Title](URL) format
4. Provides a balanced, thorough analysis. Be as comprehensive as possible, and include all information that is relevant to the overall research question. People are using you for deep research and will expect detailed, comprehensive answers.
5. Includes a "Sources" section at the end with all referenced links

You can structure your report in a number of different ways. Here are some examples:

To answer a question that asks you to compare two things, you might structure your report like this:
1/ intro
2/ overview of topic A
3/ overview of topic B
4/ comparison between A and B
5/ conclusion

To answer a question that asks you to return a list of things, you might only need a single section which is the entire list.
1/ list of things or table of things
Or, you could choose to make each item in the list a separate section in the report. When asked for lists, you don't need an introduction or conclusion.
1/ item 1
2/ item 2
3/ item 3

To answer a question that asks you to summarize a topic, give a report, or give an overview, you might structure your report like this:
1/ overview of topic
2/ concept 1
3/ concept 2
4/ concept 3
5/ conclusion

If you think you can answer the question with a single section, you can do that too!
1/ answer

REMEMBER: Section is a VERY fluid and loose concept. You can structure your report however you think is best, including in ways that are not listed above!
Make sure that your sections are cohesive, and make sense for the reader.

For each section of the report, do the following:
- Use simple, clear language
- Use ## for section title (Markdown format) for each section of the report
- Do NOT ever refer to yourself as the writer of the report. This should be a professional report without any self-referential language.
- Do not say what you are doing in the report. Just write the report without any commentary from yourself.
- Each section should be as long as necessary to deeply answer the question with the information you have gathered. It is expected that sections will be fairly long and verbose. You are writing a deep research report, and users will expect a thorough answer.
- Use bullet points to list out information when appropriate, but by default, write in paragraph form.

REMEMBER:
The brief and research may be in English, but you need to translate this information to the right language when writing the final answer.
Make sure the final answer report is in the SAME language as the human messages in the message history.

Format the report in clear markdown with proper structure and include source references where appropriate.

### Citation rules

- If there are non-empty citations, assign each unique URL a single citation number in your text
- End with ### Sources that lists each source with corresponding numbers
- IMPORTANT: Number sources sequentially without gaps (1,2,3,4...) in the final list regardless of which sources you choose
- Each source should be a separate line item in a list, so that in markdown it is rendered as a list.
- Example format:
  [1] Source Title: URL
  [2] Source Title: URL
- Citations are extremely important. Make sure to include these, and pay a lot of attention to getting these right. Users will often use these citations to look into more information.

### Subagent return format (machine headings)

**Do not duplicate the report.** Write the **entire** markdown report first (all sections,
facts, comparisons, **Sources** list, citations) as the **main body** of your response.
Then, after one blank line, add **only** this trailing section (heading verbatim English;
section body in the same language as the user's messages):

## SM_SUBAGENT_WRAPUP
A **short preview only** (2–6 sentences or a short bullet list): what was researched,
which kinds of sources mattered, and the bottom-line conclusion. This is the **only** part
the live UI shows in the timeline / task preview for this subagent. Put **no** detailed
findings, tables, long citations, or the full Sources list here—the parent agent and
conclusion pipeline already use the **main body above** as the full handoff.

**Optional legacy:** You may omit `## SM_SUBAGENT_FULL_REPORT`. If you still include it, do
**not** paste the full report again there; a one-line pointer such as “(full report above)”
is enough. The system treats the main body as authoritative when it is substantial.

**Forbidden:** Placing `## SM_SUBAGENT_WRAPUP` before your main report; renaming the WRAPUP
heading; leaving the main report empty while putting the only copy under a different heading.

### Research stats payload (required)

After `## SM_SUBAGENT_WRAPUP`, emit the sentinel line **`### SM_STATS_PAYLOAD`** verbatim, then
one blank line, then **one** fenced ```json``` block with the structured stats that power the
analyst-facing stats bar. The chat UI strips the sentinel and everything after it from your
wrapup preview, so the JSON never leaks into the visible chat bubble. **Never** mention this
block in prose. Do **not** emit any prose between the sentinel and the fenced block.

Shape (sentinel + JSON, in this exact order):

```
### SM_STATS_PAYLOAD

```json
{{ ... research_stats JSON here ... }}
```
```

Schema (all fields are non-negative integers; omit a field if not applicable):

```json
{{
  "research_stats": {{
    "keyFindings": 0,
    "recommendations": 0,
    "gaps": 0
  }}
}}
```

Counting rules (strict):
- `keyFindings` = number of distinct, decision-relevant findings the report establishes
  (consolidated; do **not** count each evidence line separately).
- `recommendations` = number of distinct actionable recommendations / next steps the report
  proposes for the reader.
- `gaps` = number of distinct open questions, limitations, or unresolved areas explicitly
  acknowledged in the report.
- Do **not** invent values to fill the chips; if the report genuinely has no recommendations or
  no acknowledged gaps, omit those fields.
- Sources count and freshness are derived by the backend from the `### Sources` URLs — do **not**
  include them here.
