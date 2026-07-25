class AmbiguousMatchError(Exception):
    """Raised when multiple open entries exist for a customer and cannot be uniquely matched."""
    def __init__(self, candidates):
        self.candidates = candidates
        super().__init__("Ambiguous match: multiple open entries found for customer")


def status_bn(due_amount_taka) -> str:
    """
    Compute status dynamically on every read:
    - due_amount_taka > 0 -> 'বাকি'
    - due_amount_taka == 0 -> 'পরিশোধিত'
    - due_amount_taka < 0 -> 'অগ্রিম' (overpayment/advance credit)
    """
    if due_amount_taka is None:
        return "বাকি"
    if due_amount_taka > 0:
        return "বাকি"
    if due_amount_taka == 0:
        return "পরিশোধিত"
    return "অগ্রিম"


def resolve_matched_entries(transaction: dict, db) -> list:
    if transaction.get("matched_entry_id") is not None:
        entry = db.get_entry(transaction["matched_entry_id"])
        if entry:
            return [entry]

    # Try name-based open entries lookup
    candidates = db.get_open_entries_by_name(transaction["customer_name"])
    if len(candidates) >= 1:
        if len(candidates) == 1:
            return candidates
        if transaction.get("full_settlement"):
            return candidates
        return [candidates[0]]

    # Fallback: if only 1 open entry exists in the entire database, return it
    if hasattr(db, "get_open_entries"):
        all_open = db.get_open_entries()
        if len(all_open) == 1:
            return all_open
        if len(all_open) > 1 and transaction.get("full_settlement"):
            return all_open

    raise ValueError(f"No open entry found for {transaction.get('customer_name')}")


def compute_ledger_update(transaction: dict, db=None, db_path: str = None) -> list:
    if db is None:
        target_path = db_path or "voice_khata.db"
        import ledger_db
        class LocalDBHelper:
            def __init__(self, p: str):
                self.p = p
            def get_entry(self, eid: int):
                return ledger_db.get_entry(eid, self.p)
            def get_open_entries_by_name(self, name: str):
                return ledger_db.get_open_entries_by_name(name, self.p)
            def get_open_entries(self):
                return ledger_db.get_open_entries(self.p)
        db = LocalDBHelper(target_path)

    t = transaction.get("transaction_type")

    if t == "new_sale":
        if transaction.get("due_amount_taka") is not None and transaction.get("paid_amount_taka") is not None:
            total = float(transaction.get("total_amount_taka") or 0.0)
            paid = float(transaction["paid_amount_taka"])
            due = float(transaction["due_amount_taka"])
        elif transaction.get("stated_due_taka") is not None:
            due = float(transaction["stated_due_taka"])
            total = float(transaction["total_amount_taka"]) if transaction.get("total_amount_taka") is not None else None
            paid = float(transaction["paid_now_taka"]) if transaction.get("paid_now_taka") is not None else None
        else:
            total = float(transaction.get("total_amount_taka") or 0.0)
            paid = float(transaction.get("paid_now_taka") or 0.0)
            due = total - paid
        return [{
            "op": "insert",
            "customer_name": transaction["customer_name"],
            "item": transaction.get("item"),
            "quantity": transaction.get("quantity"),
            "total_amount_taka": total,
            "paid_amount_taka": paid,
            "due_amount_taka": due
        }]

    if t == "update_existing":
        entries = resolve_matched_entries(transaction, db)
        if not entries:
            raise ValueError(f"No open entry found for {transaction.get('customer_name')}")
        updates = []
        for entry in entries:
            updated_item = transaction.get("item") or entry.get("item")
            updated_quantity = transaction.get("quantity") or entry.get("quantity")

            current_total = float(entry.get("total_amount_taka") or 0.0)
            current_paid = float(entry.get("paid_amount_taka") or 0.0)
            current_due = float(entry.get("due_amount_taka") or 0.0)

            if transaction.get("full_settlement"):
                new_total = current_total
                new_paid = current_total
                new_due = 0.0
            elif transaction.get("paid_amount_taka") is not None:
                # Explicit user confirmation/edit of absolute paid_amount_taka in Step 2!
                new_paid = float(transaction["paid_amount_taka"])
                new_total = float(transaction["total_amount_taka"]) if transaction.get("total_amount_taka") is not None else current_total
                if transaction.get("due_amount_taka") is not None:
                    new_due = float(transaction["due_amount_taka"])
                else:
                    new_due = new_total - new_paid
            elif transaction.get("stated_due_taka") is not None:
                new_total = float(transaction["total_amount_taka"]) if transaction.get("total_amount_taka") is not None else current_total
                new_due = float(transaction["stated_due_taka"])
                new_paid = new_total - new_due
            else:
                extra_charge = float(transaction.get("total_amount_taka") or 0.0)
                payment = float(transaction.get("paid_now_taka") or 0.0)

                new_total = current_total + extra_charge
                new_paid = current_paid + payment
                new_due = current_due + extra_charge - payment

            updates.append({
                "op": "update",
                "id": entry["id"],
                "customer_name": transaction.get("customer_name") or entry.get("customer_name"),
                "item": updated_item,
                "quantity": updated_quantity,
                "total_amount_taka": new_total,
                "paid_amount_taka": new_paid,
                "due_amount_taka": new_due
            })
        return updates

    raise ValueError(f"Unknown transaction_type: '{t}'")
