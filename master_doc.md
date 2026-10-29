# Master Doc: Everything I've Done

(Source of truth for the resume tailor. Synced Oct 28, 2026 from the Claude Doc "Master Doc: Everything I've Done" (rev 23), plus Oct 28 additions (Hindsight, Resume Tailor, Movie Genre fixes, CS 61A tailoring rule, Fung Oct 28 update, skills list), which were also added to the Claude Doc. To refresh: export the doc as Markdown and replace this file.)

## How to use this doc

This is the full-detail record behind my resumes and website. Those stay short; anything nitpicky lives here so nothing is lost. When I need a new bullet, I pull the facts from here and rewrite them in plain words.

| Role or project | One line |
|---|---|
| Guang Labs, Engineering Intern (May to Aug 2026) | Built an async Gemini video/image classification API and an in-app notification system |
| IDX Exchange, Data Science Intern (Jun to Aug 2026) | Built a California home-price model, median error 8.64% |
| CS 61A Course Staff (UCS1), Jun to Aug 2026 | Taught 4 weekly exam-prep sections, held office hours, helped write exam questions |
| CDSS 198 Reader and Tutor, Aug 2026 to present | Careers seminar feedback plus Transfer Seminar exam reviews |
| Fung Fellow, Health + Innovation, Aug 2026 to present | Team on The After Collective, an AI recovery coach for disaster survivors |
| CSM Junior Mentor, Sep 2026 to present | Weekly Transfer Affinity section for CS 88 / DATA C88C |
| SightLine (Open Projects, ML team), Fall 2026 | ML pipeline for a smart-glasses daily recap app |
| Projects | Hindsight, Resume Tailor, SB 79 analysis, Movie Genres, Housing Bias, Spam Classifier, California Housing, Scheme Interpreter, Ngordnet, Build Your Own World |

## Education and coursework

UC Berkeley B.A. in Data Science (Applied Mathematics and Modeling domain emphasis), cumulative GPA 3.85, senior, expected graduation Fall 2027 (Dec 2027). Transferred in Fall 2025 from De Anza College (A.S. in Mathematics and Computer Science, GPA 3.92, Sep 2023 to Jun 2025). Transcript shows 101.5 total units, 70 of them transfer units.

| Term | Course | Grade |
|---|---|---|
| Fall 2025 | CS 61A, Structure and Interpretation of Computer Programs | A- |
| Fall 2025 | DATA C8, Foundations of Data Science | A |
| Fall 2025 | MATH 98, Supervised Group Study | P |
| Spring 2026 | CS 61B, Data Structures | A- |
| Spring 2026 | DATA C100, Principles and Techniques of Data Science | A- |
| Spring 2026 | DATA C140, Probability for Data Science | A |
| Spring 2026 | CS 194, Special Topics | P |
| Spring 2026 | DATA 198 and INDENG 198, Directed Group Studies | P |
| Summer 2026 | CYPLAN 101, Introduction to Urban Data Analytics | A |
| Summer 2026 | DATA 197, Field Studies in Data Science | P |
| Fall 2026 | CS 170 Efficient Algorithms and Intractable Problems; CS 189 Introduction to Machine Learning; CS 194 Functional Programming and AI-Assisted App Development; DATA C101 Data Engineering; ENGIN 188 Fung Fellowship Seminar | In progress |

Note: resumes list full course names, never course codes.

## Guang Labs (Engineering Intern, May to Aug 2026, Remote)

Guang Labs is an AI video platform: users upload video, the system ingests it, and the product supports search, highlights, Agent editing, and export. I worked in the guang-labs repo with Akin as mentor and reviewer, on two tickets. Stack: React and Vite frontend (ui/), FastAPI backend (restapi/) with Auth0 Bearer auth, Postgres, S3, SQS, Qdrant, SQL migrations in dbscripts/.

### ENG-39: Video Domain Classification API

- **Goal:** a lightweight REST API that classifies images and videos into six domains with Gemini: sports_like, game_like, talk_like, narrative_like, music_like, other.
- **Inputs:** images, short videos of 10 seconds or less, and long videos sampled as random 10-second clips (1 to 10 segments by duration). Short videos over 10 seconds are trimmed to the first 10 seconds with a warning.
- **Async flow:** POST /api/video-domain/classify/submit returns a job_id; GET /api/video-domain/classify/jobs/{job_id} polls. Same Auth0 Bearer token as the rest of restapi.
- **Output per segment:** domain, confidence (0 to 1), ad_or_intermission, up to 5 evidence strings, optional secondary_domain. Prompt version video_domain_classifier.v1, default model gemini-2.5-flash, default confidence threshold 0.55.
- **Trust layer:** a result is untrusted if confidence is under the threshold, evidence is empty, JSON validation fails, or domain is other with confidence under 0.7. Untrusted long-video results resample fresh windows (excluding prior ones), up to 10 attempts. Images and short videos never resample.
- **Job store:** video_domain_jobs table (dbscripts/2026.1.6_video_domain_jobs.sql) with job_id, user_id, status, progress_pct, request_json, result_json, error_message, timestamps.
- **Modules:** prompt loader, Pydantic schemas, config, media resolver (local_path, s3_key, s3_url, http_url), trust evaluator, segment sampler (ffprobe duration, ffmpeg clip extraction), Gemini provider (inline bytes for small clips, File API for large), a deterministic fake provider for tests, a service orchestrator, and a progress module with per-item progress slices.
- **Timeline:** June 8 to 15 built prompts, schemas, config, resolver, trust, sampler, fake provider, Gemini provider, service, routes, migration (38 passing tests, 2 skipped because FastAPI was missing locally). Review found the production path still sent text segment refs instead of real media. July 2 to 20 fixed it: real media attached, auto-detected media type, resample loop, real call counting, all four source kinds, timeout wiring, granular progress, acceptance tests, a manual staging script. Result: 86 tests; commit d3383e8 (about 1,892 insertions) on branch ENG-39.
- **Status:** merged into main (confirmed Oct 8, 2026). Say "merged" on resumes and the website, not "shipped to production", since deployment is not something I can speak to.

### ENG-62: In-app notification framework

- **Why:** pipeline work is async, so after upload a video can be ingesting, processing, ready, or exported while the UI looks idle. V1 is an in-app inbox and bell only (no email, push, websockets, or admin UI).
- **Schema:** notifications (id, nullable user_id, type, title, message, link_url, metadata, created_at, expires_at) with a unique index on user_id, type, and metadata video_id to block duplicates; notification_reads stores per-user read_at so reading a global announcement does not hide it for others. Migration: dbscripts/2026.3.3_notifications.sql.
- **API:** GET /api/notifications, POST /api/notifications/{id}/read, POST /api/notifications/read-all, and admin-only POST /api/notifications. Six types: product_update, feature_update, video_processing_ready, video_processing_failed, export_ready, export_failed. Auth0 maps to internal users.id; users never see others' notices.
- **Hooks:** fire-and-forget emit helpers so a failed insert never fails ingest or export; wired into v1 ingest, v2 ingest, the V3 orchestrator, and V3 render jobs.
- **Frontend:** dashboard NotificationBell with unread badge, popover, mark one and mark all, deep links, 30-second React Query polling.
- **Output:** commit 5b79098, about 1,476 lines added across 17 files, tests for API, emit helpers, bell, and header. PR #42 opened.
- **Status:** PR #42 merged, and Jira ENG-62 moved from In Review to Done (resolution Done) on Aug 20, 2026, per Rick Chen's Jira update. Say "merged", not "shipped to production".

### What I learned

- How production ML systems connect frontend, APIs, workers, queues, databases, and storage.
- Embeddings and vector search (Qdrant), and that the pipeline uses off-the-shelf models (bge-base-en-v1.5, Whisper small, CLAP, VideoMAE, YAMNet tags), not fine-tuned ones.
- Migrations, idempotency, API scoping, and testing without live services using fake providers.
- Early workshops: on June 2 I joined the user story and user flow workshop for the website redesign and worked with Avery on the video processing flow (upload or link input, credit checks, clip length selection, processing-time messages). Learned how personas (vloggers, editors, creators) guide product decisions.

## IDX Exchange (Data Science Intern, Jun to Aug 2026, Remote)

Goal: predict the close (sale) price of California single-family homes from CRMLS MLS data. Mentor: Aidan. Each intern built an independent pipeline against shared rules: chronological split (no shuffling), no ListPrice or OriginalListPrice (target leakage), and R2 (log and dollar), MAPE, and MdAPE as metrics. MdAPE is the headline metric because ultra-luxury sales distort MAPE and dollar R2. Repo: vdkarthikeya/idx-summer2026.

### Final result

XGBoost (400 trees, depth 8, learning rate 0.05, seed 42), 10 features, tested on June 2026 (train Nov 2025 to May 2026): R2 log 0.9266, R2 dollar 0.8787, MAPE 12.33%, MdAPE 8.64%.

### Week by week

- **Weeks 1 and 2, setup and exploration:** downloaded 7 to 8 months of CRMLS sold data over FTP; filtered to Residential / SingleFamilyResidence (143K+ raw rows to about 71K); missingness audit of 68 fields; picked core features (LivingArea, bedrooms, bathrooms, LotSizeSquareFeet, YearBuilt, latitude, longitude, CloseDate). Caught a variable typo (sf vs sfr) that had saved an unfiltered file.
- **Week 3, preprocessing:** dropped high-missingness columns and zero or garbage rows, capped LotSize (99.9th percentile) and GarageSpaces, filled missing GarageSpaces with 0, dropped implausible prices, log1p target, first chronological split (59,316 train, 12,000 test).
- **Weeks 4 and 5, the leakage fix:** first Linear Regression had dollar R2 of -4,646.95. Cause: outlier thresholds were computed on train and test combined before the split. Fix: split first, compute every threshold on train only, freeze, then apply to test. Dollar R2 went to -0.38 and MAPE fell from 47.75% to 37.86%. Random Forest then became best (R2 dollar 0.854, MdAPE 8.77%).
- **Week 6, rolling-origin shift and features:** moved the cutoff forward one month. Added bed_bath_ratio and property_age (negligible effect). Added school_district_encoded: spatial join of 937 CA school districts, overlap duplicates resolved by first match, about 34 train and 4 test properties marked Unknown, 5-fold out-of-fold target encoding on train and a frozen lookup on test. Linear Regression MdAPE went from 29.27% to 14.58%; Random Forest was roughly neutral.
- **Week 7, XGBoost:** tested three configs against Random Forest (MdAPE 8.73%): v1 300 trees depth 6 lr 0.1 gave 9.01%; v2 600 trees depth 6 lr 0.05 gave 8.89%; v3 400 trees depth 8 lr 0.05 gave 8.64%. Depth mattered more than learning rate.
- **Week 8, evaluation:** retrained from scratch and matched results exactly (reproducibility). By price quintile, MdAPE ranged from 6.48% (Q2, $575K to $800K) to 12.95% (Q5, $1.65M to $9M). Of 937 districts, 161 had at least 20 test homes; worst were low-volume coastal and resort markets (12 to 21%), best were high-volume suburbs (3.6 to 5%). The 15 worst districts were not just luxury (Q5 33%, Q1 24%), so the two findings are independent. Saved metrics_summary.csv.
- **Week 9:** optional Streamlit app, skipped. **Week 10:** documentation. **Weeks 11 and 12:** presentations.

## Teaching, fellowship, and current roles

### CDSS 198 Transfer Seminar, Undergraduate Course Staff (Tutor), Aug 2026 to present

- Attend both weekly class meetings (Tuesdays and Wednesdays) to help student study groups work through material.
- Hold review sessions before exams for lower-division CS and data science courses, including CS 61A and Data 8.
- Create worksheets for the seminar's study sessions, hold weekly office hours, and give on-demand tutoring.
- Attend weekly staff meetings with the course supervisor to give feedback on student progress.

### CDSS 198 Careers in Data Science and Computing, Undergraduate Course Staff (Reader), Aug 2026 to present

- Facilitate group discussions and activities for a weekly seminar for CDSS undergraduates.
- Give feedback on development plans, resumes, and cover letters.
- Research and post job and internship listings on Ed Discussion, and help coordinate alumni and industry guest visits and CDSS Industry Nexus events.

### Fung Fellow, Health + Innovation track, Aug 2026 to present

- Selected for Berkeley's Fung Fellowship, which builds digital public-health tools with industry and community partners using human-centered design.
- Placed on the team for The After Collective: a free, science-backed, trauma-informed AI recovery coach for disaster survivors, built with researchers at Stanford's Department of Psychiatry and Center for AI for Mental Health. It helps survivors complete recovery tasks such as room-by-room inventories of lost belongings for insurance or FEMA.
- Key challenges: context-aware recovery support, safe and private AI use, and agentic AI that carries out tasks end to end.

**Update Oct 6, 2026: user research and documentation.**

- Reached out to real wildfire survivors and interviewed them to learn what they experienced, which tools they relied on, and where they got their information, so the team understands who we are building for.
- Organized the team's documentation, from the canonical doc to weekly updates and test documentation.

**Update Oct 15, 2026: what I did, pulled from the team's Drive docs (Weekly Shipped Log, Canonical, Partner Meeting Notes, Build + Learn).**

- Project focus so far: after a wildfire, the person who runs the household's insurance claim. Insurance was the hardest practical problem in 2 of our first 3 interviews. The team's current bullseye is a Palisades homeowner interviewed Oct 12 who spent months disputing his claim after conflicting advice from adjusters and advisers.
- User research: contacted two wildfire survivors, scheduled the interviews, drafted the interview questions, and conducted interviews with both (Oct 3). Led the Oct 12 interview with a Pacific Palisades survivor, real estate broker, and recovery-group board member. Four interviews documented in total (3 on Oct 3, 1 on Oct 12).
- Partner work: attended the Sep 24 kickoff, the Oct 1 product deep dive, the product demo (asked questions about the product), and the Oct 8 check-in on the Build and Learn assignment, recruiting, and the beta plan. Sent the early scheduling emails to the partner.
- Product speccing: lined up and joined two working sessions with Abhi (Oct 12 and 13) on how TAC takes a feature from user feedback to a spec and a build (question catalog of about 418 questions, a curation-import wizard built with Cursor). Wrote both up in the Partner Meeting Notes and Running Notes. Next: run simulator tests on the new catalog items and note gaps and ideas ahead of the beta.
- Team operations: DRI of the week for Week 7 (Oct 12) and the Build and Learn assignment. Set up and formatted the team folder, then kept the Running Notes, Canonical doc, interview notes, partner meeting notes, and Weekly Status Updates current; moved the Running Notes, Canonical doc, and Weekly Status Updates into Google Docs.
- Midpoint prep: with Sabrina and Peggy, built the five-slide discovery read-out and supporting few-pager for the Oct 19 to 20 midpoint, and updated all documentation to match the new bullseye.
- Accuracy notes: concepts in Build and Learn (Claim Roadmap, AfterVerify, Help That Fits) are early and not yet tested with real users, so nothing here is a result. The curation pilots in TAC staging (ALE and Section 16 question sets) were Peggy's work with Abhi, not mine. The shipped log says I conducted two Oct 3 interviews while the Canonical timeline words it loosely; the shipped log is the safer source.

**Update Oct 21, 2026: my part and what is not built.**

- The team found insurance was a pain point shared across survivor interviews and came up with 3 AI-assisted solution ideas. My own part is a checklist tool that gives each survivor a needs-based checklist, one step at a time.
- I have met with project partners and attended a demo on using AI tools to build features, but I have not built any features yet.
- Update Oct 28, 2026: seven interviews documented through Oct 22 (Oct 3 x3, Oct 12, Oct 16, Oct 18, Oct 22). Led the Oct 12 and Oct 16 interviews. Interviewees on Oct 16, 18, and 22 gave early reactions to the three concepts (claim steps, resource evaluation, service-fit checks). Joined the Oct 13 product speccing session and took the action item to test the partner's recovery coach for gaps and feature ideas before its beta.
- Drive check Oct 28, 2026 (Weekly Shipped Log, Research Plan, midpoint read-out deck, Oct 22 interview notes): the shipped log lists me as DRI of the week for Weeks 5 to 8 (Sep 28, Oct 5, Oct 12, Oct 19), not only Week 7. My Week 8 row in the log is still blank, so nothing is claimed for that week beyond being DRI.
- Midpoint read-out: the five-slide deck (Sabrina, Peggy and me) has a speaker script where I open with the hook slide, the Palisades homeowner's "frozen into immobility" quote and the bullseye (the person who runs the household's insurance claim after a California wildfire). The deck says six interviews and two concept walkthroughs. The shipped log schedules the partner meeting for the read-out on Oct 26, so do not claim it was presented to the partner unless I confirm.
- Oct 22 interview (Eaton Fire resident, Dawn): Peggy was the interviewer and Sabrina took notes; my role is not recorded. Do not say I led or attended it. Her reactions: favored Claim Roadmap or AfterVerify, and questioned Help That Fits and vendor reliability. Proposed team next step: have an insurance professional review the claims checklist.

### CS 61A Undergraduate Course Staff (UCS1), Jun to Aug 2026

- Course staff for Berkeley's intro CS course in Python, SQL, and Scheme.
- Taught 4 weekly exam-prep sections, held office hours, and handled regrade requests and extension approvals.
- Helped write midterm and final exam questions, led final review sessions, and helped review two assignments.
- Accuracy note: 200+ students is the total class size, not my personal caseload. Do not mention Gradescope autograders.
- Sections and review work were in Python, Scheme, and SQL. Reinforced data structures like linked lists, trees, lists, and dictionaries, plus recursion, OOP, Scheme (tail calls, macros, cons/list/append), and SQL joins and aggregation (GROUP BY, HAVING vs WHERE). Hand-traced code with real numbers.
- Tailoring rule: keep the CS 61A resume bullet as written (taught 4 weekly exam-prep sections in Python, Scheme, and SQL, reinforcing linked lists, trees, lists, and dictionaries, held office hours, helped write midterm and final questions). Do not rewrite it.

### CSM Junior Mentor, CS 88 / DATA C88C, Sep 2026 to present

- Teach one weekly Transfer Affinity section, reviewing the previous week's concepts and practice problems.

- Signed up for the Socials task force within CSM exec.

### CDSS Dean's Cabinet, Transfer Representative, Fall 2026 to present

- Member of the cabinet. Met with the associate dean and other CDSS faculty and program leads to discuss broad issues around the data science major. Nothing I changed or shipped yet, so keep this to one line on resumes and the website: member of the cabinet.

- Raised at the cabinet that community colleges lack articulated lower-division courses, so transfers retake them at Berkeley and lose time to explore opportunities. Narges agreed transfers should be able to start upper-division courses on arrival. This was a conversation, not a change I made yet.

## Projects

### Hindsight (Cal Hacks 13.0, Oct 2026, team project)
Stack: Claude, FastAPI (Python), React, TypeScript, Vite, Supabase, Apify, Factory Droid SDK, ASSIST, Render. Repo: Cal-Hacks-2026/Hindsight.
- A transfer planner for California community college students: shows which classes count toward a major using official ASSIST agreements, a plan for every term, GE progress, a class schedule view, campus opportunities, and an Ask panel. Every answer cites its source.
- My part: helped come up with the product idea, features, and vision, and gave feedback on how the interface could improve and how more useful features could be added. The team built it with Claude. I did not write the matcher or planner code.
- Grounded data: a Factory Droid agent starts the Apify scraper that pulls campus events and opportunities from real pages, so nothing is generated without evidence. Credit matching is deterministic code against ASSIST data, not a model guess.
- Team: Atishay (product, design, engineering), Amaan, Shiv (admissions input), and me. Built over the 3-day hackathon, splitting work by phase and leaving time to test with real users.
- Technical design (from the repo README, DECISIONS.md and tests; the team's system, not code I wrote): academic decisions come from deterministic code, not a model. A matcher handles course groups, alternatives, sequence rules, minimum grades, in-progress courses and agreement years, and flags renumbered or ambiguous courses; a planner schedules remaining major courses around prerequisites; GE progress checks each course against the college's Cal-GETC or IGETC list for the year it was taken. Claude only reads transcripts and class schedules (the student confirms every row), writes opportunity explanations and the University guide, and answers questions with numbered source citations that code validates.
- Grounding checks: a University guide item is dropped unless its quote appears on the cited page; missing dates stay empty; every listing links to its source page. Requirements come from the SJSU 2025-26 catalog; unclear items are marked for review instead of guessed.
- Droid agent: the Factory Droid SDK runs a background service that scans campus sources every two hours, ranks results and writes alerts. If a source returns nothing, Droid may repair only that source's extractor script, with a per-run patch budget; shell and web access are denied, repairs run in a sandboxed process without keys, and every plan, patch and result is logged to an events table.
- Design choices: no school is named in code (a campus registry file per school holds school-specific data); Apify's existing Cheerio Scraper Actor is used instead of building a custom one; all students get credits, GE and community-college terms, but only SJSU Data Science and Economics have a full plan, University guide and opportunities feed.
- Scale: about 28K lines of Python and TypeScript, with 450+ API tests and 24 agent tests. Atishay was the only coder and ran parallel Claude Code sessions; I did not write the code.
- Accuracy notes: no award or result is claimed. Do not say I built the backend, matcher, planner or agent. Say "co-designed" and describe the system as the team's.

### Resume Tailor (personal tool, Oct 2026)
Stack: Python, FastAPI, LaTeX, Claude. Repo: resume-tailor.
- A tool that takes a job link or pasted description and produces a tailored one-page PDF from my own LaTeX resumes. Four base resumes (SWE, DS, ML, PM); it picks the best one for the job.
- Built with Claude. I defined the problem (tailoring every application by hand took too long), the rules it must follow, and the checks, and I review and test it. Claude wrote most of the code. I should be able to explain the design in an interview.
- Safety design: my LaTeX is never regenerated; only bullet text, skills lines, coursework and project choices are replaced. Every rewritten bullet must carry verbatim quotes from this Master Doc, numbers must already exist in it, and banned claims are rejected. A rejected edit falls back to the original bullet.
- Checks: compiles the PDF and enforces one page with the page filled, an ATS keyword and parse check, a diff review panel, and an application tracker that logs each application to a Google Sheet and saves the PDF to Drive.
- Accuracy notes: personal tool, not a product with users. Do not claim I wrote all the code.

### SightLine (Open Projects, ML team, Fall 2026, in progress)

Stack: Python, PyTorch, OpenCV, YOLO. Repo: sightline-ml-public.

- A mobile app that connects to Meta Ray-Ban glasses, captures audio and video through the day, and outputs a 60-second edited recap.
- ML pipeline: pull footage, split into clips, rank clips with multimodal models on audio and visual cues, assemble the top clips through automated video rendering. The ML team builds and fine-tunes computer vision and audio scoring models.
- Works alongside the iOS team (app and Meta Wearables SDK) and the backend team (FastAPI, Supabase, Docker, orchestration, final assembly).

**Update Oct 6, 2026: PM meeting (ideas I pitched, not built yet).** These are proposals, so they stay off the resume until implemented.

- Use the CLIP model to sample frames from many short (about 5 second) clips and get an embedding for each. Visually similar clips land close together, so clustering them by location and scene gives a recap that covers everything in the day, not just one moment.
- Keep a list of descriptive phrases, turn them into vectors with CLIP's text encoder, and use them as blueprints: clips whose embeddings are very close to a phrase get priority in the recap.
- Note: the model I called "flip model" out loud is CLIP (confirmed Oct 15, 2026).

### SB 79 Transit-Oriented Development Analysis (CYPLAN 101, Summer 2026)

Stack: ArcGIS Online, StoryMaps. Two-person group project.

- GIS eligibility engine flagging zoning features in the City of Los Angeles near qualifying transit stops under SB 79 (denser housing near transit). Final layer: 6,413 zoning features.
- Each feature characterized against four layers: TCAC/HCD opportunity areas, displacement-risk tracts, CalEnviroScreen 4.0, CAL FIRE fire hazard zones.
- Delivered a research paper, a policy brief, and an interactive StoryMap. I wrote Methods, Results, Discussion (limitations), Abstract, and Appendices.

### Movie Genre Classification (DSS Decal, Spring 2026)
Data source (Oct 28, 2026): MovieLens and TMDB (with IMDb metadata fields), not Netflix. Name it "Movie Genre Classification (MovieLens/TMDB)" on resumes.
Stack: Python, PyTorch, SentenceTransformers, scikit-learn, XGBoost, LightGBM. Repo: movie-genre-classification-nlp.
- Multi-label genre prediction on 42K+ MovieLens/TMDB films across 20+ genres. Parsed nested IMDb metadata with regex; engineered log budget and revenue and release-time features.
- Embedded title, tagline, and overview with MiniLM, MPNet, and e5-large-v2; compared Logistic Regression, XGBoost, and LightGBM.
- Handled class imbalance with a genre-frequency cutoff (drop genres under 3,000 films, 20 to 14 genres) and one tuned global decision threshold (0.28). It was NOT per-genre thresholds (those are listed as future work in the repo), so never say "each genre its own cutoff". Macro F1 (the primary metric, so rare genres count equally) rose from 0.48 to 0.66; Micro F1 0.68. Note the label set shrank, so the 0.48 and 0.66 are not on identical labels.
- Models used: MiniLM (all-MiniLM-L6-v2), MPNet (all-mpnet-base-v2), e5-large-v2 embeddings; Logistic Regression (OneVsRest), XGBoost, LightGBM. Best: e5-large-v2 on title+tagline+overview with Logistic Regression. The model comparison table (LR 1 min, XGBoost 12 min, LightGBM 6 min; Macro F1 0.545, 0.528, 0.525) was run on MiniLM embeddings.
- Logistic Regression on 1024-dim e5 embeddings beat the boosted trees and trained about 12x faster.

### Housing Price and Assessment Bias

Stack: pandas, NumPy, scikit-learn. Repo: housing-price-assessment-bias-public.

- Linear regression on 200K+ Cook County Assessor records with 15+ engineered features: log square footage, polynomial age and geographic terms, latitude x longitude interactions, one-hot road and garage features.
- Filtered non-arm's-length $1 sales so training mirrored real assessment practice. Test RMSE 0.562 with 4-fold cross-validation.
- Quantified over- and under-estimation across price bands, tying the model to documented inequities in property-tax assessment.

### Email Spam / Ham Classifier

Stack: scikit-learn, pandas, NumPy. Repo: spam-ham-classifier-public.

- 50+ features from raw email text: regex counts (links, punctuation, dollar signs), HTML and subject-line indicators, log length, curated bag-of-words.
- L1-regularized Logistic Regression to keep only informative features, tuned with GridSearchCV and 10-fold cross-validation. 92.1% accuracy on a held-out leaderboard set, weighing precision against recall because false positives cost more.

### California Housing Regression

- Median home value prediction for 20K+ California block groups. Compared Linear Regression and k-Nearest-Neighbors on feature scaling, bias-variance tradeoff, and interpretability versus accuracy.

### Scheme Interpreter (Python)

- Interpreter for a Scheme subset built on a scheme_eval / scheme_apply cycle: lexically scoped environment frames, special forms (define, lambda, if, cond, let, quote, and/or), user-defined and built-in procedures, and tail-call optimization so deep recursion runs in constant stack space.

### Ngordnet (Java)

- Links a WordNet semantic graph with Google NGrams word-frequency data. Adjacency-list graph with recursive DFS and a visited set to find hyponyms; tests cover cycles, self-loops, diamonds, disconnected pieces, deep chains.
- Multi-word queries by set intersection; top-k most popular words in a category, with k=0 returning all hyponyms alphabetically.
- Fixed a bug where synset IDs split across multiple lines were overwritten instead of merged, silently dropping hyponyms.

### Build Your Own World (Java)

- Dungeon crawler on the StdDraw tile engine: explore a procedurally generated world, fight enemies in quiz battles, collect health kits.
- Deterministic seed-based generation: non-overlapping rooms joined by L-shaped hallways along a Kruskal minimum spanning tree so every room is reachable.
- BFS for click-to-move pathfinding (animated shortest path) and enemy chasing; one precomputed BFS distance map for O(1) spawn-distance checks so enemies and items spread evenly.
- Full-screen quiz-battle overlay that preserves world state; save/load stores the seed and move history and replays it to rebuild the exact world.
- Gameplay rules: 5 to 10 enemies and 4 to 8 health packs spawn per world, spread across the map by path distance. Within 14 tiles by path, an enemy takes 2 steps for every 1 step the player takes (it chases along the BFS shortest path). Touching an enemy starts a quiz battle.
- Quiz battle: 100+ one-word trivia questions on CS 61B concepts (Java, linked lists, inheritance, asymptotics, trees, graphs, hashing, sorting) plus 61B course and staff facts. Passive damage is 3 HP per second, a wrong answer costs 10 HP, and one correct answer defeats the enemy (enemy HP 20, correct answer deals 50). Health packs restore 20 HP; 5 lives, with HP restored to 100 on losing a life.
- The question bank was generated with LLM assistance (noted in the QuestionBank.java header) from 61B course material. Be ready to say this if asked.

### LLM Arena Leaderboard (CS 189 Homework 2, Fall 2026)

Stack: Python, scikit-learn, pandas, NumPy, Plotly. Course homework in a staff-provided notebook with fill-in sections.

- Used the public Arena human-preference battle data from Hugging Face: top 20 LLMs by battle count, about 40K battles (about 26K after removing ties).
- Computed pairwise win fractions and average win rates, then fit a Bradley-Terry model (logistic regression, no intercept, L2) to learn one strength score per LLM. Compared it against win rates on a held-out 20% of battles using log loss.
- Bootstrapped 200 resamples for confidence intervals and confidence-aware ranks.
- Found prompt topics with LSA (TruncatedSVD), K-Means, and a Gaussian mixture model, then compared leaderboards by topic.
- Built a style-controlled leaderboard using response length and bold, header, and list counts.
- [MISSING] Which parts I completed myself, and whether I did the custom style feature (Question 7).

### Fashion-MNIST Rotation Robustness (CS 189, Fall 2026)

Stack: Python, scikit-learn (MLPClassifier, MLPRegressor, LinearRegression), NumPy, Plotly, torchvision (loads the dataset). Course homework.

- Fashion-MNIST: 70K 28x28 grayscale clothing images in 10 classes. Trained a 2-layer MLP classifier, and a linear regression that predicts clothing price from image features (RMSE and MAE).
- The secret test set was rotated. Three fixes: train on randomly rotated augmented images; train a regressor that predicts the rotation angle and un-rotate test images before classifying; test-time augmentation.
- [MISSING] Final accuracy numbers for each fix.

## Earlier roles at De Anza

- **Boundary.0, Secretary (Apr 2024 to Jun 2025, Cupertino):** one of the club's first officers; helped partner with 5+ companies across construction, finance, and computer science; coordinated board meetings; organized launch and outreach events to grow a 120+ member community. Mission: connect students with industry opportunities.
- **Mentors at De Anza, Mentor (Sep 2024 to Apr 2025):** mentored a first-generation nursing student over two quarters on course planning, transfer-credit policies, and academic pathways; researched nursing programs, clubs, and internships for her; gave a steady, judgment-free space for guidance.
- **De Anza Student Government, Programs Committee Intern (Feb 2024 to Feb 2025):** planned and ran 5+ major campus events (Club Day, Spring Carnival, Resource Fair, Homecoming, de-stress events); negotiated the Spring Carnival photo-booth vendor, the highest-turnout activity; designed a Club Day game that drove new DASG sign-ups.
- **Indian Students Association, Events Coordinator (Oct 2023 to Feb 2025):** led the flagship Diwali celebration, the largest event of the year; coordinated 30+ volunteers across timed shifts; secured sponsorships and owned budget, vendors, and organizer communication; drew 200+ attendees.
- **Kirsch Center, Lab Technician Assistant (Dec 2023 to Mar 2024):** worked in a team of about 30 restoring sustainability spaces to pre-pandemic condition; seeded and maintained native plants and cleared bio-waste for on-campus food production; led tours for prospective environmental science students and planted wildflowers.

## Skills (only these may appear in a Skills section)
- Languages: Python, Java, C++, SQL, Scheme, TypeScript
- ML and data science: pandas, NumPy, scikit-learn, PyTorch, TensorFlow, XGBoost, LightGBM, SentenceTransformers, Embeddings, Cross-Validation, Feature Engineering, GeoPandas, Matplotlib, seaborn
- Backend and infrastructure: FastAPI, Pydantic, PostgreSQL, Auth0, AWS S3, Gemini API, Claude API, Apify, Factory Droid SDK, Supabase, Vite, REST APIs, pytest, ffmpeg, ffprobe, React, Background Jobs
- Product: User Research, User Interviews, Discovery Read-outs, Documentation, Cross-Functional Collaboration
- Developer tools: Git, GitHub, VS Code, IntelliJ, Jupyter, Google Colab, MATLAB, Cursor
- Fundamentals: Data Structures, Graph Algorithms, Complexity Analysis, OOP, Functional Programming
- GIS: ArcGIS Online, StoryMaps

## Background and rules

**PyTorch (Oct 21, 2026).** I have experience with PyTorch and will keep using it. Where it shows up in my work so far: SightLine (ML team stack), the Movie Genre embeddings (SentenceTransformers runs on PyTorch), and torchvision data loading in the CS 189 Fashion-MNIST homework. [MISSING] The specific PyTorch code I wrote, to name in an interview.

**Background (from the old About page).** Grew up in Vijayawada, India, where studying in the U.S. was almost unheard of. Started at community college with no roadmap, and figured most of the path out alone; family, especially my father, believed in it before I did. Learned most of what I know through coursework. Current focus: Machine Learning Engineer roles, later a pivot toward Machine Learning Research. Interests: multimodal AI and reinforcement learning.

**Writing rules I settled on.** Short bullets that say what the thing is in plain words, then a number. No em dashes. Nothing goes on a resume or site unless I can explain it in a live conversation.

**Resume versions.** I keep four role-tailored resumes: Software Engineer intern, Data Science, ML, and Product Manager. Four one-page LaTeX bases (SWE, DS, ML, PM) live in resumes/ in the resume-tailor repo. At most 3 projects per resume. ATS rules: single column, plain hyphen dates, Bachelor of Arts wording, comma-separated coursework, exact job keywords in Skills and bullets.
