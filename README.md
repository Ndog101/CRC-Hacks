<p align="center">
  <img src="assets/logo.png" alt="RiverRoute logo" width="120">
</p>

# RiverRoute

**Your professors. Your time. Your route.**

RiverRoute is a class-planning website for students of the Los Rios Community College District
(Cosumnes River, Sacramento City, American River, and Folsom Lake colleges). Search classes, compare
professors, build up to four schedules, and find out *before registration day* whether a schedule
actually works, including the drive or bus ride between campuses. **Rio**, a built-in AI guide powered by
the Google Gemini API, summarizes student reviews, compares your plans, and shows you around the site.

Built for the Cosumnes River College hackathon (November 2026), using Python and Streamlit.

> **Demo data notice:** the professors, ratings, reviews, seat counts, and most class times in this
> repository are **fictional sample data** for the demo, and travel times are approximate estimates. The site
> says so on every page. The app never contacts Los Rios or Rate My Professors while it runs
> (see [Data and terms of service](#data-and-terms-of-service)).

## What it does

**Find professors** (class search)
- Search by course code or name, instructor, or class number, with suggestions as you type.
- Filter by campus, mode (in person, partially online, online synchronous, online asynchronous), seat status,
  time of day and days, and minimum professor rating. Sort by rating, difficulty, or number of ratings.
- Each class card shows days and times, mode, and **seats in plain words**: green for open seats, yellow when
  the class is full but the waitlist has room (it shows your waitlist position), and red when the class and its
  waitlist are both full.
- A "What students say" bar under each card opens that professor's reviews (styled like Rate My Professors)
  and a **Summarize reviews with Rio** button (Gemini). Professors with no ratings show "N/A".
- **Add to plan** adds a class (a lecture and its lab are added together) to the plan you are working on.

**Build schedule**
- Up to four plans (A to D), switched from the bar under the top bar, with a health dot for each plan.
- A Monday to Friday calendar. Classes that overlap sit side by side. Commute time between campuses is drawn
  as a hatched block. Hover any class or commute block for all of its details.
- A **schedule check** sorts problems into three levels:
  - **Conflict** (red): classes overlap, the trip between campuses can't be made in time, or a class and its
    waitlist are both full.
  - **Risky** (gold): a tight trip, a full class with a waitlist, under 5 minutes between classes on the same
    campus, or details the schedule doesn't confirm (such as which days of a partially online class are on campus).
  - **Heads-up** (blue): few seats left, the same course twice, a 5 to 9 minute break, or a professor with no
    ratings yet.
- Choose **Car**, **Transit**, or a different one for each weekday. Trips are checked against both a typical
  time and a bad-day time, plus parking or waiting time.
- **Compare plans** puts two or three plans side by side with a table (the best value in each row gets a check
  mark), small calendars, and what differs between the plans, including each professor's rating.
- **Courses I must take** shows which required courses each plan is missing. **What matters most to me** lets
  you rank your priorities (best professors, easier classes, fewest days on campus, and so on) for Rio.

**Ask Rio** (floating chat on every page)
- Answers questions about your plans, professors, and how to use the site, using only the data on the page.
- Compares plans, weighing professor ratings and difficulty together with conflicts, commute, days on campus,
  your required courses, and your ranked priorities.

## How the AI is used

RiverRoute uses the **Google Gemini API** (`gemini-3.5-flash-lite` by default) in two places:

1. **Review summaries**: a short paragraph of what students say about a professor, written only from the
   reviews provided.
2. **Rio, the chat guide**: gets your plans, the checker's results, the class list, and a guide to the site as
   context, and answers in plain language.

All scheduling math (overlaps, travel time, seat levels, which plan wins a priority) is done by ordinary Python
in `scheduler.py`, not by the AI, so the AI explains results instead of inventing them. The AI is told not to
make up ratings, times, or section numbers. If the AI is unavailable (no key, free limit reached, no internet),
the rest of the site still works and a friendly message is shown.

## Run it on your computer

You need Python 3.12 or newer and a free Gemini API key.

1. **Get a free Gemini API key** at <https://aistudio.google.com/apikey>.
2. **Download the project** and open a terminal in its folder.
3. **Create your key file:** copy `.env.example` to a new file named `.env` and replace `your-key-here` with
   your key. The `.env` file is ignored by git, so your key is never uploaded.
4. **Install and start:**

   Windows (PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   streamlit run app.py
   ```

   macOS or Linux:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   streamlit run app.py
   ```

The site opens at <http://localhost:8501>. Without a key, everything works except Rio and the review summaries.

To use a different Gemini model, add `GEMINI_MODEL=model-name` to your `.env` file.

## Data and terms of service

The app reads hand-collected CSV files in `data/` and **never scrapes or contacts Los Rios, Rate My Professors,
or any other site while it runs.** The "Check live seats" link opens the official Los Rios class search in your
browser; it is a plain link.

| File | What it holds |
|---|---|
| `classes.csv` | One row per class meeting: `offering, course_code, course_name, class_number, component, professor, campus, mode, days, start_time, end_time, seats_open, waitlist`. Rows with the same `offering` are one card (for example a lecture and its lab). |
| `professors.csv` | `professor, rmp_rating, rmp_difficulty, would_take_again_pct, num_ratings`. Leave the numbers blank for a professor with no ratings. |
| `reviews.csv` | Sample student reviews, one row per review. |
| `campuses.csv` | Campus codes and names. |
| `travel_times.csv` | Typical and bad-day minutes between each pair of campuses, by car and by transit (estimates). |
| `meta.csv` | The date and time of the seat snapshot. |

Seat counts are a snapshot, not live. Professor names must be spelled the same in `classes.csv` and
`professors.csv`. When real data replaces the demo data, set `USING_SAMPLE_DATA = False` in `app.py` to remove
the demo banner.

RiverRoute is a student project. It is **not affiliated with** Los Rios Community College District, Cosumnes
River College, or Rate My Professors.

## Project layout

```
app.py             The website (pages, top bar, filters, plan bar, Rio chat)
scheduler.py       Schedule logic: overlaps, travel checks, seats, comparing plans, text for the AI
calendar_view.py   The weekly calendar and its hover boxes
review_view.py     Student review cards
ai_summary.py      Gemini calls: review summaries and Rio
data_loader.py     Reads the CSV files in data/
data/              The CSV data (see above)
assets/            Logo and Rio's icon
.streamlit/        Theme settings
```

## Tools and credits

- [Streamlit](https://streamlit.io) (web app), [pandas](https://pandas.pydata.org) (data),
  [python-dotenv](https://github.com/theskumar/python-dotenv) (reads the `.env` file)
- [Google Gemini API](https://ai.google.dev) through the `google-genai` Python package
- The logo and Rio's icon were drawn for this project as SVG files.
- The look of the review cards is inspired by Rate My Professors; no RMP data or code is used.

All of the code in this repository was written for this project. The dependencies above are installed from
PyPI and are not included in the repository.

## Known limits and future work

- Demo data only: real class, professor, and seat data would need a trusted source and an update routine.
- Only the four main Los Rios campuses are covered. Off-campus centers (for example Elk Grove) are not.
- Travel times are fixed estimates, not live traffic or live transit schedules. A real version could use a
  maps API.
- Seat counts are a snapshot taken by hand.
- Plans are kept in the browser session only, so they reset when the page is reloaded.
