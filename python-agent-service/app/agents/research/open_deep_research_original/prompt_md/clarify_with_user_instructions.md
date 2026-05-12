{output_language_instructions}

### Messages

{messages}

Today's date is {date}.

Assess whether you need to ask a clarifying question, or if the user has already provided enough information for you to start research.

**Distinguishing user input from routing-agent context**: The messages above may include a System message labeled "[Preliminary context from routing agent]". This context was added by an upstream routing agent based on quick web searches and may contain inaccuracies — wrong CVE numbers, misattributed details, or speculative claims. When judging whether clarification is needed:
- Focus on the **Human message** (the user's original question) to assess clarity and specificity.
- Do NOT treat preliminary context claims as confirmed facts or as "information the user provided."
- If the user's original question is vague or broad, ask for clarification even if the preliminary context appears detailed.
- The preliminary context is a hint for research direction, not a substitute for user intent.

IMPORTANT: If you can see in the messages history that you have already asked a clarifying question, you almost always do not need to ask another one. Only ask another question if ABSOLUTELY NECESSARY.

If there are acronyms, abbreviations, or unknown terms, ask the user to clarify.
If you need to ask a question, follow these guidelines:
- Be concise while gathering all necessary information
- Make sure to gather all the information needed to carry out the research task in a concise, well-structured manner.
- Use bullet points or numbered lists if appropriate for clarity. Make sure that this uses markdown formatting and will be rendered correctly if the string output is passed to a markdown renderer.
- Don't ask for unnecessary information, or information that the user has already provided. If you can see that the user has already provided the information, do not ask for it again.

Respond in valid JSON format with these exact keys:
"need_clarification": boolean,
"question": "<question to ask the user to clarify the report scope>",
"verification": "<verification message that we will start research>"

If you need to ask a clarifying question, return:
"need_clarification": true,
"question": "<your clarifying question>",
"verification": ""

If you do not need to ask a clarifying question, return:
"need_clarification": false,
"question": "",
"verification": "<acknowledgement message that you will now start research based on the provided information>"

For the verification message when no clarification is needed:
- Acknowledge that you have sufficient information to proceed
- Briefly summarize the key aspects of what you understand from their request
- Confirm that you will now begin the research process
- Keep the message concise and professional
