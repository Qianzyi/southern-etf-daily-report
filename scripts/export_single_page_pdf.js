const fs = require("fs");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");
const { spawn } = require("child_process");

function usage() {
  console.error("Usage: node export_single_page_pdf.js <input.html> <output.pdf> [--chrome <path>]");
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const positional = [];
  let chrome = process.env.CHROME_EXE || "";
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--chrome") {
      chrome = args[i + 1] || "";
      i += 1;
    } else {
      positional.push(args[i]);
    }
  }
  if (positional.length < 2) {
    usage();
    process.exit(2);
  }
  return {
    htmlPath: path.resolve(positional[0]),
    pdfPath: path.resolve(positional[1]),
    chromePath: chrome || findBrowser(),
  };
}

function findBrowser() {
  const candidates = process.platform === "win32"
    ? [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
      ]
    : [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
      ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    throw new Error("Chrome or Edge was not found. Set CHROME_EXE to the browser executable path.");
  }
  return found;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(url, timeoutMs = 10000) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return await response.json();
      }
      lastError = new Error(`${response.status} ${response.statusText}`);
    } catch (error) {
      lastError = error;
    }
    await delay(120);
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
}

function connect(wsUrl) {
  const socket = new WebSocket(wsUrl);
  const pending = new Map();
  const events = [];
  let nextId = 1;

  socket.addEventListener("message", (message) => {
    const payload = JSON.parse(message.data);
    if (payload.id && pending.has(payload.id)) {
      const { resolve, reject } = pending.get(payload.id);
      pending.delete(payload.id);
      if (payload.error) {
        reject(new Error(JSON.stringify(payload.error)));
      } else {
        resolve(payload.result || {});
      }
    } else if (payload.method) {
      events.push(payload);
    }
  });

  function command(method, params = {}) {
    const id = nextId++;
    const body = JSON.stringify({ id, method, params });
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      socket.send(body);
    });
  }

  function waitForEvent(method, timeoutMs = 15000) {
    const existingIndex = events.findIndex((event) => event.method === method);
    if (existingIndex >= 0) {
      const [event] = events.splice(existingIndex, 1);
      return Promise.resolve(event);
    }
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = setInterval(() => {
        const index = events.findIndex((event) => event.method === method);
        if (index >= 0) {
          clearInterval(timer);
          const [event] = events.splice(index, 1);
          resolve(event);
        } else if (Date.now() - started >= timeoutMs) {
          clearInterval(timer);
          reject(new Error(`Timed out waiting for ${method}`));
        }
      }, 80);
    });
  }

  return new Promise((resolve, reject) => {
    socket.addEventListener("open", () => resolve({ socket, command, waitForEvent }));
    socket.addEventListener("error", reject);
  });
}

function countPdfPages(buffer) {
  const text = buffer.toString("latin1");
  const matches = text.match(/\/Type\s*\/Page\b/g);
  return matches ? matches.length : 0;
}

function createJpegPdf(jpegBuffer, widthPx, heightPx) {
  const widthPt = widthPx * 0.75;
  const heightPt = heightPx * 0.75;
  const content = Buffer.from(`q\n${widthPt.toFixed(3)} 0 0 ${heightPt.toFixed(3)} 0 0 cm\n/Im0 Do\nQ\n`, "ascii");
  const chunks = [];
  const offsets = [0];
  let offset = 0;

  function push(data) {
    const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data, "ascii");
    chunks.push(buffer);
    offset += buffer.length;
  }

  function object(id, body) {
    offsets[id] = offset;
    push(`${id} 0 obj\n${body}\nendobj\n`);
  }

  push("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  object(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${widthPt.toFixed(3)} ${heightPt.toFixed(3)}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);

  offsets[4] = offset;
  push(`4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${widthPx} /Height ${heightPx} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBuffer.length} >>\nstream\n`);
  push(jpegBuffer);
  push("\nendstream\nendobj\n");

  offsets[5] = offset;
  push(`5 0 obj\n<< /Length ${content.length} >>\nstream\n`);
  push(content);
  push("endstream\nendobj\n");

  const xrefOffset = offset;
  push("xref\n0 6\n0000000000 65535 f \n");
  for (let i = 1; i <= 5; i += 1) {
    push(`${String(offsets[i]).padStart(10, "0")} 00000 n \n`);
  }
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`);
  return Buffer.concat(chunks);
}

async function exportPdf({ htmlPath, pdfPath, chromePath }) {
  if (!fs.existsSync(htmlPath)) {
    throw new Error(`HTML input does not exist: ${htmlPath}`);
  }
  if (!fs.existsSync(chromePath)) {
    throw new Error(`Chrome executable does not exist: ${chromePath}`);
  }

  fs.mkdirSync(path.dirname(pdfPath), { recursive: true });
  const port = 45000 + Math.floor(Math.random() * 10000);
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "southern-etf-pdf-"));
  const chrome = spawn(chromePath, [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-web-security",
    "--font-render-hinting=medium",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "about:blank",
  ], { stdio: "ignore" });

  try {
    const tabs = await waitForJson(`http://127.0.0.1:${port}/json/list`);
    const tab = tabs.find((item) => item.type === "page") || tabs[0];
    if (!tab || !tab.webSocketDebuggerUrl) {
      throw new Error("Unable to find a debuggable Chrome page.");
    }

    const client = await connect(tab.webSocketDebuggerUrl);
    await client.command("Page.enable");
    await client.command("Runtime.enable");
    const loadEvent = client.waitForEvent("Page.loadEventFired");
    await client.command("Page.navigate", { url: pathToFileURL(htmlPath).href });
    await loadEvent;
    await client.command("Runtime.evaluate", {
      expression: "(async () => { if (document.fonts && document.fonts.ready) await document.fonts.ready; return true; })()",
      awaitPromise: true,
    });
    await client.command("Runtime.evaluate", {
      expression: `(() => {
        const existing = document.getElementById('single-page-pdf-print-override');
        if (existing) existing.remove();
        const style = document.createElement('style');
        style.id = 'single-page-pdf-print-override';
        style.textContent = \`
          @page { margin: 0 !important; }
          @media print {
            html, body {
              margin: 0 !important;
              width: 1440px !important;
              background: #eef3f8 !important;
              -webkit-print-color-adjust: exact !important;
              print-color-adjust: exact !important;
            }
            .page {
              max-width: 1400px !important;
              margin: 18px auto 32px !important;
              padding: 0 24px !important;
            }
            .hero {
              display: grid !important;
              grid-template-columns: 1.2fr auto !important;
            }
            .grid-2, .summary-grid, .trend-grid, .flow-grid {
              display: grid !important;
              grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            }
            .grid-3, .manager-grid {
              display: grid !important;
              grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            }
            .kpis {
              display: grid !important;
              grid-template-columns: repeat(5, 1fr) !important;
            }
            .meta { text-align: right !important; white-space: nowrap !important; }
            footer { display: block !important; }
          }
        \`;
        document.head.appendChild(style);
        return true;
      })()`,
    });
    await client.command("Emulation.setEmulatedMedia", { media: "screen" });

    const measured = await client.command("Runtime.evaluate", {
      expression: `(() => {
        const el = document.querySelector('.page') || document.body;
        const rect = el.getBoundingClientRect();
        const maxElementBottom = Array.from(document.body.querySelectorAll('*')).reduce((max, node) => {
          const box = node.getBoundingClientRect();
          return Math.max(max, box.bottom + window.scrollY);
        }, rect.bottom + window.scrollY);
        const styles = getComputedStyle(el);
        const marginTop = parseFloat(styles.marginTop) || 0;
        const marginBottom = parseFloat(styles.marginBottom) || 0;
        const width = Math.ceil(Math.max(1440, document.documentElement.scrollWidth, document.body.scrollWidth, rect.width + 64));
        const height = Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, maxElementBottom + marginBottom + 16, rect.height + marginTop + marginBottom + 16));
        return { width, height };
      })()`,
      returnByValue: true,
    });
    const metrics = measured.result.value;
    const widthPx = Math.max(1440, metrics.width);
    const heightPx = Math.max(900, metrics.height);

    await client.command("Emulation.setDeviceMetricsOverride", {
      width: widthPx,
      height: Math.min(heightPx, 12000),
      deviceScaleFactor: 1,
      mobile: false,
    });

    const finalMeasured = await client.command("Runtime.evaluate", {
      expression: `(() => {
        const el = document.querySelector('.page') || document.body;
        const rect = el.getBoundingClientRect();
        const styles = getComputedStyle(el);
        const marginBottom = parseFloat(styles.marginBottom) || 0;
        const maxElementBottom = Array.from(document.body.querySelectorAll('*')).reduce((max, node) => {
          const box = node.getBoundingClientRect();
          return Math.max(max, box.bottom + window.scrollY);
        }, rect.bottom + window.scrollY);
        return Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, maxElementBottom + marginBottom + 12));
      })()`,
      returnByValue: true,
    });
    const finalHeightPx = Math.max(900, finalMeasured.result.value + 8);
    const screenshot = await client.command("Page.captureScreenshot", {
      format: "jpeg",
      quality: 96,
      fromSurface: true,
      captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: widthPx, height: finalHeightPx, scale: 1 },
    });
    const jpegBuffer = Buffer.from(screenshot.data, "base64");
    const outputBuffer = createJpegPdf(jpegBuffer, widthPx, finalHeightPx);
    const pageCount = countPdfPages(outputBuffer);
    fs.writeFileSync(pdfPath, outputBuffer);
    client.socket.close();
    return { pdf: pdfPath, width: widthPx, height: finalHeightPx, pages: pageCount, bytes: fs.statSync(pdfPath).size };
  } finally {
    chrome.kill();
    await new Promise((resolve) => {
      chrome.once("exit", resolve);
      setTimeout(resolve, 1200);
    });
    for (let attempt = 0; attempt < 5; attempt += 1) {
      try {
        fs.rmSync(profileDir, { recursive: true, force: true });
        break;
      } catch (error) {
        if (attempt === 4) {
          console.error(`Warning: unable to remove temporary Chrome profile ${profileDir}: ${error.message}`);
        } else {
          await delay(250);
        }
      }
    }
  }
}

exportPdf(parseArgs(process.argv))
  .then((result) => console.log(JSON.stringify(result, null, 2)))
  .catch((error) => {
    console.error(error && error.stack ? error.stack : error);
    process.exit(1);
  });
