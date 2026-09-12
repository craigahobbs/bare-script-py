# Choosing the Line Chart Color Palette

The
[dataLineChart.bare](https://craigahobbs.github.io/bare-script/library/#var.vGroup='dataLineChart.bare')
include library draws each series in its own color. Choosing those colors is not a matter of taste
alone - a chart line is a *thin* mark, and color difference shrinks as marks get smaller. A palette
that looks well separated on a swatch card can collapse into near-identical lines on a chart.

This article walks through how the palette in the library was derived: the perceptual model it is
based on, the extension that model needed before it could describe a chart line, why the palette has
exactly five colors, and what the colors cost when they were held to an aesthetic.

## The problem, measured

Start with the palette everybody knows. Tableau's Classic 10 is the ancestor of the default
categorical palette in most charting libraries. Here are its first five colors, and the first five
of its 2016 successor, evaluated at the size of a chart line:

| palette | worst pair | mean chroma | minimum contrast |
| --- | --- | --- | --- |
| Tableau Classic 10 | 0.11 | 65.4 | 2.53 |
| Tableau 10 (2016) | 0.14 | 47.3 | 2.29 |

The "worst pair" column is the closest pair of colors in the palette, in units where 1.0 means
"every viewer can tell them apart, side by side". Both palettes score around **0.1** - an order of
magnitude below threshold. The reason is color vision deficiency: Classic 10's green and red are all
but identical to a deuteranope, which is roughly 6% of men. Neither palette clears the 3:1 contrast
minimum that [WCAG 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html) asks
of non-text graphics, either.

These are not bad palettes. They are palettes designed for *area* marks - bars, pie slices, filled
regions - being asked to do a job they were not measured for.

## The model

The right tool is Stone, Szafir and Setlur's engineering model for color difference as a function of
size (CIC 2014). It gives, for a mark of angular size `s`, the CIELAB distance along each axis that
a given fraction `p` of viewers will notice:

    ND(p, s) = p * (A + B / s)

with A and B fitted per axis: L\* (10.16, 1.50), a\* (10.68, 3.08), b\* (10.70, 5.74). Two colors
are discriminable when the distance between them, divided axis-by-axis by these thresholds, is at
least 1. The `B / s` term is the whole point - as marks shrink, the threshold grows, and it grows
fastest on b\*, the yellow-blue axis.

The model is calibrated on **square patches**, from 0.33 degrees of visual angle up to 6. A chart
line is not a square patch. It is 3 pixels wide and hundreds long.

## Extending the model to a thin mark

Two obvious readings of `s` both fail:

- **Use the stroke width.** Three pixels is 0.064 degrees, five times below the model's calibrated
  floor. Down there the `B / s` term explodes and the model declares that essentially no palette
  works, which every chart anybody has ever read contradicts.
- **Use the whole line.** Taking the equal-area square of a 500-pixel path ignores that chromatic
  acuity is limited by the *thin* dimension. It would happily approve colors that are
  indistinguishable in practice.

The extension used here takes the middle road. Chromatic signal integrates over area, but only up to
a critical summation length; past that, extra length buys nothing. So the effective size is the
equal-area square of the mark *truncated* at that length:

    s_eff = sqrt(width * min(length, 1 degree))

This keeps the thin dimension inside a geometric mean while crediting the length that actually
contributes.

Then: **which** mark? Color appears in exactly two places in a line chart - the chart lines
themselves, and the line samples in the color legend. Measured from the rendering code, the legend
sample is `2 * fontSize` long, which is 32 pixels at the default font size; the median polyline
segment across the library's own demo charts is 47 pixels. That gives:

| mark | s_eff |
| --- | --- |
| legend sample, 3 x 32 px | 0.209 deg |
| line segment, 3 x 47 px | 0.253 deg |
| stroke width alone | 0.064 deg |

The legend sample is the smaller of the two, *and* it is the reference a reader matches a line
against. It sets the size. At 0.209 degrees the extrapolation below the model's floor is a factor of
1.6 rather than 5 - still extrapolation, but not a different regime.

Two further adjustments suit the task rather than the mark. A reader matching a line to a legend
entry saccades between them and carries the color in memory across the saccade, which is reliably
worse than judging two patches side by side; that is taken as a factor of two. And `p` is evaluated
at 1.0, not the conventional 0.5 - a chart is not usable when half its readers can tell two lines
apart.

## What the extension says

At the binding size the per-axis thresholds come out as:

| axis | noticeable difference |
| --- | --- |
| L\* (lightness) | 17.3 |
| a\* (red-green) | 25.4 |
| b\* (yellow-blue) | 38.2 |

These are **not** equal, and that is the single most useful thing the extension produces. A pure
yellow-blue difference must be 38 CIELAB units to clear threshold; the same job is done by 17 units
of lightness. At line-chart scale, **lightness is 2.2 times as efficient a channel as yellow-blue**,
and 1.5 times as efficient as red-green. At 2 degrees - a pie slice, a choropleth region - those
ratios collapse to 1.24 and 1.12, and the axes are near enough interchangeable.

So a palette for thin marks should spend its budget on lightness and treat hue as the secondary
separator. That is the opposite of how a palette for large areas should be built, and it is why
borrowing one for the other goes wrong.

## How many colors fit

With a model that describes the actual mark, the palette *size* stops being a judgment call. Pack
sRGB as densely as possible subject to the criterion - every pair at least 2.0 apart at p = 1.0,
under normal, deuteranope and protanope vision, every color clearing 3:1 contrast on white - and
count what fits:

| criterion | normal | + CVD | + CVD + 3:1 contrast |
| --- | --- | --- | --- |
| d >= 1.0, side by side | 60 | 15 | 12 |
| d >= 1.5 | 22 | 8 | 6 |
| **d >= 2.0, the design point** | **14** | **5** | **5** |
| d >= 2.5 | 9 | 4 | 4 |

Five. And it is stable: varying the critical summation length from 0.75 to 2 degrees, and the memory
factor from 1.75 to 2.0, gives five throughout, dipping to four only in the most pessimistic corner.

A second, independent line of evidence agrees. Ask for the best *nameable* palette at each size -
one where every color takes a distinct basic color name - and measure the marginal cost of each
addition:

| colors | best worst-pair | change |
| --- | --- | --- |
| 3 | 3.19 | - |
| 4 | 2.24 | -30% |
| **5** | **1.93** | **-14%** |
| 6 | 1.33 | -31% |
| 7 | 1.21 | -9% |

There is a cliff between five and six. The fifth color is cheap; the sixth costs more than twice as
much. That is why the library's palette has five colors, and why a sixth series takes a *dash
pattern* instead - color has run out, so a second channel starts.

## Nameability is part of parseability

A search that maximizes discriminability alone returns colors nobody can name: two blues a lightness
apart, a yellow-brown, a magenta. That is a worse chart, not a better one. Heer and Stone (CHI 2012)
showed that legend matching is faster and more accurate when each color takes a distinct basic color
name, because the reader encodes "the blue line", not a point in CIELAB.

So the search is structured. Each slot is pinned to a *name region* - a hue range plus the lightness
and chroma range over which that name actually holds. An orange below L\* 55 is a brown; a red above
L\* 58 is a pink; anything below about C\* 25 is a gray whatever its hue.

This constraint has teeth. Left to itself the optimizer placed "blue" at hue 285 and "violet" at hue
292 and counted them as two colors, because the name regions touch at their edges. A minimum hue gap
between palette members fixes that. CIELAB also puts pure sRGB blue at hue ~306, inside any generous
violet range, so an early run cheerfully put electric blue in the violet slot and produced a palette
with two blues.

## Getting the optimizer right

Maximin problems are easy to solve badly. The first optimizer here was coordinate descent from
random starts, and it kept returning a *worse* score for a constraint point than for a strict subset
of that point's feasible region - which is impossible for a true optimum, and a clear signal the
search was stalling in local basins rather than measuring anything.

Maximin has an exact decision version: *is there a palette with every pair at least `t` apart?* That
is answered by backtracking with domain filtering, and binary search on `t` then gives the true
optimum over the search grid, with no restarts and no luck. Adding arc consistency - dropping every
candidate that has no viable partner in some other family, repeated to a fixpoint - makes it fast
enough to sweep a whole constraint grid in seconds.

The objective is *lexicographic* maximin over the sorted pairwise distances: an improvement must
help the worst pair, then the second worst, and so on. A plain maximin will happily buy one good
pair at the cost of every other one.

## The aesthetic constraint, and what it cost

Discriminability is a requirement with a threshold, not a quantity to maximize without limit. Past
the design point, extra separation is unspent budget - and it can be spent on how the palette looks.

The first attempt spent it badly. Using a chroma *ceiling* as the restraint lever drove mean chroma
from 63 down to 44 and produced ochre, oxblood and forest green - 1970s earth tones. Forcing chroma
*up* with a floor was worse still: it pins every color to the sRGB gamut boundary, where they crowd
together, and the worst pair collapsed from 1.85 to 1.23.

The formulation that works turns the two around - *maximize chroma subject to a discriminability
floor*, ranked by the least chromatic color first so one neon line beside four muted ones cannot
win. At the same parseability as the palette it replaced, that yields mean chroma 72 instead of 63.
Vivid and well separated are not in conflict; they were only in conflict under a badly posed
objective.

The final envelope asks for **semi-precious stone tones**: deep in lightness, saturated, but held
just inside the gamut rather than on its boundary - which is the whole difference between lapis and
electric blue, or malachite and screen green. A chroma ceiling *and* a floor, together.

## The palette

| stone | color | L\* | C\* | contrast on white |
| --- | --- | --- | --- | --- |
| lapis | `#026cba` | 44.6 | 48.3 | 5.45 |
| carnelian | `#e86d00` | 60.0 | 80.7 | 3.17 |
| malachite | `#0c9b3f` | 56.0 | 66.2 | 3.64 |
| garnet | `#9c0018` | 32.1 | 65.9 | 8.65 |
| amethyst | `#68266f` | 28.1 | 49.5 | 10.02 |

Against the palette it replaced, and against the Tableau palettes it descends from:

| palette | worst pair | deuteranope | protanope | mean chroma | min contrast |
| --- | --- | --- | --- | --- | --- |
| Tableau Classic 10 | 0.11 | - | - | 65.4 | 2.53 |
| Tableau 10 (2016) | 0.14 | - | - | 47.3 | 2.29 |
| previous palette | 1.66 | 1.66 | 1.67 | 62.6 | 3.00 |
| **stone palette** | **1.78** | **1.78** | **1.78** | **62.1** | **3.17** |

Every color clears the 3:1 non-text contrast minimum with margin, the palette is unchanged in
quality under both common forms of color vision deficiency, and it holds the saturation of the
palette it replaced while separating better.

## What it does not solve

**Tritanopia.** Garnet and amethyst converge for a tritanope - purple loses its blue and reads as
red - scoring 0.59. Optimizing for it costs about 4% of the margin and pulls the palette back toward
electric azure and tan, and the lightness ladder cannot stretch far enough inside the stone band to
separate those two on a channel tritanopia leaves intact. The palette it replaced scored 0.57 here,
and no widely used categorical palette does better. It is a known limit, not an oversight.

**The dash channel is the real backstop.** Past the fifth series the colors repeat with a line dash
pattern, giving twenty-five series before any two are drawn alike - and the color legend draws a
segment of the line itself, dash pattern included, so a reader who cannot separate two colors can
still match a legend entry to its line by pattern.

## References

- Stone, Szafir & Setlur, "An Engineering Model for Color Difference as a Function of Size", CIC 2014
- Szafir, "Modeling Color Difference for Visualization Design", IEEE TVCG 2018
- Heer & Stone, "Color Naming Models for Color Selection, Image Editing and Palette Design", CHI 2012
- Vienot, Brettel & Mollon, "Digital video colourmaps for checking the legibility of displays by
  dichromats", Color Research & Application, 1999
- [WCAG 2.1, Non-text Contrast](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html)
