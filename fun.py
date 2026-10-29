"""Silly reactions when a score is entered: a toast message + a CSS emoji animation."""

import random

import streamlit as st

# (lowest score, animation, emojis, messages). {who} and {beer} are filled in.
TIERS = [
    (10, "rain", "🏆🍺🎉👑✨", [
        "PERFECTION. {who} wants to marry {beer}.",
        "{who} has found the Holy Grail of beer.",
        "A 10?! {who} is legally required to buy a crate of {beer}.",
    ]),
    (8.5, "rain", "🍻😍🍺💛", [
        "{who} would sell a kidney for {beer}.",
        "{beer} just got a new fan club. President: {who}.",
        "Delicious! {who} is writing {beer} a love letter.",
    ]),
    (7, "bounce", "😋", [
        "{who} approves. Nice one, {beer}.",
        "Solid! {beer} goes on {who}'s shopping list.",
        "{who} nods slowly and respectfully at {beer}.",
    ]),
    (5, "wobble", "😐", [
        "Meh. {who} has had better. And worse.",
        "{beer} is the beige wallpaper of beers, says {who}.",
        "{who}: 'It's... wet. And beer-ish.'",
    ]),
    (3, "shake", "🤢", [
        "{who} is quietly looking for a plant to pour {beer} into.",
        "{beer} tastes like a sad Monday, according to {who}.",
        "{who}'s face says everything.",
    ]),
    (1, "flush", "💀🚽", [
        "{beer} has been flushed by {who}. RIP.",
        "{who} would rather drink pond water.",
        "Call a doctor, {who} just tasted {beer}.",
    ]),
]

CSS = """
<style>
.fun-layer { position: fixed; inset: 0; pointer-events: none; z-index: 999999; overflow: hidden; }
.fun-layer span { position: absolute; line-height: 1; }

/* rain: emojis fall from the top */
.fun-rain span { top: -10vh; animation: fun-fall 2.6s ease-in forwards; }
@keyframes fun-fall {
  to { transform: translateY(120vh) rotate(540deg); }
}

/* bounce / wobble / shake / flush: one big emoji in the middle */
.fun-solo span { left: 50%; top: 45%; font-size: 9rem; transform: translate(-50%, -50%); }
.fun-bounce span { animation: fun-bounce 1.6s ease-out forwards; }
@keyframes fun-bounce {
  0%   { transform: translate(-50%, 60vh) scale(.5); opacity: 0; }
  40%  { transform: translate(-50%, -60%) scale(1.2); opacity: 1; }
  60%  { transform: translate(-50%, -45%) scale(.95); }
  80%  { transform: translate(-50%, -52%) scale(1.05); opacity: 1; }
  100% { transform: translate(-50%, -50%) scale(1); opacity: 0; }
}
.fun-wobble span { animation: fun-wobble 2s ease-in-out forwards; }
@keyframes fun-wobble {
  0%   { transform: translate(-50%, -50%) rotate(0); opacity: 0; }
  15%  { opacity: 1; }
  30%  { transform: translate(-50%, -50%) rotate(-12deg); }
  50%  { transform: translate(-50%, -50%) rotate(10deg); }
  70%  { transform: translate(-50%, -50%) rotate(-6deg); opacity: 1; }
  100% { transform: translate(-50%, -50%) rotate(0); opacity: 0; }
}
.fun-shake span { animation: fun-shake 1.8s linear forwards; }
@keyframes fun-shake {
  0%, 100% { transform: translate(-50%, -50%); opacity: 0; }
  10% { opacity: 1; }
  10%, 30%, 50%, 70% { transform: translate(-56%, -50%) rotate(-4deg); }
  20%, 40%, 60%, 80% { transform: translate(-44%, -50%) rotate(4deg); }
  90% { opacity: 1; }
}
.fun-shake { animation: fun-sick 1.8s ease forwards; }
@keyframes fun-sick {
  0%, 100% { background: transparent; }
  30%, 70% { background: rgba(80, 160, 40, .18); }
}
.fun-flush span:first-child { animation: fun-drain 2.2s ease-in forwards; }
.fun-flush span:last-child { animation: fun-toilet 2.2s ease forwards; }
@keyframes fun-drain {
  0%   { transform: translate(-50%, -50%) scale(1) rotate(0); opacity: 0; }
  15%  { opacity: 1; }
  100% { transform: translate(-50%, 10%) scale(0) rotate(1080deg); opacity: 1; }
}
@keyframes fun-toilet {
  0%   { transform: translate(-50%, 0) scale(.6); opacity: 0; }
  20%  { opacity: 1; }
  85%  { transform: translate(-50%, 0) scale(1); opacity: 1; }
  100% { transform: translate(-50%, 0) scale(1); opacity: 0; }
}
</style>
"""


def tier(score: float):
    return next(t for t in TIERS if score >= t[0])


def announce(who: str, beer: str, score: float) -> None:
    """Toast with a funny message (plus balloons for a perfect 10)."""
    _, _, emojis, messages = tier(score)
    st.toast(random.choice(messages).format(who=who, beer=beer), icon=emojis[0])
    if score == 10:
        st.balloons()


def animation(score: float, counter: int) -> str:
    """HTML/CSS overlay animation for a score, to render with st.html."""
    _, kind, emojis, _ = tier(score)
    if kind == "rain":
        spans = "".join(
            f'<span style="left:{random.uniform(0, 95):.1f}vw;'
            f'font-size:{random.uniform(1.8, 4):.1f}rem;'
            f'animation-delay:{random.uniform(0, 0.9):.2f}s">{random.choice(emojis)}</span>'
            for _ in range(40 if score == 10 else 25)
        )
        layer = f'<div class="fun-layer fun-rain">{spans}</div>'
    elif kind == "flush":
        layer = ('<div class="fun-layer fun-solo fun-flush">'
                 '<span>💀</span><span style="top:62%">🚽</span></div>')
    else:
        layer = f'<div class="fun-layer fun-solo fun-{kind}"><span>{emojis}</span></div>'

    # The counter makes the HTML differ for every new score, so the browser replays the
    # animation; rendering the same HTML again keeps it running undisturbed
    return f"{CSS}<!-- {counter} -->{layer}"
