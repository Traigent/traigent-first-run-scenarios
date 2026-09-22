# SPDX-License-Identifier: Apache-2.0
"""Compares the intent a first message was routed to with the intent our intake team recorded.

The six intents are spelled three ways across our own records. The flow export writes them as
the vendor's intent keys (new_claim), the weekly routing report the vendor emails us writes them
as titles (New Claim), and the intake team's review spreadsheet uses hyphens (new-claim). INTENTS
lists the six keys the flow routes to, and both sides are folded to that spelling before they are
compared -- so a label written the report's way is still the same routing decision, which
comparing the strings would mark wrong.

A routed intent that folds to none of the six is a wrong route and scores 0.0: the flow has a
fallback node for exactly that case, and a message that lands there was not routed. A recorded
intent that folds to none of them is a row we mislabelled or an intent we have since retired, and
grading against it would quietly mark every route wrong, so it is raised instead.
"""

INTENTS = (
    "new_claim",
    "claim_status",
    "policy_question",
    "update_details",
    "complaint",
    "human_agent",
)


def _intent(label):
    """The intent key this spelling names, or None when the flow has no such intent."""
    key = str(label).strip().casefold()
    for separator in (" ", "-"):
        key = key.replace(separator, "_")
    while "__" in key:
        key = key.replace("__", "_")
    key = key.strip("_")
    return key if key in INTENTS else None


def score(output, expected, input_data=None, metadata=None):
    recorded = _intent(expected)
    if recorded is None:
        raise ValueError(
            f"recorded intent {expected!r} is not one of INTENTS -- "
            "the row or the intent list is out of date"
        )
    return 1.0 if _intent(output) == recorded else 0.0
