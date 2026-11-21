"""Case text from the tests' code: docstrings, comments, test.step titles, annotations, Gherkin."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from testharbor_cli import collect, describe


def test_parse_doc_sections() -> None:
    doc = textwrap.dedent("""
        Applies a discount code at checkout.
        Only active codes count.

        Preconditions:
        - A cart with one product
        Steps:
        1. Open the cart -> The total is shown
        2. Enter SAVE10 and apply it
           Expected: the total drops by 10%
        3. Pay
        Expected result:
        The order total includes the discount.
    """)
    assert describe.parse_doc(doc) == {
        "description": "Applies a discount code at checkout.\nOnly active codes count.",
        "preconditions": "- A cart with one product",
        "steps": [
            {"action": "Open the cart", "expected": "The total is shown"},
            {"action": "Enter SAVE10 and apply it", "expected": "the total drops by 10%"},
            {"action": "Pay", "expected": ""},
        ],
        "expected_result": "The order total includes the discount.",
    }
    assert describe.parse_doc("") == {}
    assert describe.parse_doc("Just prose.") == {"description": "Just prose."}


def test_parse_doc_gherkin_lines() -> None:
    doc = "Discounts.\n\nGiven a cart\nWhen I apply SAVE10\nAnd I pay\nThen the total drops\nAnd a receipt is sent"
    assert describe.parse_doc(doc) == {
        "description": "Discounts.",
        "preconditions": "- Given a cart",
        "steps": [{"action": "When I apply SAVE10\nAnd I pay", "expected": "Then the total drops\nAnd a receipt is sent"}],
    }


def test_title_and_doc() -> None:
    assert describe.title_and_doc("Refunds a paid order.\n\nSteps:\n1. Refund") == ("Refunds a paid order", "Steps:\n1. Refund")
    assert describe.title_and_doc("Line one\nline two") == (None, "Line one\nline two")
    assert describe.title_and_doc("Steps:\n1. x") == (None, "Steps:\n1. x")


PW_SOURCE = """import { test, expect } from '@playwright/test';

/**
 * A customer applies a discount code.
 *
 * Preconditions:
 * - A cart with one product
 * @see https://example.com
 */
test('applies a code', { tag: '@smoke', annotation: { type: 'issue', description: 'SHOP-12' } }, async ({ page }) => {
  await test.step('Open the cart -> The total is shown', async () => {
    await page.goto('/cart');
  });
  await test.step("Apply \\"SAVE10\\"", async () => {
    // Expected: the total drops by 10%
    await test.step(`Type the code`, async () => {});
    await expect(page.getByText('(')).toBeVisible();
  });
});

// Just a comment above.
test('plain', async ({ page }) => {});

test('bare', async () => {});
"""


def test_playwright_catalog_reads_the_source(tmp_path: Path) -> None:
    (tmp_path / "cart.spec.ts").write_text(PW_SOURCE)
    listing = {"config": {"rootDir": str(tmp_path)}, "suites": [{"title": "cart.spec.ts", "file": "cart.spec.ts", "specs": [
        {"title": "applies a code", "file": "cart.spec.ts", "line": 10, "column": 1, "tags": ["@smoke"],
         "tests": [{"annotations": [{"type": "issue", "description": "SHOP-12"},
                                    {"type": "expected", "description": "The order is cheaper"}]},
                   {"annotations": [{"type": "issue", "description": "SHOP-12"}]}]},  # a second project
        {"title": "plain", "file": "cart.spec.ts", "line": 22, "column": 1, "tags": [], "tests": []},
        {"title": "bare", "file": "cart.spec.ts", "line": 24, "column": 1, "tags": [], "tests": []},
    ]}]}
    a, plain, bare = collect.playwright_catalog_from_list(listing, tmp_path)
    assert a["description"] == "A customer applies a discount code.\n\n- Issue: SHOP-12"
    assert a["preconditions"] == "- A cart with one product"
    assert a["steps"] == [
        {"action": "Open the cart", "expected": "The total is shown"},
        {"action": 'Apply "SAVE10"\n- Type the code', "expected": "the total drops by 10%"},
    ]
    assert a["expected_result"] == "The order is cheaper"
    assert plain["description"] == "Just a comment above." and "steps" not in plain
    assert bare["description"] == describe.source_note("cart.spec.ts", 24)


def test_pytest_rows() -> None:
    rows = [
        {"nodeid": "tests/test_orders.py::test_refund[a]", "file": "tests/test_orders.py", "line": 5,
         "doc": "Refunds a paid order.\n\nSteps:\n1. Refund it -> The money is back",
         "markers": [{"name": "parametrize", "args": []}, {"name": "regression", "args": []},
                     {"name": "case", "args": ["C7", 8]}]},
        {"nodeid": "tests/test_orders.py::test_refund[b]", "markers": [{"name": "smoke", "args": []}]},
        {"nodeid": "tests/test_orders.py::test_cancel", "file": "tests/test_orders.py", "line": 12, "markers": []},
        {"nodeid": "tests/test_checkout.py::test_discount_outline[x]", "markers": [{"name": "case:C9", "args": []}],
         "bdd": {"feature": "Discount codes", "feature_file": "features/checkout/discounts.feature",
                 "feature_description": "Customers pay less with a code.", "scenario": "Apply <code>",
                 "scenario_description": "", "line": 4, "tags": ["case:C9", "smoke"],
                 "steps": [["Given", "a cart"], ["When", "I apply <code>"], ["Then", "the total drops"]],
                 "example": {"code": "SAVE10"}}},
        {"nodeid": "tests/test_checkout.py::test_discount_outline[y]", "markers": [],
         "bdd": {"feature": "Discount codes", "feature_file": "features/checkout/discounts.feature",
                 "scenario": "Apply <code>", "steps": [], "example": {"code": "SAVE20"}}},
    ]
    refund, cancel, outline = collect.pytest_catalog_from_rows(rows)
    assert refund["title"] == "Refunds a paid order"
    assert refund["steps"] == [{"action": "Refund it", "expected": "The money is back"}]
    assert refund["description"] == describe.source_note("tests/test_orders.py", 5)
    assert refund["tags"] == ["regression", "smoke"] and refund["case_ids"] == [7, 8]
    assert cancel["title"] == "Cancel" and cancel["description"] == describe.source_note("tests/test_orders.py", 12)
    assert outline["title"] == "Apply <code>"
    assert outline["path"] == ["Checkout", "Discount codes"]
    assert outline["preconditions"] == "- Given a cart"
    assert outline["steps"] == [{"action": "When I apply <code>", "expected": "Then the total drops"}]
    assert outline["description"] == (
        "Customers pay less with a code.\n\nExamples:\n\n| code |\n|---|\n| SAVE10 |\n| SAVE20 |")
    assert outline["tags"] == ["smoke"] and outline["case_ids"] == [9]


def test_pytest_catalog_runs_the_plugin(tmp_path: Path) -> None:
    (tmp_path / "test_shop.py").write_text(textwrap.dedent('''
        import pytest

        @pytest.mark.case("C3")
        @pytest.mark.slow
        def test_pay():
            """Pays for an order.

            Expected result:
            The order is paid.
            """
    '''))
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    slow: slow\n    case: case\n")
    (test,) = collect.pytest_catalog(f"{sys.executable} -m pytest -p no:testharbor", tmp_path)
    assert (test["key"], test["title"], test["expected_result"], test["tags"], test["case_ids"]) == (
        "test_shop.py::test_pay", "Pays for an order", "The order is paid.", ["slow"], [3])


def test_pytest_catalog_reads_pytest_bdd(tmp_path: Path) -> None:
    pytest.importorskip("pytest_bdd")
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "cart.feature").write_text(textwrap.dedent("""
        @smoke
        Feature: Cart
          People keep products in a cart.

          @case:C5
          Scenario Outline: Add <count> products
            Given an empty cart
            When I add <count> products
            Then the cart has <count> products

            Examples:
              | count |
              | 1     |
              | 2     |
    """))
    (tmp_path / "test_cart.py").write_text(textwrap.dedent('''
        from pytest_bdd import given, parsers, scenarios, then, when

        scenarios("features/cart.feature")

        @given("an empty cart", target_fixture="cart")
        def cart():
            return []

        @when(parsers.parse("I add {count:d} products"))
        def add(cart, count):
            cart.extend([1] * count)

        @then(parsers.parse("the cart has {count:d} products"))
        def check(cart, count):
            assert len(cart) == count
    '''))
    (tmp_path / "pytest.ini").write_text("[pytest]\nbdd_features_base_dir = .\nmarkers =\n    smoke\n    case:C5\n")
    (test,) = collect.pytest_catalog(f"{sys.executable} -m pytest -p no:testharbor", tmp_path)
    assert test["title"] == "Add <count> products"
    assert test["path"] == ["Cart"]
    assert test["description"].startswith("People keep products in a cart.\n\nExamples:")
    assert test["preconditions"] == "- Given an empty cart"
    assert test["steps"] == [{"action": "When I add <count> products", "expected": "Then the cart has <count> products"}]
    assert test["case_ids"] == [5] and "smoke" in test["tags"]
