import json
import re
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Optional

from .cdp_client import CdpClient, CdpError
from .chrome_launcher import ChromeLaunchError, launch_debug_chrome


class BrowserCollectError(RuntimeError):
    """Raised when browser-based collection fails at a known stage."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


DEFAULT_COLLECTOR_OPTIONS = {
    "mode": "scroll",
    "maxSteps": 220,
    "delayMs": 800,
    "scrollRatio": 1.2,
    "noNewLimit": 18,
    "imageSelector": "img",
    "scrollContainerSelector": "",
    "minWidth": 180,
    "minHeight": 180,
    "imageFilterPattern": "auto",
    "pageNumberPattern": "auto",
    "nextButtonSelector": "",
    "pageIndicatorSelector": "",
    "maxPages": "",
    "clickDelayMs": 1000,
    "maxUnchangedSteps": 3,
}


COLLECTOR_SCRIPT_TEMPLATE = r"""
(async (userConfig) => {
  const config = Object.assign({
    mode: "scroll",
    maxSteps: 220,
    delayMs: 800,
    scrollRatio: 1.2,
    noNewLimit: 18,
    imageSelector: "img",
    scrollContainerSelector: "",
    minWidth: 180,
    minHeight: 180,
    imageFilterPattern: "auto",
    pageNumberPattern: "auto",
    nextButtonSelector: "",
    pageIndicatorSelector: "",
    maxPages: "",
    clickDelayMs: 1000,
    maxUnchangedSteps: 3
  }, userConfig || {});

  const imageFilter = config.imageFilterPattern && config.imageFilterPattern !== "auto"
    ? new RegExp(config.imageFilterPattern, "i")
    : null;
  const pageNumberRegex = config.pageNumberPattern && config.pageNumberPattern !== "auto"
    ? new RegExp(config.pageNumberPattern, "i")
    : null;
  const autoImageRegex = /\.(jpg|jpeg|png|webp|gif|bmp|avif|svg)(\?|#|$)/i;
  const autoPageRegexes = [
    /(?:^|\/)(\d+)(?:[-_.][^/]+)?\.(?:jpg|jpeg|png|webp|gif|bmp|avif|svg)(?:\?|#|$)/i,
    /(?:^|\/)(?:page|p)[^\d]{0,3}(\d+)(?:[^\d/][^/]*)?(?:\?|#|$)/i,
    /[?&](?:page|p)=(\d+)/i
  ];
  const seen = new Map();
  const stats = {
    mode: config.mode,
    stepsRun: 0,
    clicksRun: 0,
    duplicateCount: 0,
    filteredByType: 0,
    filteredBySize: 0,
    missingSrcCount: 0,
    stalledScrollCount: 0,
    buttonMissingCount: 0,
    unchangedSteps: 0,
    currentPage: null,
    totalPagesDetected: null,
    finalScrollTop: 0,
    totalDomImagesLastScan: 0,
    stopReason: "",
    stopDetails: ""
  };

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function getScrollRoot() {
    if (!config.scrollContainerSelector) {
      return window;
    }
    return document.querySelector(config.scrollContainerSelector) || window;
  }

  const scrollRoot = getScrollRoot();

  function getScrollTop() {
    if (scrollRoot === window) return window.scrollY;
    return scrollRoot.scrollTop;
  }

  function getViewportHeight() {
    if (scrollRoot === window) return window.innerHeight;
    return scrollRoot.clientHeight || window.innerHeight;
  }

  function scrollByRatio(ratio) {
    const distance = getViewportHeight() * ratio;
    if (scrollRoot === window) {
      window.scrollBy(0, distance);
    } else {
      scrollRoot.scrollBy(0, distance);
    }
  }

  function scrollToTop() {
    if (scrollRoot === window) {
      window.scrollTo(0, 0);
    } else {
      scrollRoot.scrollTop = 0;
    }
  }

  function extractPageNumber(rawSrc, resolvedSrc) {
    if (pageNumberRegex) {
      const customMatch = rawSrc.match(pageNumberRegex) || resolvedSrc.match(pageNumberRegex);
      return customMatch ? Number(customMatch[1]) : null;
    }
    for (const regex of autoPageRegexes) {
      const match = rawSrc.match(regex) || resolvedSrc.match(regex);
      if (match) {
        return Number(match[1]);
      }
    }
    return null;
  }

  function getImageSources(img) {
    const rawSrc =
      img.getAttribute("src") ||
      img.getAttribute("data-src") ||
      img.getAttribute("data-lazy-src") ||
      img.getAttribute("data-original") ||
      img.currentSrc ||
      img.src ||
      "";
    let resolvedSrc = rawSrc;
    try {
      resolvedSrc = new URL(rawSrc, document.baseURI).href;
    } catch (error) {
      resolvedSrc = rawSrc;
    }
    return { rawSrc, resolvedSrc };
  }

  function matchesImageFilter(rawSrc, resolvedSrc) {
    if (imageFilter) {
      return imageFilter.test(rawSrc) || imageFilter.test(resolvedSrc);
    }
    return autoImageRegex.test(rawSrc) || autoImageRegex.test(resolvedSrc);
  }

  function getImageSize(img) {
    return {
      width: img.naturalWidth || img.width || 0,
      height: img.naturalHeight || img.height || 0
    };
  }

  function isVisibleImage(img, width, height) {
    const style = window.getComputedStyle(img);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return false;
    }
    const rect = img.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }
    if (width <= 0 || height <= 0) {
      return false;
    }
    const inViewportHorizontally = rect.right > 0 && rect.left < window.innerWidth;
    const inViewportVertically = rect.bottom > 0 && rect.top < window.innerHeight;
    return inViewportHorizontally && inViewportVertically;
  }

  function readPageIndicator() {
    if (!config.pageIndicatorSelector) {
      return { currentPage: null, totalPages: null, rawText: "" };
    }
    const node = document.querySelector(config.pageIndicatorSelector);
    if (!node) {
      return { currentPage: null, totalPages: null, rawText: "" };
    }
    const rawText = (node.textContent || node.getAttribute("value") || "").trim();
    const slashMatch = rawText.match(/(\d+)\s*\/\s*(\d+)/);
    if (slashMatch) {
      return {
        currentPage: Number(slashMatch[1]),
        totalPages: Number(slashMatch[2]),
        rawText
      };
    }
    const numberMatches = [...rawText.matchAll(/\d+/g)].map(match => Number(match[0]));
    if (numberMatches.length >= 2) {
      return {
        currentPage: numberMatches[0],
        totalPages: numberMatches[1],
        rawText
      };
    }
    if (numberMatches.length === 1) {
      return {
        currentPage: numberMatches[0],
        totalPages: null,
        rawText
      };
    }
    return { currentPage: null, totalPages: null, rawText };
  }

  function buildVisibleSignature() {
    const images = [...document.querySelectorAll(config.imageSelector)]
      .map(img => {
        const { rawSrc, resolvedSrc } = getImageSources(img);
        const { width, height } = getImageSize(img);
        return {
          rawSrc,
          resolvedSrc,
          width,
          height,
          visible: isVisibleImage(img, width, height)
        };
      })
      .filter(item => item.visible && matchesImageFilter(item.rawSrc, item.resolvedSrc))
      .map(item => item.resolvedSrc);
    const indicator = readPageIndicator();
    return JSON.stringify({
      currentPage: indicator.currentPage,
      totalPages: indicator.totalPages,
      images
    });
  }

  function sortEntries(entries) {
    return entries.sort((a, b) => {
      const ka = a.pageNumber ?? Number.MAX_SAFE_INTEGER;
      const kb = b.pageNumber ?? Number.MAX_SAFE_INTEGER;
      if (ka !== kb) return ka - kb;
      return a.imageUrl.localeCompare(b.imageUrl);
    });
  }

  function collectOnce(visibleOnly = false) {
    const imgs = [...document.querySelectorAll(config.imageSelector)];
    stats.totalDomImagesLastScan = imgs.length;
    let newCount = 0;
    for (const img of imgs) {
      const { rawSrc, resolvedSrc } = getImageSources(img);
      if (!rawSrc && !resolvedSrc) {
        stats.missingSrcCount += 1;
        continue;
      }
      if (!matchesImageFilter(rawSrc, resolvedSrc)) {
        stats.filteredByType += 1;
        continue;
      }
      const { width, height } = getImageSize(img);
      if (width < config.minWidth || height < config.minHeight) {
        stats.filteredBySize += 1;
        continue;
      }
      if (visibleOnly && !isVisibleImage(img, width, height)) {
        continue;
      }
      const pageNumber = extractPageNumber(rawSrc, resolvedSrc);
      const key = pageNumber ?? resolvedSrc;
      if (!seen.has(key)) {
        seen.set(key, {
          pageNumber,
          imageUrl: resolvedSrc,
          rawImageUrl: rawSrc,
          width,
          height
        });
        newCount += 1;
      } else {
        stats.duplicateCount += 1;
      }
    }
    return newCount;
  }

  async function runScrollMode() {
    scrollToTop();
    await sleep(config.delayMs);

    let noNewCount = 0;
    let lastScrollY = -1;
    let stopReason = "max_steps";
    let stopDetails = `Reached configured maxSteps=${config.maxSteps}.`;

    for (let i = 0; i < config.maxSteps; i++) {
      stats.stepsRun = i + 1;
      const addedBefore = collectOnce();
      const beforeY = getScrollTop();
      scrollByRatio(config.scrollRatio);
      await sleep(config.delayMs);
      const addedAfter = collectOnce();
      const afterY = getScrollTop();
      const addedTotal = addedBefore + addedAfter;

      if (addedTotal === 0) {
        noNewCount += 1;
      } else {
        noNewCount = 0;
      }
      if (afterY === beforeY || afterY === lastScrollY) {
        noNewCount += 2;
        stats.stalledScrollCount += 1;
      }
      lastScrollY = afterY;
      if (noNewCount >= config.noNewLimit) {
        stopReason = "no_new_limit";
        stopDetails = `Stopped after ${noNewCount} consecutive no-new cycles.`;
        break;
      }
    }

    collectOnce();
    return { stopReason, stopDetails };
  }

  function isNextButtonActionable(button) {
    if (!button) {
      return false;
    }
    if (button.disabled) {
      return false;
    }
    const ariaDisabled = button.getAttribute("aria-disabled");
    if (ariaDisabled && ariaDisabled.toLowerCase() === "true") {
      return false;
    }
    const style = window.getComputedStyle(button);
    if (style.display === "none" || style.visibility === "hidden" || style.pointerEvents === "none") {
      return false;
    }
    return true;
  }

  async function waitForVisibleChange(previousSignature) {
    const deadline = Date.now() + Math.max(200, config.clickDelayMs);
    while (Date.now() < deadline) {
      await sleep(200);
      const currentSignature = buildVisibleSignature();
      if (currentSignature !== previousSignature) {
        return true;
      }
    }
    return false;
  }

  async function runPaginateMode() {
    let stopReason = "max_steps";
    let stopDetails = `Reached configured maxSteps=${config.maxSteps}.`;

    await sleep(config.delayMs);

    for (let i = 0; i < config.maxSteps; i++) {
      stats.stepsRun = i + 1;
      collectOnce(true);
      const indicator = readPageIndicator();
      stats.currentPage = indicator.currentPage;
      stats.totalPagesDetected = indicator.totalPages;

      if (config.maxPages && seen.size >= config.maxPages) {
        stopReason = "max_pages";
        stopDetails = `Stopped after reaching configured maxPages=${config.maxPages}.`;
        break;
      }

      if (indicator.totalPages && indicator.currentPage && indicator.currentPage >= indicator.totalPages) {
        stopReason = "reached_total_pages";
        stopDetails = `Stopped at page ${indicator.currentPage} of ${indicator.totalPages}.`;
        break;
      }

      const nextButton = document.querySelector(config.nextButtonSelector);
      if (!isNextButtonActionable(nextButton)) {
        stats.buttonMissingCount += 1;
        stopReason = "next_button_unavailable";
        stopDetails = `Next button is unavailable for selector: ${config.nextButtonSelector}`;
        break;
      }

      const previousSignature = buildVisibleSignature();
      nextButton.click();
      stats.clicksRun += 1;
      const changed = await waitForVisibleChange(previousSignature);

      if (!changed) {
        stats.unchangedSteps += 1;
      } else {
        stats.unchangedSteps = 0;
      }

      if (stats.unchangedSteps >= config.maxUnchangedSteps) {
        stopReason = "content_unchanged";
        stopDetails = `Stopped after ${stats.unchangedSteps} unchanged page transitions.`;
        break;
      }
    }

    collectOnce(true);
    return { stopReason, stopDetails };
  }

  const modeResult = config.mode === "paginate"
    ? await runPaginateMode()
    : await runScrollMode();

  const pages = sortEntries([...seen.values()]);
  const urlsText = pages.map(item => item.imageUrl).join("\n");
  stats.finalScrollTop = getScrollTop();
  stats.stopReason = modeResult.stopReason;
  stats.stopDetails = modeResult.stopDetails;
  return {
    title: document.title || "Collected pages",
    totalPages: pages.length,
    urlsText,
    pagesJson: pages,
    stopReason: modeResult.stopReason,
    stopDetails: modeResult.stopDetails,
    stats,
    configUsed: config
  };
})(__COLLECTOR_OPTIONS__)
"""


def collect_from_browser(
    target_url: str,
    logger: Optional[Callable[[str], None]] = None,
    collector_options: Optional[Dict] = None,
) -> Dict:
    _log(logger, f"Launching project-owned Chrome for: {target_url}")
    options = normalize_collector_options(collector_options)
    try:
        with launch_debug_chrome(target_url) as session:
            client = CdpClient(session["web_socket_debugger_url"])
            try:
                client.send("Page.enable")
                client.send("Runtime.enable")
                _wait_for_page_ready(target_url, logger=logger)
                _log(logger, "Running lazy-image collector in Chrome.")
                result = client.send(
                    "Runtime.evaluate",
                    {
                        "expression": build_collector_expression(options),
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                )
            finally:
                client.close()
    except ChromeLaunchError as exc:
        raise BrowserCollectError("launch", str(exc)) from exc
    except CdpError as exc:
        raise BrowserCollectError("cdp", str(exc)) from exc

    payload = result.get("result", {}).get("value")
    if not isinstance(payload, dict):
        raise BrowserCollectError("collect", "Collector returned an unexpected payload.")
    payload["title"] = _clean_title(str(payload.get("title") or "Collected pages"))
    payload["totalPages"] = int(payload.get("totalPages") or 0)
    if payload["totalPages"] <= 0:
        raise BrowserCollectError(
            "collect",
            "Collector did not find any qualifying image URLs on the page.",
        )
    _log(
        logger,
        "Collector stopped with "
        f"{payload.get('stopReason')}: {payload.get('stopDetails')} "
        f"(pages={payload['totalPages']}, steps={payload.get('stats', {}).get('stepsRun')})",
    )
    return payload


def _wait_for_page_ready(target_url: str, logger: Optional[Callable[[str], None]] = None) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(target_url, timeout=5) as response:
                if getattr(response, "status", 200) >= 200:
                    _log(logger, "Target page responded; waiting for lazy images.")
                    time.sleep(2)
                    return
        except (urllib.error.URLError, ValueError):
            time.sleep(0.5)
    time.sleep(2)


def _clean_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or "Collected pages"


def _log(logger: Optional[Callable[[str], None]], message: str) -> None:
    if logger is not None:
        logger(message)


def build_collector_expression(options: Dict) -> str:
    return COLLECTOR_SCRIPT_TEMPLATE.replace("__COLLECTOR_OPTIONS__", json.dumps(options, ensure_ascii=False))


def normalize_collector_options(options: Optional[Dict]) -> Dict:
    merged = dict(DEFAULT_COLLECTOR_OPTIONS)
    if options:
        merged.update({key: value for key, value in options.items() if value not in (None, "")})
    merged["mode"] = str(merged.get("mode", "scroll")).strip().lower() or "scroll"
    if merged["mode"] not in {"scroll", "paginate"}:
        raise ValueError("collector mode must be either 'scroll' or 'paginate'.")
    merged["maxSteps"] = max(1, int(merged["maxSteps"]))
    merged["delayMs"] = max(100, int(merged["delayMs"]))
    merged["scrollRatio"] = max(0.1, float(merged["scrollRatio"]))
    merged["noNewLimit"] = max(1, int(merged["noNewLimit"]))
    merged["minWidth"] = max(0, int(merged["minWidth"]))
    merged["minHeight"] = max(0, int(merged["minHeight"]))
    merged["imageSelector"] = str(merged["imageSelector"])
    merged["scrollContainerSelector"] = str(merged.get("scrollContainerSelector", ""))
    merged["imageFilterPattern"] = str(merged["imageFilterPattern"]).strip() or "auto"
    merged["pageNumberPattern"] = str(merged["pageNumberPattern"]).strip() or "auto"
    merged["nextButtonSelector"] = str(merged.get("nextButtonSelector", "")).strip()
    merged["pageIndicatorSelector"] = str(merged.get("pageIndicatorSelector", "")).strip()
    merged["clickDelayMs"] = max(100, int(merged.get("clickDelayMs", 1000)))
    merged["maxUnchangedSteps"] = max(1, int(merged.get("maxUnchangedSteps", 3)))
    merged["maxPages"] = int(merged["maxPages"]) if str(merged.get("maxPages", "")).strip() else ""
    if merged["mode"] == "paginate" and not merged["nextButtonSelector"]:
        raise ValueError("paginate mode requires a nextButtonSelector.")
    return merged
