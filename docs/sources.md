# Where these six trees came from

Each `data/domains/*.toml` carries its sourcing in a header comment. A UI edit
rewrites the whole file and **comments do not survive** (`writer.py` emits the
schema, not the prose). This file is the durable copy.

## Chinese — `chinese.toml`

**HSK 3.0**, the *Chinese Proficiency Grading Standards for International
Chinese Language Education*. Replaces the old 6-level HSK with **9 levels in
three bands**: Foundational (1–3), Developmental (4–6), Proficiency (7–9).

**Corrected July 2026.** The figures previously in this file were the **2021
proposal**, which the November 2025 CTI vocabulary syllabus superseded — the
counts came down substantially, and full implementation is July 2026. (The
previous version of this file claimed to have accounted for that revision while
still listing the 2021 numbers.) Current published figures:

| Level | Words (2021 proposal) | Words (current) |
|---|---|---|
| 1 | 500 | **300** |
| 2 | 1,272 | **500** |
| 3 | 2,245 | **1,000** |
| 4 | 3,245 | **2,000** |
| 5 | 4,316 | **3,600** |
| 6 | 5,456 | **5,400** |
| 7–9 | 11,092 | **11,000** |

Precise cumulative counts are 300 / 496 / 988 / 1,978 / 3,557 / 5,334 / 10,896;
the tree uses the rounded published figures. Per-level **character** counts are
now omitted from the tree entirely — the syllabus distinguishes recognition from
handwriting sets and I could not verify the split per level, so quoting the old
300/600/900… numbers would have been inventing precision.

Two structural facts that changed the tree's shape:

1. **HSK 7–9 is one exam**, not three. It is a single 98-question, ~210-minute
   paper across five sections (listening, reading, writing, translation,
   speaking), and your score decides which of the three certificates you get.
   The old tree modelled 7, 8 and 9 as sequential nodes each requiring the last,
   which would mean sitting the same paper three times. Now one node, `hsk7-9`.
2. **Speaking is examined from HSK 3**, via the mandatory HSKK oral exam, not
   from HSK 7. The old `speaking-band` node sat at tier 9 on the assumption that
   speaking arrives late. It is now `speaking-practice` at tier 6, entered right
   after HSK 2.

Assessment is four-dimensional: syllable, character, vocabulary, grammar.

- <https://www.chinesetest.cn/> — official registration and format
- <https://hskmock.com/> — official practice platform, real retired questions
- <https://ltl-school.com/new-hsk/>
- <https://hskstory.com/guides/what-is-hsk-30>
- <https://khanjischool.com/blog/chinese/new-hsk-30-2026-vocabulary-levels-exams-and-official-textbooks>

### On not being able to sit the exam

The domain is now built so that **no node requires an exam**. Every HSK level is
a `study` node whose gate is two unseen mock papers, timed and self-marked. This
is not a workaround — it follows from the README's own definition of the `exam`
kind ("scored by someone else, on their calendar"). If nobody else is scoring
you, it is not an exam, and calling it one made nine of the domain's thirteen
nodes depend on an institution.

The levels are *syllabi* as much as tests: word lists, grammar points and
retired papers are all published free. The one remaining `exam` node,
`certificate`, is terminal and nothing depends on it — sit it at whatever level
you have reached, if and when someone actually asks for the paper.

## Electric Guitar — `guitar.toml`

**Berklee College of Music**, guitar major, BPS sample curriculum (9 semesters).

The load-bearing fact, taken from Berklee's own Concentration Prerequisite
Guide: **OGUIT-121 Guitar Scales 101 and OGUIT-120 Guitar Chords 101 both
require OHARM-101 Music Theory 101 / OHARM-110 Getting Inside Harmony 1 first**
(or a Music Placement Test score of 60+). Theory gates the instrument. That is
the relationship hobbyist roadmaps invert, and it is why `harmony-1` is a hard
prerequisite of both technique nodes.

Structure: Private Lessons **levels 1–9** (OPLGT-101 … OPLGT-402) run every
semester alongside Harmony and Ear Training — three concurrent strands, which
is what forced the `strands` shape. All students take levels 1–4; performance
majors continue to 5–8. Every major requires **four semesters** of private
instruction, labs, and ensembles.

Course order sampled from the curriculum: Sem 1 Private Lessons 1 + Harmony;
Sem 2 Music Technology for Guitarists + Ear Training; Sem 3 Guitar Scales 101;
Sem 4 Guitar Chords 101; Sem 5 Getting Your Guitar Sound; Sem 6 Blues Guitar +
Acoustic Guitar Techniques; Sem 7 Solo Guitar; Sem 8 Guitar Chords 201 (chord
melody); Sem 9 Guitar Improvisation Techniques + Guitar Ensemble Techniques.

Style electives (the `style-lab` node): Country, Classic Rock, Metal,
Rhythm and Groove, Jazz Guitar 101/201, Funk/Rock and R&B Soloing, Acoustic and
Advanced Blues, Steve Vai Guitar Techniques.

- <https://college.berklee.edu/guitar/bachelor-of-music-in-performance-guitar>
- <https://assets.online.berklee.edu/Degree+Programs+Sample+Schedules/BPS4.OGUIT_Sample_Curriculum.pdf>
- <https://college.berklee.edu/guitar/principal>
- <https://college.berklee.edu/core-music-curriculum>

## Drumming — `drumming.toml`

**Berklee** drum set core. Fundamental snare technique — grip, sticking,
rhythmic studies, snare reading — plus a thorough study of the **26 American
drum rudiments** (the tree uses the full modern PAS 40). Named rudiments in the
syllabus: single and double stroke roll, paradiddle, double and triple
paradiddle, drag, drag paradiddle #1, flam, flam accent.

Progression: concept of time, grip, playing area, sound, hand balance → snare
reading and drum chart interpretation across **4/4, 2/4, 3/4, 6/8, 9/8, 12/8,
5/4** → two-, three- and four-way coordination, touch, balance, dynamics →
groove vocabulary in R&B, pop-rock, funk, rock, jazz, Brazilian and
Afro-Cuban.

Standard texts: George Lawrence Stone, *Stick Control*; Ted Reed, *Progressive
Steps to Syncopation* (used at Berklee as a reading and interpretation text).

- <https://college.berklee.edu/courses/ilpd-111>
- <https://online.berklee.edu/courses/drum-set-performance-101>
- <https://berkleepress.com/music/drums-percussion/>

## Electrical Engineering — `electrical-engineering.toml`

**MIT Course 6-5, Electrical Engineering with Computing** — which from Fall 2024
replaced 6-2 and retired 6-1 — plus the standard ABET BSEE spine.

Structure: a required foundation of five subjects in mathematics, programming
and algorithms, then three core system-design subjects, then an integrative
system design laboratory.

Core subjects the tree mirrors: **6.2000 Electrical Circuits: Modeling** (prereq
Physics II GIR); **6.002 Circuits and Electronics** — lumped circuit
abstraction, resistive networks, dependent sources, MOS transistors, the
digital abstraction, amplifiers, energy storage, first- and second-order
dynamics, time- and frequency-domain design; **6.003 Signals and Systems** —
discrete- and continuous-time representations, LTI systems, applications in
feedback and control, communications and signal processing; and
electromagnetics via quasistatic Maxwell and the Lorentz force law.

- <https://www.eecs.mit.edu/academics/undergraduate-programs/curriculum/6-5-electrical-engineering-with-computing/>
- <https://catalog.mit.edu/degree-charts/electrical-engineering-computing-course-6-5/>
- <https://ocw.mit.edu/courses/6-002-circuits-and-electronics-spring-2007/>
- <https://ocw.mit.edu/courses/6-003-signals-and-systems-fall-2011/>

## Software Development — `software-dev.toml`

**Teach Yourself Computer Science** — nine subjects, studied *roughly in the
presented order*: programming, computer architecture, algorithms and data
structures, math for CS, operating systems, computer networking, databases,
languages and compilers, distributed systems. TYCS recommends **100–200 hours
per subject**, which is where the session counts come from.

TYCS is explicitly aimed at competent programmers filling gaps, not at
beginners. Its own fallback advice — if nine subjects is too much, read
*Computer Systems: A Programmer's Perspective* and *Designing Data-Intensive
Applications* — is why `computer-architecture` and `databases` sit early and
carry weight.

The practitioner nodes (`shell-and-git`, `testing-debugging`, `code-review`,
`production-ops`, `own-in-production`) are **not** from TYCS. They are the
craft a CS curriculum omits, added because a tree of pure theory would have no
`social` nodes and no irreversible ones.

- <https://teachyourselfcs.com/>

## Filmmaking — `filmmaking.toml`

**AFI Conservatory**, Directing. First-year fellows direct **up to three
narrative short films — the "cycle films"** — with one-on-one mentorship (DIR
5571 / 5582 / 5583, Director's Prep) giving two mentor meetings per cycle film:
the first on script analysis and story, the second on the full range of
creative choice-making and a critique of the Director's Book. Second year is a
**thesis production** carrying full pre-production, production and
post-production responsibility, evaluated by senior faculty.

That structure — complete films, repeatedly, before you are ready — is the
whole justification for the `cycles` shape and for every edge into a cycle film
being **soft**.

Craft sequencing cross-checked against **NYU Tisch** undergraduate Film & TV,
which runs four stages (freshman, sophomore fundamentals, junior intermediate,
senior advanced) and orders its production core as **Sound Image → Frame and
Sequence → Fundamentals of Sight and Sound**, with sound continuing through
Sound Design I & II, Studio Recording, Sound Mixing Workshop. The senior
capstone Advanced Production Workshop is a year-long course producing shorts of
up to 15 minutes — the model for `cycle-3`.

- <https://conservatory.afi.com/directing-curriculum/>
- <https://conservatory.afi.com/directing-second-year/>
- <https://tisch.nyu.edu/film-tv/course-offering>
- <https://tisch.nyu.edu/film-tv/course-offering/areas>

---

## Materials — the `entry` field

Everything above is **provenance**: where each tree's *shape* came from. None of
it teaches anything. Berklee's sample-curriculum PDF tells you Guitar Chords 101
follows Harmony 1; it does not tell you what a drop 2 voicing is or where to
learn one.

`entry` is the other half, added because the trees were thoroughly sourced and
still unusable by anyone who did not already know the field. Every node in
`data/domains/` carries 3–5 lines: a canonical text, a free alternative, and
search strings that actually return the right thing.

**Cost, honestly, by domain:**

| Domain | Free ceiling | What money is unavoidable for |
|---|---|---|
| Electrical engineering | Very high — essentially the whole degree via MIT OCW, plus dspguide.com and allaboutcircuits.com as complete free texts | Atoms only: an FPGA board (~$30), a meter, a scope, a fab order (~$30) |
| Software development | Very high — OSTEP, Crafting Interpreters, SICP, the Google SRE books, MIT 6.824 and Missing Semester are all free and complete | Almost nothing. Two books (CS:APP, DDIA) and hosting |
| Drumming | High — the Vic Firth 40-rudiment hub is free and official | Two books (~$20 total), a pad and sticks (~$40), a kit eventually |
| Chinese | High — word lists, Grammar Wiki, HSK Mock, Pleco, Anki all free | Speaking partners (italki ~$10/hr), optionally one exam fee |
| Guitar | High — JustinGuitar, musictheory.net, Open Music Theory, jazzguitar.be | Leavitt's *Modern Method*; a teacher for the technique nodes is a real gap |
| Filmmaking | Medium — DaVinci Resolve and Blackmagic's six official training books are free, StudioBinder's templates are free | Sound gear (~$150–300, the highest-return spend here), festival fees, and above all *other people* |

The pattern worth noting: the **theory-heavy domains are nearly free and the
social ones are not**. What you cannot get free is rarely information — it is
feedback, an ensemble, a crew, an audience, someone senior watching you work.
That maps exactly onto the `social` nodes, which is a coincidence worth
distrusting slightly, but it held up across all six trees.

Key material sources, by domain:

- **Chinese** — <https://resources.allsetlearning.com/chinese/grammar> (Chinese
  Grammar Wiki, CC-licensed), <https://hskmock.com/>,
  <https://github.com/krmanik/HSK-3.0> (all nine levels as Anki decks),
  <https://www.hackingchinese.com/10-best-free-chinese-reading-resources-beginner-intermediate-advanced/>
- **Guitar** — <https://www.justinguitar.com/>, <https://www.musictheory.net/>,
  <https://viva.pressbooks.pub/openmusictheory/> (Open Music Theory v2),
  <https://www.jazzguitar.be/>, Leavitt *A Modern Method for Guitar* (the actual
  Berklee text)
- **Drumming** — <https://ae.vicfirth.com/education/40-essential-rudiments/>
  (all 40 PAS rudiments, free PDF, play-alongs and Wooton's lesson videos),
  <https://pas.org/publication-articles/new-approaches-to-reeds-syncopation-and-stones-stick-control/>,
  Stone *Stick Control*, Reed *Syncopation*
- **Electrical engineering** — <https://ocw.mit.edu/> (18.01/18.02/18.03/18.06,
  8.01/8.02, 6.002, 6.003), <https://dspguide.com/> (complete free DSP text),
  <https://www.allaboutcircuits.com/textbook/>, <https://eater.net/8bit>,
  Phil's Lab for KiCad four-layer boards, Razavi's UCLA lectures
- **Software development** — <https://teachyourselfcs.com/> (the book/course
  pairs are reproduced per node), <https://missing.csail.mit.edu/>,
  <https://sre.google/books/>, <https://craftinginterpreters.com/>,
  OSTEP, CMU 15-445
- **Filmmaking** — <https://www.blackmagicdesign.com/products/davinciresolve/training>
  (six official training books, free PDFs, with lesson footage),
  <https://www.studiobinder.com/film-production-documents/> (free call sheets,
  releases, schedules), <https://www.scriptslug.com/>,
  <https://www.rogerdeakins.com/forums/>, Weston *Directing Actors*

## What is *not* sourced

Honest accounting of what I chose rather than found:

- **`priority` values** (10–60) are the order the domains were requested in.
  That is your ranking to set, not a research finding.
- **`estimate` counts** are anchored to the vocabulary/hour figures above where
  those exist (HSK words per level, TYCS 100–200 hours) and are guesses
  elsewhere. They are now explicitly hypotheses, not contracts: the app records
  what each node actually took and reports the gap per node and per domain.
  **They are known to be low** — the nine TYCS subjects get 66 h each here
  against TYCS's own 100–200, and Chinese budgets 786 h to HSK 7–9 where FSI
  allows ~2,200 class hours plus equivalent self-study for a *lower* level.
  They were left low on purpose rather than flat-scaled by guesswork: the point
  is to find the real multiplier from completed nodes instead of inventing a
  second set of numbers to be wrong about.
- **`decay_days`** values are judgement. No curriculum publishes a decay rate.
  The *ordering* is defensible — hands decay faster than theory — but the
  numbers are starting points to tune.
- **`metric_target`** tempos are conventional practice targets, not Berklee
  requirements. Berklee's proficiency exams are assessed by an instructor.
- **`entry` prices and free tiers** were correct when researched (July 2026) and
  will rot faster than anything else here. Free tiers get withdrawn, courses get
  paywalled, YouTube channels vanish. Treat a dead link as expected, not as a
  bug — the search strings on each node are there partly as insurance against
  exactly that.
- **The self-marked mock-paper thresholds** in `chinese.toml` (85% / 80% / 75%,
  descending with level) are mine. HSK's real pass mark is 60% at every level;
  I set the self-assessment bar higher because marking your own unseen paper is
  softer than sitting a real one, and because the descending curve reflects that
  the upper levels are genuinely harder to self-mark honestly.
- **`scheduled`** is deliberately blank everywhere. HSK sitting dates are real
  and fixed, but they depend on your test centre — the app prompts for one
  rather than inventing it.
