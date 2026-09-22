# Ilex Mutual claims intake assistant

We are the claims operations team at Ilex Mutual Insurance. The assistant in this folder is the
chatbot that greets a customer on the claims page of our website and works out, from the first
thing they type, which of six places to send them:

- `new_claim` - they are telling us about a loss we have not heard about yet
- `claim_status` - they have a claim open and want to know where it has got to
- `policy_question` - they want to know what their cover includes or how it works
- `update_details` - they want something on their record changed
- `complaint` - they are unhappy with how we or a supplier have treated them
- `human_agent` - they want a person, not the assistant

Everything after that first routing decision - the claim form, the status lookup, the handoff to
the webchat queue - works well enough. The routing decision itself is what we want to improve.
When it is wrong the customer is walked through the wrong conversation, gives up, and phones us,
which is the outcome the assistant exists to avoid.

## Where the assistant runs

The assistant is not code we wrote. It is a conversation flow built in Conversa Flows, a hosted
product. We design the flow in the vendor's editor, the vendor runs it, and the vendor's own
classifier model decides the intent using the prompt and the example utterances we typed into
the `classify_intent` node. We do not have the model, the classifier's code, or any way to call
it outside the vendor's platform.

What we can do is export the flow definition and re-import a changed one. `flow-export.json` is
that export, taken from version 14 of the live flow. It holds every node in the flow, the prompt
the classifier is given, the six intents with the example utterances the vendor uses for
matching, the confidence threshold below which the assistant asks the customer to clarify, and
the precedence order we apply when one message asks for two things. Those are the things we are
able to change: the prompt text, the examples under each intent, the threshold, and the order.

## What else is in this folder

- `dataset.jsonl` - 90 real first messages from the last quarter, one per line, each with the
  intent our intake team would have routed it to. The team labelled them by hand, applying the
  precedence order in the flow export to messages that ask for two things. Every message is
  different. Each row says whether it is one we are willing to tune against (`tuning`) or one we
  are keeping back to check a change against afterwards (`holdout`), and how hard the team judged
  it. Names, addresses and references in the messages have been replaced.
- `evaluator.py` - how we grade a routing decision: right intent or wrong intent, with the three
  spellings our own records use for the same intent treated as the same answer. The docstring
  says why.
- `calibration-cases.json`, in the runs folder - two messages with the answers we expect the
  grader to accept and reject, so anyone touching the grader can check it still agrees with us.

## What we want

A measured routing accuracy on the tuning rows for the flow as it stands, and then a version of
the classifier prompt and intent examples that scores better - checked on the held-back rows,
not the ones it was tuned on. The hard cases are the ones where a customer's wording sounds like
one intent and means another, and the ones where a message asks for two things at once.

We would rather be told plainly that something cannot be measured from what is here than be
given a number that is not real. If the flow has to be driven from outside the vendor's platform
to measure it, that is the first thing we need to hear.
