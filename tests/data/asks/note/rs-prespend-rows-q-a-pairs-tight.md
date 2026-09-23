<!-- ask-corpus
expect: note
material: false
source: run-safety.md, The pre-spend approval card: "Quote each row's input and its expected answer" - the easiest and hardest rows as `Q:`/`A:` pairs, tight; a `Q:` label more than three past `A` joins no list (the guide offers at most three choices), so the rows are not routes and their questions are noted (a probe from review)
note: above the routes besides the one they answer
-->
Stage 3/5 · Baseline

The two rows at each end of your dataset:

Q: Which providers specialise in Cardiology?
A: SELECT full_name FROM providers WHERE specialty = 'Cardiology'
Q: Which patients have never had an appointment?
A: SELECT first_name FROM patients WHERE id NOT IN (SELECT patient_id FROM appointments)

> **A. Run the baseline** *(recommended - the spend is bounded)*
> Reply `continue`.
>
> **B. Fix first.**
> Reply `fix`.
