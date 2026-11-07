"""Build the Phase 2 evidence PDF using ReportLab (a reporting-only dependency).

Run from the repository root with a Python environment containing ReportLab:
    python -m scripts.build_demo_report

Collect the JSON/JUnit evidence and screenshots first. This command does not run
tests, contact GitHub, query Docker, retrain a model, or modify the registry.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "Phase_2_Demonstration_Evidence.pdf"
PAGE_W, PAGE_H = landscape(A4)
MARGIN = 42
WIDTH = PAGE_W - MARGIN * 2
NAVY = colors.HexColor("#133142")
TEAL = colors.HexColor("#087F83")
INK = colors.HexColor("#203842")
MUTED = colors.HexColor("#526672")
PALE = colors.HexColor("#EEF5F6")
IST = timezone(timedelta(hours=5, minutes=30))


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def plain(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def timestamp(value: str | None) -> str:
    if not value:
        return "timestamp unavailable"
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # This evidence pack's JUnit file was created on the Windows demo host in IST.
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=IST)
    return observed.astimezone(IST).strftime("%d %b %Y, %H:%M IST")


def paragraph(pdf, text, x, top, width, *, size=10.5, color=INK, leading=None, max_height=500):
    style = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=size, leading=leading or size * 1.35,
        textColor=color, spaceAfter=0, splitLongWords=True,
    )
    item = Paragraph(text, style)
    _, height = item.wrap(width, max_height)
    if height > max_height:
        raise ValueError("Report text exceeds its layout box; shorten it before rendering.")
    item.drawOn(pdf, x, top - height)
    return top - height


def table(pdf, rows, top, widths, *, size=9.8):
    style = ParagraphStyle("cell", fontName="Helvetica", fontSize=size, leading=size * 1.3, textColor=INK)
    cells = [[Paragraph(plain(value), style) for value in row] for row in rows]
    result = Table(cells, colWidths=widths, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E2E5")),
    ]))
    _, height = result.wrap(WIDTH, PAGE_H)
    if height > top - 56:
        raise ValueError("Report table exceeds available page height.")
    result.drawOn(pdf, MARGIN, top - height)
    return top - height


def page_header(pdf, number, title, subtitle):
    pdf.setFillColor(NAVY)
    pdf.rect(0, PAGE_H - 15, PAGE_W, 15, fill=1, stroke=0)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(TEAL)
    pdf.drawString(MARGIN, PAGE_H - 42, "TRANSPORTATION ADVISOR  /  PHASE 2")
    paragraph(pdf, plain(title), MARGIN, PAGE_H - 61, WIDTH, size=25, color=NAVY, max_height=55)
    paragraph(pdf, plain(subtitle), MARGIN, PAGE_H - 99, WIDTH, size=10, color=MUTED, max_height=35)
    pdf.setStrokeColor(colors.HexColor("#D8E2E5"))
    pdf.line(MARGIN, 37, PAGE_W - MARGIN, 37)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(MUTED)
    pdf.drawString(MARGIN, 23, "Historical Route 90 demo | Local Windows / WSL 2 deployment")
    pdf.drawRightString(PAGE_W - MARGIN, 23, f"{number} / 9")


def screenshot(pdf, directory, name, *, top=393, bottom=62):
    path = directory / name
    box_h = top - bottom
    pdf.setFillColor(PALE)
    pdf.roundRect(MARGIN, bottom, WIDTH, box_h, 5, fill=1, stroke=0)
    if not path.is_file():
        paragraph(pdf, f"Screenshot not supplied: {plain(name)}.<br/>Use the recorded machine-readable evidence and capture the UI before presenting.", MARGIN + 22, top - 30, WIDTH - 44, color=MUTED)
        return
    image = ImageReader(str(path))
    iw, ih = image.getSize()
    scale = min((WIDTH - 12) / iw, (box_h - 12) / ih)
    dw, dh = iw * scale, ih * scale
    pdf.drawImage(image, MARGIN + (WIDTH - dw) / 2, bottom + (box_h - dh) / 2, dw, dh, mask="auto")


def build_report(output: Path) -> None:
    evidence = ROOT / "outputs" / "phase2_demo"
    snapshots = ROOT / "docs" / "results" / "phase2-v1"
    runtime = read_json(evidence / "deployment_check.json")
    registry = read_json(evidence / "registry_check.json")
    ci = read_json(evidence / "ci_run.json")
    quality = read_json(snapshots / "quality_report.json")
    registered = read_json(snapshots / "registration.json")
    release = read_json(ROOT / "deploy" / "model-v1.json")
    junit = ET.parse(evidence / "pytest.xml").getroot()
    suites = [junit] if junit.tag == "testsuite" else list(junit.iter("testsuite"))
    counts = {key: sum(int(item.get(key, "0")) for item in suites) for key in ("tests", "failures", "errors", "skipped")}
    test_time = suites[0].get("timestamp") if suites else None
    passed = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    screenshots = evidence / "screenshots"
    http = {item["case"]: item for item in runtime["http_checks"]}
    model = registry["model_version"]
    candidate = quality["candidate"]
    median = "Historical-Median Baseline"
    tags = {item["key"]: item["value"] for item in registry.get("tags", [])}
    registry_matches = (
        model.get("name") == registered["model_name"]
        and model.get("status") == registered["status"] == "READY"
        and model.get("version") == registered["version"]
        and model.get("run_id") == registered["training_run_id"]
        and tags.get("joblib_sha256") == registered["joblib_sha256"]
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    pdf.setTitle("Phase 2 MLOps Demonstration Evidence")
    pdf.setAuthor("AI-Powered Sustainable Transportation Advisor project team")
    pdf.setSubject("Recorded test, model quality, registry, API, Docker and CI/release evidence")

    # 1: The distinction between historical approval and current runtime is explicit.
    page_header(pdf, 1, "MLOps demonstration evidence", f"Report assembled {timestamp(datetime.now(timezone.utc).isoformat())}. Evidence timestamps below identify when each check ran.")
    status_rows = [
        ["Evidence", "Recorded result", "When checked"],
        ["Current Python suite", f"{passed}/{counts['tests']} passed; {counts['failures']} failures; {counts['errors']} errors; {counts['skipped']} skipped", timestamp(test_time)],
        ["Local runtime", f"overall_passed={runtime['overall_passed']}; {len(runtime['passed_checks'])} checks", timestamp(runtime['checked_at_utc'])],
        ["MLflow registry", f"v{model['version']} {model['status']}; approval match={registry_matches}", timestamp(registry['checked_at_utc'])],
        ["GitHub CI", f"{ci['status']} / {ci['conclusion']}", timestamp(ci.get('updated_at'))],
        ["Historical release quality", f"quality_gate_passed={quality['quality_gate_passed']}", timestamp(quality['checked_at_utc'])],
    ]
    top = table(pdf, status_rows, 448, [170, 355, WIDTH - 525], size=9.5) - 20
    top = paragraph(pdf, "<b>Tools and their role</b><br/>Pytest checks the pipeline, API and recovery paths. pandas and scikit-learn support historical quality evaluation. MLflow tracks experiments and registers the versioned model; Joblib stores its artifact. FastAPI/Pydantic/Uvicorn serve inference. Docker Desktop, WSL 2 and Compose run the local service. GitHub Actions tests/builds the image; GHCR stores the published release.", MARGIN, top, WIDTH, size=10.3, max_height=110) - 13
    paragraph(pdf, "<b>Deployment boundary:</b> GitHub Actions automates tests, image build, publication and published-image verification. A local command starts the scripted workstation deployment. This report does not claim automatic deployment from GitHub to the Windows PC.", MARGIN, top, WIDTH, size=10.3, max_height=80)
    pdf.showPage()

    # 2: Actual metrics, samples, splits and limits from the historical approval.
    page_header(pdf, 2, "Model quality and approved scope", f"{candidate} | cold_start_v1 | historical approval recorded {timestamp(quality['checked_at_utc'])}")
    top = paragraph(pdf, f"<b>Approved use:</b> Route {plain(quality['demo_scope']['route_id'])}, eastbound segment {plain(quality['demo_scope']['segment_id'])}. Target: segment riding time in minutes.", MARGIN, 451, WIDTH, size=10.5) - 15
    split_rows = [["Split", "IST observation dates", "Traversals"]]
    split_rows += [[key.title(), ", ".join(quality["split_dates_ist"][key]), quality["split_counts"][key]] for key in ("train", "validation", "test")]
    top = table(pdf, split_rows, top, [100, 520, WIDTH - 620], size=9.4) - 16
    metric_rows = [["Scope", "Model", "MAE min", "RMSE min", "MAPE %"]]
    for scope, metrics in (("All test traversals", quality['test_metrics']), (f"Route 90: {quality['demo_scope']['held_out_traversals']} traversals", quality['demo_scope']['metrics'])):
        for name in (candidate, median):
            values = metrics[name]
            metric_rows.append([scope, name, f"{values['mae_minutes']:.3f}", f"{values['rmse_minutes']:.3f}", f"{values['mape_percent']:.2f}"])
    top = table(pdf, metric_rows, top, [190, 245, 100, 105, WIDTH - 640], size=9.3) - 14
    top = paragraph(pdf, f"<b>Selection and checks:</b> The candidate's validation MAE was {quality['validation_metrics'][candidate]['mae_minutes']:.3f} minutes. The saved report records {sum(value is True for value in quality['checks'].values())}/{len(quality['checks'])} passing quality checks. Checks include split agreement, feature consistency, candidate improvement, finite positive predictions, reload agreement and logged-artifact hashes. The earlier approval-stage test count is {quality['pytest']['tests']}; the current suite is recorded on page 1.", MARGIN, top, WIDTH, size=9.6, max_height=80) - 10
    paragraph(pdf, "<b>Limits:</b> " + " ".join(plain(item) for item in quality['limitations']) + " Inference does not consume a live GPS feed. An HTTP success validates serving behavior; historical error metrics support the accuracy claim.", MARGIN, top, WIDTH, size=9.6, max_height=70)
    pdf.showPage()

    # 3-9: Evidence screenshots, each kept on its own wide page.
    page_header(pdf, 3, "MLflow model registry", "Dashboard screenshot from a local registry copy; the original store was checked separately in read-only mode.")
    paragraph(pdf, f"<b>Observed:</b> {plain(model['name'])} v{model['version']} - {plain(model['status'])}; training run {plain(model['run_id'])}.<br/><b>Artifact SHA-256:</b> {plain(registered['joblib_sha256'])}<br/><b>Registry / approval identity match:</b> {registry_matches}. Read-only registry check: {timestamp(registry['checked_at_utc'])}.", MARGIN, 452, WIDTH, size=10.1, max_height=68)
    screenshot(pdf, screenshots, "mlflow_registry.jpg", top=382)
    pdf.showPage()

    health = http.get("readiness")
    page_header(pdf, 4, "FastAPI readiness", "The service reports the loaded model version and feature-history policy.")
    paragraph(pdf, f"<b>Runtime check:</b> {timestamp(runtime['checked_at_utc'])}.<br/><b>Recorded GET /health:</b> {plain(json.dumps(health, separators=(', ', ': ')) if health else 'No readiness record supplied')}", MARGIN, 452, WIDTH, size=10.2, max_height=68)
    screenshot(pdf, screenshots, "api_health.jpg", top=386)
    pdf.showPage()

    prediction = http.get("approved_prediction")
    page_header(pdf, 5, "Approved bus-time prediction", "The published model predicts duration for the documented historical Route 90 request.")
    if prediction:
        detail = f"<b>Request:</b> {plain(json.dumps(prediction['request'], separators=(', ', ': ')))}<br/><b>Observed response (HTTP {prediction['status']}):</b> {plain(json.dumps(prediction['response'], separators=(', ', ': ')))}"
    else:
        detail = "No approved-prediction runtime record supplied."
    paragraph(pdf, detail, MARGIN, 452, WIDTH, size=10.2, max_height=70)
    screenshot(pdf, screenshots, "api_prediction.jpg", top=380)
    pdf.showPage()

    rejection = http.get("unsupported_route")
    page_header(pdf, 6, "Request validation and model scope", "Requests outside the approved route/segment and timestamps without a timezone are rejected.")
    cases = [(name, http[name]["status"]) for name in ("unsupported_route", "unsupported_segment", "missing_timezone") if name in http]
    paragraph(pdf, "<b>Observed HTTP checks:</b> " + plain("; ".join(f"{name}: HTTP {status}" for name, status in cases)) + ".<br/><b>Unsupported-route response:</b> " + plain(json.dumps(rejection['response']) if rejection else "No record supplied"), MARGIN, 452, WIDTH, size=10.2, max_height=68)
    screenshot(pdf, screenshots, "api_rejection.jpg", top=386)
    pdf.showPage()

    container = runtime.get("container", {})
    page_header(pdf, 7, "Docker deployment on Windows / WSL 2", "The verifier compares the running container and its repository digest with the approved release.")
    paragraph(pdf, f"<b>Observed container:</b> running={plain(container.get('running', 'unavailable'))}, health={plain(container.get('health', 'unavailable'))}; binding {plain(json.dumps(container.get('ports', {})))}.<br/><b>Approved image:</b> {plain(release['image'])}<br/><b>Image source revision:</b> {plain(container.get('source_revision', 'unavailable'))}. Runtime verification overall_passed={runtime['overall_passed']}.", MARGIN, 452, WIDTH, size=9.5, max_height=80)
    screenshot(pdf, screenshots, "docker_container.png", top=367)
    pdf.showPage()

    page_header(pdf, 8, "Continuous integration", "GitHub Actions tests source, builds a fixture image, and checks readiness, prediction and validation over HTTP.")
    paragraph(pdf, f"<b>Recorded CI:</b> {plain(ci['name'])} - {plain(ci['status'])} / {plain(ci['conclusion'])}; source {plain(ci['head_sha'])}.<br/><b>Run:</b> <link href=\"{escape(ci['html_url'], quote=True)}\" color=\"#087F83\">{plain(ci['html_url'])}</link><br/>The controlled CI fixture expects 6.25 minutes. The real released model has the separate 6.3204-minute sample result shown on page 5.", MARGIN, 452, WIDTH, size=10.0, max_height=75)
    screenshot(pdf, screenshots, "github_ci.jpg", top=376)
    pdf.showPage()

    page_header(pdf, 9, "Image release and classroom demonstration", "The v1 release publishes the verified real-model image; local deployment then uses its immutable digest.")
    release_run = release['release_run']
    paragraph(pdf, f"<b>Release record:</b> <link href=\"{escape(release_run, quote=True)}\" color=\"#087F83\">{plain(release_run)}</link><br/>The release workflow verifies bundle hashes, tests the real model, publishes the image, then pulls and checks the published digest on a fresh runner. Use the visible run result below as publication evidence.<br/><b>Present in this order:</b> current tests, historical quality, MLflow registry, CI/release, Docker health, valid prediction, HTTP 422. Deployment command: <font face=\"Courier\">python -m scripts.deploy_api --port 8001</font>. Verify with <font face=\"Courier\">python -m scripts.verify_deployment</font>.", MARGIN, 452, WIDTH, size=9.8, max_height=95)
    screenshot(pdf, screenshots, "github_release.jpg", top=351)
    pdf.showPage()
    pdf.save()
    print(f"Wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        build_report(args.output)
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        parser.exit(1, f"Could not build evidence report: {exc}\n")


if __name__ == "__main__":
    main()
