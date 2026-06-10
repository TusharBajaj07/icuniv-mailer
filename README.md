# ICUniv Mailer — AI-Personalised University Outreach

Automated outreach system that invites international professors/universities to host
**IIT Bombay students for summer research internships**. For each professor it:

1. **Researches their work** using Google's Gemini model with **Google Search grounding**,
   extracting three specific, current research domains.
2. **Validates** the research quality and skips professors with insufficient/generic data.
3. **Matches** those domains to the most relevant IIT Bombay department(s)/centre(s)
   (from `iitb_research_summary.json` + the PDFs in `dept_pdfs/`).
4. **Generates a tailored HTML email** that references the professor's domains and a concrete
   IIT Bombay research connection, signed by the assigned Internship Coordinator (IC).
5. **Sends it via the Gmail API** (OAuth2), embeds the institute logo, and logs everything.

Progress is tracked in `professors.csv` (`email_sent`, `message_id` columns) so the run is
**resumable** — already-sent professors are skipped on the next run.

---

## Project layout

```
icuniv_mailer.py            # Main script (run this)
iitb_research_summary.json  # Dept/centre research summaries used for matching
dept_pdfs/                  # One <Department>.pdf per dept, used as LLM context
logo.png                    # Institute logo embedded in the email signature
contacts.csv                # IC contact details (private — gitignored)
professors.csv              # Recipient list + send progress (private — gitignored)
old_iterations/             # Earlier versions of the script, kept for reference only
```

`*.example.csv`, `.env.example`, and `credentials.json.example` are committed templates —
copy them and remove the `.example` suffix to create your real (gitignored) files.

---

## Setup

### 1. Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Gemini API key
Copy `.env.example` → `.env` and paste a key from
[Google AI Studio](https://aistudio.google.com/app/apikey):
```
GEMINI_API_KEY="your-key"
```

### 3. Gmail API credentials (OAuth2)
1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project and
   **enable the Gmail API**.
2. Create an **OAuth client ID** of type *Desktop app* and download the JSON.
3. Save it as **`credentials.json`** in this folder (see `credentials.json.example` for shape).
4. On first run a browser window opens for you to authorise; a `token.json` is then cached
   for subsequent runs. The script requests only the `gmail.send` scope.

> The sender address/name are set in `icuniv_mailer.py` (`self.sender_email`,
> `self.sender_name`). Update them to your own.

### 4. Input data
- **`contacts.csv`** — IC directory. Columns: `name_IC, ph_no, linkedin_link`.
- **`professors.csv`** — recipients. Columns:
  `name, email, university, IC, email_sent, message_id`
  (`IC` must match a `name_IC` in `contacts.csv`; leave `email_sent`/`message_id` blank).

See the `*.example.csv` files for the exact format.

---

## Run
```bash
python icuniv_mailer.py
```
The campaign processes each professor (≤2.5 min timeout each), writes a detailed
`email_sending_log.json`, and updates `professors.csv` after every send. Re-run any time to
continue where it left off.

---

## Working with the CSV files

There are two CSVs. You can edit them in **Excel, Google Sheets, or any text editor** — just
keep the header row exactly as-is and **save as CSV (comma-separated)**. If a name contains a
comma, wrap the whole field in double quotes, e.g. `"Bernhard, Jennifer"`.

### `contacts.csv` — the IC directory
| Column | Meaning |
|--------|---------|
| `name_IC` | The IC's full name. **This is the key** other files refer to. |
| `ph_no` | Phone shown in the email signature. |
| `linkedin_link` | LinkedIn URL shown in the signature. |

Add one row per Internship Coordinator. Example:
```csv
name_IC,ph_no,linkedin_link
Tushar Bajaj,(+91) 90000 00000,https://www.linkedin.com/in/your-handle/
```

### `professors.csv` — the recipient list + send progress
| Column | Meaning |
|--------|---------|
| `name` | Professor's name (used to research them). |
| `email` | Where the invite is sent. |
| `university` | Their university (used to research them). |
| `IC` | **Must match a `name_IC` in `contacts.csv`** — decides whose signature is used. |
| `email_sent` | Auto-filled `True` after a successful send. **Leave blank** for new rows. |
| `message_id` | Auto-filled with the Gmail message ID after sending (see below). **Leave blank.** |

To add recipients, append rows and leave the last two columns empty. To **force a re-send**
to someone, clear their `email_sent` and `message_id` cells.

---

## Changing the Internship Coordinator (IC)

The IC controls the name, phone, and LinkedIn in the email body and signature.

1. **Pick the IC per professor** by setting the `IC` column in `professors.csv` to a name that
   exists in `contacts.csv`. Different professors can have different ICs.
2. **Add or edit an IC's details** by adding/editing a row in `contacts.csv`
   (`name_IC, ph_no, linkedin_link`).
3. **Fallback IC** — if a row's `IC` is blank or doesn't match any `name_IC`, the script uses a
   hardcoded default. To change it, edit the dictionary in `get_ic_info()` near the top of
   `icuniv_mailer.py` (currently set to Tushar Bajaj's details).
4. The **sender address/name** (the actual mailbox the email is sent from, e.g.
   `training@iitb.ac.in`) is separate from the IC and is set via `self.sender_email` /
   `self.sender_name` in `icuniv_mailer.py`.

---

## Message IDs & reply tracking

When Gmail accepts an email it returns a unique **message ID** (e.g. `19a511e096510bdd`). The
script captures it and writes it into the `message_id` column of `professors.csv`. It is used
for two things:

- **Resuming safely.** On the next run, any professor that already has `email_sent = True` is
  skipped, so you never double-mail someone — even if the campaign was interrupted.
- **Tracking replies & following up.** The message ID is the handle to that exact Gmail
  conversation (thread). With it you can later check whether the professor **opened or replied**,
  and send a follow-up **in the same thread**.

`professors.csv` already has a `message_id` column, so it plugs straight into the tracking and
follow-up scripts in the companion **`company-mailer`** repo:
- `track_status.py` — reads the `message_id` column and writes a `*_tracked.csv` marking each
  row as `REPLIED` / `READ` / `UNREAD`, with the latest reply's sender, date, and snippet.
- `followup.py` — paste a message ID to send a threaded follow-up reply.

---

## Notes & safeguards
- Professors whose best-matched department is **Humanities & Social Sciences** are skipped.
- Each professor is given a hard **150 s timeout** to avoid hanging on a slow API call.
- A 2 s delay is added between sends to stay under Gmail rate limits.
- Models used: `gemini-2.5-flash` (grounded research) and `gemini-2.5-flash-lite`
  (department matching + connection sentence).

## ⚠️ Security
Never commit `.env`, `credentials.json`, or `token.json` — they are gitignored. If any key
was ever committed or shared, **revoke/rotate it** (Gemini key in AI Studio, OAuth client in
Google Cloud Console).
