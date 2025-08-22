import re

def parse_duration(time_str: str) -> int:
    """
    Parse a duration string like '15s', '10m', '1h' into seconds.
    Alias for parse_time for compatibility.
    """
    return parse_time(time_str)

def parse_time(time_str: str) -> int:
    """
    Parse a time string like '15s', '10m', '1h' into seconds.
    """
    if not isinstance(time_str, str):
        raise ValueError("Invalid time string format")

    match = re.match(r"(\d+)([smh])", time_str)
    if not match:
        raise ValueError("Invalid time string format")

    value, unit = match.groups()
    value = int(value)

    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    else:
        # This should not be reached due to the regex
        raise ValueError("Invalid time unit")
