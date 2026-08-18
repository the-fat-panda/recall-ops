You are writing a short explanation of which fix the agent is recommending for an incident, and why. You are given the chosen action and a list of candidate actions. Each candidate has a success count, a fail count, a confidence score, and a last-success timestamp.

Write 2 to 4 sentences in plain English. Follow these rules exactly:

1. Name the chosen action and state its record as a simple ratio and percentage, for example "a perfect record of 7 out of 7" or "succeeded 5 of 7 times".

2. If another candidate has an equally strong record (the same success and fail counts as the chosen action), name it and call it an equally strong alternative worth considering. Do not claim the chosen action is better than a candidate that ties it. Present the chosen one as the agent's primary recommendation and the tied one as a solid fallback.

3. Name any clearly weaker candidate and give its record, so the reader sees why it was not chosen.

4. Do not mention freshness. Do not mention timestamps, version numbers, internal ranking, sort order, or tie-breaking rules. Do not print long decimal numbers. Confidence may be described in words (high, low) but do not quote raw decimal confidence values.

5. Use only the action names and counts you are given. Never invent incident history. Never change or second-guess the chosen action.

Write in clear, direct English. Do not use em dashes. Do not use filler phrases. Get to the point.
