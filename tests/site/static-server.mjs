import { createServer } from "node:http";
import { spawnSync } from "node:child_process";
import { readFileSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";

const host = "127.0.0.1";
const port = 4173;
const root = resolve("site/generated");
const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
  [".woff2", "font/woff2"],
]);

function mimeType(path) {
  for (const [extension, type] of contentTypes) {
    if (path.endsWith(extension)) return type;
  }
  return "application/octet-stream";
}

function buildSite(releaseSha) {
  const result = spawnSync(
    process.platform === "win32" ? "python" : "python3",
    ["scripts/build_preview_site.py", "--output", root, "--release-sha", releaseSha],
    { encoding: "utf8" },
  );
  if (result.status !== 0) {
    process.stderr.write(result.stderr || result.stdout || "Academy site build failed.\n");
    process.exit(result.status || 1);
  }
}

if (process.argv.includes("--build")) {
  const position = process.argv.indexOf("--release-sha");
  const releaseSha = position >= 0 ? process.argv[position + 1] : undefined;
  if (!/^[0-9a-f]{40}$/.test(releaseSha ?? "")) {
    throw new Error("visual static server requires a lowercase 40-character release SHA");
  }
  buildSite(releaseSha);
}

createServer((request, response) => {
  const requested = new URL(request.url ?? "/", `http://${host}`).pathname;
  const relative = decodeURIComponent(requested === "/" ? "/index.html" : requested).replace(/^[/\\]+/, "");
  const candidate = resolve(root, relative);
  if (candidate !== root && !candidate.startsWith(`${root}${sep}`)) {
    response.writeHead(403).end();
    return;
  }
  try {
    if (!statSync(candidate).isFile()) throw new Error("not a file");
    response.writeHead(200, { "content-type": mimeType(candidate), "cache-control": "no-store" });
    response.end(readFileSync(candidate));
  } catch {
    response.writeHead(404).end();
  }
}).listen(port, host, () => {
  process.stdout.write(`Academy visual server listening on http://${host}:${port}\n`);
});
