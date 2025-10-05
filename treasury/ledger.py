from datetime import datetime, timezone


class Ledger:
    """
    Handles logging of paid reimbursements into a separate 'LedgerLog' sheet
    using the structure of your Reimbursement sheet.
    """

    def __init__(self, handler, ledger_sheet_name="LedgerLog"):
        self.handler = handler
        self.ledger_sheet_name = ledger_sheet_name

        # Load or create the ledger worksheet
        try:
            self.ws = self.handler.spreadsheet.worksheet(ledger_sheet_name)
        except Exception:
            print(f"[INIT] Ledger sheet '{ledger_sheet_name}' not found — creating new one.")
            self.ws = self.handler.spreadsheet.add_worksheet(
                title=ledger_sheet_name, rows=500, cols=15
            )
            self.ws.update(
                "A1:J1",
                [[
                    "Timestamp (UTC)",
                    "Officer Name",
                    "Position",
                    "Payment Method",
                    "Amount ($)",
                    "Reason for Expenditure",
                    "Receipt Link",
                    "Budget Category",
                    "Reimb Row #",
                    "Processed By",
                ]],
            )

    # ----------------------------------------------------
    # Log entry based on reimbursement info
    # ----------------------------------------------------
    def log_paid(self, reimb_row: list, row_number: int, category: str, processed_by: str):
        """
        Add a row to the ledger when a reimbursement is marked paid.
        reimb_row: list of strings (raw data from reimbursement sheet row)
        row_number: int (the row number in the reimbursement sheet)
        category: str (the budget category it maps to)
        processed_by: str (Discord user or officer who clicked 'Mark Paid')
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            full_name = reimb_row[1] if len(reimb_row) > 1 else ""
            position = reimb_row[2] if len(reimb_row) > 2 else ""
            payment_method = reimb_row[4] if len(reimb_row) > 4 else ""
            amount = reimb_row[5] if len(reimb_row) > 5 else ""
            reason = reimb_row[7] if len(reimb_row) > 7 else ""
            receipt = reimb_row[8] if len(reimb_row) > 8 else ""

            entry = [
                timestamp,
                full_name,
                position,
                payment_method,
                amount,
                reason,
                receipt,
                category,
                row_number,
                processed_by,
            ]

            self.ws.append_row(entry, value_input_option="USER_ENTERED")
            print(f"[LEDGER] Logged: {full_name} | {category} | ${amount} | {processed_by}")

        except Exception as e:
            print(f"[ERROR] Failed to log ledger entry: {e}")

    # ----------------------------------------------------
    # Helpers for viewing or auditing
    # ----------------------------------------------------
    def last_entries(self, n=10):
        """Return the last n ledger entries."""
        try:
            rows = self.ws.get_all_values()
            return rows[-n:] if len(rows) > n else rows
        except Exception as e:
            print(f"[ERROR] Failed to fetch ledger entries: {e}")
            return []

    def find_by_name(self, name: str):
        """Find all reimbursements logged for a given person."""
        try:
            rows = self.ws.get_all_values()
            header = rows[0] if rows else []
            name_col = next((i for i, h in enumerate(header) if "officer" in h.lower()), 1)
            return [r for r in rows[1:] if len(r) > name_col and name.lower() in r[name_col].lower()]
        except Exception as e:
            print(f"[ERROR] Failed to search ledger: {e}")
            return []
