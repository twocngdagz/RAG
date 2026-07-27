> **NONCANONICAL RESEARCH INPUT.** This document is a dated observation or synthesis,
> not a decision. It does not adopt anything. Only the authorities listed in
> `docs/research-rule-classification.md` are authoritative — that list includes the
> requirements and architecture guidelines, not only ADRs and plans.
>
> Captured 2026-07-26 · RAG `296d6b5` · Ela `da188c5`

# Research Citations

### Evidence for the ⟦cite⟧ claims in `01_pedagogy_guidelines.md`

This is the source layer. Each engine invariant in the pedagogy doc rests on findings that are stronger and more precise than the popular-science framing in *A Mind for Numbers*; this document supplies the primary references, notes the effect where it matters for design, and flags the caveats an implementer should know. References were verified against their publishing venues in a single sequential pass (July 2026). Where a claim rests on a meta-analysis rather than a single study, the meta-analysis is cited in preference to any one experiment.

A framing note worth keeping: two syntheses do most of the heavy lifting and are the right things to hand a skeptical stakeholder — **Dunlosky et al. (2013)**, which rates ten study techniques and puts *practice testing* and *distributed practice* alone in the "high utility" tier, and **Cepeda et al. (2006)**, the definitive spacing meta-analysis. If you read only two things, read those.

---

## Invariant 1 — Retrieval practice / the testing effect

- **Roediger, H. L., & Karpicke, J. D. (2006).** Test-Enhanced Learning: Taking Memory Tests Improves Long-Term Retention. *Psychological Science*, 17(3), 249–255. — The canonical demonstration that a retrieval test beats restudy on a *delayed* final test, and that repeated restudy can look better on an immediate test while losing badly at a delay. https://journals.sagepub.com/doi/10.1111/j.1467-9280.2006.01693.x
- **Karpicke, J. D., & Roediger, H. L. (2008).** The Critical Importance of Retrieval for Learning. *Science*, 319, 966–968. — Retrieval, not repeated study, is what produces retention. (Companion to the above; establishes "repeated retrieval" as the active ingredient.)
- **Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., & Willingham, D. T. (2013).** Improving Students' Learning With Effective Learning Techniques. *Psychological Science in the Public Interest*, 14(1), 4–58. — Rates *practice testing* as high-utility across ages, materials and settings. https://journals.sagepub.com/doi/abs/10.1177/1529100612453266

*Design note.* The effect is largest when retrieval is effortful but succeeds, and it is amplified by feedback (see Invariant 5). This is the basis for "produce before you see the answer" (`01` Inv. 1) and for refusing to count exposure/rereading as learning.

## Invariant 1/6 — Metacognitive illusions (why learners choose the worse strategy)

- **Karpicke, J. D., Butler, A. C., & Roediger, H. L. (2009).** Metacognitive strategies in student learning: Do students practise retrieval when they study on their own? *Memory*, 17(4), 471–479. — Most students reread rather than self-test, and misjudge which works.
- **Kornell, N., & Bjork, R. A. (2008).** Learning Concepts and Categories: Is Spacing the "Enemy of Induction"? *Psychological Science*, 19(6), 585–592. — Learners rate the *worse* (blocked) schedule as more effective even after the interleaved one produced better results — direct evidence for the "illusion of competence." https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Kornell_Bjork_2008_PsychScience.pdf

*Design note.* This is the empirical backbone of the anti-illusion progress surface (`02` §3.1): the interface must not optimise for what feels effective in the moment.

## Invariant 2 — Distributed practice / spacing, optimal gap, expanding intervals

- **Cepeda, N. J., Pashler, H., Vul, E., Wixted, J. T., & Rohrer, D. (2006).** Distributed Practice in Verbal Recall Tasks: A Review and Quantitative Synthesis. *Psychological Bulletin*, 132(3), 354–380. — The meta-analysis; spacing reliably beats massing. https://pubmed.ncbi.nlm.nih.gov/16719566/
- **Cepeda, N. J., Vul, E., Rohrer, D., Wixted, J. T., & Pashler, H. (2008).** Spacing Effects in Learning: A Temporal Ridgeline of Optimal Retention. *Psychological Science*, 19(11), 1095–1102. — The key result for a scheduler: the *optimal* gap grows with the target retention interval, and the ratio of optimal gap to retention interval is smaller for longer delays (roughly 10–30%, declining as the horizon lengthens). https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf
- **Dunlosky et al. (2013)** — also rates *distributed practice* high-utility (ref. above).

*Design note.* This is the direct justification for replacing both repos' capped ladders with an unbounded, expanding, stability-based scheduler (`01` §3.2). Cepeda 2008 is why the interval must scale with the *desired* retention horizon rather than sitting at a fixed maximum.

## Invariant 2 — Modern spaced-repetition algorithms (the implementable form)

- **Open Spaced Repetition — FSRS (Free Spaced Repetition Scheduler).** DSR (Difficulty–Stability–Retrievability) model; now the default scheduler in Anki. Algorithm reference and wiki. https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler and https://github.com/open-spaced-repetition/fsrs4anki/wiki
- **SM-2 (SuperMemo 2), Wozniak.** The older ease-factor algorithm; adequate as a simpler fallback if FSRS is too much to adopt initially.

*Design note.* FSRS is recommended in `01` §3.2 because it models a retrievability curve and per-item stability/difficulty explicitly, which maps cleanly onto the item-state columns proposed for both repos. It is production-proven at very large scale (Anki).

## Invariant 3 — Interleaving and desirable difficulties; overlearning decays

- **Rohrer, D., & Taylor, K. (2007).** The shuffling of mathematics problems improves learning. *Instructional Science*, 35, 481–498. — Interleaved maths practice: worse during practice, much better on a delayed test. http://uweb.cas.usf.edu/~drohrer/pdfs/Rohrer&Taylor2007IS.pdf
- **Rohrer, D., Dedrick, R. F., & Stershic, S. (2015).** Interleaved Practice Improves Mathematics Learning. *Journal of Educational Psychology*. — Classroom replication with a large delayed-test advantage. https://gwern.net/doc/psychology/spaced-repetition/2014-rohrer.pdf
- **Kornell & Bjork (2008)** (ref. above) — interleaving aids *inductive* category learning, not just motor/problem skills.
- **Birnbaum, M. S., Kornell, N., E. Bjork, E. L., & R. Bjork, R. A. (2013).** Why interleaving enhances inductive learning: the roles of discrimination and retrieval. *Memory & Cognition*, 41, 392–402. — Mechanism: interleaving works by forcing *discrimination* between confusable categories. Important design nuance — interleaving helps when items are confusable, which is why `01` Inv. 3 says place confusable skills near each other.
- **Rohrer, D., & Taylor, K. (2006).** The effects of overlearning and distributed practice on the retention of mathematics knowledge. *Applied Cognitive Psychology*, 20, 1209–1224. — Overlearning gives short-lived gains that decay; spacing is the better use of time. https://onlinelibrary.wiley.com/doi/abs/10.1002/acp.1598

*Design note.* Backs both the "mix confusable skills" rule and the "stop same-session repetition once correct; convert to spacing" rule (`01` Inv. 3).

## Invariant 4 — Cognitive load, worked examples, faded guidance, expertise reversal

- **Sweller, J. (1988; and Sweller, Ayres & Kalyuga, 2011, *Cognitive Load Theory*, Springer).** Working memory is severely limited for novel information but effectively unlimited when drawing on long-term schemas.
- **Sweller, J., & Cooper, G. A. (1985).** The use of worked examples as a substitute for problem solving. *Cognition and Instruction*, 2, 59–89. — The worked-example effect for novices.
- **Renkl, A., & Atkinson, R. K. (2003).** Structuring the transition from example study to problem solving. *Educational Psychologist*, 38, 15–22. — *Fading* worked examples (complete → partial → solo) is the efficient path.
- **Kalyuga, S., Ayres, P., Chandler, P., & Sweller, J. (2003).** The Expertise Reversal Effect. *Educational Psychologist*, 38(1), 23–31. — Support that helps a novice *hurts* an expert; scaffolding must be withdrawn as competence grows. https://link.springer.com/article/10.1007/s11251-009-9102-0 (special-issue introduction)

*Design note.* Directly justifies state-driven fading (`01` Inv. 4; `03` Phase 3.2) and the lower new-element cap for children (`01` §4.4).

## Invariant 5 — Feedback amplifies retrieval; elaborated feedback for complex material

- **Butler, A. C., Karpicke, J. D., & Roediger, H. L. (2007/2008).** The effect of type and timing of feedback on learning from multiple-choice tests. *Journal of Experimental Psychology: Applied.* — Feedback amplifies the testing effect, especially by correcting confident errors.
- **Shute, V. J. (2008).** Focus on Formative Feedback. *Review of Educational Research*, 78(1), 153–189. — Synthesis: specific, elaborated, correction-focused feedback outperforms mere right/wrong for complex learning.
- **Hattie, J., & Timperley, H. (2007).** The Power of Feedback. *Review of Educational Research*, 77(1), 81–112. — Feedback is among the highest-leverage instructional moves, but its effect depends heavily on type and timing.

*Design note.* Supports "every response gets feedback," elaborated over binary, and — combined with the project's own internal finding that a temperature-0 model judge flipped a contradicted numeric claim across runs while the deterministic check caught it every time — the rule that deterministic checkers own the right/wrong decision and the model only elaborates (`01` Inv. 5).

## Invariant 6 — Calibration and judgements of learning

- **Kruger, J., & Dunning, D. (1999).** Unskilled and Unaware of It. *Journal of Personality and Social Psychology*, 77(6), 1121–1134. — Weaker performers systematically overestimate themselves.
- **Nelson, T. O., & Dunlosky, J. (1991).** When people's Judgements of Learning (JOLs) are extremely accurate at predicting subsequent recall: the "delayed-JOL effect." *Psychological Science*, 2, 267–270. — Confidence judgements taken *at a delay* are far better calibrated than immediate ones.

*Design note.* Justifies capturing a pre-answer confidence prediction and surfacing the felt-vs-actual gap (`01` Inv. 6; `02` §3.1, the "felt sure but missed" panel), and taking calibration signals at a delay rather than immediately.

## Invariant 7 — Sleep, habit/implementation intentions, bounded sessions

- **Diekelmann, S., & Born, J. (2010).** The memory function of sleep. *Nature Reviews Neuroscience*, 11, 114–126. — Sleep actively consolidates memory (and preferentially strengthens what's relevant); the strongest form of the book's sleep claim. https://www.nature.com/articles/nrn2762
- **Walker, M. P. (2008).** Sleep-dependent memory processing / *Why We Sleep* (2017) for the popular synthesis. — Sleep deprivation impairs encoding and consolidation.
- **Gollwitzer, P. M., & Sheeran, P. (2006).** Implementation Intentions and Goal Achievement: A Meta-Analysis of Effects and Processes. *Advances in Experimental Social Psychology*, 38, 69–119. — "If-then" plans that bind a cue to an action have a medium-to-large effect (d ≈ 0.65) on goal attainment — the evidence base under cue-triggered focus sessions and streak habits. https://www.socmot.uni-konstanz.de/publications/implementation-intentions-and-goal-achievement-meta-analysis-effects-and-processes

*Design note.* Backs the motivation/scheduling scaffolding (`01` Inv. 7; `02` §3.2) — bounded sessions with a cue and reward, and date-anchored sleep reminders for test/interview tracks. (The Pomodoro technique itself is a popular method rather than a heavily-studied intervention; the *support* for it is the time-boxing + implementation-intention + focused-attention literatures, not a large "Pomodoro" trial base — worth stating honestly.)

## §4.2 — Language: formulaic sequences and vocabulary coverage thresholds

- **Nation, I. S. P. (2006).** How Large a Vocabulary Is Needed for Reading and Listening? *Canadian Modern Language Review*, 63(1), 59–82. — ~98% lexical coverage is needed for unassisted comprehension, implying roughly 8,000–9,000 word families for reading a wide range of texts (fewer for speech). Sets the *volume + spacing* regime for the language track. https://utppublishing.com/doi/10.3138/cmlr.63.1.59
- **Wray, A. (2002).** *Formulaic Language and the Lexicon.* Cambridge University Press. — Formulaic sequences/chunks are central to fluent processing — the evidence base under Ela's phrase-first thesis.
- **Boers, F., et al. (2006).** Formulaic sequences and perceived oral proficiency. *Language Teaching Research.* — Chunk knowledge relates to rated fluency.

*Design note.* Justifies phrase-first content as a real bet (not just a product opinion) and the "production in a sentence to graduate" rule for the language track (`01` §4.2; `02` §2.2), and underlines that the current all-single-word seed library starves the design (`03` decision 3).

## §4.3 — Interview: arousal reappraisal; structured interviews

- **Brooks, A. W. (2014).** Get Excited: Reappraising Pre-Performance Anxiety as Excitement. *Journal of Experimental Psychology: General*, 143(3), 1144–1158. — Relabelling anxiety as excitement measurably improves performance (singing, speaking, maths) — the evidence for the book's reframing technique, rehearsed rather than merely stated. https://www.apa.org/pubs/journals/releases/xge-a0035325.pdf
- **STAR / behavioural interviewing** — the STAR *format* is an industry structuring convention rather than a validated intervention; the adjacent evidence is that *structured* interviews predict job performance far better than unstructured ones (Schmidt & Hunter, 1998, *Psychological Bulletin*). Stated honestly in `01` §4.3: STAR is a scaffold that makes answers completeness-checkable, not a proven learning treatment.

## §4.4 — Children: systematic phonics and the reading model

- **Ehri, L. C., Nunes, S. R., Stahl, S. A., & Willows, D. M. (2001).** Systematic Phonics Instruction Helps Students Learn to Read: Evidence from the National Reading Panel's Meta-Analysis. *Review of Educational Research*, 71(3), 393–447. — The meta-analytic case for systematic phonics. https://journals.sagepub.com/doi/10.3102/00346543071003393
- **National Reading Panel (2000).** *Teaching Children to Read.* — The five pillars (phonemic awareness, phonics, fluency, vocabulary, comprehension). https://www.readingrockets.org/topics/curriculum-and-instruction/articles/findings-national-reading-panel
- **Gough, P. B., & Tunmer, W. E. (1986).** Decoding, reading, and reading disability (the *Simple View of Reading*: Reading = Decoding × Language Comprehension). *Remedial and Special Education*, 7, 6–10.
- **Scarborough, H. S. (2001).** Connecting early language and literacy to later reading (dis)abilities — the *Reading Rope* (word-recognition strands + language-comprehension strands). In *Handbook of Early Literacy Research.*

*Design note.* Grounds the kids-reading track in the mainstream science-of-reading consensus (`01` §4.4; `02` §2.4): systematic synthetic phonics, one pattern at a time, inside a rope of decoding + comprehension — not whole-language guessing.

---

## Honesty notes for the implementer

Three places where the design deliberately follows the evidence *against* or *beyond* the book, and should be defended that way:

1. **The book's handwriting-over-typing and memory-palace material is weakly evidenced or minor** by the book's own admission; `01` keeps these out of the engine and in an optional techniques surface. Don't over-invest there.
2. **"Learning styles" appear nowhere in this design on purpose** — the claim that matching instruction to a preferred modality improves learning has repeatedly failed to replicate (Pashler et al., 2008, *Psychological Science in the Public Interest*). The audience presets in `02` adapt *content, load and format to the task and the learner's demonstrated state* — never to a self-reported "style."
3. **Model-as-judge is treated as a last resort, not a default** — consistent with this project's own internal measurement (a temperature-0 judge flipping a contradicted numeric claim) and with the broader reliability caution around LLM-as-judge. Every ⟦cite⟧-backed invariant above is enforceable in deterministic code; the model is confined to elaboration and to genuinely-open scoring that is always labelled and always deterministically bounded.

*These references complete the four-document set: `01` (pedagogy) · `02` (UX) · `03` (implementation) · `04` (this). Every load-bearing claim in `01` now traces to a primary source.*
