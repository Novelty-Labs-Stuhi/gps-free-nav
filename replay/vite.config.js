import { createReadStream, existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, resolve, sep } from "node:path";
import { defineConfig } from "vite";
import { runSummary } from "./src/summary.js";

// Replays live outside the app in data/replays; serve them read-only at /replays/.
const REPLAYS = resolve(import.meta.dirname, "../data/replays");
const TYPES = { ".json": "application/json", ".glb": "model/gltf-binary" };

// /replays/index.json is built here from the folders themselves, so every run shows up with its summary
// no matter which exporter wrote it. Summaries are cached by replay.json mtime + size.
const cache = new Map();
function buildIndex() {
  const runs = [];
  for (const exp of existsSync(REPLAYS) ? readdirSync(REPLAYS) : []) {
    const dir = join(REPLAYS, exp);
    if (!statSync(dir).isDirectory()) continue;
    for (const run of readdirSync(dir)) {
      const file = join(dir, run, "replay.json");
      if (!existsSync(file)) continue;
      const id = `${exp}/${run}`, st = statSync(file), stamp = `${st.mtimeMs}:${st.size}`;
      let hit = cache.get(id);
      if (hit?.stamp !== stamp) {
        try {
          const R = JSON.parse(readFileSync(file, "utf8"));
          hit = { stamp, entry: { id, experiment: R.experiment ?? exp, scenario: R.scenario ?? "–", world: R.world ?? "–", run_id: R.run_id ?? run, ...runSummary(R) } };
        } catch (err) {
          console.warn(`replay index: skipping summary for ${id}: ${err.message}`);
          hit = { stamp, entry: { id, experiment: exp, scenario: "–", world: "–", run_id: run } };
        }
        cache.set(id, hit);
      }
      runs.push(hit.entry);
    }
  }
  return runs.sort((a, b) => a.id.localeCompare(b.id));
}

function serveReplays() {
  const handler = (req, res, next) => {
    const url = decodeURIComponent(req.url.split("?")[0]);
    if (!url.startsWith("/replays/")) return next();
    res.setHeader("Cache-Control", "no-cache");
    if (url === "/replays/index.json") {
      res.setHeader("Content-Type", "application/json");
      return res.end(JSON.stringify(buildIndex()));
    }
    const file = resolve(REPLAYS, "." + url.slice("/replays".length));
    if (!file.startsWith(REPLAYS + sep) || !existsSync(file) || !statSync(file).isFile()) {
      res.statusCode = 404;
      return res.end("not found");
    }
    res.setHeader("Content-Type", TYPES[extname(file)] || "application/octet-stream");
    createReadStream(file).pipe(res);
  };
  return {
    name: "serve-replays",
    configureServer: (server) => void server.middlewares.use(handler),
    configurePreviewServer: (server) => void server.middlewares.use(handler),
  };
}

export default defineConfig({
  plugins: [serveReplays()],
  server: { port: 5174 },
  build: { target: "es2022" },
});
