"""Generate the README architecture diagrams as SVG (standard library only).

    python docs/diagrams/build_diagrams.py      # writes docs/images/*.svg

Layouts are explicit (layers and swimlanes), so the pictures stay readable and
consistent. Colour language, used in every diagram:
    purple = LLM agent · teal = deterministic code · navy = orchestration / input
    green = state and outputs · amber = untrusted model output / external · red = stop or failure
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "images"
FONT = "Helvetica, Arial, sans-serif"

C = {
    "ink": "#1B2433", "muted": "#5B6B7F", "line": "#3B4A5E",
    "llm": "#6D4BC3", "code": "#0F7B74", "orch": "#1F3A5F", "out": "#2E7D32",
    "data_fill": "#E8F5E9", "data_line": "#2E7D32", "ext_fill": "#FFF4E5", "ext_line": "#B45309",
    "stop": "#B42318", "band": "#F4F6F9", "band_line": "#D5DCE5", "white": "#FFFFFF",
    "untrusted": "#FFF4E5", "valid": "#EEF7EF",
}
KINDS = {  # fill, stroke, text colour
    "llm": (C["llm"], "#4B3391", C["white"]),
    "code": (C["code"], "#0A5752", C["white"]),
    "orch": (C["orch"], "#142740", C["white"]),
    "out": (C["out"], "#1B5E20", C["white"]),
    "stop": (C["stop"], "#7A1710", C["white"]),
    "data": (C["data_fill"], C["data_line"], C["ink"]),
    "ext": (C["ext_fill"], C["ext_line"], C["ink"]),
    "iface": ("#E8EEF6", C["orch"], C["ink"]),
    "note": (C["white"], C["band_line"], C["ink"]),
}


class Svg:
    def __init__(self, w: int, h: int, title: str, subtitle: str = ""):
        self.w, self.h, self.parts = w, h, []
        self.text(28, 38, title, 22, bold=True)
        if subtitle:
            self.text(28, 62, subtitle, 14, color=C["muted"])

    # --- primitives --------------------------------------------------------------
    def text(self, x, y, s, fs=14, color=None, anchor="start", bold=False, italic=False):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{fs}" fill="{color or C["ink"]}" '
            f'text-anchor="{anchor}"{" font-weight=\"bold\"" if bold else ""}{" font-style=\"italic\"" if italic else ""}>'
            f"{escape(s)}</text>")

    def lines(self, cx, cy, lines, fs, color, bold_first=True):
        lh = fs * 1.28
        y0 = cy - (len(lines) - 1) * lh / 2 + fs * 0.35
        for i, s in enumerate(lines):
            self.text(cx, round(y0 + i * lh, 1), s, fs if i == 0 or not bold_first else fs - 1.5,
                      color, "middle", bold=bold_first and i == 0)

    def band(self, x, y, w, h, label, fill=None, line=None, label_color=None, dashed=False):
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill or C["band"]}" '
                          f'stroke="{line or C["band_line"]}" stroke-width="1.2"{dash}/>')
        if label:
            self.text(x + 12, y + 20, label, 13, color=label_color or C["muted"], bold=True)

    def box(self, x, y, w, h, lines, kind, fs=15, rx=8):
        fill, stroke, tc = KINDS[kind]
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="1.4"/>')
        self.lines(x + w / 2, y + h / 2, lines, fs, tc)

    def pill(self, x, y, w, h, lines, kind="orch", fs=15):
        self.box(x, y, w, h, lines, kind, fs, rx=h / 2)

    def cylinder(self, x, y, w, h, lines, kind="data", fs=15):
        fill, stroke, tc = KINDS[kind]
        e = 9
        self.parts.append(
            f'<path d="M{x},{y + e} a{w / 2},{e} 0 0,0 {w},0 v{h - 2 * e} a{w / 2},{e} 0 0,1 {-w},0 z" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
            f'<ellipse cx="{x + w / 2}" cy="{y + e}" rx="{w / 2}" ry="{e}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
        self.lines(x + w / 2, y + h / 2 + e / 2, lines, fs, tc)

    def diamond(self, cx, cy, w, h, lines, fs=14):
        pts = f"{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}"
        self.parts.append(f'<polygon points="{pts}" fill="{C["white"]}" stroke="{C["orch"]}" stroke-width="1.6"/>')
        self.lines(cx, cy, lines, fs, C["ink"], bold_first=False)

    def arrow(self, pts, color=None, dashed=False, label=None, at=None, head=True, label_color=None, fs=12.5):
        color = color or C["line"]
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        mid = {C["line"]: "a-line", C["llm"]: "a-llm", C["stop"]: "a-stop", C["out"]: "a-out", C["muted"]: "a-muted"}[color]
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        end = f' marker-end="url(#{mid})"' if head else ""
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{dash}{end}/>')
        if label:
            lx, ly = at or ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2 - 7)
            w = len(label) * fs * 0.53 + 10
            self.parts.append(f'<rect x="{lx - w / 2}" y="{ly - fs + 1}" width="{w}" height="{fs + 6}" rx="3" fill="{C["white"]}" opacity="0.92"/>')
            self.text(lx, ly + 1, label, fs, color=label_color or color, anchor="middle", italic=True)

    def legend(self, x, y):
        items = [("LLM agent", "llm"), ("Deterministic code", "code"), ("Orchestration / input", "orch"),
                 ("State and outputs", "out"), ("Untrusted / external", "ext"), ("Stop or failure", "stop")]
        for label, kind in items:
            fill, stroke, _ = KINDS[kind]
            self.parts.append(f'<rect x="{x}" y="{y - 11}" width="16" height="13" rx="3" fill="{fill}" stroke="{stroke}"/>')
            self.text(x + 22, y, label, 12.5, color=C["muted"])
            x += len(label) * 7 + 44

    def save(self, name):
        markers = "".join(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>'
            for mid, col in [("a-line", C["line"]), ("a-llm", C["llm"]), ("a-stop", C["stop"]), ("a-out", C["out"]), ("a-muted", C["muted"])])
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
               f'<defs>{markers}</defs><rect width="100%" height="100%" fill="{C["white"]}"/>' + "".join(self.parts) + "</svg>")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_text(svg, encoding="utf-8")
        print("wrote", OUT / name)


# ---------------------------------------------------------------------------------------
def architecture():
    s = Svg(1400, 830, "High-level architecture",
            "Layered view: who calls whom. Agents never call each other; the workflow calls every step in order.")
    s.legend(28, 96)

    s.pill(24, 360, 120, 56, ["Analyst"], "orch")
    s.band(165, 120, 185, 500, "INTERFACE")
    s.box(180, 343, 155, 90, ["CLI", "app.py", "input + config checks"], "iface")
    s.band(370, 120, 205, 500, "ORCHESTRATION")
    s.box(385, 180, 175, 410, ["Workflow", "research_briefing.py", "", "fixed sequence", "failure policy",
                               "bounded revision", "trace per step", "only writer of RunState"], "orch")

    s.band(600, 120, 560, 160, "AGENTS · LLM, typed contracts", label_color=C["llm"])
    for i, ln in enumerate([["Planner", "intent +", "sub-questions"], ["Researcher ×N", "claims +", "exact quotes"],
                            ["Synthesiser", "draft from", "claims only"], ["Verifier", "challenges", "the draft"]]):
        s.box(615 + i * 135, 158, 125, 104, ln, "llm")
    s.band(600, 290, 560, 160, "POLICIES · deterministic code", label_color=C["code"])
    for i, ln in enumerate([["Trust boundary", "quotes · citations", "· verdicts"], ["Sufficiency", "covered / thin / gap"],
                            ["Confidence", "support score", "per finding"]]):
        s.box(615 + i * 180, 328, 170, 104, ln, "code")
    s.band(600, 460, 560, 160, "TOOLS & DATA", label_color=C["code"])
    s.box(615, 498, 220, 104, ["Search", "BM25, top 5 documents"], "code")
    s.cylinder(905, 494, 240, 112, ["Corpus", "12 documents +", "tier, origin, date"], "data")

    s.band(1185, 120, 190, 160, "LLM PROVIDER", label_color=C["ext_line"])
    s.box(1200, 158, 160, 104, ["Gemini", "+ fallback", "model chain"], "ext")

    s.band(370, 645, 1005, 135, "STATE & OUTPUTS", label_color=C["out"])
    s.cylinder(600, 668, 200, 92, ["RunState", "one typed record"], "data")
    s.cylinder(880, 668, 200, 92, ["run.json", "audit trail"], "out")
    s.box(1160, 676, 200, 80, ["briefing.md", "for the analyst"], "out")

    s.arrow([(144, 388), (180, 388)])
    s.arrow([(335, 388), (385, 388)])
    s.arrow([(560, 210), (600, 210)], label="calls", at=(580, 202))
    s.arrow([(560, 380), (600, 380)], label="calls", at=(580, 372))
    s.arrow([(560, 550), (600, 550)], label="calls", at=(580, 542))
    s.arrow([(1160, 210), (1200, 210)], C["llm"])
    s.arrow([(835, 550), (905, 550)], head=False)
    s.arrow([(472, 590), (472, 714), (600, 714)], C["out"], label="writes", at=(530, 706))
    s.arrow([(800, 714), (880, 714)], C["out"], label="saved", at=(840, 706))
    s.arrow([(700, 668), (700, 656), (1260, 656), (1260, 676)], C["out"], label="rendered", at=(1010, 650))
    s.arrow([(1260, 756), (1260, 805), (84, 805), (84, 416)], C["out"], dashed=True,
            label="briefing returned to the analyst", at=(640, 799))
    s.save("architecture.svg")


def run_flow():
    s = Svg(1560, 640, "How one run flows",
            "Swimlanes show who does each step. Red paths are early stops; every outcome is saved to run.json.")
    s.legend(28, 92)
    lanes = [("INTERFACE", 115, 95), ("AGENTS · LLM", 220, 140), ("CODE · tools and policies", 370, 140), ("OUTCOMES", 520, 105)]
    for label, y, h in lanes:
        s.band(20, y, 1520, h, label)
    W, H = 122, 66
    cx = lambda i: 175 + i * 138  # column x (left edge)
    L1, L2, L3, L4 = 130, 252, 402, 538  # box top per lane

    s.box(cx(0), L1, W, H, ["Question", "+ config check"], "iface", 14)
    s.box(cx(1), L2, W, H, ["Planner", "3–5 sub-questions"], "llm", 14)
    s.band(cx(2) - 10, 238, 3 * 138 - 2, 248, "for each sub-question", fill="none", line=C["muted"], dashed=True)
    s.box(cx(2), L3, W, H, ["Search", "top 5 documents"], "code", 14)
    s.box(cx(3), L2, W, H, ["Researcher", "claims + quotes"], "llm", 14)
    s.box(cx(4), L3, W, H, ["Trust boundary", "accept / reject"], "code", 14)
    s.box(cx(5), L3, W, H, ["Sufficiency", "covered/thin/gap"], "code", 14)
    s.box(cx(6), L2, W, H, ["Synthesiser", "draft from claims"], "llm", 14)
    s.box(cx(7), L3, W, H, ["check_draft", "valid citations?"], "code", 14)
    s.box(cx(8), L2, W, H, ["Verifier", "challenges draft"], "llm", 14)
    s.box(cx(9), L3, W, H, ["Confidence", "support scores"], "code", 14)

    def elbow(i, ya, j, yb, color=None):
        x1, x2 = cx(i) + W, cx(j)
        xm = (x1 + x2) / 2
        s.arrow([(x1, ya), (xm, ya), (xm, yb), (x2, yb)], color)
    m1, m2, m3 = L1 + H / 2, L2 + H / 2, L3 + H / 2
    elbow(0, m1, 1, m2); elbow(1, m2, 2, m3); elbow(2, m3, 3, m2); elbow(3, m2, 4, m3)
    s.arrow([(cx(4) + W, m3), (cx(5), m3)])
    elbow(5, m3, 6, m2); elbow(6, m2, 7, m3); elbow(7, m3, 8, m2); elbow(8, m2, 9, m3)
    s.arrow([(cx(8) + W / 2, L2), (cx(8) + W / 2, 236), (cx(6) + W / 2, 236), (cx(6) + W / 2, L2)], C["llm"],
            label="at most 1 revision", at=(cx(7) + W / 2, 230), fs=12)

    s.box(cx(0), L4, W, 60, ["Exit code 2", "no model call"], "stop", 13.5)
    s.arrow([(cx(0) + W / 2, L1 + H), (cx(0) + W / 2, L4)], C["stop"], label="invalid", at=(cx(0) + W / 2 + 34, 480))
    s.box(cx(5), L4, W, 60, ["Insufficient-", "evidence briefing"], "stop", 13.5)
    s.arrow([(cx(5) + W / 2, L3 + H), (cx(5) + W / 2, L4)], C["stop"], label="nothing credible", at=(cx(5) + W / 2, 500))
    s.box(cx(7), L4, W, 60, ["Run failed", "state saved"], "stop", 13.5)
    s.arrow([(cx(7) + W / 2, L3 + H), (cx(7) + W / 2, L4)], C["stop"], label="no valid draft", at=(cx(7) + W / 2, 500))
    s.box(cx(9), L4, W, 60, ["run.json +", "briefing.md"], "out", 13.5)
    s.arrow([(cx(9) + W / 2, L3 + H), (cx(9) + W / 2, L4)], C["out"])

    s.text(cx(1) + W / 2, L2 + H + 20, "fails → whole question", 11.5, C["muted"], "middle", italic=True)
    s.text(cx(1) + W / 2, L2 + H + 35, "as one sub-question", 11.5, C["muted"], "middle", italic=True)
    s.text(cx(3) + W / 2, L2 + H + 20, "fails → that", 11.5, C["muted"], "middle", italic=True)
    s.text(cx(3) + W / 2, L2 + H + 35, "sub-question is a gap", 11.5, C["muted"], "middle", italic=True)
    s.text(cx(8) + W / 2, L2 + H + 20, "fails → not verified,", 11.5, C["muted"], "middle", italic=True)
    s.text(cx(8) + W / 2, L2 + H + 35, "scores capped at 0.39", 11.5, C["muted"], "middle", italic=True)
    s.save("run_flow.svg")


def research_trust():
    s = Svg(1400, 560, "Research and the trust boundary (once per sub-question)",
            "Nothing the model returns is trusted until code checks it. Rejected evidence is kept, with a reason.")
    s.legend(28, 92)
    s.pill(28, 225, 150, 60, ["Sub-question", "SQ1 … SQn"], "orch", 14)
    s.box(225, 214, 175, 82, ["Search (BM25)", "top 5 documents"], "code")
    s.band(445, 140, 440, 230, "UNTRUSTED · model output", fill=C["untrusted"], line=C["ext_line"], label_color=C["ext_line"])
    s.box(470, 205, 170, 100, ["Researcher", "LLM", "schema-checked;", "invalid → retried once"], "llm", 14)
    s.box(690, 205, 175, 100, ["ExtractedClaim", "statement", "source_id · quote"], "ext", 14)
    s.box(930, 175, 210, 160, ["Trust boundary · code", "1  source was given", "2  quote found in it", "3  not a duplicate",
                               "→ ID assigned by code"], "code", 14)
    s.band(1180, 140, 200, 230, "VALIDATED", fill=C["valid"], line=C["data_line"], label_color=C["out"])
    s.box(1195, 175, 170, 95, ["Claim", "trusted · C1, C2 …", "tier + origin from", "the source"], "out", 13.5)
    s.box(1195, 395, 170, 85, ["rejected_claims", "kept with a reason"], "stop", 13.5)

    s.arrow([(178, 255), (225, 255)])
    s.arrow([(400, 255), (470, 255)])
    s.arrow([(640, 255), (690, 255)])
    s.arrow([(865, 255), (930, 255)])
    s.arrow([(1140, 222), (1195, 222)], C["out"], label="pass", at=(1166, 214))
    s.arrow([(1140, 300), (1162, 300), (1162, 437), (1195, 437)], C["stop"], label="fail", at=(1162, 375))

    s.box(225, 410, 175, 70, ["No LLM call", "sub-question = gap"], "note", 13.5)
    s.arrow([(312, 296), (312, 410)], C["muted"], label="no documents", at=(312, 360))
    s.box(470, 410, 210, 70, ["No evidence for it", "WARNING issue"], "note", 13.5)
    s.arrow([(555, 305), (555, 410)], C["muted"], label="agent failure", at=(555, 375))
    s.text(462, 352, "Documents are passed inside <document> delimiters: data, never instructions.", 12, C["muted"], italic=True)
    s.text(930, 520, "The model never assigns IDs, tiers or scores: code does.", 13, C["muted"], italic=True)
    s.save("research_trust_boundary.svg")


def verification():
    s = Svg(1400, 600, "Verification and the single revision",
            "The Verifier challenges the draft; code limits what its verdict can change. There is no second revision.")
    s.legend(28, 92)
    Y = 300
    s.box(28, Y - 45, 165, 90, ["Draft", "findings F1 … Fn", "citations checked"], "data", 14)
    s.box(235, Y - 45, 150, 90, ["Verifier", "LLM"], "llm")
    s.box(425, Y - 45, 190, 90, ["check_verdicts", "support only from", "cited claims"], "code", 14)
    s.diamond(745, Y, 210, 120, ["All findings", "fully supported?"])
    s.box(1000, Y - 45, 170, 90, ["Confidence", "scorer"], "code")
    s.box(1205, Y - 55, 180, 110, ["Outcome", "unsupported → excluded", "no verdict → kept,", "capped at 0.39"], "note", 13)

    s.arrow([(193, Y), (235, Y)]); s.arrow([(385, Y), (425, Y)]); s.arrow([(615, Y), (640, Y)])
    s.arrow([(850, Y), (1000, Y)], C["out"], label="yes", at=(925, Y - 8))
    s.arrow([(1170, Y), (1210, Y)])

    R = 470
    s.box(650, R - 40, 190, 80, ["Synthesiser revises", "given the verdicts"], "llm", 14)
    s.box(880, R - 40, 160, 80, ["Verifier", "re-checks once"], "llm", 14)
    s.box(1080, R - 40, 160, 80, ["check_verdicts"], "code", 14)
    s.arrow([(745, Y + 60), (745, R - 40)], C["llm"], label="no: revise once", at=(800, 395))
    s.arrow([(840, R), (880, R)], C["llm"]); s.arrow([(1040, R), (1080, R)])
    s.arrow([(1160, R - 40), (1160, 395), (1085, 395), (1085, Y + 45)])
    s.text(745, R + 62, "fails → keep the first draft and its verdicts (warning)", 12, C["muted"], "middle", italic=True)

    s.box(235, 140, 330, 60, ["Not verified: every score capped at 0.39", "REVIEW issue"], "stop", 13.5)
    s.arrow([(310, Y - 45), (310, 200)], C["stop"], label="agent failure", at=(358, 228))
    s.arrow([(565, 170), (1085, 170), (1085, Y - 45)], C["stop"])
    s.text(960, R + 62, "re-check fails → also not verified", 12, C["muted"], "start", italic=True)
    s.save("verification_revision.svg")


if __name__ == "__main__":
    architecture(); run_flow(); research_trust(); verification()
