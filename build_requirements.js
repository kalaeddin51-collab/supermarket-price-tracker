const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  VerticalAlign, LevelFormat, PageNumber, Header, Footer,
  ExternalHyperlink
} = require('docx');
const fs = require('fs');

// ── Colours ──────────────────────────────────────────────────────────────────
const GREEN   = "1A6B3C";  // dark emerald
const LGREY   = "F2F4F6";  // light grey fill
const MGREY   = "D0D5DD";  // medium grey border
const BLACK   = "1A1A1A";
const WHITE   = "FFFFFF";
const AMBER   = "92400E";  // "to-do" text

// ── Helpers ───────────────────────────────────────────────────────────────────
function hBorder(color = MGREY, size = 4) {
  return { style: BorderStyle.SINGLE, size, color };
}
function noBorder() {
  return { style: BorderStyle.NIL, size: 0, color: WHITE };
}

function cell(text, opts = {}) {
  const {
    bold = false, fill = WHITE, color = BLACK, width = 4680,
    italic = false, size = 20, borderColor = MGREY, shade = ShadingType.CLEAR,
    colspan = 1
  } = opts;
  const b = hBorder(borderColor);
  return new TableCell({
    columnSpan: colspan,
    width: { size: width, type: WidthType.DXA },
    shading: { fill, type: shade },
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    borders: { top: b, bottom: b, left: b, right: b },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      children: [new TextRun({ text, bold, italic, color, size, font: "Arial" })]
    })]
  });
}

function headerCell(text, width = 4680) {
  return cell(text, { bold: true, fill: GREEN, color: WHITE, width, size: 20 });
}

function twoColRow(label, value, statusColor) {
  return new TableRow({ children: [
    cell(label, { bold: true, fill: LGREY, width: 3200, size: 20 }),
    cell(value, { color: statusColor || BLACK, width: 6160, size: 20 })
  ]});
}

function statusRow(feature, status, notes) {
  const statusColors = { "✅ Built": "166534", "🔧 Partial": "92400E", "📋 Planned": "1E3A5F" };
  const c = statusColors[status] || BLACK;
  return new TableRow({ children: [
    cell(feature, { width: 3200, size: 20 }),
    cell(status,  { bold: true, color: c, width: 1800, size: 20 }),
    cell(notes,   { italic: true, color: "555555", width: 4360, size: 20 }),
  ]});
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 120 },
    children: [new TextRun({ text, bold: true, size: 36, color: GREEN, font: "Arial" })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 80 },
    children: [new TextRun({ text, bold: true, size: 26, color: BLACK, font: "Arial" })]
  });
}

function h3(text) {
  return new Paragraph({
    spacing: { before: 200, after: 60 },
    children: [new TextRun({ text, bold: true, size: 22, color: GREEN, font: "Arial" })]
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text, size: 20, font: "Arial", color: BLACK, ...opts })]
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, size: 20, font: "Arial", color: BLACK })]
  });
}

function rule() {
  return new Paragraph({
    spacing: { before: 120, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: MGREY } },
    children: []
  });
}

function gap(lines = 1) {
  return new Paragraph({ spacing: { before: 0, after: lines * 120 }, children: [] });
}

// ── Table builders ────────────────────────────────────────────────────────────

function makeStoresTable() {
  const b = hBorder(MGREY);
  const borders = { top: b, bottom: b, left: b, right: b };
  function sc(t, fill = WHITE, bold = false, color = BLACK) {
    return new TableCell({
      width: { size: 2340, type: WidthType.DXA },
      shading: { fill, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 140, right: 140 },
      borders,
      children: [new Paragraph({ children: [new TextRun({ text: t, bold, size: 20, font: "Arial", color })] })]
    });
  }
  const rows = [
    new TableRow({ children: [
      headerCell("Store", 2340), headerCell("Coverage", 2340),
      headerCell("Scraper Status", 2340), headerCell("Notes", 2340)
    ]}),
    new TableRow({ children: [
      sc("Woolworths"),  sc("North Sydney / Online"),  sc("✅ Live", LGREY, true, "166534"),  sc("Full product API") ]}),
    new TableRow({ children: [
      sc("Coles"),       sc("North Sydney / Online"),  sc("✅ Live", LGREY, true, "166534"),  sc("Full product API") ]}),
    new TableRow({ children: [
      sc("Harris Farm"), sc("Cammeray, Crows Nest"),   sc("🔧 Stub", LGREY, true, AMBER),    sc("Scraper to be built") ]}),
    new TableRow({ children: [
      sc("IGA Crows Nest"),      sc("Crows Nest"),     sc("🔧 Stub", LGREY, true, AMBER),    sc("Scraper to be built") ]}),
    new TableRow({ children: [
      sc("IGA Milsons Point"),   sc("Milsons Point"),  sc("🔧 Stub", LGREY, true, AMBER),    sc("Scraper to be built") ]}),
    new TableRow({ children: [
      sc("IGA North Sydney"),    sc("North Sydney"),   sc("🔧 Stub", LGREY, true, AMBER),    sc("Scraper to be built") ]}),
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2340, 2340, 2340, 2340],
    rows
  });
}

function makeFeatureTable() {
  const rows = [
    new TableRow({ children: [
      headerCell("Feature", 3200), headerCell("Status", 1800), headerCell("Notes", 4360)
    ]}),
    // Search
    statusRow("Live product search (Woolworths + Coles)", "✅ Built", "HTMX, debounced, per-store filter"),
    statusRow("Store filter tabs on search page",         "✅ Built", "All / Woolworths / Coles / Harris Farm / IGA"),
    statusRow("Harris Farm & IGA search results",         "📋 Planned", "Scrapers not yet written"),
    statusRow("Product detail page + price history",      "✅ Built", "SVG sparkline chart"),
    // Watchlist
    statusRow("Add product to watchlist",                 "✅ Built", "One-click from search results"),
    statusRow("Remove product from watchlist",            "✅ Built", "HTMX inline, no page reload"),
    statusRow("Edit alert thresholds per product",        "✅ Built", "Drop % or fixed price threshold"),
    statusRow("Watchlist page with current prices",       "✅ Built", "Sparklines, specials badge"),
    // Dashboard
    statusRow("Dashboard with price summary",             "✅ Built", "Drops today, specials count, watchlist count"),
    statusRow("Price sparklines (14-day)",                "✅ Built", "Inline SVG in all list views"),
    // Notifications
    statusRow("Email notification (SMTP)",                "🔧 Partial", "Settings saved, send logic to be wired"),
    statusRow("Push notification via ntfy.sh",            "🔧 Partial", "Settings saved, send logic to be wired"),
    statusRow("Daily digest email",                       "📋 Planned", "Scheduler + email template needed"),
    statusRow("Immediate alert on price drop",            "📋 Planned", "Triggered after each scrape run"),
    statusRow("Back-in-stock alert",                      "📋 Planned", "PriceRecord.in_stock transition"),
    // Settings
    statusRow("Notification settings page",              "✅ Built", "Email, push, frequency, quiet hours, days"),
    statusRow("Global minimum drop % threshold",         "✅ Built", "Saved in NotificationSettings"),
    statusRow("Quiet hours (no alerts between X-Y)",     "✅ Built", "Stored, enforcement logic pending"),
    statusRow("Notify days of week selection",           "✅ Built", "Mon-Sun checkboxes"),
    // Scheduler
    statusRow("Scheduled price polling (cron-like)",      "📋 Planned", "manage.py fetch_prices to be scheduled"),
    statusRow("Alert evaluation engine",                  "📋 Planned", "Compare new vs previous price records"),
    statusRow("Email preview / test send button",         "🔧 Partial", "Template exists, not wired to SMTP"),
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3200, 1800, 4360],
    rows
  });
}

function makeSchemaTable() {
  function schemaRow(table, fields, purpose) {
    return new TableRow({ children: [
      cell(table,   { bold: true, fill: LGREY, width: 2200, size: 19 }),
      cell(fields,  { italic: true, color: "444444", width: 4360, size: 18 }),
      cell(purpose, { width: 2800, size: 19 })
    ]});
  }
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2200, 4360, 2800],
    rows: [
      new TableRow({ children: [
        headerCell("Table", 2200), headerCell("Key Fields", 4360), headerCell("Purpose", 2800)
      ]}),
      schemaRow("products", "id, name, store, external_id, url, image_url, unit", "One row per store product"),
      schemaRow("price_history", "product_id, price, was_price, in_stock, on_special, scraped_at", "Time-series price log"),
      schemaRow("watchlist", "product_id, alert_drop_pct, alert_price_below, notify_email, notify_push", "User&#x2019;s tracked items"),
      schemaRow("alert_events", "watchlist_entry_id, trigger_type, old_price, new_price, triggered_at, notified_at", "Audit log of fired alerts"),
      schemaRow("notification_settings", "email_address, digest_frequency, notify_hour, notify_days, ntfy_topic, quiet_hours_*", "Singleton config row"),
    ]
  });
}

function makeStackTable() {
  function stackRow(layer, tech, notes) {
    return new TableRow({ children: [
      cell(layer, { bold: true, fill: LGREY, width: 2000, size: 20 }),
      cell(tech,  { width: 3000, size: 20 }),
      cell(notes, { italic: true, color: "555555", width: 4360, size: 20 })
    ]});
  }
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2000, 3000, 4360],
    rows: [
      new TableRow({ children: [
        headerCell("Layer", 2000), headerCell("Technology", 3000), headerCell("Notes", 4360)
      ]}),
      stackRow("Web framework", "FastAPI (Python 3.11+)", "Async, runs via Uvicorn"),
      stackRow("Frontend interaction", "HTMX 1.9 + Alpine.js 3", "No JavaScript bundle needed"),
      stackRow("Styling", "Tailwind CSS (CDN)", "Utility-first, responsive"),
      stackRow("Database", "SQLite via SQLAlchemy 2", "File: prices.db — swap for Postgres if multi-user"),
      stackRow("Scrapers", "httpx (async HTTP)", "JSON product APIs for Woolworths and Coles"),
      stackRow("Notifications (email)", "Python smtplib / SMTP", "Credentials in .env"),
      stackRow("Notifications (push)", "ntfy.sh (free, open-source)", "No account needed"),
      stackRow("Scheduling", "manage.py CLI", "To be wired to OS cron / Windows Task Scheduler"),
      stackRow("Dev environment", "Miniconda3 (base env)", "Windows — C:\\Users\\kalae\\"),
    ]
  });
}

function makeApiTable() {
  function apiRow(method, path, purpose) {
    const mColor = method === "GET" ? "1E3A5F" : "166534";
    return new TableRow({ children: [
      cell(method, { bold: true, color: mColor, fill: LGREY, width: 800, size: 19 }),
      cell(path,   { bold: true, width: 3600, size: 19 }),
      cell(purpose,{ width: 4960, size: 19 })
    ]});
  }
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [800, 3600, 4960],
    rows: [
      new TableRow({ children: [
        headerCell("Method", 800), headerCell("Path", 3600), headerCell("Description", 4960)
      ]}),
      // Pages
      apiRow("GET",  "/",                            "Dashboard — watchlist summary, drops today, specials"),
      apiRow("GET",  "/search?q=&store=",            "Search page with store filter"),
      apiRow("GET",  "/watchlist",                   "Full watchlist with sparklines and alert settings"),
      apiRow("GET",  "/settings",                    "Notification settings form"),
      apiRow("GET",  "/product/{id}",                "Product detail + full price history chart"),
      // Partials
      apiRow("GET",  "/partials/search-results",     "HTMX: live search results cards"),
      apiRow("POST", "/partials/watchlist/add",      "HTMX: add product; returns updated watchlist row"),
      apiRow("POST", "/partials/watchlist/{id}/delete", "HTMX: remove product from watchlist"),
      apiRow("GET",  "/partials/watchlist/{id}/edit",   "HTMX: inline edit form for alert thresholds"),
      apiRow("POST", "/partials/watchlist/{id}/edit",   "HTMX: save alert thresholds"),
      apiRow("POST", "/settings/save",               "HTMX: persist notification settings"),
      // Planned
      apiRow("POST", "/api/fetch-prices",            "📋 Planned: trigger a manual scrape run"),
      apiRow("POST", "/api/send-test-email",         "📋 Planned: send a test digest email"),
    ]
  });
}

// ── Document ──────────────────────────────────────────────────────────────────
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 20, color: BLACK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 36, bold: true, font: "Arial", color: GREEN },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run:       { size: 26, bold: true, font: "Arial", color: BLACK },
        paragraph: { spacing: { before: 280, after: 80 }, outlineLevel: 1 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 540, hanging: 260 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 900, hanging: 260 } } } },
        ]
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
      }
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: MGREY } },
        children: [
          new TextRun({ text: "Supermarket Price Tracker — Requirements Document", size: 18, color: "555555", font: "Arial" }),
          new TextRun({ text: "\tDRAFT  v0.1  |  March 2026", size: 18, color: "888888", font: "Arial" }),
        ],
        tabStops: [{ type: "right", position: 9360 }]
      })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: MGREY } },
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "Page ", size: 18, color: "888888", font: "Arial" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888", font: "Arial" }),
          new TextRun({ text: " of ", size: 18, color: "888888", font: "Arial" }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: "888888", font: "Arial" }),
        ]
      })] })
    },
    children: [

      // ── TITLE BLOCK ──────────────────────────────────────────────────────
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "Supermarket Price Tracker", bold: true, size: 56, color: GREEN, font: "Arial" })]
      }),
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "Product Requirements Document", size: 28, color: "444444", font: "Arial" })]
      }),
      new Paragraph({
        spacing: { before: 0, after: 240 },
        children: [new TextRun({ text: "Version 0.1  |  Draft for review  |  March 2026", size: 20, italic: true, color: "888888", font: "Arial" })]
      }),
      rule(),

      // ── 1. PURPOSE ───────────────────────────────────────────────────────
      h1("1. Purpose & Scope"),
      body("This document describes the requirements for a personal web application that monitors supermarket product prices, stores price history, and sends scheduled email and push notifications when prices drop or products go on special."),
      gap(),
      body("The app is a single-user tool running locally on Windows (Miniconda3 environment). It is not a public-facing SaaS product."),
      gap(),

      h2("Target Supermarkets"),
      body("Coverage is limited to stores in and around North Sydney, Milsons Point, Crows Nest, and Cammeray, NSW, Australia:"),
      bullet("Woolworths — online store (ships to area) ✅ Live"),
      bullet("Coles — online store (ships to area) ✅ Live"),
      bullet("Harris Farm Markets — Cammeray & Crows Nest 🔧 Scraper pending"),
      bullet("IGA Crows Nest 🔧 Scraper pending"),
      bullet("IGA Milsons Point 🔧 Scraper pending"),
      bullet("IGA North Sydney 🔧 Scraper pending"),
      gap(),

      // ── 2. STORES TABLE ──────────────────────────────────────────────────
      h1("2. Store Coverage"),
      makeStoresTable(),
      gap(2),

      // ── 3. FEATURE STATUS ────────────────────────────────────────────────
      h1("3. Feature Status"),
      body("Legend:  ✅ Built = working code in production   🔧 Partial = scaffolding exists, logic incomplete   📋 Planned = not yet started"),
      gap(),
      makeFeatureTable(),
      gap(2),

      // ── 4. DETAILED REQUIREMENTS ─────────────────────────────────────────
      h1("4. Detailed Requirements"),

      h2("4.1  Search"),
      bullet("The user can type a product name (e.g. &#x201C;olive oil&#x201D;, &#x201C;eggs&#x201D;) into a search box."),
      bullet("Results appear as the user types (debounced at 350 ms)."),
      bullet("Results show: product image, name, current price, unit price, store badge, on-special indicator."),
      bullet("A store filter tab allows narrowing to one store or viewing all."),
      bullet("Any result card can be added to the watchlist with one click."),
      gap(),

      h2("4.2  Watchlist"),
      bullet("Products added to the watchlist are stored locally in SQLite."),
      bullet("Each watchlist entry can have:"),
      bullet("Alert on price drop by % (e.g. alert when price drops 10%+)", 1),
      bullet("Alert when price falls below a fixed dollar threshold", 1),
      bullet("Email notification toggle", 1),
      bullet("Push notification toggle", 1),
      bullet("The watchlist page shows current price, previous price, % change, and a 14-day sparkline."),
      bullet("Products on special are highlighted with a badge."),
      gap(),

      h2("4.3  Price History"),
      bullet("Each time prices are fetched the result is appended to price_history table (never overwritten)."),
      bullet("Product detail page shows a full SVG line chart of historical prices."),
      bullet("The scraper records: current price, was-price (if on special), in_stock, on_special, scrape_error."),
      gap(),

      h2("4.4  Notifications — Email"),
      bullet("A single recipient email address is configured in Settings."),
      bullet("Frequency options: Immediate (on each scrape), Daily digest, Weekly digest."),
      bullet("Send time: user-configurable hour (0-23) and days of week."),
      bullet("Quiet hours: no notifications sent between configured start and end hour."),
      bullet("Global minimum drop %: no alert fires unless the drop exceeds this threshold."),
      bullet("The daily/weekly digest email lists all watched products with price changes, specials, and back-in-stock items."),
      bullet("SMTP credentials are stored in .env (not committed to source control)."),
      gap(),

      h2("4.5  Notifications — Push (ntfy.sh)"),
      bullet("Uses ntfy.sh (free, self-hostable) — no account required."),
      bullet("User configures an ntfy topic name and optional custom server URL."),
      bullet("The same frequency, quiet hours, and global threshold settings apply."),
      bullet("Push messages include: product name, store, old price, new price, and a link."),
      gap(),

      h2("4.6  Price Polling / Scheduler"),
      bullet("manage.py fetch_prices command scrapes all watched products on demand."),
      bullet("This command is intended to be wired to Windows Task Scheduler or OS cron."),
      bullet("Recommended polling interval: once or twice per day."),
      bullet("After each scrape run, the alert evaluation engine compares new vs previous prices and fires any pending alerts."),
      gap(),

      h2("4.7  Settings Page"),
      bullet("Single settings page configures all notification preferences:"),
      bullet("Recipient email address", 1),
      bullet("Digest frequency (immediate / daily / weekly)", 1),
      bullet("Send hour and days of week", 1),
      bullet("Quiet hours start and end", 1),
      bullet("Global minimum drop % (default 5%)", 1),
      bullet("Back-in-stock alerts toggle", 1),
      bullet("On-special alerts toggle", 1),
      bullet("ntfy.sh topic and server URL", 1),
      bullet("Push notification toggle", 1),
      bullet("Settings are saved via HTMX with instant feedback (no page reload)."),
      gap(2),

      // ── 5. TECHNICAL STACK ───────────────────────────────────────────────
      h1("5. Technical Stack"),
      makeStackTable(),
      gap(2),

      // ── 6. DATABASE SCHEMA ───────────────────────────────────────────────
      h1("6. Database Schema (SQLite)"),
      makeSchemaTable(),
      gap(),
      body("The database file is prices.db in the project root. To migrate to PostgreSQL, change the DATABASE_URL in .env — SQLAlchemy handles the rest."),
      gap(2),

      // ── 7. API ROUTES ────────────────────────────────────────────────────
      h1("7. API Routes"),
      makeApiTable(),
      gap(2),

      // ── 8. OUTSTANDING WORK ──────────────────────────────────────────────
      h1("8. Outstanding Work (Priority Order)"),

      h3("High Priority"),
      bullet("Wire SMTP send logic — connect NotificationSettings to smtplib, test with Gmail/Outlook."),
      bullet("Wire ntfy.sh send logic — HTTP POST to ntfy topic on alert trigger."),
      bullet("Alert evaluation engine — post-scrape comparison: price_drop, below_threshold, back_in_stock."),
      bullet("Schedule manage.py fetch_prices via Windows Task Scheduler (or cron on WSL)."),
      gap(),

      h3("Medium Priority"),
      bullet("Harris Farm scraper — Cammeray and Crows Nest store pages."),
      bullet("IGA scrapers (x3) — Crows Nest, Milsons Point, North Sydney."),
      bullet("Daily digest email template — HTML email listing all watchlist changes."),
      bullet("Test send button on settings page — sends a sample digest immediately."),
      gap(),

      h3("Lower Priority / Nice to Have"),
      bullet("Price drop percentage badge on dashboard cards."),
      bullet("Search history / recently searched suggestions."),
      bullet("Bulk import watchlist from a CSV."),
      bullet("Compare the same product across stores side-by-side."),
      bullet("Multiple user profiles or family sharing (requires auth layer)."),
      bullet("Mobile PWA — add to home screen for push-like experience."),
      bullet("Auto-detect store by postcode rather than fixed store list."),
      gap(2),

      // ── 9. OPEN QUESTIONS ────────────────────────────────────────────────
      h1("9. Open Questions & Decisions Needed"),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [400, 4480, 4480],
        rows: [
          new TableRow({ children: [
            headerCell("#", 400), headerCell("Question", 4480), headerCell("Options / Notes", 4480)
          ]}),
          new TableRow({ children: [
            cell("1", { fill: LGREY, width: 400 }),
            cell("Which email provider to use for sending?", { width: 4480 }),
            cell("Gmail App Password, Outlook SMTP, SendGrid free tier, Mailjet", { italic: true, color: "555555", width: 4480 })
          ]}),
          new TableRow({ children: [
            cell("2", { fill: LGREY, width: 400 }),
            cell("Should Harris Farm and IGA prices be scraped from store web pages, or is there an API?", { width: 4480 }),
            cell("Likely HTML scraping via httpx + BeautifulSoup. Rate-limit considerations apply.", { italic: true, color: "555555", width: 4480 })
          ]}),
          new TableRow({ children: [
            cell("3", { fill: LGREY, width: 400 }),
            cell("How often should prices be fetched?", { width: 4480 }),
            cell("Once daily (e.g. 7am) is likely sufficient. Twice daily (7am + 5pm) catches specials faster.", { italic: true, color: "555555", width: 4480 })
          ]}),
          new TableRow({ children: [
            cell("4", { fill: LGREY, width: 400 }),
            cell("Should the SQLite database be backed up automatically?", { width: 4480 }),
            cell("Simple: daily copy of prices.db to a backup folder. Or use Google Drive sync.", { italic: true, color: "555555", width: 4480 })
          ]}),
          new TableRow({ children: [
            cell("5", { fill: LGREY, width: 400 }),
            cell("Do you want price alerts for specific pack sizes (e.g. 500ml vs 1L)?", { width: 4480 }),
            cell("Currently tracked at product SKU level — same SKU = same size. Confirm this is sufficient.", { italic: true, color: "555555", width: 4480 })
          ]}),
          new TableRow({ children: [
            cell("6", { fill: LGREY, width: 400 }),
            cell("Should alerts fire on every price drop, or only once per day per product?", { width: 4480 }),
            cell("Immediate mode fires each scrape cycle. Daily digest batches them. Preference?", { italic: true, color: "555555", width: 4480 })
          ]}),
        ]
      }),
      gap(2),

      // ── 10. FILE STRUCTURE ───────────────────────────────────────────────
      h1("10. Project File Structure"),
      new Paragraph({
        spacing: { before: 60, after: 60 },
        children: [new TextRun({
          text: [
            "supermarket-price-tracker/",
            "  app/",
            "    main.py              ← FastAPI app, all routes",
            "    models.py            ← SQLAlchemy models",
            "    database.py          ← SQLite session setup",
            "    config.py            ← Settings from .env",
            "    scrapers/",
            "      base.py            ← Shared scraper base class",
            "      woolworths.py      ← Live Woolworths scraper",
            "      coles.py           ← Live Coles scraper",
            "      harris_farm.py     ← [TO DO] stub",
            "      iga_*.py           ← [TO DO] stubs",
            "    notifiers/",
            "      __init__.py        ← [TO DO] email + push logic",
            "    templates/",
            "      base.html          ← Layout, nav, CDN includes",
            "      dashboard.html     ← Home / overview",
            "      search.html        ← Product search + store filter",
            "      watchlist.html     ← Watched products list",
            "      settings.html      ← Notification preferences",
            "      product_detail.html← Price history chart",
            "      partials/          ← HTMX fragments",
            "  manage.py             ← CLI: fetch_prices, init_db",
            "  prices.db             ← SQLite database (gitignored)",
            "  .env                  ← Secrets (gitignored)",
            "  requirements.txt",
          ].join("\n"),
          size: 18, font: "Courier New", color: "1A1A1A"
        })]
      }),
      gap(2),

      // ── SIGN-OFF ─────────────────────────────────────────────────────────
      rule(),
      new Paragraph({
        spacing: { before: 120, after: 40 },
        children: [new TextRun({ text: "Review & Sign-off", bold: true, size: 22, font: "Arial" })]
      }),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3120, 3120, 3120],
        rows: [
          new TableRow({ children: [
            headerCell("Name", 3120), headerCell("Role", 3120), headerCell("Date", 3120)
          ]}),
          new TableRow({ children: [
            cell("", { width: 3120 }), cell("Owner / Developer", { width: 3120 }), cell("", { width: 3120 })
          ]}),
        ]
      }),
      gap(),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("SupermarketPriceTracker_Requirements_v0.1.docx", buf);
  console.log("Written OK — size:", buf.length, "bytes");
}).catch(e => { console.error("ERROR:", e.message); process.exit(1); });
