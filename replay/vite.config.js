import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, resolve, sep } from "node:path";
import { defineConfig } from "vite";

// Replays live outside the app in data/replays; serve them read-only at /replays/.
const REPLAYS = resolve(import.meta.dirname, "../data/replays");
const TYPES = { ".json": "application/json", ".glb": "model/gltf-binary" };

function serveReplays() {
  const handler = (req, res, next) => {
    const url = decodeURIComponent(req.url.split("?")[0]);
    if (!url.startsWith("/replays/")) return next();
    const file = resolve(REPLAYS, "." + url.slice("/replays".length));
    if (!file.startsWith(REPLAYS + sep) || !existsSync(file) || !statSync(file).isFile()) {
      res.statusCode = 404;
      return res.end("not found");
    }
    res.setHeader("Content-Type", TYPES[extname(file)] || "application/octet-stream");
    res.setHeader("Cache-Control", "no-cache");
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
