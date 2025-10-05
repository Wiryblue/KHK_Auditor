"""
Unified test suite for KHK Treasury Bot (offline-safe)
Run:  pytest -v test_treasury_bot.py
"""
import discord
import pytest
from unittest.mock import MagicMock, patch
       # <-- make sure this import is near the top of the file
from discord.ext import commands


from treasury.sheet_handler import SheetHandler
from treasury.ledger import Ledger
from treasury.cogs import reimburse

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------
# Fixtures
# -----------------------

@pytest.fixture
def mock_config():
    return {
        "spreadsheet_name": "FakeSheet",
        "budget_sheet_index": 0,
        "reimb_sheet_index": 1,
        "ledger_sheet_name": "LedgerLog",
        "treasurer_role_id": None,
    }


@pytest.fixture
def fake_handler(mock_config):
    """Build a SheetHandler with mocked gspread so no API call occurs."""
    with patch("treasury.sheet_handler.gspread.authorize") as mock_auth:
        fake_client = MagicMock()
        fake_spreadsheet = MagicMock()
        fake_client.open.return_value = fake_spreadsheet
        mock_auth.return_value = fake_client

        handler = SheetHandler(mock_config)

        # Mock Budget sheet
        fake_budget = MagicMock()
        fake_budget.row_count = 100
        fake_budget.col_count = 10
        fake_budget.get_values.return_value = [
            ["Category", "Allocated", "Amount Used", "Remaining"],
            ["Social Chair", "1000", "100", "900"],
            ["Rush events", "500", "0", "500"],
            ["Brotherhood Engagement Chair", "600", "200", "400"]
        ]

        # Mock Reimbursement sheet
        fake_reimb = MagicMock()
        fake_reimb.row_count = 100
        fake_reimb.col_count = 10
        fake_reimb.get_values.return_value = [
            ["Name", "Category", "Amount", "Paid", "Paid By", "Paid At"],
            ["John Doe", "Social", "50", "", "", ""]
        ]

        handler.budget_ws = fake_budget
        handler.reimb_ws = fake_reimb
        handler._budget_header_map = {
            "category": 1, "allocated": 2, "used": 3, "remaining": 4
        }
        handler._reimb_header_map = {
            "category": 2, "amount": 3, "paid": 4, "paid_by": 5, "paid_at": 6
        }

        return handler

# -----------------------
# Core Sheet Logic
# -----------------------

def test_add_to_budget_used_exact(fake_handler):
    ws = fake_handler.budget_ws
    fake_handler.add_to_budget_used("Social Chair", 50.0)
    ws.batch_update.assert_called_once()
    args = ws.batch_update.call_args[0][0]
    assert any("C" in u["range"] for u in args)


def test_add_to_budget_used_fuzzy(fake_handler):
    ws = fake_handler.budget_ws
    fake_handler.add_to_budget_used("Rush", 25.0)
    ws.batch_update.assert_called()


def test_category_not_found(fake_handler, capsys):
    ws = fake_handler.budget_ws
    ws.batch_update.reset_mock()
    fake_handler.add_to_budget_used("Unknown", 10.0)
    ws.batch_update.assert_not_called()
    out = capsys.readouterr().out
    assert "not found" in out.lower()


# -----------------------
# Mark-Paid + Ledger
# -----------------------

def test_mark_paid_and_sync_budget(fake_handler):
    fake_handler.reimb_ws.batch_update = MagicMock()
    fake_handler.add_to_budget_used = MagicMock()
    amt, cat = fake_handler.mark_paid_and_sync_budget(2, "Tester")
    assert isinstance(amt, float)
    assert isinstance(cat, str)
    fake_handler.reimb_ws.batch_update.assert_called()
    fake_handler.add_to_budget_used.assert_called()


def test_ledger_log_append(fake_handler):
    ledger = Ledger(fake_handler, "LedgerLog")
    ledger.ws = MagicMock()
    ledger.log_paid("Tester", "Social Chair", 50.0, 2)
    ledger.ws.append_row.assert_called_once()
    args = ledger.ws.append_row.call_args[0][0]
    assert "Tester" in args
    assert "Social" in args[3]


# -----------------------
# Discord Cog Flow
# -----------------------

@pytest.mark.asyncio
async def test_markpaid_command(monkeypatch):
    intents = discord.Intents.default()      # <-- comes from discord, not commands
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
