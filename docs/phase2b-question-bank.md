# CareerCoach RIASEC question-bank review

Version: `careercoach-riasec-2026.1`. Status: active for exploratory product use, empirically unvalidated.

All items are original CareerCoach wording. Content review was performed during implementation against the requested activity-interest principles. No independent expert endorsement, pilot evidence or psychometric calibration is claimed.

## Active items

Every item follows the common prompt: **How much would you enjoy doing this activity?**

There are 36 active items, six per dimension. The first three in each dimension are fixed Quick core; all six are used in Detailed. Purpose is to explore enjoyment of the stated facet, not existing ability, personality, experience, or professional eligibility.

| Code | Dimension | Facet / purpose | Activity | Quick core |
| --- | --- | --- | --- | --- |
| R01 | R | Interest in mechanical repair | Repair a simple mechanical object. | Yes |
| R02 | R | Interest in practical assembly | Assemble an object by following a diagram. | Yes |
| R03 | R | Interest in outdoor plant care | Grow and care for plants outdoors. | Yes |
| R04 | R | Interest in hands-on making | Use hand tools to shape a piece of material. | No |
| R05 | R | Interest in practical measurement | Take measurements for a small building project. | No |
| R06 | R | Interest in equipment setup | Set up equipment for a practical task. | No |
| I01 | I | Interest in causal analysis | Compare information to work out why an event happened. | Yes |
| I02 | I | Interest in experimental inquiry | Plan a small experiment to test an idea. | Yes |
| I03 | I | Interest in quantitative patterns | Look for patterns in a set of numbers. | Yes |
| I04 | I | Interest in scientific inquiry | Investigate how a natural process works. | No |
| I05 | I | Interest in researching explanations | Research different explanations for an unanswered question. | No |
| I06 | I | Interest in logical reasoning | Develop a step-by-step solution to a logic puzzle. | No |
| A01 | A | Interest in visual expression | Create an original illustration. | Yes |
| A02 | A | Interest in creative writing | Write a short fictional story. | Yes |
| A03 | A | Interest in musical expression | Perform a piece of music. | Yes |
| A04 | A | Interest in communication design | Develop a visual concept for a poster. | No |
| A05 | A | Interest in movement expression | Experiment with movements for a dance. | No |
| A06 | A | Interest in three-dimensional expression | Shape a sculpture from clay or another material. | No |
| S01 | S | Interest in teaching | Explain an unfamiliar idea to someone who wants to learn. | Yes |
| S02 | S | Interest in supportive listening | Listen to a person who needs support with a difficulty. | Yes |
| S03 | S | Interest in coaching | Help someone practise a new skill. | Yes |
| S04 | S | Interest in mentoring | Guide a new student as they settle into a course. | No |
| S05 | S | Interest in practical helping | Help someone find services they need. | No |
| S06 | S | Interest in inclusive learning support | Adapt a learning activity for someone who needs extra support. | No |
| E01 | E | Interest in persuasion | Present a proposal to persuade a group to support it. | Yes |
| E02 | E | Interest in entrepreneurship | Plan how to turn a small business idea into a service. | Yes |
| E03 | E | Interest in negotiation | Negotiate an agreement between people with different goals. | Yes |
| E04 | E | Interest in project coordination | Coordinate people's tasks to deliver a group project. | No |
| E05 | E | Interest in initiative direction | Make decisions about the direction of a student initiative. | No |
| E06 | E | Interest in promotion | Promote an event to attract participants. | No |
| C01 | C | Interest in information organization | Sort information into a clear filing system. | Yes |
| C02 | C | Interest in checking accuracy | Check a list of figures for recording errors. | Yes |
| C03 | C | Interest in record keeping | Keep records of a group's spending. | Yes |
| C04 | C | Interest in following procedures | Follow a written procedure to process a form. | No |
| C05 | C | Interest in structured scheduling | Build a timetable that meets a set of requirements. | No |
| C06 | C | Interest in consistent data entry | Update a spreadsheet using a consistent format. | No |

The E coordination item focuses on directing tasks toward a project goal; teamwork itself is not defined as exclusively Social. Social activities focus on helping/teaching rather than sociability or teamwork preference. Practical tasks may overlap conceptually with analytical or creative tasks; dimension assignment is a hypothesis to test in the future validation study.

## Review of all 42 legacy questions

No legacy question row is overwritten or deleted. The entire legacy bank is retired from new delivery and kept as an archival reference. The legacy adaptive utility remains for old regression coverage; the application endpoint is retired (410). Concepts above were selected and rewritten individually rather than blindly reusing the old bank.

| Legacy ID | Dimension | Implementation content review and decision |
| --- | --- | --- |
| 1 | R | Split tools, machines and building into R01/R02/R04 rather than combine activities. |
| 2 | R | Retire the forced concrete-versus-abstract preference; use direct activities. |
| 3 | I | Split analysis/research and remove complex-ability framing (I01/I05). |
| 4 | I | Replace broad why preference with concrete investigation activities. |
| 5 | A | Split several creative modalities into A01/A02/A04. |
| 6 | A | Retire open-ended-versus-rules preference; avoid confounding personality with an activity. |
| 7 | S | Split helping, teaching and supporting into S01/S02/S03. |
| 8 | S | Retire people-versus-technical-work contrast; it is not exclusively a Social activity. |
| 9 | E | Split leading, pitching and persuading into E01/E04. |
| 10 | E | Replace broad role attraction with a concrete initiative decision (E05). |
| 11 | C | Split organizing, procedures and accuracy into C01/C02/C04. |
| 12 | C | Retire certainty/ambiguity preference and use concrete structured activities. |
| 13 | R | Narrow plants/animals/environment to one outdoor plant-care activity (R03). |
| 14 | R | Retire outdoor-versus-desk preference; use a particular outdoor task. |
| 15 | R | Retire satisfaction/visible-result trait framing. |
| 16 | R | Retire comfort/ability framing; ask about enjoyment of repair/setup. |
| 17 | R | Replace multiple sports/driving/crafting examples with specific making activities. |
| 18 | I | Retain experiment-interest facet in a single original activity item (I02). |
| 19 | I | Replace broad abstract learning preference with natural-process inquiry (I04). |
| 20 | I | Replace several puzzle/game examples with one logical-reasoning activity (I06). |
| 21 | I | Retire broad field/discipline attraction and implicit prestige associations. |
| 22 | I | Remove ability to spot patterns; ask enjoyment of pattern exploration (I03). |
| 23 | A | Retire broad idea/self-expression preference in favor of specific creative tasks. |
| 24 | A | Split performing, presenting and sharing; use specific expression activities. |
| 25 | A | Separate modalities and remove free-time access assumptions. |
| 26 | A | Retire negative boredom/repetition wording. |
| 27 | A | Retire aesthetic attention/personality wording; use creation tasks. |
| 28 | S | Retain explanation/teaching facet with new concrete wording (S01). |
| 29 | S | Retire social-role evidence (people seeking advice) rather than interest. |
| 30 | S | Retire perceived teamwork performance; helping is represented by concrete actions. |
| 31 | S | Retire self-perceived emotional ability. |
| 32 | S | Split coaching/counselling/caring job labels into direct support/coaching activities. |
| 33 | E | Remove natural-leadership trait claim; use project coordination (E04). |
| 34 | E | Retire competitiveness/dominance rather than an activity. |
| 35 | E | Retain entrepreneurial facet as planning a small service (E02). |
| 36 | E | Retire ambition/energy trait framing. |
| 37 | E | Retire general risk-taking trait; use negotiation/persuasion activities. |
| 38 | C | Replace planning-versus-improvisation preference with structured scheduling (C05). |
| 39 | C | Replace multiple document types with a specific form procedure (C04). |
| 40 | C | Retire self-perceived attention ability; use checking figures for errors (C02). |
| 41 | C | Split numbers/schedules/systems into specific records, timetables and spreadsheet tasks. |
| 42 | C | Retire general stability/routine personality preference. |

The nine rewrites in migration 0004 improved variety but did not establish item validity. Neither the legacy bank nor the 36-item replacement is claimed to be validated. These content decisions need independent expert review and student comprehension testing.

## Drafts and revisions

InterestItem has explicit draft/active/retired status. The initial replacement has 36 active items and no separately seeded draft candidates. Do not add candidate items to the active form until a new bank version has balanced coverage and completed content review. Clone/edit/check/publish instructions are in phase2b-assessment-guide.md.
