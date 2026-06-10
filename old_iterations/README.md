# Old iterations (archive)

These are earlier versions of the outreach script, kept only for reference. They are **not
maintained** — use `../icuniv_mailer.py` instead.

Rough chronology (oldest → newest):

| File | What it was |
|------|-------------|
| `Fetch.py` | First experiment — only fetched/generated professor research domains via Gemini (no sending). |
| `full.py` | Added email generation + sending via **SMTP** (`smtp-auth.iitb.ac.in`). |
| `mail_integration.py` | Switched sending from SMTP to the **Gmail API** (OAuth2). |
| `mail_all_dept.py` | Added multi-department context loading from `dept_pdfs/` + research summary JSON. |
| `full_sig_dept.py` | Department-aware version with the full HTML signature — the iteration just before the final. |

The final version (`icuniv_mailer.py`, formerly `Final_code.py`) builds on `full_sig_dept.py`
and adds Gmail `message_id` capture into `professors.csv` for reply tracking.
