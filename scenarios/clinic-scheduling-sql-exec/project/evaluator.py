# SPDX-License-Identifier: Apache-2.0
"""Scores a generated query by running it against clinic.db and comparing rows.

Running the model's SQL is how this benchmark has always been scored. The
front desk does not care whether the query is written the way ours is - a
different join order, a subquery instead of a HAVING, an alias we would not
have picked - it cares whether the rows that come back are the rows on the
schedule. So both queries are executed against the same read-only copy of the
scheduling database and the result sets are compared as multisets: the share of
rows the two sets have in common over the rows either one returned. Row order
is ignored unless the recorded query carries an ORDER BY, in which case the
rows also have to arrive in the same order to keep full credit; the right rows
in the wrong order earn half.

The database is opened read-only, each statement is stopped after a fixed
number of seconds, and no more than ROW_CAP rows are read from either side. A
candidate that fails to run, runs past the budget, or returns too many rows is
a wrong answer and scores 0.0. A recorded query that does any of those things is
a broken row, and the row is raised rather than silently marking every
candidate wrong against it.
"""

import re
import sqlite3
import time
from collections import Counter
from pathlib import Path

DATABASE = Path(__file__).with_name("clinic.db")
STATEMENT_TIMEOUT_SECONDS = 5.0
ROW_CAP = 5000
ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)


def _connect():
    """A read-only connection that interrupts any statement past the time budget."""
    connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = 1")
    started = time.monotonic()

    def watchdog():
        if time.monotonic() - started > STATEMENT_TIMEOUT_SECONDS:
            return 1
        return 0

    connection.set_progress_handler(watchdog, 1000)
    return connection


def _canonical(value):
    """One spelling per value, so 25 and 25.0 are the same copay."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _rows(sql):
    """The rows one statement returns, as canonical tuples, or None when it cannot run."""
    if not isinstance(sql, str) or not sql.strip():
        return None
    connection = _connect()
    try:
        cursor = connection.execute(sql.strip().rstrip(";"))
        fetched = cursor.fetchmany(ROW_CAP + 1)
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if len(fetched) > ROW_CAP:
        return None
    return [tuple(_canonical(value) for value in row) for row in fetched]


def score(output, expected, input_data=None, metadata=None):
    recorded = _rows(expected)
    if recorded is None:
        raise ValueError(
            f"the recorded query cannot be run against {DATABASE.name} -- "
            f"the row is out of date or the database is: {expected!r}"
        )
    candidate = _rows(output)
    if candidate is None:
        return 0.0
    recorded_counts = Counter(recorded)
    candidate_counts = Counter(candidate)
    common = sum((recorded_counts & candidate_counts).values())
    union = sum((recorded_counts | candidate_counts).values())
    if union == 0:
        return 1.0
    overlap = common / union
    if overlap == 1.0 and ORDER_BY.search(expected) and candidate != recorded:
        return 0.5
    return overlap
