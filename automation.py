"""
automation.py — Playwright automation for Telangana EPermit Transit Pass generation.

Flow per record:
  1. Login with OTP
  2. Dismiss any popup
  3. E-Trans → Permits → Approved Permits
  4. Click "New" in Transit Passes column
  5. Step 1 — MDL Selection → Get Details
  6. Step 2 — Select Aggregator
  7. Step 3 — Consignee Info (Qty, Stationary No, Sales Value) → Next
  8. Step 4 — Vehicle & Driver Info → Print Transit Pass
  9. Capture PDF from print popup window
"""
from __future__ import annotations

import asyncio
import base64
import time
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional

from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    BrowserContext,
    TimeoutError as PWTimeout,
)

import config


# ─────────────────────────────────────────────────────────────────
#  Low-level helpers
# ─────────────────────────────────────────────────────────────────

async def try_selectors(page: Page, selectors: list[str], timeout: int = 3000) -> Optional[str]:
    if not selectors:
        return None
    combined = ", ".join(selectors)
    try:
        el = await page.wait_for_selector(combined, timeout=timeout, state="visible")
        if el:
            for sel in selectors:
                try:
                    if await page.locator(sel).first.is_visible():
                        return sel
                except Exception:
                    continue
            return selectors[0]
    except Exception:
        pass
    return None


async def safe_fill(page: Page, selectors: list[str], value: str) -> bool:
    sel = await try_selectors(page, selectors)
    if sel:
        try:
            await page.fill(sel, value)
            return True
        except Exception:
            pass
    return False


async def safe_select(page: Page, selectors: list[str], value: str) -> bool:
    sel = await try_selectors(page, selectors)
    if not sel:
        return False
    # Try exact value, then label, then partial label match
    for method in ["value", "label"]:
        try:
            if method == "value":
                await page.select_option(sel, value=value)
            else:
                await page.select_option(sel, label=value)
            return True
        except Exception:
            continue
    # Partial text match fallback
    try:
        opts = await page.query_selector_all(f"{sel} option")
        for opt in opts:
            text = (await opt.inner_text()).strip()
            if value.lower() in text.lower():
                opt_val = await opt.get_attribute("value")
                await page.select_option(sel, value=opt_val)
                return True
    except Exception:
        pass
    return False


async def safe_click(page: Page, selectors: list[str], timeout: int = 5000) -> bool:
    sel = await try_selectors(page, selectors, timeout=timeout)
    if sel:
        try:
            await page.locator(sel).first.click()
            return True
        except Exception as e:
            try:
                await page.locator(sel).first.evaluate("el => el.click()")
                return True
            except Exception as js_err:
                pass
    return False


async def wait_for_ajax(page: Page, timeout: int = 8000):
    """
    Wait for ASP.NET AJAX PostBack to complete.
    If a postback is in progress, waits until 'endRequest' is fired.
    Otherwise, returns immediately.
    """
    try:
        # Give a very brief moment (80ms) for the browser to trigger/start the postback
        # if the change event was queued
        await page.wait_for_timeout(80)
        
        await page.evaluate("""
            (timeoutMs) => {
                return new Promise((resolve, reject) => {
                    if (typeof Sys !== 'undefined' && Sys.WebForms && Sys.WebForms.PageRequestManager) {
                        const prm = Sys.WebForms.PageRequestManager.getInstance();
                        if (prm.get_isInAsyncPostBack()) {
                            const handler = () => {
                                prm.remove_endRequest(handler);
                                clearTimeout(tid);
                                resolve();
                            };
                            const tid = setTimeout(() => {
                                prm.remove_endRequest(handler);
                                reject(new Error("AJAX PostBack timeout"));
                            }, timeoutMs);
                            prm.add_endRequest(handler);
                        } else {
                            resolve();
                        }
                    } else {
                        resolve();
                    }
                });
            }
        """, timeout)
    except Exception:
        # Fallback if Sys is not defined or error occurs
        await page.wait_for_timeout(500)


async def take_screenshot(page: Page, name: str) -> str:
    folder = Path("screenshots")
    folder.mkdir(exist_ok=True)
    ts = int(time.time())
    path = folder / f"{name}_{ts}.png"
    try:
        await page.screenshot(path=str(path), full_page=False)
    except Exception:
        pass
    return str(path)


async def discover_fields(page: Page) -> list[dict]:
    return await page.evaluate("""() => {
        const visible = el => el.offsetParent !== null && el.offsetWidth > 0;
        return Array.from(document.querySelectorAll('input,select,textarea,button,a'))
            .filter(visible)
            .map(el => ({
                tag:   el.tagName,
                id:    el.id || '',
                name:  el.name || '',
                type:  el.type || '',
                text:  (el.innerText||'').trim().substring(0,60),
                value: el.value || '',
                href:  (el.href||'').split('/').slice(-1)[0],
            }));
    }""")


async def dismiss_popup(page: Page, log_fn=None):
    """Close any modal/alert popup that may appear after login."""
    close_sels = [
        "button:has-text('Close')",
        "button:has-text('OK')",
        ".close",
        ".btn-close",
        ".modal-close",
        "[aria-label='Close']",
        "[data-dismiss='modal']",
        ".modal-footer button",
        "span:has-text('×')",
        "button:has-text('×')",
        "a:has-text('×')",
        "span:has-text('x')",
        "button:has-text('x')",
        "a:has-text('x')",
        "span:has-text('X')",
        "button:has-text('X')",
        "a:has-text('X')",
        "div:has-text('X')",
    ]
    for sel in close_sels:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(600)
                if log_fn:
                    log_fn("ℹ️  Dismissed popup.")
                return
        except Exception:
            continue


# ─────────────────────────────────────────────────────────────────
#  PDF capture helper
# ─────────────────────────────────────────────────────────────────


# async def _cdp_print_to_pdf(target_page: Page, pdf_path: Path) -> bool:
#     """
#     Use Chrome DevTools Protocol Page.printToPDF to save the transit pass popup
#     as a clean PDF matching the target output:
#       - Portrait A4
#       - Both Original + Duplicate on ONE page  (scale 0.75 = Chrome auto-fit)
#       - NO browser header / footer (no date, no URL, no page number)
#       - Minimal clean margins (8 mm)
#     """
#     cdp = await target_page.context.new_cdp_session(target_page)
#     try:
#         result = await cdp.send("Page.printToPDF", {
#             "printBackground":      True,
#             "landscape":            False,
#             "paperWidth":           8.27,     # A4 portrait (inches)
#             "paperHeight":          11.69,
#             "marginTop":            0.31,     # ≈ 8 mm
#             "marginBottom":         0.31,
#             "marginLeft":           0.31,
#             "marginRight":          0.31,

#             # Scale 0.75 → Chrome's auto-fit equivalent, fits Original +
#             # Duplicate on one A4 sheet identical to OS print-dialog output.
#             "scale":                0.75,

#             "preferCSSPageSize":    False,

#             # No browser chrome — matches the target screenshot exactly.
#             "displayHeaderFooter":  False,
#         })
#         pdf_bytes = base64.b64decode(result["data"])
#         if not pdf_bytes:
#             raise RuntimeError("CDP returned empty PDF data")
#         pdf_path.parent.mkdir(parents=True, exist_ok=True)
#         pdf_path.write_bytes(pdf_bytes)
#         return True
#     finally:
#         try:
#             await cdp.detach()
#         except Exception:
#             pass

async def _cdp_print_to_pdf(target_page: Page, pdf_path: Path) -> bool:
    """
    CDP Page.printToPDF — works in both headed and headless mode.
    Produces an A4 portrait PDF matching the target format:
      - Original + Duplicate copies both on ONE page (scale 0.75)
      - No browser header/footer (no URL, date, page numbers)
      - Clean 8mm margins
    """
    cdp = await target_page.context.new_cdp_session(target_page)
    try:
        result = await cdp.send("Page.printToPDF", {
            "printBackground":     True,
            "landscape":           False,
            "paperWidth":          8.27,    # A4 inches
            "paperHeight":         11.69,
            "marginTop":           0.31,    # ~8mm
            "marginBottom":        0.31,
            "marginLeft":          0.31,
            "marginRight":         0.31,
            "scale":               0.75,    # fits Original + Duplicate on 1 page
            "preferCSSPageSize":   False,
            "displayHeaderFooter": False,   # no URL / date / page numbers
        })
        pdf_bytes = base64.b64decode(result["data"])
        if not pdf_bytes:
            raise RuntimeError("CDP returned empty PDF")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        return True
    finally:
        try:
            await cdp.detach()
        except Exception:
            pass


# async def _clean_popup_for_pdf(target_page: Page) -> None:
#     """
#     Hide portal UI chrome that renders on EVERY page (fixed/sticky positioned
#     elements like the 'Transit Pass Print' header bar and 'My Balance' widget).

#     NOTE: The PRINT button, guidelines text, HELP DESK footer, and page-setup
#     screenshot are on PAGE 2 of the document. They are excluded automatically
#     by pageRanges='1' in _cdp_print_to_pdf — no DOM manipulation needed.
#     """
#     # Part 1: CSS to hide fixed/sticky overlays that appear on every page
#     try:
#         await target_page.add_style_tag(content="""
#             /* Fixed/sticky overlays (Transit Pass Print bar, My Balance widget) */
#             *[style*='position:fixed'],
#             *[style*='position: fixed'],
#             *[style*='position:sticky'],
#             *[style*='position: sticky'] {
#                 display: none !important;
#                 visibility: hidden !important;
#             }
#             /* Page-break suppression so both passes stay on page 1 */
#             * {
#                 page-break-before: avoid !important;
#                 page-break-after:  avoid !important;
#                 page-break-inside: avoid !important;
#                 break-before:      avoid !important;
#                 break-after:       avoid !important;
#                 break-inside:      avoid !important;
#             }
#             @page { margin: 8mm; size: A4 portrait; }
#         """)
#     except Exception:
#         pass

#     # Part 2: JS to hide elements with position:fixed/sticky set via CSS class
#     # (CSS attribute selectors only catch inline style="position:fixed")
#     try:
#         await target_page.evaluate("""
#             () => {
#                 const hideEl = el => {
#                     el.style.setProperty('display',    'none',   'important');
#                     el.style.setProperty('visibility', 'hidden', 'important');
#                 };

#                 // Fixed / sticky elements (nav bar, balance widget)
#                 document.querySelectorAll('*').forEach(el => {
#                     if (el.closest('table')) return;
#                     const pos = window.getComputedStyle(el).position;
#                     if (pos === 'fixed' || pos === 'sticky') hideEl(el);
#                 });

#                 // Exact-text match for known portal UI labels
#                 const UI_LABELS = ['transit pass print', 'my balance'];
#                 document.querySelectorAll('div,span,nav,header,aside,section').forEach(el => {
#                     if (el.closest('table')) return;
#                     const ownTxt = Array.from(el.childNodes)
#                         .filter(n => n.nodeType === 3)
#                         .map(n => n.textContent.trim().toLowerCase())
#                         .join(' ');
#                     if (UI_LABELS.some(kw => ownTxt.includes(kw))) hideEl(el);
#                 });
#             }
#         """)
#     except Exception:
#         pass

# async def _clean_popup_for_pdf(target_page: Page, log_fn=None) -> None:
#     """
#     FINAL FIX:
#     Keep ONLY transit pass tables (Original + Duplicate) and signatures.
#     Remove EVERYTHING else (header, footer, print button, printer guidelines).
#     Iterates through all frames (top-level + nested iframes) to handle nested documents.
#     Runs the cleanup continually every 100ms using setInterval to guarantee late-loaded elements are instantly neutralized.
#     Uses leaf-node unconditional targeting to bypass layout wrapper table protection.
#     """
#     for frame in target_page.frames:
#         try:
#             await frame.evaluate("""
#                 () => {
#                     const runCleanup = () => {
#                         const hideEl = el => {
#                             try {
#                                 if (!el) return;
#                                 el.style.setProperty('display', 'none', 'important');
#                                 el.style.setProperty('visibility', 'hidden', 'important');
#                                 el.style.setProperty('height', '0', 'important');
#                                 el.style.setProperty('padding', '0', 'important');
#                                 el.style.setProperty('margin', '0', 'important');
#                             } catch(e) {}
#                         };

#                         // 1. Find the actual clean transit pass tables (must contain permit text and NO nested target tables)
#                         let tables = [];
#                         try {
#                             tables = Array.from(document.querySelectorAll('table')).filter(t => {
#                                 let txt = "";
#                                 try { txt = (t.textContent || "").toLowerCase(); } catch(e) {}
#                                 const hasPermit = txt.includes('permit no') || txt.includes('consignor') || txt.includes('stationery');
#                                 if (!hasPermit) return false;

#                                 // Check if there is a nested inner table that ALSO contains permit text (indicates this is a layout table)
#                                 const innerTables = Array.from(t.querySelectorAll('table'));
#                                 const hasTargetInnerTable = innerTables.some(sub => {
#                                     let subTxt = "";
#                                     try { subTxt = (sub.textContent || "").toLowerCase(); } catch(e) {}
#                                     return subTxt.includes('permit no') || subTxt.includes('consignor') || subTxt.includes('stationery');
#                                 });
#                                 return !hasTargetInnerTable;
#                             });
#                         } catch(e) {}

#                         // 2. Hide any other tables on the page (layout/junk tables) — protecting signature tables
#                         try {
#                             document.querySelectorAll('table').forEach(t => {
#                                 let tTxt = "";
#                                 try { tTxt = (t.textContent || "").toLowerCase(); } catch(e) {}
#                                 const isSignatureTable = tTxt.includes('signature of') || tTxt.includes('assistant director');
#                                 if (!tables.includes(t) && !isSignatureTable) {
#                                     hideEl(t);
#                                 }
#                             });
#                         } catch(e) {}

#                         // 3. Walk siblings of valid tables and hide them
#                         try {
#                             if (tables.length > 0) {
#                                 const firstTable = tables[0];
#                                 const lastTable = tables[tables.length - 1];

#                                 // Walk up from first table and hide all previous sibling subtrees (header bar, overlays)
#                                 let curr = firstTable;
#                                 coupLoop1: while (curr && curr !== document.body) {
#                                     let prev = curr.previousElementSibling;
#                                     while (prev) {
#                                         const hasValidTable = Array.from(prev.querySelectorAll('table')).some(t => tables.includes(t));
#                                         if (!hasValidTable && prev !== firstTable) {
#                                             hideEl(prev);
#                                         }
#                                         prev = prev.previousElementSibling;
#                                     }
#                                     curr = curr.parentElement;
#                                 }

#                                 // Walk up from last table and hide all following sibling subtrees (PRINT btn, setup guidelines, help desk footer) — protecting signature block
#                                 curr = lastTable;
#                                 coupLoop2: while (curr && curr !== document.body) {
#                                     let next = curr.nextElementSibling;
#                                     while (next) {
#                                         const hasValidTable = Array.from(next.querySelectorAll('table')).some(t => tables.includes(t));
                                        
#                                         // Protect signature block!
#                                         let nextTxt = "";
#                                         try { nextTxt = (next.textContent || "").toLowerCase(); } catch(e) {}
#                                         const isSig = nextTxt.includes('signature of') || nextTxt.includes('assistant director') || nextTxt.includes('signature of mdl');

#                                         if (!hasValidTable && next !== lastTable && !isSig) {
#                                             hideEl(next);
#                                         }
#                                         next = next.nextElementSibling;
#                                     }
#                                     curr = curr.parentElement;
#                                 }
#                             }
#                         } catch(e) {}

#                         // 4. Hide all print button variants based on attributes, classes, and values unconditionally
#                         try {
#                             document.querySelectorAll('input, button, a, img, div, span').forEach(el => {
#                                 let isPrint = false;
                                
#                                 // Check attributes (id, class, name, src, alt, onclick, value) for 'print' keyword
#                                 ['id', 'class', 'name', 'src', 'alt', 'onclick', 'value'].forEach(attr => {
#                                     if (el.hasAttribute(attr)) {
#                                         const val = (el.getAttribute(attr) || "").toLowerCase();
#                                         if (val.includes('print') && !val.includes('fingerprint') && !val.includes('blueprint')) {
#                                             isPrint = true;
#                                         }
#                                     }
#                                 });

#                                 // Check inner text / text content
#                                 let txt = (el.textContent || el.innerText || "").trim().toLowerCase();
#                                 if (txt === 'print' || txt === 'print transit pass' || txt === 'print transit' || txt.includes('print_btn') || txt.includes('btnprint')) {
#                                     isPrint = true;
#                                 }

#                                 if (isPrint) {
#                                     hideEl(el);
#                                 }
#                             });
#                         } catch(e) {}

#                         // 5. Hide specific elements containing junk keywords unconditionally (leaf nodes only)
#                         try {
#                             const JUNK_KEYWORDS = [
#                                 'please follow', 'guidelines for print', 'printer setup',
#                                 'page setup', 'help desk', 'helpdesk', 'itcell-dmg',
#                                 'admg-rr-mines', 'dmgtg-it-mines', '8977522600', '9740135858',
#                                 '8639718177', 'transit pass print', 'my balance'
#                             ];

#                             document.querySelectorAll('*').forEach(el => {
#                                 let tag = "";
#                                 try { tag = el.tagName.toLowerCase(); } catch(e) {}
#                                 if (!tag || ['html', 'body', 'table', 'tbody', 'tr'].includes(tag)) return;

#                                 let txt = "";
#                                 try { txt = (el.textContent || "").toLowerCase(); } catch(e) {}

#                                 if (JUNK_KEYWORDS.some(kw => txt.includes(kw))) {
#                                     // Target deepest containers / leaf nodes containing these words to prevent hiding large container divs
#                                     const children = Array.from(el.children);
#                                     const childMatches = children.some(child => {
#                                         let childTxt = "";
#                                         try { childTxt = (child.textContent || "").toLowerCase(); } catch(e) {}
#                                         return JUNK_KEYWORDS.some(kw => childTxt.includes(kw));
#                                     });
#                                     if (!childMatches) {
#                                         hideEl(el);
#                                     }
#                                 }
#                             });
#                         } catch(e) {}
#                     };

#                     // Run immediately
#                     runCleanup();

#                     // Run continually in background every 100ms to instantly neutralize late-loaded elements
#                     const intervalId = setInterval(runCleanup, 100);

#                     // Stop the interval after 15 seconds to free up memory
#                     setTimeout(() => clearInterval(intervalId), 15000);
#                 }
#             """)
#         except Exception as e:
#             if log_fn:
#                 log_fn(f"⚠️  DOM cleanup script failed in frame {frame.url}: {e}")

#         # ✅ Prevent page breaks + clean layout in this frame
#         try:
#             await frame.add_style_tag(content="""
#                 * {
#                     page-break-before: avoid !important;
#                     page-break-after:  avoid !important;
#                     page-break-inside: avoid !important;
#                     break-before:      avoid !important;
#                     break-after:       avoid !important;
#                     break-inside:      avoid !important;
#                 }

#                 @page {
#                     size: A4 portrait;
#                     margin: 8mm;
#                 }

#                 body {
#                     margin: 0 !important;
#                     padding: 0 !important;
#                     background: #ffffff !important;
#                 }
#             """)
#         except Exception:
#             pass
async def _clean_popup_for_pdf(target_page: Page, log_fn=None) -> None:
    """
    FINAL CLEAN VERSION

    Removes:
    - PRINT button
    - "Please follow guidelines"
    - "Transit Pass Print"
    - "My Balance"
    - Helpdesk footer (phones, emails)

    Keeps:
    - Transit pass tables
    - Signature section
    """

    for frame in target_page.frames:
        try:
            await frame.evaluate("""
                () => {

                    const hideEl = (el) => {
                        try {
                            el.style.setProperty('display', 'none', 'important');
                            el.style.setProperty('visibility', 'hidden', 'important');
                            el.style.setProperty('height', '0', 'important');
                            el.style.setProperty('margin', '0', 'important');
                            el.style.setProperty('padding', '0', 'important');
                        } catch(e) {}
                    };

                    // =====================================================
                    // ✅ STEP 1: Identify VALID transit pass tables
                    // =====================================================
                    let validTables = Array.from(document.querySelectorAll('table')).filter(t => {
                        let txt = (t.textContent || "").toLowerCase();
                        return (
                            txt.includes('permit no') ||
                            txt.includes('consignor') ||
                            txt.includes('stationery')
                        );
                    });

                    // =====================================================
                    // ✅ STEP 2: Hide all other tables (except signatures)
                    // =====================================================
                    document.querySelectorAll('table').forEach(t => {
                        let txt = (t.textContent || "").toLowerCase();

                        const isSignature =
                            txt.includes('signature of') ||
                            txt.includes('assistant director');

                        if (!validTables.includes(t) && !isSignature) {
                            hideEl(t);
                        }
                    });

                    // =====================================================
                    // 🔥 STEP 3: REMOVE PRINT BUTTON (ALL TYPES)
                    // =====================================================
                    document.querySelectorAll('input, button, a').forEach(el => {
                        let txt = (el.textContent || el.value || "").toLowerCase();

                        if (
                            txt.includes('print') &&
                            !txt.includes('fingerprint') &&
                            !txt.includes('blueprint')
                        ) {
                            el.remove(); // HARD REMOVE
                        }
                    });

                    // =====================================================
                    // 🔥 STEP 4: REMOVE TEXT BLOCKS (MAIN FIX)
                    // =====================================================
                    document.querySelectorAll('*').forEach(el => {
                        let txt = (el.textContent || "").toLowerCase();

                        const isJunk =
                            txt.includes('please follow the guidelines') ||
                            txt.includes('printer setup') ||
                            txt.includes('transit pass print') ||
                            txt.includes('my balance') ||
                            txt.includes('help desk') ||
                            txt.includes('telangana.gov.in') ||
                            txt.includes('dmgtg-it-mines') ||
                            txt.includes('admg-rr-mines') ||
                            txt.includes('8977522600') ||
                            txt.includes('9740135858') ||
                            txt.includes('8639718177');

                        // ✅ remove only leaf nodes (safe)
                        if (isJunk && el.children.length === 0) {
                            el.remove();
                        }
                    });

                    // =====================================================
                    // 🔥 STEP 5: REMOVE EMPTY CONTAINERS (cleanup)
                    // =====================================================
                    document.querySelectorAll('div, span, p').forEach(el => {
                        if (el.innerText.trim() === "") {
                            el.remove();
                        }
                    });

                }
            """)

        except Exception as e:
            if log_fn:
                log_fn(f"⚠️ Cleanup failed in frame: {e}")

        # =====================================================
        # ✅ FINAL STYLE FIX (important for clean PDF)
        # =====================================================
        try:
            await frame.add_style_tag(content="""
                * {
                    page-break-before: avoid !important;
                    page-break-after:  avoid !important;
                    page-break-inside: avoid !important;
                }

                @page {
                    size: A4 portrait;
                    margin: 8mm;
                }

                body {
                    margin: 0 !important;
                    padding: 0 !important;
                    background: white !important;
                }
            """)
        except Exception:
            pass

# async def capture_pdf_from_print(
#     page: Page,
#     context: BrowserContext,
#     print_btn_selectors: list[str],
#     pdf_path: Path,
#     log_fn,
# ) -> bool:
#     """
#     PDF-save flow (dialog-free)
#     ───────────────────────────
#     1. Click "PRINT TRANSIT PASS" on the main form → transit pass popup opens.
#     2. Wait for the popup page to fully load (networkidle + settle).
#        window.print() is already suppressed via context-level init script,
#        so no OS dialog can appear regardless of what the page JS does.
#     3. Clean the popup (hide PRINT button, guidelines, page-break rules).
#     4. Use CDP Page.printToPDF to save directly to pdf_path — no dialogs.
#     5. Close popup.
    
#     NOTE: We intentionally do NOT click the in-page PRINT button.
#     The page is fully rendered after networkidle; clicking PRINT only
#     triggers window.print() which we suppress anyway, so it adds no value
#     and risks a timing race that could expose the OS dialog.
#     """
#     pdf_path.parent.mkdir(parents=True, exist_ok=True)

#     # ── Step 1: find "PRINT TRANSIT PASS" button on the main form ────────────
#     print_sel = await try_selectors(page, print_btn_selectors, timeout=8000)
#     if not print_sel:
#         log_fn("⚠️  'Print Transit Pass' button not found.")
#         return False

#     log_fn(f"🖨️  'Print Transit Pass' found [{print_sel}] — clicking…")

#     popup: Optional[Page] = None
#     try:
#         # ── Step 2: click → expect popup ─────────────────────────────────────────
#         try:
#             async with context.expect_page(timeout=14_000) as new_page_info:
#                 await page.click(print_sel)
#             popup = await new_page_info.value
#             log_fn("📄 Transit pass popup opened.")
#         except Exception as e:
#             log_fn(f"⚠️  No popup appeared after clicking Print Transit Pass: {e}")
#             # Fallback: try CDP on the current page (e.g. same-tab navigation)
#             log_fn("🔄 Attempting CDP on current page as fallback…")
#             try:
#                 await _cdp_print_to_pdf(page, pdf_path)
#                 log_fn(f"✅ PDF saved (current-page CDP fallback) → {pdf_path}")
#                 return True
#             except Exception as e2:
#                 log_fn(f"❌ Current-page CDP fallback failed: {e2}")
#                 return False

#         # ── Step 3: wait for popup to fully load ─────────────────────────────
#         log_fn("   ⏳ Waiting for transit pass content to load…")
#         try:
#             await popup.wait_for_load_state("networkidle", timeout=12_000)
#         except Exception:
#             try:
#                 await popup.wait_for_load_state("domcontentloaded", timeout=6_000)
#             except Exception:
#                 pass

#         # 🎯 Dynamic load polling: Wait up to 10s for the transit pass table to load inside any frame
#         log_fn("   ⏳ Polling frames for transit pass tables to appear…")
#         table_found = False
#         for polling_idx in range(20):  # 20 * 500ms = 10s
#             for frame in popup.frames:
#                 try:
#                     has_table = await frame.evaluate("""
#                         () => {
#                             const tables = Array.from(document.querySelectorAll('table'));
#                             return tables.some(t => {
#                                 const txt = (t.textContent || "").toLowerCase();
#                                 return txt.includes('permit no') || txt.includes('consignor') || txt.includes('stationery');
#                             });
#                         }
#                     """)
#                     if has_table:
#                         table_found = True
#                         break
#                 except Exception:
#                     pass
#             if table_found:
#                 break
#             await popup.wait_for_timeout(500)

#         if table_found:
#             log_fn("   🎯 Transit pass tables detected in DOM!")
#         else:
#             log_fn("   ⚠️  Transit pass tables not detected, cleaning up layout anyway…")

#         # Extra settle — barcodes, fonts, images
#         await popup.wait_for_timeout(1000)

#         # ── Step 4: belt-and-suspenders print suppression ─────────────────────
#         # The context init script already suppressed window.print() before any
#         # page JS ran. This re-applies it in case the page overwrote it.
#         try:
#             await popup.evaluate(
#                 "window.print = function() { window.__printSuppressed = true; };"
#                 "window.onbeforeprint = null; window.onafterprint = null;"
#             )
#         except Exception:
#             pass

#         # ── Step 5: Clean popup — hide PRINT btn, guidelines, fix page breaks ─
#         log_fn("   🧹 Cleaning popup (isolating transit pass range)…")
#         await _clean_popup_for_pdf(popup, log_fn)
#         await popup.wait_for_timeout(300)
        
#         # Apply cleanup twice to handle any dynamic ASP.NET DOM re-renderings
#         await _clean_popup_for_pdf(popup, log_fn)
#         await popup.wait_for_timeout(300)

#         # ── Step 6: CDP Page.printToPDF → save directly — NO OS dialog ───────
#         log_fn(f"   💾 Saving PDF → {pdf_path.name}")
#         try:
#             await _cdp_print_to_pdf(popup, pdf_path)
#             log_fn(f"✅ PDF saved → {pdf_path}")
#             await popup.close()
#             return True
#         except Exception as cdp_err:
#             log_fn(f"⚠️  CDP PDF save failed: {cdp_err}")

#         # ── Fallback: page.pdf() ──────────────────────────────────────────────
#         try:
#             await popup.pdf(
#                 path=str(pdf_path), format="A4", print_background=True,
#                 margin={"top": "8mm", "bottom": "8mm",
#                         "left": "8mm",  "right": "8mm"},
#             )
#             log_fn(f"✅ PDF saved (page.pdf fallback) → {pdf_path}")
#             await popup.close()
#             return True
#         except Exception as pdf_err:
#             log_fn(f"⚠️  page.pdf() fallback failed: {pdf_err}")

#         # ── Last resort: full-page screenshot ────────────────────────────────
#         try:
#             png = pdf_path.with_suffix(".png")
#             await popup.screenshot(path=str(png), full_page=True)
#             log_fn(f"📸 Saved PNG (all PDF methods failed) → {png}")
#         except Exception as ss_err:
#             log_fn(f"⚠️  Screenshot also failed: {ss_err}")

#         await popup.close()
#         return False

#     except Exception as err:
#         log_fn(f"❌ Unexpected error during PDF capture: {err}")
#         try:
#             await popup.close()
#         except Exception:
#             pass
#         return False

async def _handle_os_print_dialog(pdf_path: Path, log_fn) -> bool:
    """
    After window.print() opens Chrome's print dialog, automate:
      1. Wait for Chrome's print preview to load and click 'Save'.
      2. Detect the OS Save As dialog using standard Win32 class '#32770'.
      3. Paste full path and finalize saving.
    """
    import asyncio, subprocess, time, ctypes

    def _clip(text: str):
        """Put text on Windows clipboard via pyperclip (fast) or PowerShell fallback."""
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception:
            safe = text.replace("'", "''")
            subprocess.run(
                ["powershell", "-command", f"Set-Clipboard -Value '{safe}'"],
                capture_output=True, timeout=5,
            )

    def get_foreground_window_info():
        """Returns the title, class name, and hwnd of the current active window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            title_len = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            title_buff = ctypes.create_unicode_buffer(title_len + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buff, title_len + 1)
            
            class_buff = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_buff, 256)
            return title_buff.value, class_buff.value, hwnd
        except Exception:
            return "", "", None

    def find_chrome_print_window():
        """Finds the visible Chrome window handle, prioritizing one with 'print' in its title."""
        hwnd_target = None
        
        def enum_windows_callback(hwnd, lParam):
            nonlocal hwnd_target
            class_name = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, class_name, 256)
            
            if class_name.value == "Chrome_WidgetWin_1":
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    title = ctypes.create_unicode_buffer(512)
                    ctypes.windll.user32.GetWindowTextW(hwnd, title, 512)
                    t_val = title.value.lower()
                    if "print" in t_val:
                        hwnd_target = hwnd
                        return False  # Stop enumeration
                    elif hwnd_target is None:
                        hwnd_target = hwnd
            return True  # Continue enumeration
            
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return hwnd_target

    def focus_chrome_window():
        """Forces the Chrome browser window to gain foreground focus, only if a Chrome window is not already active."""
        try:
            # Check current active window info
            title, class_name, active_hwnd = get_foreground_window_info()
            if class_name == "Chrome_WidgetWin_1":
                # Chrome is already in the foreground! Do not steal or shift focus.
                return
                
            hwnd = find_chrome_print_window()
            if hwnd:
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW = 5
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                # Alt tap key sequence to force Windows to allow SetForegroundWindow
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0) # Alt down
                ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0) # Alt up
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def focus_save_dialog(hwnd=None):
        """Forces the '#32770' Save As dialog window to gain foreground focus."""
        try:
            if not hwnd:
                hwnd = ctypes.windll.user32.FindWindowW("#32770", None)
            if hwnd:
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW = 5
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                # Alt tap key sequence
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    # Check if pyautogui is available
    pyautogui_available = False
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui_available = True
    except ImportError:
        pass

    # ctypes fallback helpers
    VK = {"ENTER": 0x0D, "CTRL": 0x11, "A": 0x41, "V": 0x56}
    UP = 0x0002
    def dn(k): ctypes.windll.user32.keybd_event(k, 0, 0,  0); time.sleep(0.05)
    def up(k): ctypes.windll.user32.keybd_event(k, 0, UP, 0); time.sleep(0.05)
    def key(*ks):
        for k in ks: dn(k)
        for k in reversed(ks): up(k)

    log_fn("   ⏳ Focus Chrome and wait for Save As dialog...")
    focus_chrome_window()
    await asyncio.sleep(0.5)
    
    # ── Wait/Detect Save As Dialog Loop ──────────────────────────────────────
    dialog_opened = False
    save_dialog_hwnd = None
    
    # Check for up to 10 seconds (20 checks of 0.5s)
    for attempt in range(1, 21):
        title, class_name, hwnd = get_foreground_window_info()
        
        # Windows standard dialog class is '#32770'
        # Or title contains 'Save' / 'Save As' / 'Save Print Output As'
        if class_name == "#32770" or "save" in title.lower():
            dialog_opened = True
            save_dialog_hwnd = hwnd
            log_fn(f"   ✓ Save As dialog detected: '{title}' ({class_name})")
            break
            
        # Try to trigger the Print Preview Save button by pressing Enter
        # Press Enter every second (attempts 3, 5, 7, 9, 11, 13, 15, 17, 19) to ensure focus-registration
        if attempt >= 3 and attempt % 2 == 1:
            log_fn(f"   🖨️ Sending Enter to Chrome print window (attempt {attempt})...")
            focus_chrome_window()
            await asyncio.sleep(0.15)
            if pyautogui_available:
                pyautogui.press("enter")
            else:
                key(VK["ENTER"])
                
        await asyncio.sleep(0.5)

    if not dialog_opened:
        log_fn("   ❌ Save As dialog did not open/focus after 10 seconds.")
        return False

    # Force focus the Save As dialog window
    focus_save_dialog(save_dialog_hwnd)
    await asyncio.sleep(0.5)

    # ── Set File Path & Save ────────────────────────────────────────────────
    log_fn("   ✍️ Writing file path to Save As dialog...")
    
    path_written = False
    if save_dialog_hwnd:
        try:
            # Locate the Edit child control inside the Save As dialog recursively
            hwnd_edit = None
            def enum_child_proc(hwnd_child, lParam):
                nonlocal hwnd_edit
                c_name = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd_child, c_name, 256)
                if c_name.value == "Edit":
                    hwnd_edit = hwnd_child
                    return False  # Stop enumeration
                return True
                
            WNDENUMPROC_CHILD = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            ctypes.windll.user32.EnumChildWindows(save_dialog_hwnd, WNDENUMPROC_CHILD(enum_child_proc), 0)
            
            if hwnd_edit:
                WM_SETTEXT = 0x000C
                ctypes.windll.user32.SendMessageW(hwnd_edit, WM_SETTEXT, 0, str(pdf_path))
                path_written = True
                log_fn("   ✓ Path set directly via Win32 SendMessage.")
        except Exception as ex:
            log_fn(f"   ⚠️ Direct Win32 path injection failed: {ex}")

    # Fallback to copy-paste if direct injection did not execute successfully
    if not path_written:
        log_fn("   🔄 Falling back to clipboard copy-paste sequence...")
        _clip(str(pdf_path))
        focus_save_dialog(save_dialog_hwnd)
        await asyncio.sleep(0.2)
        if pyautogui_available:
            pyautogui.hotkey("ctrl", "a")
            await asyncio.sleep(0.3)
            pyautogui.hotkey("ctrl", "v")
            await asyncio.sleep(0.4)
        else:
            key(VK["CTRL"], VK["A"])
            await asyncio.sleep(0.3)
            key(VK["CTRL"], VK["V"])
            await asyncio.sleep(0.4)

    # Press Enter to finalize saving the file
    focus_save_dialog(save_dialog_hwnd)
    await asyncio.sleep(0.1)
    if pyautogui_available:
        pyautogui.press("enter")
    else:
        key(VK["ENTER"])

    # ── Wait for dialog to close (confirms file is saved) ───────────────────
    log_fn("   ⏳ Finalizing save operations...")
    for _ in range(12):
        await asyncio.sleep(0.5)
        title, class_name, hwnd = get_foreground_window_info()
        if class_name != "#32770" and "save" not in title.lower():
            # Wait another 0.5s for final disk write to complete
            await asyncio.sleep(0.5)
            # Check if file exists on disk
            if pdf_path.exists():
                log_fn(f"   ✅ Saved successfully → {pdf_path.name}")
                return True
            else:
                log_fn("   ⚠️ Save As dialog closed, but file not found on disk yet...")

    if pdf_path.exists():
        log_fn(f"   ✅ File verified on disk → {pdf_path.name}")
        return True
        
    log_fn("   ❌ File save failed or was canceled.")
    return False


async def capture_pdf_from_print(
    page: Page,
    context: BrowserContext,
    print_btn_selectors: list[str],
    pdf_path: Path,
    log_fn,
) -> bool:
    """
    Fully automated PDF save using CDP Page.printToPDF — no OS dialogs needed.
      1. Click 'PRINT TRANSIT PASS' → transit pass page opens in a new tab
      2. Clean DOM to show only the PrintContent div
      3. Inject base tag to fix relative logo/image paths
      4. Re-render barcodes using local $Barcode library
      5. Use CDP Page.printToPDF to save directly to pdf_path
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Find & click "PRINT TRANSIT PASS" on the form ────────────────
    print_sel = await try_selectors(page, print_btn_selectors, timeout=8000)
    if not print_sel:
        log_fn("⚠️ 'Print Transit Pass' button not found")
        return False

    log_fn("🖨️ Opening Transit Pass page...")
    
    popup = None
    try:
        async with context.expect_page(timeout=25000) as new_page_info:
            submitted = await page.evaluate(f"""
                (sel) => {{
                    const form = document.forms[0];
                    if (!form) return false;
                    const btn = document.querySelector(sel);
                    if (!btn) return false;
                    
                    const origTarget = form.target;
                    form.target = '_blank';
                    
                    // Trigger client side validation if exists
                    if (typeof Page_ClientValidate === 'function') {{
                        if (!Page_ClientValidate()) {{
                            form.target = origTarget || '';
                            return false;
                        }}
                    }}
                    
                    // Create temporary input to carry the submit button's name & value
                    const tempInput = document.createElement('input');
                    tempInput.type = 'hidden';
                    tempInput.name = btn.name || btn.id || 'btnPrintTP';
                    tempInput.value = btn.value || 'Print Transit Pass';
                    tempInput.id = 'temp_print_trigger';
                    form.appendChild(tempInput);
                    
                    // Set __EVENTTARGET if applicable
                    const evTarget = form.elements['__EVENTTARGET'];
                    const origEvTarget = evTarget ? evTarget.value : '';
                    if (evTarget) {{
                        if (btn.name) {{
                            evTarget.value = btn.name;
                        }} else if (btn.id) {{
                            evTarget.value = btn.id.replace(/_/g, '$');
                        }}
                    }}
                    
                    form.submit();
                    
                    // Revert form target and clean up after submission
                    setTimeout(() => {{
                        form.target = origTarget || '';
                        const el = document.getElementById('temp_print_trigger');
                        if (el) el.remove();
                        if (evTarget) evTarget.value = origEvTarget;
                    }}, 1000);
                    
                    return true;
                }}
            """, print_sel)
            
            if not submitted:
                raise RuntimeError("JS evaluation could not submit form (missing form/button or validation failed).")
                
        popup = await new_page_info.value
        log_fn("📄 Transit pass opened in new tab.")
    except Exception as e:
        log_fn(f"❌ Failed to open transit pass in new tab: {e}")
        return False

    # ── Step 2: Wait for transit pass to fully render ─────────────────────────
    # Smart wait: poll for the PrintContent div or a permit table instead of blind waits
    try:
        await popup.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass
    # Poll up to 8s for transit pass content (permit table) to appear
    content_ready = False
    for _ in range(16):  # 16 × 500ms = 8s max
        try:
            found = await popup.evaluate("""
                () => {
                    const div = document.getElementById('PrintContent');
                    if (div && div.textContent.trim().length > 50) return true;
                    const tables = Array.from(document.querySelectorAll('table'));
                    return tables.some(t => (t.textContent || '').toLowerCase().includes('permit no'));
                }
            """)
            if found:
                content_ready = True
                break
        except Exception:
            pass
        await popup.wait_for_timeout(500)
    if not content_ready:
        await popup.wait_for_timeout(1000)  # brief grace if content never detected

    # ── Step 3: Inject DOM cleanup + base tag + barcode rendering ─────────────
    log_fn("🔧 Preparing transit pass for PDF generation...")
    for frame in popup.frames:
        try:
            await frame.evaluate("""
                () => {
                    // Get the transit pass content only
                    const printDiv = document.getElementById("PrintContent");
                    if (!printDiv) return;
                    const printContent = printDiv.innerHTML;

                    // Replace entire body with only the transit pass content
                    document.body.innerHTML =
                        '<div id="PrintContent" style="color:black;padding:20px;">'
                        + printContent +
                        '</div>';

                    // Inject <base> tag so relative paths (../Images/tslogo.png) resolve
                    // correctly to the live portal URL over HTTPS
                    let base = document.querySelector("base");
                    if (!base) {
                        base = document.createElement("base");
                        document.head.appendChild(base);
                    }
                    base.href = "https://mines.telangana.gov.in/EPermit/MDL/";

                    // Force background graphics to print
                    const style = document.createElement("style");
                    style.textContent =
                        "* { -webkit-print-color-adjust: exact !important;" +
                        "    print-color-adjust: exact !important; }" +
                        "body { background: white !important; margin: 0; padding: 0; }";
                    document.head.appendChild(style);

                    // Re-render barcodes using the portal's local $Barcode library
                    try {
                        if (typeof $Barcode !== "undefined") {
                            const passNoEl = document.getElementById(
                                "ContentPlaceHolder1_lbl_OPTP_TransitPassNo"
                            );
                            if (passNoEl) {
                                const passNo = passNoEl.innerText.trim();
                                $Barcode("#Topbarcode,#Bottombarcode").JsBarcode(passNo, {
                                    width: 1,
                                    height: 30,
                                    quite: 10,
                                    format: "CODE128",
                                    backgroundColor: "#fff",
                                    lineColor: "#000"
                                });
                            }
                        }
                    } catch (e) {
                        console.error("Barcode rendering error:", e);
                    }
                }
            """)
            break  # Only need to run on the main frame
        except Exception as e:
            log_fn(f"   ⚠️ DOM prep failed on frame: {e}")

    # Give browser time to fetch the logo and other assets over HTTPS
    await popup.wait_for_timeout(1000)
    log_fn("   ✓ Page prepared.")

    # ── Step 4: Generate PDF via CDP (no OS dialog, no keystrokes) ────────────
    log_fn(f"💾 Generating PDF → {pdf_path.name}")
    try:
        cdp_session = await context.new_cdp_session(popup)
        result = await cdp_session.send("Page.printToPDF", {
            "printBackground": True,
            "paperWidth": 8.27,    # A4 width in inches
            "paperHeight": 11.69,  # A4 height in inches
            "marginTop": 0.4,
            "marginBottom": 0.4,
            "marginLeft": 0.4,
            "marginRight": 0.4,
            "displayHeaderFooter": False,
            "landscape": False,
        })
        pdf_bytes = base64.b64decode(result["data"])
        pdf_path.write_bytes(pdf_bytes)
        log_fn(f"   ✅ PDF saved successfully → {pdf_path.name} ({len(pdf_bytes):,} bytes)")
        saved = True
    except Exception as e:
        log_fn(f"   ❌ CDP PDF generation failed: {e}")
        saved = False

    # ── Step 5: Clean up popup tab and return focus to main page ───────────────
    try:
        await popup.close()
    except Exception:
        pass
    # After closing the popup Chrome may focus a different tab.
    # Explicitly bring the caller's main page back to the front.
    try:
        await page.bring_to_front()
    except Exception:
        pass

    return saved



# ─────────────────────────────────────────────────────────────────
#  Automation Engine
# ─────────────────────────────────────────────────────────────────


class TransitPassAutomation:
    def __init__(
        self,
        log_fn:      Callable[[str], None],
        otp_fn:      Optional[Callable[[], str]] = None,
        progress_fn: Optional[Callable[[int, int], None]] = None,
        headless:    bool = config.HEADLESS,
    ):
        self.log        = log_fn
        self.otp_fn     = otp_fn
        self.progress   = progress_fn
        self.headless   = headless
        self.playwright = None
        self.browser:   Optional[Browser]        = None
        self.context:   Optional[BrowserContext] = None
        self.page:      Optional[Page]           = None
        self._stop      = False
        self.username   = ""

    def stop(self):
        self._stop = True

    # ── Lifecycle ─────────────────────────────────────────────

    async def start(self):
        self.log("🌐 Starting Playwright…")
        self.playwright = await async_playwright().start()

        # Ensure PDF output folder exists
        pdf_folder = Path(config.PDF_SAVE_FOLDER).resolve()
        pdf_folder.mkdir(parents=True, exist_ok=True)
        self.log(f"📁 PDF save folder: {pdf_folder}")

        # Pre-configure Chrome's Default Preferences to default to 'Save as PDF'
        # and print Page 1 only with 75% scaling.
        user_data_dir = Path("chrome_profile").resolve()
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        prefs_dir = user_data_dir / "Default"
        prefs_dir.mkdir(parents=True, exist_ok=True)
        prefs_file = prefs_dir / "Preferences"
        
        import json
        prefs = {}
        if prefs_file.exists():
            try:
                prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        # Build appState structure for print settings
        app_state = {
            "recentDestinations": [
                {
                    "id": "Save as PDF",
                    "origin": "local",
                    "account": ""
                }
            ],
            "selectedDestinationId": "Save as PDF",
            "version": 2,
            "isHeaderFooterEnabled": False,
            "isCssBackgroundEnabled": True,
            "scalingType": 3,      # Custom scaling
            "scaling": "75",       # 75%
            "pagesType": 2,        # Custom pages
            "pageRange": "1"       # Page 1 only
        }
        
        # Inject into preferences
        prefs["printing"] = prefs.get("printing", {})
        prefs["printing"]["print_preview_sticky_settings"] = {
            "appState": json.dumps(app_state)
        }
        
        try:
            prefs_file.write_text(json.dumps(prefs), encoding="utf-8")
        except Exception as e:
            self.log(f"⚠️ Could not write print preferences: {e}")

        # Launch using persistent context
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.headless,
            slow_mo=80,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--allow-running-insecure-content",
                "--disable-web-security",
                "--ignore-certificate-errors",
            ],
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
            accept_downloads=True,
        )

        # Smart handler for native browser dialogs (alert/confirm/print/beforeunload)
        async def handle_dialog(dialog):
            try:
                self.log(f"💬 Dialog appeared: [{dialog.type}] '{dialog.message}'")
                if dialog.type == "beforeunload":
                    await dialog.accept()
                    self.log("   ✓ Accepted beforeunload dialog.")
                else:
                    await dialog.dismiss()
                    self.log("   ✓ Dismissed dialog.")
            except Exception as e:
                self.log(f"⚠️ Dialog handling error: {e}")

        self.context.on("dialog", lambda dlg: asyncio.create_task(handle_dialog(dlg)))

        # Suppress native print dialog and block beforeunload event registration globally
        await self.context.add_init_script("""
            window.print = () => { console.log('window.print() suppressed'); };
            try {
                Object.defineProperty(window, 'onbeforeunload', {
                    get: () => null,
                    set: () => { console.log('onbeforeunload write ignored'); }
                });
                const originalAdd = window.addEventListener;
                window.addEventListener = function(type, listener, options) {
                    if (type === 'beforeunload') {
                        console.log('beforeunload listener registration blocked');
                        return;
                    }
                    return originalAdd.apply(this, arguments);
                };
            } catch (e) {
                console.error('Failed to suppress beforeunload:', e);
            }
        """)

        # Grab the default page created by persistent context
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()
            
        self.log("✅ Browser launched with pre-configured print profile!")


    async def close(self):
        try:
            if self.context:    await self.context.close()
            if self.browser:    await self.browser.close()
            if self.playwright: await self.playwright.stop()
        except Exception:
            pass
        self.log("🔒 Browser closed.")

    # ── Login ─────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> bool:
        self.username = username
        self.password = password
        try:
            self.log(f"🔐 Opening login page: {config.LOGIN_URL}")
            await self.page.goto(config.LOGIN_URL, wait_until="domcontentloaded",
                                 timeout=config.PAGE_LOAD_TIMEOUT)
            await self.page.wait_for_timeout(500)

            # Fill username
            self.log("📝 Looking for username field…")
            try:
                await self.page.wait_for_selector(config.SEL_USERNAME, timeout=config.ELEMENT_TIMEOUT)
                await self.page.fill(config.SEL_USERNAME, username)
            except Exception as e:
                self.log(f"❌ Username field not found: {e}")
                return False

            # Fill password
            self.log("📝 Filling password…")
            await self.page.fill(config.SEL_PASSWORD, password)
            await self.page.wait_for_timeout(100)

            # Click LOGIN → triggers OTP SMS
            self.log(f"🖱️  Clicking LOGIN button…")
            await self.page.click(config.SEL_LOGIN_BTN)
            self.log("⏳ Waiting for OTP to be sent to your mobile…")
            await self.page.wait_for_timeout(1000)

            ss = await take_screenshot(self.page, "after_login_click")
            self.log(f"📸 Screenshot → {ss}")

            # Detect OTP input field
            otp_sel = await try_selectors(self.page, config.OTP_INPUT_SELECTORS, timeout=12_000)
            if otp_sel:
                self.log(f"📲 OTP field detected [{otp_sel}]. Check your mobile for OTP…")
                self.log("__OTP_REQUESTED__")
            else:
                if await self._is_logged_in():
                    self.log("✅ Logged in (no OTP required).")
                    return True
                self.log("⚠️  OTP field not found — signalling prompt anyway…")
                self.log("__OTP_REQUESTED__")

            # Wait for OTP from user
            otp = self.otp_fn() if self.otp_fn else None
            if not otp:
                self.log("❌ No OTP provided. Login aborted.")
                return False

            self.log("🔢 Entering OTP…")
            if otp_sel:
                await self.page.fill(otp_sel, otp.strip())
                await self.page.wait_for_timeout(500)

            # Submit OTP — #btnGetOtp is the same button reused for OTP submit
            submitted = await safe_click(self.page, config.OTP_SUBMIT_SELECTORS)
            if not submitted:
                self.log("⚠️  OTP submit button not found — pressing Enter…")
                await self.page.keyboard.press("Enter")

            # Smart wait — poll for URL change instead of blind 3s sleep
            try:
                await self.page.wait_for_url(
                    lambda url: "Login" not in url or "OTP" not in url,
                    timeout=8000,
                )
            except Exception:
                await self.page.wait_for_timeout(1000)
            await take_screenshot(self.page, "after_otp_submit")

            if await self._is_logged_in():
                self.log("✅ Login successful!")
                await dismiss_popup(self.page, self.log)
                return True
            else:
                self.log("❌ Login failed — check OTP or credentials.")
                return False

        except Exception as e:
            self.log(f"❌ Login error: {e}")
            await take_screenshot(self.page, "login_error")
            return False

    async def _is_logged_in(self) -> bool:
        try:
            await self.page.wait_for_url(
                lambda url: "Login" not in url and "login" not in url,
                timeout=8000,
            )
            return True
        except Exception:
            url = self.page.url
            return "Login" not in url and "login" not in url

    async def _check_and_recover_session(self) -> bool:
        """Checks if session has expired (URL redirect to login page) and re-logs in."""
        current_url = self.page.url.lower()

        # Only trigger if the browser was REDIRECTED to the login page
        # (do NOT check page body text — dashboard pages can contain 'Error' text in hidden elements)
        is_login_page = "login.aspx" in current_url

        # As a secondary check: detect the specific ASP.NET crash page
        # It is identified by having BOTH an error heading AND a 'Click here to Login' link
        is_crash_page = False
        if not is_login_page:
            try:
                is_crash_page = await self.page.evaluate("""
                    () => {
                        const hasLoginLink = !!document.querySelector('a[href*="Login"]');
                        const txt = document.body.textContent || '';
                        const hasErrorHeading = txt.includes('Error Occured') && txt.includes('Click here to Login');
                        return hasLoginLink && hasErrorHeading;
                    }
                """)
            except Exception:
                pass

        if is_login_page or is_crash_page:
            reason = "redirected to Login page" if is_login_page else "ASP.NET error/crash page"
            self.log(f"⚠️  Session issue detected ({reason}) — attempting automatic re-login…")
            if hasattr(self, "username") and hasattr(self, "password") and self.username and self.password:
                ok = await self.login(self.username, self.password)
                if ok:
                    self.log("✅ Automatic re-login succeeded.")
                    return True
                else:
                    raise RuntimeError("❌ Automatic re-login failed. Please restart the app.")
            else:
                raise RuntimeError("❌ Session expired and credentials not available for re-login.")
        return False

    # ── Navigation: E-Trans → Approved Permits ────────────────

    async def _nav_to_approved_permits(self):
        self.log("🗺️  Navigating to Approved Permits page...")

        # Guard: Check session health before starting navigation
        await self._check_and_recover_session()

        current_url = self.page.url

        # ── If already on the Approved Permits grid page (with New button), skip navigation ──
        if "MDLApprovedPermitsNew" in current_url:
            new_btn = await try_selectors(self.page, config.TP_NEW_BTN, timeout=1000)
            if new_btn:
                self.log("   ✓ Already on Approved Permits grid page — skipping navigation.")
                return
            self.log("   🔄 On form page — will navigate via menu to return to grid.")

        # ── Navigate to MDL dashboard if not already there ──
        if "mdldashboard" in current_url.lower():
            self.log("   ✓ Already on MDL dashboard page — skipping URL navigation.")
        else:
            self.log("   🏠 Returning to MDL dashboard to cleanly reset page state...")
            home_selectors = [
                "a:has-text('Home')",
                "a[href*='Dashboard']",
                "a[href*='MDLDashboard']",
                "#lnkHome"
            ]
            clicked_home = await safe_click(self.page, home_selectors, timeout=3000)
            if clicked_home:
                try:
                    await self.page.wait_for_url("**/MDLDashboard.aspx", timeout=5000)
                    self.log("   ✓ Returned to dashboard via Home click.")
                except Exception:
                    self.log("   ⚠️ Home click navigation timed out — trying direct navigation.")
                    clicked_home = False
            
            if not clicked_home:
                home_url = f"{config.BASE_URL}/EPermit/MDL/MDLDashboard.aspx"
                self.log(f"   🏠 Navigating directly to MDL dashboard: {home_url}")
                try:
                    await self.page.goto(home_url, wait_until="domcontentloaded", timeout=12000)
                    await self.page.wait_for_timeout(300)
                except Exception as e:
                    self.log(f"   ⚠️ Dashboard navigation failed: {e}")

        # Dismiss any popup/modal that may have loaded after home navigation (e.g. announcements)
        await dismiss_popup(self.page, self.log)
        await self.page.wait_for_timeout(100)

        # Step 1: Click the E-Trans top-menu item
        clicked = await safe_click(self.page, config.NAV_ETRANS_MENU, timeout=8000)
        if not clicked:
            # Fallback: use JavaScript to find and click the nav link by text content
            self.log("   ⚠️  Normal click failed — trying JS force-click on E-Trans nav link…")
            try:
                js_clicked = await self.page.evaluate("""
                    () => {
                        const keywords = ['e-trans', 'etrans', 'e-transmit', 'etransmit', 'transit'];
                        const links = Array.from(document.querySelectorAll('a, li > a, nav a'));
                        for (const link of links) {
                            const txt = (link.textContent || '').trim().toLowerCase();
                            if (keywords.some(kw => txt.includes(kw))) {
                                link.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if js_clicked:
                    self.log("   ✓ JS force-click on E-Trans menu succeeded.")
                    clicked = True
                    await self.page.wait_for_timeout(1000)
            except Exception as js_err:
                self.log(f"   ⚠️  JS force-click failed: {js_err}")

        if not clicked:
            self.log("   ⚠️  E-Trans menu not found — checking session health…")
            recovered = await self._check_and_recover_session()
            if recovered:
                self.log("   🔄 Session recovered (re-login succeeded) — restarting navigation to Approved Permits...")
                return await self._nav_to_approved_permits()
            else:
                self.log("   ❌ E-Trans menu not found and session recovery was not triggered.")
                await take_screenshot(self.page, "etrans_not_found_error")
                raise RuntimeError("E-Trans menu not found — portal may have changed its layout.")

        await self.page.wait_for_timeout(200)

        # Step 2: Click Permits sub-menu
        await safe_click(self.page, config.NAV_PERMITS_SUBMENU, timeout=5000)
        await self.page.wait_for_timeout(200)

        # Step 3: Click Approved Permits
        await safe_click(self.page, config.NAV_APPROVED_PERMITS, timeout=5000)

        # Wait for the Approved Permits page to load
        try:
            await self.page.wait_for_url(
                lambda url: "MDLApprovedPermitsNew" in url or "ApprovedPermit" in url,
                timeout=10000,
            )
        except Exception:
            await self.page.wait_for_timeout(1500)

        final_url = self.page.url
        self.log(f"📍 Current URL: {final_url}")

        # ── Session / permission checks ────────────────────────────────────────
        if "Login.aspx" in final_url or "login.aspx" in final_url:
            raise RuntimeError(
                "❌ Session expired — redirected to Login page. "
                "Please restart and log in again."
            )
        if "ErrorPage.aspx" in final_url:
            raise RuntimeError(
                "❌ Unauthorized Access even via menu — the logged-in account may not "
                "have the required role/permissions for this module."
            )


    # ── Click "New" in Transit Passes column ──────────────────

    async def _click_new_tp(self):
        self.log("🖱️  Clicking 'New' in Transit Passes column…")

        # Guard: if we got redirected to Login, raise early with a clear message
        current_url = self.page.url
        if "Login.aspx" in current_url or "login.aspx" in current_url:
            raise RuntimeError(
                "❌ Session expired — page redirected to Login before clicking New. "
                "Please restart and log in again."
            )

        clicked = await safe_click(self.page, config.TP_NEW_BTN, timeout=8000)
        if not clicked:
            self.log("⚠️  'New' button not found — logging table elements…")
            fields = await discover_fields(self.page)
            btns = [f for f in fields if f['tag'] in ('A', 'INPUT', 'BUTTON')][:20]
            self.log(f"   Buttons/Links: {btns}")
            raise RuntimeError("'New' Transit Pass button not found")
        # Smart wait — poll for MDL Type dropdown instead of blind 2s sleep
        await try_selectors(self.page, config.MDL_TYPE_DDL, timeout=3000)
        self.log(f"📍 Transit Pass page: {self.page.url}")

    # ── Step 1: MDL Selection ─────────────────────────────────

    async def _step1_mdl(self):
        self.log("📋 Step 1 — MDL Selection…")

        # ── 1b: Find the Type-of-MDL dropdown ────────────────
        type_ddl_sel = await try_selectors(self.page, config.MDL_TYPE_DDL, timeout=8000)
        if not type_ddl_sel:
            self.log("   ⚠️  'Type of MDL' dropdown not found — scanning page…")
            fields = await discover_fields(self.page)
            all_ddls = [f for f in fields if f['tag'] == 'SELECT']
            self.log(f"   Dropdowns on page: {[d['id'] for d in all_ddls]}")
            if all_ddls:
                type_ddl_sel = f"select#{all_ddls[0]['id']}" if all_ddls[0]['id'] else "select"
                self.log(f"   Auto-selected first dropdown: [{type_ddl_sel}]")
            else:
                self.log("   ❌ No SELECT elements found on page at all!")
                await take_screenshot(self.page, "step1_no_dropdowns")
                return

        # ── 1c: Select "MDL" and wait for dynamic form to load ─
        self.log(f"   Selecting '{config.MDL_TYPE_VALUE}' in [{type_ddl_sel}]…")

        # Inject a MutationObserver BEFORE selecting, to detect DOM changes
        await self.page.evaluate("""
            () => {
                window.__newElemsAdded = 0;
                const obs = new MutationObserver(muts => {
                    muts.forEach(m => { window.__newElemsAdded += m.addedNodes.length; });
                });
                obs.observe(document.body, { childList: true, subtree: true });
                window.__domObserver = obs;
            }
        """)

        # Try selecting by value "MDL", then by label "MDL"
        selected = False
        for method, kwarg in [("value", {"value": "MDL"}), ("label", {"label": "MDL"})]:
            try:
                await self.page.select_option(type_ddl_sel, **kwarg)
                selected = True
                self.log(f"   ✓ Selected 'MDL' by {method}.")
                break
            except Exception:
                continue

        if not selected:
            # Partial-match fallback: iterate <option> elements
            self.log("   Trying partial-match fallback for MDL type…")
            try:
                opts = await self.page.query_selector_all(f"{type_ddl_sel} option")
                for opt in opts:
                    txt = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value")
                    if "mdl" in txt.lower() and val:
                        await self.page.select_option(type_ddl_sel, value=val)
                        selected = True
                        self.log(f"   ✓ Selected option '{txt}' (value='{val}') by partial match.")
                        break
            except Exception as pe:
                self.log(f"   Partial-match failed: {pe}")

        if not selected:
            self.log("   ❌ Could not select MDL type — aborting step 1.")
            await take_screenshot(self.page, "step1_mdl_type_fail")
            return

        # ── 1d: Wait for the DYNAMIC FORM to load ─────────────
        # The page uses AJAX / ASP.NET UpdatePanel — wait for network + DOM changes
        self.log("   ⏳ Waiting for dynamic form to appear after MDL selection…")

        # Strategy A: Wait for ASP.NET AJAX PostBack to complete
        await wait_for_ajax(self.page, timeout=8000)

        # Check how many DOM nodes were added
        new_nodes = await self.page.evaluate("() => { try { window.__domObserver.disconnect(); } catch(e){} return window.__newElemsAdded || 0; }")
        self.log(f"   DOM nodes added after selection: {new_nodes}")

        # Strategy B: poll for the MDL ID dropdown up to 6 × 400 ms = ~2.4 s
        mdl_id_sel = None
        for attempt in range(6):
            mdl_id_sel = await try_selectors(self.page, config.MDL_ID_DDL, timeout=600)
            if mdl_id_sel:
                self.log(f"   ✓ MDL ID dropdown appeared [{mdl_id_sel}] after {attempt+1} poll(s).")
                break
            await self.page.wait_for_timeout(400)

        if not mdl_id_sel:
            # Log ALL selects visible now for diagnosis
            self.log("   ⚠️  MDL ID dropdown not found — scanning all dropdowns now visible…")
            fields2 = await discover_fields(self.page)
            ddls2 = [f for f in fields2 if f['tag'] == 'SELECT']
            self.log(f"   SELECT elements now: {[(d['id'], d['name'], d['value']) for d in ddls2]}")
            await take_screenshot(self.page, "step1_mdl_id_missing")

        # ── 1e: Select MDL ID from the dynamic dropdown ───────
        # Strategy 1 — exact username match
        # Strategy 2 — partial match (e.g. "M302024216-RANGAREDDY" contains "M302024216")
        # Strategy 3 — auto-select the FIRST non-Select option (fallback)
        ok = False
        mdl_id_sels = config.MDL_ID_DDL

        # Strategy 1: exact match on username
        ok = await safe_select(self.page, mdl_id_sels, self.username)
        if ok:
            self.log(f"   ✓ MDL ID selected by exact username match: '{self.username}'")

        # Strategy 2: partial match — username is prefix of option text
        if not ok and mdl_id_sel:
            self.log(f"   Trying partial-match for MDL ID (username = '{self.username}')…")
            try:
                opts = await self.page.query_selector_all(f"{mdl_id_sel} option")
                for opt in opts:
                    txt = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value") or ""
                    uname_prefix = self.username[:8]
                    if (self.username.lower() in txt.lower() or
                            self.username.lower() in val.lower() or
                            uname_prefix.lower() in txt.lower()):
                        if val and val.lower() not in ("--select--", "", "0"):
                            await self.page.select_option(mdl_id_sel, value=val)
                            ok = True
                            self.log(f"   ✓ MDL ID selected by partial match: '{txt}' (value='{val}')")
                            break
            except Exception as e2:
                self.log(f"   Partial-match error: {e2}")

        # Strategy 3: auto-select first non-Select option
        if not ok and mdl_id_sel:
            self.log("   Auto-selecting first available MDL ID option…")
            try:
                opts = await self.page.query_selector_all(f"{mdl_id_sel} option")
                for opt in opts:
                    txt = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value") or ""
                    if txt and val and txt.lower() not in ("--select--", "select") and val not in ("", "0"):
                        await self.page.select_option(mdl_id_sel, value=val)
                        ok = True
                        self.log(f"   ✓ MDL ID auto-selected first option: '{txt}' (value='{val}')")
                        break
                if not ok:
                    self.log("   ⚠️  All options in MDL ID dropdown appear to be --Select-- placeholders.")
            except Exception as e3:
                self.log(f"   Auto-select error: {e3}")

        if not ok:
            self.log(f"   ❌ Could not select MDL ID — will try GET DETAILS anyway.")
            await take_screenshot(self.page, "step1_mdl_id_select_fail")

        await wait_for_ajax(self.page, timeout=8000)

        # ── 1f: Click GET DETAILS ──────────────────────────────
        ok = await safe_click(self.page, config.MDL_GET_DETAILS_BTN, timeout=8000)
        self.log(f"   GET DETAILS button: {'✓ clicked' if ok else '⚠ not found'}")
        if not ok:
            fields3 = await discover_fields(self.page)
            btns = [f for f in fields3 if f['tag'] in ('INPUT', 'BUTTON')]
            self.log(f"   Buttons visible: {[(b['id'], b.get('value') or b.get('text','')) for b in btns[:12]]}")
            await take_screenshot(self.page, "step1_get_details_fail")

        # Wait for GET DETAILS response
        await wait_for_ajax(self.page, timeout=8000)
        agg_ready = await try_selectors(self.page, config.AGGREGATOR_DDL, timeout=4000)
        self.log("   ✅ Step 1 complete.")


    # ── Step 2: PERMIT INFO — Aggregator ────────────────────────────────

    async def _step2_aggregator(self, aggregator: str):
        self.log(f"📋 Step 2 — Aggregator selection…")

        # ── 2a: Wait for the Aggregator dropdown to appear (replaces slow networkidle+1500ms)
        agg_sel = None
        for attempt in range(12):  # up to ~6 s
            agg_sel = await try_selectors(self.page, config.AGGREGATOR_DDL, timeout=500)
            if agg_sel:
                break
            await self.page.wait_for_timeout(500)

        if not agg_sel:
            self.log("   ⚠️  Aggregators dropdown not found — trying auto-detect…")
            # Last-resort: scan all SELECTs, skip MDL-type ones
            fields = await discover_fields(self.page)
            non_mdl = [d for d in fields if d['tag'] == 'SELECT'
                       and 'TypeOfMDL' not in d['id'] and 'AllMDLs' not in d['id']]
            if non_mdl:
                agg_sel = f"select#{non_mdl[-1]['id']}" if non_mdl[-1]['id'] else None
                self.log(f"   Auto-detected aggregator dropdown: [{agg_sel}]")
            if not agg_sel:
                self.log("   ❌ Cannot find Aggregators dropdown — skipping Step 2.")
                return

        if not aggregator:
            self.log("   ⚠️  No aggregator in Excel — auto-selecting first option.")

        # ── 2b: Select aggregator — exact → partial → first-available
        ok = False

        if aggregator:
            for method, kwarg in [("value", {"value": aggregator}), ("label", {"label": aggregator})]:
                try:
                    await self.page.select_option(agg_sel, **kwarg)
                    ok = True
                    self.log(f"   ✓ Aggregator by {method}: '{aggregator}'")
                    break
                except Exception:
                    continue

            if not ok:
                try:
                    opts = await self.page.query_selector_all(f"{agg_sel} option")
                    for opt in opts:
                        txt = (await opt.inner_text()).strip()
                        val = await opt.get_attribute("value") or ""
                        if val.lower() in ("", "0") or txt.lower() in ("--select--", "select"):
                            continue
                        if (aggregator.lower() in txt.lower() or
                                txt.lower() in aggregator.lower() or
                                aggregator[:6].lower() in txt.lower()):
                            await self.page.select_option(agg_sel, value=val)
                            ok = True
                            self.log(f"   ✓ Aggregator partial match: '{txt}'")
                            break
                except Exception as e:
                    self.log(f"   Partial match error: {e}")

        if not ok:
            try:
                opts = await self.page.query_selector_all(f"{agg_sel} option")
                for opt in opts:
                    txt = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value") or ""
                    if txt and val and txt.lower() not in ("--select--", "select") and val not in ("", "0"):
                        await self.page.select_option(agg_sel, value=val)
                        ok = True
                        self.log(f"   ✓ Aggregator auto-selected: '{txt}'")
                        break
                if not ok:
                    self.log("   ⚠️  No valid options in Aggregators dropdown.")
            except Exception as e3:
                self.log(f"   Auto-select error: {e3}")

        if not ok:
            self.log("   ❌ Aggregator selection failed.")

        # ── 2c: Wait for CONSIGNEE INFO after aggregator postback
        await wait_for_ajax(self.page, timeout=8000)
        consignee_appeared = await try_selectors(
            self.page, config.DISPATCH_QTY_INPUT, timeout=6000
        )
        self.log("   ✅ Step 2 complete.")

    # ── Step 3: CONSIGNEE INFO ────────────────────────────────

    async def _step3_consignee(self, record: dict):
        self.log("📋 Step 3 — CONSIGNEE INFO form…")

        # ── 3a: Fields already waited on in Step 2 — just confirm qty field is ready
        qty_sel = await try_selectors(self.page, config.DISPATCH_QTY_INPUT, timeout=5000)
        if not qty_sel:
            # Brief wait if somehow not ready yet
            await self.page.wait_for_timeout(500)

        # ── 3b: Read values from Excel record
        qty     = str(record.get("dispatch_qty",  "")).strip()
        sales   = str(record.get("sales_value",   "")).strip()
        stat_no = str(record.get("stationary_no", "")).strip()
        self.log(f"   Qty='{qty}' | Sale='{sales}' | StatNo='{stat_no}'")

        # ── 3c: Fill fields — sequential (ASP.NET may react to each change)
        ok = await safe_fill(self.page, config.DISPATCH_QTY_INPUT, qty)
        self.log(f"   Dispatch Qty: {'✓' if ok else '⚠ not found'}")

        ok = await safe_fill(self.page, config.SALES_VALUE_INPUT, sales)
        self.log(f"   Sale Value: {'✓' if ok else '⚠ not found'}")

        ok = await safe_fill(self.page, config.STATIONARY_NO_INPUT, stat_no)
        self.log(f"   Stationary No: {'✓' if ok else '⚠ not found'}")

        # ── 3d: Click Next — then wait for Vehicle/Driver form to appear
        ok = await safe_click(self.page, config.CONSIGNEE_NEXT_BTN, timeout=8000)
        self.log(f"   Next button: {'✓ clicked' if ok else '⚠ not found — pressing Enter'}")
        if not ok:
            await self.page.keyboard.press("Enter")

        # Wait for Vehicle Type dropdown (confirms Step 4 form loaded)
        vehicle_appeared = await try_selectors(
            self.page, config.VEHICLE_TYPE_DDL, timeout=8000
        )
        if not vehicle_appeared:
            await self.page.wait_for_timeout(500)  # brief grace only
        self.log("   ✅ Step 3 complete.")

    # ── Step 4: Vehicle & Driver → Print ──────────────────────

    async def _step4_vehicle_driver(self, record: dict, label: str, pdf_path: Path) -> bool:
        self.log("📋 Step 4 — Vehicle & Driver Information…")
        fields = await discover_fields(self.page)
        field_ids = [f['id'] for f in fields if f['id']][:25]
        self.log(f"   Fields: {field_ids}")

        # Vehicle Type = Tipper
        ok = await safe_select(self.page, config.VEHICLE_TYPE_DDL, config.VEHICLE_TYPE_VALUE)
        self.log(f"   Vehicle Type='Tipper': {'✓' if ok else '⚠'}")
        
        # Wait for dynamic fields to update after vehicle type postback
        await wait_for_ajax(self.page, timeout=8000)
        await try_selectors(self.page, config.VEHICLE_NO_INPUT, timeout=4000)

        # Vehicle No
        ok = await safe_fill(self.page, config.VEHICLE_NO_INPUT, record.get("vehicle_no", ""))
        if not ok:
            ok = await safe_select(self.page, config.VEHICLE_NO_INPUT, record.get("vehicle_no", ""))
        self.log(f"   Vehicle No={record.get('vehicle_no')}: {'✓' if ok else '⚠'}")
        
        # Wait for vehicle lookup AJAX postback to complete
        await wait_for_ajax(self.page, timeout=5000)

        # Driver Name
        ok = await safe_fill(self.page, config.DRIVER_NAME_INPUT, record.get("driver", ""))
        self.log(f"   Driver Name={record.get('driver')}: {'✓' if ok else '⚠'}")

        # Driver License
        ok = await safe_fill(self.page, config.DRIVER_LICENSE_INPUT, record.get("license", ""))
        self.log(f"   License={record.get('license')}: {'✓' if ok else '⚠'}")

        # Driver Mobile
        ok = await safe_fill(self.page, config.DRIVER_MOBILE_INPUT, record.get("phone", ""))
        self.log(f"   Mobile={record.get('phone')}: {'✓' if ok else '⚠'}")

        await self.page.wait_for_timeout(200)
        await take_screenshot(self.page, f"before_print_{label.replace(' ', '_')}")

        # Click Print Transit Pass → capture PDF
        pdf_ok = await capture_pdf_from_print(
            self.page, self.context, config.PRINT_TP_BTN, pdf_path, self.log
        )
        return pdf_ok

    # ── Process one record ────────────────────────────────────

    async def process_record(self, record: dict) -> tuple[str, Optional[str]]:
        """
        Generate one Transit Pass. Returns ('success'|'failed'|'skipped', pdf_path|None).
        """
        row    = record.get("_row", "?")
        veh    = record.get("vehicle_no", "?") or "unknown"
        stat   = record.get("stationary_no", "") or ""
        label  = f"Row{row}_{veh}"

        # Build a descriptive, filesystem-safe filename:
        #   TP_<VehicleNo>_<StationeryNo>_<timestamp>.pdf
        def _safe(s: str) -> str:
            return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(s)).strip("_")

        ts         = int(time.time())
        pdf_folder = Path(config.PDF_SAVE_FOLDER).resolve()
        pdf_folder.mkdir(parents=True, exist_ok=True)
        fname      = f"TP_{_safe(veh)}{'_' + _safe(stat) if stat else ''}_{ts}.pdf"
        pdf_path   = pdf_folder / fname

        for attempt in range(1, config.MAX_RETRIES + 1):
            if self._stop:
                self.log("⏹️  Stopped by user.")
                return "skipped", None
            try:
                self.log(f"\n🚗 {label} — attempt {attempt}/{config.MAX_RETRIES}")

                # Close any stray tabs left from a previous print-preview
                await self._close_extra_tabs()

                # Dismiss any open popup first
                await dismiss_popup(self.page, self.log)

                # Navigate to Approved Permits
                await self._nav_to_approved_permits()

                # Click New Transit Pass
                await self._click_new_tp()

                # Step 1 — MDL
                await self._step1_mdl()

                # Step 2 — Aggregator
                await self._step2_aggregator(record.get("aggregator", ""))

                # Step 3 — Consignee
                await self._step3_consignee(record)

                # Step 4 — Vehicle/Driver + Print
                pdf_ok = await self._step4_vehicle_driver(record, label, pdf_path)

                if pdf_ok:
                    return "success", str(pdf_path)
                else:
                    self.log(f"⚠️  {label} — PDF not captured, retrying…")
                    await take_screenshot(self.page, f"warn_{row}_{attempt}")

            except Exception as e:
                self.log(f"❌ {label} — error attempt {attempt}: {e}")
                await take_screenshot(self.page, f"error_{row}_{attempt}")
                if attempt < config.MAX_RETRIES:
                    await asyncio.sleep(3)

        self.log(f"❌ {label} — FAILED after {config.MAX_RETRIES} attempts.")
        return "failed", None

    # ── Tab cleanup ───────────────────────────────────────────

    async def _close_extra_tabs(self):
        """
        Close any tabs that were opened as print-preview windows and were
        not closed properly (e.g. after a failed PDF capture). Keeps only
        self.page (the main portal tab).
        After closing strays, re-syncs self.page to the first surviving page
        and brings it to the front, so the next record always starts on the
        correct portal tab.
        """
        try:
            pages = self.context.pages
            for p in pages:
                if p is not self.page:
                    try:
                        await p.close()
                        self.log("🗂️  Closed a stray tab.")
                    except Exception:
                        pass
        except Exception:
            pass

        # Re-sync self.page — in case the original page object was somehow
        # replaced or the context pages list shifted after closures.
        try:
            remaining = self.context.pages
            if remaining:
                if not self.page or self.page not in remaining:
                    self.page = remaining[0]
                    self.log("🔄 Re-synced main page reference.")
                # Always bring the main page to the foreground
                await self.page.bring_to_front()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────
#  Public entry point
# ─────────────────────────────────────────────────────────────────

async def run_batch(
    records:     List[Dict],
    username:    str,
    password:    str,
    log_fn:      Callable[[str], None],
    otp_fn:      Optional[Callable[[], str]],
    progress_fn: Optional[Callable[[int, int], None]] = None,
    headless:    bool = False,
    pdf_folder:  Optional[str] = None,
) -> List[Dict]:
    """
    Login then generate one Transit Pass per record.
    Returns records list with '_status' and '_pdf' fields added.

    pdf_folder: override the default PDF save folder (config.PDF_SAVE_FOLDER).
    """
    # Override config if caller supplied a folder
    if pdf_folder:
        config.PDF_SAVE_FOLDER = pdf_folder

    engine = TransitPassAutomation(
        log_fn=log_fn,
        otp_fn=otp_fn,
        progress_fn=progress_fn,
        headless=headless,
    )
    try:
        await engine.start()

        # Login
        ok = await engine.login(username, password)
        if not ok:
            log_fn("❌ Login failed. All records marked as failed.")
            for r in records:
                r["_status"] = "❌ Login Failed"
                r["_pdf"]    = ""
            return records

        total = len(records)
        log_fn(f"📋 Processing {total} record(s) — PDFs → {Path(config.PDF_SAVE_FOLDER).resolve()}")

        for i, record in enumerate(records):
            if engine._stop:
                log_fn("⏹️  Automation stopped by user.")
                break

            log_fn(f"\n{'─'*55}")
            log_fn(f"🔄 Record {i+1}/{total}: Vehicle={record.get('vehicle_no','?')}  "
                   f"Stat={record.get('stationary_no','?')}")
            log_fn(f"{'─'*55}")

            result, pdf_path = await engine.process_record(record)

            record["_status"] = (
                "✅ Success" if result == "success" else
                "⏭️ Skipped" if result == "skipped" else
                "❌ Failed"
            )
            record["_pdf"] = pdf_path or ""

            if pdf_path:
                log_fn(f"__PDF__{pdf_path}")   # signal app.py to add download button

            # ── Live stat update signal ──────────────────────────────────────
            # app.py drains this to update the Total/Success/Failed/Pending
            # boxes in real-time after every record, without waiting for the
            # final __RESULTS__ dump at the end of the batch.
            log_fn(f"__RECORD_DONE__{result}")

            if progress_fn:
                progress_fn(i + 1, total)

            # Brief pause between records (not after the last one)
            if i < total - 1 and not engine._stop:
                log_fn(f"⏱️  Waiting {config.DELAY_BETWEEN_RECORDS}s before next record…")
                await asyncio.sleep(config.DELAY_BETWEEN_RECORDS)

        s = sum(1 for r in records if "✅" in r.get("_status", ""))
        f = sum(1 for r in records if "❌" in r.get("_status", ""))
        log_fn(f"\n{'═'*55}")
        log_fn(f"🎉 Batch complete!  ✅ {s} succeeded  ❌ {f} failed  (total {total})")
        log_fn(f"📁 PDFs saved to: {Path(config.PDF_SAVE_FOLDER).resolve()}")
        log_fn(f"{'═'*55}")

    except Exception as e:
        log_fn(f"💥 Fatal error: {e}\n{traceback.format_exc()}")
    finally:
        await engine.close()

    return records
