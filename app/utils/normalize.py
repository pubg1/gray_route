
import re
ABBR = {'abs': 'ABS','esp': 'ESP','epb': 'EPB',}
COMMON_MISSPELL = {'fa men': '阀门','famen': '阀门','you yi xiang': '有异响','youyixiang': '有异响',}
def fullwidth_to_halfwidth(s: str) -> str:
    res = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000: code = 0x0020
        elif 0xFF01 <= code <= 0xFF5E: code -= 0xFEE0
        res.append(chr(code))
    return ''.join(res)
def normalize_query(q: str) -> str:
    q = q.strip()
    q = fullwidth_to_halfwidth(q)
    q = re.sub(r"\s+", ' ', q)
    q = ''.join(ch.lower() if ord(ch) < 128 else ch for ch in q)
    for k, v in COMMON_MISSPELL.items(): q = q.replace(k, v)
    for k, v in ABBR.items(): q = re.sub(rf"\b{k}\b", v, q)
    return q
