<!-- ask-corpus
expect: note
material: false
source: run-safety.md, The pre-spend approval card: "Quote each row's input and its expected answer" - case 50's card with its two rows as `Q:`/`A:` pairs; a `Q:` label more than three past `A` joins no list (the guide offers at most three choices), so the rows are not routes and their questions are noted (a message from review)
note: above the routes besides the one they answer
-->
Stage 3/5 · Baseline

- **Two rows: the easiest and the hardest.**

Q: Which providers specialise in Cardiology? Show their full names.
A: `SELECT full_name FROM providers WHERE specialty = 'Cardiology'`
Q: Which patients have never had an appointment? Show first and last names.
A: `SELECT first_name, last_name FROM patients WHERE id NOT IN (SELECT patient_id FROM appointments)`

- **What the evaluation method counts as correct.** It runs your query and the expected one against the clinic database and counts a match when the rows agree.
- **What an asking cap asked.** This run did not calibrate your evaluator, because it executes the generated SQL; the baseline runs on that disclosure.

> **A. Run the baseline** *(recommended - your material is sound and the spend is bounded)*
> Reply `continue` and I will run the twelve configurations on the 28 selected rows.
>
> **B. Fix first.**
> Reply `fix` and I will return to the repair route before anything is spent.
>
> Or reply with a smaller trial cap or a lower ceiling and I will re-price this same step.
