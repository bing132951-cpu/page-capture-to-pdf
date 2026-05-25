import argparse
import os
import sys

from .browser_collect import collect_from_browser
from .collector import load_document_json, load_url_list, save_document_json
from .models import CollectedDocument, PageImage
from .exporter import export_document_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download JPEG image URLs and merge them into a PDF.")
    parser.add_argument("--verbose", action="store_true", help="Print step-by-step debug output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Launch a project-owned Chrome and collect JPG/JPEG links.")
    collect_parser.add_argument("--target-url", required=True, help="Target page URL to open in Chrome.")
    collect_parser.add_argument("--output", required=True, help="Path to the output JSON file.")
    collect_parser.add_argument("--mode", choices=("scroll", "paginate"), default="scroll", help="Collector mode.")
    collect_parser.add_argument("--image-selector", help="CSS selector for image elements.")
    collect_parser.add_argument("--scroll-container-selector", help="CSS selector for the scroll container.")
    collect_parser.add_argument("--max-steps", type=int, help="Maximum collection steps.")
    collect_parser.add_argument("--delay-ms", type=int, help="Delay between collection steps in milliseconds.")
    collect_parser.add_argument("--scroll-ratio", type=float, help="Scroll distance as a ratio of viewport height.")
    collect_parser.add_argument("--no-new-limit", type=int, help="Stop after this many no-new cycles in scroll mode.")
    collect_parser.add_argument("--min-width", type=int, help="Minimum image width.")
    collect_parser.add_argument("--min-height", type=int, help="Minimum image height.")
    collect_parser.add_argument("--image-filter-pattern", help="Regex for matching image URLs, or auto.")
    collect_parser.add_argument("--page-number-pattern", help="Regex for extracting page numbers, or auto.")
    collect_parser.add_argument("--next-button-selector", help="CSS selector for the next-page button in paginate mode.")
    collect_parser.add_argument("--page-indicator-selector", help="CSS selector for the page indicator text.")
    collect_parser.add_argument("--max-pages", type=int, help="Optional hard limit for collected pages.")
    collect_parser.add_argument("--click-delay-ms", type=int, help="Wait after clicking next in paginate mode.")
    collect_parser.add_argument("--max-unchanged-steps", type=int, help="Stop after this many unchanged transitions.")

    export_parser = subparsers.add_parser("export", help="Export a PDF from a URL list or JSON file.")
    export_parser.add_argument("--pages-json", help="Path to a previously collected JSON file.")
    export_parser.add_argument("--url-list", help="Plain text file with one page image URL per line.")
    export_parser.add_argument("--output", required=True, help="Path to the generated PDF file.")
    export_parser.add_argument(
        "--download-dir",
        default="output/downloads",
        help="Directory for downloaded page images.",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = print if args.verbose else None

    try:
        if args.command == "collect":
            payload = collect_from_browser(
                args.target_url,
                logger=logger,
                collector_options=_collector_options_from_args(args),
            )
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            save_document_json(
                CollectedDocument(
                    title=payload["title"],
                    total_pages=payload["totalPages"],
                    pages=[
                        PageImage(page_number=index, image_url=url)
                        for index, url in enumerate(payload["urlsText"].splitlines(), start=1)
                    ],
                ),
                args.output,
            )
            print(f"Collected {payload['totalPages']} pages into {args.output}")
            return 0

        document = None
        if args.pages_json:
            document = load_document_json(args.pages_json)
        elif args.url_list:
            title = os.path.splitext(os.path.basename(args.output))[0] or "Untitled document"
            document = load_url_list(args.url_list, title=title)

        output_path, document = export_document_pdf(
            output_path=args.output,
            document=document,
            work_dir=args.download_dir,
            logger=logger,
        )
        print(f"Exported {document.total_pages} pages to {output_path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _collector_options_from_args(args) -> dict:
    return {
        "mode": args.mode,
        "imageSelector": args.image_selector,
        "scrollContainerSelector": args.scroll_container_selector,
        "maxSteps": args.max_steps,
        "delayMs": args.delay_ms,
        "scrollRatio": args.scroll_ratio,
        "noNewLimit": args.no_new_limit,
        "minWidth": args.min_width,
        "minHeight": args.min_height,
        "imageFilterPattern": args.image_filter_pattern,
        "pageNumberPattern": args.page_number_pattern,
        "nextButtonSelector": args.next_button_selector,
        "pageIndicatorSelector": args.page_indicator_selector,
        "maxPages": args.max_pages,
        "clickDelayMs": args.click_delay_ms,
        "maxUnchangedSteps": args.max_unchanged_steps,
    }


if __name__ == "__main__":
    raise SystemExit(main())
