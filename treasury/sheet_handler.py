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
        self.reimb_ws = self.spreadsheet.get_worksheet(config["reimb_sheet_index"])
        print(f"[INIT] Connected to: Reinbursement='{self.reimb_ws.title}'")

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


