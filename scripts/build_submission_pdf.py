from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Akash - Infrastructure SRE Intern Assignment.pdf"
GITHUB_LINK = "https://github.com/<your-username>/zeotap-ims-assignment"


def story():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallMono", fontName="Courier", fontSize=8, leading=10))
    title = styles["Title"]
    heading = styles["Heading2"]
    body = styles["BodyText"]
    body.leading = 14

    sections = [
        Paragraph("Akash - Infrastructure / SRE Intern Assignment", title),
        Paragraph(f"<b>GitHub Link:</b> {GITHUB_LINK}", body),
        Spacer(1, 0.2 * inch),
        Paragraph("Project Summary", heading),
        Paragraph(
            "This repository implements a resilient Incident Management System for high-volume distributed-stack signals. "
            "It includes an async FastAPI backend, a React dashboard, debounced incident creation, mandatory RCA closure, "
            "MTTR calculation, rate limiting, health checks, throughput logging, sample data, and tests.",
            body,
        ),
        Paragraph("Architecture", heading),
        Paragraph(
            "Signal producers send JSON payloads to the FastAPI ingestion API. A sliding-window rate limiter protects the "
            "edge. Accepted signals enter a bounded asyncio queue so persistence slowness does not crash ingestion. Async "
            "workers write raw signals to an append-only JSONL data lake, structured incidents/RCA to SQLite, per-minute "
            "aggregates to SQLite, and active state to an in-memory dashboard cache. The React dashboard reads incidents, "
            "raw signals, status, and RCA state from the backend.",
            body,
        ),
        Paragraph("Key Requirements Covered", heading),
        Paragraph(
            "Async processing, 10-second component debouncing, separate raw/structured/cache/aggregate storage paths, "
            "Strategy pattern alert routing, state-machine workflow transitions, mandatory RCA before CLOSED, MTTR "
            "calculation, rate limiting, /health endpoint, throughput metrics every 5 seconds, Docker Compose packaging, "
            "sample failure data, and RCA validation tests.",
            body,
        ),
        Paragraph("Run Instructions", heading),
        Paragraph("docker compose up --build", styles["SmallMono"]),
        Paragraph("Dashboard: http://localhost:5173", body),
        Paragraph("Backend health: http://localhost:8000/health", body),
        Paragraph("API docs: http://localhost:8000/docs", body),
        Paragraph("Seed sample data: python scripts/seed_failure.py", styles["SmallMono"]),
        Paragraph("Tests", heading),
        Paragraph("cd backend && pip install -r requirements.txt && pytest", styles["SmallMono"]),
        Paragraph("Backpressure", heading),
        Paragraph(
            "The API returns after enqueueing signals into a fixed-size async queue. When the queue is full, the response "
            "reports rejected items instead of allowing memory growth or process failure. Worker persistence uses retry "
            "with exponential backoff.",
            body,
        ),
        Paragraph("Bonus / Non-Functional Work", heading),
        Paragraph(
            "Input validation with Pydantic, restricted CORS configuration, Docker health checks, explicit rate limiting, "
            "transactional RCA/status updates, async-safe write locking, retry logic, and documentation for architecture, "
            "prompts, plans, setup, and backpressure.",
            body,
        ),
    ]
    return sections


def main() -> None:
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    doc.build(story())
    print(OUTPUT)


if __name__ == "__main__":
    main()
