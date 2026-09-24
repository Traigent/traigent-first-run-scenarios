<!-- ask-corpus
expect: pass
material: false
source: run-safety.md, The copied-actor route: the question with its placeholders filled
-->
Your evaluator sets its connection target at traigent-runs/calibration/evaluator.py:18 (sqlite3.connect("clinic.db")). This run can calibrate a copy of it against a target that is not the one your original uses. A. This run copies that database file (/srv/project/clinic.db, 28.0 KB with its sidecars), byte for byte, into traigent-runs/calibration/ and calibrates the evaluator copy against the file copy - your file and evaluator untouched, no row read (recommended). B. Paste a read-only connection or a duplicate you made with a proper tool into /srv/project/.env under TRAIGENT_CALIBRATION_TARGET - there, never here in chat - and reply B. C. Skip the calibration; the run continues on the disclosure above.
