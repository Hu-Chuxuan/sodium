import numpy as np

def parse_value(val):
    if isinstance(val, str):
        val = val.strip()
        if val.startswith('$'):
            try:
                return float(val.replace('$', ''))
            except ValueError:
                return val
        if val.endswith('%'):
            try:
                return float(val.replace('%', '')) / 100
            except ValueError:
                return val
        try:
            return float(val)
        except ValueError:
            return val
    return val

def compare(a, b, rtol=1e-3, atol=0.5) -> bool:
    a = parse_value(a)
    b = parse_value(b)
    try:
        return np.isclose(float(a), float(b), rtol=rtol, atol=atol)
    except (ValueError, TypeError):
        try:
            a_dt = pd.to_datetime(a)
            b_dt = pd.to_datetime(b)
            return a_dt == b_dt
        except:
            return str(a).strip() == str(b).strip()