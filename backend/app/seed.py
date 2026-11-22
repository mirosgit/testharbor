"""Demo data so a fresh install looks alive.

    python -m app.seed             # add the demo project (even if other data exists)
    python -m app.seed --if-empty  # only when there are no projects yet (used on container start)
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    AutomationComplexity,
    AutomationProgress,
    AutomationStatus,
    CaseState,
    CaseType,
    Priority,
    Project,
    ResultStatus,
    RunCase,
    RunSource,
    Section,
    Suite,
    TestCase,
    TestResult,
    TestRun,
)

A, M, T = AutomationStatus.automated, AutomationStatus.manual, AutomationStatus.to_be_automated
P = Priority
CT = CaseType

# (title, priority, type, tags, automation, automation_key, steps)
# steps: list of (action, expected)
DEMO: dict[str, dict[str, list[tuple]]] = {
    "Web App": {
        "Authentication/Login": [
            ("Login with valid email and password", P.critical, CT.smoke, ["auth", "smoke"], A,
             "tests/web/test_auth.py::test_login_valid",
             [("Open /login", "Login form is shown"),
              ("Enter a registered email and the correct password", "Fields accept input"),
              ("Click **Sign in**", "User lands on the dashboard; avatar is shown in the header")]),
            ("Login fails with wrong password", P.high, CT.functional, ["auth", "negative"], A,
             "tests/web/test_auth.py::test_login_wrong_password",
             [("Enter a registered email and a wrong password", ""),
              ("Click **Sign in**", "Error `Invalid email or password` is shown; no session cookie is set")]),
            ("Account locks after 5 failed attempts", P.high, CT.security, ["auth", "security"], T, None,
             [("Fail login 5 times in a row for the same account", "Each attempt shows a generic error"),
              ("Try the correct password", "Message says the account is locked for 15 minutes")]),
            ("Remember me keeps the session after browser restart", P.medium, CT.functional, ["auth"], M, None,
             [("Log in with **Remember me** checked", ""),
              ("Close and reopen the browser", "User is still logged in")]),
            ("Logout clears the session", P.high, CT.smoke, ["auth", "smoke"], A,
             "tests/web/test_auth.py::test_logout",
             [("Click avatar → **Log out**", "Redirected to /login"),
              ("Press browser Back", "Protected page is not shown")]),
        ],
        "Authentication/Registration": [
            ("Register a new account", P.critical, CT.smoke, ["auth", "smoke"], A,
             "tests/web/test_signup.py::test_signup_happy_path",
             [("Open /signup and fill in name, email, password", ""),
              ("Submit the form", "Confirmation email is sent; user sees *Check your inbox*")]),
            ("Registration rejects an already used email", P.medium, CT.functional, ["auth", "negative"], A,
             "tests/web/test_signup.py::test_signup_duplicate_email",
             [("Submit the form with an existing email", "Inline error *Email is already registered*")]),
            ("Password strength meter", P.low, CT.functional, ["auth", "ux"], M, None,
             [("Type `abc`", "Meter shows *Weak*"), ("Type `Tr0ub4dor&3xyz`", "Meter shows *Strong*")]),
        ],
        "Authentication/Password reset": [
            ("Request password reset email", P.high, CT.functional, ["auth"], T, None,
             [("Click **Forgot password?** and enter email", "Generic success message regardless of whether the email exists")]),
            ("Reset link expires after 1 hour", P.medium, CT.security, ["auth", "security"], M, None,
             [("Open a reset link older than 1 hour", "Page says the link has expired and offers to resend")]),
        ],
        "Catalog/Search": [
            ("Search by product name", P.high, CT.smoke, ["catalog", "smoke"], A,
             "tests/web/test_search.py::test_search_by_name",
             [("Type `headphones` into the search box and press Enter", "Results contain only matching products")]),
            ("Search with no results shows suggestions", P.low, CT.functional, ["catalog", "ux"], M, None,
             [("Search for `zzzzqqq`", "Empty state with popular categories is shown")]),
            ("Filter results by price range", P.medium, CT.functional, ["catalog"], A,
             "tests/web/test_search.py::test_filter_price",
             [("Set price from 50 to 100", "All shown prices are within 50–100"),
              ("Clear the filter", "Full result list is restored")]),
            ("Sort results by rating", P.low, CT.regression, ["catalog"], T, None,
             [("Choose *Sort: Rating*", "Products are ordered by rating, highest first")]),
        ],
        "Catalog/Product page": [
            ("Product page shows price, stock and gallery", P.high, CT.functional, ["catalog"], A,
             "tests/web/test_product.py::test_product_page",
             [("Open any in-stock product", "Price, *In stock* badge and at least one image are visible")]),
            ("Out of stock product cannot be added to cart", P.high, CT.regression, ["catalog", "cart"], M, None,
             [("Open an out-of-stock product", "**Add to cart** is disabled; *Notify me* is shown")]),
        ],
        "Cart & Checkout/Cart": [
            ("Add product to cart", P.critical, CT.smoke, ["cart", "smoke"], A,
             "tests/web/test_cart.py::test_add_to_cart",
             [("Click **Add to cart** on a product page", "Cart badge shows 1"),
              ("Open the cart", "Product, quantity 1 and correct subtotal are shown")]),
            ("Change quantity in cart", P.medium, CT.functional, ["cart"], A,
             "tests/web/test_cart.py::test_change_quantity",
             [("Set quantity to 3", "Subtotal updates to 3 × price")]),
            ("Cart persists for a logged-in user across devices", P.medium, CT.functional, ["cart"], M, None,
             [("Add an item on desktop", ""), ("Log in on mobile", "Same item is in the cart")]),
            ("Apply a discount code", P.high, CT.functional, ["cart", "promo"], T, None,
             [("Enter `WELCOME10`", "10% discount line appears; total is recalculated")]),
        ],
        "Cart & Checkout/Payment": [
            ("Pay with a valid card", P.critical, CT.smoke, ["checkout", "payments", "smoke"], A,
             "tests/web/test_checkout.py::test_pay_with_card",
             [("Proceed to checkout and enter test card `4242 4242 4242 4242`", ""),
              ("Confirm the order", "Order confirmation page with order number is shown")]),
            ("Declined card shows a clear error", P.high, CT.functional, ["checkout", "payments", "negative"], A,
             "tests/web/test_checkout.py::test_declined_card",
             [("Use test card `4000 0000 0000 0002`", "Error *Your card was declined*; order is not created")]),
            ("3-D Secure challenge flow", P.high, CT.functional, ["checkout", "payments"], M, None,
             [("Use a 3DS test card", "Challenge modal opens"),
              ("Complete the challenge", "Order is placed")]),
        ],
    },
    "Public API": {
        "Auth API": [
            ("POST /auth/token returns a JWT for valid credentials", P.critical, CT.smoke, ["api", "auth"], A,
             "tests/api/test_auth_api.py::test_token_ok",
             [("POST valid credentials", "200, body has `access_token` and `expires_in`")]),
            ("POST /auth/token returns 401 for invalid credentials", P.high, CT.functional, ["api", "auth", "negative"], A,
             "tests/api/test_auth_api.py::test_token_invalid",
             [("POST wrong password", "401 with error code `invalid_credentials`")]),
            ("Expired token is rejected", P.high, CT.security, ["api", "auth", "security"], A,
             "tests/api/test_auth_api.py::test_expired_token",
             [("Call any endpoint with an expired token", "401 `token_expired`")]),
        ],
        "Orders API": [
            ("Create order", P.critical, CT.smoke, ["api", "orders"], A,
             "tests/api/test_orders.py::test_create_order",
             [("POST /orders with a valid cart", "201 and `Location` header")]),
            ("List orders is paginated", P.medium, CT.functional, ["api", "orders"], A,
             "tests/api/test_orders.py::test_list_orders_pagination",
             [("GET /orders?limit=10", "At most 10 items and a `next` cursor")]),
            ("Cancel order within 30 minutes", P.medium, CT.functional, ["api", "orders"], T, None,
             [("POST /orders/{id}/cancel right after creating", "200, status `cancelled`")]),
            ("Order total uses server-side prices", P.high, CT.security, ["api", "orders", "security"], M, None,
             [("POST /orders with a tampered price", "Server ignores client price; total is correct")]),
            ("Rate limit returns 429", P.low, CT.performance, ["api"], M, None,
             [("Send 200 requests in 10 seconds", "Requests above the limit get 429 with `Retry-After`")]),
        ],
    },
}

FAILURES = [
    ("AssertionError: expected status 200, got 500",
     'Traceback (most recent call last):\n  File "tests/api/test_orders.py", line 42, in test_create_order\n'
     "    assert resp.status_code == 200\nAssertionError: expected status 200, got 500"),
    ("TimeoutError: locator('button:has-text(\"Sign in\")') not visible after 5000ms",
     "TimeoutError: waiting for locator('button:has-text(\"Sign in\")')\n    at tests/web/test_auth.py:18:11"),
    ("AssertionError: Subtotal mismatch: '$59.97' != '$59.98'",
     'File "tests/web/test_cart.py", line 77, in test_change_quantity\n    assert subtotal == expected'),
]

# A few cases that are not plain Active, so the dashboard and filters have something to show.
EXTRA: dict[str, dict[str, Any]] = {
    "Account locks after 5 failed attempts": {
        "state": CaseState.pending_review, "automation_progress": AutomationProgress.in_progress,
        "automation_complexity": AutomationComplexity.medium},
    "Reset link expires after 1 hour": {"state": CaseState.pending_review},
    "Cart persists for a logged-in user across devices": {"state": CaseState.pending_review},
    "Order total uses server-side prices": {"state": CaseState.draft},
    "Rate limit returns 429": {"state": CaseState.draft},
    "Password strength meter": {"state": CaseState.outdated},
    "Remember me keeps the session after browser restart": {
        "automation_progress": AutomationProgress.cannot_be_automated},
}
# Nightly failure chance per test; the rest fail rarely. "Create order" broke for a few days.
FLAKY = {"Change quantity in cart": 0.45, "Login fails with wrong password": 0.3}
BROKEN = [("Create order", 3, 6), ("Pay with a valid card", 31, 37)]  # title, failing from N to M days ago
OWNERS = ["Ana", "Ben", "Chen"]
PROGRESS = {A: AutomationProgress.automated, T: AutomationProgress.not_automated}


def _failure(c: TestCase, rnd: random.Random) -> tuple[str, str]:
    key = c.automation_key or ""
    for i, part in enumerate(("test_orders", "test_auth", "test_cart")):
        if part in key:
            return FAILURES[i]
    return rnd.choice(FAILURES)


async def seed(session: AsyncSession) -> Project:
    rnd = random.Random(42)
    now = datetime.now(UTC)
    project = Project(
        name="Demo Shop",
        description="Sample e-commerce project with web and API suites. Feel free to delete it.",
        roles=["Admin", "Customer", "Guest"],
    )
    session.add(project)
    await session.flush()

    cases: list[TestCase] = []
    for suite_name, sections in DEMO.items():
        suite = Suite(project_id=project.id, name=suite_name,
                      description=f"{suite_name} test cases")
        session.add(suite)
        await session.flush()
        section_ids: dict[str, int] = {}
        for path, rows in sections.items():
            parent_id = None
            parts = path.split("/")
            for depth in range(len(parts)):
                sub = "/".join(parts[: depth + 1])
                if sub not in section_ids:
                    sec = Section(suite_id=suite.id, parent_id=parent_id, name=parts[depth],
                                  position=len(section_ids))
                    session.add(sec)
                    await session.flush()
                    section_ids[sub] = sec.id
                parent_id = section_ids[sub]
            for pos, (title, prio, ctype, tags, auto, key, steps) in enumerate(rows):
                c = TestCase(
                    project_id=project.id, suite_id=suite.id, section_id=parent_id, title=title,
                    preconditions="A registered user `demo@example.com` exists." if "auth" in tags else "",
                    steps=[{"action": a, "expected": e} for a, e in steps],
                    expected_result=steps[-1][1], priority=prio, type=ctype, tags=tags,
                    automation_status=auto, automation_key=key, position=pos,
                    owner=OWNERS[len(cases) % len(OWNERS)], updated_by=OWNERS[len(cases) % len(OWNERS)],
                    sprint="Sprint 15" if len(cases) % 4 == 0 else "Sprint 14",
                    roles=["Customer"] if suite_name == "Web App" else ["Admin"],
                    created_at=now - timedelta(days=60),
                    updated_at=now - timedelta(days=len(cases) * 7 % 20 + 1, hours=len(cases) % 9),
                    **({"automation_progress": PROGRESS.get(auto)} | EXTRA.get(title, {})),
                )
                session.add(c)
                cases.append(c)
    await session.flush()

    automated = [c for c in cases if c.automation_status == AutomationStatus.automated]
    # Six weeks of nightly CI runs before the two named ones below.
    nightlies = [
        (f"Nightly #{213 - k}", RunSource.ci, automated, now - timedelta(days=k, hours=2), True, 1.0,
         {"branch": "main", "commit": f"{rnd.getrandbits(28):07x}",
          "build_url": f"https://ci.example.com/builds/{213 - k}"})
        for k in range(42, 1, -1)
    ]
    runs_spec = [
        *nightlies,
        ("Regression — release 1.4", RunSource.manual, cases, now - timedelta(days=9), True, 1.0, {}),
        ("Nightly #212", RunSource.ci, automated, now - timedelta(days=1, hours=2), True, 1.0,
         {"branch": "main", "commit": "9f3c2ab", "build_url": "https://ci.example.com/builds/212"}),
        ("Nightly #213", RunSource.ci, automated, now - timedelta(hours=3), False, 1.0,
         {"branch": "main", "commit": "a41be07", "build_url": "https://ci.example.com/builds/213"}),
        ("Smoke — release 1.5", RunSource.manual, [c for c in cases if c.type == CaseType.smoke],
         now - timedelta(hours=1), False, 0.5, {}),
    ]
    for name, source, run_cases, created, closed, done_ratio, ci in runs_spec:
        run = TestRun(project_id=project.id, name=name, source=source, created_at=created,
                      closed=closed, closed_at=created + timedelta(hours=6) if closed else None,
                      description="Created by the demo seed." if source == RunSource.manual else "", **ci)
        session.add(run)
        await session.flush()
        for i, c in enumerate(run_cases):
            status = ResultStatus.untested
            if i < len(run_cases) * done_ratio:
                roll = rnd.random()
                if source == RunSource.ci:
                    age = (now - created).days
                    fail = FLAKY.get(c.title, 0.03 if age < 30 else 0.07)
                    if any(c.title == t and lo <= age <= hi for t, lo, hi in BROKEN):
                        fail = 1.0
                    status = (ResultStatus.failed if roll < fail else
                              ResultStatus.skipped if roll < fail + 0.03 else ResultStatus.passed)
                else:
                    status = (ResultStatus.failed if roll < 0.1 else ResultStatus.blocked if roll < 0.16
                              else ResultStatus.retest if roll < 0.2 else ResultStatus.passed)
            session.add(RunCase(run_id=run.id, case_id=c.id, status=status))
            if status == ResultStatus.untested:
                continue
            err = _failure(c, rnd) if status == ResultStatus.failed else (None, None)
            if status == ResultStatus.failed and source == RunSource.manual:
                err = ("Actual result differs from expected — see comment.", None)
            session.add(TestResult(
                run_id=run.id, case_id=c.id, status=status,
                duration_ms=rnd.randint(300, 9000) if source == RunSource.ci else None,
                error_message=err[0], stack_trace=err[1],
                comment="Blocked by staging outage" if status == ResultStatus.blocked else None,
                created_at=created + timedelta(minutes=5 + i),
            ))
    await session.commit()
    return project


async def main(if_empty: bool) -> None:
    async with SessionLocal() as session:
        if if_empty:
            if not get_settings().seed_demo:
                print("seed: SEED_DEMO is off, skipping")
                return
            count = await session.scalar(select(func.count()).select_from(Project))
            if count:
                print("seed: database already has data, skipping")
                return
        project = await seed(session)
        print(f"seed: created demo project #{project.id} '{project.name}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-empty", action="store_true", help="only seed when no projects exist")
    asyncio.run(main(parser.parse_args().if_empty))
