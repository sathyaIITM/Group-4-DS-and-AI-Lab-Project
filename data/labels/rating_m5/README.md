# Blind rating of 30 answers (Milestone 5)

30 answers from the test runs: 10 each from three agent versions, drawn at random (seed 0) from items the agent answered and the gold expects an answer. The version is hidden; the key is in `sealed/` and is opened only after both files are returned.

Rate alone, without discussing with the other rater until both files are in. Fill your own file:
- Shaoni Samanta (T1): `rating_sample_T1.csv`
- Sathya Prakash (T3): `rating_sample_T3.csv`

| Scale | 0 | 1 | 2 |
| --- | --- | --- | --- |
| interpretation_0_2 | Wrong place, period or indicator | Partly right | Right |
| completeness_0_2 | Key values missing | Some values or caveats missing | Complete |
| wording_0_2 | Misleading or hard to read | Awkward but correct | Clear |

Judge against the question and the evidence shown (tables used, SQL). About 1 minute per answer.
