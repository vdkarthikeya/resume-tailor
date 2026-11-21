"""A short cover email for one tailored resume. No model call: every fact comes from the job text and the finished PDF."""
from __future__ import annotations

NAME = "Dhana Karthikeya Ventrapragada"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build(company: str, role: str, keywords: list[str], pdf_text: str, base_name: str = "") -> dict:
    """Subject and body. Only keywords that really appear in the finished resume are named, at most three."""
    low = (pdf_text or "").lower()
    used, seen = [], set()
    for k in keywords or []:
        k = str(k).strip()
        if k and k.lower() not in seen and k.lower() in low:
            used.append(k)
            seen.add(k.lower())
        if len(used) == 3:
            break
    at = f" at {company}" if company else ""
    role_txt = role or "open"
    lines = [
        f"Hi,",
        "",
        f"I am applying for the {role_txt} role{at}. I am a senior at UC Berkeley studying Data Science and Applied Mathematics, and my resume is attached.",
    ]
    if used:
        lines.append(f"My experience with {_join(used)} matches what the role asks for.")
    lines += ["I would be glad to talk more.", "", "Thank you,", NAME]
    subject = f"{role_txt} application, {NAME}" if role else f"Application, {NAME}"
    body = "\n".join(lines)
    assert "—" not in body and "–" not in body
    return {"subject": subject, "body": body, "keywords": used}
