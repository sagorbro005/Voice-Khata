BANGLA_DIGITS = str.maketrans('0123456789', '০১২৩৪৫৬৭৮৯')

def to_bangla_number(n):
    """Convert any number or numeric string to Bangla numerals."""
    if n is None or n == "":
        return "-"
    # If float ends with .0, format as int
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    return str(n).translate(BANGLA_DIGITS)
