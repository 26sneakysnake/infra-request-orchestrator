"""Render a BPMN 2.0 diagram (its DI layout) as a standalone SVG: python -m diagrams.bpmn_svg

A small renderer for the documents: pools and lanes, tasks with their kind, gateways, events with
their trigger, sequence flows and labels, at the positions saved by the modeller. No browser, no
Node: the images in docs/img/ are rebuilt by `make diagrams` and identical on every run.
"""

import sys
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAGRAMS = [
    (ROOT / "bpmn" / "expose_service.bpmn", ROOT / "docs" / "img" / "expose_service.svg"),
    (
        ROOT / "bpmn" / "as-is" / "expose_service_as_is.bpmn",
        ROOT / "docs" / "img" / "expose_service_as_is.svg",
    ),
]
NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
TASKS = {
    "task": "",
    "serviceTask": "automatique",
    "businessRuleTask": "règle DMN",
    "userTask": "humain",
    "manualTask": "manuel",
    "sendTask": "envoi",
    "receiveTask": "réception",
    "scriptTask": "script",
}
GATEWAYS = {
    "exclusiveGateway": "×",
    "parallelGateway": "+",
    "eventBasedGateway": "",
    "inclusiveGateway": "○",
}
EVENTS = {
    "startEvent",
    "endEvent",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
}
INK, MUTED, FILL, AUTO, HUMAN = "#1f2937", "#6b7280", "#ffffff", "#e8f1fb", "#fdf1e3"
FONT = "font-family='Segoe UI, Helvetica, Arial, sans-serif'"
CHAR_W = 6.1  # average glyph width at 11 px, enough to wrap labels


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _wrap(text: str, width: float) -> list[str]:
    limit = max(4, int(width / CHAR_W))
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > limit and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    return [*lines, line] if line else lines


def _text(x: float, y: float, w: float, text: str, size: int = 11, color: str = INK) -> str:
    lines = _wrap(text, w)
    top = y - (len(lines) - 1) * (size + 2) / 2
    return "".join(
        f"<text x='{x:.0f}' y='{top + i * (size + 2):.0f}' font-size='{size}' fill='{color}' "
        f"text-anchor='middle' dominant-baseline='middle' {FONT}>{escape(line)}</text>"
        for i, line in enumerate(lines)
    )


def _trigger(kinds: set[str], cx: float, cy: float, r: float) -> str:
    """Small geometric icon of the event definition (no font glyphs)."""
    s = r * 0.5
    if "messageEventDefinition" in kinds:
        return (
            f"<rect x='{cx - s:.1f}' y='{cy - s * 0.7:.1f}' width='{2 * s:.1f}' "
            f"height='{1.4 * s:.1f}' fill='none' stroke='{INK}'/>"
            f"<polyline points='{cx - s:.1f},{cy - s * 0.7:.1f} {cx:.1f},{cy + s * 0.1:.1f} "
            f"{cx + s:.1f},{cy - s * 0.7:.1f}' fill='none' stroke='{INK}'/>"
        )
    if "timerEventDefinition" in kinds:
        return (
            f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='{s:.1f}' fill='none' stroke='{INK}'/>"
            f"<polyline points='{cx:.1f},{cy - s * 0.7:.1f} {cx:.1f},{cy:.1f} "
            f"{cx + s * 0.6:.1f},{cy:.1f}' fill='none' stroke='{INK}'/>"
        )
    if "errorEventDefinition" in kinds:
        return (
            f"<polyline points='{cx - s:.1f},{cy + s:.1f} {cx - s * 0.3:.1f},{cy - s:.1f} "
            f"{cx + s * 0.3:.1f},{cy + s * 0.3:.1f} {cx + s:.1f},{cy - s:.1f}' fill='none' "
            f"stroke='{INK}' stroke-width='1.5'/>"
        )
    return ""


def render(bpmn: Path) -> str:
    root = ET.parse(bpmn).getroot()
    elements = {el.get("id"): el for el in root.iter() if el.get("id")}
    shapes = root.findall(".//bpmndi:BPMNShape", NS)
    edges = root.findall(".//bpmndi:BPMNEdge", NS)

    xs, ys = [], []
    for shape in shapes:
        b = shape.find("dc:Bounds", NS)
        x, y, w, h = (float(b.get(k)) for k in ("x", "y", "width", "height"))
        xs += [x, x + w]
        ys += [y, y + h]
    for edge in edges:
        for p in edge.findall("di:waypoint", NS):
            xs.append(float(p.get("x")))
            ys.append(float(p.get("y")))
    margin = 20
    left, top = min(xs) - margin, min(ys) - margin
    width, height = max(xs) - left + margin, max(ys) - top + margin

    back, flows, middle, front = [], [], [], []
    for shape in shapes:
        el = elements[shape.get("bpmnElement")]
        kind = _local(el.tag)
        name = el.get("name") or ""
        b = shape.find("dc:Bounds", NS)
        x, y, w, h = (float(b.get(k)) for k in ("x", "y", "width", "height"))
        label = shape.find("bpmndi:BPMNLabel/dc:Bounds", NS)
        if kind in ("participant", "lane"):
            # A frame, and the name written vertically in a 30 px band on the left.
            band = 30
            pool = kind == "participant"
            separator = (
                f"<line x1='{x + band}' y1='{y}' x2='{x + band}' y2='{y + h}' stroke='{MUTED}'/>"
            )
            back.append(
                f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='none' stroke='{MUTED}'/>"
                + (separator if pool else "")
                + f"<g transform='translate({x + band / 2:.0f},{y + h / 2:.0f}) rotate(-90)'>"
                f"{_text(0, 0, h - 10, name, 12 if pool else 11, INK if pool else MUTED)}</g>"
            )
        elif kind in TASKS:
            fill = HUMAN if kind in ("userTask", "manualTask") else AUTO if TASKS[kind] else FILL
            middle.append(
                f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='10' fill='{fill}' "
                f"stroke='{INK}' stroke-width='1.2'/>"
                f"<text x='{x + 6}' y='{y + 12}' font-size='9' fill='{MUTED}' {FONT}>"
                f"{escape(TASKS[kind])}</text>{_text(x + w / 2, y + h / 2 + 4, w - 10, name)}"
            )
        elif kind in GATEWAYS:
            cx, cy = x + w / 2, y + h / 2
            points = f"{cx},{y} {x + w},{cy} {cx},{y + h} {x},{cy}"
            marker = GATEWAYS[kind]
            if kind == "exclusiveGateway" and shape.get("isMarkerVisible") != "true":
                marker = ""
            inner = (
                f"<text x='{cx}' y='{cy + 1}' font-size='22' fill='{INK}' text-anchor='middle' "
                f"dominant-baseline='middle' {FONT}>{marker}</text>"
                if marker
                else f"<circle cx='{cx}' cy='{cy}' r='{w * 0.22:.1f}' fill='none' stroke='{INK}'/>"
                if kind == "eventBasedGateway"
                else ""
            )
            middle.append(
                f"<polygon points='{points}' fill='{FILL}' stroke='{INK}' "
                f"stroke-width='1.2'/>{inner}"
            )
            if name:
                lx, ly, lw = _label(label, cx, y + h + 12, 90)
                front.append(_text(lx, ly, lw, name, 10, MUTED))
        elif kind in EVENTS:
            cx, cy, r = x + w / 2, y + h / 2, w / 2
            stroke = "3" if kind == "endEvent" else "1.2"
            double = kind not in ("startEvent", "endEvent")
            definitions = {_local(child.tag) for child in el}
            middle.append(
                f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{FILL}' stroke='{INK}' "
                f"stroke-width='{stroke}'/>"
                + (
                    f"<circle cx='{cx}' cy='{cy}' r='{r - 3}' fill='none' stroke='{INK}'/>"
                    if double
                    else ""
                )
                + _trigger(definitions, cx, cy, r)
            )
            if name:
                lx, ly, lw = _label(label, cx, y + h + 14, 100)
                front.append(_text(lx, ly, lw, name, 10, MUTED))

    for edge in edges:
        el = elements[edge.get("bpmnElement")]
        points = " ".join(f"{p.get('x')},{p.get('y')}" for p in edge.findall("di:waypoint", NS))
        flows.append(
            f"<polyline points='{points}' fill='none' stroke='{INK}' stroke-width='1.1' "
            f"marker-end='url(#arrow)'/>"
        )
        name = el.get("name")
        label = edge.find("bpmndi:BPMNLabel/dc:Bounds", NS)
        if name and label is not None:
            lx, ly, lw = _label(label, 0, 0, 80)
            front.append(_text(lx, ly, lw, name, 10, MUTED))

    title = escape(root.find(".//bpmn:process", NS).get("name") or bpmn.stem)
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{left:.0f} {top:.0f} {width:.0f} "
        f"{height:.0f}' width='{width:.0f}' height='{height:.0f}' role='img'>"
        f"<title>{title}</title>"
        "<defs><marker id='arrow' viewBox='0 0 10 10' refX='10' refY='5' markerWidth='7' "
        f"markerHeight='7' orient='auto-start-reverse'><path d='M0,0 L10,5 L0,10 z' fill='{INK}'/>"
        "</marker></defs>"
        f"<rect x='{left:.0f}' y='{top:.0f}' width='{width:.0f}' height='{height:.0f}' "
        f"fill='{FILL}'/>" + "".join(back + flows + middle + front) + "</svg>\n"
    )


def _label(bounds: ET.Element | None, cx: float, cy: float, width: float) -> tuple:
    """Centre and width of a label: its saved bounds, or a default place under the shape."""
    if bounds is None:
        return cx, cy, width
    x, y, w, h = (float(bounds.get(k)) for k in ("x", "y", "width", "height"))
    return x + w / 2, y + h / 2, max(w + 24, 60)


def main() -> int:
    for source, target in DIAGRAMS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(source), encoding="utf-8", newline="\n")
        print(f"{source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
