# Master Doc: Everything I've Done

(Source of truth for the resume tailor. Copy of the Claude Doc "Master Doc: Everything I've Done", synced Oct 21, 2026. To refresh: export the doc as Markdown and replace this file.)

## Writing rules
Short bullets that say what the thing is in plain words, then a number. No em dashes. Nothing goes on a resume unless I can explain it in a live conversation.

## Summary
- Guang Labs, Engineering Intern (May to Aug 2026): Built an async Gemini video/image classification API and an in-app notification system
- IDX Exchange, Data Science Intern (Jun to Aug 2026): Built a California home-price model, median error 8.64%
- CS 61A Course Staff , Jun to Aug 2026: Taught 4 weekly exam-prep sections, held office hours, helped write exam questions
- CDSS 198 Reader and Tutor, Aug 2026 to present: Careers seminar feedback plus Transfer Seminar exam reviews
- Fung Fellow, Health + Innovation, Aug 2026 to present: Team on The After Collective, an AI recovery coach for disaster survivors
- CSM Junior Mentor, Sep 2026 to present: Weekly Transfer Affinity section for CS 88 / DATA C88C
- SightLine (Open Projects, ML team), Fall 2026: ML pipeline for a smart-glasses daily recap app
- CS 189 course projects (Fall 2026): LLM Arena Leaderboard, Fashion-MNIST Rotation Robustness (see Projects)
- Projects: SB 79 analysis, Movie Genres, Housing Bias, Spam Classifier, California Housing, Scheme Interpreter, Ngordnet, Build Your Own World

## Education and coursework
UC Berkeley B.A. in Data Science (Applied Mathematics and Modeling domain emphasis), cumulative GPA 3.85, senior, expected graduation Dec 2027. Transferred in Fall 2025 from De Anza College (A.S. in Mathematics and Computer Science, GPA 3.92, Sep 2023 to Jun 2025).

Completed Berkeley courses (use full names, never course codes on resumes):
- Structure and Interpretation of Computer Programs (A-)
- Foundations of Data Science (A)
- Data Structures (A-)
- Principles and Techniques of Data Science (A-)
- Probability for Data Science (A)
- Introduction to Urban Data Analytics (A)

In progress (Fall 2026): Efficient Algorithms and Intractable Problems; Introduction to Machine Learning; Functional Programming and AI-Assisted App Development; Data Engineering; Fung Fellowship Seminar.

## Guang Labs (Engineering Intern, May to Aug 2026, Remote)
Guang Labs is an AI video platform: users upload video, the system ingests it, and the product supports search, highlights, Agent editing, and export. I worked in the guang-labs repo with Akin as mentor and reviewer, on two tickets. Stack: React and Vite frontend, FastAPI backend with Auth0 Bearer auth, Postgres, S3, SQS, Qdrant, SQL migrations.

### ENG-39: Video Domain Classification API
- Goal: a lightweight REST API that classifies images and videos into six domains with Gemini: sports_like, game_like, talk_like, narrative_like, music_like, other.
- Inputs: images, short videos of 10 seconds or less, and long videos sampled as random 10-second clips (1 to 10 segments by duration). Short videos over 10 seconds are trimmed to the first 10 seconds with a warning.
- Async flow: POST /api/video-domain/classify/submit returns a job_id; GET /api/video-domain/classify/jobs/{job_id} polls. Same Auth0 Bearer token as the rest of the API.
- Output per segment: domain, confidence (0 to 1), ad_or_intermission, up to 5 evidence strings, optional secondary_domain. Default model gemini-2.5-flash, default confidence threshold 0.55.
- Trust layer: a result is untrusted if confidence is under the threshold, evidence is empty, JSON validation fails, or domain is other with confidence under 0.7. Untrusted long-video results resample fresh windows (excluding prior ones), up to 10 attempts. Images and short videos never resample.
- Job store: a Postgres table with job_id, user_id, status, progress_pct, request_json, result_json, error_message, timestamps.
- Modules: prompt loader, Pydantic schemas, config, media resolver (local_path, s3_key, s3_url, http_url), trust evaluator, segment sampler (ffprobe duration, ffmpeg clip extraction), Gemini provider (inline bytes for small clips, File API for large), a deterministic fake provider for tests, a service orchestrator, and a progress module with per-item progress slices.
- Timeline: June 8 to 15 built the first version (38 passing tests). Code review found the production path still sent text segment refs instead of real media. July 2 to 20 fixed it: real media attached, auto-detected media type, resample loop, real call counting, all four source kinds, timeout wiring, granular progress, acceptance tests, a manual staging script. Result: 86 tests.
- Status: merged into main. Say "merged" on resumes, not "shipped to production".

### ENG-62: In-app notification framework
- Why: pipeline work is async, so after upload a video can be ingesting, processing, ready, or exported while the UI looks idle. V1 is an in-app inbox and bell only (no email, push, websockets, or admin UI).
- Schema: notifications table (nullable user_id, type, title, message, link_url, metadata, created_at, expires_at) with a unique index to block duplicates; notification_reads stores per-user read time so reading a global announcement does not hide it for others.
- API: list notifications, mark one read, mark all read, and an admin-only create. Six types: product_update, feature_update, video_processing_ready, video_processing_failed, export_ready, export_failed. Auth0 maps to internal user ids; users never see others' notices.
- Hooks: fire-and-forget emit helpers so a failed insert never fails ingest or export; wired into v1 ingest, v2 ingest, the V3 orchestrator, and V3 render jobs.
- Frontend: dashboard NotificationBell with unread badge, popover, mark one and mark all, deep links, 30-second React Query polling.
- Output: about 1,476 lines added across 17 files, tests for API, emit helpers, bell, and header. PR #42.
- Status: PR #42 merged, Jira ENG-62 Done on Aug 20, 2026. Say "merged", not "shipped to production".

### Early workshops (June 2)
- June 2: ran a user story and user flow workshop with Avery (mentor) before the build.

### What I learned
- How production ML systems connect frontend, APIs, workers, queues, databases, and storage.
- Embeddings and vector search (Qdrant); the pipeline uses off-the-shelf models, not fine-tuned ones.
- Migrations, idempotency, API scoping, and testing without live services using fake providers.

## IDX Exchange (Data Science Intern, Jun to Aug 2026, Remote)
Goal: predict the close (sale) price of California single-family homes from CRMLS MLS data. Mentor: Aidan. Each intern built an independent pipeline against shared rules: chronological split (no shuffling), no ListPrice or OriginalListPrice (target leakage), and R2 (log and dollar), MAPE, and MdAPE as metrics. MdAPE is the headline metric because ultra-luxury sales distort MAPE and dollar R2.

Final result: XGBoost (400 trees, depth 8, learning rate 0.05, seed 42), 10 features, tested on June 2026 (train Nov 2025 to May 2026): R2 log 0.9266, R2 dollar 0.8787, MAPE 12.33%, MdAPE 8.64%.

- Weeks 1 and 2: downloaded 7 to 8 months of CRMLS sold data over FTP; filtered to single-family residential (143K+ raw rows to about 71K); missingness audit of 68 fields; picked core features (living area, bedrooms, bathrooms, lot size, year built, latitude, longitude, close date). Caught a variable typo that had saved an unfiltered file.
- Week 3: dropped high-missingness columns and zero or garbage rows, capped lot size (99.9th percentile) and garage spaces, dropped implausible prices, log target, first chronological split (59,316 train, 12,000 test).
- Weeks 4 and 5, the leakage fix: first Linear Regression had dollar R2 of -4,646.95. Cause: outlier thresholds were computed on train and test combined before the split. Fix: split first, compute every threshold on train only, freeze, then apply to test. Dollar R2 went to -0.38 and MAPE fell from 47.75% to 37.86%. Random Forest then became best (R2 dollar 0.854, MdAPE 8.77%).
- Week 6: moved the cutoff forward one month. Added bed_bath_ratio and property_age (negligible effect). Added a school district feature: spatial join of 937 CA school districts, 5-fold out-of-fold target encoding on train and a frozen lookup on test. Linear Regression MdAPE went from 29.27% to 14.58%; Random Forest was roughly neutral.
- Week 7, XGBoost: tested three configs against Random Forest (MdAPE 8.73%): 300 trees depth 6 gave 9.01%; 600 trees depth 6 lr 0.05 gave 8.89%; 400 trees depth 8 lr 0.05 gave 8.64%. Depth mattered more than learning rate.
- Week 8, evaluation: retrained from scratch and matched results exactly (reproducibility). By price quintile, MdAPE ranged from 6.48% (middle band, $575K to $800K) to 12.95% (top band, $1.65M to $9M). Of 937 districts, 161 had at least 20 test homes; worst were low-volume coastal and resort markets (12 to 21%), best were high-volume suburbs (3.6 to 5%). The worst districts were not just luxury, so the two findings are independent.

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
- Placed on the team for The After Collective: a free, science-backed, trauma-informed AI recovery coach for disaster survivors, built with researchers at Stanford. It helps survivors complete recovery tasks such as room-by-room inventories of lost belongings for insurance or FEMA.
- Key challenges: context-aware recovery support, safe and private AI use, and agentic AI that carries out tasks end to end.
- User research: reached out to real wildfire survivors and interviewed them to learn what they experienced, which tools they relied on, and where they got their information, so the team understands who we are building for.
- Organized the team's documentation, from the canonical doc to weekly updates and test documentation.
- Update Oct 21, 2026: The team turned the insurance pain point into 3 AI-assisted solution ideas; I worked on one, a tool that gives each survivor a checklist based on their needs, one step at a time. No features built yet; concepts are early.
- Update Oct 15, 2026: Project focus so far is the person who runs the household's insurance claim after a wildfire. Insurance was the hardest practical problem in 2 of our first 3 interviews.
- Contacted two wildfire survivors, scheduled the interviews, drafted the interview questions, and conducted interviews with both (Oct 3). Led the Oct 12 interview with a Pacific Palisades survivor, real estate broker, and recovery-group board member. Four interviews documented in total.
- Attended the Sep 24 kickoff, the Oct 1 product deep dive, the product demo (asked questions about the product), and the Oct 8 check-in on recruiting and the beta plan. Sent the early scheduling emails to the partner.
- Product speccing: lined up and joined two working sessions with Abhi (Oct 12 and 13) on how the partner takes a feature from user feedback to a spec and a build. Wrote both up in the partner meeting notes.
- Team operations: DRI of the week for Week 7 and the Build and Learn assignment. Set up and formatted the team folder, then kept the running notes, canonical doc, interview notes, partner meeting notes, and weekly status updates current.
- Midpoint prep: with two teammates, built the five-slide discovery read-out and supporting few-pager for the Oct 19 to 20 midpoint.
- Update Oct 28, 2026: seven interviews documented through Oct 22 (Oct 3 x3, Oct 12, Oct 16, Oct 18, Oct 22). Led the Oct 12 and Oct 16 interviews. Interviewees on Oct 16, 18, and 22 gave early reactions to the three concepts (claim steps, resource evaluation, service-fit checks). Joined the Oct 13 product speccing session and took the action item to test the partner's recovery coach for gaps and feature ideas before its beta.
- Accuracy notes: concept reactions are early feedback from a few interviewees, not formal tests, so nothing here is a result. The curation pilots in the partner's staging were a teammate's work, not mine.

### CS 61A Undergraduate Course Staff , Jun to Aug 2026
- Course staff for Berkeley's intro CS course in Python, SQL, and Scheme.
- Sections and review work were in Python, Scheme, and SQL. Reinforced data structures like linked lists, trees, lists, and dictionaries, plus recursion, OOP, Scheme (tail calls, macros, cons/list/append), and SQL joins and aggregation (GROUP BY, HAVING vs WHERE). Hand-traced code with real numbers.
- Tailoring rule: keep the CS 61A resume bullet as written (taught 4 weekly exam-prep sections in Python, Scheme, and SQL, reinforcing linked lists, trees, lists, and dictionaries, held office hours, helped write midterm and final questions). Do not rewrite it.
- Taught 4 weekly exam-prep sections, held office hours, and handled regrade requests and extension approvals.
- Helped write midterm and final exam questions, led final review sessions, and helped review two assignments.
- Accuracy note: 200+ students is the total class size, not my personal caseload. Do not mention Gradescope autograders.

### CSM Junior Mentor, CS 88 / DATA C88C, Sep 2026 to present
- Teach one weekly Transfer Affinity section, reviewing the previous week's concepts and practice problems.

### CSM Socials task force (Fall 2026)
- Member of the CSM Socials task force.

### CDSS Dean's Cabinet, Transfer Representative, Fall 2026 to present
- Member of the cabinet. Met with the associate dean and other CDSS faculty and program leads to discuss broad issues around the data science major. Raised the articulation issue for transfer students with the cabinet. Nothing I changed or shipped yet, so keep this to one line: member of the cabinet.

## Projects

### Hindsight (Cal Hacks 13.0, Oct 2026, team project)
Stack: Claude, FastAPI, React, Apify, Factory Droid SDK, ASSIST, Supabase. Repo: Cal-Hacks-2026/Hindsight.
- A transfer planner for California community college students: shows which classes count toward a major using official ASSIST agreements, a plan for every term, GE progress, a class schedule view, campus opportunities, and an Ask panel. Every answer cites its source.
- My part: helped come up with the product idea, features, and vision, and gave feedback on how the interface could improve and how more useful features could be added. The team built it with Claude. I did not write the matcher or planner code.
- Grounded data: a Factory Droid agent starts the Apify scraper that pulls campus events and opportunities from real pages, so nothing is generated without evidence. Credit matching is deterministic code against ASSIST data, not a model guess.
- Team: Atishay (product, design, engineering), Amaan, Shiv (admissions input), and me. Built over the 3-day hackathon, splitting work by phase and leaving time to test with real users.
- Accuracy notes: no award or result is claimed. Do not say I built the backend.

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
- Works alongside the iOS team and the backend team (FastAPI, Supabase, Docker, orchestration, final assembly).
- Ideas I pitched, NOT built yet (keep off the resume): use CLIP to embed frames from short clips and cluster them so the recap covers the whole day; use CLIP's text encoder with descriptive phrases to prioritize clips.

### SB 79 Transit-Oriented Development Analysis (CYPLAN 101, Summer 2026)
Stack: ArcGIS Online, StoryMaps. Two-person group project.
- GIS eligibility engine flagging zoning features in the City of Los Angeles near qualifying transit stops under SB 79 (denser housing near transit). Final layer: 6,413 zoning features.
- Each feature characterized against four layers: opportunity areas, displacement-risk tracts, CalEnviroScreen 4.0, CAL FIRE fire hazard zones.
- Delivered a research paper, a policy brief, and an interactive StoryMap. I wrote Methods, Results, Discussion (limitations), Abstract, and Appendices.

### Movie Genre Classification (DSS Decal, Spring 2026)
Stack: Python, PyTorch, SentenceTransformers, scikit-learn, XGBoost, LightGBM. Repo: movie-genre-classification-nlp.
- Multi-label genre prediction on 42K+ MovieLens/TMDB films across 20+ genres. Parsed nested IMDb metadata with regex; engineered log budget and revenue and release-time features.
- Embedded title, tagline, and overview with MiniLM, MPNet, and e5-large-v2; compared Logistic Regression, XGBoost, and LightGBM.
- Handled class imbalance with a rare-genre cutoff and per-label threshold tuning. Macro F1 (the primary metric, so rare genres count equally) rose from 0.48 to 0.66; Micro F1 0.68.
- Logistic Regression on 1024-dim e5 embeddings beat the boosted trees and trained about 12x faster.

### Housing Price and Assessment Bias
Stack: pandas, NumPy, scikit-learn. Repo: housing-price-assessment-bias-public.
- Linear regression on 200K+ Cook County Assessor records with 15+ engineered features: log square footage, polynomial age and geographic terms, latitude x longitude interactions, one-hot road and garage features.
- Filtered non-arm's-length $1 sales so training mirrored real assessment practice. Test RMSE 0.562 with 4-fold cross-validation.
- Quantified over- and under-estimation across price bands, tying the model to documented inequities in property-tax assessment.

### CS 189 course projects (Fall 2026, PyTorch)
- LLM Arena Leaderboard (chatbot_arena notebook) and Fashion-MNIST Rotation Robustness (fashion_pt_2 notebook). Used torchvision for data loading. [MISSING: model training specifics; do not claim PyTorch model training on a resume until filled in.]
- PyTorch (Oct 21, 2026): I have experience with it and will keep using it; PyTorch stays on all four resumes' skills. [MISSING: specific PyTorch code I wrote.]

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
- Multi-word queries by set intersection; top-k most popular words in a category.
- Fixed a bug where synset IDs split across multiple lines were overwritten instead of merged, silently dropping hyponyms.

### Build Your Own World (Java)
- Dungeon crawler on the StdDraw tile engine: explore a procedurally generated world, fight enemies in quiz battles, collect health kits.
- Deterministic seed-based generation: non-overlapping rooms joined by L-shaped hallways along a Kruskal minimum spanning tree so every room is reachable.
- BFS for click-to-move pathfinding and enemy chasing; one precomputed BFS distance map for O(1) spawn-distance checks.
- Full-screen quiz-battle overlay that preserves world state; save/load stores the seed and move history and replays it to rebuild the exact world.
- Within 14 tiles by path, an enemy takes 2 steps for every 1 step the player takes. Touching an enemy starts a quiz battle with 100+ one-word trivia questions on CS 61B concepts. Health packs restore 20 HP.
- The question bank was generated with LLM assistance from 61B course material. Be ready to say this if asked.

## Earlier roles at De Anza
- Boundary.0, Secretary (Apr 2024 to Jun 2025): one of the club's first officers (helped launch it, not a co-founder); helped partner with 5+ companies across construction, finance, and computer science; organized launch and outreach events to grow a 120+ member community.
- Mentors at De Anza, Mentor (Sep 2024 to Apr 2025): mentored a first-generation nursing student over two quarters on course planning, transfer-credit policies, and academic pathways.
- De Anza Student Government, Programs Committee Intern (Feb 2024 to Feb 2025): planned and ran 5+ major campus events (Club Day, Spring Carnival, Resource Fair, Homecoming).
- Indian Students Association, Events Coordinator (Oct 2023 to Feb 2025): led the flagship Diwali celebration; coordinated 30+ volunteers; secured sponsorships and owned budget and vendors; drew 200+ attendees.
- Kirsch Center, Lab Technician Assistant (Dec 2023 to Mar 2024): worked in a team of about 30 restoring sustainability spaces.

## Resume versions
Four one-page LaTeX bases (SWE, DS, ML, PM) in resumes/. At most 3 projects per resume. ATS rules: single column, plain hyphen dates, Bachelor of Arts wording, comma-separated coursework, exact job keywords in Skills and bullets.

## Skills (only these may appear in a Skills section)
- Languages: Python, Java, C++, SQL, Scheme, TypeScript
- ML and data science: pandas, NumPy, scikit-learn, PyTorch, TensorFlow, XGBoost, LightGBM, SentenceTransformers, Embeddings, Cross-Validation, Feature Engineering, GeoPandas, Matplotlib, seaborn
- Backend and infrastructure: FastAPI, Pydantic, PostgreSQL, Auth0, AWS S3, Gemini API, REST APIs, pytest, ffmpeg, ffprobe, React, Background Jobs
- Product: User Research, User Interviews, Discovery Read-outs, Documentation, Cross-Functional Collaboration
- Developer tools: Git, GitHub, VS Code, IntelliJ, Jupyter, Google Colab, MATLAB, Cursor
- Fundamentals: Data Structures, Graph Algorithms, Complexity Analysis, OOP, Functional Programming
- GIS: ArcGIS Online, StoryMaps

## Background
Grew up in Vijayawada, India, where studying in the U.S. was almost unheard of. Started at community college with no roadmap. Transfer student. Current focus: Machine Learning Engineer roles. Interests: multimodal AI and reinforcement learning.
