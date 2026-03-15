import { readdir, stat } from "node:fs/promises";
import path from "node:path";

const DIST_DIR = path.resolve(process.cwd(), "dist/assets");
const MAX_MAIN_BUNDLE_BYTES = Number(process.env.MAX_MAIN_BUNDLE_BYTES || 250_000);
const MAX_LAZY_BUNDLE_BYTES = Number(process.env.MAX_LAZY_BUNDLE_BYTES || 5_500_000);

const files = await readdir(DIST_DIR);
const jsFiles = files.filter((f) => f.endsWith(".js"));
if (jsFiles.length === 0) {
  throw new Error("No JS bundles found in dist/assets");
}

const sized = [];
for (const file of jsFiles) {
  const full = path.join(DIST_DIR, file);
  const info = await stat(full);
  sized.push({ file, size: info.size });
}

sized.sort((a, b) => b.size - a.size);
const mainChunk = sized.find((x) => x.file.startsWith("index-"));
if (!mainChunk) {
  throw new Error("Main index chunk not found");
}
console.log("Main bundle:", mainChunk.file, mainChunk.size, "bytes");
if (mainChunk.size > MAX_MAIN_BUNDLE_BYTES) {
  throw new Error(
    `Main bundle budget exceeded: ${mainChunk.size} > ${MAX_MAIN_BUNDLE_BYTES}. ` +
      "Reduce bundle size or increase MAX_MAIN_BUNDLE_BYTES intentionally."
  );
}

const lazyChunks = sized.filter((x) => !x.file.startsWith("index-"));
for (const chunk of lazyChunks) {
  if (chunk.size > MAX_LAZY_BUNDLE_BYTES) {
    throw new Error(
      `Lazy chunk budget exceeded (${chunk.file}): ${chunk.size} > ${MAX_LAZY_BUNDLE_BYTES}. ` +
        "Split large chart bundles further."
    );
  }
}
