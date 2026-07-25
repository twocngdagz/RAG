"""Known-quality responses for measuring the model graders. The corpus IS the truth.

There is no bank of human-marked PTE responses here, so absolute accuracy —
"is 18/26 the right score?" — cannot be measured, and this module does not pretend
otherwise. What can be established without a marker's key is written down here:

  - RELATIVE quality. These responses were authored at deliberately different
    levels, so the grader must rank them in the intended order. A grader that
    cannot put a developed argument above a repetitive one is not measuring
    anything, whatever numbers it prints.
  - PLANTED defects. The misspellings in the middling essay and the invented
    figures in the wrong-numbers description were put there on purpose and are
    listed alongside the text, so "did it notice?" has an exact answer.
  - RULE-BREAKING responses. The off-topic essay and the two-sentence summary must
    trigger the gating rules, which are the one part of the rubric with a
    defined right answer.

Each entry carries `level` (higher is better) and `why`, so a future disagreement
is a debate about the authored judgement rather than about what was intended.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Write Essay
# --------------------------------------------------------------------------- #

ESSAY_PROMPT = (
    "Some people believe that university education should be free for all "
    "students. Others argue that students should pay for their own education. "
    "Discuss both views and give your own opinion."
)

# Deliberate misspellings in ESSAY_MIDDLING. Each appears exactly as written.
PLANTED_MISSPELLINGS = ["goverment", "oportunity", "sucessful", "beleive", "definately"]

ESSAY_STRONG = """Whether higher education should be funded by the state or by the individual is one of the more contested questions in public policy. Both positions rest on reasonable principles, though I believe a publicly funded system serves a country better over the long term.

Those who argue for free university education usually appeal to fairness. If places are allocated by ability to pay rather than by ability to learn, a large share of talented young people never reach the lecture theatre at all, and the country loses the doctors and engineers they would have become. Countries such as Germany and Norway have removed tuition fees and continue to produce highly skilled graduates, which suggests the model is workable rather than merely idealistic.

The opposing view is more concerned with cost and incentives. A university system is expensive to run, and if the taxpayer covers it, a factory worker who never attended university helps to fund the degree of a future banker. Supporters of tuition fees also argue that students who pay for their own study choose their courses more carefully and work harder, because the money at stake is their own.

In my view the fairness argument is the stronger of the two, but the objection about cost deserves a serious answer rather than dismissal. A graduate tax, under which students pay nothing upfront and contribute later only if their degree actually raises their income, captures most of the benefits of both positions. Education remains open to everyone at the point of entry, while those who gain financially from it still contribute to its cost."""

ESSAY_MIDDLING = """There are two sides to the question of who should pay for university education. Some people think the goverment should pay for it and other people think that students should pay by themselves. I will discuss both of these views before giving my own opinion on the matter.

The first opinion is that education must be free for everybody. If university is free then poor students have the same oportunity as rich students to study and improve their lives. Many clever people cannot go to university at the moment because they do not have enough money, and most people would agree that this is not fair. Also, a country with more graduates is more sucessful in the economy, so the goverment gets the money back later through the taxes that those graduates pay.

On the other hand, some people beleive that students should pay for themselves. University is very expensive to run and the money must come from somewhere. If everybody studies for free then taxes will go up for all people, including those who never went to university at all. Some also say that students who pay their own fees are more serious about their study and work harder.

In my opinion education should be free, or at least very cheap, because it is definately better for society when talented people are able to study. However I also think that students should pay a small part of the cost so that they take their studies seriously."""

ESSAY_WEAK = """University education is a big topic today. Some people say it should be free and some people say students should pay. I will discuss both sides of this topic in my essay.

Free education is good. It helps students who do not have money. Money is a big problem for many families today. If education is free then more students can go and study. More students studying is good for the country. The country needs educated people to work. So free education is good for the country and for the students.

But paying is also good in some ways. Universities need money to work properly. Teachers need to get their salary every month. Buildings need repair and equipment costs money too. If students do not pay then where does the money come from. The government must pay and the government takes money from taxes. So everyone pays in the end anyway, even people who did not study.

I think education should be free. This is my opinion about this topic. Free education helps poor students and it also helps the country. Students who cannot pay should still be able to study at university. Education is important for everybody and it should not depend on money. That is why I think university should be free for all the students who want to study."""

ESSAY_OFF_TOPIC = """Baking bread at home is far simpler than most people assume, and the results are consistently better than what a supermarket produces. The process needs only four ingredients: flour, water, salt and yeast, and none of them is expensive.

The first stage is mixing. Flour and water are combined and left to rest for half an hour before the salt and yeast are added, which allows the flour to absorb the water fully and makes the dough far easier to handle afterwards. This resting period is often skipped by beginners, and the difference in the final loaf is noticeable to anyone who tries both methods.

Kneading develops the gluten that gives bread its structure. Ten minutes of firm work is usually enough, and the dough is ready when a small piece stretches thin enough to see light through it without tearing. After kneading, the dough rises for several hours at room temperature, or overnight in a refrigerator if a slower fermentation and a deeper flavour are wanted.

Shaping and the final proof come next, followed by baking in the hottest oven available. A tray of water on the lower shelf produces steam, which keeps the crust soft long enough for the loaf to expand properly before it sets. The bread is done when the base sounds hollow when it is tapped."""

ESSAY_FLUENT_BUT_EMPTY = """The question of who should pay for university education is undoubtedly a highly significant and multifaceted issue that has generated considerable debate in contemporary society. On the one hand, there are numerous compelling arguments that merit careful consideration. On the other hand, the opposing perspective also presents points that cannot simply be dismissed out of hand.

To begin with, it is important to acknowledge that this matter affects a wide range of stakeholders in a variety of different ways. Furthermore, the implications extend well beyond the immediate context and into the broader social sphere. Moreover, one must take into account the long-term consequences, which are frequently overlooked in discussions of this nature.

Nevertheless, it would be misleading to suggest that the situation is straightforward. In fact, the complexity of the issue means that simplistic solutions are unlikely to prove effective in practice. Consequently, a more nuanced approach is required, one that carefully balances the competing priorities at stake.

In addition, it is worth noting that different countries have approached this question in different ways, with varying degrees of success. This diversity of experience suggests that context matters a great deal when such policies are considered.

In conclusion, having considered the various arguments on both sides of this important debate, I would argue that a balanced position is the most sensible one to adopt."""

ESSAYS: list[dict[str, Any]] = [
    {"key": "strong", "level": 3, "text": ESSAY_STRONG,
     "why": "clear position, both views developed with concrete examples, a real synthesis in the conclusion"},
    {"key": "middling", "level": 2, "text": ESSAY_MIDDLING,
     "why": "on topic and structured, but generic reasoning and five planted misspellings",
     "planted_misspellings": PLANTED_MISSPELLINGS},
    {"key": "weak", "level": 1, "text": ESSAY_WEAK,
     "why": "on topic but repetitive, simple sentences, no examples, restates rather than develops"},
    {"key": "off_topic", "level": 0, "text": ESSAY_OFF_TOPIC, "expect_gated": True,
     "why": "fluent and error-free but answers a different question entirely — Content must be 0"},
]

# Probed separately: fluent, well-formed, and says nothing. The characteristic
# failure of an automated rater is rewarding this as though it were an argument.
ESSAY_PROBE_EMPTY = {
    "key": "fluent_but_empty", "text": ESSAY_FLUENT_BUT_EMPTY,
    "why": "connectives and hedging with no claim, no example and no position",
}


# --------------------------------------------------------------------------- #
# Summarize Written Text
# --------------------------------------------------------------------------- #

SWT_PASSAGE = """Urban trees are increasingly treated by city planners as infrastructure rather than decoration. A mature street tree intercepts rainfall before it reaches the drainage system, reducing the volume that must be carried away during heavy storms, and its canopy lowers surface temperatures on surrounding streets by several degrees during summer heatwaves. Studies in several European cities have found measurable reductions in heat-related hospital admissions on streets with dense canopy cover compared with bare streets nearby. The benefits are not automatic, however. Trees planted in compacted soil with insufficient root volume rarely reach the size at which these effects become significant, and many municipal planting programmes are still judged on the number of saplings planted rather than the number surviving after a decade. Researchers argue that planting targets should therefore be replaced by canopy-cover targets, which measure the outcome that actually delivers the cooling and drainage benefits rather than the activity that is supposed to produce it."""

SWT_CENTRAL_CLAIM = (
    "Urban trees deliver drainage and cooling benefits only once they reach maturity, "
    "so cities should measure canopy cover rather than saplings planted."
)

SUMMARIES: list[dict[str, Any]] = [
    {"key": "good", "level": 3,
     "text": ("Urban trees are valued as infrastructure because their canopies reduce stormwater "
              "run-off and lower street temperatures during heatwaves, but these benefits only "
              "appear once the trees reach maturity, so researchers argue that cities should set "
              "canopy-cover targets rather than simply counting the saplings they plant."),
     "why": "one sentence, in range, carries both halves of the central claim"},
    {"key": "partial", "level": 2,
     "text": ("Urban trees in cities can lower street temperatures during summer heatwaves and "
              "reduce the amount of rainwater entering the drainage system, which has been "
              "measured in several European cities in recent years."),
     "why": "one well-formed sentence, but stops at the benefits and misses the argument about measurement"},
    {"key": "two_sentences", "level": 1, "expect_gated": True,
     "text": ("Urban trees reduce run-off and cool streets. Cities should measure canopy cover "
              "instead of counting saplings."),
     "why": "content is fine but it is two sentences — Form is 0 and the whole response gates to 0"},
    {"key": "off_topic", "level": 0, "expect_gated": True,
     "text": ("The passage explains how to prepare garden soil for vegetables and recommends "
              "adding compost each spring before any planting begins."),
     "why": "one sentence, but about a passage that was never read"},
]


# --------------------------------------------------------------------------- #
# Describe Image (against the renewable-electricity bar chart in the bank)
# --------------------------------------------------------------------------- #

DESCRIBE_ITEM_ID = "renewable-electricity-genera-01"

# Figures that appear in no bar of that chart. check_numbers() is pure code, so
# this has an exact expected answer and costs nothing to verify.
PLANTED_WRONG_NUMBERS = [9400.0, 850.0, 5100.0, 3300.0]

DESCRIPTIONS: list[dict[str, Any]] = [
    {"key": "full", "level": 3,
     "text": ("The bar chart shows renewable electricity generation by source in 2023, measured in "
              "gigawatt hours. Hydro is the largest source at 7800 GWh, followed by wind at 6200 "
              "and solar at 4500. Biomass contributes 1200 GWh, while geothermal is the smallest "
              "at just 300 GWh. The gap between the highest and lowest source is substantial: "
              "hydro produces 7500 GWh more than geothermal, roughly twenty-six times as much. "
              "Overall, hydro, wind and solar together account for the great majority of the "
              "20000 GWh total."),
     "why": "every essential fact stated with the correct figure"},
    {"key": "vague", "level": 1,
     "text": ("The chart shows different sources of renewable energy. Some of them are much bigger "
              "than others. The first few bars are quite tall and the last ones are very small. "
              "Overall it shows that renewable energy comes from a mixture of sources, and that "
              "some sources are used a great deal more than others."),
     "why": "describes the shape of the chart without naming a single value"},
    {"key": "wrong_numbers", "level": 0,
     "text": ("The bar chart shows renewable electricity generation by source. Hydro is the highest "
              "at 9400 GWh and geothermal is the lowest at 850 GWh. Wind produces around 5100 GWh "
              "while solar contributes about 3300 GWh."),
     "why": "confident, well-structured, and every figure invented",
     "planted_wrong_numbers": PLANTED_WRONG_NUMBERS},
]
