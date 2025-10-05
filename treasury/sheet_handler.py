import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone
from gspread.utils import rowcol_to_a1


class SheetHandler:
    """
    Handles interaction with the single Google Sheet:
      - Budget sheet (index 0), header at row 8, data rows 9–36
      - Reinbursement sheet (index 1) — acts as inbox + ledger (Marked Paid column)
    """

    def __init__(self, config):
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        self.client = gspread.authorize(creds)

        ss_name = config["spreadsheet_name"]
        self.spreadsheet = self.client.open(ss_name)
        self.budget_ws = self.spreadsheet.get_worksheet(config["budget_sheet_index"])
        self.reimb_ws = self.spreadsheet.get_worksheet(config["reimb_sheet_index"])
        print(f"[INIT] Connected to: Budget='{self.budget_ws.title}', Reinbursement='{self.reimb_ws.title}'")

    # ----------- Helpers -----------
    def _normalize(self, s: str) -> str:
        return str(s).strip().lower()

    def _get_nonempty_rows(self, ws):
        """Return all rows that have at least one non-empty cell."""
        try:
            values = ws.get_all_values()
            return [r for r in values if any(c.strip() for c in r)]
        except Exception as e:
            print(f"[ERROR] Failed to read rows: {e}")
            return []

    # ----------- Data Accessors -----------
    def budget_rows(self):
        """
        Return rows only for the usable budget range.
        Row 8 is header → index 7; data rows 9–36 → indices 8..35.
        Returns a list whose [0] is the header (row 8).
        """
        rows_all = self._get_nonempty_rows(self.budget_ws)
        if len(rows_all) <= 7:
            return rows_all
        # Slice header (7) through row 36 (index 35) inclusive
        return rows_all[7:36]

    def reimb_rows(self):
        """Reinbursement sheet rows, with header on row 1 (index 0)."""
        return self._get_nonempty_rows(self.reimb_ws)

    def get_last_nonempty_row_index(self):
        """
        1-based index of last non-empty row in the Reinbursement sheet.
        Includes the header row if present.
        """
        try:
            rows = self.reimb_rows()
            last = len(rows) if rows else 1
            print(f"[DEBUG] Reinbursement last non-empty row: {last}")
            return last
        except Exception as e:
            print(f"[ERROR] Could not determine last row: {e}")
            return 1

    # ----------- Budget Update -----------
    def add_to_budget_used(self, category_name: str, amount: float):
        """
        Match an 'Office' (role) row and update:
         - 'Amount used' (+amount)
         - 'Remaining Balance' (= Allocated - Used)
        """
        if amount <= 0 or not category_name:
            return

        # Fuzzy canonical mapping (helps map Position -> Budget Office)
        CATEGORY_MAP = {
            # core chairs
            "academic": "Academic Chair",
            "athletic": "Athletic Chair",
            "computer": "Computer Chair",
            "dei": "DEI Chair",
            "expo": "Expo",
            "frat meal": "Frat Meal Chair",
            "meal": "Frat Meal Chair",
            "gopher": "Gopher",
            "house": "House Steward / Kitchen",
            "kitchen": "House Steward / Kitchen",
            "industry": "Industry Chair",
            "parliamentarian": "Parliamentarian",
            "philanthropy": "Philanthropy",
            "photographer": "Photographer",
            "pledge": "Pledge Trainer",
            "president": "President",
            "publicity": "Publicity Chair",
            "social": "Social Chair",
            "brotherhood": "Brotherhood Engagement Chair",
            "engagement": "Brotherhood Engagement Chair",
            "treasurer": "Treasurer",
            "vice": "Vice President",
            # budget events
            "rush": "Rush events",
            "popcorn": "Popcorn & Fun Night",
            "steak": "Steak dinner",
            # misc
            "float": "Float",
            "composite": "Composites",
            "subscription": "Subscription Services",
        }

        # Find the canonical target name
        norm_in = self._normalize(category_name)
        match = next((v for k, v in CATEGORY_MAP.items() if k in norm_in), category_name)

        # Budget headers + rows (header at index 0 in this slice)
        rows = self.budget_rows()
        if not rows or len(rows) < 2:
            print("❌ Budget rows unavailable.")
            return

        header = [h.strip().lower() for h in rows[0]]
        office_col = 0  # "Office"
        # "Amount" is allocated total, but **not** "Amount used" or "Remaining"
        alloc_col = next((i for i, h in enumerate(header) if "amount" in h and "used" not in h and "remain" not in h), 2)
        used_col = next((i for i, h in enumerate(header) if "used" in h), 4)
        remain_col = next((i for i, h in enumerate(header) if "remain" in h), 5)

        # Find row for that office
        target_row_index_in_slice = None
        for i, row in enumerate(rows[1:], start=2):  # sheet row number relative to slice header
            if len(row) > office_col and self._normalize(row[office_col]) == self._normalize(match):
                target_row_index_in_slice = i  # 1-based within the real sheet
                break

        if not target_row_index_in_slice:
            print(f"❌ Office not found in budget: {match}")
            return

        # Convert slice row -> real sheet row index
        # Slice starts at sheet row 8 → +7 offset
        real_row = 7 + target_row_index_in_slice

        def to_float(x):
            try:
                return float(str(x).replace("$", "").replace(",", "").strip())
            except Exception:
                return 0.0

        current_used = to_float(self.budget_ws.cell(real_row, used_col + 1).value)
        allocated = to_float(self.budget_ws.cell(real_row, alloc_col + 1).value)
        new_used = current_used + amount
        new_remain = allocated - new_used

        self.budget_ws.batch_update([
            {"range": rowcol_to_a1(real_row, used_col + 1), "values": [[new_used]]},
            {"range": rowcol_to_a1(real_row, remain_col + 1), "values": [[new_remain]]}
        ])
        print(f"[OK] Updated {match} (+${amount:.2f}) → used {new_used:.2f}, remain {new_remain:.2f}")
